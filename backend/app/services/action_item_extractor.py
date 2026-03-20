"""
Action item extraction using GPT-4o-mini.

Called automatically after a document is processed by the RAG pipeline.
Errors are logged but never surface to the caller — document processing
succeeds regardless of whether action item extraction works.
"""

from __future__ import annotations

import re

import json
import logging
from datetime import date, datetime
from uuid import UUID

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Truncate very long documents to stay well under the 128k-token context limit.
# 80 000 chars ≈ 20 000 tokens — leaves ample room for system prompt + response.
_MAX_TEXT_CHARS = 80_000

_SYSTEM_PROMPT = """\
You are an expert at identifying action items, tasks, to-dos, follow-ups, and \
commitments in business documents.

Extract all actionable items that someone needs to act on:
- Explicit tasks ("please send", "need to", "will follow up", "action required")
- Commitments made ("I will", "we will", "they agreed to")
- Deadlines or time-sensitive items
- Documents or information requested

Return a JSON object with a single "items" key containing an array.
Each element must have exactly these keys:
  "text"     : string  — the action item (clear, specific, actionable)
  "due_date" : string or null — ISO date YYYY-MM-DD if a date is mentioned, else null
  "priority" : "low" | "medium" | "high" — based on urgency and importance

If there are no action items return: {"items": []}
"""


async def extract_action_items(
    db: Session,
    document_text: str,
    document_id: UUID,
    client_id: UUID,
    user_id: str | None = None,
) -> list:
    """
    Extract action items from *document_text* and persist them.

    Returns the list of created ActionItem ORM objects (may be empty).
    Never raises — errors are logged and an empty list is returned.
    """
    from openai import AsyncOpenAI
    from app.core.config import get_settings
    from app.models.action_item import ActionItem

    if not document_text.strip():
        return []

    text_for_extraction = document_text[:_MAX_TEXT_CHARS]
    if len(document_text) > _MAX_TEXT_CHARS:
        text_for_extraction += "\n\n[Document truncated for action item extraction]"

    # ── Call GPT-4o-mini ──────────────────────────────────────────────────
    try:
        openai_client = AsyncOpenAI(api_key=get_settings().openai_api_key)
        response = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Extract action items from this document:\n\n"
                        f"{text_for_extraction}"
                    ),
                },
            ],
            temperature=0.1,
            max_tokens=2_000,
            response_format={"type": "json_object"},
        )
    except Exception as exc:
        logger.error(
            "Action item extraction API call failed for document %s: %s",
            document_id,
            exc,
        )
        return []

    # Log token usage for cost tracking
    if user_id:
        try:
            from app.services.token_tracking_service import log_token_usage
            usage = response.usage
            log_token_usage(
                db,
                user_id=user_id,
                client_id=client_id,
                query_type="extraction",
                model="gpt-4o-mini",
                prompt_tokens=usage.prompt_tokens if usage else 0,
                completion_tokens=usage.completion_tokens if usage else 0,
                endpoint="action_items",
            )
        except Exception:
            logger.error("Failed to log action_items token usage", exc_info=True)

    # ── Parse response ────────────────────────────────────────────────────
    raw = response.choices[0].message.content or "{}"

    # Strip markdown code fences that GPT sometimes wraps around JSON
    raw = re.sub(r"^```(?:json)?\s*\n?", "", raw.strip())
    raw = re.sub(r"\n?\s*```$", "", raw.strip())

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error(
            "Failed to parse action items JSON for document %s: %s\nRaw response: %s",
            document_id,
            exc,
            raw[:500],
        )
        return []

    # Accept {"items": [...]} or a bare list (defensive)
    if isinstance(parsed, dict):
        items_raw = parsed.get("items") or parsed.get("action_items") or []
        if not items_raw:
            for v in parsed.values():
                if isinstance(v, list):
                    items_raw = v
                    break
    elif isinstance(parsed, list):
        items_raw = parsed
    else:
        items_raw = []

    if not items_raw:
        logger.info("No action items found in document %s", document_id)
        return []

    # ── Build and persist ORM rows ────────────────────────────────────────
    now = datetime.utcnow()
    created: list[ActionItem] = []

    for raw_item in items_raw:
        if not isinstance(raw_item, dict):
            continue

        text = str(raw_item.get("text", "")).strip()
        if not text:
            continue

        # Parse due date
        due_date: date | None = None
        due_date_str = raw_item.get("due_date")
        if due_date_str:
            try:
                due_date = date.fromisoformat(str(due_date_str))
            except (ValueError, TypeError):
                due_date = None

        # Validate priority
        priority_raw = str(raw_item.get("priority", "")).lower().strip()
        priority = priority_raw if priority_raw in ("low", "medium", "high") else None

        action_item = ActionItem(
            document_id=document_id,
            client_id=client_id,
            text=text,
            status="pending",
            priority=priority,
            due_date=due_date,
            extracted_at=now,
        )
        db.add(action_item)
        created.append(action_item)

    if not created:
        return []

    try:
        db.commit()
        for item in created:
            db.refresh(item)
        logger.info(
            "Extracted %d action item(s) from document %s",
            len(created),
            document_id,
        )
    except Exception as exc:
        logger.error(
            "Failed to save action items for document %s: %s",
            document_id,
            exc,
        )
        db.rollback()
        return []

    return created


async def reextract_action_items(
    db: Session,
    document_id: UUID,
    client_id: UUID,
) -> list:
    """
    Delete existing action items for a document and re-run extraction.

    Callers must supply the document text themselves (already extracted
    during the original processing pass).  This function re-extracts text
    from disk so it can be used for on-demand re-extraction.
    """
    from app.models.action_item import ActionItem
    from app.models.document import Document
    from app.services.text_extraction import extract_text, ExtractionError

    # Fetch the document to get file path and type
    document = db.query(Document).filter(Document.id == document_id).first()
    if document is None:
        logger.warning("reextract_action_items: document %s not found", document_id)
        return []

    # Extract text
    try:
        text = extract_text(document.file_path, document.file_type)
    except ExtractionError as exc:
        logger.error(
            "reextract_action_items: text extraction failed for %s: %s",
            document_id,
            exc,
        )
        return []

    if not text.strip():
        return []

    # Delete existing action items for this document
    try:
        db.query(ActionItem).filter(
            ActionItem.document_id == document_id
        ).delete(synchronize_session=False)
        db.flush()
    except Exception as exc:
        logger.error(
            "reextract_action_items: failed to delete existing items for %s: %s",
            document_id,
            exc,
        )
        db.rollback()
        return []

    return await extract_action_items(db, text, document_id, client_id)

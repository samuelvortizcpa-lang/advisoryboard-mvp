"""
Client brief generator: uses GPT-4o to produce a one-click meeting prep brief.

Gathers documents, action items, and client metadata, then produces a
structured markdown brief suitable for quick pre-meeting review.
"""

from __future__ import annotations

import logging
import time
from uuid import UUID

from openai import AsyncOpenAI
from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.models.action_item import ActionItem
from app.models.client import Client
from app.models.document import Document

logger = logging.getLogger(__name__)

BRIEF_MODEL = "gpt-4o"  # Use GPT-4o for higher quality briefs

BRIEF_SYSTEM_PROMPT = """\
You are an expert CPA meeting preparation assistant. Your job is to create a concise,
actionable client brief that a CPA can review in 2-3 minutes before a meeting.

Produce a well-structured markdown brief with these sections:

## Client Snapshot
A 2-3 sentence executive summary of who this client is and their current situation.

## Key Documents Summary
Summarize the most important documents on file, highlighting critical numbers,
dates, and findings. Group by document type when possible.

## Open Action Items
List pending action items with their priority and due dates.
Flag any overdue items prominently.

## Discussion Points
Based on the documents and action items, suggest 3-5 specific talking points
for the upcoming meeting. Be concrete — reference specific numbers, deadlines,
or documents.

## Risk Flags
Highlight any potential risks, compliance issues, approaching deadlines, or
items that need urgent attention.

Guidelines:
- Be concise and scannable — use bullet points and bold for key figures
- Reference specific document names and dates
- Prioritize actionable information over general summaries
- If data is limited, note gaps and suggest what information to request
- Use professional CPA terminology where appropriate
"""

BRIEF_USER_PROMPT = """\
Generate a meeting prep brief for the following client.

**Client Information:**
{client_info}

**Documents on File ({doc_count} total):**
{documents_summary}

**Pending Action Items ({action_count} total):**
{action_items_summary}
"""


def _openai() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=get_settings().openai_api_key)


def _build_client_info(client: Client) -> str:
    """Build a text summary of client metadata."""
    parts = [f"- Name: {client.name}"]
    if client.business_name:
        parts.append(f"- Business: {client.business_name}")
    if client.entity_type:
        parts.append(f"- Entity Type: {client.entity_type}")
    if client.industry:
        parts.append(f"- Industry: {client.industry}")
    if client.notes:
        parts.append(f"- Notes: {client.notes}")
    if client.client_type:
        parts.append(f"- Client Type: {client.client_type.name}")
    return "\n".join(parts)


def _build_documents_summary(documents: list[Document]) -> str:
    """Build a text summary of all client documents."""
    if not documents:
        return "No documents on file."

    lines: list[str] = []
    for doc in documents:
        line = f"- {doc.filename} ({doc.file_type}, {_format_bytes(doc.file_size)})"
        if doc.document_type and doc.document_type != "other":
            line += f" — Type: {doc.document_type}"
            if doc.document_subtype:
                line += f" ({doc.document_subtype})"
        if doc.document_period:
            line += f" | Period: {doc.document_period}"
        if doc.is_superseded:
            line += " [SUPERSEDED]"
        if not doc.processed:
            line += " [PROCESSING]"
        upload_date = doc.upload_date.strftime("%b %d, %Y") if doc.upload_date else "unknown"
        line += f" | Uploaded: {upload_date}"
        lines.append(line)

    return "\n".join(lines)


def _build_action_items_summary(items: list[ActionItem]) -> str:
    """Build a text summary of pending action items."""
    if not items:
        return "No pending action items."

    lines: list[str] = []
    for item in items:
        priority_tag = f"[{item.priority.upper()}]" if item.priority else "[NONE]"
        due_tag = f" — Due: {item.due_date.strftime('%b %d, %Y')}" if item.due_date else ""
        lines.append(f"- {priority_tag} {item.text}{due_tag}")

    return "\n".join(lines)


def _format_bytes(bytes_val: int) -> str:
    if bytes_val < 1024:
        return f"{bytes_val} B"
    if bytes_val < 1024 * 1024:
        return f"{bytes_val / 1024:.1f} KB"
    return f"{bytes_val / (1024 * 1024):.1f} MB"


async def generate_brief(
    db: Session,
    client_id: UUID,
    user_id: str,
) -> dict:
    """
    Generate a meeting prep brief for a client.

    Returns::

        {
            "content": str,           # markdown brief
            "document_count": int,
            "action_item_count": int,
            "metadata": dict,
        }
    """
    start_time = time.time()

    # Fetch client with type
    client = (
        db.query(Client)
        .options(joinedload(Client.client_type))
        .filter(Client.id == client_id)
        .first()
    )
    if client is None:
        raise ValueError(f"Client {client_id} not found")

    # Fetch documents (most recent first)
    documents = (
        db.query(Document)
        .filter(Document.client_id == client_id)
        .order_by(Document.upload_date.desc())
        .all()
    )

    # Fetch pending action items
    action_items = (
        db.query(ActionItem)
        .filter(
            ActionItem.client_id == client_id,
            ActionItem.status == "pending",
        )
        .order_by(ActionItem.due_date.asc().nullslast(), ActionItem.created_at.desc())
        .all()
    )

    # Build prompt
    client_info = _build_client_info(client)
    documents_summary = _build_documents_summary(documents)
    action_items_summary = _build_action_items_summary(action_items)

    user_prompt = BRIEF_USER_PROMPT.format(
        client_info=client_info,
        doc_count=len(documents),
        documents_summary=documents_summary,
        action_count=len(action_items),
        action_items_summary=action_items_summary,
    )

    # Call GPT-4o
    openai_client = _openai()
    response = await openai_client.chat.completions.create(
        model=BRIEF_MODEL,
        messages=[
            {"role": "system", "content": BRIEF_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,
        max_tokens=2_000,
    )

    content = response.choices[0].message.content or "Brief generation failed."

    elapsed = round(time.time() - start_time, 2)
    usage = response.usage

    metadata = {
        "model": BRIEF_MODEL,
        "generation_time_seconds": elapsed,
        "prompt_tokens": usage.prompt_tokens if usage else 0,
        "completion_tokens": usage.completion_tokens if usage else 0,
        "total_tokens": usage.total_tokens if usage else 0,
    }

    # Log token usage for cost tracking
    try:
        from app.services.token_tracking_service import log_token_usage
        log_token_usage(
            db,
            user_id=user_id,
            client_id=client_id,
            query_type="brief",
            model=BRIEF_MODEL,
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            endpoint="brief",
        )
    except Exception:
        logger.error("Failed to log brief token usage", exc_info=True)

    logger.info(
        "Brief generated for client %s: %d docs, %d actions, %.1fs",
        client_id, len(documents), len(action_items), elapsed,
    )

    return {
        "content": content,
        "document_count": len(documents),
        "action_item_count": len(action_items),
        "metadata": metadata,
    }

"""
AI-powered strategy suggestion service.

Analyzes a client's uploaded documents to:
1. Suggest profile flag updates based on detected document subtypes (rule-based).
2. Suggest strategy statuses using GPT-4o analysis of document excerpts.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import HTTPException, status
from openai import AsyncOpenAI
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.client import Client
from app.models.client_strategy_status import ClientStrategyStatus
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.tax_strategy import TaxStrategy
from app.services.strategy_service import (
    PROFILE_FLAG_COLUMNS,
    VALID_STATUSES,
    _client_flags,
    _get_client_or_404,
    _strategy_applicable,
)

logger = logging.getLogger(__name__)

CHAT_MODEL = "gpt-4o"
MAX_DOCUMENTS = 10
MAX_CHARS_PER_DOC = 1500


# ---------------------------------------------------------------------------
# OpenAI client
# ---------------------------------------------------------------------------


def _openai() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=get_settings().openai_api_key)


# ---------------------------------------------------------------------------
# Rule-based flag suggestions
# ---------------------------------------------------------------------------

# Map of (substring in document_subtype) → suggested flag
_SUBTYPE_FLAG_RULES: list[tuple[list[str], str]] = [
    (["Schedule C", "1120-S", "1120", "1065"], "has_business_entity"),
    (["Schedule E"], "has_real_estate"),
    (["1041"], "has_estate_planning"),
]


def _suggest_flags_from_documents(
    db: Session, client_id: UUID, current_flags: dict[str, bool]
) -> list[dict]:
    """
    Rule-based: scan document subtypes and suggest flag changes.
    Only suggests flags that are currently False.
    """
    docs = (
        db.query(Document.document_subtype)
        .filter(
            Document.client_id == client_id,
            Document.is_superseded == False,  # noqa: E712
            Document.document_subtype.isnot(None),
        )
        .all()
    )

    subtypes = [d.document_subtype for d in docs if d.document_subtype]

    suggestions: list[dict] = []
    seen_flags: set[str] = set()

    for subtype in subtypes:
        upper = subtype.upper()

        # Standard subtype → flag rules
        for keywords, flag in _SUBTYPE_FLAG_RULES:
            if flag not in seen_flags and not current_flags.get(flag, False):
                if any(kw.upper() in upper for kw in keywords):
                    suggestions.append({
                        "flag": flag,
                        "suggested_value": True,
                        "reason": f"{subtype} detected in uploaded documents",
                    })
                    seen_flags.add(flag)

        # Medical professional: 1065 with medical/dental keywords
        if (
            "is_medical_professional" not in seen_flags
            and not current_flags.get("is_medical_professional", False)
            and "1065" in upper
        ):
            medical_keywords = ["medical", "dental", "physician", "doctor", "clinic", "healthcare"]
            if any(mk in upper for mk in medical_keywords):
                suggestions.append({
                    "flag": "is_medical_professional",
                    "suggested_value": True,
                    "reason": f"Medical/dental partnership return ({subtype}) detected",
                })
                seen_flags.add("is_medical_professional")

    return suggestions


# ---------------------------------------------------------------------------
# Document excerpt gathering
# ---------------------------------------------------------------------------


def _gather_document_excerpts(db: Session, client_id: UUID) -> tuple[list[dict], int]:
    """
    Gather the first MAX_CHARS_PER_DOC characters of text from each of the
    client's most recent non-superseded documents (up to MAX_DOCUMENTS).

    Returns (excerpts, doc_count) where each excerpt is:
        {"filename": str, "subtype": str|None, "text": str}
    """
    docs = (
        db.query(Document)
        .filter(
            Document.client_id == client_id,
            Document.is_superseded == False,  # noqa: E712
            Document.processed == True,  # noqa: E712
        )
        .order_by(Document.upload_date.desc())
        .limit(MAX_DOCUMENTS)
        .all()
    )

    excerpts: list[dict] = []
    for doc in docs:
        chunks = (
            db.query(DocumentChunk.chunk_text)
            .filter(DocumentChunk.document_id == doc.id)
            .order_by(DocumentChunk.chunk_index)
            .all()
        )
        full_text = " ".join(c.chunk_text for c in chunks)
        if full_text.strip():
            excerpts.append({
                "filename": doc.filename,
                "subtype": doc.document_subtype,
                "text": full_text[:MAX_CHARS_PER_DOC],
            })

    return excerpts, len(docs)


# ---------------------------------------------------------------------------
# GPT-4o strategy analysis
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a tax strategy advisor AI for a CPA firm platform. You analyze client \
documents and suggest which tax strategies are applicable and what their status \
should be.

For each strategy listed, analyze the document excerpts and assign one of:
- "implemented" — evidence the strategy is already in use (e.g., SEP-IRA \
contribution visible, home office deduction claimed, Schedule C present)
- "recommended" — documents suggest the strategy would be beneficial but no \
evidence it's currently implemented
- "not_applicable" — documents clearly indicate the strategy doesn't apply
- "not_reviewed" — not enough information to determine

For each suggestion, include a brief 1-sentence reason explaining why.

Also suggest any profile flag changes based on what you see in the documents:
- has_business_entity: true if business income/entities detected
- has_real_estate: true if real estate holdings detected
- is_real_estate_professional: true if RE professional status evident
- has_high_income: true if income appears above $200k
- has_estate_planning: true if estate/trust documents detected
- is_medical_professional: true if medical practice detected
- has_retirement_plans: true if retirement accounts detected
- has_investments: true if investment income/portfolios detected
- has_employees: true if payroll/employee-related items detected

Respond with valid JSON only, no markdown fences:
{
  "flag_suggestions": [
    {"flag": "has_business_entity", "suggested_value": true, "reason": "..."}
  ],
  "strategy_suggestions": [
    {"strategy_name": "Strategy Name", "suggested_status": "recommended", "reason": "..."}
  ]
}
"""


async def _analyze_with_gpt(
    excerpts: list[dict],
    strategies: list[TaxStrategy],
    current_flags: dict[str, bool],
) -> dict:
    """Call GPT-4o to analyze document excerpts against strategy list."""

    strategy_list = "\n".join(
        f"- {s.name} (category: {s.category})"
        + (f": {s.description}" if s.description else "")
        for s in strategies
    )

    doc_context = "\n\n".join(
        f"--- {e['filename']}"
        + (f" [{e['subtype']}]" if e.get("subtype") else "")
        + f" ---\n{e['text']}"
        for e in excerpts
    )

    current_flags_str = ", ".join(
        f"{k}={v}" for k, v in current_flags.items() if v
    ) or "none set"

    user_prompt = f"""\
Current profile flags: {current_flags_str}

Applicable strategies to evaluate:
{strategy_list}

Document excerpts ({len(excerpts)} documents):
{doc_context}

Analyze these documents and suggest statuses for each strategy listed above. \
Also suggest any profile flag changes."""

    client = _openai()
    response = await client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
        max_tokens=4000,
    )

    content = response.choices[0].message.content or "{}"
    # Strip markdown fences if present
    content = content.strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[-1]
    if content.endswith("```"):
        content = content.rsplit("```", 1)[0]
    content = content.strip()

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        logger.warning("GPT-4o returned invalid JSON for strategy suggestions")
        return {"flag_suggestions": [], "strategy_suggestions": []}


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def generate_strategy_suggestions(
    db: Session, client_id: UUID, user_id: str
) -> dict:
    """
    Analyze client documents and generate AI-powered strategy suggestions.

    Returns:
        {
            "flag_suggestions": [...],
            "strategy_suggestions": [...],
            "documents_analyzed": int,
            "tax_year": int,
        }
    """
    client = _get_client_or_404(db, client_id)
    current_flags = _client_flags(client)
    tax_year = date.today().year

    # 1. Rule-based flag suggestions from document subtypes
    rule_flag_suggestions = _suggest_flags_from_documents(db, client_id, current_flags)

    # 2. Gather document excerpts for GPT analysis
    excerpts, doc_count = _gather_document_excerpts(db, client_id)

    if not excerpts:
        # No processed documents — return only rule-based flag suggestions
        return {
            "flag_suggestions": rule_flag_suggestions,
            "strategy_suggestions": [],
            "documents_analyzed": 0,
            "tax_year": tax_year,
        }

    # 3. Determine applicable strategies (using current flags + any newly suggested flags)
    merged_flags = {**current_flags}
    for fs in rule_flag_suggestions:
        merged_flags[fs["flag"]] = fs["suggested_value"]

    all_strategies = (
        db.query(TaxStrategy)
        .filter(TaxStrategy.is_active == True)  # noqa: E712
        .order_by(TaxStrategy.category, TaxStrategy.display_order)
        .all()
    )
    applicable = [
        s for s in all_strategies
        if _strategy_applicable(merged_flags, s.required_flags or [])
    ]

    if not applicable:
        return {
            "flag_suggestions": rule_flag_suggestions,
            "strategy_suggestions": [],
            "documents_analyzed": doc_count,
            "tax_year": tax_year,
        }

    # 4. GPT-4o analysis
    gpt_result = await _analyze_with_gpt(excerpts, applicable, current_flags)

    # Merge flag suggestions: rule-based first, then GPT (deduplicated)
    seen_flags = {fs["flag"] for fs in rule_flag_suggestions}
    all_flag_suggestions = list(rule_flag_suggestions)
    for gpt_flag in gpt_result.get("flag_suggestions", []):
        flag_name = gpt_flag.get("flag", "")
        if flag_name in PROFILE_FLAG_COLUMNS and flag_name not in seen_flags:
            # Only suggest if the flag would change
            if current_flags.get(flag_name) != gpt_flag.get("suggested_value"):
                all_flag_suggestions.append(gpt_flag)
                seen_flags.add(flag_name)

    # Enrich strategy suggestions with strategy_id
    strategy_name_map = {s.name.lower(): str(s.id) for s in applicable}
    strategy_suggestions = []
    for ss in gpt_result.get("strategy_suggestions", []):
        name = ss.get("strategy_name", "")
        suggested_status = ss.get("suggested_status", "not_reviewed")
        if suggested_status not in VALID_STATUSES:
            suggested_status = "not_reviewed"
        strategy_id = strategy_name_map.get(name.lower())
        strategy_suggestions.append({
            "strategy_name": name,
            "strategy_id": strategy_id,
            "suggested_status": suggested_status,
            "reason": ss.get("reason", ""),
        })

    return {
        "flag_suggestions": all_flag_suggestions,
        "strategy_suggestions": strategy_suggestions,
        "documents_analyzed": doc_count,
        "tax_year": tax_year,
    }


# ---------------------------------------------------------------------------
# Apply accepted suggestions
# ---------------------------------------------------------------------------


async def apply_suggestions(
    db: Session,
    client_id: UUID,
    user_id: str,
    accepted_flags: list[dict],
    accepted_strategies: list[dict],
    tax_year: int,
) -> dict:
    """
    Apply user-accepted AI suggestions in a single transaction.

    accepted_flags: [{"flag": "has_business_entity", "value": true}, ...]
    accepted_strategies: [{"strategy_id": UUID, "status": "implemented", "notes": "AI suggested: ..."}, ...]

    Returns: {"flags_updated": N, "strategies_updated": N}
    """
    from datetime import datetime, timezone

    client = _get_client_or_404(db, client_id)
    now = datetime.now(timezone.utc)

    # Apply flag updates
    flags_updated = 0
    for af in accepted_flags:
        flag_name = af.get("flag", "")
        value = af.get("value")
        if flag_name in PROFILE_FLAG_COLUMNS and value is not None:
            setattr(client, flag_name, value)
            flags_updated += 1

    if flags_updated > 0:
        client.updated_at = now

    # Apply strategy status updates
    strategies_updated = 0
    for ast in accepted_strategies:
        sid_raw = ast.get("strategy_id")
        if not sid_raw:
            continue

        strategy_id = UUID(str(sid_raw)) if not isinstance(sid_raw, UUID) else sid_raw
        new_status = ast.get("status", "not_reviewed")
        if new_status not in VALID_STATUSES:
            continue

        notes = ast.get("notes")

        row = (
            db.query(ClientStrategyStatus)
            .filter(
                ClientStrategyStatus.client_id == client_id,
                ClientStrategyStatus.strategy_id == strategy_id,
                ClientStrategyStatus.tax_year == tax_year,
            )
            .first()
        )

        if row:
            row.status = new_status
            row.notes = notes
            row.updated_by = user_id
            row.updated_at = now
        else:
            row = ClientStrategyStatus(
                client_id=client_id,
                strategy_id=strategy_id,
                tax_year=tax_year,
                status=new_status,
                notes=notes,
                updated_by=user_id,
                updated_at=now,
            )
            db.add(row)

        strategies_updated += 1

    db.commit()
    return {"flags_updated": flags_updated, "strategies_updated": strategies_updated}

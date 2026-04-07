"""
Unified AI Context Assembler.

Centralised service that every AI feature calls to build client context.
Replaces ad-hoc context gathering scattered across brief_generator,
rag_service answer composition, email drafting, and strategy suggestions.

Usage::

    ctx = await assemble_context(db, client_id, user_id, ContextPurpose.CHAT,
                                 options={"query": "What was the Q3 revenue?"})
    prompt_text = format_context_for_prompt(ctx, ContextPurpose.CHAT)
"""

from __future__ import annotations

import enum
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.models.action_item import ActionItem
from app.models.client import Client
from app.models.client_communication import ClientCommunication
from app.models.client_strategy_status import ClientStrategyStatus
from app.models.document import Document
from app.models.tax_strategy import TaxStrategy

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Purpose enum
# ---------------------------------------------------------------------------


class ContextPurpose(str, enum.Enum):
    CHAT = "chat"
    EMAIL_DRAFT = "email_draft"
    QUARTERLY_ESTIMATE = "quarterly_estimate"
    BRIEF = "brief"
    STRATEGY_SUGGEST = "strategy_suggest"
    GENERAL = "general"


# ---------------------------------------------------------------------------
# Token budgets (approximate, used for trimming)
# ---------------------------------------------------------------------------

TOKEN_BUDGETS: dict[ContextPurpose, int] = {
    ContextPurpose.CHAT: 8000,
    ContextPurpose.EMAIL_DRAFT: 4000,
    ContextPurpose.QUARTERLY_ESTIMATE: 6000,
    ContextPurpose.BRIEF: 12000,
    ContextPurpose.STRATEGY_SUGGEST: 6000,
    ContextPurpose.GENERAL: 6000,
}

# ---------------------------------------------------------------------------
# Client profile flag columns
# ---------------------------------------------------------------------------

PROFILE_FLAG_COLUMNS = [
    "has_business_entity",
    "has_real_estate",
    "is_real_estate_professional",
    "has_high_income",
    "has_estate_planning",
    "is_medical_professional",
    "has_retirement_plans",
    "has_investments",
    "has_employees",
]

# ---------------------------------------------------------------------------
# ClientContext dataclass
# ---------------------------------------------------------------------------


@dataclass
class ClientContext:
    """Assembled context for a single client, ready for AI consumption."""

    client_profile: dict[str, Any]
    documents_summary: list[dict[str, Any]] = field(default_factory=list)
    financial_metrics: dict[str, Any] | None = None  # TODO: Feature 2
    action_items: list[dict[str, Any]] = field(default_factory=list)
    communication_history: list[dict[str, Any]] = field(default_factory=list)
    journal_entries: list[dict[str, Any]] | None = None  # TODO: Feature 3
    strategy_status: dict[str, Any] | None = None
    engagement_calendar: list[dict[str, Any]] | None = None  # TODO: Feature 4
    rag_chunks: list[dict[str, Any]] | None = None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def assemble_context(
    db: Session,
    client_id: UUID,
    user_id: str,
    purpose: ContextPurpose = ContextPurpose.GENERAL,
    options: dict[str, Any] | None = None,
) -> ClientContext:
    """
    Build a :class:`ClientContext` for the given client and purpose.

    *options* is a purpose-specific dict.  For ``CHAT`` it may contain:

    - ``{"query": "..."}`` — the assembler will run vector search internally.
    - ``{"rag_chunks": [...]}`` — pre-fetched RAG chunks (list of dicts with
      ``chunk_text``, ``document_filename``, etc.).  When provided the
      assembler skips its own vector search.
    """
    options = options or {}
    current_year = datetime.now().year

    # 1. Always fetch client profile -----------------------------------------
    client_profile = _fetch_client_profile(db, client_id)

    ctx = ClientContext(client_profile=client_profile)

    # 2. Fetch data sources based on purpose ----------------------------------
    if purpose == ContextPurpose.CHAT:
        # Prefer pre-fetched RAG chunks from the caller (rag_service)
        if "rag_chunks" in options:
            ctx.rag_chunks = options["rag_chunks"]
        else:
            query = options.get("query", "")
            if query:
                ctx.rag_chunks = await _fetch_rag_chunks(db, client_id, query)
        ctx.action_items = _fetch_action_items(db, client_id, limit=10)
        ctx.communication_history = _fetch_communications(db, client_id, limit=5)
        ctx.strategy_status = _fetch_strategy_status(db, client_id, [current_year])

    elif purpose == ContextPurpose.EMAIL_DRAFT:
        ctx.communication_history = _fetch_communications(db, client_id, limit=10)
        ctx.action_items = _fetch_action_items(db, client_id, limit=10)
        ctx.strategy_status = _fetch_strategy_status(db, client_id, [current_year])

    elif purpose == ContextPurpose.QUARTERLY_ESTIMATE:
        ctx.communication_history = _fetch_communications(
            db, client_id, limit=None, year=current_year,
        )
        ctx.action_items = _fetch_action_items(db, client_id, limit=None)
        ctx.strategy_status = _fetch_strategy_status(db, client_id, [current_year])

    elif purpose == ContextPurpose.BRIEF:
        ctx.documents_summary = _fetch_documents_summary(db, client_id)
        ctx.action_items = _fetch_action_items(db, client_id, limit=None)
        ctx.communication_history = _fetch_communications(db, client_id, limit=20)
        ctx.strategy_status = _fetch_strategy_status(
            db, client_id, [current_year, current_year - 1],
        )

    elif purpose == ContextPurpose.STRATEGY_SUGGEST:
        ctx.documents_summary = _fetch_documents_summary(db, client_id)
        ctx.strategy_status = _fetch_strategy_status(
            db, client_id, [current_year, current_year - 1],
        )

    else:  # GENERAL
        ctx.action_items = _fetch_action_items(db, client_id, limit=10)
        ctx.communication_history = _fetch_communications(db, client_id, limit=5)

    # TODO: Feature 2 — populate ctx.financial_metrics
    # TODO: Feature 3 — populate ctx.journal_entries
    # TODO: Feature 4 — populate ctx.engagement_calendar

    # 3. Trim to budget -------------------------------------------------------
    budget = TOKEN_BUDGETS.get(purpose, TOKEN_BUDGETS[ContextPurpose.GENERAL])
    _trim_to_budget(ctx, budget)

    return ctx


# ---------------------------------------------------------------------------
# Data fetchers
# ---------------------------------------------------------------------------


def _fetch_client_profile(db: Session, client_id: UUID) -> dict[str, Any]:
    client = (
        db.query(Client)
        .options(joinedload(Client.client_type))
        .filter(Client.id == client_id)
        .first()
    )
    if not client:
        return {"id": str(client_id), "name": "Unknown client"}

    profile: dict[str, Any] = {
        "id": str(client.id),
        "name": client.name,
        "email": client.email,
        "business_name": client.business_name,
        "entity_type": client.entity_type,
        "industry": client.industry,
        "notes": client.notes,
        "custom_instructions": client.custom_instructions,
        "client_type": client.client_type.name if client.client_type else None,
        "consent_status": client.consent_status,
        "is_tax_preparer": client.is_tax_preparer,
    }

    # Profile flags
    profile["profile_flags"] = {
        col: getattr(client, col, False) for col in PROFILE_FLAG_COLUMNS
    }

    return profile


def _fetch_documents_summary(
    db: Session,
    client_id: UUID,
) -> list[dict[str, Any]]:
    docs = (
        db.query(Document)
        .filter(
            Document.client_id == client_id,
            Document.is_superseded == False,  # noqa: E712
        )
        .order_by(Document.upload_date.desc())
        .all()
    )
    results: list[dict[str, Any]] = []
    for doc in docs:
        entry: dict[str, Any] = {
            "id": str(doc.id),
            "filename": doc.filename,
            "file_type": doc.file_type,
            "document_type": doc.document_type,
            "document_subtype": doc.document_subtype,
            "document_period": doc.document_period,
            "upload_date": doc.upload_date.isoformat() if doc.upload_date else None,
            "processed": doc.processed,
        }
        if doc.amends_subtype:
            entry["amendment_note"] = (
                f"Amendment #{doc.amendment_number or 1} of {doc.amends_subtype}"
            )
        results.append(entry)
    return results


def _fetch_action_items(
    db: Session,
    client_id: UUID,
    *,
    limit: int | None = 10,
) -> list[dict[str, Any]]:
    q = (
        db.query(ActionItem)
        .filter(
            ActionItem.client_id == client_id,
            ActionItem.status == "pending",
        )
        .order_by(
            ActionItem.due_date.asc().nullslast(),
            ActionItem.created_at.desc(),
        )
    )
    if limit is not None:
        q = q.limit(limit)

    items = q.all()
    return [
        {
            "id": str(item.id),
            "text": item.text,
            "priority": item.priority,
            "due_date": item.due_date.isoformat() if item.due_date else None,
            "assigned_to_name": item.assigned_to_name,
            "source": item.source,
            "notes": item.notes,
        }
        for item in items
    ]


def _fetch_communications(
    db: Session,
    client_id: UUID,
    *,
    limit: int | None = 10,
    year: int | None = None,
) -> list[dict[str, Any]]:
    q = (
        db.query(ClientCommunication)
        .filter(ClientCommunication.client_id == client_id)
    )
    if year is not None:
        q = q.filter(
            func.extract("year", ClientCommunication.sent_at) == year,
        )
    q = q.order_by(ClientCommunication.sent_at.desc())
    if limit is not None:
        q = q.limit(limit)

    comms = q.all()
    return [
        {
            "subject": c.subject,
            "recipient_name": c.recipient_name,
            "recipient_email": c.recipient_email,
            "communication_type": c.communication_type,
            "body_text": (c.body_text or "")[:500],  # truncate for context
            "sent_at": c.sent_at.isoformat() if c.sent_at else None,
            "status": c.status,
        }
        for c in comms
    ]


def _fetch_strategy_status(
    db: Session,
    client_id: UUID,
    years: list[int],
) -> dict[str, Any]:
    rows = (
        db.query(ClientStrategyStatus)
        .options(joinedload(ClientStrategyStatus.strategy))
        .filter(
            ClientStrategyStatus.client_id == client_id,
            ClientStrategyStatus.tax_year.in_(years),
        )
        .all()
    )

    by_year: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        strategy_name = row.strategy.name if row.strategy else "Unknown"
        category = row.strategy.category if row.strategy else "unknown"
        entry = {
            "strategy": strategy_name,
            "category": category,
            "status": row.status,
            "notes": row.notes,
            "estimated_impact": float(row.estimated_impact) if row.estimated_impact else None,
        }
        by_year.setdefault(row.tax_year, []).append(entry)

    return {"years": {str(y): by_year.get(y, []) for y in years}}


async def _fetch_rag_chunks(
    db: Session,
    client_id: UUID,
    query: str,
) -> list[dict[str, Any]]:
    from app.services.rag_service import search_chunks

    results = await search_chunks(db, client_id, query)
    return [
        {
            "chunk_text": chunk.chunk_text,
            "document_filename": chunk.document.filename if chunk.document else None,
            "document_type": chunk.document.document_type if chunk.document else None,
            "document_period": chunk.document.document_period if chunk.document else None,
            "confidence": round(score, 1),
        }
        for chunk, score in results
    ]


# ---------------------------------------------------------------------------
# Token estimation & budget trimming
# ---------------------------------------------------------------------------


def _estimate_tokens(text: str) -> int:
    """Approximate token count: ~4 characters per token."""
    return len(text) // 4


def _trim_to_budget(ctx: ClientContext, budget: int) -> None:
    """
    Remove items from the lowest-priority sections until the total
    estimated token count fits within *budget*.

    Priority order (highest to lowest):
    1. client_profile — never trimmed
    2. rag_chunks — only present for CHAT, high value
    3. action_items
    4. strategy_status
    5. communication_history
    6. documents_summary
    """
    import json

    def _ctx_tokens() -> int:
        parts = [
            json.dumps(ctx.client_profile, default=str),
        ]
        if ctx.rag_chunks:
            parts.append(json.dumps(ctx.rag_chunks, default=str))
        if ctx.action_items:
            parts.append(json.dumps(ctx.action_items, default=str))
        if ctx.strategy_status:
            parts.append(json.dumps(ctx.strategy_status, default=str))
        if ctx.communication_history:
            parts.append(json.dumps(ctx.communication_history, default=str))
        if ctx.documents_summary:
            parts.append(json.dumps(ctx.documents_summary, default=str))
        return _estimate_tokens("".join(parts))

    # Trim in reverse priority order
    trimmable = [
        "documents_summary",
        "communication_history",
        "strategy_status",
        "action_items",
        "rag_chunks",
    ]

    for attr in trimmable:
        if _ctx_tokens() <= budget:
            return

        value = getattr(ctx, attr)
        if value is None:
            continue

        if isinstance(value, list) and len(value) > 0:
            # Remove items from the end (least relevant) until under budget
            while value and _ctx_tokens() > budget:
                value.pop()
            if not value:
                setattr(ctx, attr, [] if isinstance(getattr(ctx, attr), list) else None)
        elif isinstance(value, dict):
            # Clear the whole section
            setattr(ctx, attr, None)


# ---------------------------------------------------------------------------
# Prompt formatter
# ---------------------------------------------------------------------------


def format_context_for_prompt(
    ctx: ClientContext,
    purpose: ContextPurpose = ContextPurpose.GENERAL,
) -> str:
    """
    Convert a :class:`ClientContext` into a formatted string for inclusion
    in an AI prompt.
    """
    sections: list[str] = []

    # --- Client profile (always present) ------------------------------------
    p = ctx.client_profile
    profile_lines = [
        f"=== CLIENT PROFILE ===",
        f"Name: {p.get('name', 'Unknown')}",
    ]
    if p.get("business_name"):
        profile_lines.append(f"Business: {p['business_name']}")
    if p.get("entity_type"):
        profile_lines.append(f"Entity type: {p['entity_type']}")
    if p.get("industry"):
        profile_lines.append(f"Industry: {p['industry']}")
    if p.get("client_type"):
        profile_lines.append(f"Client type: {p['client_type']}")
    if p.get("notes"):
        profile_lines.append(f"Notes: {p['notes']}")

    flags = p.get("profile_flags", {})
    active_flags = [k for k, v in flags.items() if v]
    if active_flags:
        profile_lines.append(f"Profile flags: {', '.join(active_flags)}")

    if p.get("custom_instructions"):
        profile_lines.append(f"\nCustom AI instructions: {p['custom_instructions']}")

    sections.append("\n".join(profile_lines))

    # --- RAG chunks (CHAT only) ---------------------------------------------
    if ctx.rag_chunks:
        chunk_lines = ["=== RELEVANT DOCUMENT EXCERPTS ==="]
        for i, chunk in enumerate(ctx.rag_chunks, 1):
            source = chunk.get("document_filename", "Unknown")
            period = chunk.get("document_period", "")
            confidence = chunk.get("confidence", 0)
            header = f"[{i}] {source}"
            if period:
                header += f" ({period})"
            header += f" — {confidence}% match"
            chunk_lines.append(header)
            chunk_lines.append(chunk.get("chunk_text", ""))
            chunk_lines.append("")
        sections.append("\n".join(chunk_lines))

    # --- Action items -------------------------------------------------------
    if ctx.action_items:
        item_lines = ["=== OPEN ACTION ITEMS ==="]
        for item in ctx.action_items:
            parts = [f"• {item['text']}"]
            if item.get("priority"):
                parts.append(f"[{item['priority'].upper()}]")
            if item.get("due_date"):
                parts.append(f"due {item['due_date']}")
            if item.get("assigned_to_name"):
                parts.append(f"→ {item['assigned_to_name']}")
            item_lines.append(" ".join(parts))
        sections.append("\n".join(item_lines))

    # --- Communications -----------------------------------------------------
    if ctx.communication_history:
        if purpose == ContextPurpose.QUARTERLY_ESTIMATE:
            comm_header = "=== TAX YEAR COMMUNICATIONS ==="
        else:
            comm_header = "=== RECENT COMMUNICATIONS ==="

        comm_lines = [comm_header]
        for comm in ctx.communication_history:
            date = comm.get("sent_at", "")[:10] if comm.get("sent_at") else "Unknown"
            subject = comm.get("subject", "(no subject)")
            recipient = comm.get("recipient_name") or comm.get("recipient_email", "")
            comm_lines.append(f"[{date}] To: {recipient} — {subject}")
            body = comm.get("body_text", "")
            if body:
                comm_lines.append(f"  {body[:200]}...")
            comm_lines.append("")
        sections.append("\n".join(comm_lines))

    # --- Strategy status ----------------------------------------------------
    if ctx.strategy_status and ctx.strategy_status.get("years"):
        strat_lines = ["=== STRATEGY STATUS ==="]
        for year, strategies in ctx.strategy_status["years"].items():
            if not strategies:
                continue
            strat_lines.append(f"\nTax Year {year}:")
            for s in strategies:
                line = f"  • {s['strategy']} ({s['category']}): {s['status']}"
                if s.get("estimated_impact"):
                    line += f" — est. ${s['estimated_impact']:,.0f}"
                if s.get("notes"):
                    line += f" | {s['notes']}"
                strat_lines.append(line)
        sections.append("\n".join(strat_lines))

    # --- Documents summary --------------------------------------------------
    if ctx.documents_summary:
        doc_lines = ["=== DOCUMENTS ON FILE ==="]
        for doc in ctx.documents_summary:
            parts = [doc.get("filename", "unknown")]
            if doc.get("document_subtype"):
                parts.append(f"({doc['document_subtype']})")
            elif doc.get("document_type"):
                parts.append(f"({doc['document_type']})")
            if doc.get("document_period"):
                parts.append(f"[{doc['document_period']}]")
            if doc.get("amendment_note"):
                parts.append(f"⚠ {doc['amendment_note']}")
            doc_lines.append(f"• {' '.join(parts)}")
        sections.append("\n".join(doc_lines))

    return "\n\n".join(sections)

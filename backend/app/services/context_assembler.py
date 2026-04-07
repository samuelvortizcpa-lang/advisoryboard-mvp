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

from sqlalchemy import case, func
from sqlalchemy.orm import Session, joinedload

from app.models.action_item import ActionItem
from app.models.client import Client
from app.models.client_communication import ClientCommunication
from app.models.client_financial_metric import ClientFinancialMetric
from app.models.client_strategy_status import ClientStrategyStatus
from app.models.document import Document
from app.models.client_engagement import ClientEngagement
from app.models.engagement_template import EngagementTemplate
from app.models.journal_entry import JournalEntry
from app.models.profile_flag_history import ProfileFlagHistory
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
    financial_metrics: dict[str, Any] | None = None
    action_items: list[dict[str, Any]] = field(default_factory=list)
    communication_history: list[dict[str, Any]] = field(default_factory=list)
    journal_entries: list[dict[str, Any]] | None = None  # TODO: Feature 3
    strategy_status: dict[str, Any] | None = None
    engagement_calendar: list[dict[str, Any]] | None = None  # TODO: Feature 4
    session_history: list[dict[str, Any]] = field(default_factory=list)
    contradictions: list[dict[str, Any]] = field(default_factory=list)
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
    *,
    current_query: str | None = None,
) -> ClientContext:
    """
    Build a :class:`ClientContext` for the given client and purpose.

    *options* is a purpose-specific dict.  For ``CHAT`` it may contain:

    - ``{"query": "..."}`` — the assembler will run vector search internally.
    - ``{"rag_chunks": [...]}`` — pre-fetched RAG chunks (list of dicts with
      ``chunk_text``, ``document_filename``, etc.).  When provided the
      assembler skips its own vector search.

    *current_query* — when provided (typically for CHAT), enables semantic
    search over prior session summaries to surface relevant past conversations.
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
        # Include profile flag history for strategy context
        flag_history = _fetch_profile_flag_history(db, client_id)
        if flag_history:
            profile = ctx.client_profile
            profile["profile_flag_history"] = flag_history

    else:  # GENERAL
        ctx.action_items = _fetch_action_items(db, client_id, limit=10)
        ctx.communication_history = _fetch_communications(db, client_id, limit=5)

    # Populate financial metrics for most purposes
    if purpose in (
        ContextPurpose.CHAT,
        ContextPurpose.EMAIL_DRAFT,
        ContextPurpose.QUARTERLY_ESTIMATE,
        ContextPurpose.BRIEF,
        ContextPurpose.STRATEGY_SUGGEST,
    ):
        ctx.financial_metrics = _fetch_financial_metrics(
            db, client_id, current_year,
        )

    # Populate journal entries based on purpose
    if purpose == ContextPurpose.CHAT:
        ctx.journal_entries = _fetch_journal_entries(
            db, client_id, limit=10, include_pinned=True,
        )
    elif purpose == ContextPurpose.EMAIL_DRAFT:
        ctx.journal_entries = _fetch_journal_entries(
            db, client_id, limit=5, include_pinned=True,
        )
    elif purpose == ContextPurpose.QUARTERLY_ESTIMATE:
        # Entries since last quarterly estimate email
        last_estimate_date = _find_last_quarterly_estimate_date(
            ctx.communication_history,
        )
        ctx.journal_entries = _fetch_journal_entries(
            db, client_id, since=last_estimate_date, include_pinned=True,
        )
    elif purpose == ContextPurpose.BRIEF:
        ctx.journal_entries = _fetch_journal_entries(
            db, client_id, limit=20, include_pinned=True,
        )
    elif purpose == ContextPurpose.STRATEGY_SUGGEST:
        ctx.journal_entries = _fetch_journal_entries(
            db, client_id, months=12,
            categories=["income", "deductions", "business", "investment", "property"],
            include_pinned=False,
        )

    # Populate engagement calendar for purposes that benefit from deadline awareness
    if purpose in (
        ContextPurpose.CHAT,
        ContextPurpose.EMAIL_DRAFT,
        ContextPurpose.QUARTERLY_ESTIMATE,
        ContextPurpose.BRIEF,
    ):
        ctx.engagement_calendar = _fetch_engagement_calendar(db, client_id)

    # Populate session history (prior advisory conversations)
    try:
        ctx.session_history = await _gather_session_history(
            client_id, user_id, purpose, current_query, db,
        )
    except Exception:
        logger.warning("Session history gathering failed; continuing without it", exc_info=True)

    # Populate open contradictions for ALL purposes
    try:
        ctx.contradictions = _gather_contradictions(db, client_id)
    except Exception:
        logger.warning("Contradiction gathering failed; continuing without it", exc_info=True)

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


def _fetch_financial_metrics(
    db: Session,
    client_id: UUID,
    current_year: int,
) -> dict[str, Any] | None:
    """Fetch financial metrics for the current year and 2 prior years."""
    years = [current_year, current_year - 1, current_year - 2]
    rows = (
        db.query(ClientFinancialMetric)
        .filter(
            ClientFinancialMetric.client_id == client_id,
            ClientFinancialMetric.tax_year.in_(years),
        )
        .order_by(
            ClientFinancialMetric.tax_year.desc(),
            ClientFinancialMetric.metric_name,
        )
        .all()
    )
    if not rows:
        return None

    by_year: dict[int, dict[str, Any]] = {}
    for row in rows:
        yr_data = by_year.setdefault(row.tax_year, {})
        entry: dict[str, Any] = {
            "value": float(row.metric_value) if row.metric_value is not None else None,
            "category": row.metric_category,
            "form_source": row.form_source,
        }
        if row.line_reference:
            entry["line_reference"] = row.line_reference
        if row.is_amended:
            entry["amended"] = True
        yr_data[row.metric_name] = entry

    return {str(y): by_year.get(y, {}) for y in years if by_year.get(y)}


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


def _fetch_journal_entries(
    db: Session,
    client_id: UUID,
    *,
    limit: int | None = None,
    include_pinned: bool = True,
    since: datetime | None = None,
    months: int | None = None,
    categories: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Fetch journal entries with flexible filtering."""
    from dateutil.relativedelta import relativedelta

    results: list[dict[str, Any]] = []
    seen_ids: set[UUID] = set()

    # Always fetch pinned entries first (if requested)
    if include_pinned:
        pinned = (
            db.query(JournalEntry)
            .filter(
                JournalEntry.client_id == client_id,
                JournalEntry.is_pinned == True,  # noqa: E712
            )
            .order_by(JournalEntry.created_at.desc())
            .all()
        )
        for e in pinned:
            results.append(_journal_to_dict(e, pinned=True))
            seen_ids.add(e.id)

    # Build main query
    q = (
        db.query(JournalEntry)
        .filter(
            JournalEntry.client_id == client_id,
        )
        .order_by(JournalEntry.created_at.desc())
    )

    if since is not None:
        q = q.filter(JournalEntry.created_at >= since)
    elif months is not None:
        cutoff = datetime.now() - relativedelta(months=months)
        q = q.filter(JournalEntry.created_at >= cutoff)

    if categories:
        q = q.filter(JournalEntry.category.in_(categories))

    if limit is not None:
        # Fetch extra to account for pinned entries we already have
        q = q.limit(limit + len(seen_ids))

    rows = q.all()
    for e in rows:
        if e.id not in seen_ids:
            results.append(_journal_to_dict(e, pinned=False))
            seen_ids.add(e.id)
        if limit is not None and len(results) >= limit + (len(seen_ids) - len(results)):
            break

    return results if results else None  # type: ignore[return-value]


def _journal_to_dict(entry: JournalEntry, *, pinned: bool) -> dict[str, Any]:
    """Convert a journal entry to a context dict."""
    d: dict[str, Any] = {
        "date": entry.created_at.strftime("%Y-%m-%d") if entry.created_at else "",
        "type": entry.entry_type,
        "title": entry.title,
        "content": (entry.content or "")[:200] if entry.content else None,
        "category": entry.category,
        "pinned": pinned or entry.is_pinned,
    }
    if entry.effective_date:
        d["effective_date"] = entry.effective_date.isoformat()
    return d


def _find_last_quarterly_estimate_date(
    communication_history: list[dict[str, Any]],
) -> datetime | None:
    """Find the date of the last quarterly estimate email from communication history."""
    for comm in communication_history:
        subject = (comm.get("subject") or "").lower()
        if any(kw in subject for kw in ("quarterly estimate", "estimated tax", "q1 ", "q2 ", "q3 ", "q4 ")):
            sent = comm.get("sent_at")
            if sent:
                try:
                    return datetime.fromisoformat(sent)
                except (ValueError, TypeError):
                    pass
    return None


def _fetch_profile_flag_history(
    db: Session,
    client_id: UUID,
) -> list[dict[str, Any]]:
    """Fetch profile flag change history for strategy context."""
    rows = (
        db.query(ProfileFlagHistory)
        .filter(ProfileFlagHistory.client_id == client_id)
        .order_by(ProfileFlagHistory.changed_at.desc())
        .limit(20)
        .all()
    )
    return [
        {
            "flag": r.flag_name,
            "old": r.old_value,
            "new": r.new_value,
            "date": r.changed_at.strftime("%Y-%m-%d") if r.changed_at else "",
            "source": r.source,
        }
        for r in rows
    ] if rows else []


def _fetch_engagement_calendar(
    db: Session,
    client_id: UUID,
    days_ahead: int = 90,
) -> list[dict[str, Any]] | None:
    """Calculate upcoming engagement deadlines for the next N days."""
    from datetime import date, timedelta
    import calendar as cal_mod

    today = date.today()
    window_end = today + timedelta(days=days_ahead)
    current_year = today.year

    engagements = (
        db.query(ClientEngagement)
        .options(
            joinedload(ClientEngagement.template).joinedload(EngagementTemplate.tasks),
        )
        .filter(
            ClientEngagement.client_id == client_id,
            ClientEngagement.is_active == True,  # noqa: E712
        )
        .all()
    )

    if not engagements:
        return None

    deadlines: list[dict[str, Any]] = []

    for eng in engagements:
        template = eng.template
        if not template or not template.is_active:
            continue

        overrides = eng.custom_overrides or {}

        for task in template.tasks:
            for year in [current_year, current_year + 1]:
                if year < eng.start_year:
                    continue

                # Calculate deadline(s) for this task in this year
                override_key = str(task.id)
                if override_key in overrides:
                    ov = overrides[override_key]
                    if isinstance(ov, dict) and "month" in ov and "day" in ov:
                        try:
                            task_deadlines = [date(year, ov["month"], ov["day"])]
                        except (ValueError, TypeError):
                            continue
                    else:
                        continue
                elif task.month is not None and task.day is not None:
                    try:
                        max_day = cal_mod.monthrange(year, task.month)[1]
                        actual_day = min(task.day, max_day)
                        task_deadlines = [date(year, task.month, actual_day)]
                    except (ValueError, TypeError):
                        continue
                else:
                    continue

                for deadline in task_deadlines:
                    if today <= deadline <= window_end:
                        deadlines.append({
                            "task": task.task_name,
                            "date": deadline.isoformat(),
                            "priority": task.priority,
                            "category": task.category,
                            "template": template.name,
                        })

    if not deadlines:
        return None

    # Sort by date
    deadlines.sort(key=lambda d: d["date"])
    return deadlines


# ---------------------------------------------------------------------------
# Contradictions
# ---------------------------------------------------------------------------


def _gather_contradictions(
    db: Session,
    client_id: UUID,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Fetch open data contradictions for inclusion in AI context."""
    from app.models.data_contradiction import DataContradiction

    rows = (
        db.query(DataContradiction)
        .filter(
            DataContradiction.client_id == client_id,
            DataContradiction.status == "open",
        )
        .order_by(
            # high first
            case(
                (DataContradiction.severity == "high", 0),
                (DataContradiction.severity == "medium", 1),
                else_=2,
            ),
            DataContradiction.created_at.desc(),
        )
        .limit(limit)
        .all()
    )

    return [
        {
            "title": r.title,
            "severity": r.severity,
            "type": r.contradiction_type,
            "field": r.field_name,
            "description": r.description,
            "tax_year": r.tax_year,
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Session history (prior advisory conversations)
# ---------------------------------------------------------------------------


# Token budgets per purpose for the session history section
_SESSION_TOKEN_BUDGETS: dict[ContextPurpose, int] = {
    ContextPurpose.CHAT: 1500,
    ContextPurpose.BRIEF: 2000,
    ContextPurpose.EMAIL_DRAFT: 500,
    ContextPurpose.STRATEGY_SUGGEST: 800,
    ContextPurpose.QUARTERLY_ESTIMATE: 800,
    ContextPurpose.GENERAL: 800,
}


def _format_session_entry(session: Any) -> str:
    """Format a single session dict into a context string."""
    # Handle both dict and ORM object
    if hasattr(session, "started_at"):
        date = session.started_at.strftime("%Y-%m-%d") if session.started_at else "Unknown"
        summary = session.summary or "(no summary)"
        topics = session.key_topics or []
        decisions = session.key_decisions or []
    else:
        date = session.get("started_at", "Unknown")
        if hasattr(date, "strftime"):
            date = date.strftime("%Y-%m-%d")
        summary = session.get("summary") or "(no summary)"
        topics = session.get("key_topics") or []
        decisions = session.get("key_decisions") or []

    parts = [f"Session ({date}): {summary}"]
    if topics:
        parts.append(f"  Topics: {', '.join(str(t) for t in topics)}")
    if decisions:
        parts.append(f"  Decisions: {'; '.join(str(d) for d in decisions)}")
    return "\n".join(parts)


async def _gather_session_history(
    client_id: UUID,
    user_id: str,
    purpose: ContextPurpose,
    current_query: str | None,
    db: Session,
) -> list[dict[str, Any]]:
    """Gather prior session context based on purpose and query.

    Combines recent sessions with semantically relevant ones (if a query
    is provided), deduplicates, and trims to the purpose-specific budget.
    """
    from app.services.session_memory_service import (
        get_recent_sessions,
        search_sessions,
    )

    budget = _SESSION_TOKEN_BUDGETS.get(purpose, 800)
    results: list[dict[str, Any]] = []
    seen_ids: set[UUID] = set()

    if purpose == ContextPurpose.CHAT:
        recent = get_recent_sessions(client_id, user_id, db, limit=2)
        for s in recent:
            seen_ids.add(s.id)
            results.append({
                "id": str(s.id),
                "started_at": s.started_at,
                "summary": s.summary,
                "key_topics": s.key_topics,
                "key_decisions": s.key_decisions,
                "formatted": _format_session_entry(s),
            })
        # Semantic search for relevant sessions
        if current_query:
            semantic = await search_sessions(
                client_id, user_id, current_query, db, limit=3,
            )
            for s in semantic:
                sid = UUID(str(s["id"])) if not isinstance(s["id"], UUID) else s["id"]
                if sid not in seen_ids:
                    seen_ids.add(sid)
                    results.append({
                        "id": str(sid),
                        "started_at": s["started_at"],
                        "summary": s["summary"],
                        "key_topics": s["key_topics"],
                        "key_decisions": s["key_decisions"],
                        "formatted": _format_session_entry(s),
                    })

    elif purpose == ContextPurpose.BRIEF:
        recent = get_recent_sessions(client_id, user_id, db, limit=5)
        for s in recent:
            results.append({
                "id": str(s.id),
                "started_at": s.started_at,
                "summary": s.summary,
                "key_topics": s.key_topics,
                "key_decisions": s.key_decisions,
                "formatted": _format_session_entry(s),
            })

    elif purpose == ContextPurpose.EMAIL_DRAFT:
        recent = get_recent_sessions(client_id, user_id, db, limit=1)
        for s in recent:
            seen_ids.add(s.id)
            results.append({
                "id": str(s.id),
                "started_at": s.started_at,
                "summary": s.summary,
                "key_topics": s.key_topics,
                "key_decisions": s.key_decisions,
                "formatted": _format_session_entry(s),
            })
        if current_query:
            semantic = await search_sessions(
                client_id, user_id, current_query, db, limit=2,
            )
            for s in semantic:
                sid = UUID(str(s["id"])) if not isinstance(s["id"], UUID) else s["id"]
                if sid not in seen_ids:
                    seen_ids.add(sid)
                    results.append({
                        "id": str(sid),
                        "started_at": s["started_at"],
                        "summary": s["summary"],
                        "key_topics": s["key_topics"],
                        "key_decisions": s["key_decisions"],
                        "formatted": _format_session_entry(s),
                    })

    elif purpose == ContextPurpose.STRATEGY_SUGGEST:
        # Prioritize sessions with decisions
        recent = get_recent_sessions(client_id, user_id, db, limit=5)
        # Sort: sessions with decisions first
        with_decisions = [s for s in recent if s.key_decisions]
        without_decisions = [s for s in recent if not s.key_decisions]
        for s in (with_decisions + without_decisions)[:3]:
            results.append({
                "id": str(s.id),
                "started_at": s.started_at,
                "summary": s.summary,
                "key_topics": s.key_topics,
                "key_decisions": s.key_decisions,
                "formatted": _format_session_entry(s),
            })

    else:
        # GENERAL / QUARTERLY_ESTIMATE
        recent = get_recent_sessions(client_id, user_id, db, limit=2)
        for s in recent:
            results.append({
                "id": str(s.id),
                "started_at": s.started_at,
                "summary": s.summary,
                "key_topics": s.key_topics,
                "key_decisions": s.key_decisions,
                "formatted": _format_session_entry(s),
            })

    # Trim to token budget
    trimmed: list[dict[str, Any]] = []
    total_tokens = 0
    for entry in results:
        entry_tokens = _estimate_tokens(entry["formatted"])
        if total_tokens + entry_tokens > budget:
            break
        trimmed.append(entry)
        total_tokens += entry_tokens

    return trimmed


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
    3. session_history — prior conversations
    4. financial_metrics
    5. action_items
    6. strategy_status
    7. communication_history
    8. documents_summary
    """
    import json

    def _ctx_tokens() -> int:
        parts = [
            json.dumps(ctx.client_profile, default=str),
        ]
        if ctx.rag_chunks:
            parts.append(json.dumps(ctx.rag_chunks, default=str))
        if ctx.session_history:
            parts.append(json.dumps(ctx.session_history, default=str))
        if ctx.financial_metrics:
            parts.append(json.dumps(ctx.financial_metrics, default=str))
        if ctx.action_items:
            parts.append(json.dumps(ctx.action_items, default=str))
        if ctx.strategy_status:
            parts.append(json.dumps(ctx.strategy_status, default=str))
        if ctx.journal_entries:
            parts.append(json.dumps(ctx.journal_entries, default=str))
        if ctx.communication_history:
            parts.append(json.dumps(ctx.communication_history, default=str))
        if ctx.engagement_calendar:
            parts.append(json.dumps(ctx.engagement_calendar, default=str))
        if ctx.documents_summary:
            parts.append(json.dumps(ctx.documents_summary, default=str))
        return _estimate_tokens("".join(parts))

    # Trim in reverse priority order
    trimmable = [
        "documents_summary",
        "engagement_calendar",
        "communication_history",
        "journal_entries",
        "strategy_status",
        "action_items",
        "financial_metrics",
        "session_history",
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

    # --- Data contradictions (FIRST — high priority) ------------------------
    if ctx.contradictions:
        contra_lines = ["=== DATA CONTRADICTIONS (REQUIRES ATTENTION) ==="]
        for c in ctx.contradictions:
            sev = c.get("severity", "").upper()
            title = c.get("title", "")
            contra_lines.append(f"⚠ [{sev}] {title}")
            if c.get("description"):
                contra_lines.append(f"  {c['description']}")
        sections.append("\n".join(contra_lines))

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

    if p.get("profile_flag_history"):
        profile_lines.append("\nProfile flag changes:")
        for fh in p["profile_flag_history"]:
            old = "on" if fh.get("old") else "off"
            new = "on" if fh.get("new") else "off"
            profile_lines.append(
                f"  [{fh.get('date', '')}] {fh['flag']}: {old} → {new} ({fh.get('source', 'unknown')})"
            )

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

    # --- Financial metrics ---------------------------------------------------
    if ctx.financial_metrics:
        fin_lines = ["=== FINANCIAL METRICS ==="]
        sorted_years = sorted(ctx.financial_metrics.keys(), reverse=True)
        prev_year_data: dict[str, Any] | None = None

        for yr in sorted_years:
            yr_data = ctx.financial_metrics[yr]
            fin_lines.append(f"\nTax Year {yr}:")
            for name, info in sorted(yr_data.items()):
                val = info.get("value")
                if val is None:
                    continue
                line = f"  {name}: ${val:,.2f}"
                if info.get("line_reference"):
                    line += f" ({info['line_reference']})"
                if info.get("amended"):
                    line += " [AMENDED]"
                # YoY change for QUARTERLY_ESTIMATE purpose
                if purpose == ContextPurpose.QUARTERLY_ESTIMATE and prev_year_data:
                    prev_info = prev_year_data.get(name)
                    if prev_info and prev_info.get("value"):
                        prev_val = prev_info["value"]
                        if prev_val != 0:
                            pct = ((val - prev_val) / abs(prev_val)) * 100
                            line += f" ({pct:+.1f}% YoY)"
                fin_lines.append(line)

            # For QUARTERLY_ESTIMATE: note estimated payment status
            if purpose == ContextPurpose.QUARTERLY_ESTIMATE:
                paid_qs = []
                for q in range(1, 5):
                    qname = f"estimated_payments_q{q}"
                    if qname in yr_data and yr_data[qname].get("value"):
                        paid_qs.append(f"Q{q}")
                if paid_qs:
                    fin_lines.append(f"  Estimated payments made: {', '.join(paid_qs)}")

            prev_year_data = yr_data

        sections.append("\n".join(fin_lines))

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

    # --- Session history (prior advisory interactions) -----------------------
    if ctx.session_history:
        session_lines = ["=== PRIOR ADVISORY INTERACTIONS ==="]
        for entry in ctx.session_history:
            session_lines.append(entry.get("formatted", ""))
        sections.append("\n".join(session_lines))

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

    # --- Client journal -----------------------------------------------------
    if ctx.journal_entries:
        journal_lines = ["=== CLIENT JOURNAL ==="]
        for entry in ctx.journal_entries:
            date_str = entry.get("date", "")
            entry_type = entry.get("type", "").replace("_", " ")
            title = entry.get("title", "")
            content = entry.get("content")

            prefix = "[PINNED] " if entry.get("pinned") else ""
            line = f"{prefix}[{date_str}] [{entry_type}] {title}"
            if content:
                line += f": {content}"
            journal_lines.append(line)
        sections.append("\n".join(journal_lines))

    # --- Engagement calendar ------------------------------------------------
    if ctx.engagement_calendar:
        cal_lines = ["=== UPCOMING ENGAGEMENT DEADLINES ==="]
        for item in ctx.engagement_calendar:
            parts = [f"• {item['task']}"]
            if item.get("priority"):
                parts.append(f"[{item['priority'].upper()}]")
            parts.append(f"due {item['date']}")
            if item.get("template"):
                parts.append(f"({item['template']})")
            cal_lines.append(" ".join(parts))
        sections.append("\n".join(cal_lines))

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

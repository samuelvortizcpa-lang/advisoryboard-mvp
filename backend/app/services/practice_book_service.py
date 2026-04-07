"""
Practice Book Export — full-practice or single-client PDF reports.

Generates professional PDFs matching the strategy impact report styling
(dark navy headers, medium blue subheaders, Helvetica, 1-inch margins,
alternating table row shading).

Public functions:
  generate_client_practice_page  — structured data for one client
  generate_practice_summary      — practice-level aggregate data
  generate_practice_book_pdf     — full multi-client PDF (bytes)
  generate_single_client_pdf     — single-client PDF (bytes)
"""

from __future__ import annotations

import io
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.models.action_item import ActionItem
from app.models.client import Client
from app.models.client_communication import ClientCommunication
from app.models.client_engagement import ClientEngagement
from app.models.client_financial_metric import ClientFinancialMetric
from app.models.client_strategy_status import ClientStrategyStatus
from app.models.document import Document
from app.models.engagement_template import EngagementTemplate
from app.models.journal_entry import JournalEntry
from app.models.organization import Organization
from app.models.tax_strategy import TaxStrategy
from app.models.data_contradiction import DataContradiction
from app.models.user import User

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared constants (match strategy_report_service.py)
# ---------------------------------------------------------------------------

NAVY = "#1B3A5C"
BLUE = "#2E75B6"
DARK = "#1a1a1a"
GRAY = "#6b7280"
LIGHT_GRAY = "#f3f4f6"
ALT_ROW = "#f9fafb"

PROFILE_FLAGS = [
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

KEY_METRICS = [
    "adjusted_gross_income",
    "gross_receipts",
    "total_tax",
    "total_income",
    "taxable_income",
]


def _fmt_money(n: float) -> str:
    if abs(n) >= 1_000_000:
        return f"${n / 1_000_000:,.1f}M"
    if abs(n) >= 1_000:
        return f"${n:,.0f}"
    return f"${n:,.2f}"


def _trunc(s: str | None, length: int = 120) -> str:
    if not s:
        return ""
    return s[:length] + ("..." if len(s) > length else "")


# ═══════════════════════════════════════════════════════════════════════════
# Function 1: generate_client_practice_page
# ═══════════════════════════════════════════════════════════════════════════


def generate_client_practice_page(
    db: Session,
    client_id: UUID,
    user_id: str,
) -> dict[str, Any]:
    """Gather all data for a single client's practice book section."""

    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise ValueError("Client not found")

    current_year = date.today().year

    return {
        "client_profile": _gather_client_profile(db, client),
        "financial_summary": _gather_financial_summary(db, client_id),
        "strategy_summary": _gather_strategy_summary(db, client, current_year),
        "journal_highlights": _gather_journal_highlights(db, client_id),
        "communication_summary": _gather_communication_summary(db, client_id, user_id),
        "document_inventory": _gather_document_inventory(db, client_id),
        "open_action_items": _gather_open_action_items(db, client_id),
        "engagement_health": _compute_engagement_health(db, client_id, user_id, current_year),
    }


# ── 1. Client profile ────────────────────────────────────────────────────


def _gather_client_profile(db: Session, client: Client) -> dict[str, Any]:
    # Engagement start date: earliest document or client created_at
    earliest_doc = (
        db.query(func.min(Document.upload_date))
        .filter(Document.client_id == client.id)
        .scalar()
    )
    engagement_start = earliest_doc or (
        client.created_at.date() if client.created_at else None
    )

    # Service scope from engagement template
    service_scope = None
    eng = (
        db.query(ClientEngagement)
        .options(joinedload(ClientEngagement.template))
        .filter(
            ClientEngagement.client_id == client.id,
            ClientEngagement.is_active == True,  # noqa: E712
        )
        .first()
    )
    if eng and eng.template:
        service_scope = eng.template.name

    # Active profile flags
    flags = [f for f in PROFILE_FLAGS if getattr(client, f, False)]

    return {
        "name": client.name,
        "entity_type": client.entity_type,
        "industry": client.industry,
        "email": client.email,
        "business_name": client.business_name,
        "engagement_start": engagement_start.isoformat() if engagement_start else None,
        "service_scope": service_scope,
        "profile_flags": flags,
        "custom_instructions": _trunc(client.custom_instructions, 200),
    }


# ── 2. Financial summary ─────────────────────────────────────────────────


def _gather_financial_summary(
    db: Session, client_id: UUID,
) -> dict[str, Any]:
    current_year = date.today().year
    years = list(range(current_year - 4, current_year + 1))

    metrics = (
        db.query(ClientFinancialMetric)
        .filter(
            ClientFinancialMetric.client_id == client_id,
            ClientFinancialMetric.tax_year.in_(years),
            ClientFinancialMetric.metric_name.in_(KEY_METRICS),
        )
        .all()
    )

    result: dict[int, dict[str, Any]] = {}
    amended_years: set[int] = set()

    for m in metrics:
        yr = m.tax_year
        if yr not in result:
            result[yr] = {}
        if m.metric_value is not None:
            result[yr][m.metric_name] = float(m.metric_value)
        if m.is_amended:
            amended_years.add(yr)

    return {
        "years": {str(y): result.get(y, {}) for y in years},
        "amended_years": sorted(amended_years),
    }


# ── 3. Strategy summary ──────────────────────────────────────────────────


def _gather_strategy_summary(
    db: Session, client: Client, tax_year: int,
) -> dict[str, Any]:
    statuses = (
        db.query(ClientStrategyStatus)
        .filter(
            ClientStrategyStatus.client_id == client.id,
            ClientStrategyStatus.tax_year == tax_year,
        )
        .all()
    )

    implemented = []
    counts = {"implemented": 0, "recommended": 0, "declined": 0, "not_reviewed": 0}
    total_impact = 0.0

    for s in statuses:
        status_key = s.status if s.status in counts else "not_reviewed"
        counts[status_key] = counts.get(status_key, 0) + 1

        if s.status == "implemented":
            impact = float(s.estimated_impact) if s.estimated_impact else 0.0
            total_impact += impact
            # Load the strategy name
            strategy = db.query(TaxStrategy).filter(TaxStrategy.id == s.strategy_id).first()
            implemented.append({
                "name": strategy.name if strategy else "Unknown",
                "impact": impact,
                "notes": _trunc(s.notes),
            })

    return {
        "tax_year": tax_year,
        "counts": counts,
        "total_impact": total_impact,
        "implemented": implemented,
    }


# ── 4. Journal highlights ────────────────────────────────────────────────


def _gather_journal_highlights(
    db: Session, client_id: UUID,
) -> list[dict[str, Any]]:
    # Pinned entries
    pinned = (
        db.query(JournalEntry)
        .filter(
            JournalEntry.client_id == client_id,
            JournalEntry.is_pinned == True,  # noqa: E712
        )
        .order_by(JournalEntry.created_at.desc())
        .all()
    )

    # Last 10 entries
    recent = (
        db.query(JournalEntry)
        .filter(JournalEntry.client_id == client_id)
        .order_by(JournalEntry.created_at.desc())
        .limit(10)
        .all()
    )

    # Merge, deduplicate, and sort by date desc
    seen: set[UUID] = set()
    entries: list[dict[str, Any]] = []
    for e in pinned + recent:
        if e.id in seen:
            continue
        seen.add(e.id)
        entries.append({
            "date": (e.effective_date or e.created_at.date()).isoformat()
                if e.effective_date or e.created_at
                else None,
            "type": e.entry_type,
            "title": e.title,
            "content_preview": _trunc(e.content),
            "is_pinned": e.is_pinned,
        })

    entries.sort(key=lambda x: x["date"] or "", reverse=True)
    return entries


# ── 5. Communication summary ─────────────────────────────────────────────


def _gather_communication_summary(
    db: Session, client_id: UUID, user_id: str,
) -> dict[str, Any]:
    comms = (
        db.query(ClientCommunication)
        .filter(
            ClientCommunication.client_id == client_id,
            ClientCommunication.user_id == user_id,
        )
        .order_by(ClientCommunication.sent_at.desc())
        .all()
    )

    total = len(comms)
    last_contact = comms[0].sent_at if comms else None

    # Communication frequency
    frequency = "none"
    if total > 0 and last_contact:
        first = comms[-1].sent_at
        span_days = max((last_contact - first).days, 1) if total > 1 else 0
        if total >= 2:
            avg_gap = span_days / (total - 1)
            if avg_gap <= 35:
                frequency = "monthly"
            elif avg_gap <= 100:
                frequency = "quarterly"
            elif avg_gap <= 200:
                frequency = "semi-annual"
            else:
                frequency = "annual"
        else:
            frequency = "single"

    # Open items across all threads
    open_items_count = 0
    for c in comms:
        if c.open_items:
            items = c.open_items if isinstance(c.open_items, list) else []
            open_items_count += sum(
                1 for item in items
                if isinstance(item, dict) and item.get("status") == "open"
            )

    return {
        "total_emails": total,
        "frequency": frequency,
        "last_contact": last_contact.isoformat() if last_contact else None,
        "open_items_count": open_items_count,
    }


# ── 6. Document inventory ────────────────────────────────────────────────


def _gather_document_inventory(
    db: Session, client_id: UUID,
) -> list[dict[str, Any]]:
    docs = (
        db.query(Document)
        .filter(Document.client_id == client_id)
        .order_by(Document.document_type, Document.upload_date.desc())
        .all()
    )

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for d in docs:
        doc_type = d.document_type or "uncategorized"
        grouped[doc_type].append({
            "filename": d.filename,
            "subtype": d.document_subtype,
            "period": d.document_period,
            "is_superseded": d.is_superseded,
            "amendment_number": d.amendment_number,
            "upload_date": d.upload_date.isoformat() if d.upload_date else None,
        })

    return [
        {"type": doc_type, "documents": docs_list}
        for doc_type, docs_list in sorted(grouped.items())
    ]


# ── 7. Open action items ─────────────────────────────────────────────────


def _gather_open_action_items(
    db: Session, client_id: UUID,
) -> list[dict[str, Any]]:
    items = (
        db.query(ActionItem)
        .filter(
            ActionItem.client_id == client_id,
            ActionItem.status == "pending",
        )
        .order_by(ActionItem.due_date.asc().nullslast(), ActionItem.priority.desc())
        .all()
    )
    return [
        {
            "text": i.text,
            "priority": i.priority,
            "due_date": i.due_date.isoformat() if i.due_date else None,
            "source": i.source,
        }
        for i in items
    ]


# ── 8. Engagement health score ───────────────────────────────────────────


def _compute_engagement_health(
    db: Session,
    client_id: UUID,
    user_id: str,
    current_year: int,
) -> dict[str, Any]:
    scores: dict[str, float] = {}

    # -- Communication frequency (25%) --
    now = datetime.now(timezone.utc)
    recent_comms = (
        db.query(func.count(ClientCommunication.id))
        .filter(
            ClientCommunication.client_id == client_id,
            ClientCommunication.sent_at >= now - timedelta(days=365),
        )
        .scalar()
    ) or 0

    if recent_comms >= 12:
        scores["communication"] = 100
    elif recent_comms >= 4:
        scores["communication"] = 75
    elif recent_comms >= 2:
        scores["communication"] = 50
    elif recent_comms >= 1:
        scores["communication"] = 25
    else:
        scores["communication"] = 0

    # -- Action item completion rate (20%) --
    completed = (
        db.query(func.count(ActionItem.id))
        .filter(ActionItem.client_id == client_id, ActionItem.status == "completed")
        .scalar()
    ) or 0
    overdue = (
        db.query(func.count(ActionItem.id))
        .filter(
            ActionItem.client_id == client_id,
            ActionItem.status == "pending",
            ActionItem.due_date < date.today(),
        )
        .scalar()
    ) or 0

    denom = completed + overdue
    scores["action_items"] = round(completed / denom * 100) if denom > 0 else 100

    # -- Strategy coverage (20%) --
    client = db.query(Client).filter(Client.id == client_id).first()
    total_applicable = 0
    total_implemented = 0
    if client:
        flags = {f: getattr(client, f, False) for f in PROFILE_FLAGS}
        strategies = (
            db.query(TaxStrategy)
            .filter(TaxStrategy.is_active == True)  # noqa: E712
            .all()
        )
        applicable_ids = set()
        for s in strategies:
            req = s.required_flags or []
            if not req or any(flags.get(f, False) for f in req):
                applicable_ids.add(s.id)

        total_applicable = len(applicable_ids)
        if applicable_ids:
            total_implemented = (
                db.query(func.count(ClientStrategyStatus.id))
                .filter(
                    ClientStrategyStatus.client_id == client_id,
                    ClientStrategyStatus.tax_year == current_year,
                    ClientStrategyStatus.status == "implemented",
                    ClientStrategyStatus.strategy_id.in_(applicable_ids),
                )
                .scalar()
            ) or 0

    scores["strategy"] = (
        round(total_implemented / total_applicable * 100)
        if total_applicable > 0 else 0
    )

    # -- Document currency (20%) --
    has_current = (
        db.query(Document.id)
        .filter(
            Document.client_id == client_id,
            Document.document_type == "tax_return",
            Document.document_period.ilike(f"%{current_year}%"),
        )
        .first()
    ) is not None

    has_prior = (
        db.query(Document.id)
        .filter(
            Document.client_id == client_id,
            Document.document_type == "tax_return",
            Document.document_period.ilike(f"%{current_year - 1}%"),
        )
        .first()
    ) is not None

    scores["documents"] = (50 if has_current else 0) + (50 if has_prior else 0)

    # -- Journal depth (15%) --
    pinned_count = (
        db.query(func.count(JournalEntry.id))
        .filter(
            JournalEntry.client_id == client_id,
            JournalEntry.is_pinned == True,  # noqa: E712
        )
        .scalar()
    ) or 0
    recent_manual = (
        db.query(func.count(JournalEntry.id))
        .filter(
            JournalEntry.client_id == client_id,
            JournalEntry.entry_type == "manual",
            JournalEntry.created_at >= now - timedelta(days=180),
        )
        .scalar()
    ) or 0

    journal_score = min(100, (50 if pinned_count > 0 else 0) + min(50, recent_manual * 10))
    scores["journal"] = journal_score

    # -- Data quality penalty --
    high_contradictions = (
        db.query(func.count(DataContradiction.id))
        .filter(
            DataContradiction.client_id == client_id,
            DataContradiction.status == "open",
            DataContradiction.severity == "high",
        )
        .scalar()
    ) or 0
    medium_contradictions = (
        db.query(func.count(DataContradiction.id))
        .filter(
            DataContradiction.client_id == client_id,
            DataContradiction.status == "open",
            DataContradiction.severity == "medium",
        )
        .scalar()
    ) or 0

    data_quality_penalty = (high_contradictions * 15) + (medium_contradictions * 5)
    scores["data_quality_penalty"] = data_quality_penalty

    # -- Weighted total --
    total = round(
        scores["communication"] * 0.25
        + scores["action_items"] * 0.20
        + scores["strategy"] * 0.20
        + scores["documents"] * 0.20
        + scores["journal"] * 0.15
    )
    total = max(0, total - data_quality_penalty)

    # Data quality label for export
    if high_contradictions > 0:
        data_quality_label = f"Urgent ({high_contradictions + medium_contradictions})"
    elif medium_contradictions > 0:
        data_quality_label = f"Review Needed ({medium_contradictions})"
    else:
        data_quality_label = "Clean"

    return {
        "total": total,
        "breakdown": scores,
        "_comm_count": recent_comms,
        "data_quality": data_quality_label,
        "data_quality_counts": {
            "high": high_contradictions,
            "medium": medium_contradictions,
        },
    }


# ═══════════════════════════════════════════════════════════════════════════
# Function 2: generate_practice_summary
# ═══════════════════════════════════════════════════════════════════════════


def generate_practice_summary(
    db: Session,
    user_id: str,
    org_id: UUID | None = None,
) -> dict[str, Any]:
    """Gather practice-level summary data."""

    # All clients
    q = db.query(Client)
    if org_id:
        q = q.filter(Client.org_id == org_id)
    else:
        q = q.filter(Client.owner_id == user_id)
    clients = q.all()

    total = len(clients)
    by_entity: dict[str, int] = defaultdict(int)
    for c in clients:
        by_entity[c.entity_type or "unspecified"] += 1

    # Total advisory impact
    current_year = date.today().year
    client_ids = [c.id for c in clients]
    total_impact = 0.0
    if client_ids:
        impact_sum = (
            db.query(func.sum(ClientStrategyStatus.estimated_impact))
            .filter(
                ClientStrategyStatus.client_id.in_(client_ids),
                ClientStrategyStatus.status == "implemented",
            )
            .scalar()
        )
        total_impact = float(impact_sum) if impact_sum else 0.0

    # Per-client health scores, complexity, and row data
    health_scores: list[int] = []
    complexity: dict[str, int] = {"low": 0, "medium": 0, "high": 0}
    client_rows: list[dict[str, Any]] = []

    for c in clients:
        health = _compute_engagement_health(db, c.id, user_id, current_year)
        health_scores.append(health["total"])

        # Complexity = document count + strategy status count
        doc_count = (
            db.query(func.count(Document.id))
            .filter(Document.client_id == c.id)
            .scalar()
        ) or 0
        strat_count = (
            db.query(func.count(ClientStrategyStatus.id))
            .filter(ClientStrategyStatus.client_id == c.id)
            .scalar()
        ) or 0
        score = doc_count + strat_count
        if score >= 15:
            complexity["high"] += 1
        elif score >= 5:
            complexity["medium"] += 1
        else:
            complexity["low"] += 1

        # Open action items
        open_actions = (
            db.query(func.count(ActionItem.id))
            .filter(ActionItem.client_id == c.id, ActionItem.status == "pending")
            .scalar()
        ) or 0

        # Last communication
        last_comm = (
            db.query(func.max(ClientCommunication.sent_at))
            .filter(ClientCommunication.client_id == c.id)
            .scalar()
        )

        # Per-client impact
        client_impact = (
            db.query(func.sum(ClientStrategyStatus.estimated_impact))
            .filter(
                ClientStrategyStatus.client_id == c.id,
                ClientStrategyStatus.status == "implemented",
            )
            .scalar()
        )

        # Journal entry count
        journal_count = (
            db.query(func.count(JournalEntry.id))
            .filter(JournalEntry.client_id == c.id)
            .scalar()
        ) or 0

        client_rows.append({
            "client_id": str(c.id),
            "name": c.name,
            "entity_type": c.entity_type or "unspecified",
            "health_score": health["total"],
            "health_breakdown": health,
            "document_count": doc_count,
            "open_action_count": open_actions,
            "last_contact": last_comm.isoformat() if last_comm else None,
            "estimated_impact": float(client_impact) if client_impact else 0.0,
            "journal_count": journal_count,
            "communication_count": health.get("_comm_count", 0),
            "data_quality": health.get("data_quality", "Clean"),
        })

    avg_health = round(sum(health_scores) / len(health_scores)) if health_scores else 0
    transition_ready = (
        round(sum(1 for s in health_scores if s > 60) / len(health_scores) * 100)
        if health_scores else 0
    )

    return {
        "total_clients": total,
        "by_entity_type": dict(by_entity),
        "total_advisory_impact": total_impact,
        "avg_engagement_health": avg_health,
        "complexity_distribution": complexity,
        "transition_readiness": transition_ready,
        "clients": client_rows,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Function 3: generate_practice_book_pdf
# ═══════════════════════════════════════════════════════════════════════════


def generate_practice_book_pdf(
    db: Session,
    user_id: str,
    org_id: UUID | None = None,
    client_ids: list[UUID] | None = None,
) -> bytes:
    """Generate the full practice book PDF."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    # Resolve firm / advisor name
    user = db.query(User).filter(User.clerk_id == user_id).first()
    advisor_name = "Advisor"
    if user:
        parts = [user.first_name, user.last_name]
        advisor_name = " ".join(p for p in parts if p) or user.email or "Advisor"

    firm_name = None
    if org_id:
        org = db.query(Organization).filter(Organization.id == org_id).first()
        if org and org.org_type != "personal":
            firm_name = org.name

    # Fetch clients
    q = db.query(Client)
    if client_ids:
        q = q.filter(Client.id.in_(client_ids))
    elif org_id:
        q = q.filter(Client.org_id == org_id)
    else:
        q = q.filter(Client.owner_id == user_id)
    clients = q.order_by(Client.name).all()

    # Practice summary
    summary = generate_practice_summary(db, user_id, org_id)

    # Gather per-client data
    client_pages: list[dict[str, Any]] = []
    for c in clients:
        try:
            page = generate_client_practice_page(db, c.id, user_id)
            page["_client_name"] = c.name
            page["_client_id"] = str(c.id)
            client_pages.append(page)
        except Exception:
            logger.warning("Failed to gather data for client %s", c.id, exc_info=True)

    # ── Build PDF ─────────────────────────────────────────────────────

    buf = io.BytesIO()
    header_name = firm_name or advisor_name

    # We need page numbers, so we use a NumberedCanvas approach
    page_count_holder: list[int] = [0]

    def _footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor(GRAY))
        canvas.drawString(
            inch, 0.45 * inch,
            f"Confidential — Page {doc.page}",
        )
        canvas.restoreState()
        page_count_holder[0] = max(page_count_holder[0], doc.page)

    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=inch,
        rightMargin=inch,
        topMargin=inch,
        bottomMargin=0.75 * inch,
    )

    styles = getSampleStyleSheet()
    s = _build_styles(styles)

    elements: list = []

    # ── Cover page ────────────────────────────────────────────────────
    elements.append(Spacer(1, 1.5 * inch))
    elements.append(Paragraph(header_name, s["firm"]))
    elements.append(Spacer(1, 0.1 * inch))
    elements.append(Paragraph("Practice Book", s["title"]))
    elements.append(Spacer(1, 0.15 * inch))
    elements.append(Paragraph(date.today().strftime("%B %d, %Y"), s["date"]))
    elements.append(Spacer(1, 0.3 * inch))
    elements.append(Paragraph(
        f"{len(clients)} client{'s' if len(clients) != 1 else ''}",
        s["subtitle"],
    ))

    # ── Practice summary page ─────────────────────────────────────────
    elements.append(PageBreak())
    elements.append(Paragraph("Practice Summary", s["section"]))

    # Summary metrics
    summary_metrics = [
        ["Total Clients", str(summary["total_clients"])],
        ["Advisory Impact", _fmt_money(summary["total_advisory_impact"])
         if summary["total_advisory_impact"] > 0 else "—"],
        ["Avg Health Score", f"{summary['avg_engagement_health']}%"],
        ["Transition Ready", f"{summary['transition_readiness']}%"],
    ]
    metric_cells = []
    for label, value in summary_metrics:
        metric_cells.append([
            Paragraph(value, s["metric_value"]),
            Paragraph(label, s["metric_label"]),
        ])
    m_table = Table([metric_cells], colWidths=[doc.width / 4] * 4)
    m_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(LIGHT_GRAY)),
    ]))
    elements.append(m_table)
    elements.append(Spacer(1, 0.25 * inch))

    # Entity type distribution
    elements.append(Paragraph("Client Distribution by Entity Type", s["subsection"]))
    for etype, count in sorted(summary["by_entity_type"].items()):
        label = etype.replace("_", " ").title()
        elements.append(Paragraph(f"{label}: {count}", s["body"]))
    elements.append(Spacer(1, 0.15 * inch))

    # Complexity distribution
    elements.append(Paragraph("Client Complexity", s["subsection"]))
    cx = summary["complexity_distribution"]
    elements.append(Paragraph(
        f"High: {cx.get('high', 0)}  |  Medium: {cx.get('medium', 0)}  |  Low: {cx.get('low', 0)}",
        s["body"],
    ))

    # ── Clients with data quality issues ─────────────────────────────
    dq_clients = [c for c in summary["clients"] if c.get("data_quality", "Clean") != "Clean"]
    if dq_clients:
        elements.append(Spacer(1, 0.2 * inch))
        elements.append(Paragraph("Clients with Data Quality Issues", s["subsection"]))
        for c in sorted(dq_clients, key=lambda x: 0 if "Urgent" in x.get("data_quality", "") else 1):
            dq = c["data_quality"]
            color = "#dc2626" if "Urgent" in dq else "#d97706"
            elements.append(Paragraph(
                f'{c["name"]} — <font color="{color}"><b>{dq}</b></font>',
                s["body"],
            ))

    # ── Table of contents ─────────────────────────────────────────────
    elements.append(PageBreak())
    elements.append(Paragraph("Table of Contents", s["section"]))
    elements.append(Spacer(1, 0.15 * inch))

    for i, page_data in enumerate(client_pages, 1):
        profile = page_data["client_profile"]
        health = page_data["engagement_health"]["total"]
        scope = profile.get("service_scope") or ""
        entry = f"{i}. {profile['name']}"
        if scope:
            entry += f"  —  {scope}"
        entry += f"  (Health: {health}%)"
        elements.append(Paragraph(entry, s["body"]))

    # ── Per-client sections ───────────────────────────────────────────
    for page_data in client_pages:
        elements.append(PageBreak())
        _build_client_section(elements, page_data, s, doc)

    # Build
    doc.build(elements, onFirstPage=_footer, onLaterPages=_footer)
    pdf_bytes = buf.getvalue()
    buf.close()
    return pdf_bytes


# ═══════════════════════════════════════════════════════════════════════════
# Function 4: generate_single_client_pdf
# ═══════════════════════════════════════════════════════════════════════════


def generate_single_client_pdf(
    db: Session,
    client_id: UUID,
    user_id: str,
) -> bytes:
    """Generate a single-client practice book PDF (no practice summary)."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
    )

    page_data = generate_client_practice_page(db, client_id, user_id)
    profile = page_data["client_profile"]
    client_name = profile["name"]

    # Advisor info
    user = db.query(User).filter(User.clerk_id == user_id).first()
    advisor_name = "Advisor"
    if user:
        parts = [user.first_name, user.last_name]
        advisor_name = " ".join(p for p in parts if p) or user.email or "Advisor"

    client = db.query(Client).filter(Client.id == client_id).first()
    firm_name = None
    if client and client.org_id:
        org = db.query(Organization).filter(Organization.id == client.org_id).first()
        if org and org.org_type != "personal":
            firm_name = org.name

    buf = io.BytesIO()
    header_name = firm_name or advisor_name

    def _footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor(GRAY))
        canvas.drawString(
            inch, 0.45 * inch,
            f"Confidential — Page {doc.page}",
        )
        canvas.restoreState()

    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=inch,
        rightMargin=inch,
        topMargin=inch,
        bottomMargin=0.75 * inch,
    )

    styles = getSampleStyleSheet()
    s = _build_styles(styles)

    elements: list = []

    # Cover
    elements.append(Spacer(1, 1.5 * inch))
    elements.append(Paragraph(header_name, s["firm"]))
    elements.append(Spacer(1, 0.1 * inch))
    elements.append(Paragraph("Client Practice Report", s["title"]))
    elements.append(Spacer(1, 0.1 * inch))
    elements.append(Paragraph(client_name, s["subtitle"]))
    elements.append(Spacer(1, 0.15 * inch))
    elements.append(Paragraph(date.today().strftime("%B %d, %Y"), s["date"]))

    # Client section
    elements.append(PageBreak())
    page_data["_client_name"] = client_name
    page_data["_client_id"] = str(client_id)
    _build_client_section(elements, page_data, s, doc)

    doc.build(elements, onFirstPage=_footer, onLaterPages=_footer)
    pdf_bytes = buf.getvalue()
    buf.close()
    return pdf_bytes


# ═══════════════════════════════════════════════════════════════════════════
# PDF building helpers
# ═══════════════════════════════════════════════════════════════════════════


def _build_styles(base_styles) -> dict[str, Any]:
    """Build all paragraph styles used in the practice book."""
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle

    return {
        "firm": ParagraphStyle(
            "PBFirm", parent=base_styles["Normal"],
            fontSize=10, textColor=colors.HexColor(GRAY), spaceAfter=4,
        ),
        "title": ParagraphStyle(
            "PBTitle", parent=base_styles["Title"],
            fontSize=22, textColor=colors.HexColor(NAVY),
            spaceAfter=6, leading=26,
        ),
        "subtitle": ParagraphStyle(
            "PBSubtitle", parent=base_styles["Normal"],
            fontSize=13, textColor=colors.HexColor(BLUE), spaceAfter=4,
        ),
        "date": ParagraphStyle(
            "PBDate", parent=base_styles["Normal"],
            fontSize=9, textColor=colors.HexColor(GRAY), spaceAfter=24,
        ),
        "section": ParagraphStyle(
            "PBSection", parent=base_styles["Heading2"],
            fontSize=14, textColor=colors.HexColor(NAVY),
            spaceBefore=16, spaceAfter=10, fontName="Helvetica-Bold",
        ),
        "subsection": ParagraphStyle(
            "PBSubsection", parent=base_styles["Heading3"],
            fontSize=11, textColor=colors.HexColor(BLUE),
            spaceBefore=10, spaceAfter=6, fontName="Helvetica-Bold",
        ),
        "body": ParagraphStyle(
            "PBBody", parent=base_styles["Normal"],
            fontSize=9.5, textColor=colors.HexColor(DARK),
            leading=13, spaceAfter=4,
        ),
        "bold": ParagraphStyle(
            "PBBold", parent=base_styles["Normal"],
            fontSize=9.5, textColor=colors.HexColor(DARK),
            fontName="Helvetica-Bold", spaceAfter=2,
        ),
        "notes": ParagraphStyle(
            "PBNotes", parent=base_styles["Normal"],
            fontSize=9.5, textColor=colors.HexColor(GRAY),
            fontName="Helvetica-Oblique", leftIndent=12,
        ),
        "metric_label": ParagraphStyle(
            "PBMetricLabel", parent=base_styles["Normal"],
            fontSize=8, textColor=colors.HexColor(GRAY),
        ),
        "metric_value": ParagraphStyle(
            "PBMetricValue", parent=base_styles["Normal"],
            fontSize=16, fontName="Helvetica-Bold",
            textColor=colors.HexColor(NAVY),
        ),
        "small": ParagraphStyle(
            "PBSmall", parent=base_styles["Normal"],
            fontSize=8, textColor=colors.HexColor(GRAY), leading=10,
        ),
    }


def _build_client_section(
    elements: list,
    page_data: dict[str, Any],
    s: dict[str, Any],
    doc,
) -> None:
    """Append all flowables for one client's section."""
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

    profile = page_data["client_profile"]
    health = page_data["engagement_health"]

    # ── Client header ─────────────────────────────────────────────────
    elements.append(Paragraph(profile["name"], s["section"]))

    # Health score badge
    score = health["total"]
    if score >= 75:
        badge_color = "#059669"
    elif score >= 50:
        badge_color = "#d97706"
    else:
        badge_color = "#dc2626"
    elements.append(Paragraph(
        f'Engagement Health: <font color="{badge_color}"><b>{score}%</b></font>',
        s["body"],
    ))
    elements.append(Spacer(1, 0.1 * inch))

    # ── Profile details ───────────────────────────────────────────────
    elements.append(Paragraph("Client Profile", s["subsection"]))

    profile_rows = []
    if profile.get("entity_type"):
        profile_rows.append(["Entity Type", profile["entity_type"].replace("_", " ").title()])
    if profile.get("industry"):
        profile_rows.append(["Industry", profile["industry"]])
    if profile.get("email"):
        profile_rows.append(["Email", profile["email"]])
    if profile.get("business_name"):
        profile_rows.append(["Business", profile["business_name"]])
    if profile.get("engagement_start"):
        profile_rows.append(["Engagement Since", profile["engagement_start"]])
    if profile.get("service_scope"):
        profile_rows.append(["Service Scope", profile["service_scope"]])
    if profile.get("profile_flags"):
        flags_str = ", ".join(
            f.replace("has_", "").replace("is_", "").replace("_", " ").title()
            for f in profile["profile_flags"]
        )
        profile_rows.append(["Profile Flags", flags_str])

    if profile_rows:
        profile_data = [
            [Paragraph(f"<b>{r[0]}</b>", s["small"]), Paragraph(str(r[1]), s["body"])]
            for r in profile_rows
        ]
        pt = Table(profile_data, colWidths=[1.5 * inch, doc.width - 1.5 * inch])
        pt.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ]))
        elements.append(pt)

    if profile.get("custom_instructions"):
        elements.append(Paragraph(f"AI Instructions: {profile['custom_instructions']}", s["notes"]))

    elements.append(Spacer(1, 0.15 * inch))

    # ── Financial summary ─────────────────────────────────────────────
    fin = page_data["financial_summary"]
    years_data = fin["years"]
    active_years = [y for y in sorted(years_data.keys()) if years_data[y]]

    if active_years:
        elements.append(Paragraph("Financial Summary", s["subsection"]))

        # Build table: metric names as rows, years as columns
        header = ["Metric"] + [
            f"{y}{'*' if int(y) in fin['amended_years'] else ''}"
            for y in active_years
        ]
        table_data = [header]

        for metric in KEY_METRICS:
            label = metric.replace("_", " ").title()
            row = [Paragraph(label, s["body"])]
            for y in active_years:
                val = years_data[y].get(metric)
                row.append(Paragraph(
                    _fmt_money(val) if val is not None else "—",
                    s["body"],
                ))
            table_data.append(row)

        n_cols = len(active_years) + 1
        name_w = 2 * inch
        year_w = (doc.width - name_w) / max(len(active_years), 1)
        col_widths = [name_w] + [year_w] * len(active_years)

        ft = Table(table_data, colWidths=col_widths, repeatRows=1)
        ft.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor(NAVY)),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(LIGHT_GRAY)),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("LINEBELOW", (0, 0), (-1, 0), 0.75, colors.HexColor(NAVY)),
            ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.lightgrey),
            *[
                ("BACKGROUND", (0, i), (-1, i), colors.HexColor(ALT_ROW))
                for i in range(2, len(table_data), 2)
            ],
        ]))
        elements.append(ft)

        if fin["amended_years"]:
            elements.append(Paragraph(
                "* Amended return on file",
                s["small"],
            ))
        elements.append(Spacer(1, 0.15 * inch))

    # ── Strategy summary ──────────────────────────────────────────────
    strat = page_data["strategy_summary"]
    elements.append(Paragraph(
        f"Strategy Summary — {strat['tax_year']}",
        s["subsection"],
    ))

    counts = strat["counts"]
    elements.append(Paragraph(
        f"Implemented: {counts['implemented']}  |  "
        f"Recommended: {counts['recommended']}  |  "
        f"Declined: {counts['declined']}",
        s["body"],
    ))
    if strat["total_impact"] > 0:
        elements.append(Paragraph(
            f"Total Estimated Impact: <b>{_fmt_money(strat['total_impact'])}</b>",
            s["body"],
        ))
    if strat["implemented"]:
        for si in strat["implemented"][:5]:
            impact_str = _fmt_money(si["impact"]) if si["impact"] else "—"
            elements.append(Paragraph(
                f"  • {si['name']} ({impact_str})",
                s["body"],
            ))
    elements.append(Spacer(1, 0.1 * inch))

    # ── Communication summary ─────────────────────────────────────────
    comm = page_data["communication_summary"]
    elements.append(Paragraph("Communication", s["subsection"]))
    elements.append(Paragraph(
        f"Total emails: {comm['total_emails']}  |  "
        f"Frequency: {comm['frequency']}  |  "
        f"Open items: {comm['open_items_count']}",
        s["body"],
    ))
    if comm["last_contact"]:
        elements.append(Paragraph(
            f"Last contact: {comm['last_contact'][:10]}",
            s["small"],
        ))
    elements.append(Spacer(1, 0.1 * inch))

    # ── Open action items ─────────────────────────────────────────────
    actions = page_data["open_action_items"]
    if actions:
        elements.append(Paragraph(
            f"Open Action Items ({len(actions)})",
            s["subsection"],
        ))

        header = ["Description", "Priority", "Due Date"]
        action_rows = [header]
        for a in actions[:15]:
            action_rows.append([
                Paragraph(_trunc(a["text"], 80), s["body"]),
                Paragraph((a["priority"] or "—").title(), s["body"]),
                Paragraph(a["due_date"] or "—", s["body"]),
            ])

        at = Table(
            action_rows,
            colWidths=[doc.width * 0.55, doc.width * 0.2, doc.width * 0.25],
            repeatRows=1,
        )
        at.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor(NAVY)),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(LIGHT_GRAY)),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("LINEBELOW", (0, 0), (-1, 0), 0.75, colors.HexColor(NAVY)),
            ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.lightgrey),
            *[
                ("BACKGROUND", (0, i), (-1, i), colors.HexColor(ALT_ROW))
                for i in range(2, len(action_rows), 2)
            ],
        ]))
        elements.append(at)
        if len(actions) > 15:
            elements.append(Paragraph(
                f"+ {len(actions) - 15} more items",
                s["small"],
            ))
        elements.append(Spacer(1, 0.1 * inch))

    # ── Document inventory ────────────────────────────────────────────
    doc_inv = page_data["document_inventory"]
    if doc_inv:
        elements.append(Paragraph("Documents on File", s["subsection"]))
        for group in doc_inv:
            doc_type = group["type"].replace("_", " ").title()
            elements.append(Paragraph(
                f"<b>{doc_type}</b> ({len(group['documents'])})",
                s["body"],
            ))
            for d in group["documents"][:8]:
                parts = [d["filename"]]
                if d.get("period"):
                    parts.append(d["period"])
                if d.get("is_superseded"):
                    parts.append("[superseded]")
                if d.get("amendment_number"):
                    parts.append(f"[amended #{d['amendment_number']}]")
                elements.append(Paragraph(f"  • {' — '.join(parts)}", s["small"]))
            if len(group["documents"]) > 8:
                elements.append(Paragraph(
                    f"  + {len(group['documents']) - 8} more",
                    s["small"],
                ))
        elements.append(Spacer(1, 0.1 * inch))

    # ── Journal highlights ────────────────────────────────────────────
    journal = page_data["journal_highlights"]
    if journal:
        elements.append(Paragraph("Journal Highlights", s["subsection"]))
        for j in journal[:8]:
            pin = "📌 " if j.get("is_pinned") else ""
            date_str = j.get("date", "")
            elements.append(Paragraph(
                f"<b>{pin}{j['title']}</b> ({date_str})",
                s["body"],
            ))
            if j.get("content_preview"):
                elements.append(Paragraph(j["content_preview"], s["notes"]))
        if len(journal) > 8:
            elements.append(Paragraph(
                f"+ {len(journal) - 8} more entries",
                s["small"],
            ))
        elements.append(Spacer(1, 0.1 * inch))

    # ── Data quality ─────────────────────────────────────────────────
    dq = health.get("data_quality", "Clean")
    dq_counts = health.get("data_quality_counts", {})
    if dq != "Clean":
        dq_color = "#dc2626" if dq_counts.get("high", 0) > 0 else "#d97706"
        elements.append(Paragraph("Data Quality", s["subsection"]))
        elements.append(Paragraph(
            f'Status: <font color="{dq_color}"><b>{dq}</b></font>',
            s["body"],
        ))
        if dq_counts.get("high", 0):
            elements.append(Paragraph(
                f"  High severity: {dq_counts['high']} conflict(s)", s["body"],
            ))
        if dq_counts.get("medium", 0):
            elements.append(Paragraph(
                f"  Medium severity: {dq_counts['medium']} conflict(s)", s["body"],
            ))
        elements.append(Paragraph(
            f"Health score penalty: -{health['breakdown'].get('data_quality_penalty', 0)} points",
            s["small"],
        ))
        elements.append(Spacer(1, 0.1 * inch))

    # ── Engagement health breakdown ───────────────────────────────────
    elements.append(Paragraph("Engagement Health Breakdown", s["subsection"]))
    breakdown = health["breakdown"]
    health_labels = {
        "communication": "Communication (25%)",
        "action_items": "Action Items (20%)",
        "strategy": "Strategy Coverage (20%)",
        "documents": "Document Currency (20%)",
        "journal": "Journal Depth (15%)",
    }
    for key, label in health_labels.items():
        val = breakdown.get(key, 0)
        elements.append(Paragraph(f"{label}: {val}%", s["body"]))
    if breakdown.get("data_quality_penalty", 0) > 0:
        elements.append(Paragraph(
            f"Data quality penalty: -{breakdown['data_quality_penalty']} pts",
            s["body"],
        ))

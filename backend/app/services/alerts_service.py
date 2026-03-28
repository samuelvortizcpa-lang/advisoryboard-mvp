"""
Smart Alerts service: computes cross-client alerts on demand.

Alert types:
- overdue_action:                pending action item with due_date < today
- upcoming_deadline:             pending action item with due_date within next 7 days
- stale_client:                  client with no documents and no chat messages in last 30 days
- stuck_document:                document where processed = false (stuck in processing)
- preparer_determination_needed: tax docs uploaded, preparer relationship not yet set
- consent_needed:                preparer confirmed, full §7216 consent required
- consent_expiring:              §7216 consent expires within 30 days
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.action_item import ActionItem
from app.models.chat_message import ChatMessage
from app.models.client import Client
from app.models.client_consent import ClientConsent
from app.models.dismissed_alert import DismissedAlert
from app.models.document import Document

logger = logging.getLogger(__name__)

SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}


def compute_alerts(
    db: Session,
    owner_id: UUID,
    clerk_user_id: str,
) -> list[dict[str, Any]]:
    """
    Compute all alerts for a user's clients, filtering out dismissed ones.

    Returns a list of alert dicts sorted by severity (critical first), then date.
    """
    today = date.today()
    seven_days = today + timedelta(days=7)
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)

    # Get all client IDs owned by this user
    client_rows = (
        db.query(Client.id, Client.name)
        .filter(Client.owner_id == owner_id)
        .all()
    )
    if not client_rows:
        return []

    client_ids = [r.id for r in client_rows]
    client_names = {r.id: r.name for r in client_rows}

    # Load dismissed alerts for this user
    dismissed = set()
    dismissed_rows = (
        db.query(DismissedAlert.alert_type, DismissedAlert.related_id)
        .filter(DismissedAlert.user_id == clerk_user_id)
        .all()
    )
    for d in dismissed_rows:
        dismissed.add((d.alert_type, d.related_id))

    alerts: list[dict[str, Any]] = []

    # ── 1. Overdue action items ──────────────────────────────────────────────
    overdue_items = (
        db.query(ActionItem)
        .filter(
            ActionItem.client_id.in_(client_ids),
            ActionItem.status == "pending",
            ActionItem.due_date < today,
            ActionItem.due_date.isnot(None),
        )
        .order_by(ActionItem.due_date.asc())
        .all()
    )
    for item in overdue_items:
        if ("overdue_action", item.id) in dismissed:
            continue
        days_overdue = (today - item.due_date).days
        alerts.append({
            "id": str(item.id),
            "type": "overdue_action",
            "severity": "critical",
            "client_id": str(item.client_id),
            "client_name": client_names.get(item.client_id, "Unknown"),
            "message": f"Action item overdue by {days_overdue} day{'s' if days_overdue != 1 else ''}: {item.text[:100]}",
            "related_id": str(item.id),
            "created_at": item.due_date.isoformat(),
        })

    # ── 2. Upcoming deadlines (within 7 days) ────────────────────────────────
    upcoming_items = (
        db.query(ActionItem)
        .filter(
            ActionItem.client_id.in_(client_ids),
            ActionItem.status == "pending",
            ActionItem.due_date >= today,
            ActionItem.due_date <= seven_days,
            ActionItem.due_date.isnot(None),
        )
        .order_by(ActionItem.due_date.asc())
        .all()
    )
    for item in upcoming_items:
        if ("upcoming_deadline", item.id) in dismissed:
            continue
        days_until = (item.due_date - today).days
        time_label = "today" if days_until == 0 else (
            "tomorrow" if days_until == 1 else f"in {days_until} days"
        )
        alerts.append({
            "id": str(item.id),
            "type": "upcoming_deadline",
            "severity": "warning",
            "client_id": str(item.client_id),
            "client_name": client_names.get(item.client_id, "Unknown"),
            "message": f"Deadline {time_label}: {item.text[:100]}",
            "related_id": str(item.id),
            "created_at": item.due_date.isoformat(),
        })

    # ── 3. Stale clients ─────────────────────────────────────────────────────
    # Bulk query: document counts per client
    doc_counts_rows = (
        db.query(Document.client_id, func.count(Document.id))
        .filter(Document.client_id.in_(client_ids))
        .group_by(Document.client_id)
        .all()
    )
    doc_counts = {row[0]: row[1] for row in doc_counts_rows}

    # Bulk query: recent chat message counts per client
    chat_counts_rows = (
        db.query(ChatMessage.client_id, func.count(ChatMessage.id))
        .filter(
            ChatMessage.client_id.in_(client_ids),
            ChatMessage.created_at >= thirty_days_ago,
        )
        .group_by(ChatMessage.client_id)
        .all()
    )
    chat_counts = {row[0]: row[1] for row in chat_counts_rows}

    for cid in client_ids:
        if ("stale_client", cid) in dismissed:
            continue

        if doc_counts.get(cid, 0) == 0 and chat_counts.get(cid, 0) == 0:
            alerts.append({
                "id": str(cid),
                "type": "stale_client",
                "severity": "info",
                "client_id": str(cid),
                "client_name": client_names.get(cid, "Unknown"),
                "message": f"{client_names.get(cid, 'Client')} has no documents and no recent activity",
                "related_id": str(cid),
                "created_at": datetime.now(timezone.utc).date().isoformat(),
            })

    # ── 4. Stuck documents (unprocessed) ─────────────────────────────────────
    stuck_docs = (
        db.query(Document)
        .filter(
            Document.client_id.in_(client_ids),
            Document.processed == False,  # noqa: E712
        )
        .all()
    )
    for doc in stuck_docs:
        if ("stuck_document", doc.id) in dismissed:
            continue
        alerts.append({
            "id": str(doc.id),
            "type": "stuck_document",
            "severity": "warning",
            "client_id": str(doc.client_id),
            "client_name": client_names.get(doc.client_id, "Unknown"),
            "message": f"Document \"{doc.filename}\" has not been processed"
                + (f" — {doc.processing_error[:80]}" if doc.processing_error else ""),
            "related_id": str(doc.id),
            "created_at": doc.upload_date.isoformat() if doc.upload_date else datetime.now(timezone.utc).isoformat(),
        })

    # ── 5a. Preparer determination needed ────────────────────────────────
    determination_needed_clients = (
        db.query(Client)
        .filter(
            Client.owner_id == owner_id,
            Client.has_tax_documents == True,  # noqa: E712
            Client.consent_status == "determination_needed",
        )
        .all()
    )
    for c in determination_needed_clients:
        if ("preparer_determination_needed", c.id) in dismissed:
            continue
        alerts.append({
            "id": str(c.id),
            "type": "preparer_determination_needed",
            "severity": "info",
            "client_id": str(c.id),
            "client_name": c.name,
            "message": (
                f"Tax documents uploaded for {c.name} "
                f"\u2014 please confirm your preparer relationship to determine compliance requirements"
            ),
            "related_id": str(c.id),
            "created_at": datetime.now(timezone.utc).date().isoformat(),
        })

    # ── 5b. Consent needed (preparer confirmed, full 7216 required) ───
    consent_needed_clients = (
        db.query(Client)
        .filter(
            Client.owner_id == owner_id,
            Client.has_tax_documents == True,  # noqa: E712
            Client.consent_status == "pending",
        )
        .all()
    )
    for c in consent_needed_clients:
        if ("consent_needed", c.id) in dismissed:
            continue
        alerts.append({
            "id": str(c.id),
            "type": "consent_needed",
            "severity": "warning",
            "client_id": str(c.id),
            "client_name": c.name,
            "message": (
                f"Section 7216 consent needed for {c.name} "
                f"\u2014 tax documents uploaded without recorded consent"
            ),
            "related_id": str(c.id),
            "created_at": datetime.now(timezone.utc).date().isoformat(),
        })

    # ── 6. Consent expiring (within 30 days) ──────────────────────────────
    from app.services.consent_service import get_expiring_consents

    expiring = get_expiring_consents(clerk_user_id, db, days_ahead=30)
    for item in expiring:
        cid = item["client_id"]
        if ("consent_expiring", cid) in dismissed:
            continue
        days_left = item["days_until_expiry"]
        alerts.append({
            "id": str(item["consent_id"]),
            "type": "consent_expiring",
            "severity": "info",
            "client_id": str(cid),
            "client_name": item["client_name"],
            "message": (
                f"Section 7216 consent for {item['client_name']} "
                f"expires in {days_left} day{'s' if days_left != 1 else ''}"
            ),
            "related_id": str(cid),
            "created_at": datetime.now(timezone.utc).date().isoformat(),
        })

    # Sort: critical first, then warning, then info; within same severity by date
    alerts.sort(key=lambda a: (SEVERITY_ORDER.get(a["severity"], 99), a["created_at"]))

    return alerts


def compute_summary(
    db: Session,
    owner_id: UUID,
    clerk_user_id: str,
) -> dict[str, int]:
    """Return alert counts by severity."""
    alerts = compute_alerts(db, owner_id, clerk_user_id)
    summary = {"critical": 0, "warning": 0, "info": 0, "total": 0}
    for a in alerts:
        sev = a["severity"]
        if sev in summary:
            summary[sev] += 1
        summary["total"] += 1
    return summary

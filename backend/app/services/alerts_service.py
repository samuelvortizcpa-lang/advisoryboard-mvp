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
- quarterly_estimate_due:        quarterly estimate prep task with upcoming deadline
- follow_up_due:                 follow-up reminder whose remind_at has passed
- session_follow_up:             chat session with decisions mentioning follow-up keywords
- contradiction:                 open data contradiction with high or medium severity
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.action_item import ActionItem
from app.models.chat_message import ChatMessage
from app.models.client import Client
from app.models.client_consent import ClientConsent
from app.models.client_communication import ClientCommunication
from app.models.dismissed_alert import DismissedAlert
from app.models.document import Document
from app.models.follow_up_reminder import FollowUpReminder

logger = logging.getLogger(__name__)

SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}

# ---------------------------------------------------------------------------
# TTL cache — prevents repeated computation on rapid-fire requests
# ---------------------------------------------------------------------------
_CACHE_TTL = 60  # seconds
_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}


def _cache_key(org_id: UUID, clerk_user_id: str) -> str:
    return f"{org_id}:{clerk_user_id}"


def invalidate_alerts_cache(org_id: UUID, clerk_user_id: str) -> None:
    """Drop cached alerts for a user after a dismiss or data change."""
    _cache.pop(_cache_key(org_id, clerk_user_id), None)


def compute_alerts(
    db: Session,
    org_id: UUID,
    clerk_user_id: str,
) -> list[dict[str, Any]]:
    """
    Compute all alerts for clients in the user's active org, filtering out dismissed ones.

    Uses batch queries (constant query count regardless of client count) and a
    60-second TTL cache to avoid redundant computation.

    Returns a list of alert dicts sorted by severity (critical first), then date.
    """
    key = _cache_key(org_id, clerk_user_id)
    cached = _cache.get(key)
    if cached is not None:
        ts, data = cached
        if time.monotonic() - ts < _CACHE_TTL:
            return data

    result = _compute_alerts_uncached(db, org_id, clerk_user_id)
    _cache[key] = (time.monotonic(), result)
    return result


def _compute_alerts_uncached(
    db: Session,
    org_id: UUID,
    clerk_user_id: str,
) -> list[dict[str, Any]]:
    """Core alert computation — all batch queries, no per-client loops."""

    today = date.today()
    seven_days = today + timedelta(days=7)
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)

    # ── Q1: All clients in this org ───────────────────────────────────────
    client_rows = (
        db.query(Client.id, Client.name)
        .filter(Client.org_id == org_id)
        .all()
    )
    if not client_rows:
        return []

    client_ids = [r.id for r in client_rows]
    client_names = {r.id: r.name for r in client_rows}

    # ── Q2: Dismissed alerts for this user ────────────────────────────────
    dismissed = set()
    dismissed_rows = (
        db.query(DismissedAlert.alert_type, DismissedAlert.related_id)
        .filter(DismissedAlert.user_id == clerk_user_id)
        .limit(500)
        .all()
    )
    for d in dismissed_rows:
        dismissed.add((d.alert_type, d.related_id))

    alerts: list[dict[str, Any]] = []

    # ── Q3: Pending action items with due dates (overdue + upcoming) ──────
    # Single query fetches both overdue and upcoming-within-7-days
    pending_items = (
        db.query(ActionItem)
        .filter(
            ActionItem.client_id.in_(client_ids),
            ActionItem.status == "pending",
            ActionItem.due_date.isnot(None),
            ActionItem.due_date <= seven_days,
        )
        .order_by(ActionItem.due_date.asc())
        .all()
    )
    for item in pending_items:
        if item.due_date < today:
            # Overdue
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
        else:
            # Upcoming
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

    # ── Q4+Q5: Stale clients (no docs AND no recent chat) ────────────────
    doc_counts_rows = (
        db.query(Document.client_id, func.count(Document.id))
        .filter(Document.client_id.in_(client_ids))
        .group_by(Document.client_id)
        .all()
    )
    doc_counts = {row[0]: row[1] for row in doc_counts_rows}

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

    # ── Q6: Stuck documents (unprocessed) ─────────────────────────────────
    stuck_docs = (
        db.query(Document)
        .filter(
            Document.client_id.in_(client_ids),
            Document.processed == False,  # noqa: E712
        )
        .limit(100)
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

    # ── Q7: Consent status alerts (determination + pending in one query) ──
    consent_alert_clients = (
        db.query(Client)
        .filter(
            Client.org_id == org_id,
            Client.has_tax_documents == True,  # noqa: E712
            or_(
                Client.consent_status == "determination_needed",
                Client.consent_status == "pending",
            ),
        )
        .limit(100)
        .all()
    )
    for c in consent_alert_clients:
        if c.consent_status == "determination_needed":
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
        else:
            # consent_status == "pending"
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

    # ── Q8: Consent expiring (within 30 days) ────────────────────────────
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

    # ── Q9.5: Quarterly estimate due — engagement tasks with workflow_type ─
    import re
    from app.models.engagement_template_task import EngagementTemplateTask

    # IRS quarterly estimate due dates — (month, day)
    _QE_DUE = {1: (4, 15), 2: (6, 15), 3: (9, 15), 4: (1, 15)}

    thirty_days_ahead = today + timedelta(days=30)
    qe_items = (
        db.query(ActionItem)
        .join(EngagementTemplateTask, ActionItem.engagement_task_id == EngagementTemplateTask.id)
        .filter(
            ActionItem.client_id.in_(client_ids),
            ActionItem.status == "pending",
            EngagementTemplateTask.workflow_type == "quarterly_estimate",
            ActionItem.due_date.isnot(None),
            ActionItem.due_date <= thirty_days_ahead,
        )
        .all()
    )
    for item in qe_items:
        if ("quarterly_estimate_due", item.id) in dismissed:
            continue
        # Extract quarter from task text (e.g. "Q1 estimated tax prep (2026)")
        m = re.search(r"Q(\d)", item.text)
        quarter = int(m.group(1)) if m else None
        # Extract year from text
        yr_match = re.search(r"\((\d{4})\)", item.text)
        tax_year = int(yr_match.group(1)) if yr_match else today.year
        if quarter:
            due_month, due_day = _QE_DUE.get(quarter, (4, 15))
            due_year = tax_year + 1 if quarter == 4 else tax_year
            try:
                payment_due = date(due_year, due_month, due_day)
                due_str = payment_due.strftime("%B %d, %Y")
            except ValueError:
                due_str = "upcoming"
        else:
            due_str = "upcoming"

        cname = client_names.get(item.client_id, "Unknown")
        q_label = f"Q{quarter} {tax_year}" if quarter else "Quarterly"
        alerts.append({
            "id": str(item.id),
            "type": "quarterly_estimate_due",
            "severity": "warning",
            "client_id": str(item.client_id),
            "client_name": cname,
            "message": f"{q_label} estimated tax payment due {due_str} for {cname}. Draft estimate email?",
            "related_id": str(item.id),
            "created_at": item.due_date.isoformat() if item.due_date else today.isoformat(),
        })

    # ── Q10: Follow-up reminders that are due ──────────────────────────────
    now = datetime.now(timezone.utc)
    due_reminders = (
        db.query(FollowUpReminder)
        .filter(
            FollowUpReminder.client_id.in_(client_ids),
            FollowUpReminder.user_id == clerk_user_id,
            FollowUpReminder.status == "pending",
            FollowUpReminder.remind_at <= now,
        )
        .limit(100)
        .all()
    )
    for reminder in due_reminders:
        if ("follow_up_due", reminder.communication_id) in dismissed:
            continue

        # Fetch the communication for subject and sent_at
        comm = (
            db.query(ClientCommunication)
            .filter(ClientCommunication.id == reminder.communication_id)
            .first()
        )
        if not comm:
            continue

        # Mark as triggered
        reminder.status = "triggered"
        reminder.triggered_at = now

        cname = client_names.get(reminder.client_id, "Unknown")
        sent_date = comm.sent_at.strftime("%b %d") if comm.sent_at else "unknown date"
        subject_preview = (comm.subject or "")[:80]

        alerts.append({
            "id": str(reminder.id),
            "type": "follow_up_due",
            "severity": "warning",
            "client_id": str(reminder.client_id),
            "client_name": cname,
            "message": (
                f"Follow-up due: You emailed {cname} about "
                f"\"{subject_preview}\" on {sent_date} with no response"
            ),
            "related_id": str(reminder.communication_id),
            "created_at": reminder.remind_at.isoformat(),
        })

    if due_reminders:
        db.commit()

    # ── Q11: Session follow-up suggestions ────────────────────────────
    from app.models.chat_session import ChatSession

    _FOLLOW_UP_KW = [
        "follow up", "follow-up", "followup", "revisit", "next time",
        "come back to", "check on", "circle back", "touch base",
    ]

    # Sessions closed in the last 14 days that have key_decisions
    fourteen_days_ago = datetime.now(timezone.utc) - timedelta(days=14)
    recent_sessions = (
        db.query(ChatSession)
        .filter(
            ChatSession.client_id.in_(client_ids),
            ChatSession.is_active.is_(False),
            ChatSession.ended_at >= fourteen_days_ago,
            ChatSession.key_decisions.isnot(None),
        )
        .limit(100)
        .all()
    )
    for sess in recent_sessions:
        if ("session_follow_up", sess.id) in dismissed:
            continue
        if not sess.key_decisions:
            continue
        # Check if any decision mentions follow-up keywords
        matching = [
            d for d in sess.key_decisions
            if any(kw in d.lower() for kw in _FOLLOW_UP_KW)
        ]
        if not matching:
            continue
        cname = client_names.get(sess.client_id, "Unknown")
        decision_preview = matching[0][:100]
        alerts.append({
            "id": str(sess.id),
            "type": "session_follow_up",
            "severity": "info",
            "client_id": str(sess.client_id),
            "client_name": cname,
            "message": f"Session follow-up suggested for {cname}: \"{decision_preview}\"",
            "related_id": str(sess.id),
            "created_at": (sess.ended_at or sess.started_at).isoformat(),
        })

    # ── Q12: Open data contradictions (high / medium) ───────────────
    from app.models.data_contradiction import DataContradiction

    open_contradictions = (
        db.query(DataContradiction)
        .filter(
            DataContradiction.client_id.in_(client_ids),
            DataContradiction.status == "open",
            DataContradiction.severity.in_(["high", "medium"]),
        )
        .order_by(DataContradiction.created_at.desc())
        .limit(50)
        .all()
    )
    for c in open_contradictions:
        if ("contradiction", c.id) in dismissed:
            continue
        cname = client_names.get(c.client_id, "Unknown")
        severity = "warning" if c.severity == "high" else "info"
        alerts.append({
            "id": str(c.id),
            "type": "contradiction",
            "severity": severity,
            "client_id": str(c.client_id),
            "client_name": cname,
            "message": f"Data contradiction for {cname}: {c.title}",
            "related_id": str(c.id),
            "created_at": c.created_at.isoformat(),
        })

    # ── Q13: Check-in completed in last 24 hours ─────────────────────
    from app.models.checkin_response import CheckinResponse
    from app.models.checkin_template import CheckinTemplate

    twenty_four_hours_ago = datetime.now(timezone.utc) - timedelta(hours=24)
    completed_checkins = (
        db.query(CheckinResponse, CheckinTemplate.name)
        .join(CheckinTemplate, CheckinResponse.template_id == CheckinTemplate.id)
        .filter(
            CheckinResponse.client_id.in_(client_ids),
            CheckinResponse.status == "completed",
            CheckinResponse.completed_at >= twenty_four_hours_ago,
        )
        .all()
    )
    for ci, template_name in completed_checkins:
        if ("checkin_completed", ci.id) in dismissed:
            continue
        cname = client_names.get(ci.client_id, "Unknown")
        respondent = ci.sent_to_name or "Client"
        alerts.append({
            "id": str(ci.id),
            "type": "checkin_completed",
            "severity": "info",
            "client_id": str(ci.client_id),
            "client_name": cname,
            "message": f"{respondent} completed their {template_name} check-in",
            "related_id": str(ci.id),
            "created_at": ci.completed_at.isoformat() if ci.completed_at else now.isoformat(),
        })

    # ── Q14: Check-in expiring within 48 hours ─────────────────────
    forty_eight_hours = datetime.now(timezone.utc) + timedelta(hours=48)
    expiring_checkins = (
        db.query(CheckinResponse, CheckinTemplate.name, Client.name)
        .join(CheckinTemplate, CheckinResponse.template_id == CheckinTemplate.id)
        .join(Client, CheckinResponse.client_id == Client.id)
        .filter(
            CheckinResponse.client_id.in_(client_ids),
            CheckinResponse.status == "pending",
            CheckinResponse.expires_at >= now,
            CheckinResponse.expires_at <= forty_eight_hours,
        )
        .all()
    )
    for ci, template_name, ci_client_name in expiring_checkins:
        if ("checkin_expiring", ci.id) in dismissed:
            continue
        hours_left = int((ci.expires_at.replace(tzinfo=timezone.utc) - now).total_seconds() / 3600)
        if hours_left < 0:
            hours_left = 0
        alerts.append({
            "id": str(ci.id),
            "type": "checkin_expiring",
            "severity": "warning",
            "client_id": str(ci.client_id),
            "client_name": ci_client_name or "Unknown",
            "message": f"Check-in for {ci_client_name or 'client'} expires in {hours_left} hours",
            "related_id": str(ci.id),
            "created_at": ci.expires_at.isoformat(),
        })

    # Sort: critical first, then warning, then info; within same severity by date
    alerts.sort(key=lambda a: (SEVERITY_ORDER.get(a["severity"], 99), a["created_at"]))

    return alerts


def compute_summary(
    db: Session,
    org_id: UUID,
    clerk_user_id: str,
) -> dict[str, int]:
    """Return alert counts by severity."""
    alerts = compute_alerts(db, org_id, clerk_user_id)
    summary = {"critical": 0, "warning": 0, "info": 0, "total": 0}
    for a in alerts:
        sev = a["severity"]
        if sev in summary:
            summary[sev] += 1
        summary["total"] += 1
    return summary

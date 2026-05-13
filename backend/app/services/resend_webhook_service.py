"""Resend webhook event handler — delivery, bounce, complaint tracking."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.client_communication import ClientCommunication
from app.models.journal_entry import JournalEntry

logger = logging.getLogger(__name__)


def handle_event(
    db: Session,
    event_type: str,
    event_data: dict,
    event_id: str,
) -> None:
    """Dispatch a Resend webhook event to the appropriate handler."""
    resend_message_id = event_data.get("email_id") or event_data.get("id")
    if not resend_message_id:
        logger.warning("Resend webhook missing email_id: %s", event_type)
        return

    comm = (
        db.query(ClientCommunication)
        .filter(ClientCommunication.resend_message_id == resend_message_id)
        .first()
    )
    if comm is None:
        logger.info(
            "No ClientCommunication found for resend_message_id=%s", resend_message_id
        )
        return

    # Idempotency: check if this event_id was already processed
    existing_events = (comm.metadata_ or {}).get("webhook_events", [])
    if any(e.get("event_id") == event_id for e in existing_events):
        logger.info("Skipping duplicate webhook event %s", event_id)
        return

    now = datetime.now(timezone.utc)

    if event_type == "email.delivered":
        _handle_delivered(db, comm, event_data, event_id, now)
    elif event_type == "email.bounced":
        _handle_bounced(db, comm, event_data, event_id, now)
    elif event_type == "email.complained":
        _handle_complained(db, comm, event_data, event_id, now)
    else:
        logger.info("Unhandled Resend event type: %s", event_type)
        return

    # Append event to metadata.webhook_events
    new_meta = dict(comm.metadata_ or {})
    events = list(new_meta.get("webhook_events", []))
    events.append({
        "event_id": event_id,
        "event_type": event_type,
        "processed_at": now.isoformat(),
    })
    new_meta["webhook_events"] = events
    comm.metadata_ = new_meta


def _handle_delivered(
    db: Session,
    comm: ClientCommunication,
    event_data: dict,
    event_id: str,
    now: datetime,
) -> None:
    comm.delivered_at = now
    # Q4: status remains unchanged; delivered_at is the disambiguator.


def _handle_bounced(
    db: Session,
    comm: ClientCommunication,
    event_data: dict,
    event_id: str,
    now: datetime,
) -> None:
    comm.bounced_at = now
    comm.status = "bounced"

    # Journal entry for bounce
    db.add(JournalEntry(
        client_id=comm.client_id,
        user_id=comm.user_id,
        entry_type="system",
        category="deliverable",
        title=f"Email bounced: {comm.subject}",
        content=f"Recipient: {comm.recipient_email}",
        source_type="system",
    ))


def _handle_complained(
    db: Session,
    comm: ClientCommunication,
    event_data: dict,
    event_id: str,
    now: datetime,
) -> None:
    # Q5: complaint is capture-only. The webhook_events[] append happens in
    # the dispatcher; nothing to do here beyond that.
    pass

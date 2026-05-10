"""
Engagement deliverable service — shell orchestrator.

Coordinates draft generation, sending, and history for cadence-driven
deliverables (kickoff_memo, progress_note, etc.) via the handler registry.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from openai import AsyncOpenAI
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.client import Client
from app.models.client_communication import ClientCommunication
from app.models.journal_entry import JournalEntry
from app.schemas.deliverables import (
    DeliverableDraftResponse,
    ReferencesPayload,
    StrategyReference,
    TaskReference,
)
from app.services.cadence_service import is_deliverable_enabled
from app.services.communication_service import (
    extract_open_items_from_email,
    get_or_create_thread,
)
from app.services.context_assembler import ContextPurpose, assemble_context
from app.services.deliverables import get_handler
from app.services.deliverables._base import ClientFacts, ContextBundle

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# draft_deliverable
# ---------------------------------------------------------------------------


async def draft_deliverable(
    db: Session,
    client_id: UUID,
    deliverable_key: str,
    tax_year: int,
    requested_by: str,
) -> DeliverableDraftResponse:
    """
    Generate an AI draft for the given deliverable type.

    Raises:
        ValueError: if deliverable_key has no registered handler.
        PermissionError: if the deliverable is cadence-disabled for this client.
    """
    handler = get_handler(deliverable_key)

    if not is_deliverable_enabled(db, client_id, deliverable_key):
        raise PermissionError(
            f"{deliverable_key} deliverable not enabled for client_id={client_id}"
        )

    # Fetch client
    client = db.query(Client).filter(Client.id == client_id).first()
    if client is None:
        raise ValueError(f"Client not found: {client_id}")

    # Assemble context
    raw_ctx = await assemble_context(
        db,
        client_id=client_id,
        user_id=requested_by,
        purpose=ContextPurpose(handler.context_purpose),
    )

    # Build ContextBundle from assembled context
    strategy_entries = []
    if raw_ctx.strategy_status and raw_ctx.strategy_status.get("years"):
        for _year, entries in raw_ctx.strategy_status["years"].items():
            strategy_entries.extend(entries)

    bundle = ContextBundle(
        strategies=strategy_entries,
        action_items=raw_ctx.action_items or [],
        journal=raw_ctx.journal_entries or [],
        financials=raw_ctx.financial_metrics or {},
        comms=raw_ctx.communication_history or [],
    )

    facts = ClientFacts(
        name=client.name,
        entity_type=client.entity_type,
        tax_year=tax_year,
    )

    # Build prompt
    prompt = handler.build_prompt(bundle, facts)

    # Call LLM
    settings = get_settings()
    openai_client = AsyncOpenAI(api_key=settings.openai_api_key)

    response = await openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=1500,
    )
    ai_body = response.choices[0].message.content.strip()

    # Subject (pre-filled per handler prompt)
    subject = f"Engagement kickoff — {client.name} — {tax_year}"

    # Extract references
    references_dict = handler.extract_references(bundle, facts)

    # Build typed references (filter out entries with empty IDs)
    strategies_ref = [
        StrategyReference(id=s["id"], name=s["name"])
        for s in references_dict.get("strategies", [])
        if s.get("id")
    ]
    tasks_ref = [
        TaskReference(
            id=t["id"],
            name=t["name"],
            owner_role=t["owner_role"],
            due_date=t.get("due_date"),
            strategy_name=t.get("strategy_name", ""),
        )
        for t in references_dict.get("tasks", [])
        if t.get("id")
    ]

    references = ReferencesPayload(strategies=strategies_ref, tasks=tasks_ref)

    # Warnings
    warnings: list[str] = []
    if not strategies_ref:
        warnings.append("No recommended strategies found")

    # Journal entry
    db.add(JournalEntry(
        client_id=client_id,
        user_id=requested_by,
        entry_type="system",
        category="deliverable",
        title=f"Drafted {deliverable_key} for {client.name}",
        source_type="system",
    ))
    db.commit()

    return DeliverableDraftResponse(
        subject=subject,
        body=ai_body,
        references=references,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# record_deliverable_sent
# ---------------------------------------------------------------------------


def record_deliverable_sent(
    db: Session,
    client_id: UUID,
    deliverable_key: str,
    tax_year: int,
    subject: str,
    body: str,
    sent_by: str,
    recipient_email: str,
    gmail_message_id: Optional[str] = None,
) -> ClientCommunication:
    """
    Record that a deliverable email was sent. Creates a ClientCommunication row
    with threading, runs open-items extraction, and writes a journal entry.

    Idempotent: if gmail_message_id is provided and already recorded, returns
    the existing row without side effects.

    Raises:
        ValueError: if deliverable_key has no registered handler.
        PermissionError: if the deliverable is cadence-disabled for this client.
    """
    handler = get_handler(deliverable_key)

    if not is_deliverable_enabled(db, client_id, deliverable_key):
        raise PermissionError(
            f"{deliverable_key} deliverable not enabled for client_id={client_id}"
        )

    # Idempotency check (Python-side for SQLite portability)
    if gmail_message_id:
        existing = (
            db.query(ClientCommunication)
            .filter(
                ClientCommunication.client_id == client_id,
                ClientCommunication.thread_type == handler.thread_type,
                ClientCommunication.thread_year == tax_year,
            )
            .all()
        )
        for row in existing:
            meta = row.metadata_ or {}
            if meta.get("gmail_message_id") == gmail_message_id:
                return row

    # Thread
    thread_id = get_or_create_thread(
        db,
        client_id=client_id,
        thread_type=handler.thread_type,
        thread_year=tax_year,
        thread_quarter=None,
    )

    # Fetch client name for journal
    client = db.query(Client).filter(Client.id == client_id).first()
    client_name = client.name if client else "Unknown"

    # Build metadata
    metadata: dict = {}
    if gmail_message_id:
        metadata["gmail_message_id"] = gmail_message_id

    # Create communication row
    comm = ClientCommunication(
        client_id=client_id,
        user_id=sent_by,
        communication_type="email",
        subject=subject,
        body_html=body,
        body_text=body,
        recipient_email=recipient_email,
        thread_id=thread_id,
        thread_type=handler.thread_type,
        thread_year=tax_year,
        thread_quarter=None,
        open_items=[],
        metadata_=metadata or None,
    )
    db.add(comm)
    db.flush()

    # Extract open items
    if handler.extract_open_items is not None:
        items = handler.extract_open_items(body, comm.id, comm.created_at)
        comm.open_items = [item.model_dump(mode="json") for item in items]

    # Journal entry
    db.add(JournalEntry(
        client_id=client_id,
        user_id=sent_by,
        entry_type="system",
        category="deliverable",
        title=f"Sent {deliverable_key} to {client_name}",
        source_type="system",
    ))
    db.commit()

    return comm


# ---------------------------------------------------------------------------
# list_deliverable_history
# ---------------------------------------------------------------------------


def list_deliverable_history(
    db: Session,
    client_id: UUID,
    deliverable_key: str,
    tax_year: Optional[int] = None,
) -> list[ClientCommunication]:
    """
    List all communications for a given deliverable type and client.
    Optionally filter by tax_year.
    """
    handler = get_handler(deliverable_key)

    q = db.query(ClientCommunication).filter(
        ClientCommunication.client_id == client_id,
        ClientCommunication.thread_type == handler.thread_type,
    )
    if tax_year is not None:
        q = q.filter(ClientCommunication.thread_year == tax_year)

    return q.order_by(ClientCommunication.created_at.desc()).all()

"""Client journal service — CRUD for journal entries and profile flag history."""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.journal_entry import JournalEntry
from app.models.profile_flag_history import ProfileFlagHistory
from app.schemas.journal import (
    JournalEntryCreate,
    JournalEntryResponse,
    JournalEntryUpdate,
    JournalFeedResponse,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. Create manual entry
# ---------------------------------------------------------------------------

def create_entry(
    db: Session,
    client_id: UUID,
    user_id: str,
    entry_data: JournalEntryCreate,
) -> JournalEntry:
    entry = JournalEntry(
        client_id=client_id,
        user_id=user_id,
        entry_type=entry_data.entry_type,
        category=entry_data.category,
        title=entry_data.title,
        content=entry_data.content,
        effective_date=entry_data.effective_date,
        source_type=entry_data.source_type or "manual",
        source_id=entry_data.source_id,
        metadata_=entry_data.metadata,
        is_pinned=entry_data.is_pinned,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


# ---------------------------------------------------------------------------
# 2. Create auto/system entry (called by other services)
# ---------------------------------------------------------------------------

def create_auto_entry(
    db: Session,
    client_id: UUID,
    user_id: str,
    entry_type: str,
    category: str | None,
    title: str,
    content: str | None = None,
    source_type: str | None = None,
    source_id: UUID | None = None,
    metadata: dict[str, Any] | None = None,
    effective_date: date | None = None,
) -> JournalEntry:
    entry = JournalEntry(
        client_id=client_id,
        user_id=user_id,
        entry_type=entry_type,
        category=category,
        title=title,
        content=content,
        effective_date=effective_date,
        source_type=source_type or "system",
        source_id=source_id,
        metadata_=metadata,
        is_pinned=False,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


# ---------------------------------------------------------------------------
# 3. Get paginated, filtered, searchable feed
# ---------------------------------------------------------------------------

def get_entries(
    db: Session,
    client_id: UUID,
    entry_type: str | None = None,
    category: str | None = None,
    pinned_only: bool = False,
    page: int = 1,
    per_page: int = 20,
    search: str | None = None,
) -> JournalFeedResponse:
    q = db.query(JournalEntry).filter(JournalEntry.client_id == client_id)

    if entry_type:
        q = q.filter(JournalEntry.entry_type == entry_type)
    if category:
        q = q.filter(JournalEntry.category == category)
    if pinned_only:
        q = q.filter(JournalEntry.is_pinned == True)  # noqa: E712
    if search:
        pattern = f"%{search}%"
        q = q.filter(
            JournalEntry.title.ilike(pattern)
            | JournalEntry.content.ilike(pattern)
        )

    total = q.count()

    # Pinned entries first, then by created_at descending
    rows = (
        q.order_by(
            JournalEntry.is_pinned.desc(),
            JournalEntry.created_at.desc(),
        )
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    return JournalFeedResponse(
        entries=[JournalEntryResponse.model_validate(r) for r in rows],
        total=total,
    )


# ---------------------------------------------------------------------------
# 4. Update manual entry
# ---------------------------------------------------------------------------

def update_entry(
    db: Session,
    entry_id: UUID,
    user_id: str,
    update_data: JournalEntryUpdate,
) -> JournalEntry:
    entry = db.query(JournalEntry).filter(JournalEntry.id == entry_id).first()
    if entry is None:
        raise ValueError("Journal entry not found")
    if entry.entry_type != "manual":
        raise ValueError("Only manual entries can be edited")

    updates = update_data.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(entry, key, value)

    entry.updated_at = func.now()
    db.commit()
    db.refresh(entry)
    return entry


# ---------------------------------------------------------------------------
# 5. Toggle pin
# ---------------------------------------------------------------------------

def toggle_pin(db: Session, entry_id: UUID, user_id: str) -> JournalEntry:
    entry = db.query(JournalEntry).filter(JournalEntry.id == entry_id).first()
    if entry is None:
        raise ValueError("Journal entry not found")

    entry.is_pinned = not entry.is_pinned
    entry.updated_at = func.now()
    db.commit()
    db.refresh(entry)
    return entry


# ---------------------------------------------------------------------------
# 6. Delete manual entry
# ---------------------------------------------------------------------------

def delete_entry(db: Session, entry_id: UUID, user_id: str) -> bool:
    entry = db.query(JournalEntry).filter(JournalEntry.id == entry_id).first()
    if entry is None:
        raise ValueError("Journal entry not found")
    if entry.entry_type != "manual":
        raise ValueError("Only manual entries can be deleted")

    db.delete(entry)
    db.commit()
    return True


# ---------------------------------------------------------------------------
# 7. Profile flag change logging
# ---------------------------------------------------------------------------

def log_profile_flag_change(
    db: Session,
    client_id: UUID,
    flag_name: str,
    old_value: bool | None,
    new_value: bool | None,
    changed_by: str,
    source: str = "manual",
) -> None:
    # Record in history table
    record = ProfileFlagHistory(
        client_id=client_id,
        flag_name=flag_name,
        old_value=old_value,
        new_value=new_value,
        changed_by=changed_by,
        source=source,
    )
    db.add(record)

    # Create a journal entry for the change
    label = flag_name.replace("_", " ").replace("has ", "")
    action = "enabled" if new_value else "disabled"
    create_auto_entry(
        db=db,
        client_id=client_id,
        user_id=changed_by,
        entry_type="system",
        category="compliance",
        title=f"Profile flag updated: {label} {action}",
        content=f"{flag_name} changed from {old_value} to {new_value}",
        source_type="system",
        metadata={"flag_name": flag_name, "old_value": old_value, "new_value": new_value},
    )

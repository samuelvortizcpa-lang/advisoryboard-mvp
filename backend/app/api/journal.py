"""Client journal API — chronological feed of client events and notes."""

from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.profile_flag_history import ProfileFlagHistory
from app.schemas.journal import (
    JournalEntryCreate,
    JournalEntryResponse,
    JournalEntryUpdate,
    JournalFeedResponse,
    ProfileFlagChange,
)
from app.services import journal_service
from app.services.auth_context import AuthContext, check_client_access, get_auth

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# GET /clients/{client_id}/journal
# ---------------------------------------------------------------------------

@router.get(
    "/clients/{client_id}/journal",
    response_model=JournalFeedResponse,
    summary="Get client journal feed",
)
async def get_journal(
    client_id: UUID,
    entry_type: Optional[str] = Query(None, description="Filter by entry type"),
    category: Optional[str] = Query(None, description="Filter by category"),
    pinned_only: bool = Query(False, description="Only return pinned entries"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None, description="Search title and content"),
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> JournalFeedResponse:
    check_client_access(auth, client_id, db)
    return journal_service.get_entries(
        db,
        client_id=client_id,
        entry_type=entry_type,
        category=category,
        pinned_only=pinned_only,
        page=page,
        per_page=per_page,
        search=search,
    )


# ---------------------------------------------------------------------------
# POST /clients/{client_id}/journal
# ---------------------------------------------------------------------------

@router.post(
    "/clients/{client_id}/journal",
    response_model=JournalEntryResponse,
    status_code=201,
    summary="Create a manual journal entry",
)
async def create_journal_entry(
    client_id: UUID,
    body: JournalEntryCreate,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> JournalEntryResponse:
    check_client_access(auth, client_id, db)
    entry = journal_service.create_entry(db, client_id, auth.user_id, body)
    return JournalEntryResponse.model_validate(entry)


# ---------------------------------------------------------------------------
# PATCH /journal/{entry_id}
# ---------------------------------------------------------------------------

@router.patch(
    "/journal/{entry_id}",
    response_model=JournalEntryResponse,
    summary="Update a manual journal entry",
)
async def update_journal_entry(
    entry_id: UUID,
    body: JournalEntryUpdate,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> JournalEntryResponse:
    try:
        entry = journal_service.update_entry(db, entry_id, auth.user_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return JournalEntryResponse.model_validate(entry)


# ---------------------------------------------------------------------------
# DELETE /journal/{entry_id}
# ---------------------------------------------------------------------------

@router.delete(
    "/journal/{entry_id}",
    status_code=204,
    summary="Delete a manual journal entry",
)
async def delete_journal_entry(
    entry_id: UUID,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
):
    try:
        journal_service.delete_entry(db, entry_id, auth.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ---------------------------------------------------------------------------
# PATCH /journal/{entry_id}/pin
# ---------------------------------------------------------------------------

@router.patch(
    "/journal/{entry_id}/pin",
    response_model=JournalEntryResponse,
    summary="Toggle pin status on a journal entry",
)
async def toggle_pin(
    entry_id: UUID,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> JournalEntryResponse:
    try:
        entry = journal_service.toggle_pin(db, entry_id, auth.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return JournalEntryResponse.model_validate(entry)


# ---------------------------------------------------------------------------
# GET /clients/{client_id}/profile-flag-history
# ---------------------------------------------------------------------------

@router.get(
    "/clients/{client_id}/profile-flag-history",
    response_model=list[ProfileFlagChange],
    summary="Get profile flag change history",
)
async def get_flag_history(
    client_id: UUID,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> list[ProfileFlagChange]:
    check_client_access(auth, client_id, db)
    rows = (
        db.query(ProfileFlagHistory)
        .filter(ProfileFlagHistory.client_id == client_id)
        .order_by(ProfileFlagHistory.changed_at.desc())
        .all()
    )
    return [ProfileFlagChange.model_validate(r) for r in rows]

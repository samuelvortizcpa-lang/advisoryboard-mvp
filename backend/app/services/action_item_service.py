"""
Action item CRUD service.

Mirrors the pattern of document_service.py — pure DB operations,
no business logic or HTTP concerns.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Tuple
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.models.action_item import ActionItem
from app.models.client import Client
from app.schemas.action_item import ActionItemListResponse, ActionItemResponse


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _verify_client_ownership(
    db: Session, client_id: UUID, owner_id: UUID
) -> Client:
    client = (
        db.query(Client)
        .filter(Client.id == client_id, Client.owner_id == owner_id)
        .first()
    )
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Client not found"
        )
    return client


def _to_response(item: ActionItem) -> ActionItemResponse:
    """Build an ActionItemResponse, eagerly pulling the document filename."""
    return ActionItemResponse(
        id=item.id,
        document_id=item.document_id,
        client_id=item.client_id,
        text=item.text,
        status=item.status,
        priority=item.priority,
        due_date=item.due_date,
        extracted_at=item.extracted_at,
        completed_at=item.completed_at,
        created_at=item.created_at,
        updated_at=item.updated_at,
        document_filename=item.document.filename if item.document else None,
    )


# ---------------------------------------------------------------------------
# Public service functions
# ---------------------------------------------------------------------------


def get_action_items(
    db: Session,
    client_id: UUID,
    owner_id: UUID,
    status_filter: Optional[str] = None,   # 'pending' | 'completed' | 'cancelled' | None
    skip: int = 0,
    limit: int = 50,
) -> Tuple[list[ActionItemResponse], int]:
    """Return paginated action items for a client (ownership-scoped)."""
    _verify_client_ownership(db, client_id, owner_id)

    base = (
        db.query(ActionItem)
        .filter(ActionItem.client_id == client_id)
    )
    if status_filter and status_filter != "all":
        base = base.filter(ActionItem.status == status_filter)

    total = base.count()

    items = (
        base
        .options(joinedload(ActionItem.document))
        .order_by(ActionItem.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [_to_response(i) for i in items], total


def get_action_item_by_id(
    db: Session,
    item_id: UUID,
    owner_id: UUID,
) -> Optional[ActionItem]:
    """Fetch a single action item, verifying the client is owned by owner_id."""
    return (
        db.query(ActionItem)
        .join(Client, ActionItem.client_id == Client.id)
        .options(joinedload(ActionItem.document))
        .filter(ActionItem.id == item_id, Client.owner_id == owner_id)
        .first()
    )


def update_action_item(
    db: Session,
    item_id: UUID,
    owner_id: UUID,
    updates: dict,
) -> ActionItemResponse:
    """
    Apply *updates* (only provided keys) to an action item.

    Setting status → 'completed' records completed_at.
    Setting status → anything else clears completed_at.
    """
    item = get_action_item_by_id(db, item_id, owner_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Action item not found"
        )

    if "status" in updates:
        new_status = updates["status"]
        if new_status not in ("pending", "completed", "cancelled"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="status must be 'pending', 'completed', or 'cancelled'",
            )
        if new_status == "completed" and item.status != "completed":
            item.completed_at = datetime.utcnow()
        elif new_status != "completed":
            item.completed_at = None
        item.status = new_status

    if "priority" in updates:
        prio = updates["priority"]
        if prio is not None and prio not in ("low", "medium", "high"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="priority must be 'low', 'medium', 'high', or null",
            )
        item.priority = prio

    if "due_date" in updates:
        item.due_date = updates["due_date"]

    db.commit()
    db.refresh(item)
    return _to_response(item)


def delete_action_item(
    db: Session,
    item_id: UUID,
    owner_id: UUID,
) -> bool:
    """Delete an action item. Returns False if not found."""
    item = get_action_item_by_id(db, item_id, owner_id)
    if item is None:
        return False
    db.delete(item)
    db.commit()
    return True

"""
Action item CRUD service.

Mirrors the pattern of document_service.py — pure DB operations,
no business logic or HTTP concerns.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional, Tuple
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import asc, desc, case
from sqlalchemy.orm import Session, joinedload

from app.models.action_item import ActionItem
from app.models.client import Client
from app.schemas.action_item import ActionItemListResponse, ActionItemResponse


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _verify_client_ownership(
    db: Session, client_id: UUID, owner_id: UUID | None = None, org_id: UUID | None = None,
) -> Client:
    if org_id is not None:
        client = (
            db.query(Client)
            .filter(Client.id == client_id, Client.org_id == org_id)
            .first()
        )
    else:
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


def _to_response(item: ActionItem, client_name: str | None = None) -> ActionItemResponse:
    """Build an ActionItemResponse, eagerly pulling the document filename."""
    return ActionItemResponse(
        id=item.id,
        document_id=item.document_id,
        client_id=item.client_id,
        text=item.text,
        status=item.status,
        priority=item.priority,
        due_date=item.due_date,
        assigned_to=item.assigned_to,
        assigned_to_name=item.assigned_to_name,
        notes=item.notes,
        created_by=item.created_by,
        source=item.source,
        extracted_at=item.extracted_at,
        completed_at=item.completed_at,
        created_at=item.created_at,
        updated_at=item.updated_at,
        document_filename=item.document.filename if item.document else None,
        client_name=client_name,
    )


# ---------------------------------------------------------------------------
# Public service functions
# ---------------------------------------------------------------------------


def get_action_items(
    db: Session,
    client_id: UUID,
    owner_id: UUID | None = None,
    org_id: UUID | None = None,
    status_filter: Optional[str] = None,   # 'pending' | 'completed' | 'cancelled' | None
    skip: int = 0,
    limit: int = 50,
) -> Tuple[list[ActionItemResponse], int]:
    """Return paginated action items for a client (org or owner scoped)."""
    _verify_client_ownership(db, client_id, owner_id=owner_id, org_id=org_id)

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
    owner_id: UUID | None = None,
    org_id: UUID | None = None,
) -> Optional[ActionItem]:
    """Fetch a single action item, verifying the client belongs to the org (or owner)."""
    query = (
        db.query(ActionItem)
        .join(Client, ActionItem.client_id == Client.id)
        .options(joinedload(ActionItem.document))
    )
    if org_id is not None:
        query = query.filter(ActionItem.id == item_id, Client.org_id == org_id)
    else:
        query = query.filter(ActionItem.id == item_id, Client.owner_id == owner_id)
    return query.first()


def update_action_item(
    db: Session,
    item_id: UUID,
    owner_id: UUID | None = None,
    org_id: UUID | None = None,
    updates: dict | None = None,
) -> ActionItemResponse:
    """
    Apply *updates* (only provided keys) to an action item.

    Setting status → 'completed' records completed_at.
    Setting status → anything else clears completed_at.
    """
    updates = updates or {}
    item = get_action_item_by_id(db, item_id, owner_id=owner_id, org_id=org_id)
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

    if "text" in updates:
        item.text = updates["text"]

    if "assigned_to" in updates:
        item.assigned_to = updates["assigned_to"]

    if "assigned_to_name" in updates:
        item.assigned_to_name = updates["assigned_to_name"]

    if "notes" in updates:
        item.notes = updates["notes"]

    db.commit()
    db.refresh(item)
    return _to_response(item)


def create_action_item(
    db: Session,
    client_id: UUID,
    org_id: UUID,
    user_id: str,
    data: dict,
) -> ActionItemResponse:
    """Create a manual action item (not tied to a document)."""
    _verify_client_ownership(db, client_id, org_id=org_id)

    item = ActionItem(
        client_id=client_id,
        document_id=None,
        text=data["text"],
        status="pending",
        priority=data.get("priority", "medium"),
        due_date=data.get("due_date"),
        assigned_to=data.get("assigned_to"),
        assigned_to_name=data.get("assigned_to_name"),
        notes=data.get("notes"),
        created_by=user_id,
        source="manual",
        extracted_at=None,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _to_response(item)


def get_org_action_items(
    db: Session,
    org_id: UUID,
    user_id: str,
    is_admin: bool,
    *,
    status_filter: Optional[str] = None,
    priority_filter: Optional[str] = None,
    assigned_to_filter: Optional[str] = None,
    client_id_filter: Optional[UUID] = None,
    due_before: Optional[date] = None,
    include_overdue: bool = False,
    sort: str = "due_date",
    skip: int = 0,
    limit: int = 50,
) -> Tuple[list[ActionItemResponse], int]:
    """Return paginated action items across the org, scoped by assignment access."""
    from app.services.assignment_service import get_accessible_client_ids

    accessible_ids = get_accessible_client_ids(user_id, org_id, is_admin, db)

    query = (
        db.query(ActionItem, Client.name.label("client_name"))
        .join(Client, ActionItem.client_id == Client.id)
        .filter(Client.org_id == org_id)
    )

    if accessible_ids is not None:
        query = query.filter(ActionItem.client_id.in_(accessible_ids))

    if status_filter and status_filter != "all":
        query = query.filter(ActionItem.status == status_filter)
    if priority_filter:
        query = query.filter(ActionItem.priority == priority_filter)
    if assigned_to_filter:
        query = query.filter(ActionItem.assigned_to == assigned_to_filter)
    if client_id_filter:
        query = query.filter(ActionItem.client_id == client_id_filter)
    if due_before:
        query = query.filter(ActionItem.due_date <= due_before)
    if include_overdue:
        query = query.filter(
            ActionItem.due_date < date.today(),
            ActionItem.status == "pending",
        )

    total = query.count()

    # Sorting
    if sort == "priority":
        priority_order = case(
            (ActionItem.priority == "high", 1),
            (ActionItem.priority == "medium", 2),
            (ActionItem.priority == "low", 3),
            else_=4,
        )
        query = query.order_by(priority_order, ActionItem.created_at.desc())
    elif sort == "created_at":
        query = query.order_by(desc(ActionItem.created_at))
    else:
        # due_date — nulls last
        query = query.order_by(
            asc(ActionItem.due_date).nullslast(),
            ActionItem.created_at.desc(),
        )

    rows = query.options(joinedload(ActionItem.document)).offset(skip).limit(limit).all()

    items = [_to_response(item, client_name=cname) for item, cname in rows]
    return items, total


def delete_action_item(
    db: Session,
    item_id: UUID,
    owner_id: UUID | None = None,
    org_id: UUID | None = None,
) -> bool:
    """Delete an action item. Returns False if not found."""
    item = get_action_item_by_id(db, item_id, owner_id=owner_id, org_id=org_id)
    if item is None:
        return False
    db.delete(item)
    db.commit()
    return True

"""
Action items API router.

Endpoints:
  GET  /action-items                              org-wide listing (filterable)
  POST /action-items                              create manual action item
  GET  /clients/{client_id}/action-items           list (filterable by status)
  GET  /clients/{client_id}/action-items/pending   shortcut — pending only
  PATCH /action-items/{item_id}                    update fields
  DELETE /action-items/{item_id}                   remove item
  POST /documents/{document_id}/reextract-action-items  re-run extraction
"""

from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.action_item import ActionItem
from app.models.client import Client
from app.schemas.action_item import (
    ActionItemCreate,
    ActionItemListResponse,
    ActionItemResponse,
    ActionItemUpdate,
)
import logging

from app.services import action_item_service
from app.services.auth_context import AuthContext, check_client_access, get_auth
from app.services.document_service import get_document

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Org-wide action items
# ---------------------------------------------------------------------------


@router.get(
    "/action-items",
    response_model=ActionItemListResponse,
    summary="List action items across the org",
)
async def list_org_action_items(
    status: Optional[str] = None,
    priority: Optional[str] = None,
    assigned_to: Optional[str] = None,
    client_id: Optional[UUID] = None,
    due_before: Optional[date] = None,
    due_after: Optional[date] = None,
    include_overdue: bool = False,
    sort: str = Query(default="due_date", pattern="^(due_date|priority|created_at)$"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> ActionItemListResponse:
    items, total = action_item_service.get_org_action_items(
        db=db,
        org_id=auth.org_id,
        user_id=auth.user_id,
        is_admin=auth.org_role == "admin",
        status_filter=status,
        priority_filter=priority,
        assigned_to_filter=assigned_to,
        client_id_filter=client_id,
        due_before=due_before,
        due_after=due_after,
        include_overdue=include_overdue,
        sort=sort,
        skip=skip,
        limit=limit,
    )
    return ActionItemListResponse(items=items, total=total, skip=skip, limit=limit)


@router.post(
    "/action-items",
    response_model=ActionItemResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a manual action item",
)
async def create_action_item(
    body: ActionItemCreate,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> ActionItemResponse:
    check_client_access(auth, body.client_id, db)
    return action_item_service.create_action_item(
        db=db,
        client_id=body.client_id,
        org_id=auth.org_id,
        user_id=auth.user_id,
        data=body.model_dump(exclude={"client_id"}, exclude_unset=False),
    )


# ---------------------------------------------------------------------------
# List action items for a client
# ---------------------------------------------------------------------------


@router.get(
    "/clients/{client_id}/action-items",
    response_model=ActionItemListResponse,
    summary="List action items for a client",
)
async def list_action_items(
    client_id: UUID,
    status: Optional[str] = None,   # 'pending' | 'completed' | 'cancelled' | 'all'
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> ActionItemListResponse:
    check_client_access(auth, client_id, db)
    items, total = action_item_service.get_action_items(
        db=db,
        client_id=client_id,
        org_id=auth.org_id,
        status_filter=status,
        skip=skip,
        limit=limit,
    )
    return ActionItemListResponse(items=items, total=total, skip=skip, limit=limit)


@router.get(
    "/clients/{client_id}/action-items/pending",
    response_model=ActionItemListResponse,
    summary="List pending action items for a client",
)
async def list_pending_action_items(
    client_id: UUID,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> ActionItemListResponse:
    check_client_access(auth, client_id, db)
    items, total = action_item_service.get_action_items(
        db=db,
        client_id=client_id,
        org_id=auth.org_id,
        status_filter="pending",
        skip=skip,
        limit=limit,
    )
    return ActionItemListResponse(items=items, total=total, skip=skip, limit=limit)


# ---------------------------------------------------------------------------
# Update / delete a single action item
# ---------------------------------------------------------------------------


@router.patch(
    "/action-items/{item_id}",
    response_model=ActionItemResponse,
    summary="Update an action item",
)
async def update_action_item(
    item_id: UUID,
    body: ActionItemUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> ActionItemResponse:
    # Look up the action item's client to verify org access
    item = (
        db.query(ActionItem)
        .filter(ActionItem.id == item_id)
        .first()
    )
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Action item not found"
        )
    check_client_access(auth, item.client_id, db)

    # Snapshot pre-update state for notification logic
    old_assigned_to = item.assigned_to
    old_status = item.status
    creator_id = item.created_by

    updates = body.model_dump(exclude_unset=True)
    updated_item = action_item_service.update_action_item(
        db=db,
        item_id=item_id,
        org_id=auth.org_id,
        updates=updates,
    )

    # --- Notification triggers (fire-and-forget in background) ---

    # Assignment notification: new assignee who isn't the current user
    new_assigned = updates.get("assigned_to")
    if new_assigned and new_assigned != old_assigned_to and new_assigned != auth.user_id:
        background_tasks.add_task(
            _send_assignment_notification,
            assigned_to=new_assigned,
            assigner_id=auth.user_id,
            item_id=str(item_id),
            org_id=str(auth.org_id),
        )

    # Completion notification: notify the creator (if different from completer)
    if updates.get("status") == "completed" and old_status != "completed":
        if creator_id and creator_id != auth.user_id:
            background_tasks.add_task(
                _send_completion_notification,
                creator_id=creator_id,
                completer_id=auth.user_id,
                item_id=str(item_id),
                org_id=str(auth.org_id),
            )

    return updated_item


@router.delete(
    "/action-items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an action item",
)
async def delete_action_item(
    item_id: UUID,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> None:
    # Look up the action item's client to verify org access
    item = (
        db.query(ActionItem)
        .filter(ActionItem.id == item_id)
        .first()
    )
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Action item not found"
        )
    check_client_access(auth, item.client_id, db)

    deleted = action_item_service.delete_action_item(
        db=db,
        item_id=item_id,
        org_id=auth.org_id,
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Action item not found"
        )


# ---------------------------------------------------------------------------
# Re-extract action items from a document
# ---------------------------------------------------------------------------


@router.post(
    "/documents/{document_id}/reextract-action-items",
    summary="Re-extract action items from a document",
)
async def reextract_action_items(
    document_id: UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> dict:
    # Verify the document belongs to a client in this org
    document = get_document(db, document_id=document_id, org_id=auth.org_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )
    check_client_access(auth, document.client_id, db)

    if not document.processed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Document has not been processed yet. Process it first.",
        )

    async def _reextract_task(doc_id: UUID, client_id: UUID) -> None:
        from app.core.database import SessionLocal
        from app.services.action_item_extractor import reextract_action_items as _re

        task_db: Session = SessionLocal()
        try:
            await _re(task_db, doc_id, client_id)
        finally:
            task_db.close()

    background_tasks.add_task(
        _reextract_task, document.id, document.client_id
    )
    return {"message": "Re-extraction started in the background"}


# ---------------------------------------------------------------------------
# Notification background helpers
# ---------------------------------------------------------------------------


def _send_assignment_notification(
    assigned_to: str,
    assigner_id: str,
    item_id: str,
    org_id: str,
) -> None:
    """Look up users and send task-assigned email. Runs as a background task."""
    from app.core.config import get_settings
    from app.core.database import SessionLocal
    from app.models.user import User
    from app.services import notification_service

    db = SessionLocal()
    try:
        recipient = db.query(User).filter(User.clerk_id == assigned_to).first()
        if not recipient or not recipient.email:
            return

        # Check preferences
        prefs = notification_service.get_user_preferences(db, assigned_to, org_id)
        if prefs and not prefs.task_assigned:
            return

        sender = db.query(User).filter(User.clerk_id == assigner_id).first()
        assigner_name = (
            f"{sender.first_name or ''} {sender.last_name or ''}".strip()
            if sender else "A teammate"
        ) or "A teammate"

        item = db.query(ActionItem).filter(ActionItem.id == item_id).first()
        if not item:
            return

        client = db.query(Client).filter(Client.id == item.client_id).first()
        settings = get_settings()
        task_url = f"{settings.frontend_url}/dashboard/actions"

        to_name = f"{recipient.first_name or ''} {recipient.last_name or ''}".strip() or "there"

        notification_service.send_task_assigned_email(
            to_email=recipient.email,
            to_name=to_name,
            assigner_name=assigner_name,
            task_text=item.text,
            client_name=client.name if client else None,
            due_date=item.due_date,
            task_url=task_url,
        )
    except Exception:
        logger.exception("Failed to send assignment notification for item %s", item_id)
    finally:
        db.close()


def _send_completion_notification(
    creator_id: str,
    completer_id: str,
    item_id: str,
    org_id: str,
) -> None:
    """Look up users and send task-completed email. Runs as a background task."""
    from app.core.config import get_settings
    from app.core.database import SessionLocal
    from app.models.user import User
    from app.services import notification_service

    db = SessionLocal()
    try:
        recipient = db.query(User).filter(User.clerk_id == creator_id).first()
        if not recipient or not recipient.email:
            return

        # Check preferences
        prefs = notification_service.get_user_preferences(db, creator_id, org_id)
        if prefs and not prefs.task_completed:
            return

        completer = db.query(User).filter(User.clerk_id == completer_id).first()
        completer_name = (
            f"{completer.first_name or ''} {completer.last_name or ''}".strip()
            if completer else "A teammate"
        ) or "A teammate"

        item = db.query(ActionItem).filter(ActionItem.id == item_id).first()
        if not item:
            return

        client = db.query(Client).filter(Client.id == item.client_id).first()
        settings = get_settings()
        task_url = f"{settings.frontend_url}/dashboard/actions"

        to_name = f"{recipient.first_name or ''} {recipient.last_name or ''}".strip() or "there"

        notification_service.send_task_completed_email(
            to_email=recipient.email,
            to_name=to_name,
            completer_name=completer_name,
            task_text=item.text,
            client_name=client.name if client else None,
            task_url=task_url,
        )
    except Exception:
        logger.exception("Failed to send completion notification for item %s", item_id)
    finally:
        db.close()

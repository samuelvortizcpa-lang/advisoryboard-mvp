"""
Action items API router.

Endpoints:
  GET  /clients/{client_id}/action-items           list (filterable by status)
  GET  /clients/{client_id}/action-items/pending   shortcut — pending only
  PATCH /action-items/{item_id}                    update status/priority/due_date
  DELETE /action-items/{item_id}                   remove item
  POST /documents/{document_id}/reextract-action-items  re-run extraction
"""

from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.schemas.action_item import (
    ActionItemListResponse,
    ActionItemResponse,
    ActionItemUpdate,
)
from app.services import action_item_service, user_service
from app.services.document_service import get_document

router = APIRouter()


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
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> ActionItemListResponse:
    user = user_service.get_or_create_user(db, current_user)
    items, total = action_item_service.get_action_items(
        db=db,
        client_id=client_id,
        owner_id=user.id,
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
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> ActionItemListResponse:
    user = user_service.get_or_create_user(db, current_user)
    items, total = action_item_service.get_action_items(
        db=db,
        client_id=client_id,
        owner_id=user.id,
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
    summary="Update an action item (status, priority, due_date)",
)
async def update_action_item(
    item_id: UUID,
    body: ActionItemUpdate,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> ActionItemResponse:
    user = user_service.get_or_create_user(db, current_user)
    # Only pass fields that were actually provided in the request body
    updates = body.model_dump(exclude_unset=True)
    return action_item_service.update_action_item(
        db=db,
        item_id=item_id,
        owner_id=user.id,
        updates=updates,
    )


@router.delete(
    "/action-items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an action item",
)
async def delete_action_item(
    item_id: UUID,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> None:
    user = user_service.get_or_create_user(db, current_user)
    deleted = action_item_service.delete_action_item(
        db=db,
        item_id=item_id,
        owner_id=user.id,
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
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> dict:
    user = user_service.get_or_create_user(db, current_user)

    # Verify the document belongs to a client owned by this user
    document = get_document(db, document_id=document_id, owner_id=user.id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )
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

"""
Timeline API router.

Endpoints:
  GET /clients/{client_id}/timeline   chronological list of documents + action items
"""

from datetime import date
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.models.action_item import ActionItem
from app.models.client import Client
from app.models.document import Document
from app.schemas.timeline import (
    ActionItemTimelineItem,
    DocumentTimelineItem,
    TimelineItem,
    TimelineResponse,
)
from app.services.auth_context import AuthContext, check_client_access, get_auth

router = APIRouter()


@router.get(
    "/clients/{client_id}/timeline",
    response_model=TimelineResponse,
    summary="Get chronological timeline of all client interactions",
)
async def get_client_timeline(
    client_id: UUID,
    types: Optional[List[str]] = Query(default=None),  # ["document", "action_item"]
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    limit: int = Query(default=50, ge=1, le=200),
    skip: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> TimelineResponse:
    check_client_access(auth, client_id, db)

    include_documents = not types or "document" in types
    include_action_items = not types or "action_item" in types

    items: List[TimelineItem] = []

    # Cap per-source fetch to skip+limit so we never load unbounded result
    # sets into memory. This bounds total in-memory records to 2*(skip+limit).
    fetch_limit = skip + limit

    # Fetch documents
    if include_documents:
        doc_query = (
            db.query(Document)
            .filter(Document.client_id == client_id)
            .order_by(Document.upload_date.desc())
        )
        if start_date:
            doc_query = doc_query.filter(Document.upload_date >= start_date)
        if end_date:
            doc_query = doc_query.filter(Document.upload_date <= end_date)
        for doc in doc_query.limit(fetch_limit).all():
            items.append(
                DocumentTimelineItem(
                    type="document",
                    id=doc.id,
                    date=doc.upload_date,
                    filename=doc.filename,
                    file_type=doc.file_type,
                    file_size=doc.file_size,
                    processed=doc.processed,
                )
            )

    # Fetch action items
    if include_action_items:
        ai_query = (
            db.query(ActionItem)
            .filter(ActionItem.client_id == client_id)
            .options(joinedload(ActionItem.document))
            .order_by(ActionItem.created_at.desc())
        )
        if start_date:
            ai_query = ai_query.filter(ActionItem.created_at >= start_date)
        if end_date:
            ai_query = ai_query.filter(ActionItem.created_at <= end_date)
        for ai in ai_query.limit(fetch_limit).all():
            items.append(
                ActionItemTimelineItem(
                    type="action_item",
                    id=ai.id,
                    date=ai.created_at,
                    text=ai.text,
                    status=ai.status,
                    priority=ai.priority,
                    source_doc=ai.document.filename if ai.document else None,
                )
            )

    # Sort newest first and apply pagination
    items.sort(key=lambda x: x.date, reverse=True)
    total = len(items)
    paginated = items[skip : skip + limit]

    return TimelineResponse(items=paginated, total=total, skip=skip, limit=limit)

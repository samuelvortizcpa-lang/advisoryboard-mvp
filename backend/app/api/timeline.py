"""
Timeline API router.

Endpoints:
  GET /clients/{client_id}/timeline   chronological list of documents, action items + communications
"""

from datetime import date
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.models.action_item import ActionItem
from app.models.client import Client
from app.models.client_communication import ClientCommunication
from app.models.document import Document
from app.models.checkin_response import CheckinResponse
from app.models.checkin_template import CheckinTemplate
from app.models.chat_session import ChatSession
from app.schemas.timeline import (
    ActionItemTimelineItem,
    CheckinTimelineItem,
    CommunicationTimelineItem,
    DocumentTimelineItem,
    SessionTimelineItem,
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
    types: Optional[List[str]] = Query(default=None),  # ["document", "action_item", "communication"]
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
    include_communications = not types or "communication" in types
    include_sessions = not types or "session" in types
    include_checkins = not types or "checkin" in types

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

    # Fetch communications
    if include_communications:
        comm_query = (
            db.query(ClientCommunication)
            .filter(ClientCommunication.client_id == client_id)
            .options(joinedload(ClientCommunication.template))
            .order_by(ClientCommunication.sent_at.desc())
        )
        if start_date:
            comm_query = comm_query.filter(ClientCommunication.sent_at >= start_date)
        if end_date:
            comm_query = comm_query.filter(ClientCommunication.sent_at <= end_date)
        for comm in comm_query.limit(fetch_limit).all():
            meta = {
                "communication_id": str(comm.id),
                "ai_drafted": bool(
                    comm.metadata_ and comm.metadata_.get("ai_drafted")
                ),
            }
            if comm.template and comm.template.name:
                meta["template_name"] = comm.template.name

            items.append(
                CommunicationTimelineItem(
                    type="communication",
                    id=comm.id,
                    date=comm.sent_at,
                    title=f"Email sent: {comm.subject}",
                    subtitle=f"To {comm.recipient_name or comm.recipient_email}",
                    icon_hint="email",
                    status=comm.status,
                    metadata=meta,
                )
            )

    # Fetch closed sessions
    if include_sessions:
        sess_query = (
            db.query(ChatSession)
            .filter(
                ChatSession.client_id == client_id,
                ChatSession.is_active.is_(False),
            )
            .order_by(ChatSession.started_at.desc())
        )
        if start_date:
            sess_query = sess_query.filter(ChatSession.started_at >= start_date)
        if end_date:
            sess_query = sess_query.filter(ChatSession.started_at <= end_date)
        for sess in sess_query.limit(fetch_limit).all():
            items.append(
                SessionTimelineItem(
                    type="session",
                    id=sess.id,
                    date=sess.started_at,
                    title=sess.title,
                    ended_at=sess.ended_at,
                    message_count=sess.message_count or 0,
                    topic_count=len(sess.key_topics) if sess.key_topics else 0,
                    icon_hint="chat",
                )
            )

    # Fetch check-ins
    if include_checkins:
        ci_query = (
            db.query(CheckinResponse, CheckinTemplate.name)
            .join(CheckinTemplate, CheckinResponse.template_id == CheckinTemplate.id)
            .filter(CheckinResponse.client_id == client_id)
            .order_by(CheckinResponse.sent_at.desc())
        )
        if start_date:
            ci_query = ci_query.filter(CheckinResponse.sent_at >= start_date)
        if end_date:
            ci_query = ci_query.filter(CheckinResponse.sent_at <= end_date)
        for ci, template_name in ci_query.limit(fetch_limit).all():
            if ci.status == "completed" and ci.completed_at:
                items.append(
                    CheckinTimelineItem(
                        type="checkin",
                        id=ci.id,
                        date=ci.completed_at,
                        title=f"Check-in completed: {template_name}",
                        subtitle=f"{ci.sent_to_name or ci.sent_to_email} responded",
                        icon_hint="check-circle",
                        status="completed",
                    )
                )
            else:
                items.append(
                    CheckinTimelineItem(
                        type="checkin",
                        id=ci.id,
                        date=ci.sent_at,
                        title=f"Check-in sent: {template_name}",
                        subtitle=f"Sent to {ci.sent_to_email}",
                        icon_hint="mail",
                        status=ci.status,
                    )
                )

    # Sort newest first and apply pagination
    items.sort(key=lambda x: x.date, reverse=True)
    total = len(items)
    paginated = items[skip : skip + limit]

    return TimelineResponse(items=paginated, total=total, skip=skip, limit=limit)

"""
Session Memory API endpoints.

Routes:
  GET    /api/clients/{client_id}/sessions                 — Paginated session list
  GET    /api/clients/{client_id}/sessions/{session_id}    — Session detail with messages
  GET    /api/sessions/{session_id}/messages                — Session messages (standalone)
  POST   /api/clients/{client_id}/sessions/search          — Semantic search
  POST   /api/clients/{client_id}/sessions/new             — Close active session (new chat)
  DELETE /api/clients/{client_id}/sessions/{session_id}    — Soft delete
"""

from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.chat_message import ChatMessage
from app.models.chat_session import ChatSession
from app.schemas.chat_message import ChatMessageResponse
from app.schemas.session import (
    CloseSessionResponse,
    QAPairResult,
    SessionDetail,
    SessionListResponse,
    SessionSearchRequest,
    SessionSearchResponse,
    SessionSearchResult,
    SessionSummary,
    SessionWithMessages,
)
from app.services.auth_context import AuthContext, check_client_access, get_auth
from app.services.session_memory_service import (
    _close_session_sync,
    get_session_detail,
    search_qa_pairs,
    search_sessions,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _verify_client(db: Session, client_id: UUID, auth: AuthContext) -> None:
    """Ensure the caller has access to this client."""
    check_client_access(auth, client_id, db)
    from app.models.client import Client
    client = (
        db.query(Client)
        .filter(Client.id == client_id, Client.org_id == auth.org_id)
        .first()
    )
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")


# ---------------------------------------------------------------------------
# List sessions (paginated)
# ---------------------------------------------------------------------------


@router.get(
    "/clients/{client_id}/sessions",
    response_model=SessionListResponse,
    summary="List chat sessions for a client",
)
async def list_sessions(
    client_id: UUID,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> SessionListResponse:
    _verify_client(db, client_id, auth)

    base_q = db.query(ChatSession).filter(
        ChatSession.client_id == client_id,
        ChatSession.user_id == auth.user_id,
    )

    total = base_q.count()

    sessions = (
        base_q
        .order_by(ChatSession.started_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    return SessionListResponse(
        sessions=[SessionSummary.model_validate(s) for s in sessions],
        total=total,
        page=page,
        per_page=per_page,
    )


# ---------------------------------------------------------------------------
# Session detail
# ---------------------------------------------------------------------------


@router.get(
    "/clients/{client_id}/sessions/{session_id}",
    response_model=SessionDetail,
    summary="Get session detail with all messages",
)
async def session_detail(
    client_id: UUID,
    session_id: UUID,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> SessionDetail:
    _verify_client(db, client_id, auth)

    session = get_session_detail(session_id, auth.user_id, db)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session not found"
        )
    if session.client_id != client_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session not found"
        )

    return SessionDetail(
        id=session.id,
        title=session.title,
        summary=session.summary,
        key_topics=session.key_topics,
        key_decisions=session.key_decisions,
        started_at=session.started_at,
        ended_at=session.ended_at,
        message_count=session.message_count,
        messages=[ChatMessageResponse.model_validate(m) for m in session.messages],
    )


# ---------------------------------------------------------------------------
# Standalone session messages (by session_id only)
# ---------------------------------------------------------------------------


@router.get(
    "/sessions/{session_id}/messages",
    response_model=SessionWithMessages,
    summary="Get session metadata and messages by session ID",
)
async def session_messages(
    session_id: UUID,
    limit: int = Query(default=0, ge=0, le=500, description="Max messages (0 = all)"),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> SessionWithMessages:
    session = (
        db.query(ChatSession)
        .filter(
            ChatSession.id == session_id,
            ChatSession.user_id == auth.user_id,
        )
        .first()
    )
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session not found"
        )

    msg_q = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
    )
    if offset:
        msg_q = msg_q.offset(offset)
    if limit:
        msg_q = msg_q.limit(limit)

    from app.schemas.session import SessionMessageItem

    return SessionWithMessages(
        id=session.id,
        title=session.title,
        summary=session.summary,
        key_topics=session.key_topics,
        key_decisions=session.key_decisions,
        started_at=session.started_at,
        ended_at=session.ended_at,
        is_active=session.is_active,
        message_count=session.message_count,
        messages=[SessionMessageItem.model_validate(m) for m in msg_q.all()],
    )


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


@router.post(
    "/clients/{client_id}/sessions/search",
    response_model=SessionSearchResponse,
    summary="Semantic search over sessions and Q&A pairs",
)
async def search(
    client_id: UUID,
    body: SessionSearchRequest,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> SessionSearchResponse:
    _verify_client(db, client_id, auth)

    # Run both searches in parallel
    session_results, qa_results = await asyncio.gather(
        search_sessions(client_id, auth.user_id, body.query, db, limit=body.limit),
        search_qa_pairs(client_id, auth.user_id, body.query, db, limit=body.limit * 2),
    )

    return SessionSearchResponse(
        sessions=[SessionSearchResult(**s) for s in session_results],
        qa_pairs=[QAPairResult(**q) for q in qa_results],
    )


# ---------------------------------------------------------------------------
# Delete (soft)
# ---------------------------------------------------------------------------


@router.delete(
    "/clients/{client_id}/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Delete a session (unlinks messages, removes session record)",
)
async def delete_session(
    client_id: UUID,
    session_id: UUID,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> None:
    _verify_client(db, client_id, auth)

    session = (
        db.query(ChatSession)
        .filter(
            ChatSession.id == session_id,
            ChatSession.client_id == client_id,
            ChatSession.user_id == auth.user_id,
        )
        .first()
    )
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session not found"
        )

    # Unlink messages (set session_id = null)
    db.query(ChatMessage).filter(
        ChatMessage.session_id == session_id
    ).update({"session_id": None})

    db.delete(session)
    db.commit()


# ---------------------------------------------------------------------------
# Close active session (new chat)
# ---------------------------------------------------------------------------


@router.post(
    "/clients/{client_id}/sessions/new",
    response_model=CloseSessionResponse,
    summary="Close the active session so the next message starts a new chat",
)
async def close_active_session(
    client_id: UUID,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> CloseSessionResponse:
    _verify_client(db, client_id, auth)

    active = (
        db.query(ChatSession)
        .filter(
            ChatSession.client_id == client_id,
            ChatSession.user_id == auth.user_id,
            ChatSession.is_active.is_(True),
        )
        .first()
    )

    if active is None:
        return CloseSessionResponse()

    closed_id = active.id
    closed_title = active.title

    _close_session_sync(active, db)
    db.commit()

    return CloseSessionResponse(
        closed_session_id=closed_id,
        closed_session_title=closed_title,
    )

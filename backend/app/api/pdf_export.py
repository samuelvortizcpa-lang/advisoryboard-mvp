"""
PDF Export API endpoints.

Routes (all require Clerk JWT auth):
  POST /api/clients/{client_id}/briefs/{brief_id}/pdf
  POST /api/clients/{client_id}/chat/{message_id}/pdf
  POST /api/clients/{client_id}/briefs/generate-pdf
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.client import Client
from app.models.client_brief import ClientBrief
from app.models.chat_message import ChatMessage
from app.services.auth_context import AuthContext, check_client_access, get_auth

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Response schemas ──────────────────────────────────────────────────────────


class PdfExportResponse(BaseModel):
    pdf_url: str
    size_bytes: int


class GenerateWithPdfResponse(BaseModel):
    brief_id: str
    pdf_url: str
    markdown: str


# ── Helpers ───────────────────────────────────────────────────────────────────


def _upload_and_sign(storage_path: str, pdf_bytes: bytes) -> str:
    """Upload PDF to Supabase and return a signed URL."""
    from app.services.storage_service import upload_file_to_path, get_signed_url

    upload_file_to_path(storage_path, pdf_bytes, "application/pdf")
    return get_signed_url(storage_path, expires_in=3600)


def _try_cached(storage_path: str) -> str | None:
    """Return a signed URL if the file already exists in storage."""
    try:
        from app.services.storage_service import get_signed_url
        return get_signed_url(storage_path, expires_in=3600)
    except Exception:
        return None


def _get_client_name(db: Session, client_id: UUID) -> str | None:
    client = db.query(Client).filter(Client.id == client_id).first()
    return client.name if client else None


# ── POST /clients/{client_id}/briefs/{brief_id}/pdf ──────────────────────────


@router.post(
    "/clients/{client_id}/briefs/{brief_id}/pdf",
    response_model=PdfExportResponse,
    summary="Export an existing brief as PDF",
)
async def export_brief_pdf(
    client_id: UUID,
    brief_id: UUID,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> PdfExportResponse:
    check_client_access(auth, client_id, db)

    brief = (
        db.query(ClientBrief)
        .filter(ClientBrief.id == brief_id, ClientBrief.client_id == client_id)
        .first()
    )
    if not brief:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Brief not found")

    storage_path = f"exports/{auth.user_id}/{brief_id}.pdf"

    # Check cache
    cached_url = _try_cached(storage_path)
    if cached_url:
        return PdfExportResponse(pdf_url=cached_url, size_bytes=0)

    # Generate
    from app.services.pdf_generator import generate_brief_pdf

    client_name = _get_client_name(db, client_id)
    pdf_bytes = generate_brief_pdf(
        markdown_content=brief.content,
        client_name=client_name,
        generated_at=brief.generated_at,
    )

    signed_url = _upload_and_sign(storage_path, pdf_bytes)
    return PdfExportResponse(pdf_url=signed_url, size_bytes=len(pdf_bytes))


# ── POST /clients/{client_id}/chat/{message_id}/pdf ──────────────────────────


@router.post(
    "/clients/{client_id}/chat/{message_id}/pdf",
    response_model=PdfExportResponse,
    summary="Export a single chat response as PDF",
)
async def export_chat_pdf(
    client_id: UUID,
    message_id: UUID,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> PdfExportResponse:
    check_client_access(auth, client_id, db)

    assistant_msg = (
        db.query(ChatMessage)
        .filter(ChatMessage.id == message_id, ChatMessage.client_id == client_id)
        .first()
    )
    if not assistant_msg:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Message not found")

    # Find the preceding user question in the same session
    question = "N/A"
    if assistant_msg.session_id:
        user_msg = (
            db.query(ChatMessage)
            .filter(
                ChatMessage.session_id == assistant_msg.session_id,
                ChatMessage.role == "user",
                ChatMessage.created_at < assistant_msg.created_at,
            )
            .order_by(ChatMessage.created_at.desc())
            .first()
        )
        if user_msg:
            question = user_msg.content
    else:
        # Fallback: find the previous user message for this client
        user_msg = (
            db.query(ChatMessage)
            .filter(
                ChatMessage.client_id == client_id,
                ChatMessage.role == "user",
                ChatMessage.created_at < assistant_msg.created_at,
            )
            .order_by(ChatMessage.created_at.desc())
            .first()
        )
        if user_msg:
            question = user_msg.content

    storage_path = f"exports/{auth.user_id}/chat_{message_id}.pdf"

    cached_url = _try_cached(storage_path)
    if cached_url:
        return PdfExportResponse(pdf_url=cached_url, size_bytes=0)

    from app.services.pdf_generator import generate_chat_response_pdf

    client_name = _get_client_name(db, client_id)
    sources = assistant_msg.sources if isinstance(assistant_msg.sources, list) else []

    pdf_bytes = generate_chat_response_pdf(
        question=question,
        answer_markdown=assistant_msg.content,
        sources=sources,
        client_name=client_name,
    )

    signed_url = _upload_and_sign(storage_path, pdf_bytes)
    return PdfExportResponse(pdf_url=signed_url, size_bytes=len(pdf_bytes))


# ── POST /clients/{client_id}/briefs/generate-pdf ────────────────────────────


@router.post(
    "/clients/{client_id}/briefs/generate-pdf",
    response_model=GenerateWithPdfResponse,
    summary="Generate a new brief and return it as PDF",
)
async def generate_brief_with_pdf(
    client_id: UUID,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> GenerateWithPdfResponse:
    check_client_access(auth, client_id, db)

    # IRC §7216 consent check
    from app.api.rag import _require_consent_for_ai

    client = db.query(Client).filter(Client.id == client_id).first()
    if client:
        _require_consent_for_ai(client, auth, db)

    from app.services.brief_generator import generate_brief as _generate

    try:
        result = await _generate(db, client_id=client_id, user_id=auth.user_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    # Persist the brief
    brief = ClientBrief(
        client_id=client_id,
        user_id=auth.user_id,
        content=result["content"],
        document_count=result["document_count"],
        action_item_count=result["action_item_count"],
        metadata_=result["metadata"],
    )
    db.add(brief)
    db.commit()
    db.refresh(brief)

    # Generate PDF
    from app.services.pdf_generator import generate_brief_pdf

    pdf_bytes = generate_brief_pdf(
        markdown_content=brief.content,
        client_name=client.name if client else None,
        generated_at=brief.generated_at,
    )

    storage_path = f"exports/{auth.user_id}/{brief.id}.pdf"
    signed_url = _upload_and_sign(storage_path, pdf_bytes)

    return GenerateWithPdfResponse(
        brief_id=str(brief.id),
        pdf_url=signed_url,
        markdown=brief.content,
    )

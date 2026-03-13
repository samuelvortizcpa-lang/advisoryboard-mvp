"""
RAG API endpoints.

Routes (all require Clerk JWT auth):
  GET  /api/clients/{client_id}/rag/status
  POST /api/clients/{client_id}/rag/process
  POST /api/clients/{client_id}/documents/{document_id}/process
  POST /api/clients/{client_id}/rag/search
  POST /api/clients/{client_id}/rag/chat          ← now persists messages
  GET  /api/clients/{client_id}/chat-history
  DELETE /api/clients/{client_id}/chat-history
  GET  /api/clients/{client_id}/chat-history/export?format=txt|pdf
"""

from __future__ import annotations

from typing import Any, Dict, List
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.chat_message import ChatMessage
from app.models.client import Client
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.document_page_image import DocumentPageImage
from app.schemas.chat_message import ChatHistoryResponse, ChatMessageResponse
from app.services import rag_service, storage_service, user_service

router = APIRouter()


# ---------------------------------------------------------------------------
# Ownership guard
# ---------------------------------------------------------------------------


def _require_client(db: Session, client_id: UUID, owner_id: UUID) -> Client:
    client = (
        db.query(Client)
        .filter(Client.id == client_id, Client.owner_id == owner_id)
        .first()
    )
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    return client


# ---------------------------------------------------------------------------
# Pydantic schemas (local, route-level)
# ---------------------------------------------------------------------------


class ProcessResponse(BaseModel):
    queued: int
    message: str


class RagStatusResponse(BaseModel):
    total_documents: int
    processed: int
    pending: int
    errors: int
    total_chunks: int


class SearchRequest(BaseModel):
    query: str
    limit: int = 5


class SearchResult(BaseModel):
    chunk_text: str
    document_id: str
    filename: str
    chunk_index: int


class SearchResponse(BaseModel):
    results: List[SearchResult]


class ChatRequest(BaseModel):
    question: str


class SourceItem(BaseModel):
    document_id: str
    filename: str
    preview: str
    score: float = 0.0
    chunk_text: str = ""
    chunk_index: int = 0
    page_number: int | None = None
    image_url: str | None = None


class ChatResponse(BaseModel):
    answer: str
    confidence_tier: str = "low"
    confidence_score: float = 0.0
    sources: List[SourceItem]


class CompareRequest(BaseModel):
    document_ids: List[UUID]
    comparison_type: str = "summary"  # "summary" | "changes" | "financial"


class CompareDocumentMeta(BaseModel):
    id: str
    filename: str


class CompareResponse(BaseModel):
    comparison_type: str
    documents: List[CompareDocumentMeta]
    report: str


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


@router.get(
    "/clients/{client_id}/rag/status",
    response_model=RagStatusResponse,
    summary="Get RAG processing status for a client",
)
async def get_rag_status(
    client_id: UUID,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> RagStatusResponse:
    user = user_service.get_or_create_user(db, current_user)
    _require_client(db, client_id, user.id)

    documents = db.query(Document).filter(Document.client_id == client_id).all()

    processed = sum(1 for d in documents if d.processed)
    errors = sum(
        1 for d in documents if d.processing_error and not d.processed
    )
    pending = len(documents) - processed - errors

    total_chunks = (
        db.query(DocumentChunk)
        .filter(DocumentChunk.client_id == client_id)
        .count()
    )

    return RagStatusResponse(
        total_documents=len(documents),
        processed=processed,
        pending=pending,
        errors=errors,
        total_chunks=total_chunks,
    )


# ---------------------------------------------------------------------------
# Process all unprocessed documents
# ---------------------------------------------------------------------------


@router.post(
    "/clients/{client_id}/rag/process",
    response_model=ProcessResponse,
    summary="Queue all unprocessed documents for embedding",
)
async def process_client_documents(
    client_id: UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> ProcessResponse:
    user = user_service.get_or_create_user(db, current_user)
    _require_client(db, client_id, user.id)

    unprocessed = (
        db.query(Document)
        .filter(
            Document.client_id == client_id,
            Document.processed == False,  # noqa: E712
        )
        .all()
    )

    if not unprocessed:
        return ProcessResponse(
            queued=0, message="All documents are already processed."
        )

    for doc in unprocessed:
        background_tasks.add_task(rag_service.process_document_task, doc.id)

    return ProcessResponse(
        queued=len(unprocessed),
        message=f"Queued {len(unprocessed)} document(s) for processing.",
    )


# ---------------------------------------------------------------------------
# Process / re-process a single document
# ---------------------------------------------------------------------------


@router.post(
    "/clients/{client_id}/documents/{document_id}/process",
    response_model=ProcessResponse,
    summary="Queue a single document for (re)processing",
)
async def process_single_document(
    client_id: UUID,
    document_id: UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> ProcessResponse:
    user = user_service.get_or_create_user(db, current_user)
    _require_client(db, client_id, user.id)

    document = (
        db.query(Document)
        .filter(Document.id == document_id, Document.client_id == client_id)
        .first()
    )
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    background_tasks.add_task(rag_service.process_document_task, document.id)

    return ProcessResponse(queued=1, message="Document queued for processing.")


# ---------------------------------------------------------------------------
# Backfill page images for legacy PDFs
# ---------------------------------------------------------------------------


class BackfillResponse(BaseModel):
    processed: int
    skipped: int
    total_pages: int
    message: str


@router.post(
    "/documents/backfill-pages",
    response_model=BackfillResponse,
    summary="Backfill page images for PDFs missing them",
)
async def backfill_page_images(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> BackfillResponse:
    """
    Find all PDF documents that have no rows in document_page_images
    and run page image processing on them.
    """
    from app.services.page_image_service import process_page_images

    user = user_service.get_or_create_user(db, current_user)

    # Find all PDF documents owned by this user
    pdf_docs = (
        db.query(Document)
        .join(Client, Document.client_id == Client.id)
        .filter(
            Client.owner_id == user.id,
            Document.file_type == "pdf",
            Document.processed == True,  # noqa: E712
        )
        .all()
    )

    processed = 0
    skipped = 0
    total_pages = 0

    for doc in pdf_docs:
        # Check if page images already exist
        existing = (
            db.query(DocumentPageImage)
            .filter(DocumentPageImage.document_id == doc.id)
            .count()
        )
        if existing > 0:
            skipped += 1
            continue

        try:
            await process_page_images(db, doc)
            page_count = (
                db.query(DocumentPageImage)
                .filter(DocumentPageImage.document_id == doc.id)
                .count()
            )
            total_pages += page_count
            processed += 1
        except Exception:
            pass  # logged inside process_page_images

    return BackfillResponse(
        processed=processed,
        skipped=skipped,
        total_pages=total_pages,
        message=f"Processed {processed} PDF(s), generated {total_pages} page images. Skipped {skipped} already done.",
    )


# ---------------------------------------------------------------------------
# Debug: inspect chunks for a document
# ---------------------------------------------------------------------------


class DebugChunkItem(BaseModel):
    chunk_index: int
    chunk_text: str


class DebugChunksResponse(BaseModel):
    document_id: str
    filename: str
    total_chunks: int
    chunks: List[DebugChunkItem]


@router.get(
    "/documents/{document_id}/chunks",
    response_model=DebugChunksResponse,
    summary="[DEBUG] Return all chunks for a document",
)
async def debug_get_chunks(
    document_id: UUID,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> DebugChunksResponse:
    user = user_service.get_or_create_user(db, current_user)

    # Verify the document belongs to a client owned by this user
    document = (
        db.query(Document)
        .join(Client, Document.client_id == Client.id)
        .filter(Document.id == document_id, Client.owner_id == user.id)
        .first()
    )
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )

    chunks = (
        db.query(DocumentChunk)
        .filter(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.chunk_index)
        .all()
    )

    return DebugChunksResponse(
        document_id=str(document_id),
        filename=document.filename,
        total_chunks=len(chunks),
        chunks=[
            DebugChunkItem(chunk_index=c.chunk_index, chunk_text=c.chunk_text)
            for c in chunks
        ],
    )


# ---------------------------------------------------------------------------
# Semantic search
# ---------------------------------------------------------------------------


@router.post(
    "/clients/{client_id}/rag/search",
    response_model=SearchResponse,
    summary="Semantic search over client documents",
)
async def semantic_search(
    client_id: UUID,
    request: SearchRequest,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> SearchResponse:
    user = user_service.get_or_create_user(db, current_user)
    _require_client(db, client_id, user.id)

    if not request.query.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Query cannot be empty.")

    chunks = await rag_service.search_chunks(
        db, client_id=client_id, query=request.query, limit=request.limit
    )

    results = [
        SearchResult(
            chunk_text=c.chunk_text,
            document_id=str(c.document_id),
            filename=c.document.filename if c.document else "unknown",
            chunk_index=c.chunk_index,
        )
        for c in chunks
    ]

    return SearchResponse(results=results)


# ---------------------------------------------------------------------------
# Chat / Q&A  (persists both the question and answer)
# ---------------------------------------------------------------------------


@router.post(
    "/clients/{client_id}/rag/chat",
    response_model=ChatResponse,
    summary="Ask a question about client documents",
)
async def chat(
    client_id: UUID,
    request: ChatRequest,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> ChatResponse:
    user = user_service.get_or_create_user(db, current_user)
    _require_client(db, client_id, user.id)

    if not request.question.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Question cannot be empty."
        )

    result = await rag_service.answer_question(
        db, client_id=client_id, question=request.question
    )

    # Persist user question
    db.add(ChatMessage(
        client_id=client_id,
        user_id=user.clerk_id,
        role="user",
        content=request.question,
        sources=None,
    ))

    # Generate signed URLs for page image sources and build persisted data
    sources_data = []
    response_sources = []
    for s in result["sources"]:
        # Persist source metadata (image_path stored for future URL regeneration)
        persisted = {
            "document_id": s["document_id"],
            "filename": s["filename"],
            "preview": s["preview"],
            "score": s["score"],
            "chunk_text": s["chunk_text"],
            "chunk_index": s["chunk_index"],
        }
        if s.get("page_number") is not None:
            persisted["page_number"] = s["page_number"]
        if s.get("image_path"):
            persisted["image_path"] = s["image_path"]
        sources_data.append(persisted)

        # Build response source with signed URL
        response_source = {
            "document_id": s["document_id"],
            "filename": s["filename"],
            "preview": s["preview"],
            "score": s["score"],
            "chunk_text": s["chunk_text"],
            "chunk_index": s["chunk_index"],
        }
        if s.get("page_number") is not None:
            response_source["page_number"] = s["page_number"]
        if s.get("image_path"):
            try:
                response_source["image_url"] = storage_service.get_signed_url(
                    s["image_path"], expires_in=3600
                )
            except Exception:
                pass  # non-fatal: image URL generation failure
        response_sources.append(response_source)

    db.add(ChatMessage(
        client_id=client_id,
        user_id=user.clerk_id,
        role="assistant",
        content=result["answer"],
        sources=sources_data or None,
    ))

    db.commit()

    return ChatResponse(
        answer=result["answer"],
        confidence_tier=result["confidence_tier"],
        confidence_score=result["confidence_score"],
        sources=[SourceItem(**s) for s in response_sources],
    )


# ---------------------------------------------------------------------------
# Document comparison
# ---------------------------------------------------------------------------


@router.post(
    "/clients/{client_id}/rag/compare",
    response_model=CompareResponse,
    summary="Compare multiple client documents using AI",
)
async def compare_documents(
    client_id: UUID,
    request: CompareRequest,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> CompareResponse:
    user = user_service.get_or_create_user(db, current_user)
    _require_client(db, client_id, user.id)

    if len(request.document_ids) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least 2 documents are required for comparison.",
        )

    from app.services.document_comparator import compare_documents as _compare

    try:
        result = await _compare(
            document_ids=request.document_ids,
            comparison_type=request.comparison_type,
            client_id=client_id,
            db=db,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    return CompareResponse(
        comparison_type=result["comparison_type"],
        documents=[CompareDocumentMeta(**d) for d in result["documents"]],
        report=result["report"],
    )


# ---------------------------------------------------------------------------
# Chat history — GET
# ---------------------------------------------------------------------------


@router.get(
    "/clients/{client_id}/chat-history",
    response_model=ChatHistoryResponse,
    summary="Retrieve persisted chat history for a client",
)
async def get_chat_history(
    client_id: UUID,
    limit: int = 100,
    skip: int = 0,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> ChatHistoryResponse:
    user = user_service.get_or_create_user(db, current_user)
    _require_client(db, client_id, user.id)

    total = (
        db.query(ChatMessage)
        .filter(ChatMessage.client_id == client_id)
        .count()
    )
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.client_id == client_id)
        .order_by(ChatMessage.created_at.asc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    # Regenerate signed URLs for any page image sources in history
    validated_messages = []
    for m in messages:
        msg = ChatMessageResponse.model_validate(m)
        if msg.sources:
            for src in msg.sources:
                if src.image_path and not src.image_url:
                    try:
                        src.image_url = storage_service.get_signed_url(
                            src.image_path, expires_in=3600
                        )
                    except Exception:
                        pass  # non-fatal
        validated_messages.append(msg)

    return ChatHistoryResponse(
        messages=validated_messages,
        total=total,
        skip=skip,
        limit=limit,
    )


# ---------------------------------------------------------------------------
# Chat history — DELETE (clear all)
# ---------------------------------------------------------------------------


@router.delete(
    "/clients/{client_id}/chat-history",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Delete all chat messages for a client",
)
async def clear_chat_history(
    client_id: UUID,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> None:
    user = user_service.get_or_create_user(db, current_user)
    _require_client(db, client_id, user.id)

    db.query(ChatMessage).filter(ChatMessage.client_id == client_id).delete()
    db.commit()


# ---------------------------------------------------------------------------
# Chat history — Export as TXT or PDF
# ---------------------------------------------------------------------------


@router.get(
    "/clients/{client_id}/chat-history/export",
    summary="Export chat history as TXT or PDF",
)
async def export_chat_history(
    client_id: UUID,
    format: str = Query(..., description="Export format: 'txt' or 'pdf'"),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> StreamingResponse:
    user = user_service.get_or_create_user(db, current_user)
    client = _require_client(db, client_id, user.id)

    if format not in ("txt", "pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="format must be 'txt' or 'pdf'",
        )

    # Sanitize client name for use in filename
    safe_name = (
        "".join(c if c.isalnum() or c in " -_" else "" for c in client.name)
        .strip()
        .replace(" ", "-")[:50]
        or "client"
    )

    from app.services.chat_exporter import export_chat_as_pdf, export_chat_as_txt

    if format == "txt":
        content = export_chat_as_txt(client_id, client.name, db)
        return StreamingResponse(
            iter([content.encode("utf-8")]),
            media_type="text/plain; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="chat-history-{safe_name}.txt"'
            },
        )
    else:
        pdf_bytes = export_chat_as_pdf(client_id, client.name, db)
        return StreamingResponse(
            iter([pdf_bytes]),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="chat-history-{safe_name}.pdf"'
            },
        )

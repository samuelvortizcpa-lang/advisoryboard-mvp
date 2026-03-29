import asyncio
import logging
import os
import re
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from sqlalchemy import func as sa_func

from app.core.database import get_db
from app.models.client import Client
from app.models.document import Document
from app.models.document_page_image import DocumentPageImage
from app.schemas.document import DocumentListResponse, DocumentResponse
from app.services import document_service, rag_service, storage_service, user_service
from app.services.audit_service import log_action
from app.services.auth_context import AuthContext, check_client_access, get_auth
from app.services.notification_service import send_notification
from app.services.subscription_service import check_document_limit

logger = logging.getLogger(__name__)

router = APIRouter()


def _sanitize_filename(filename: str) -> str:
    """Sanitize a filename to prevent path traversal and other attacks."""
    # Remove path separators and null bytes
    filename = filename.replace("/", "").replace("\\", "").replace("\0", "")
    # Remove leading dots (hidden files)
    filename = filename.lstrip(".")
    # Remove control characters
    filename = re.sub(r"[\x00-\x1f\x7f]", "", filename)
    # Truncate to 255 chars preserving extension
    if len(filename) > 255:
        name, ext = os.path.splitext(filename)
        filename = name[: 255 - len(ext)] + ext
    return filename or "unnamed"


@router.post(
    "/clients/{client_id}/documents",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a document for a client",
)
async def upload_document(
    client_id: UUID,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> DocumentResponse:
    check_client_access(auth, client_id, db)

    # ── File validation ──────────────────────────────────────────────────
    ALLOWED_CONTENT_TYPES = {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
        "application/vnd.ms-outlook",
        "text/plain",
        "text/csv",
        "image/png",
        "image/jpeg",
        "image/tiff",
    }
    ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".msg", ".txt", ".csv", ".png", ".jpg", ".jpeg", ".tiff", ".tif"}
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB

    # Sanitize filename to prevent path traversal
    filename = _sanitize_filename(file.filename or "")
    file.filename = filename
    ext = ("." + filename.rsplit(".", 1)[-1]).lower() if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type '{ext}' is not supported. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    # Read file to check size (file is in memory anyway for upload)
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum size of {MAX_FILE_SIZE // (1024*1024)} MB.",
        )
    # Reset file position so save_document can read it
    await file.seek(0)

    limit_check = check_document_limit(db, auth.user_id, org_id=auth.org_id)
    if not limit_check["allowed"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Document limit reached. Upgrade your plan to upload more documents.",
        )
    # Duplicate check: same filename (case-insensitive) + same client
    existing = (
        db.query(Document.id)
        .filter(
            Document.client_id == client_id,
            sa_func.lower(Document.filename) == (file.filename or "").lower(),
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A document with this name already exists for this client. Please rename the file or delete the existing document first.",
        )

    # Resolve the local User row for uploaded_by (UUID FK)
    user = user_service.get_or_create_user(db, {"user_id": auth.user_id})

    document = await document_service.save_document(
        db=db,
        file=file,
        client_id=client_id,
        owner_id=user.id,
        uploaded_by=user.id,
        org_id=auth.org_id,
    )
    # Auto-process: kick off RAG embedding in a subprocess to avoid blocking the API
    from app.services.background_processor import run_in_process
    from app.core.config import get_settings
    asyncio.create_task(
        run_in_process(
            rag_service.process_document_sync,
            str(document.id),
            get_settings().database_url,
        )
    )

    # Slack notification (fire-and-forget)
    client_obj = db.query(Client).filter(Client.id == client_id).first()
    asyncio.create_task(send_notification(
        "document_upload",
        "New document uploaded",
        {"email": user.email or user.clerk_id, "filename": document.filename, "client": client_obj.name if client_obj else str(client_id)},
    ))

    log_action(db, auth, "document.upload", "document", document.id,
               detail={"client_id": str(client_id), "filename": document.filename},
               request=request)
    return document


@router.get(
    "/clients/{client_id}/documents",
    response_model=DocumentListResponse,
    summary="List documents for a client",
)
async def list_documents(
    client_id: UUID,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> DocumentListResponse:
    check_client_access(auth, client_id, db)
    documents, total = document_service.get_documents(
        db=db,
        client_id=client_id,
        org_id=auth.org_id,
        skip=skip,
        limit=limit,
    )
    return DocumentListResponse(items=documents, total=total, skip=skip, limit=limit)


@router.get(
    "/documents/{document_id}/download",
    summary="Download a document by ID",
)
async def download_document(
    document_id: UUID,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
):
    document = document_service.get_document(
        db, document_id=document_id, org_id=auth.org_id
    )
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )
    # Verify client access for the document's client
    check_client_access(auth, document.client_id, db)

    try:
        file_bytes = storage_service.download_file(document.file_path)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found in storage",
        )

    safe_filename = _sanitize_filename(document.filename or "download")
    # Escape quotes in filename for Content-Disposition header
    safe_filename = safe_filename.replace('"', '\\"')
    return Response(
        content=file_bytes,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_filename}"'
        },
    )


@router.delete(
    "/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a document",
)
async def delete_document(
    document_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> None:
    document = document_service.get_document(
        db, document_id=document_id, org_id=auth.org_id
    )
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )
    check_client_access(auth, document.client_id, db)

    deleted = document_service.delete_document(
        db, document_id=document_id, org_id=auth.org_id
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )
    log_action(db, auth, "document.delete", "document", document_id, request=request)


@router.post(
    "/documents/backfill-pages",
    summary="Backfill page images for PDFs missing them",
)
async def backfill_page_images(
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> dict:
    """
    Find all PDF documents in the user's org that have no rows in
    document_page_images and run page image processing on them.
    """
    from app.services.page_image_service import process_page_images

    # Find all processed PDF documents in this org
    pdf_docs = (
        db.query(Document)
        .join(Client, Document.client_id == Client.id)
        .filter(
            Client.org_id == auth.org_id,
            Document.file_type == "pdf",
            Document.processed == True,  # noqa: E712
        )
        .all()
    )

    processed = 0
    skipped = 0
    total_pages = 0

    for doc in pdf_docs:
        # Delete existing page images from Supabase Storage and DB
        existing_pages = (
            db.query(DocumentPageImage)
            .filter(DocumentPageImage.document_id == doc.id)
            .all()
        )
        if existing_pages:
            for page_img in existing_pages:
                if page_img.image_path:
                    storage_service.delete_file(page_img.image_path)
            db.query(DocumentPageImage).filter(
                DocumentPageImage.document_id == doc.id
            ).delete()
            db.commit()

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
            logger.warning(
                "Failed to process page images for document %s (%s)",
                doc.id, doc.filename, exc_info=True,
            )

    return {
        "processed": processed,
        "skipped": skipped,
        "total_pages": total_pages,
        "message": f"Reprocessed {processed} PDF(s), generated {total_pages} page images.",
    }

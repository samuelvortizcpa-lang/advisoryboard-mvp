from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from sqlalchemy import func as sa_func

from app.core.database import get_db
from app.models.client import Client
from app.models.document import Document
from app.models.document_page_image import DocumentPageImage
from app.schemas.document import DocumentListResponse, DocumentResponse
from app.services import document_service, rag_service, storage_service, user_service
from app.services.auth_context import AuthContext, check_client_access, get_auth
from app.services.notification_service import send_notification
from app.services.subscription_service import check_document_limit

router = APIRouter()


@router.post(
    "/clients/{client_id}/documents",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a document for a client",
)
async def upload_document(
    client_id: UUID,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> DocumentResponse:
    check_client_access(auth, client_id, db)

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
    # Auto-process: kick off RAG embedding in the background right after upload
    background_tasks.add_task(rag_service.process_document_task, document.id)

    # Slack notification (fire-and-forget)
    import asyncio
    client_obj = db.query(Client).filter(Client.id == client_id).first()
    asyncio.create_task(send_notification(
        "document_upload",
        "New document uploaded",
        {"email": user.email or user.clerk_id, "filename": document.filename, "client": client_obj.name if client_obj else str(client_id)},
    ))

    return document


@router.get(
    "/clients/{client_id}/documents",
    response_model=DocumentListResponse,
    summary="List documents for a client",
)
async def list_documents(
    client_id: UUID,
    skip: int = 0,
    limit: int = 50,
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

    return Response(
        content=file_bytes,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{document.filename}"'
        },
    )


@router.delete(
    "/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a document",
)
async def delete_document(
    document_id: UUID,
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
            pass  # logged inside process_page_images

    return {
        "processed": processed,
        "skipped": skipped,
        "total_pages": total_pages,
        "message": f"Reprocessed {processed} PDF(s), generated {total_pages} page images.",
    }

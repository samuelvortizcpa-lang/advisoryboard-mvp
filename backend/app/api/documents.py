from typing import Any, Dict
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from sqlalchemy import func as sa_func

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.client import Client
from app.models.document import Document
from app.schemas.document import DocumentListResponse, DocumentResponse
from app.services import document_service, rag_service, storage_service, user_service
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
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> DocumentResponse:
    user = user_service.get_or_create_user(db, current_user)
    limit_check = check_document_limit(db, user.clerk_id, user.id)
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
    document = await document_service.save_document(
        db=db,
        file=file,
        client_id=client_id,
        owner_id=user.id,
        uploaded_by=user.id,
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
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> DocumentListResponse:
    user = user_service.get_or_create_user(db, current_user)
    documents, total = document_service.get_documents(
        db=db,
        client_id=client_id,
        owner_id=user.id,
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
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    user = user_service.get_or_create_user(db, current_user)
    document = document_service.get_document(
        db, document_id=document_id, owner_id=user.id
    )
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )

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
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> None:
    user = user_service.get_or_create_user(db, current_user)
    deleted = document_service.delete_document(
        db, document_id=document_id, owner_id=user.id
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )

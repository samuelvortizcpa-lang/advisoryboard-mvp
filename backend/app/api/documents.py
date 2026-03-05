from pathlib import Path
from typing import Any, Dict
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.schemas.document import DocumentListResponse, DocumentResponse
from app.services import document_service, rag_service, storage_service, user_service

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
    document = await document_service.save_document(
        db=db,
        file=file,
        client_id=client_id,
        owner_id=user.id,
        uploaded_by=user.id,
    )
    # Auto-process: kick off RAG embedding in the background right after upload
    background_tasks.add_task(rag_service.process_document_task, document.id)
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

    # S3 mode: redirect the client to a short-lived presigned URL
    if storage_service.is_s3_enabled():
        presigned_url = storage_service.get_presigned_url(
            document.file_path,
            expires=3600,
            filename=document.filename,
        )
        return RedirectResponse(url=presigned_url, status_code=302)

    # Local mode: stream the file from disk
    file_path = Path(document.file_path)
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found on disk",
        )
    return FileResponse(
        path=str(file_path),
        filename=document.filename,
        media_type="application/octet-stream",
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

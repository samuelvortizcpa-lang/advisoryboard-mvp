"""
Document service: file storage + database operations.

Upload flow:
  1. Validate file extension and size.
  2. Verify the target client belongs to the requesting user.
  3. Upload bytes via storage_service (S3 or local filesystem).
  4. Insert a Document row.  If the DB insert fails, delete the file.

Storage:
  When S3 credentials are set (AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY +
  S3_BUCKET_NAME), files are stored in S3 and Document.file_path holds the
  S3 object key.  Otherwise files go to  uploads/  on local disk and
  Document.file_path holds the absolute path — so local dev works without
  any AWS configuration.

  Key / relative-path pattern:  {owner_id}/{client_id}/{uuid}_{filename}
"""

import uuid
from typing import Optional, Tuple
from uuid import UUID

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.document import Document
from app.services import storage_service

# ---------------------------------------------------------------------------
# File validation constants
# ---------------------------------------------------------------------------

ALLOWED_EXTENSIONS: frozenset[str] = frozenset(
    {"pdf", "docx", "doc", "xlsx", "xls", "pptx", "txt", "csv", "json",
     "mp4", "m4a", "mp3", "wav", "eml", "msg"}
)

# Audio/video files can be much larger because ffmpeg compresses before Whisper.
AUDIO_EXTENSIONS: frozenset[str] = frozenset({"mp4", "m4a", "mp3", "wav"})

MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024          # 50 MB  – documents
MAX_AUDIO_FILE_SIZE_BYTES = 500 * 1024 * 1024   # 500 MB – audio/video


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extension(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def _verify_client_ownership(
    db: Session, client_id: UUID, owner_id: UUID
) -> Client:
    client = (
        db.query(Client)
        .filter(Client.id == client_id, Client.owner_id == owner_id)
        .first()
    )
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Client not found"
        )
    return client


# ---------------------------------------------------------------------------
# Public service functions
# ---------------------------------------------------------------------------


async def save_document(
    db: Session,
    file: UploadFile,
    client_id: UUID,
    owner_id: UUID,
    uploaded_by: UUID,
) -> Document:
    """Validate, persist (S3 or local disk), and create a Document record."""
    original_name = file.filename or "untitled"

    # --- validation ---
    ext = _extension(original_name)
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"File type '.{ext}' is not allowed. "
                f"Allowed types: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
            ),
        )

    content = await file.read()
    file_size = len(content)

    if file_size == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    size_limit = MAX_AUDIO_FILE_SIZE_BYTES if ext in AUDIO_EXTENSIONS else MAX_FILE_SIZE_BYTES
    if file_size > size_limit:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the {size_limit // (1024 * 1024)} MB limit.",
        )

    # --- ownership check ---
    _verify_client_ownership(db, client_id, owner_id)

    # --- upload to storage (S3 or local filesystem) ---
    # Key pattern: {owner_id}/{client_id}/{uuid}_{filename}
    stored_name = f"{uuid.uuid4()}_{original_name}"
    storage_key = f"{owner_id}/{client_id}/{stored_name}"
    content_type = storage_service.content_type_for(original_name)

    # stored_ref is the S3 key (S3 mode) or absolute local path (local mode)
    stored_ref = storage_service.upload_file(content, storage_key, content_type)

    # --- insert DB record (roll back file on failure) ---
    try:
        document = Document(
            client_id=client_id,
            uploaded_by=uploaded_by,
            filename=original_name,
            file_path=stored_ref,   # S3 key or absolute local path
            file_type=ext,
            file_size=file_size,
        )
        db.add(document)
        db.commit()
        db.refresh(document)
    except Exception:
        storage_service.delete_file(stored_ref)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save document metadata.",
        )

    return document


def get_documents(
    db: Session,
    client_id: UUID,
    owner_id: UUID,
    skip: int = 0,
    limit: int = 50,
) -> Tuple[list[Document], int]:
    """Return a paginated list of documents for a client (ownership-scoped)."""
    _verify_client_ownership(db, client_id, owner_id)

    base = (
        db.query(Document)
        .filter(Document.client_id == client_id)
        .order_by(Document.upload_date.desc())
    )
    total = base.count()
    documents = base.offset(skip).limit(limit).all()
    return documents, total


def get_document(
    db: Session,
    document_id: UUID,
    owner_id: UUID,
) -> Optional[Document]:
    """Return a single document, verifying it belongs to a client owned by owner_id."""
    return (
        db.query(Document)
        .join(Client, Document.client_id == Client.id)
        .filter(Document.id == document_id, Client.owner_id == owner_id)
        .first()
    )


def delete_document(
    db: Session,
    document_id: UUID,
    owner_id: UUID,
) -> bool:
    """Delete the DB record and the stored file. Returns False if not found."""
    document = get_document(db, document_id, owner_id)
    if document is None:
        return False

    # Remove from storage first; a missing file is non-fatal.
    storage_service.delete_file(document.file_path)

    db.delete(document)
    db.commit()
    return True

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.action_item import ActionItem
    from app.models.client import Client
    from app.models.document_chunk import DocumentChunk
    from app.models.document_page_image import DocumentPageImage
    from app.models.user import User


class Document(Base):
    """
    A file uploaded for a client (PDF, DOCX, XLSX, etc.).

    After upload, a background job splits the file into DocumentChunk rows
    and generates embeddings for semantic search.  The `processed` flag and
    `processing_error` field track that pipeline.
    """

    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint(
            "client_id", "external_id",
            name="uq_documents_client_external_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Nullable so the row survives if the uploading user is deleted.
    uploaded_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # File metadata
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    file_type: Mapped[str] = mapped_column(String(50), nullable=False)   # e.g. "pdf", "docx"
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)      # bytes

    # Gmail integration — prevents duplicate ingestion of the same email
    gmail_message_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, unique=True, index=True
    )

    # Source tracking for multi-integration ingestion
    source: Mapped[str] = mapped_column(
        String(20), server_default="upload", nullable=False, index=True
    )  # 'upload', 'gmail', 'outlook', 'zoom'
    external_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )  # Gmail message ID, Zoom recording ID, etc.

    upload_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # RAG processing state
    processed: Mapped[bool] = mapped_column(
        Boolean,
        server_default="false",
        nullable=False,
    )
    processing_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Document intelligence — auto-classification
    document_type: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, index=True
    )
    document_subtype: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )
    document_period: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True
    )
    classification_confidence: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )

    # Amended return tracking
    amends_subtype: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )
    amendment_number: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )

    # Document versioning
    superseded_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_superseded: Mapped[bool] = mapped_column(
        Boolean, server_default="false", nullable=False, index=True
    )

    # -----------------------------------------------------------------------
    # Relationships
    # -----------------------------------------------------------------------

    client: Mapped["Client"] = relationship("Client", back_populates="documents")
    uploader: Mapped[Optional["User"]] = relationship(
        "User",
        back_populates="documents_uploaded",
        foreign_keys=[uploaded_by],
    )
    chunks: Mapped[List["DocumentChunk"]] = relationship(
        "DocumentChunk",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentChunk.chunk_index",
    )
    action_items: Mapped[List["ActionItem"]] = relationship(
        "ActionItem",
        back_populates="document",
        cascade="all, delete-orphan",
    )
    page_images: Mapped[List["DocumentPageImage"]] = relationship(
        "DocumentPageImage",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentPageImage.page_number",
    )

    def __repr__(self) -> str:
        return (
            f"<Document id={self.id} filename={self.filename!r} "
            f"processed={self.processed}>"
        )

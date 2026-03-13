"""
DocumentPageImage model: stores page-level JPEG snapshots of PDF documents
along with their Gemini multimodal embeddings for visual retrieval.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.document import Document

# Gemini embedding dimension (gemini-embedding-exp-03-07 outputs 768 dims)
IMAGE_EMBEDDING_DIM = 768


class DocumentPageImage(Base):
    """
    A single page image extracted from a PDF document.

    Each row stores:
    - The Supabase Storage path to the JPEG image
    - A 768-dim Gemini embedding of the page image for visual similarity search
    """

    __tablename__ = "document_page_images"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    page_number: Mapped[int] = mapped_column(Integer, nullable=False)

    # Supabase Storage path, e.g. "page_images/{doc_id}/page_1.jpg"
    image_path: Mapped[str] = mapped_column(Text, nullable=False)

    # 768-dim Gemini multimodal embedding (NULL until embedded)
    image_embedding: Mapped[Optional[list[float]]] = mapped_column(
        Vector(IMAGE_EMBEDDING_DIM),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # ── Relationships ──────────────────────────────────────────────────────────

    document: Mapped["Document"] = relationship(
        "Document", back_populates="page_images",
    )

    def __repr__(self) -> str:
        return (
            f"<DocumentPageImage id={self.id} document_id={self.document_id} "
            f"page={self.page_number}>"
        )

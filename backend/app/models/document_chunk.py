import uuid
from typing import TYPE_CHECKING, Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.client import Client
    from app.models.document import Document

# Dimensionality used by OpenAI text-embedding-3-small (1536) and
# text-embedding-ada-002 (1536).  Change to 3072 for text-embedding-3-large.
EMBEDDING_DIM = 1536


class DocumentChunk(Base):
    """
    A contiguous slice of text extracted from a Document, with its embedding.

    The embedding column uses pgvector so similarity searches can be expressed
    as simple SQL ORDER BY queries (cosine distance, L2, inner product).

    Example nearest-neighbour query:
        db.query(DocumentChunk)
          .filter(DocumentChunk.client_id == client_id)
          .order_by(DocumentChunk.embedding.cosine_distance(query_vector))
          .limit(5)
          .all()
    """

    __tablename__ = "document_chunks"

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
    # Denormalised for efficient per-client similarity searches without
    # requiring a JOIN through documents every time.
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)

    # Populated by the embedding pipeline after upload.
    # None until the document has been processed.
    embedding: Mapped[Optional[list]] = mapped_column(
        Vector(EMBEDDING_DIM),
        nullable=True,
    )

    # Full-text search vector, auto-populated by a DB trigger on chunk_text.
    search_vector: Mapped[Optional[str]] = mapped_column(
        TSVECTOR,
        nullable=True,
    )

    # -----------------------------------------------------------------------
    # Relationships
    # -----------------------------------------------------------------------

    document: Mapped["Document"] = relationship(
        "Document",
        back_populates="chunks",
    )
    client: Mapped["Client"] = relationship("Client")

    def __repr__(self) -> str:
        has_embedding = self.embedding is not None
        return (
            f"<DocumentChunk id={self.id} doc={self.document_id} "
            f"index={self.chunk_index} embedded={has_embedding}>"
        )

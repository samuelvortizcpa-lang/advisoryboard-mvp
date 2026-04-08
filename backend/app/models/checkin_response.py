import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.document_chunk import EMBEDDING_DIM

if TYPE_CHECKING:
    from app.models.checkin_template import CheckinTemplate
    from app.models.client import Client


class CheckinResponse(Base):
    """
    A single check-in sent to a client, tracking its lifecycle from
    pending → completed/expired.

    The response_embedding column stores the pgvector embedding of the
    flattened response_text so it can be surfaced by the AI context assembler
    via cosine-similarity search.
    """

    __tablename__ = "checkin_responses"

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

    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("checkin_templates.id"),
        nullable=False,
        index=True,
    )

    sent_by: Mapped[str] = mapped_column(String(255), nullable=False)
    sent_to_email: Mapped[str] = mapped_column(String(255), nullable=False)
    sent_to_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    access_token: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
    )

    # Array of {question_id: str, answer: any}
    responses: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)

    # Flattened Q&A text for RAG embedding
    response_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # pgvector embedding of response_text
    response_embedding: Mapped[Optional[list]] = mapped_column(
        Vector(EMBEDDING_DIM),
        nullable=True,
    )

    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # ── Relationships ─────────────────────────────────────────────────

    client: Mapped["Client"] = relationship("Client")
    template: Mapped["CheckinTemplate"] = relationship(
        "CheckinTemplate",
        back_populates="responses",
    )

    def __repr__(self) -> str:
        return (
            f"<CheckinResponse id={self.id} client={self.client_id} "
            f"status={self.status}>"
        )

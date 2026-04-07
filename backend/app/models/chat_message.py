import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

try:
    from pgvector.sqlalchemy import Vector
except ImportError:  # pragma: no cover – pgvector optional in dev
    Vector = None

if TYPE_CHECKING:
    from app.models.chat_session import ChatSession
    from app.models.client import Client


class ChatMessage(Base):
    """
    A persisted chat message (user question or AI assistant answer).

    Messages are stored in chronological order (created_at ASC) and linked
    to the client they were asked about.  The sources field (JSONB) holds the
    list of document excerpts that backed the AI answer.
    """

    __tablename__ = "chat_messages"

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

    # Clerk user ID of the person who asked the question
    user_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # 'user' | 'assistant'
    role: Mapped[str] = mapped_column(String(20), nullable=False)

    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Array of source dicts: [{"document_id": "...", "filename": "...", "preview": "..."}]
    sources: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Session memory fields
    session_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )

    pair_embedding: Mapped[Optional[Any]] = mapped_column(
        Vector(1536) if Vector else None,
        nullable=True,
    )

    pair_index: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # -----------------------------------------------------------------------
    # Relationships
    # -----------------------------------------------------------------------

    client: Mapped["Client"] = relationship("Client", back_populates="chat_messages")
    session: Mapped[Optional["ChatSession"]] = relationship(
        "ChatSession", back_populates="messages"
    )

    def __repr__(self) -> str:
        return (
            f"<ChatMessage id={self.id} role={self.role!r} "
            f"client_id={self.client_id}>"
        )

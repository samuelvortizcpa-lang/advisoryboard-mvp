import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, List, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

try:
    from pgvector.sqlalchemy import Vector
except ImportError:  # pragma: no cover – pgvector optional in dev
    Vector = None

if TYPE_CHECKING:
    from app.models.chat_message import ChatMessage
    from app.models.client import Client


SUMMARY_EMBEDDING_DIM = 1536


class ChatSession(Base):
    """
    A time-bounded group of chat messages for a single client.

    Sessions are created by detecting 30-minute inactivity gaps between
    consecutive messages.  Each session stores an AI-generated summary
    and its vector embedding for semantic search over past conversations.
    """

    __tablename__ = "chat_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )

    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
    )

    user_id: Mapped[str] = mapped_column(String(255), nullable=False)

    org_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
    )

    title: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    summary_embedding: Mapped[Optional[Any]] = mapped_column(
        Vector(SUMMARY_EMBEDDING_DIM) if Vector else None,
        nullable=True,
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    ended_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    message_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=func.cast(0, Integer)
    )

    key_topics: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)

    key_decisions: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=func.cast(True, Boolean)
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # -----------------------------------------------------------------------
    # Relationships
    # -----------------------------------------------------------------------

    client: Mapped["Client"] = relationship("Client", back_populates="chat_sessions")

    messages: Mapped[List["ChatMessage"]] = relationship(
        "ChatMessage", back_populates="session", order_by="ChatMessage.created_at"
    )

    def __repr__(self) -> str:
        return (
            f"<ChatSession id={self.id} client_id={self.client_id} "
            f"messages={self.message_count}>"
        )

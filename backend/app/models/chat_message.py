import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
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

    # -----------------------------------------------------------------------
    # Relationships
    # -----------------------------------------------------------------------

    client: Mapped["Client"] = relationship("Client", back_populates="chat_messages")

    def __repr__(self) -> str:
        return (
            f"<ChatMessage id={self.id} role={self.role!r} "
            f"client_id={self.client_id}>"
        )

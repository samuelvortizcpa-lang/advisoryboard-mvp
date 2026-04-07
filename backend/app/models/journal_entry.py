import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.client import Client


class JournalEntry(Base):
    """
    A chronological journal entry for a client — manual notes, life events,
    financial changes, strategy updates, document insights, or system events.
    """

    __tablename__ = "client_journal_entries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
    )

    user_id: Mapped[str] = mapped_column(String(255), nullable=False)

    entry_type: Mapped[str] = mapped_column(
        String(30), nullable=False,
    )  # manual, financial_change, life_event, strategy_change, communication, document_insight, system

    category: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True,
    )  # income, deductions, family, property, employment, business, investment, compliance, general

    title: Mapped[str] = mapped_column(String(200), nullable=False)

    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    effective_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    source_type: Mapped[Optional[str]] = mapped_column(
        String(30), nullable=True,
    )  # document, email, chat, manual, system

    source_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True,
    )

    metadata_: Mapped[Optional[dict[str, Any]]] = mapped_column(
        "metadata", JSONB, nullable=True,
    )

    is_pinned: Mapped[bool] = mapped_column(
        Boolean, server_default="false", nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # ── Relationships ──────────────────────────────────────────────────────

    client: Mapped["Client"] = relationship("Client")

    def __repr__(self) -> str:
        return (
            f"<JournalEntry {self.entry_type}: {self.title!r} "
            f"client={self.client_id}>"
        )

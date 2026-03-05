import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.client import Client
    from app.models.document import Document


class ActionItem(Base):
    """
    An action item extracted from a client document.

    Extracted automatically by GPT-4o-mini during document processing.
    Status lifecycle: pending → completed | cancelled
    """

    __tablename__ = "action_items"

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
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    text: Mapped[str] = mapped_column(Text, nullable=False)

    # 'pending' | 'completed' | 'cancelled'
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="pending",
    )
    # 'low' | 'medium' | 'high' | None
    priority: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)

    due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    extracted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
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

    document: Mapped["Document"] = relationship(
        "Document",
        back_populates="action_items",
    )
    client: Mapped["Client"] = relationship(
        "Client",
        back_populates="action_items",
    )

    def __repr__(self) -> str:
        return (
            f"<ActionItem id={self.id} status={self.status!r} "
            f"text={self.text[:40]!r}>"
        )

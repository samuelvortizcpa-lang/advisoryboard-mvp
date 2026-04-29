import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.client import Client
    from app.models.client_strategy_status import ClientStrategyStatus
    from app.models.document import Document
    from app.models.engagement_template_task import EngagementTemplateTask
    from app.models.strategy_implementation_task import StrategyImplementationTask


class ActionItem(Base):
    """
    An action item — either AI-extracted from a document or manually created.

    Source: 'ai_extracted' (from document processing) or 'manual' (user-created).
    Status lifecycle: pending → completed | cancelled
    """

    __tablename__ = "action_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    document_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=True,
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

    # Assignment fields
    assigned_to: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    assigned_to_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Provenance
    created_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    source: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default="ai_extracted"
    )

    engagement_task_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("engagement_template_tasks.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Strategy implementation linkage
    strategy_implementation_task_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("strategy_implementation_tasks.id"),
        nullable=True,
        index=True,
    )
    client_strategy_status_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("client_strategy_status.id"),
        nullable=True,
        index=True,
    )
    owner_role: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="cpa"
    )
    owner_external_label: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True
    )

    extracted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=True,
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

    document: Mapped[Optional["Document"]] = relationship(
        "Document",
        back_populates="action_items",
    )
    client: Mapped["Client"] = relationship(
        "Client",
        back_populates="action_items",
    )
    engagement_task: Mapped[Optional["EngagementTemplateTask"]] = relationship(
        "EngagementTemplateTask",
    )
    strategy_implementation_task: Mapped[Optional["StrategyImplementationTask"]] = relationship(
        "StrategyImplementationTask",
    )
    client_strategy_status: Mapped[Optional["ClientStrategyStatus"]] = relationship(
        "ClientStrategyStatus",
    )

    def __repr__(self) -> str:
        return (
            f"<ActionItem id={self.id} status={self.status!r} "
            f"text={self.text[:40]!r}>"
        )

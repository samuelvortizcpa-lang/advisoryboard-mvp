import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, Integer, String, Text, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.tax_strategy import TaxStrategy


class StrategyImplementationTask(Base):
    """A template task that is auto-created when a strategy status becomes 'recommended'."""

    __tablename__ = "strategy_implementation_tasks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    strategy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tax_strategies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    task_name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    default_owner_role: Mapped[str] = mapped_column(String(20), nullable=False)
    default_owner_external_label: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True
    )
    default_lead_days: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    required_documents: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default="'[]'::jsonb"
    )
    display_order: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    strategy: Mapped["TaxStrategy"] = relationship(
        "TaxStrategy", back_populates="implementation_tasks"
    )

    def __repr__(self) -> str:
        return (
            f"<StrategyImplementationTask id={self.id} "
            f"task_name={self.task_name!r} strategy_id={self.strategy_id}>"
        )

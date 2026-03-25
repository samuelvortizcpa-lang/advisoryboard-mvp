import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.client import Client
    from app.models.tax_strategy import TaxStrategy


class ClientStrategyStatus(Base):
    """Tracks the status of a tax strategy for a specific client and tax year."""

    __tablename__ = "client_strategy_status"
    __table_args__ = (
        {"comment": "Per-client, per-year status of each tax strategy"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    strategy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tax_strategies.id"),
        nullable=False,
        index=True,
    )
    tax_year: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="not_reviewed"
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    estimated_impact: Mapped[Optional[float]] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    updated_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    client: Mapped["Client"] = relationship("Client", foreign_keys=[client_id])
    strategy: Mapped["TaxStrategy"] = relationship("TaxStrategy", foreign_keys=[strategy_id])

    def __repr__(self) -> str:
        return (
            f"<ClientStrategyStatus id={self.id} client_id={self.client_id} "
            f"strategy_id={self.strategy_id} year={self.tax_year} status={self.status!r}>"
        )

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.client import Client


class DataContradiction(Base):
    """
    A detected contradiction between data sources for a client — e.g. mismatched
    income figures across documents, inconsistent filing status over time, or
    conflicting answers in advisory sessions.
    """

    __tablename__ = "data_contradictions"

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

    # metric_mismatch | cross_document | temporal_inconsistency | session_conflict
    contradiction_type: Mapped[str] = mapped_column(String(30), nullable=False)

    # high | medium | low
    severity: Mapped[str] = mapped_column(String(10), nullable=False)

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    field_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    value_a: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    value_b: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)

    # Source A
    source_a_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    source_a_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    source_a_label: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    # Source B
    source_b_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    source_b_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    source_b_label: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    tax_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="open",
    )

    resolved_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    resolution_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # ── Relationships ──────────────────────────────────────────────────────

    client: Mapped["Client"] = relationship("Client")

    # ── Table args (indexes) ───────────────────────────────────────────────

    __table_args__ = (
        Index("ix_data_contradictions_client_status", "client_id", "status"),
        Index("ix_data_contradictions_client_tax_year", "client_id", "tax_year"),
        Index("ix_data_contradictions_severity", "severity"),
    )

    def __repr__(self) -> str:
        return (
            f"<DataContradiction id={self.id} type={self.contradiction_type!r} "
            f"severity={self.severity!r} status={self.status!r}>"
        )

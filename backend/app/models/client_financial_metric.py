import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.client import Client
    from app.models.document import Document


class ClientFinancialMetric(Base):
    """
    A single financial data point extracted from a client document.

    Examples: AGI from a 1040 (Line 11), Schedule C net income (Line 31),
    W-2 wages (Box 1).  Grouped by tax_year and metric_category for
    year-over-year trend analysis.
    """

    __tablename__ = "client_financial_metrics"
    __table_args__ = (
        UniqueConstraint(
            "client_id", "tax_year", "metric_name", "form_source",
            name="uq_client_financial_metric",
        ),
    )

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

    document_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )

    tax_year: Mapped[int] = mapped_column(Integer, nullable=False)

    metric_category: Mapped[str] = mapped_column(
        String(50), nullable=False,
    )  # income, deductions, credits, tax, payments, assets, liabilities

    metric_name: Mapped[str] = mapped_column(
        String(100), nullable=False,
    )  # agi, total_income, schedule_c_net, w2_wages, estimated_payments_q1, ...

    metric_value: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(15, 2), nullable=True,
    )

    form_source: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True,
    )  # 1040, Schedule C, Schedule E, 1120-S, ...

    line_reference: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True,
    )  # "Line 11", "Box 1", ...

    is_amended: Mapped[bool] = mapped_column(
        Boolean, server_default="false", nullable=False,
    )

    extracted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    confidence: Mapped[Decimal] = mapped_column(
        Numeric(3, 2),
        server_default="1.00",
        nullable=False,
    )

    # ── Relationships ──────────────────────────────────────────────────────

    client: Mapped["Client"] = relationship("Client")
    document: Mapped[Optional["Document"]] = relationship("Document")

    def __repr__(self) -> str:
        return (
            f"<ClientFinancialMetric {self.metric_name}={self.metric_value} "
            f"year={self.tax_year} source={self.form_source}>"
        )

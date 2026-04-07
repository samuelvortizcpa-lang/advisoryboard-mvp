from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class FinancialMetric(BaseModel):
    """A single extracted financial data point."""

    id: UUID
    client_id: UUID
    document_id: Optional[UUID] = None
    tax_year: int
    metric_category: str
    metric_name: str
    metric_value: Optional[Decimal] = None
    form_source: Optional[str] = None
    line_reference: Optional[str] = None
    is_amended: bool = False
    extracted_at: datetime
    confidence: Decimal

    model_config = {"from_attributes": True}


class FinancialMetricsByYear(BaseModel):
    """Financial metrics grouped by tax year."""

    tax_year: int
    metrics: list[FinancialMetric]
    metric_count: int


class FinancialTrend(BaseModel):
    """A single metric tracked across multiple years for trend display."""

    metric_name: str
    metric_category: str
    form_source: Optional[str] = None
    line_reference: Optional[str] = None
    values: dict[int, Optional[Decimal]]  # tax_year → value


class AmendmentInfo(BaseModel):
    """Amendment history for a single tax year."""

    tax_year: int
    amended_metric_count: int


class FinancialSummary(BaseModel):
    """Top-level financial overview for a client."""

    client_id: UUID
    years_available: list[int]
    metrics_by_year: list[FinancialMetricsByYear]
    key_trends: list[FinancialTrend]
    amendment_history: list[AmendmentInfo] = []


class ReextractResponse(BaseModel):
    """Result of a bulk re-extraction run."""

    documents_processed: int
    metrics_extracted: int

"""Financial metrics API — access extracted financial data for clients."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import distinct, func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.client_financial_metric import ClientFinancialMetric
from app.models.document import Document
from app.schemas.financial import (
    AmendmentInfo,
    FinancialMetric,
    FinancialMetricsByYear,
    FinancialSummary,
    FinancialTrend,
    ReextractResponse,
)
from app.services.auth_context import AuthContext, check_client_access, get_auth

logger = logging.getLogger(__name__)

router = APIRouter()

# Key metrics shown in the summary endpoint
_KEY_METRIC_NAMES = {"agi", "total_income", "total_tax"}


# ---------------------------------------------------------------------------
# 1. GET /clients/{client_id}/financials
# ---------------------------------------------------------------------------


@router.get(
    "/clients/{client_id}/financials",
    response_model=list[FinancialMetricsByYear],
    summary="List financial metrics grouped by tax year",
)
async def list_financials(
    client_id: UUID,
    year: Optional[int] = Query(None, description="Filter to a single tax year"),
    category: Optional[str] = Query(None, description="Filter by metric_category"),
    include_amended: bool = Query(True, description="Include amended metrics"),
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> list[FinancialMetricsByYear]:
    check_client_access(auth, client_id, db)

    q = db.query(ClientFinancialMetric).filter(
        ClientFinancialMetric.client_id == client_id,
    )
    if year is not None:
        q = q.filter(ClientFinancialMetric.tax_year == year)
    if category:
        q = q.filter(ClientFinancialMetric.metric_category == category)
    if not include_amended:
        q = q.filter(ClientFinancialMetric.is_amended == False)  # noqa: E712

    rows = q.order_by(
        ClientFinancialMetric.tax_year.desc(),
        ClientFinancialMetric.metric_category,
        ClientFinancialMetric.metric_name,
    ).all()

    by_year: dict[int, list[ClientFinancialMetric]] = defaultdict(list)
    for row in rows:
        by_year[row.tax_year].append(row)

    return [
        FinancialMetricsByYear(
            tax_year=yr,
            metrics=[FinancialMetric.model_validate(m) for m in metrics],
            metric_count=len(metrics),
        )
        for yr, metrics in sorted(by_year.items(), reverse=True)
    ]


# ---------------------------------------------------------------------------
# 2. GET /clients/{client_id}/financials/trends
# ---------------------------------------------------------------------------


@router.get(
    "/clients/{client_id}/financials/trends",
    response_model=list[FinancialTrend],
    summary="Year-over-year trends for selected metrics",
)
async def get_trends(
    client_id: UUID,
    metrics: str = Query(
        "agi,total_tax,total_income",
        description="Comma-separated metric names",
    ),
    years: int = Query(5, ge=1, le=20, description="Number of recent years"),
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> list[FinancialTrend]:
    check_client_access(auth, client_id, db)

    metric_names = [m.strip() for m in metrics.split(",") if m.strip()]

    # Determine year range from available data
    max_year_row = (
        db.query(func.max(ClientFinancialMetric.tax_year))
        .filter(ClientFinancialMetric.client_id == client_id)
        .scalar()
    )
    if max_year_row is None:
        return []

    min_year = max_year_row - years + 1

    rows = (
        db.query(ClientFinancialMetric)
        .filter(
            ClientFinancialMetric.client_id == client_id,
            ClientFinancialMetric.metric_name.in_(metric_names),
            ClientFinancialMetric.tax_year >= min_year,
        )
        .all()
    )

    # Build trend objects
    trend_data: dict[str, dict[str, object]] = {}
    for row in rows:
        key = row.metric_name
        if key not in trend_data:
            trend_data[key] = {
                "metric_name": row.metric_name,
                "metric_category": row.metric_category,
                "form_source": row.form_source,
                "line_reference": row.line_reference,
                "values": {},
            }
        trend_data[key]["values"][row.tax_year] = row.metric_value  # type: ignore[index]

    # Preserve the order the caller requested
    result: list[FinancialTrend] = []
    for name in metric_names:
        if name in trend_data:
            result.append(FinancialTrend(**trend_data[name]))  # type: ignore[arg-type]

    return result


# ---------------------------------------------------------------------------
# 3. GET /clients/{client_id}/financials/summary
# ---------------------------------------------------------------------------


@router.get(
    "/clients/{client_id}/financials/summary",
    response_model=FinancialSummary,
    summary="Quick financial overview for a client",
)
async def get_summary(
    client_id: UUID,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> FinancialSummary:
    check_client_access(auth, client_id, db)

    # All metrics for this client
    all_rows = (
        db.query(ClientFinancialMetric)
        .filter(ClientFinancialMetric.client_id == client_id)
        .order_by(
            ClientFinancialMetric.tax_year.desc(),
            ClientFinancialMetric.metric_name,
        )
        .all()
    )

    # Years available
    years_set: set[int] = set()
    by_year: dict[int, list[ClientFinancialMetric]] = defaultdict(list)
    for row in all_rows:
        years_set.add(row.tax_year)
        by_year[row.tax_year].append(row)

    years_available = sorted(years_set, reverse=True)

    # Key metrics by year (only key metrics)
    metrics_by_year: list[FinancialMetricsByYear] = []
    for yr in years_available:
        key_metrics = [
            m for m in by_year[yr] if m.metric_name in _KEY_METRIC_NAMES
        ]
        if key_metrics:
            metrics_by_year.append(
                FinancialMetricsByYear(
                    tax_year=yr,
                    metrics=[FinancialMetric.model_validate(m) for m in key_metrics],
                    metric_count=len(key_metrics),
                )
            )

    # Key trends
    key_trends: list[FinancialTrend] = []
    for name in sorted(_KEY_METRIC_NAMES):
        values: dict[int, object] = {}
        category = ""
        form_source = None
        line_ref = None
        for yr in years_available:
            for m in by_year[yr]:
                if m.metric_name == name:
                    values[yr] = m.metric_value
                    category = m.metric_category
                    form_source = form_source or m.form_source
                    line_ref = line_ref or m.line_reference
                    break
        if values:
            key_trends.append(
                FinancialTrend(
                    metric_name=name,
                    metric_category=category,
                    form_source=form_source,
                    line_reference=line_ref,
                    values=values,  # type: ignore[arg-type]
                )
            )

    # Amendment history
    amendment_history: list[AmendmentInfo] = []
    for yr in years_available:
        amended_count = sum(1 for m in by_year[yr] if m.is_amended)
        if amended_count > 0:
            amendment_history.append(
                AmendmentInfo(tax_year=yr, amended_metric_count=amended_count)
            )

    return FinancialSummary(
        client_id=client_id,
        years_available=years_available,
        metrics_by_year=metrics_by_year,
        key_trends=key_trends,
        amendment_history=amendment_history,
    )


# ---------------------------------------------------------------------------
# 4. POST /clients/{client_id}/financials/reextract
# ---------------------------------------------------------------------------


@router.post(
    "/clients/{client_id}/financials/reextract",
    response_model=ReextractResponse,
    summary="Re-run financial extraction on all applicable documents",
)
async def reextract_financials(
    client_id: UUID,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> ReextractResponse:
    check_client_access(auth, client_id, db)

    from app.services.financial_extraction_service import extract_financial_metrics

    # Find all classified tax returns and financial statements
    docs = (
        db.query(Document)
        .filter(
            Document.client_id == client_id,
            Document.processed == True,  # noqa: E712
            Document.document_type.in_(["tax_return", "financial_statement"]),
        )
        .order_by(Document.upload_date.asc())
        .all()
    )

    total_metrics = 0
    docs_processed = 0

    for doc in docs:
        try:
            metrics = await extract_financial_metrics(db, doc.id, client_id)
            total_metrics += len(metrics)
            docs_processed += 1
        except Exception:
            logger.warning(
                "Reextract: failed for document %s (skipping)", doc.id, exc_info=True,
            )

    return ReextractResponse(
        documents_processed=docs_processed,
        metrics_extracted=total_metrics,
    )

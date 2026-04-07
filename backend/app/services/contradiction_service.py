"""
Contradiction Detection Engine.

Detects data inconsistencies across documents, financial metrics, and
advisory sessions for a client.  Results are stored in data_contradictions
and surfaced as alerts.

Detection types:
- metric_mismatch:          same metric, same year, different form sources disagree
- temporal_inconsistency:   year-over-year change exceeds threshold with no journal explanation
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.client_financial_metric import ClientFinancialMetric
from app.models.data_contradiction import DataContradiction
from app.models.journal_entry import JournalEntry

logger = logging.getLogger(__name__)

# Metric value difference threshold — ignore rounding noise
_MIN_DIFF = Decimal("100.00")


# ---------------------------------------------------------------------------
# 1. Metric contradictions (cross-source for same year)
# ---------------------------------------------------------------------------


def check_metric_contradictions(
    client_id: UUID,
    user_id: str,
    tax_year: int,
    new_metrics: list[dict[str, Any]],
    db: Session,
) -> list[DataContradiction]:
    """Compare newly extracted metrics against existing ones for the same
    client and tax year.  Creates contradiction records when values diverge
    by more than $100.

    ``new_metrics`` is the raw list of dicts from financial extraction, each
    containing at least ``metric_name``, ``metric_value``, and ``form_source``.
    """
    created: list[DataContradiction] = []

    for entry in new_metrics:
        metric_name = entry.get("metric_name")
        raw_value = entry.get("metric_value")
        new_source = entry.get("form_source", "")

        if not metric_name or raw_value is None:
            continue

        try:
            new_value = Decimal(str(raw_value))
        except Exception:
            continue

        # Find existing metrics with the same name + year but different source
        existing = (
            db.query(ClientFinancialMetric)
            .filter(
                ClientFinancialMetric.client_id == client_id,
                ClientFinancialMetric.tax_year == tax_year,
                ClientFinancialMetric.metric_name == metric_name,
                ClientFinancialMetric.form_source != new_source,
                ClientFinancialMetric.metric_value.isnot(None),
            )
            .all()
        )

        for existing_metric in existing:
            old_value = existing_metric.metric_value
            if old_value is None:
                continue

            diff = abs(new_value - old_value)
            if diff <= _MIN_DIFF:
                continue

            severity = _severity_from_diff(diff, old_value)

            # Dedup: skip if an open contradiction already exists for this field + year
            dup = (
                db.query(DataContradiction.id)
                .filter(
                    DataContradiction.client_id == client_id,
                    DataContradiction.field_name == metric_name,
                    DataContradiction.tax_year == tax_year,
                    DataContradiction.status == "open",
                )
                .first()
            )
            if dup:
                continue

            label = metric_name.replace("_", " ").title()
            title = (
                f"{label} discrepancy: {existing_metric.form_source} "
                f"(${old_value:,.2f}) vs {new_source} (${new_value:,.2f})"
            )
            if len(title) > 200:
                title = title[:197] + "..."

            contradiction = DataContradiction(
                client_id=client_id,
                user_id=user_id,
                contradiction_type="metric_mismatch",
                severity=severity,
                title=title,
                description=(
                    f"The metric '{label}' for tax year {tax_year} shows different "
                    f"values across document sources. "
                    f"{existing_metric.form_source} reports ${old_value:,.2f} "
                    f"while {new_source} reports ${new_value:,.2f} "
                    f"(difference: ${diff:,.2f})."
                ),
                field_name=metric_name,
                value_a=old_value,
                value_b=new_value,
                source_a_type="document",
                source_a_id=existing_metric.document_id,
                source_a_label=existing_metric.form_source,
                source_b_type="document",
                source_b_label=new_source,
                tax_year=tax_year,
            )
            db.add(contradiction)
            created.append(contradiction)

    if created:
        db.flush()
        logger.info(
            "Metric contradictions: %d new for client %s, year %d",
            len(created), client_id, tax_year,
        )

    return created


# ---------------------------------------------------------------------------
# 2. Year-over-year anomaly detection
# ---------------------------------------------------------------------------


def check_yoy_anomalies(
    client_id: UUID,
    user_id: str,
    db: Session,
) -> list[DataContradiction]:
    """Detect year-over-year metric changes that exceed thresholds and
    have no journal entry explaining the change."""
    created: list[DataContradiction] = []

    # Load all metrics grouped by (metric_name, tax_year)
    all_metrics = (
        db.query(ClientFinancialMetric)
        .filter(
            ClientFinancialMetric.client_id == client_id,
            ClientFinancialMetric.metric_value.isnot(None),
        )
        .order_by(
            ClientFinancialMetric.metric_name,
            ClientFinancialMetric.tax_year,
        )
        .all()
    )

    if not all_metrics:
        return created

    # Build lookup: metric_name -> sorted list of (year, value, form_source)
    by_name: dict[str, list[tuple[int, Decimal, str | None]]] = {}
    for m in all_metrics:
        by_name.setdefault(m.metric_name, []).append(
            (m.tax_year, m.metric_value, m.form_source)  # type: ignore[arg-type]
        )

    for metric_name, year_values in by_name.items():
        # Deduplicate by year — take the first source per year
        seen_years: dict[int, tuple[Decimal, str | None]] = {}
        for year, value, source in year_values:
            if year not in seen_years:
                seen_years[year] = (value, source)

        sorted_years = sorted(seen_years.keys())
        for i in range(1, len(sorted_years)):
            year_a = sorted_years[i - 1]
            year_b = sorted_years[i]

            # Only compare consecutive years
            if year_b - year_a != 1:
                continue

            val_a, source_a = seen_years[year_a]
            val_b, source_b = seen_years[year_b]

            if val_a == 0:
                continue

            pct_change = float(abs(val_b - val_a) / abs(val_a) * 100)
            if pct_change < 25:
                continue

            severity = "high" if pct_change > 50 else "medium"

            # Check if a journal entry explains this change
            if _journal_explains_change(db, client_id, year_b, metric_name):
                continue

            # Dedup check
            dup = (
                db.query(DataContradiction.id)
                .filter(
                    DataContradiction.client_id == client_id,
                    DataContradiction.field_name == metric_name,
                    DataContradiction.tax_year == year_b,
                    DataContradiction.contradiction_type == "temporal_inconsistency",
                    DataContradiction.status == "open",
                )
                .first()
            )
            if dup:
                continue

            label = metric_name.replace("_", " ").title()
            title = (
                f"{label} changed {pct_change:.0f}% from {year_a} to {year_b} "
                f"(${val_a:,.2f} → ${val_b:,.2f})"
            )
            if len(title) > 200:
                title = title[:197] + "..."

            contradiction = DataContradiction(
                client_id=client_id,
                user_id=user_id,
                contradiction_type="temporal_inconsistency",
                severity=severity,
                title=title,
                description=(
                    f"The metric '{label}' changed by {pct_change:.1f}% between "
                    f"tax year {year_a} (${val_a:,.2f}) and {year_b} (${val_b:,.2f}). "
                    f"No journal entry was found explaining this change."
                ),
                field_name=metric_name,
                value_a=val_a,
                value_b=val_b,
                source_a_type="metric",
                source_a_label=f"{source_a or 'unknown'} ({year_a})",
                source_b_type="metric",
                source_b_label=f"{source_b or 'unknown'} ({year_b})",
                tax_year=year_b,
            )
            db.add(contradiction)
            created.append(contradiction)

    if created:
        db.flush()
        logger.info(
            "YoY anomalies: %d new for client %s", len(created), client_id,
        )

    return created


# ---------------------------------------------------------------------------
# 3. Full scan
# ---------------------------------------------------------------------------


def run_full_scan(
    client_id: UUID,
    user_id: str,
    db: Session,
) -> dict[str, Any]:
    """Run all contradiction checks for a client and return a summary."""
    new_found: list[DataContradiction] = []

    # YoY anomalies
    new_found.extend(check_yoy_anomalies(client_id, user_id, db))

    # Cross-source metric mismatches: for each tax year that has metrics from
    # multiple form sources, compare them pairwise.
    year_rows = (
        db.query(ClientFinancialMetric.tax_year)
        .filter(ClientFinancialMetric.client_id == client_id)
        .distinct()
        .all()
    )
    for (tax_year,) in year_rows:
        metrics_for_year = (
            db.query(ClientFinancialMetric)
            .filter(
                ClientFinancialMetric.client_id == client_id,
                ClientFinancialMetric.tax_year == tax_year,
                ClientFinancialMetric.metric_value.isnot(None),
            )
            .all()
        )

        # Group by form_source to find cross-source comparisons
        sources: dict[str, list[ClientFinancialMetric]] = {}
        for m in metrics_for_year:
            sources.setdefault(m.form_source or "unknown", []).append(m)

        if len(sources) < 2:
            continue

        # For each source pair, build the "new_metrics" list from one and
        # compare against existing from the other
        source_keys = list(sources.keys())
        for i in range(len(source_keys)):
            source_metrics = sources[source_keys[i]]
            as_dicts = [
                {
                    "metric_name": m.metric_name,
                    "metric_value": float(m.metric_value) if m.metric_value else None,
                    "form_source": m.form_source,
                }
                for m in source_metrics
            ]
            new_found.extend(
                check_metric_contradictions(client_id, user_id, tax_year, as_dicts, db)
            )

    db.commit()

    total_open = (
        db.query(func.count(DataContradiction.id))
        .filter(
            DataContradiction.client_id == client_id,
            DataContradiction.status == "open",
        )
        .scalar()
    ) or 0

    return {
        "new_contradictions": len(new_found),
        "total_open": total_open,
        "contradictions": new_found,
    }


# ---------------------------------------------------------------------------
# 4. Resolve
# ---------------------------------------------------------------------------


def resolve_contradiction(
    contradiction_id: UUID,
    user_id: str,
    resolution_note: str,
    db: Session,
) -> DataContradiction | None:
    """Mark a contradiction as resolved and create a journal entry."""
    contradiction = (
        db.query(DataContradiction)
        .filter(DataContradiction.id == contradiction_id)
        .first()
    )
    if contradiction is None:
        return None

    contradiction.status = "resolved"
    contradiction.resolved_by = user_id
    contradiction.resolved_at = datetime.now(timezone.utc)
    contradiction.resolution_note = resolution_note

    # Auto-create journal entry
    try:
        from app.services.journal_service import create_auto_entry

        create_auto_entry(
            db=db,
            client_id=contradiction.client_id,
            user_id=user_id,
            entry_type="system",
            category="compliance",
            title=f"Resolved: {contradiction.title[:150]}",
            content=resolution_note,
            source_type="system",
            source_id=contradiction.id,
        )
    except Exception:
        logger.exception(
            "Failed to create journal entry for resolved contradiction %s",
            contradiction_id,
        )

    db.commit()
    return contradiction


# ---------------------------------------------------------------------------
# 5. Dismiss
# ---------------------------------------------------------------------------


def dismiss_contradiction(
    contradiction_id: UUID,
    user_id: str,
    db: Session,
) -> DataContradiction | None:
    """Mark a contradiction as dismissed."""
    contradiction = (
        db.query(DataContradiction)
        .filter(DataContradiction.id == contradiction_id)
        .first()
    )
    if contradiction is None:
        return None

    contradiction.status = "dismissed"
    contradiction.resolved_by = user_id
    contradiction.resolved_at = datetime.now(timezone.utc)
    db.commit()
    return contradiction


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _severity_from_diff(diff: Decimal, base_value: Decimal) -> str:
    """Determine contradiction severity from absolute and percentage difference."""
    pct = float(abs(diff) / abs(base_value) * 100) if base_value != 0 else 100.0
    if diff > 5000 or pct > 10:
        return "high"
    if diff > 1000 or pct > 5:
        return "medium"
    return "low"


def _journal_explains_change(
    db: Session,
    client_id: UUID,
    tax_year: int,
    metric_name: str,
) -> bool:
    """Check if a journal entry exists that might explain a YoY change.

    Looks for entries with relevant categories near the tax year.
    This is a best-effort heuristic — we search for journal entries
    with financial/employment categories and an effective_date in the
    tax year.
    """
    from datetime import date

    start = date(tax_year, 1, 1)
    end = date(tax_year, 12, 31)

    explaining_categories = {"income", "employment", "business", "investment"}

    count = (
        db.query(func.count(JournalEntry.id))
        .filter(
            JournalEntry.client_id == client_id,
            JournalEntry.category.in_(explaining_categories),
            JournalEntry.effective_date >= start,
            JournalEntry.effective_date <= end,
        )
        .scalar()
    )
    return (count or 0) > 0

"""
Financial data extraction service.

Extracts structured financial metrics from classified documents (tax returns,
financial statements) and stores them in client_financial_metrics for trend
analysis and enriched AI context.

Called as a best-effort step in the document processing pipeline after
classification and chunking.
"""

from __future__ import annotations

import json
import logging
import re
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from openai import AsyncOpenAI
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.client_financial_metric import ClientFinancialMetric
from app.models.document import Document
from app.models.document_chunk import DocumentChunk

logger = logging.getLogger(__name__)

EXTRACTION_MODEL = "gpt-4o"

# Maximum text sent to the extraction prompt (characters).  Tax returns
# rarely exceed this; we cap to control token cost.
MAX_TEXT_CHARS = 12_000

# ---------------------------------------------------------------------------
# Expected metrics per form type
# ---------------------------------------------------------------------------

FORM_METRICS: dict[str, dict[str, list[str]]] = {
    "Form 1040": {
        "income": [
            "total_income", "agi", "taxable_income", "w2_wages",
            "schedule_c_net", "schedule_d_net", "schedule_e_net",
        ],
        "deductions": [
            "itemized_or_standard", "state_local_tax_deduction",
            "mortgage_interest", "charitable_contributions",
        ],
        "tax": [
            "total_tax", "self_employment_tax",
        ],
        "payments": [
            "total_payments", "estimated_payments_q1",
            "estimated_payments_q2", "estimated_payments_q3",
            "estimated_payments_q4", "estimated_payments_total",
            "refund_or_owed",
        ],
        "other": [
            "filing_status",
        ],
    },
    "Form 1040X": {
        "income": [
            "total_income", "agi", "taxable_income",
            "original_agi", "agi_change",
        ],
        "tax": [
            "total_tax", "original_total_tax", "total_tax_change",
        ],
        "payments": [
            "total_payments", "refund_or_owed",
        ],
    },
    "Form 1120-S": {
        "income": ["gross_receipts", "ordinary_income"],
        "deductions": ["total_deductions", "officer_compensation"],
        "assets": ["total_assets"],
        "liabilities": ["total_liabilities"],
        "other": ["shareholder_distributions"],
    },
    "Form 1065": {
        "income": ["gross_receipts", "ordinary_income"],
        "deductions": ["total_deductions", "guaranteed_payments"],
        "other": ["partner_count"],
    },
    "Form 1041": {
        "income": ["total_income"],
        "deductions": ["deductions", "distributable_net_income"],
        "tax": ["tax_liability"],
        "other": ["distributions"],
    },
    "P&L": {
        "income": [
            "revenue", "cogs", "gross_profit", "net_income",
            "revenue_q1", "revenue_q2", "revenue_q3", "revenue_q4",
        ],
        "deductions": ["operating_expenses"],
    },
    "Balance Sheet": {
        "assets": ["total_assets", "cash", "accounts_receivable"],
        "liabilities": ["total_liabilities", "accounts_payable"],
        "other": ["equity"],
    },
}

# Document subtypes that map to each form key above
_SUBTYPE_TO_FORM: dict[str, str] = {
    "Form 1040": "Form 1040",
    "Form 1040X": "Form 1040X",
    "Form 1120": "Form 1120-S",
    "Form 1120-S": "Form 1120-S",
    "Form 1120-S (Amended)": "Form 1120-S",
    "Form 1065": "Form 1065",
    "Form 1065 (Amended)": "Form 1065",
    "Form 1041": "Form 1041",
    "Form 1041 (Amended)": "Form 1041",
    "Schedule C": "Form 1040",
    "Schedule K-1": "Form 1065",
    "Q3 P&L": "P&L",
    "W-2 Wage Statement": "Form 1040",
}

VALID_CATEGORIES = {
    "income", "deductions", "credits", "tax",
    "payments", "assets", "liabilities", "other",
}


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def extract_financial_metrics(
    db: Session,
    document_id: UUID,
    client_id: UUID,
) -> list[ClientFinancialMetric]:
    """
    Extract structured financial metrics from a classified document.

    Returns the list of upserted :class:`ClientFinancialMetric` rows.
    Skips documents that aren't tax returns or financial statements.
    """
    document = db.query(Document).filter(Document.id == document_id).first()
    if document is None:
        logger.warning("Financial extraction: document %s not found", document_id)
        return []

    # Only extract from tax returns and financial statements
    if document.document_type not in ("tax_return", "financial_statement"):
        return []

    # Parse tax year from document_period (e.g. "2024", "Q3 2024", "2023-2024")
    tax_year = _parse_tax_year(document.document_period)
    if tax_year is None:
        logger.warning(
            "Financial extraction: cannot determine tax year from period %r for %s",
            document.document_period, document_id,
        )
        return []

    # Determine form type for metric selection
    form_key = _resolve_form_key(document)
    if form_key is None:
        logger.info(
            "Financial extraction: no metric template for subtype %r, type %r",
            document.document_subtype, document.document_type,
        )
        return []

    # Gather document text from chunks
    text = _get_document_text(db, document_id)
    if not text.strip():
        logger.warning("Financial extraction: no text for document %s", document_id)
        return []

    # Build and send extraction prompt
    expected_metrics = FORM_METRICS[form_key]
    is_amended = bool(document.amends_subtype)
    form_source = document.document_subtype or form_key

    raw_metrics = await _call_extraction(
        text, form_key, expected_metrics, form_source, is_amended,
    )

    if not raw_metrics:
        logger.info("Financial extraction: no metrics returned for %s", document_id)
        return []

    # Snapshot existing values before upsert to detect changes
    existing_values: dict[str, Decimal | None] = {}
    for entry in raw_metrics:
        mname = entry.get("metric_name")
        if mname:
            existing_row = (
                db.query(ClientFinancialMetric.metric_value)
                .filter(
                    ClientFinancialMetric.client_id == client_id,
                    ClientFinancialMetric.tax_year == tax_year,
                    ClientFinancialMetric.metric_name == mname,
                    ClientFinancialMetric.form_source == (entry.get("form_source") or form_source),
                )
                .first()
            )
            if existing_row is not None:
                existing_values[mname] = existing_row[0]

    # Upsert into database
    results = _upsert_metrics(
        db,
        client_id=client_id,
        document_id=document_id,
        tax_year=tax_year,
        form_source=form_source,
        is_amended=is_amended,
        raw_metrics=raw_metrics,
    )

    logger.info(
        "Financial extraction: %d metrics extracted from %s (%s, %d)",
        len(results), document.filename, form_source, tax_year,
    )

    # Journal entry for changed metrics (best-effort)
    try:
        if existing_values:
            _journal_financial_changes(
                db, client_id, document_id, tax_year, results, existing_values,
            )
    except Exception:
        logger.warning("Financial journal entry failed (non-fatal)", exc_info=True)

    # Run threshold checks and profile flag suggestions (best-effort)
    try:
        check_financial_thresholds(db, client_id, tax_year, results)
    except Exception:
        logger.warning("Financial threshold check failed (non-fatal)", exc_info=True)

    try:
        check_profile_flag_suggestions(db, client_id, results, document)
    except Exception:
        logger.warning("Profile flag suggestion check failed (non-fatal)", exc_info=True)

    # Run contradiction detection against existing metrics (best-effort)
    try:
        from app.services.contradiction_service import check_metric_contradictions

        check_metric_contradictions(
            client_id=client_id,
            user_id="system",
            tax_year=tax_year,
            new_metrics=raw_metrics,
            db=db,
        )
    except Exception:
        logger.warning("Contradiction detection failed (non-fatal)", exc_info=True)

    return results


# ---------------------------------------------------------------------------
# Journal helper
# ---------------------------------------------------------------------------


_METRIC_CATEGORY_MAP = {
    "income": "income",
    "deductions": "deductions",
    "credits": "deductions",
    "tax": "income",
    "payments": "income",
    "assets": "business",
    "liabilities": "business",
}


def _journal_financial_changes(
    db: Session,
    client_id: UUID,
    document_id: UUID,
    tax_year: int,
    results: list[ClientFinancialMetric],
    existing_values: dict[str, Decimal | None],
) -> None:
    """Create a journal entry summarizing metrics that changed value."""
    from app.services.journal_service import create_auto_entry

    changes: list[dict[str, Any]] = []
    for row in results:
        if row.metric_name not in existing_values:
            continue  # newly created, not an update
        old_val = existing_values[row.metric_name]
        new_val = row.metric_value
        if old_val == new_val:
            continue
        change_pct = None
        if old_val and old_val != 0 and new_val is not None:
            change_pct = round(float((new_val - old_val) / abs(old_val) * 100), 1)
        changes.append({
            "metric": row.metric_name,
            "old": float(old_val) if old_val is not None else None,
            "new": float(new_val) if new_val is not None else None,
            "change_pct": change_pct,
        })

    if not changes:
        return

    # Build title from the first (most important) change
    first = changes[0]
    old_fmt = f"${first['old']:,.0f}" if first["old"] is not None else "N/A"
    new_fmt = f"${first['new']:,.0f}" if first["new"] is not None else "N/A"
    label = first["metric"].replace("_", " ").upper()
    title = f"{label} changed from {old_fmt} to {new_fmt} for tax year {tax_year}"
    if len(changes) > 1:
        title = f"{len(changes)} financial metrics updated for tax year {tax_year}"

    lines = []
    for ch in changes:
        old_s = f"${ch['old']:,.0f}" if ch["old"] is not None else "N/A"
        new_s = f"${ch['new']:,.0f}" if ch["new"] is not None else "N/A"
        pct = f" ({ch['change_pct']:+.1f}%)" if ch["change_pct"] is not None else ""
        lines.append(f"• {ch['metric'].replace('_', ' ')}: {old_s} → {new_s}{pct}")
    content = "\n".join(lines)

    # Use the first metric's category for the journal category
    first_category = _METRIC_CATEGORY_MAP.get(
        results[0].metric_category if results else "income", "general",
    )

    create_auto_entry(
        db=db,
        client_id=client_id,
        user_id="system",
        entry_type="financial_change",
        category=first_category,
        title=title,
        content=content,
        source_type="document",
        source_id=document_id,
        metadata={"changes": changes, "tax_year": tax_year},
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_tax_year(period: str | None) -> int | None:
    """Extract a 4-digit year from a document_period string."""
    if not period:
        return None
    # Match rightmost 4-digit year (handles "2023-2024" → 2024, "Q3 2024" → 2024)
    matches = re.findall(r"\b(20\d{2})\b", period)
    if matches:
        return int(matches[-1])
    return None


def _resolve_form_key(document: Document) -> str | None:
    """Map a document's subtype to a FORM_METRICS key."""
    subtype = document.document_subtype
    if subtype and subtype in _SUBTYPE_TO_FORM:
        return _SUBTYPE_TO_FORM[subtype]

    # Fallback: if it's a financial statement, try to guess from subtype text
    if document.document_type == "financial_statement":
        if subtype:
            lower = subtype.lower()
            if "p&l" in lower or "profit" in lower or "income statement" in lower:
                return "P&L"
            if "balance" in lower:
                return "Balance Sheet"
        return "P&L"  # default for financial statements

    # For tax returns without a recognised subtype
    if document.document_type == "tax_return":
        return "Form 1040"  # most common individual return

    return None


def _get_document_text(db: Session, document_id: UUID) -> str:
    """Concatenate all chunks for a document into full text."""
    chunks = (
        db.query(DocumentChunk.chunk_text)
        .filter(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.chunk_index)
        .all()
    )
    full = " ".join(c.chunk_text for c in chunks)
    return full[:MAX_TEXT_CHARS]


def _build_metric_list(expected: dict[str, list[str]]) -> str:
    """Format expected metrics as a readable list for the prompt."""
    lines: list[str] = []
    for category, names in expected.items():
        for name in names:
            lines.append(f"  - {name} (category: {category})")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# GPT-4o extraction
# ---------------------------------------------------------------------------

_EXTRACTION_SYSTEM = """\
You are a financial data extraction assistant for a CPA platform. Extract \
specific financial metrics from the provided document text with high accuracy.

Rules:
- Extract ONLY metrics that are clearly stated in the document. Do not infer or calculate.
- Use exact dollar amounts as they appear (e.g. 187432.00, not 187000).
- If a metric is not found in the document, omit it from the results.
- For filing_status: 1=Single, 2=MFJ, 3=MFS, 4=HoH, 5=QSS.
- For itemized_or_standard: 1=Itemized, 0=Standard.
- Include the line_reference when visible (e.g. "Line 11", "Box 1").
- Confidence should be 0.90-1.00 for clearly visible values, 0.70-0.89 for \
partially visible or inferred from context, below 0.70 for uncertain.
- For amended returns (1040X), extract values from the "Corrected" column.

Respond with ONLY a JSON array. No markdown fences, no commentary.
"""


async def _call_extraction(
    text: str,
    form_key: str,
    expected_metrics: dict[str, list[str]],
    form_source: str,
    is_amended: bool,
) -> list[dict[str, Any]]:
    """Call GPT-4o to extract financial metrics from document text."""
    metric_list = _build_metric_list(expected_metrics)

    amendment_note = ""
    if is_amended:
        amendment_note = (
            "\n\nThis is an AMENDED return. Extract values from the 'Corrected' "
            "column. Also extract original values as separate metrics with "
            "'_original' suffix (e.g. agi_original, total_tax_original)."
        )

    user_prompt = f"""\
Extract financial metrics from this {form_source} document.

Expected metrics to look for:
{metric_list}
{amendment_note}

Return a JSON array where each element has:
- "metric_category": one of (income, deductions, credits, tax, payments, assets, liabilities, other)
- "metric_name": the metric identifier from the list above
- "metric_value": the numeric value (decimal, no currency symbols)
- "form_source": "{form_source}"
- "line_reference": the line/box number if visible (e.g. "Line 11"), or null
- "confidence": your confidence 0.00-1.00

Document text:
{text}"""

    client = AsyncOpenAI(api_key=get_settings().openai_api_key)
    response = await client.chat.completions.create(
        model=EXTRACTION_MODEL,
        messages=[
            {"role": "system", "content": _EXTRACTION_SYSTEM},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.0,
        max_tokens=2000,
    )

    raw = response.choices[0].message.content or "[]"

    # Strip markdown fences
    raw = re.sub(r"^```(?:json)?\s*\n?", "", raw.strip())
    raw = re.sub(r"\n?\s*```$", "", raw.strip())

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Financial extraction: invalid JSON from GPT: %s", raw[:300])
        return []

    if not isinstance(parsed, list):
        logger.warning("Financial extraction: expected list, got %s", type(parsed).__name__)
        return []

    return parsed


# ---------------------------------------------------------------------------
# Upsert logic
# ---------------------------------------------------------------------------


def _upsert_metrics(
    db: Session,
    *,
    client_id: UUID,
    document_id: UUID,
    tax_year: int,
    form_source: str,
    is_amended: bool,
    raw_metrics: list[dict[str, Any]],
) -> list[ClientFinancialMetric]:
    """Validate and upsert extracted metrics into client_financial_metrics."""
    results: list[ClientFinancialMetric] = []

    for entry in raw_metrics:
        metric_name = entry.get("metric_name")
        metric_category = entry.get("metric_category")

        if not metric_name or not metric_category:
            continue
        if metric_category not in VALID_CATEGORIES:
            continue

        # Parse metric_value
        raw_value = entry.get("metric_value")
        metric_value = None
        if raw_value is not None:
            try:
                metric_value = Decimal(str(raw_value))
            except (InvalidOperation, ValueError, TypeError):
                continue  # skip unparseable values

        confidence_raw = entry.get("confidence", 1.0)
        try:
            confidence = Decimal(str(confidence_raw)).quantize(Decimal("0.01"))
            confidence = max(Decimal("0.00"), min(Decimal("1.00"), confidence))
        except (InvalidOperation, ValueError, TypeError):
            confidence = Decimal("1.00")

        line_ref = entry.get("line_reference") or None
        entry_form = entry.get("form_source") or form_source

        # If this is an amendment, store original values before overwriting
        if is_amended and metric_name.endswith("_original"):
            # Original-value metrics from amendments: store directly
            pass
        elif is_amended and not metric_name.endswith("_original"):
            # For amended returns, preserve the existing value as *_original
            # before upserting the corrected value
            existing = (
                db.query(ClientFinancialMetric)
                .filter(
                    ClientFinancialMetric.client_id == client_id,
                    ClientFinancialMetric.tax_year == tax_year,
                    ClientFinancialMetric.metric_name == metric_name,
                    ClientFinancialMetric.form_source == entry_form,
                )
                .first()
            )
            if existing and existing.metric_value is not None and not existing.is_amended:
                # Save the pre-amendment value
                orig_name = f"{metric_name}_original"
                _do_upsert(
                    db,
                    client_id=client_id,
                    document_id=document_id,
                    tax_year=tax_year,
                    metric_category=metric_category,
                    metric_name=orig_name,
                    metric_value=existing.metric_value,
                    form_source=entry_form,
                    line_reference=existing.line_reference,
                    is_amended=False,
                    confidence=existing.confidence,
                )

        row = _do_upsert(
            db,
            client_id=client_id,
            document_id=document_id,
            tax_year=tax_year,
            metric_category=metric_category,
            metric_name=metric_name,
            metric_value=metric_value,
            form_source=entry_form,
            line_reference=line_ref,
            is_amended=is_amended,
            confidence=confidence,
        )
        results.append(row)

    db.commit()
    return results


def _do_upsert(
    db: Session,
    *,
    client_id: UUID,
    document_id: UUID,
    tax_year: int,
    metric_category: str,
    metric_name: str,
    metric_value: Decimal | None,
    form_source: str,
    line_reference: str | None,
    is_amended: bool,
    confidence: Decimal,
) -> ClientFinancialMetric:
    """Insert or update a single financial metric row."""
    stmt = pg_insert(ClientFinancialMetric).values(
        client_id=client_id,
        document_id=document_id,
        tax_year=tax_year,
        metric_category=metric_category,
        metric_name=metric_name,
        metric_value=metric_value,
        form_source=form_source,
        line_reference=line_reference,
        is_amended=is_amended,
        confidence=confidence,
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_client_financial_metric",
        set_={
            "metric_value": stmt.excluded.metric_value,
            "document_id": stmt.excluded.document_id,
            "line_reference": stmt.excluded.line_reference,
            "is_amended": stmt.excluded.is_amended,
            "confidence": stmt.excluded.confidence,
            "extracted_at": stmt.excluded.extracted_at,
        },
    )
    db.execute(stmt)
    db.flush()

    # Fetch the row back for the return list
    row = (
        db.query(ClientFinancialMetric)
        .filter(
            ClientFinancialMetric.client_id == client_id,
            ClientFinancialMetric.tax_year == tax_year,
            ClientFinancialMetric.metric_name == metric_name,
            ClientFinancialMetric.form_source == form_source,
        )
        .first()
    )
    return row  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Threshold-based alerts
# ---------------------------------------------------------------------------

# 2024 thresholds (updated annually)
_NIIT_SINGLE = 200_000
_NIIT_MFJ = 250_000
_TOP_BRACKET_2024 = 578_125
_QBI_SINGLE = 191_950
_QBI_MFJ = 383_900


def _metric_val(
    metrics: list[ClientFinancialMetric], name: str,
) -> float | None:
    """Get a metric value by name from the extraction results."""
    for m in metrics:
        if m.metric_name == name and m.metric_value is not None:
            return float(m.metric_value)
    return None


def check_financial_thresholds(
    db: Session,
    client_id: UUID,
    tax_year: int,
    metrics: list[ClientFinancialMetric],
) -> list[dict[str, Any]]:
    """
    Check extracted metrics against tax planning thresholds and create
    alerts for significant findings.

    Alerts are created as ``financial_threshold`` type in the alerts system
    via the ``DismissedAlert``-compatible pattern: they are computed
    on-demand from the stored metrics by ``alerts_service``.

    This function stores threshold-breach records so the alerts service
    can surface them.  Returns the list of alert dicts generated
    (for logging / testing purposes).
    """
    alerts: list[dict[str, Any]] = []

    agi = _metric_val(metrics, "agi")
    taxable_income = _metric_val(metrics, "taxable_income")
    total_tax = _metric_val(metrics, "total_tax")
    filing_status = _metric_val(metrics, "filing_status")
    est_total = _metric_val(metrics, "estimated_payments_total")

    # Determine filing-status-dependent thresholds
    is_mfj = filing_status == 2.0

    # 1. NIIT threshold
    if agi is not None:
        niit_threshold = _NIIT_MFJ if is_mfj else _NIIT_SINGLE
        if agi > niit_threshold:
            alerts.append({
                "type": "financial_threshold",
                "severity": "warning",
                "client_id": str(client_id),
                "message": (
                    f"Client's MAGI of ${agi:,.0f} exceeds the "
                    f"${niit_threshold:,} NIIT threshold. "
                    f"Review Net Investment Income Tax planning strategies."
                ),
                "threshold": "niit",
                "tax_year": tax_year,
            })

    # 2. Top bracket
    if taxable_income is not None and taxable_income > _TOP_BRACKET_2024:
        alerts.append({
            "type": "financial_threshold",
            "severity": "warning",
            "client_id": str(client_id),
            "message": (
                f"Taxable income of ${taxable_income:,.0f} is in the top "
                f"bracket. Consider income timing and deferral strategies."
            ),
            "threshold": "top_bracket",
            "tax_year": tax_year,
        })

    # 3. QBI phase-out
    if taxable_income is not None:
        qbi_limit = _QBI_MFJ if is_mfj else _QBI_SINGLE
        if taxable_income > qbi_limit:
            alerts.append({
                "type": "financial_threshold",
                "severity": "info",
                "client_id": str(client_id),
                "message": (
                    f"Taxable income of ${taxable_income:,.0f} exceeds the "
                    f"${qbi_limit:,} QBI deduction phase-out threshold. "
                    f"Review Section 199A planning."
                ),
                "threshold": "qbi_phaseout",
                "tax_year": tax_year,
            })

    # 4. Year-over-year swing (>25% change)
    prior_year = tax_year - 1
    for metric_name in ("agi", "total_income", "schedule_c_net"):
        current_val = _metric_val(metrics, metric_name)
        if current_val is None:
            continue

        prior = (
            db.query(ClientFinancialMetric)
            .filter(
                ClientFinancialMetric.client_id == client_id,
                ClientFinancialMetric.tax_year == prior_year,
                ClientFinancialMetric.metric_name == metric_name,
            )
            .first()
        )
        if prior and prior.metric_value is not None:
            prior_val = float(prior.metric_value)
            if prior_val != 0:
                pct_change = ((current_val - prior_val) / abs(prior_val)) * 100
                if abs(pct_change) >= 25:
                    direction = "increased" if pct_change > 0 else "decreased"
                    alerts.append({
                        "type": "financial_threshold",
                        "severity": "warning",
                        "client_id": str(client_id),
                        "message": (
                            f"Client's {metric_name.replace('_', ' ')} "
                            f"{direction} {abs(pct_change):.0f}% from "
                            f"${prior_val:,.0f} to ${current_val:,.0f}. "
                            f"Review estimated payments and planning strategies."
                        ),
                        "threshold": "yoy_swing",
                        "tax_year": tax_year,
                    })

    # 5. Estimated payment shortfall
    if total_tax is not None and est_total is not None and total_tax > 0:
        if est_total < total_tax * 0.90:
            shortfall = total_tax - est_total
            alerts.append({
                "type": "financial_threshold",
                "severity": "warning",
                "client_id": str(client_id),
                "message": (
                    f"Estimated payments of ${est_total:,.0f} are below 90% "
                    f"of total tax (${total_tax:,.0f}). Potential underpayment "
                    f"penalty of ~${shortfall * 0.08:,.0f}. Review safe harbor."
                ),
                "threshold": "est_payment_shortfall",
                "tax_year": tax_year,
            })

    if alerts:
        logger.info(
            "Financial thresholds: %d alert(s) for client %s, year %d",
            len(alerts), client_id, tax_year,
        )

    return alerts


# ---------------------------------------------------------------------------
# Profile flag suggestions
# ---------------------------------------------------------------------------


def check_profile_flag_suggestions(
    db: Session,
    client_id: UUID,
    metrics: list[ClientFinancialMetric],
    document: Document,
) -> list[dict[str, Any]]:
    """
    Suggest profile flag updates based on extracted financial data.

    Does NOT auto-set flags — creates alerts suggesting the CPA review
    and update them via the strategy tab.
    """
    from app.models.client import Client

    client = db.query(Client).filter(Client.id == client_id).first()
    if client is None:
        return []

    suggestions: list[dict[str, Any]] = []

    # Schedule C net > 0 → has_business_entity
    sched_c = _metric_val(metrics, "schedule_c_net")
    if sched_c is not None and sched_c > 0 and not client.has_business_entity:
        suggestions.append({
            "type": "financial_threshold",
            "severity": "info",
            "client_id": str(client_id),
            "message": (
                f"Schedule C net income of ${sched_c:,.0f} detected. "
                f"Consider enabling 'Has Business Entity' profile flag "
                f"to unlock business tax strategies."
            ),
            "threshold": "flag_suggestion",
            "suggested_flag": "has_business_entity",
        })

    # Schedule E net != 0 → has_real_estate
    sched_e = _metric_val(metrics, "schedule_e_net")
    if sched_e is not None and sched_e != 0 and not client.has_real_estate:
        suggestions.append({
            "type": "financial_threshold",
            "severity": "info",
            "client_id": str(client_id),
            "message": (
                f"Schedule E activity detected (${sched_e:,.0f}). "
                f"Consider enabling 'Has Real Estate' profile flag "
                f"to unlock real estate tax strategies."
            ),
            "threshold": "flag_suggestion",
            "suggested_flag": "has_real_estate",
        })

    # AGI > $200K → has_high_income
    agi = _metric_val(metrics, "agi")
    if agi is not None and agi > 200_000 and not client.has_high_income:
        suggestions.append({
            "type": "financial_threshold",
            "severity": "info",
            "client_id": str(client_id),
            "message": (
                f"AGI of ${agi:,.0f} exceeds $200K. Consider enabling "
                f"'Has High Income' profile flag to unlock high-income "
                f"tax planning strategies."
            ),
            "threshold": "flag_suggestion",
            "suggested_flag": "has_high_income",
        })

    # Form 1041 → has_estate_planning
    if (
        document.document_subtype
        and "1041" in document.document_subtype
        and not client.has_estate_planning
    ):
        suggestions.append({
            "type": "financial_threshold",
            "severity": "info",
            "client_id": str(client_id),
            "message": (
                "Form 1041 (trust/estate return) detected. Consider "
                "enabling 'Has Estate Planning' profile flag to unlock "
                "estate planning strategies."
            ),
            "threshold": "flag_suggestion",
            "suggested_flag": "has_estate_planning",
        })

    if suggestions:
        logger.info(
            "Profile flag suggestions: %d suggestion(s) for client %s",
            len(suggestions), client_id,
        )

    return suggestions

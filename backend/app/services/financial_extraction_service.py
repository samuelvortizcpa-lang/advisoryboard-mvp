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
    return results


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

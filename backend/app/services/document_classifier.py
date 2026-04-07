"""
Document classifier: uses GPT-4o-mini to identify document type, subtype, and period.

Called during the document processing pipeline after text extraction.
"""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING

from openai import AsyncOpenAI

from app.core.config import get_settings

if TYPE_CHECKING:
    from uuid import UUID
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

CLASSIFICATION_MODEL = "gpt-4o-mini"

VALID_DOCUMENT_TYPES = {
    "tax_return", "w2", "k1", "financial_statement", "bank_statement",
    "engagement_letter", "contract", "meeting_notes", "email",
    "invoice", "receipt", "other",
}

CLASSIFICATION_PROMPT = """\
You are a document classifier for a CPA advisory platform.

Analyze the following text (the beginning of a document) and classify it.

Respond with ONLY a JSON object with these fields:
- "document_type": one of: tax_return, w2, k1, financial_statement, bank_statement, engagement_letter, contract, meeting_notes, email, invoice, receipt, other
- "document_subtype": specific form or report name. Known subtypes include: "Form 1040", "Form 1120", "Form 1120-S", "Form 1065", "Form 1041", "Schedule C", "Schedule K-1", "Form 1040X", "Form 1120X", "Form 1120-S (Amended)", "Form 1065 (Amended)", "Form 1041 (Amended)", "Q3 P&L", "W-2 Wage Statement". Use null if unclear.
- "document_period": the tax year, fiscal year, or quarter if applicable (e.g. "2024", "Q3 2024", "2023-2024"). Use null if not applicable.
- "classification_confidence": your confidence in the classification from 0 to 100.
- "amends_subtype": if this is an amended return, the form it amends (e.g. "Form 1040" for a 1040X, "Form 1120-S" for an amended 1120-S). Use null for non-amendments.
- "amendment_number": if this is an amended return, which amendment number (1 for first amendment, 2 for second, etc.). Look for indicators like "2nd Amended" in the text. Use null for non-amendments, default 1 for first amendment.

Text to classify:
{text}
"""


def _openai() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=get_settings().openai_api_key)


async def classify_document(
    text: str,
    *,
    db: "Session | None" = None,
    user_id: str | None = None,
    client_id: "UUID | None" = None,
) -> dict:
    """
    Classify a document based on its extracted text.

    Takes the first 2000 characters and returns::

        {
            "document_type": str,
            "document_subtype": str | None,
            "document_period": str | None,
            "classification_confidence": float,
            "amends_subtype": str | None,
            "amendment_number": int | None,
        }
    """
    snippet = text[:2000]

    client = _openai()
    response = await client.chat.completions.create(
        model=CLASSIFICATION_MODEL,
        messages=[
            {"role": "system", "content": "You are a document classification assistant. Respond only with valid JSON."},
            {"role": "user", "content": CLASSIFICATION_PROMPT.format(text=snippet)},
        ],
        temperature=0.0,
        max_tokens=200,
    )

    # Log token usage for cost tracking
    if db and user_id:
        try:
            from app.services.token_tracking_service import log_token_usage
            usage = response.usage
            log_token_usage(
                db,
                user_id=user_id,
                client_id=client_id,
                query_type="classification",
                model=CLASSIFICATION_MODEL,
                prompt_tokens=usage.prompt_tokens if usage else 0,
                completion_tokens=usage.completion_tokens if usage else 0,
                endpoint="document_classify",
            )
        except Exception:
            logger.error("Failed to log document classify token usage", exc_info=True)

    raw = response.choices[0].message.content or "{}"

    # Strip markdown code fences that GPT sometimes wraps around JSON
    raw = re.sub(r"^```(?:json)?\s*\n?", "", raw.strip())
    raw = re.sub(r"\n?\s*```$", "", raw.strip())

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Classifier returned invalid JSON: %s", raw[:200])
        return {
            "document_type": "other",
            "document_subtype": None,
            "document_period": None,
            "classification_confidence": 0.0,
            "amends_subtype": None,
            "amendment_number": None,
        }

    # Validate document_type
    doc_type = result.get("document_type", "other")
    if doc_type not in VALID_DOCUMENT_TYPES:
        doc_type = "other"

    # Clamp confidence
    confidence = result.get("classification_confidence", 0)
    try:
        confidence = max(0.0, min(100.0, float(confidence)))
    except (TypeError, ValueError):
        confidence = 0.0

    # Parse amendment_number
    amendment_number = result.get("amendment_number")
    if amendment_number is not None:
        try:
            amendment_number = int(amendment_number)
        except (TypeError, ValueError):
            amendment_number = None

    return {
        "document_type": doc_type,
        "document_subtype": result.get("document_subtype") or None,
        "document_period": result.get("document_period") or None,
        "classification_confidence": round(confidence, 2),
        "amends_subtype": result.get("amends_subtype") or None,
        "amendment_number": amendment_number,
    }

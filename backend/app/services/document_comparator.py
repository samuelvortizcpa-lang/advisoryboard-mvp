"""
Document comparison service.

Retrieves representative chunks from multiple documents and uses GPT-4o
to generate a structured comparison report in Markdown.

Comparison types:
  "summary"   — High-level overview + key similarities/differences/insights
  "changes"   — What changed between document versions
  "financial" — Compare numerical/financial data across documents
"""

from __future__ import annotations

import logging
from typing import List
from uuid import UUID

from openai import AsyncOpenAI
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.document import Document
from app.models.document_chunk import DocumentChunk

logger = logging.getLogger(__name__)

CHAT_MODEL = "gpt-4o"
CHUNKS_PER_DOCUMENT = 20

COMPARISON_PROMPTS: dict[str, str] = {
    "summary": """\
You are an expert document analyst for a CPA advisory platform. \
You have been given content from {num_docs} documents belonging to the same client.

Your task: produce a comprehensive comparison report in clean Markdown.

Structure your report with these exact sections:

## Document Overview
A 1-2 sentence summary of each document (label each by its filename).

## Key Similarities
Bullet points of what the documents share in common.

## Key Differences
Bullet points of the most significant differences between the documents.

## Insights & Recommendations
2-4 actionable insights a CPA would find valuable based on this comparison.

---

Documents to compare:

{documents_content}
""",

    "changes": """\
You are an expert document analyst for a CPA advisory platform. \
You have been given content from {num_docs} documents that may represent \
different versions, time periods, or revisions of related materials.

Your task: produce a detailed change analysis report in clean Markdown.

Structure your report with these exact sections:

## What Changed
Specific content, figures, or information that differs between documents.

## What Was Added
New information present in later/secondary documents not found in earlier ones.

## What Was Removed or Reduced
Information present in one document but missing or diminished in others.

## Unchanged Elements
Core content that remains consistent across all documents.

## Change Summary
A 1-paragraph executive summary of the overall changes and their significance.

---

Documents to compare:

{documents_content}
""",

    "financial": """\
You are an expert financial analyst for a CPA advisory platform. \
You have been given content from {num_docs} documents containing financial data.

Your task: produce a financial comparison report in clean Markdown.

Structure your report with these exact sections:

## Financial Metrics Comparison
Compare key numbers (revenue, expenses, profit, taxes, assets, liabilities, etc.) \
across documents. Use a table where possible; fall back to bullet lists if numbers \
are not comparable in tabular form. Include exact figures when available.

## Notable Variances
The most significant numerical differences and their potential implications.

## Trends & Patterns
Any financial trends observable across the documents (growth, decline, \
category shifts).

## Red Flags & Opportunities
Items a CPA should pay attention to based on this financial comparison.

---

Documents to compare:

{documents_content}
""",
}


def _openai() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=get_settings().openai_api_key)


async def compare_documents(
    document_ids: List[UUID],
    comparison_type: str,
    client_id: UUID,
    db: Session,
) -> dict:
    """
    Compare multiple documents using GPT-4o.

    Returns::

        {
            "comparison_type": str,
            "documents": [{"id": str, "filename": str}, ...],
            "report": str  # Markdown-formatted comparison
        }

    Raises ValueError for invalid input (wrong comparison_type, wrong client,
    unprocessed documents, etc.).
    """
    if comparison_type not in COMPARISON_PROMPTS:
        raise ValueError(
            f"Invalid comparison_type '{comparison_type}'. "
            f"Must be one of: {', '.join(COMPARISON_PROMPTS)}"
        )

    if len(document_ids) < 2:
        raise ValueError("At least 2 documents are required for comparison.")

    # 1. Validate all documents exist and belong to this client
    documents = (
        db.query(Document)
        .filter(
            Document.id.in_(document_ids),
            Document.client_id == client_id,
        )
        .all()
    )

    if len(documents) != len(document_ids):
        found_ids = {d.id for d in documents}
        missing = [str(did) for did in document_ids if did not in found_ids]
        raise ValueError(
            f"Documents not found or do not belong to this client: {', '.join(missing)}"
        )

    # 2. Ensure all documents have been processed
    unprocessed = [d.filename for d in documents if not d.processed]
    if unprocessed:
        raise ValueError(
            f"The following documents have not been processed yet: "
            f"{', '.join(unprocessed)}. "
            "Please wait for processing to complete before comparing."
        )

    # 3. For each document get up to CHUNKS_PER_DOCUMENT chunks ordered by
    #    chunk_index (sequential document content is more representative than
    #    a semantically-filtered subset for comparison purposes).
    doc_id_order = {doc_id: i for i, doc_id in enumerate(document_ids)}
    documents_sorted = sorted(documents, key=lambda d: doc_id_order[d.id])

    documents_content_parts: list[str] = []
    doc_metadata: list[dict] = []

    for doc in documents_sorted:
        chunks = (
            db.query(DocumentChunk)
            .filter(
                DocumentChunk.document_id == doc.id,
                DocumentChunk.client_id == client_id,
            )
            .order_by(DocumentChunk.chunk_index)
            .limit(CHUNKS_PER_DOCUMENT)
            .all()
        )
        combined_text = "\n\n".join(c.chunk_text for c in chunks)
        documents_content_parts.append(
            f"### Document: {doc.filename}\n\n{combined_text}"
        )
        doc_metadata.append({"id": str(doc.id), "filename": doc.filename})

    documents_content = "\n\n---\n\n".join(documents_content_parts)

    # 4. Build prompt and call GPT-4o
    system_prompt = COMPARISON_PROMPTS[comparison_type].format(
        num_docs=len(documents),
        documents_content=documents_content,
    )

    logger.info(
        "Comparing %d documents for client %s (type=%s)",
        len(documents),
        client_id,
        comparison_type,
    )

    client = _openai()
    response = await client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"Please compare these {len(documents)} documents and produce "
                    f"a {comparison_type} comparison report."
                ),
            },
        ],
        temperature=0.2,
        max_tokens=2_000,
    )

    report = response.choices[0].message.content or "No comparison report generated."

    logger.info(
        "Comparison complete for client %s: %d chars", client_id, len(report)
    )

    return {
        "comparison_type": comparison_type,
        "documents": doc_metadata,
        "report": report,
    }

"""
Google Document AI integration for structured tax form extraction.

Provides two extraction modes:
  - Form Parser: extracts key-value pairs, tables, and structured text from
    IRS forms (1040, W-2, K-1, 1099, etc.)
  - Document OCR: high-quality text extraction for general PDFs

Gracefully returns None when not configured, so the caller falls back to
the existing pdfplumber pipeline.
"""

from __future__ import annotations

import json
import logging
import os
import uuid

import sentry_sdk

logger = logging.getLogger(__name__)

_client = None

# Feature flag: enables batch processing for 31-200 page documents.
# Default False for soft launch. When False, 31-200 pp docs return None
# (same behavior as today — caller falls back to pdfplumber).
USE_DOCAI_BATCH = os.getenv("USE_DOCAI_BATCH", "false").lower() == "true"

# Financial document types get Form Parser; everything else gets OCR.
# This mirrors the routing currently in text_extraction.extract_text_with_docai.
FINANCIAL_DOC_TYPES = frozenset({
    "tax_return", "w2", "k1", "1099", "financial_statement", "1040x", "invoice",
})


class DocAITooLarge(Exception):
    """Document exceeds max supported page count for DocAI (200)."""


def is_available() -> bool:
    """Return True if all required Document AI env vars are set."""
    return bool(
        os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")
        and os.getenv("DOCAI_FORM_PARSER_ID")
        and os.getenv("DOCAI_OCR_PROCESSOR_ID")
        and os.getenv("GOOGLE_CLOUD_PROJECT")
    )


def _get_client():
    """Lazy-init Document AI client from env var JSON credentials."""
    global _client
    if _client is not None:
        return _client

    creds_json = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")
    if not creds_json:
        return None

    try:
        from google.cloud import documentai
        from google.oauth2 import service_account

        creds_info = json.loads(creds_json)
        credentials = service_account.Credentials.from_service_account_info(creds_info)
        _client = documentai.DocumentProcessorServiceClient(credentials=credentials)
        return _client
    except Exception as exc:
        sentry_sdk.capture_exception(exc)
        logger.warning("Failed to initialize Document AI client: %s", exc)
        return None


def _get_text_from_layout(layout, full_text: str) -> str:
    """Extract text from a Document AI layout element using text_anchor offsets."""
    if not layout.text_anchor or not layout.text_anchor.text_segments:
        return ""
    parts = []
    for segment in layout.text_anchor.text_segments:
        start = int(segment.start_index) if segment.start_index else 0
        end = int(segment.end_index) if segment.end_index else 0
        if end <= start:
            continue
        parts.append(full_text[start:end])
    return "".join(parts)


def _format_table(table, full_text: str) -> str:
    """Format a Document AI table as readable text with pipe-separated columns."""
    rows = []
    for row in table.header_rows:
        cells = [_get_text_from_layout(cell.layout, full_text).strip() for cell in row.cells]
        rows.append(" | ".join(cells))
    for row in table.body_rows:
        cells = [_get_text_from_layout(cell.layout, full_text).strip() for cell in row.cells]
        rows.append(" | ".join(cells))
    return "\n".join(rows)


def _count_pdf_pages(file_bytes: bytes) -> int | None:
    """Quick page count from PDF header without a full parse."""
    try:
        import pdfplumber
        import io
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            return len(pdf.pages)
    except Exception:
        return None


def extract_with_form_parser(
    file_bytes: bytes,
    mime_type: str = "application/pdf",
    *,
    imageless_mode: bool = False,
) -> dict | None:
    """
    Send PDF to Document AI Form Parser for structured extraction.

    Returns dict with text, entities, tables, pages — or None on error.
    """
    client = _get_client()
    if client is None:
        return None

    # Check page limit — imageless mode allows up to 30 pages
    max_pages = 30 if imageless_mode else 15
    page_count = _count_pdf_pages(file_bytes)
    if page_count and page_count > max_pages:
        logger.warning(
            "Document AI: PDF has %d pages (limit %d for online processing), skipping",
            page_count, max_pages,
        )
        return None

    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("DOCAI_LOCATION", "us")
    processor_id = os.getenv("DOCAI_FORM_PARSER_ID")
    processor_name = f"projects/{project_id}/locations/{location}/processors/{processor_id}"

    try:
        from google.cloud import documentai

        raw_document = documentai.RawDocument(content=file_bytes, mime_type=mime_type)
        request = documentai.ProcessRequest(
            name=processor_name, raw_document=raw_document
        )
        if imageless_mode:
            request.imageless_mode = True
        result = client.process_document(request=request, timeout=60.0)
        document = result.document

        # Extract entities (key-value pairs from the form)
        entities = []
        for entity in document.entities:
            page_num = 0
            if entity.page_anchor and entity.page_anchor.page_refs:
                page_num = int(entity.page_anchor.page_refs[0].page)
            entities.append({
                "type": entity.type_,
                "value": entity.mention_text,
                "confidence": entity.confidence,
                "page": page_num,
            })

        # Extract pages with blocks and tables
        pages = []
        for i, page in enumerate(document.pages):
            blocks = []
            for block in page.blocks:
                block_text = _get_text_from_layout(block.layout, document.text)
                if block_text.strip():
                    blocks.append({"text": block_text, "type": "paragraph"})
            for table in page.tables:
                table_text = _format_table(table, document.text)
                if table_text.strip():
                    blocks.append({"text": table_text, "type": "table"})

            page_text = _get_text_from_layout(page.layout, document.text)
            pages.append({
                "page_number": i + 1,
                "text": page_text,
                "blocks": blocks,
            })

        # Extract tables at document level
        tables = []
        for page in document.pages:
            for table in page.tables:
                headers = []
                for row in table.header_rows:
                    headers.extend(
                        _get_text_from_layout(cell.layout, document.text).strip()
                        for cell in row.cells
                    )
                body_rows = []
                for row in table.body_rows:
                    body_rows.append([
                        _get_text_from_layout(cell.layout, document.text).strip()
                        for cell in row.cells
                    ])
                tables.append({"headers": headers, "rows": body_rows})

        logger.info(
            "Document AI Form Parser: %d pages, %d entities, %d tables",
            len(pages), len(entities), len(tables),
        )

        return {
            "text": document.text,
            "entities": entities,
            "tables": tables,
            "pages": pages,
        }

    except Exception as exc:
        sentry_sdk.capture_exception(exc)
        logger.warning("Document AI Form Parser failed: %s", exc)
        return None


def extract_with_ocr(
    file_bytes: bytes,
    mime_type: str = "application/pdf",
    *,
    imageless_mode: bool = False,
) -> dict | None:
    """
    Send PDF to Document AI OCR processor for high-quality text extraction.

    Returns dict with text and pages — or None on error.
    """
    client = _get_client()
    if client is None:
        return None

    # Check page limit — imageless mode allows up to 30 pages
    max_pages = 30 if imageless_mode else 15
    page_count = _count_pdf_pages(file_bytes)
    if page_count and page_count > max_pages:
        logger.warning(
            "Document AI: PDF has %d pages (limit %d for online processing), skipping",
            page_count, max_pages,
        )
        return None

    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("DOCAI_LOCATION", "us")
    processor_id = os.getenv("DOCAI_OCR_PROCESSOR_ID")
    processor_name = f"projects/{project_id}/locations/{location}/processors/{processor_id}"

    try:
        from google.cloud import documentai

        raw_document = documentai.RawDocument(content=file_bytes, mime_type=mime_type)
        request = documentai.ProcessRequest(
            name=processor_name, raw_document=raw_document
        )
        if imageless_mode:
            request.imageless_mode = True
        result = client.process_document(request=request, timeout=60.0)
        document = result.document

        pages = []
        for i, page in enumerate(document.pages):
            page_text = _get_text_from_layout(page.layout, document.text)
            confidence = page.layout.confidence if page.layout else 0.0
            pages.append({
                "page_number": i + 1,
                "text": page_text,
                "confidence": confidence,
            })

        logger.info("Document AI OCR: %d pages extracted", len(pages))

        return {
            "text": document.text,
            "pages": pages,
        }

    except Exception as exc:
        sentry_sdk.capture_exception(exc)
        logger.warning("Document AI OCR failed: %s", exc)
        return None


def extract_with_strategy(
    file_bytes: bytes,
    document_type: str | None,
) -> dict | None:
    """
    Top-level DocAI strategy dispatcher. Routes by page count:
      - 0-30 pages: online (with imageless_mode=True)
      - 31-200 pages: batch via GCS (if USE_DOCAI_BATCH flag on, else None)
      - >200 pages: raises DocAITooLarge

    Returns the same dict | None contract as the online extractors:
      {"text": str, "pages": list[dict], ...}

    Callers should treat None as "no DocAI result, fall back to pdfplumber"
    and catch DocAITooLarge separately to surface a clear UX message.
    """
    if not is_available():
        return None

    page_count = _count_pdf_pages(file_bytes)
    if page_count is None:
        # Could not count pages — fail safe by treating as unsupported.
        logger.warning("Document AI: could not count PDF pages, skipping DocAI")
        return None

    doc_type_norm = (document_type or "").lower()
    is_financial = doc_type_norm in FINANCIAL_DOC_TYPES

    # Online tier (0-30 pages, imageless_mode extends limit from 15 to 30)
    if page_count <= 30:
        logger.info(
            "DocAI strategy: %d pages -> online (%s), imageless_mode=True",
            page_count, "form_parser" if is_financial else "ocr",
        )
        if is_financial:
            return extract_with_form_parser(file_bytes, imageless_mode=True)
        return extract_with_ocr(file_bytes, imageless_mode=True)

    # Batch tier (31-200 pages)
    if page_count <= 200:
        if not USE_DOCAI_BATCH:
            logger.info(
                "DocAI strategy: %d pages requires batch but USE_DOCAI_BATCH=false; returning None",
                page_count,
            )
            return None

        # Batch uses OCR processor only for v1 (Session 3 validated this shape).
        # Form Parser batch upgrade is a future enhancement.
        project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        location = os.getenv("DOCAI_LOCATION", "us")
        ocr_processor_id = os.getenv("DOCAI_OCR_PROCESSOR_ID")
        if not (project_id and ocr_processor_id):
            logger.warning(
                "DocAI strategy: batch requested but GOOGLE_CLOUD_PROJECT or "
                "DOCAI_OCR_PROCESSOR_ID not set; returning None"
            )
            return None

        processor_name = (
            f"projects/{project_id}/locations/{location}/processors/{ocr_processor_id}"
        )
        document_id = uuid.uuid4().hex

        # Import locally to avoid module-load-time dependency on google-cloud-storage
        # for deployments that don't use batch.
        from app.services.batch_extractor import BatchExtractor, DocAIBatchError

        logger.info(
            "DocAI strategy: %d pages -> batch (OCR), document_id=%s",
            page_count, document_id,
        )
        try:
            extractor = BatchExtractor()
            return extractor.extract(
                file_bytes=file_bytes,
                document_id=document_id,
                processor_name=processor_name,
            )
        except DocAIBatchError as exc:
            logger.warning(
                "DocAI batch failed for document_id=%s: %s: %s",
                document_id, type(exc).__name__, exc,
            )
            return None

    # Splitting tier (>200 pages) — future work
    raise DocAITooLarge(
        f"Document is {page_count} pages; max supported is 200."
    )

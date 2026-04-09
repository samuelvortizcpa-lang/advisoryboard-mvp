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

import sentry_sdk

logger = logging.getLogger(__name__)

_client = None


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
    file_bytes: bytes, mime_type: str = "application/pdf"
) -> dict | None:
    """
    Send PDF to Document AI Form Parser for structured extraction.

    Returns dict with text, entities, tables, pages — or None on error.
    """
    client = _get_client()
    if client is None:
        return None

    # Check page limit (online processing max 15 pages)
    page_count = _count_pdf_pages(file_bytes)
    if page_count and page_count > 15:
        logger.warning(
            "Document AI: PDF has %d pages (limit 15 for online processing), skipping",
            page_count,
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
    file_bytes: bytes, mime_type: str = "application/pdf"
) -> dict | None:
    """
    Send PDF to Document AI OCR processor for high-quality text extraction.

    Returns dict with text and pages — or None on error.
    """
    client = _get_client()
    if client is None:
        return None

    # Check page limit
    page_count = _count_pdf_pages(file_bytes)
    if page_count and page_count > 15:
        logger.warning(
            "Document AI: PDF has %d pages (limit 15 for online processing), skipping",
            page_count,
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

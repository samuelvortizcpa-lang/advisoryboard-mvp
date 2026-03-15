"""
Page image service: converts PDF pages to JPEG images, uploads them to
Supabase Storage, generates Gemini multimodal embeddings, and stores
the results in the document_page_images table.

This entire pipeline is best-effort — failures are logged but never
prevent the main text-based RAG pipeline from completing.
"""

from __future__ import annotations

import asyncio
import gc
import io
import logging
import os
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.document_page_image import DocumentPageImage
from app.services import gemini_embeddings, storage_service

logger = logging.getLogger(__name__)

MAX_PAGES = 200       # Safety cap for truly enormous PDFs
JPEG_QUALITY = 85     # JPEG compression quality
DPI = 100             # Render resolution (balances quality vs memory usage)


def _process_single_page(temp_path: str, page_num: int, doc_label: str) -> tuple[bytes, str | None]:
    """
    Synchronous CPU-heavy work for a single page: render + OCR + JPEG encode.

    Returns (jpeg_bytes, text_preview).  Runs in a thread pool so the async
    event loop stays free to serve HTTP requests.
    """
    from pdf2image import convert_from_path
    import pytesseract

    images = convert_from_path(
        temp_path,
        first_page=page_num,
        last_page=page_num,
        dpi=DPI,
        fmt="jpeg",
        thread_count=2,
    )
    image = images[0]

    # OCR this page for text preview
    text_preview = None
    try:
        raw = pytesseract.image_to_string(image) or ""
        text_preview = raw[:500] if raw.strip() else None
    except Exception as ocr_exc:
        logger.warning(
            "Page images: Tesseract OCR failed for %s page %d: %s",
            doc_label, page_num, ocr_exc,
        )

    # Convert PIL image to JPEG bytes
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=JPEG_QUALITY)
    jpeg_bytes = buf.getvalue()

    # Explicitly free memory
    image.close()
    del image, images
    gc.collect()

    return jpeg_bytes, text_preview


async def process_page_images(db: Session, document: Document) -> None:
    """
    Extract page images from a PDF document, upload to Supabase, and store
    in the database.  Gemini embeddings are generated when available but are
    optional — page images are always stored so the frontend can display them
    even without Gemini.

    Skips silently if the document is not a PDF.
    """
    if document.file_type != "pdf":
        return

    # TODO: Re-enable when Gemini embedding model is updated.
    # gemini-embedding-exp-03-07 returns 404 on every call, wasting time
    # and cluttering logs with failed API calls per page.
    gemini_available = False

    doc_label = f"{document.id} ({document.filename!r})"
    logger.info(
        "Page images: starting extraction for %s (file_type=%s, gemini=%s)",
        doc_label, document.file_type, gemini_available,
    )

    temp_path = None
    try:
        # 1. Download PDF to temp file
        logger.info("Page images: downloading PDF from storage: %s", document.file_path)
        temp_path = storage_service.get_temp_local_path(document.file_path)
        logger.info("Page images: downloaded to temp file: %s", temp_path)

        # 2. Get total page count without loading images into memory
        from pdf2image import pdfinfo_from_path

        info = pdfinfo_from_path(temp_path)
        total_pages = info["Pages"]
        pages_to_process = min(total_pages, MAX_PAGES)

        logger.info("Page images: PDF has %d pages, will process %d", total_pages, pages_to_process)

        if total_pages > MAX_PAGES:
            logger.warning(
                "Page images: %s has %d pages, capping at %d",
                doc_label, total_pages, MAX_PAGES,
            )

        # 3. Delete any existing page images for this document (handles re-processing)
        db.query(DocumentPageImage).filter(
            DocumentPageImage.document_id == document.id
        ).delete()
        db.flush()

        # 4. Process each page ONE AT A TIME to avoid OOM
        #    CPU-heavy work (pdf2image + Tesseract) runs in a thread pool
        #    so the async event loop stays free to serve HTTP requests.
        page_image_rows: list[DocumentPageImage] = []

        for page_num in range(1, pages_to_process + 1):
            try:
                logger.info(
                    "Page images: processing page %d/%d for document %s",
                    page_num, pages_to_process, document.id,
                )

                # Run CPU-heavy render + OCR in thread pool
                jpeg_bytes, text_preview = await asyncio.to_thread(
                    _process_single_page, temp_path, page_num, doc_label
                )

                # Upload to Supabase Storage (I/O, not CPU — fine in event loop)
                storage_path = f"page_images/{document.id}/page_{page_num}.jpg"
                try:
                    storage_service.upload_file_to_path(
                        storage_path, jpeg_bytes, "image/jpeg"
                    )
                    logger.info(
                        "Page images: uploaded page %d/%d for %s (%d bytes)",
                        page_num, pages_to_process, doc_label, len(jpeg_bytes),
                    )
                except Exception as upload_exc:
                    logger.warning(
                        "Page images: upload failed for %s page %d: %s",
                        doc_label, page_num, upload_exc,
                    )
                    continue

                if text_preview:
                    logger.info(
                        "Page images: page text preview stored for page %d (%d chars)",
                        page_num, len(text_preview),
                    )

                page_image_rows.append(
                    DocumentPageImage(
                        document_id=document.id,
                        page_number=page_num,
                        image_path=storage_path,
                        image_embedding=None,
                        page_text_preview=text_preview,
                    )
                )

            except Exception as e:
                logger.error(
                    "Failed to process page %d of document %s: %s",
                    page_num, document.id, e,
                )
                continue

        # 5. Bulk save
        if page_image_rows:
            db.bulk_save_objects(page_image_rows)
            db.commit()

        logger.info(
            "Completed page image generation for document %s: %d/%d pages processed",
            document.id, len(page_image_rows), total_pages,
        )

    except Exception as exc:
        logger.error("Page images: failed for %s: %s", doc_label, exc)
        db.rollback()
        raise

    finally:
        if temp_path:
            try:
                os.unlink(temp_path)
            except OSError:
                pass

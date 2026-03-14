"""
Page image service: converts PDF pages to JPEG images, uploads them to
Supabase Storage, generates Gemini multimodal embeddings, and stores
the results in the document_page_images table.

This entire pipeline is best-effort — failures are logged but never
prevent the main text-based RAG pipeline from completing.
"""

from __future__ import annotations

import io
import logging
import os
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.document_page_image import DocumentPageImage
from app.services import gemini_embeddings, storage_service

logger = logging.getLogger(__name__)

MAX_PAGES = 50        # Cap to prevent runaway processing on large PDFs
JPEG_QUALITY = 85     # JPEG compression quality
DPI = 150             # Render resolution (balances quality vs file size)


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

    gemini_available = gemini_embeddings.is_available()

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

        # 2. Convert pages to PIL images (used for both OCR and JPEG upload)
        from pdf2image import convert_from_path
        import pytesseract

        pil_images = convert_from_path(
            temp_path,
            dpi=DPI,
            fmt="jpeg",
            thread_count=2,
        )

        # 2a. Extract per-page text using Tesseract OCR on the rendered images.
        # This produces accurate text that matches what's visually on each page,
        # unlike pdfplumber which garbles IRS form text and misassigns content.
        page_texts: dict[int, str] = {}  # 1-indexed page_number → text preview
        for pg_idx, pil_img in enumerate(pil_images):
            pg_num = pg_idx + 1
            try:
                raw = pytesseract.image_to_string(pil_img) or ""
                page_texts[pg_num] = raw[:500]
            except Exception as ocr_exc:
                logger.warning(
                    "Page images: Tesseract OCR failed for %s page %d: %s",
                    doc_label, pg_num, ocr_exc,
                )
        if page_texts:
            logger.info(
                "Page images: OCR text previews extracted for %d pages of %s",
                len(page_texts), doc_label,
            )

        total_pages = len(pil_images)
        pages_to_process = min(total_pages, MAX_PAGES)
        logger.info("Page images: converted PDF to %d page image(s)", total_pages)

        if total_pages > MAX_PAGES:
            logger.info(
                "Page images: %s has %d pages, capping at %d",
                doc_label, total_pages, MAX_PAGES,
            )

        # 3. Delete any existing page images for this document (handles re-processing)
        db.query(DocumentPageImage).filter(
            DocumentPageImage.document_id == document.id
        ).delete()
        db.flush()

        # 4. Process each page
        page_image_rows: list[DocumentPageImage] = []

        for page_idx in range(pages_to_process):
            page_number = page_idx + 1  # 1-indexed
            pil_img = pil_images[page_idx]

            # Convert PIL image to JPEG bytes
            buf = io.BytesIO()
            pil_img.save(buf, format="JPEG", quality=JPEG_QUALITY)
            jpeg_bytes = buf.getvalue()

            # Upload to Supabase Storage
            storage_path = f"page_images/{document.id}/page_{page_number}.jpg"
            try:
                storage_service.upload_file_to_path(
                    storage_path, jpeg_bytes, "image/jpeg"
                )
                logger.info(
                    "Page images: uploaded page %d/%d for %s (%d bytes)",
                    page_number, pages_to_process, doc_label, len(jpeg_bytes),
                )
            except Exception as upload_exc:
                logger.warning(
                    "Page images: upload failed for %s page %d: %s",
                    doc_label, page_number, upload_exc,
                )
                continue

            # Generate Gemini embedding (optional — images are stored regardless)
            embedding = None
            if gemini_available:
                try:
                    embedding = gemini_embeddings.embed_image(jpeg_bytes)
                    logger.info(
                        "Page images: embedded page %d for %s (768-dim vector)",
                        page_number, doc_label,
                    )
                except Exception as embed_exc:
                    logger.warning(
                        "Page images: embedding failed for %s page %d: %s",
                        doc_label, page_number, embed_exc,
                    )

            text_preview = page_texts.get(page_number)
            if text_preview:
                logger.info(
                    "Page images: page text preview stored for page %d (%d chars)",
                    page_number, len(text_preview),
                )

            page_image_rows.append(
                DocumentPageImage(
                    document_id=document.id,
                    page_number=page_number,
                    image_path=storage_path,
                    image_embedding=embedding,
                    page_text_preview=text_preview,
                )
            )

        # 5. Bulk save
        if page_image_rows:
            db.bulk_save_objects(page_image_rows)
            db.commit()

        logger.info(
            "Page images: finished %s — %d/%d pages stored",
            doc_label, len(page_image_rows), pages_to_process,
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

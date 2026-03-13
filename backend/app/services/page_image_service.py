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
    Extract page images from a PDF document, upload to Supabase, embed with
    Gemini, and store in the database.

    Skips silently if:
    - Document is not a PDF
    - Gemini API is not configured
    """
    if document.file_type != "pdf":
        return

    if not gemini_embeddings.is_available():
        logger.info(
            "Page images: skipping %s — Gemini API not configured",
            document.id,
        )
        return

    doc_label = f"{document.id} ({document.filename!r})"
    logger.info("Page images: starting extraction for %s (file_type=%s)", doc_label, document.file_type)

    temp_path = None
    try:
        # 1. Download PDF to temp file
        logger.info("Page images: downloading PDF from storage: %s", document.file_path)
        temp_path = storage_service.get_temp_local_path(document.file_path)
        logger.info("Page images: downloaded to temp file: %s", temp_path)

        # 2. Convert pages to PIL images
        from pdf2image import convert_from_path

        pil_images = convert_from_path(
            temp_path,
            dpi=DPI,
            fmt="jpeg",
            thread_count=2,
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

            # Generate Gemini embedding
            embedding = None
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

            page_image_rows.append(
                DocumentPageImage(
                    document_id=document.id,
                    page_number=page_number,
                    image_path=storage_path,
                    image_embedding=embedding,
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

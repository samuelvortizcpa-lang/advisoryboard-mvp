"""
Batch document reprocessing service.

Re-runs the RAG pipeline (extract → chunk → embed) on existing documents
so they benefit from improved chunking and hybrid search.

Progress is tracked in-memory via REPROCESS_TASKS dict.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.document_chunk import DocumentChunk

logger = logging.getLogger(__name__)

# ── In-memory progress tracking ─────────────────────────────────────────────

REPROCESS_TASKS: dict[str, dict[str, Any]] = {}


def _new_task(total: int) -> str:
    task_id = str(uuid.uuid4())
    REPROCESS_TASKS[task_id] = {
        "task_id": task_id,
        "total": total,
        "completed": 0,
        "errors": [],
        "status": "running",
        "started_at": time.time(),
    }
    return task_id


def get_task_status(task_id: str) -> dict[str, Any] | None:
    task = REPROCESS_TASKS.get(task_id)
    if not task:
        return None
    # Add elapsed time
    result = dict(task)
    result["elapsed_seconds"] = round(time.time() - task["started_at"], 1)
    return result


# ── Background reprocessing ──────────────────────────────────────────────────


async def reprocess_documents(
    document_ids: list[UUID],
    task_id: str,
) -> None:
    """
    Reprocess a list of documents in the background.

    Each document goes through the full pipeline: extract → chunk → embed.
    Uses its own DB session since this runs after the HTTP response.
    """
    from app.core.database import SessionLocal
    from app.services.rag_service import process_document

    task = REPROCESS_TASKS[task_id]

    for doc_id in document_ids:
        db: Session = SessionLocal()
        try:
            document = db.query(Document).filter(Document.id == doc_id).first()
            if not document:
                task["errors"].append({"document_id": str(doc_id), "error": "Not found"})
                task["completed"] += 1
                continue

            # Count old chunks before reprocessing
            old_count = (
                db.query(DocumentChunk)
                .filter(DocumentChunk.document_id == doc_id)
                .count()
            )

            # Reset processed flag so pipeline runs fully
            document.processed = False
            document.processing_error = None
            db.commit()

            # Run the full pipeline (extract → classify → chunk → embed)
            await process_document(db, document)

            new_count = (
                db.query(DocumentChunk)
                .filter(DocumentChunk.document_id == doc_id)
                .count()
            )

            logger.info(
                "Reprocessed document %s (%s): %d → %d chunks",
                document.filename, doc_id, old_count, new_count,
            )

            task["completed"] += 1

        except Exception as exc:
            logger.error("Reprocess failed for %s: %s", doc_id, exc, exc_info=True)
            task["errors"].append({
                "document_id": str(doc_id),
                "error": str(exc)[:500],
            })
            task["completed"] += 1

            # Mark document processed with error so it doesn't stay stuck
            try:
                doc = db.query(Document).filter(Document.id == doc_id).first()
                if doc and not doc.processed:
                    doc.processed = True
                    doc.processing_error = f"Reprocessing failed: {str(exc)[:300]}"
                    db.commit()
            except Exception:
                logger.exception("Could not update stuck document %s", doc_id)
        finally:
            db.close()

        # Rate-limit between documents to avoid OpenAI API throttling
        await asyncio.sleep(1.0)

    task["status"] = "failed" if task["errors"] else "complete"
    logger.info(
        "Reprocess task %s finished: %d/%d completed, %d errors",
        task_id, task["completed"], task["total"], len(task["errors"]),
    )

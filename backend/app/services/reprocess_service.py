"""
Batch document reprocessing service.

Re-runs the RAG pipeline (extract → chunk → embed) on existing documents
so they benefit from improved chunking and hybrid search.

Progress is tracked in the Postgres ``reprocess_tasks`` table (see
AdvisoryBoard_DocAI_Batch_Architecture.md §3.5). Public API is unchanged
from the prior in-memory implementation — callers in app.api.admin do
not need to change.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.document import Document
from app.models.document_chunk import DocumentChunk

logger = logging.getLogger(__name__)

# ── Postgres-backed progress tracking ───────────────────────────────────────


def _new_task(total: int) -> str:
    """Create a new reprocess task row. Returns the task_id as a string."""
    task_id = str(uuid.uuid4())
    db: Session = SessionLocal()
    try:
        db.execute(
            text(
                "INSERT INTO reprocess_tasks (task_id, total) "
                "VALUES (CAST(:tid AS uuid), :total)"
            ),
            {"tid": task_id, "total": total},
        )
        db.commit()
    finally:
        db.close()
    return task_id


def get_task_status(task_id: str) -> dict[str, Any] | None:
    """
    Read task status. Returns None if the task_id is not found.

    Returned dict shape matches the prior in-memory implementation:
    {task_id, total, completed, errors, status, started_at, elapsed_seconds}.
    ``started_at`` is a Unix epoch float for backward compatibility with
    any existing frontend polling logic.
    """
    db: Session = SessionLocal()
    try:
        row = db.execute(
            text(
                "SELECT task_id, total, completed, errors, status, "
                "       EXTRACT(EPOCH FROM started_at) AS started_epoch "
                "FROM reprocess_tasks "
                "WHERE task_id = CAST(:tid AS uuid)"
            ),
            {"tid": task_id},
        ).mappings().first()
    finally:
        db.close()

    if row is None:
        return None

    started_epoch = float(row["started_epoch"])
    return {
        "task_id": str(row["task_id"]),
        "total": row["total"],
        "completed": row["completed"],
        "errors": row["errors"],
        "status": row["status"],
        "started_at": started_epoch,
        "elapsed_seconds": round(time.time() - started_epoch, 1),
    }


def _increment_completed(task_id: str) -> None:
    """Atomically bump the completed counter (success path)."""
    db: Session = SessionLocal()
    try:
        db.execute(
            text(
                "UPDATE reprocess_tasks "
                "SET completed = completed + 1, updated_at = now() "
                "WHERE task_id = CAST(:tid AS uuid)"
            ),
            {"tid": task_id},
        )
        db.commit()
    finally:
        db.close()


def _fail_one(task_id: str, error: dict[str, Any]) -> None:
    """
    Record one document's failure atomically: append error and bump
    completed in a single UPDATE. Prevents split-state if the process
    dies between the two mutations.
    """
    db: Session = SessionLocal()
    try:
        db.execute(
            text(
                "UPDATE reprocess_tasks "
                "SET errors = errors || CAST(:err AS jsonb), "
                "    completed = completed + 1, "
                "    updated_at = now() "
                "WHERE task_id = CAST(:tid AS uuid)"
            ),
            {"err": json.dumps(error), "tid": task_id},
        )
        db.commit()
    finally:
        db.close()


def _finalize_task(task_id: str) -> dict[str, Any] | None:
    """
    Transition the task to its terminal status atomically and return the
    final counters for logging. Status = 'failed' if any errors were
    recorded, else 'complete'. One round trip; no read-then-write race.

    Returns dict {status, completed, total, n_errors} or None if the
    task row has vanished.
    """
    db: Session = SessionLocal()
    try:
        row = db.execute(
            text(
                "UPDATE reprocess_tasks "
                "SET status = CASE "
                "        WHEN jsonb_array_length(errors) > 0 THEN 'failed' "
                "        ELSE 'complete' "
                "    END, "
                "    updated_at = now() "
                "WHERE task_id = CAST(:tid AS uuid) "
                "RETURNING status, completed, total, "
                "          jsonb_array_length(errors) AS n_errors"
            ),
            {"tid": task_id},
        ).mappings().first()
        db.commit()
    finally:
        db.close()

    if row is None:
        return None
    return {
        "status": row["status"],
        "completed": row["completed"],
        "total": row["total"],
        "n_errors": row["n_errors"],
    }


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
    from app.services.rag_service import process_document

    for doc_id in document_ids:
        db: Session = SessionLocal()
        try:
            document = db.query(Document).filter(Document.id == doc_id).first()
            if not document:
                _fail_one(task_id, {
                    "document_id": str(doc_id),
                    "error": "Not found",
                })
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

            _increment_completed(task_id)

        except Exception as exc:
            logger.error(
                "Reprocess failed for %s: %s", doc_id, exc, exc_info=True,
            )
            _fail_one(task_id, {
                "document_id": str(doc_id),
                "error": str(exc)[:500],
            })

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

    # Terminal status via atomic UPDATE ... RETURNING (one round trip)
    final = _finalize_task(task_id)
    if final is None:
        logger.error(
            "Reprocess task %s vanished from DB before completion", task_id,
        )
        return

    logger.info(
        "Reprocess task %s finished: %d/%d completed, %d errors",
        task_id, final["completed"], final["total"], final["n_errors"],
    )

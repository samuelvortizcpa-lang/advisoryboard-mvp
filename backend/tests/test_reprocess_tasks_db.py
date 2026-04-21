"""
Integration tests for reprocess_tasks Postgres-backed state.

These tests hit the REAL local dev Postgres via SessionLocal — the
refactored reprocess_service uses Postgres-specific features
(jsonb_array_length, CAST AS uuid, jsonb concatenation) that cannot
run against the conftest's SQLite in-memory fixtures.

Tests are self-contained: no db/engine fixture parameters. They call
the service helpers directly, which internally open real DB sessions
against whatever DATABASE_URL resolves to (local dev Postgres).

Each test cleans up its own rows via raw DELETE to avoid cross-test
contamination. Tests are safe to run in any order.

Run just this file:
    pytest tests/test_reprocess_tasks_db.py -v

Or exclude from a default pytest run:
    pytest -m "not integration"
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import text

from app.core.database import SessionLocal
from app.services.reprocess_service import (
    _fail_one,
    _finalize_task,
    _increment_completed,
    _new_task,
    get_task_status,
)

pytestmark = pytest.mark.integration


# ── Helpers ─────────────────────────────────────────────────────────────────


def _delete_task(task_id: str) -> None:
    """Remove a task row by id. Safe to call on non-existent ids."""
    db = SessionLocal()
    try:
        db.execute(
            text("DELETE FROM reprocess_tasks WHERE task_id = CAST(:tid AS uuid)"),
            {"tid": task_id},
        )
        db.commit()
    finally:
        db.close()


# ── Tests ───────────────────────────────────────────────────────────────────


def test_create_and_read():
    """_new_task inserts with defaults; get_task_status round-trips shape."""
    tid = _new_task(total=3)
    try:
        status = get_task_status(tid)
        assert status is not None
        assert status["task_id"] == tid
        assert status["total"] == 3
        assert status["completed"] == 0
        assert status["errors"] == []
        assert status["status"] == "running"
        assert isinstance(status["started_at"], float)
        assert status["started_at"] > 0
        assert "elapsed_seconds" in status
        assert status["elapsed_seconds"] >= 0
    finally:
        _delete_task(tid)


def test_get_status_missing_returns_none():
    """Non-existent task_id returns None, not an exception."""
    missing_id = "00000000-0000-0000-0000-000000000000"
    assert get_task_status(missing_id) is None


def test_increment_completed():
    """_increment_completed bumps the counter atomically."""
    tid = _new_task(total=5)
    try:
        _increment_completed(tid)
        _increment_completed(tid)
        status = get_task_status(tid)
        assert status["completed"] == 2
        assert status["errors"] == []
        assert status["status"] == "running"
    finally:
        _delete_task(tid)


def test_fail_one_is_atomic():
    """
    _fail_one appends error AND increments completed in a single UPDATE.
    If this were two commits and the process died between them, we'd see
    either completed+1 with no error recorded, or error recorded with
    completed unchanged. The single-UPDATE design makes both impossible.
    """
    tid = _new_task(total=3)
    try:
        _fail_one(tid, {"document_id": "doc-A", "error": "boom"})
        _fail_one(tid, {"document_id": "doc-B", "error": "kaboom"})

        status = get_task_status(tid)
        assert status["completed"] == 2
        assert len(status["errors"]) == 2
        # Both error dicts should be preserved verbatim
        error_docs = {e["document_id"] for e in status["errors"]}
        assert error_docs == {"doc-A", "doc-B"}
        # Status stays 'running' — only _finalize_task transitions it
        assert status["status"] == "running"
    finally:
        _delete_task(tid)


def test_finalize_transitions_to_complete_when_no_errors():
    """If no errors recorded, _finalize_task sets status='complete'."""
    tid = _new_task(total=2)
    try:
        _increment_completed(tid)
        _increment_completed(tid)
        result = _finalize_task(tid)
        assert result is not None
        assert result["status"] == "complete"
        assert result["completed"] == 2
        assert result["total"] == 2
        assert result["n_errors"] == 0

        # Post-finalize read must match
        status = get_task_status(tid)
        assert status["status"] == "complete"
    finally:
        _delete_task(tid)


def test_finalize_transitions_to_failed_when_errors_present():
    """If any errors recorded, _finalize_task sets status='failed'."""
    tid = _new_task(total=2)
    try:
        _increment_completed(tid)
        _fail_one(tid, {"document_id": "doc-X", "error": "nope"})
        result = _finalize_task(tid)
        assert result["status"] == "failed"
        assert result["completed"] == 2
        assert result["total"] == 2
        assert result["n_errors"] == 1

        status = get_task_status(tid)
        assert status["status"] == "failed"
        assert len(status["errors"]) == 1
        assert status["errors"][0]["document_id"] == "doc-X"
    finally:
        _delete_task(tid)


def test_finalize_missing_task_returns_none():
    """Calling _finalize_task on a non-existent id returns None safely."""
    missing_id = "00000000-0000-0000-0000-000000000001"
    assert _finalize_task(missing_id) is None


@pytest.mark.asyncio
async def test_concurrent_increments_are_race_safe():
    """
    Under real concurrency (10 parallel asyncio.to_thread increments),
    all increments must land. The UPDATE ... SET completed = completed + 1
    is atomic at the SQL level, so no lost updates even with interleaved
    connections from the pool.

    This mirrors how reprocess_documents runs under asyncio in production.
    """
    tid = _new_task(total=10)
    try:
        await asyncio.gather(*[
            asyncio.to_thread(_increment_completed, tid) for _ in range(10)
        ])
        status = get_task_status(tid)
        assert status["completed"] == 10, (
            f"Expected 10 concurrent increments to all land, got "
            f"{status['completed']}. Possible lost update."
        )
        assert status["status"] == "running"
    finally:
        _delete_task(tid)


def test_full_lifecycle_9_steps():
    """
    Full end-to-end lifecycle mirroring the hand-run smoke test from
    Phase 3b execution. Exercises create → read → success → fail →
    finalize → post-read → missing-id → cleanup → residue-check as a
    single regression guard against any future change that breaks the
    integration across helpers.
    """
    # 1. Create
    tid = _new_task(total=2)

    try:
        # 2. Initial read
        s1 = get_task_status(tid)
        assert s1["total"] == 2
        assert s1["completed"] == 0
        assert s1["errors"] == []
        assert s1["status"] == "running"

        # 3. One success
        _increment_completed(tid)
        s2 = get_task_status(tid)
        assert s2["completed"] == 1
        assert s2["errors"] == []
        assert s2["status"] == "running"

        # 4. One failure (atomic)
        _fail_one(tid, {"document_id": "lifecycle-test", "error": "simulated"})
        s3 = get_task_status(tid)
        assert s3["completed"] == 2
        assert len(s3["errors"]) == 1
        assert s3["errors"][0]["document_id"] == "lifecycle-test"
        assert s3["status"] == "running"

        # 5. Finalize → failed (because errors > 0)
        final = _finalize_task(tid)
        assert final["status"] == "failed"
        assert final["completed"] == 2
        assert final["total"] == 2
        assert final["n_errors"] == 1

        # 6. Post-finalize read
        s4 = get_task_status(tid)
        assert s4["status"] == "failed"

        # 7. Missing id returns None
        assert get_task_status(str(uuid.uuid4())) is None

    finally:
        # 8. Cleanup
        _delete_task(tid)

    # 9. Confirm this task_id is no longer in the table
    assert get_task_status(tid) is None

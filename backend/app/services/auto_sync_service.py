"""
Scheduled auto-sync service: runs all active integration connections
on a recurring schedule using APScheduler.

Architecture:
  - APScheduler's AsyncIOScheduler runs in the same process as FastAPI
  - Each sync gets its own database session (short-lived transactions)
  - A per-connection lock prevents overlapping syncs for the same connection
  - Only one worker process runs the scheduler (controlled by AUTO_SYNC_WORKER env)

Usage:
  main.py calls start_scheduler() on app startup and stop_scheduler() on shutdown.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models.integration_connection import IntegrationConnection

logger = logging.getLogger(__name__)

# Minimum time between syncs for a single connection (seconds)
MIN_SYNC_INTERVAL = timedelta(minutes=15)

# Default sync parameters for scheduled syncs (small incremental batches)
_SYNC_DEFAULTS = {
    "max_results": 20,
    "since_hours": 1,
    "days_back": 1,
}

# Track connections currently being synced (prevents overlapping syncs)
_syncing_connections: set[UUID] = set()

# Scheduler instance (module-level so start/stop can manage it)
_scheduler: Any = None

# Last run metadata
_last_run_at: Optional[datetime] = None
_last_run_summary: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# 1. Core sync loop
# ---------------------------------------------------------------------------

async def run_auto_sync(db: Optional[Session] = None) -> Dict[str, Any]:
    """
    Query all active connections and sync each one that's due.

    Creates its own DB session if none is provided.
    Returns a summary dict of the sync run.
    """
    global _last_run_at, _last_run_summary

    own_session = db is None
    if own_session:
        db = SessionLocal()

    summary: Dict[str, Any] = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "connections_checked": 0,
        "connections_synced": 0,
        "connections_skipped": 0,
        "connections_failed": 0,
        "details": [],
    }

    try:
        # Fetch all active connections
        connections = (
            db.query(IntegrationConnection)
            .filter(IntegrationConnection.is_active == True)
            .all()
        )
        summary["connections_checked"] = len(connections)

        for conn in connections:
            detail = await _sync_single_connection(conn, db)
            summary["details"].append(detail)

            if detail["status"] == "synced":
                summary["connections_synced"] += 1
            elif detail["status"] == "skipped":
                summary["connections_skipped"] += 1
            elif detail["status"] == "failed":
                summary["connections_failed"] += 1

    except Exception as exc:
        logger.exception("Auto-sync loop failed: %s", exc)
        summary["error"] = str(exc)
    finally:
        if own_session:
            db.close()

    summary["completed_at"] = datetime.now(timezone.utc).isoformat()

    _last_run_at = datetime.now(timezone.utc)
    _last_run_summary = summary

    logger.info(
        "Auto-sync completed: checked=%d synced=%d skipped=%d failed=%d",
        summary["connections_checked"],
        summary["connections_synced"],
        summary["connections_skipped"],
        summary["connections_failed"],
    )

    return summary


async def _sync_single_connection(
    conn: IntegrationConnection,
    db: Session,
) -> Dict[str, Any]:
    """
    Sync a single connection if it's due and not already running.

    Returns a detail dict describing what happened.
    """
    detail: Dict[str, Any] = {
        "connection_id": str(conn.id),
        "provider": conn.provider,
        "user_id": conn.user_id,
        "status": "skipped",
        "reason": None,
    }

    # ── Check if already syncing ──────────────────────────────────────────
    if conn.id in _syncing_connections:
        detail["reason"] = "sync already in progress"
        return detail

    # ── Check minimum interval ────────────────────────────────────────────
    now = datetime.now(timezone.utc)
    if conn.last_sync_at:
        # Ensure last_sync_at is timezone-aware
        last_sync = conn.last_sync_at
        if last_sync.tzinfo is None:
            last_sync = last_sync.replace(tzinfo=timezone.utc)
        elapsed = now - last_sync
        if elapsed < MIN_SYNC_INTERVAL:
            detail["reason"] = f"too soon ({elapsed.total_seconds():.0f}s since last sync)"
            return detail

    # ── Perform the sync ──────────────────────────────────────────────────
    _syncing_connections.add(conn.id)
    try:
        sync_log = await _dispatch_sync(conn, db)

        detail["status"] = "synced"
        if sync_log:
            detail["items_found"] = sync_log.emails_found
            detail["items_ingested"] = sync_log.emails_ingested
            detail["items_skipped"] = sync_log.emails_skipped
            detail["sync_log_status"] = sync_log.status

            logger.info(
                "Auto-sync %s for user %s: %d found, %d ingested",
                conn.provider,
                conn.user_id,
                sync_log.emails_found,
                sync_log.emails_ingested,
            )
    except Exception as exc:
        detail["status"] = "failed"
        detail["reason"] = str(exc)[:500]
        logger.warning(
            "Auto-sync failed for %s connection %s (user %s): %s",
            conn.provider, conn.id, conn.user_id, exc,
        )
    finally:
        _syncing_connections.discard(conn.id)

    return detail


async def _dispatch_sync(
    conn: IntegrationConnection,
    db: Session,
) -> Any:
    """
    Call the appropriate sync service based on the connection provider.

    Returns the SyncLog from the sync operation.
    """
    provider = conn.provider
    connection_id = conn.id
    user_id = conn.user_id
    max_results = _SYNC_DEFAULTS["max_results"]

    if provider == "google":
        from app.services import gmail_sync_service
        return await gmail_sync_service.sync_emails(
            connection_id=connection_id,
            user_id=user_id,
            db=db,
            sync_type="scheduled",
            max_results=max_results,
            since_hours=_SYNC_DEFAULTS["since_hours"],
        )

    elif provider == "microsoft":
        from app.services import outlook_sync_service
        return await outlook_sync_service.sync_emails(
            connection_id=connection_id,
            user_id=user_id,
            db=db,
            sync_type="scheduled",
            max_results=max_results,
            since_hours=_SYNC_DEFAULTS["since_hours"],
        )

    elif provider == "front":
        from app.services import front_sync_service
        return await front_sync_service.sync_conversations(
            connection_id=connection_id,
            user_id=user_id,
            db=db,
            sync_type="scheduled",
            max_results=max_results,
            since_hours=_SYNC_DEFAULTS["since_hours"],
        )

    elif provider == "zoom":
        from app.services import zoom_sync_service
        return await zoom_sync_service.sync_recordings(
            connection_id=connection_id,
            user_id=user_id,
            db=db,
            sync_type="scheduled",
            days_back=_SYNC_DEFAULTS["days_back"],
            max_results=max_results,
        )

    elif provider == "fathom":
        from app.services import fathom_sync_service
        return await fathom_sync_service.sync_calls(
            connection_id=connection_id,
            user_id=user_id,
            db=db,
            sync_type="scheduled",
            max_results=max_results,
            since_hours=_SYNC_DEFAULTS["since_hours"],
        )

    else:
        logger.warning("Auto-sync: unknown provider %r for connection %s", provider, conn.id)
        return None


# ---------------------------------------------------------------------------
# 2. Scheduler management
# ---------------------------------------------------------------------------

def start_scheduler() -> bool:
    """
    Start the APScheduler background scheduler.

    Returns True if the scheduler was started, False if skipped
    (disabled, wrong worker, or already running).
    """
    global _scheduler

    settings = get_settings()

    # Check if auto-sync is enabled (env var or settings)
    auto_sync_enabled = os.getenv("AUTO_SYNC_ENABLED", "true").lower() in ("true", "1", "yes")
    if not auto_sync_enabled or not settings.auto_sync_enabled:
        logger.info("Auto-sync disabled (AUTO_SYNC_ENABLED=%s, settings=%s)",
                     os.getenv("AUTO_SYNC_ENABLED"), settings.auto_sync_enabled)
        return False

    # Don't run in development unless explicitly enabled
    if settings.environment == "development":
        logger.info("Auto-sync disabled in development environment")
        return False

    # Multi-worker guard: only the designated worker runs the scheduler.
    # Set AUTO_SYNC_WORKER=true on exactly one worker process.
    # If not set, default to running (single-worker deployments).
    worker_flag = os.getenv("AUTO_SYNC_WORKER", "true").lower()
    if worker_flag not in ("true", "1", "yes"):
        logger.info("Auto-sync: this worker is not the scheduler worker (AUTO_SYNC_WORKER=%s)", worker_flag)
        return False

    if _scheduler is not None:
        logger.info("Auto-sync scheduler already running")
        return False

    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.interval import IntervalTrigger

        _scheduler = AsyncIOScheduler()
        _scheduler.add_job(
            _scheduled_sync_wrapper,
            trigger=IntervalTrigger(minutes=15),
            id="auto_sync",
            name="Auto-sync all integrations",
            replace_existing=True,
            max_instances=1,  # Don't overlap runs
        )
        _scheduler.start()
        logger.info("Auto-sync scheduler started (every 15 minutes)")
        return True

    except ImportError:
        logger.warning(
            "APScheduler not installed — auto-sync disabled. "
            "Install with: pip install apscheduler"
        )
        return False
    except Exception as exc:
        logger.exception("Failed to start auto-sync scheduler: %s", exc)
        return False


def stop_scheduler() -> None:
    """Cleanly shut down the scheduler if it's running."""
    global _scheduler

    if _scheduler is not None:
        try:
            _scheduler.shutdown(wait=False)
            logger.info("Auto-sync scheduler stopped")
        except Exception as exc:
            logger.warning("Error stopping auto-sync scheduler: %s", exc)
        finally:
            _scheduler = None


async def _scheduled_sync_wrapper() -> None:
    """
    Wrapper called by APScheduler on each tick.

    Creates a fresh DB session for each run (avoid long-lived sessions).
    """
    try:
        db = SessionLocal()
        try:
            await run_auto_sync(db)
        finally:
            db.close()
    except Exception as exc:
        logger.exception("Scheduled auto-sync wrapper failed: %s", exc)


# ---------------------------------------------------------------------------
# 3. Status helpers (for admin endpoints)
# ---------------------------------------------------------------------------

def get_scheduler_status() -> Dict[str, Any]:
    """Return the current scheduler status for admin endpoints."""
    status: Dict[str, Any] = {
        "scheduler_running": _scheduler is not None and _scheduler.running if _scheduler else False,
        "last_run_at": _last_run_at.isoformat() if _last_run_at else None,
        "last_run_summary": _last_run_summary,
        "active_syncs": [str(cid) for cid in _syncing_connections],
    }

    if _scheduler is not None and hasattr(_scheduler, "get_job"):
        job = _scheduler.get_job("auto_sync")
        if job:
            status["next_run_at"] = job.next_run_time.isoformat() if job.next_run_time else None
        else:
            status["next_run_at"] = None
    else:
        status["next_run_at"] = None

    return status

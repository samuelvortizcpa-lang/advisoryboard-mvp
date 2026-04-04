"""
Scheduled deadline reminder service.

Runs daily via APScheduler. Checks for action items with upcoming due dates
and sends reminder emails to assigned users who have reminders enabled.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta, timezone
from datetime import datetime as dt
from typing import Any

from app.core.database import SessionLocal
from app.models.action_item import ActionItem
from app.models.client import Client
from app.models.user import User
from app.services import notification_service

logger = logging.getLogger(__name__)

# Module-level scheduler
_scheduler: Any = None


# ---------------------------------------------------------------------------
# Core deadline check
# ---------------------------------------------------------------------------


def check_upcoming_deadlines() -> dict:
    """
    Query pending action items with due dates in the next 1-3 days,
    group by assignee, and send reminder emails.

    Returns a summary dict.
    """
    db = SessionLocal()
    try:
        today = date.today()
        # Look ahead up to 3 days (max reminder window)
        max_ahead = today + timedelta(days=3)

        items = (
            db.query(ActionItem)
            .filter(
                ActionItem.status == "pending",
                ActionItem.assigned_to.isnot(None),
                ActionItem.due_date.isnot(None),
                ActionItem.due_date >= today,
                ActionItem.due_date <= max_ahead,
            )
            .all()
        )

        # Group by assigned_to
        by_user: dict[str, list[ActionItem]] = {}
        for item in items:
            by_user.setdefault(item.assigned_to, []).append(item)

        emails_sent = 0

        for user_clerk_id, user_items in by_user.items():
            try:
                # Look up user email
                user = db.query(User).filter(User.clerk_id == user_clerk_id).first()
                if not user or not user.email:
                    continue

                # Determine org_id from the first item's client
                first_client = db.query(Client).filter(Client.id == user_items[0].client_id).first()
                if not first_client:
                    continue
                org_id = first_client.org_id

                # Check preferences
                prefs = notification_service.get_user_preferences(db, user_clerk_id, org_id)
                if prefs and not prefs.deadline_reminder:
                    continue

                reminder_days = prefs.deadline_reminder_days if prefs else 1
                target_date = today + timedelta(days=reminder_days)

                # Filter to items due on the target date
                matching = [
                    item for item in user_items
                    if item.due_date == target_date
                ]
                if not matching:
                    continue

                # Build task list for the email
                tasks = []
                for item in matching:
                    client = db.query(Client).filter(Client.id == item.client_id).first()
                    tasks.append({
                        "text": item.text,
                        "client_name": client.name if client else None,
                        "due_date": item.due_date,
                    })

                user_name = f"{user.first_name or ''} {user.last_name or ''}".strip() or "there"
                notification_service.send_deadline_reminder_email(
                    to_email=user.email,
                    to_name=user_name,
                    tasks=tasks,
                )
                emails_sent += 1

            except Exception:
                logger.exception("Failed to send deadline reminder to user %s", user_clerk_id)

        summary = {
            "items_checked": len(items),
            "users_checked": len(by_user),
            "emails_sent": emails_sent,
        }
        logger.info("Deadline reminder check: %s", summary)
        return summary

    finally:
        db.close()


# ---------------------------------------------------------------------------
# Scheduler management
# ---------------------------------------------------------------------------


def start_deadline_scheduler() -> bool:
    """Start a daily scheduler for deadline reminders. Returns True if started."""
    global _scheduler

    import os

    # Only run on the designated worker
    worker_flag = os.getenv("AUTO_SYNC_WORKER", "true").lower()
    if worker_flag not in ("true", "1", "yes"):
        return False

    if _scheduler is not None:
        return False

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger

        _scheduler = BackgroundScheduler()
        _scheduler.add_job(
            check_upcoming_deadlines,
            trigger=CronTrigger(hour=8, minute=0),
            id="deadline_reminders",
            name="Daily deadline reminder check",
            replace_existing=True,
        )
        _scheduler.start()
        logger.info("Deadline reminder scheduler started (daily at 08:00 UTC)")
        return True

    except ImportError:
        logger.warning("APScheduler not installed — deadline reminders disabled")
        return False
    except Exception as exc:
        logger.exception("Failed to start deadline scheduler: %s", exc)
        return False


def stop_deadline_scheduler() -> None:
    """Shut down the deadline scheduler."""
    global _scheduler

    if _scheduler is not None:
        try:
            _scheduler.shutdown(wait=False)
            logger.info("Deadline reminder scheduler stopped")
        except Exception as exc:
            logger.warning("Error stopping deadline scheduler: %s", exc)
        finally:
            _scheduler = None

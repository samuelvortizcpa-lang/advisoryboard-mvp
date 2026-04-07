"""
Engagement engine — auto-generates action items from engagement templates.

Runs daily via APScheduler. For each active client_engagement, calculates
upcoming task deadlines and creates action items when the lead time window
opens. Prevents duplicates via the (client_id, engagement_task_id, due_date)
unique constraint.
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session, joinedload

from app.core.database import SessionLocal
from app.models.action_item import ActionItem
from app.models.client import Client
from app.models.client_engagement import ClientEngagement
from app.models.engagement_template import EngagementTemplate
from app.models.engagement_template_task import EngagementTemplateTask

logger = logging.getLogger(__name__)

# Module-level scheduler
_scheduler: Any = None


# ---------------------------------------------------------------------------
# 1. Generate upcoming tasks
# ---------------------------------------------------------------------------


def generate_upcoming_tasks(
    db: Session | None = None,
    days_ahead: int = 30,
    *,
    client_id: UUID | None = None,
) -> list[dict[str, Any]]:
    """
    Scan active engagements and create action items for tasks whose
    lead-time window falls within the next *days_ahead* days.

    If *client_id* is provided, only process engagements for that client.

    Returns a list of dicts describing the created action items.
    """
    own_session = db is None
    if own_session:
        db = SessionLocal()

    try:
        return _generate(db, days_ahead, client_id)
    except Exception:
        logger.exception("Engagement engine: error generating tasks")
        return []
    finally:
        if own_session:
            db.close()


def _generate(
    db: Session,
    days_ahead: int,
    client_id: UUID | None,
) -> list[dict[str, Any]]:
    today = date.today()
    window_end = today + timedelta(days=days_ahead)

    q = (
        db.query(ClientEngagement)
        .options(
            joinedload(ClientEngagement.template).joinedload(EngagementTemplate.tasks),
            joinedload(ClientEngagement.client),
        )
        .filter(ClientEngagement.is_active == True)  # noqa: E712
    )
    if client_id is not None:
        q = q.filter(ClientEngagement.client_id == client_id)

    engagements = q.all()
    created: list[dict[str, Any]] = []

    for eng in engagements:
        template = eng.template
        if not template or not template.is_active:
            continue

        client = eng.client
        if not client:
            continue

        overrides = eng.custom_overrides or {}

        for task in template.tasks:
            try:
                items = _process_task(
                    db, eng, client, task, overrides, today, window_end,
                )
                created.extend(items)
            except Exception:
                logger.warning(
                    "Engagement engine: failed processing task %s for client %s",
                    task.id, eng.client_id, exc_info=True,
                )

    if created:
        logger.info(
            "Engagement engine: created %d action item(s) across %d engagement(s)",
            len(created), len(engagements),
        )

    return created


def _process_task(
    db: Session,
    engagement: ClientEngagement,
    client: Client,
    task: EngagementTemplateTask,
    overrides: dict[str, Any],
    today: date,
    window_end: date,
) -> list[dict[str, Any]]:
    """Calculate occurrence dates for a task and create action items if needed."""
    created: list[dict[str, Any]] = []
    current_year = today.year

    # Generate occurrences for current year and next year (to catch Jan deadlines)
    years = [current_year, current_year + 1]
    if engagement.start_year > current_year:
        return []

    for year in years:
        if year < engagement.start_year:
            continue

        deadlines = _calculate_deadlines(task, year, overrides)
        for deadline in deadlines:
            # The creation trigger date is deadline minus lead_days
            trigger_date = deadline - timedelta(days=task.lead_days)

            if not (today <= trigger_date <= window_end):
                continue

            # Check for existing action item (duplicate prevention)
            existing = (
                db.query(ActionItem.id)
                .filter(
                    ActionItem.client_id == engagement.client_id,
                    ActionItem.engagement_task_id == task.id,
                    ActionItem.due_date == deadline,
                )
                .first()
            )
            if existing:
                continue

            # Build task text with year context
            task_text = _format_task_text(task.task_name, year)

            # Create action item
            item = ActionItem(
                client_id=engagement.client_id,
                text=task_text,
                due_date=deadline,
                priority=task.priority,
                source="engagement_engine",
                engagement_task_id=task.id,
                status="pending",
            )
            db.add(item)
            db.flush()

            result = {
                "action_item_id": str(item.id),
                "client_id": str(engagement.client_id),
                "client_name": client.name,
                "task_name": task_text,
                "due_date": deadline.isoformat(),
                "priority": task.priority,
            }
            created.append(result)

            # Journal entry (best-effort)
            try:
                from app.services.journal_service import create_auto_entry

                create_auto_entry(
                    db=db,
                    client_id=engagement.client_id,
                    user_id="system",
                    entry_type="system",
                    category="compliance",
                    title=f"{task_text} auto-generated",
                    content=f"Deadline: {deadline.isoformat()}. Priority: {task.priority}.",
                    source_type="system",
                    metadata={
                        "engagement_task_id": str(task.id),
                        "template_name": engagement.template.name,
                        "tax_year": year,
                    },
                )
            except Exception:
                logger.warning("Journal entry for engagement task failed (non-fatal)", exc_info=True)

    db.commit()
    return created


def _calculate_deadlines(
    task: EngagementTemplateTask,
    year: int,
    overrides: dict[str, Any],
) -> list[date]:
    """Calculate the deadline date(s) for a task in a given year."""
    # Check for custom override
    override_key = str(task.id)
    if override_key in overrides:
        ov = overrides[override_key]
        if isinstance(ov, dict) and "month" in ov and "day" in ov:
            try:
                return [date(year, ov["month"], ov["day"])]
            except (ValueError, TypeError):
                pass

    if task.month is None or task.day is None:
        return []

    try:
        # Clamp day to valid range for the month
        import calendar
        max_day = calendar.monthrange(year, task.month)[1]
        actual_day = min(task.day, max_day)
        deadline = date(year, task.month, actual_day)
    except (ValueError, TypeError):
        return []

    if task.recurrence == "quarterly":
        # Generate 4 quarterly occurrences based on the month offset pattern
        return [deadline]  # Each quarterly task has its own month/day set
    elif task.recurrence in ("annual", "one_time"):
        return [deadline]
    elif task.recurrence == "monthly":
        # Generate for every month
        import calendar
        deadlines = []
        for m in range(1, 13):
            max_d = calendar.monthrange(year, m)[1]
            d = min(task.day, max_d)
            deadlines.append(date(year, m, d))
        return deadlines

    return [deadline]


def _format_task_text(task_name: str, year: int) -> str:
    """Add year context to task name if not already present."""
    if str(year) in task_name:
        return task_name
    return f"{task_name} ({year})"


# ---------------------------------------------------------------------------
# 2. Assign engagement
# ---------------------------------------------------------------------------


def assign_engagement(
    db: Session,
    client_id: UUID,
    template_id: UUID,
    user_id: str,
    start_year: int | None = None,
    custom_overrides: dict[str, Any] | None = None,
) -> ClientEngagement:
    """
    Create a client_engagement linking a client to a template.
    Immediately generates upcoming tasks for the new engagement.
    """
    if start_year is None:
        start_year = date.today().year

    engagement = ClientEngagement(
        client_id=client_id,
        template_id=template_id,
        start_year=start_year,
        is_active=True,
        custom_overrides=custom_overrides,
        created_by=user_id,
    )
    db.add(engagement)
    db.commit()
    db.refresh(engagement)

    # Immediately generate any upcoming tasks
    try:
        generate_upcoming_tasks(db, days_ahead=60, client_id=client_id)
    except Exception:
        logger.warning(
            "Engagement engine: initial task generation failed for client %s",
            client_id, exc_info=True,
        )

    return engagement


# ---------------------------------------------------------------------------
# 3. Remove engagement
# ---------------------------------------------------------------------------


def remove_engagement(
    db: Session,
    client_id: UUID,
    template_id: UUID,
) -> bool:
    """Deactivate the engagement. Does NOT delete existing generated action items."""
    engagement = (
        db.query(ClientEngagement)
        .filter(
            ClientEngagement.client_id == client_id,
            ClientEngagement.template_id == template_id,
        )
        .first()
    )
    if engagement is None:
        return False

    engagement.is_active = False
    db.commit()
    return True


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------


def _run_engagement_engine() -> None:
    """Wrapper called by APScheduler — opens its own session."""
    logger.info("Engagement engine: daily run starting")
    results = generate_upcoming_tasks()
    logger.info(
        "Engagement engine: daily run complete — %d task(s) created", len(results),
    )


def start_engagement_scheduler() -> bool:
    """Start a daily scheduler for engagement task generation."""
    global _scheduler

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
            _run_engagement_engine,
            trigger=CronTrigger(hour=0, minute=0),
            id="engagement_engine",
            name="Daily engagement task generation",
            replace_existing=True,
        )
        _scheduler.start()
        logger.info("Engagement engine scheduler started (daily at 00:00 UTC)")
        return True

    except ImportError:
        logger.warning("APScheduler not installed — engagement engine disabled")
        return False
    except Exception as exc:
        logger.warning("Failed to start engagement scheduler: %s", exc)
        return False


def stop_engagement_scheduler() -> None:
    """Shut down the engagement scheduler."""
    global _scheduler

    if _scheduler is not None:
        try:
            _scheduler.shutdown(wait=False)
            logger.info("Engagement engine scheduler stopped")
        except Exception as exc:
            logger.warning("Error stopping engagement scheduler: %s", exc)
        finally:
            _scheduler = None

"""
Notification service: Slack webhooks + task email notifications.

Slack: sends rich-formatted messages to an incoming webhook.
Email: sends branded Callwen emails for task assignment, completion, and deadline reminders.
Both gracefully degrade when not configured.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timezone
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.notification_preference import NotificationPreference

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Slack notifications (original)
# ---------------------------------------------------------------------------


async def send_notification(
    event_type: str,
    message: str,
    metadata: dict | None = None,
) -> None:
    """
    Send a rich Slack message via incoming webhook.

    Silently skips if SLACK_WEBHOOK_URL is not set or on any error.
    """
    webhook_url = get_settings().slack_webhook_url
    if not webhook_url:
        return

    try:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{event_type.replace('_', ' ').title()}*\n{message}",
                },
            },
        ]

        if metadata:
            fields_text = " | ".join(
                f"{k.replace('_', ' ').title()}: {v}" for k, v in metadata.items()
            )
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": fields_text},
                }
            )

        blocks.append(
            {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": f"_{timestamp}_"}],
            }
        )

        payload = {"blocks": blocks}

        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(webhook_url, json=payload)

    except Exception:
        logger.debug("Slack notification failed for event=%s", event_type, exc_info=True)


def notify(event_type: str, message: str, metadata: dict | None = None) -> None:
    """
    Fire-and-forget sync wrapper. Schedules the notification as an async task
    on the running event loop (uvicorn). Safe to call from sync service code.
    """
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(send_notification(event_type, message, metadata))
    except RuntimeError:
        pass  # No running event loop — skip silently


def notify_support_ticket(ticket: object) -> None:
    """
    Send a Slack notification for a new support ticket.

    Accepts a SupportTicket model instance (typed as object to avoid circular
    imports). Extracts fields via attribute access.
    """
    category = getattr(ticket, "category", "general")
    subject = getattr(ticket, "subject", "")
    user_name = getattr(ticket, "user_name", None) or "Unknown"
    user_email = getattr(ticket, "user_email", None) or "N/A"
    page_url = getattr(ticket, "page_url", None) or "N/A"

    category_label = category.replace("_", " ").title()
    message = f"\U0001f3ab *New Support Ticket*\n*{subject}*"

    metadata = {
        "category": category_label,
        "from": f"{user_name} ({user_email})",
        "page": page_url,
    }

    notify("support_ticket", message, metadata)


# ---------------------------------------------------------------------------
# Preference helpers
# ---------------------------------------------------------------------------


def get_user_preferences(
    db: Session, user_id: str, org_id: str
) -> Optional[NotificationPreference]:
    """Return the user's notification preferences, or None (callers treat None as defaults-on)."""
    return (
        db.query(NotificationPreference)
        .filter(
            NotificationPreference.user_id == user_id,
            NotificationPreference.org_id == org_id,
        )
        .first()
    )


def get_or_create_preferences(
    db: Session, user_id: str, org_id: str
) -> NotificationPreference:
    """Return existing preferences or create a row with all defaults."""
    prefs = get_user_preferences(db, user_id, org_id)
    if prefs is not None:
        return prefs

    prefs = NotificationPreference(user_id=user_id, org_id=org_id)
    db.add(prefs)
    db.commit()
    db.refresh(prefs)
    return prefs


# ---------------------------------------------------------------------------
# Email senders
# ---------------------------------------------------------------------------


def send_task_assigned_email(
    to_email: str,
    to_name: str,
    assigner_name: str,
    task_text: str,
    client_name: Optional[str],
    due_date: Optional[date],
    task_url: str,
) -> None:
    from app.services import email_service

    if not email_service.is_configured():
        return

    import resend

    settings = get_settings()
    resend.api_key = settings.resend_api_key

    truncated = task_text[:80] + ("…" if len(task_text) > 80 else "")
    subject = f"[Callwen] {assigner_name} assigned you: {truncated}"

    client_line = f"<p style='margin:0 0 8px;color:#6b7280;font-size:14px;'>Client: <strong style=\"color:#374151;\">{client_name}</strong></p>" if client_name else ""
    due_line = f"<p style='margin:0 0 8px;color:#6b7280;font-size:14px;'>Due: <strong style=\"color:#374151;\">{due_date.strftime('%B %d, %Y')}</strong></p>" if due_date else ""

    body_html = f"""
    <h2 style="margin:0 0 16px;color:#374151;font-size:18px;font-weight:600;">
      New task assigned to you
    </h2>
    <div style="background:#f8fafc;border-left:4px solid #d4a853;padding:16px;border-radius:0 8px 8px 0;margin:0 0 16px;">
      <p style="margin:0;color:#1e293b;font-size:15px;line-height:1.6;">{task_text}</p>
    </div>
    {client_line}
    {due_line}
    <p style="margin:0 0 8px;color:#6b7280;font-size:14px;">Assigned by: <strong style="color:#374151;">{assigner_name}</strong></p>
    <table cellpadding="0" cellspacing="0" style="margin:24px 0;">
    <tr><td style="background:#1e293b;border-radius:6px;">
      <a href="{task_url}" style="display:inline-block;padding:12px 28px;color:#d4a853;font-size:14px;font-weight:600;text-decoration:none;">
        View Task
      </a>
    </td></tr>
    </table>
    """

    html = _build_notification_html("Task Assigned", body_html)

    resend.Emails.send({
        "from": settings.resend_from_email,
        "to": [to_email],
        "subject": subject,
        "html": html,
    })
    logger.info("Task assignment email sent to %s", to_email)


def send_task_completed_email(
    to_email: str,
    to_name: str,
    completer_name: str,
    task_text: str,
    client_name: Optional[str],
    task_url: str,
) -> None:
    from app.services import email_service

    if not email_service.is_configured():
        return

    import resend

    settings = get_settings()
    resend.api_key = settings.resend_api_key

    truncated = task_text[:80] + ("…" if len(task_text) > 80 else "")
    subject = f"[Callwen] Task completed: {truncated}"

    client_line = f"<p style='margin:0 0 8px;color:#6b7280;font-size:14px;'>Client: <strong style=\"color:#374151;\">{client_name}</strong></p>" if client_name else ""

    body_html = f"""
    <h2 style="margin:0 0 16px;color:#374151;font-size:18px;font-weight:600;">
      {completer_name} completed a task you assigned
    </h2>
    <div style="background:#f0fdf4;border-left:4px solid #22c55e;padding:16px;border-radius:0 8px 8px 0;margin:0 0 16px;">
      <p style="margin:0;color:#1e293b;font-size:15px;line-height:1.6;">{task_text}</p>
    </div>
    <span style="display:inline-block;background:#dcfce7;color:#166534;font-size:12px;font-weight:600;padding:4px 12px;border-radius:12px;margin:0 0 16px;">
      Completed
    </span>
    {client_line}
    <table cellpadding="0" cellspacing="0" style="margin:24px 0;">
    <tr><td style="background:#1e293b;border-radius:6px;">
      <a href="{task_url}" style="display:inline-block;padding:12px 28px;color:#d4a853;font-size:14px;font-weight:600;text-decoration:none;">
        View Task
      </a>
    </td></tr>
    </table>
    """

    html = _build_notification_html("Task Completed", body_html)

    resend.Emails.send({
        "from": settings.resend_from_email,
        "to": [to_email],
        "subject": subject,
        "html": html,
    })
    logger.info("Task completion email sent to %s", to_email)


def send_deadline_reminder_email(
    to_email: str,
    to_name: str,
    tasks: list[dict],
) -> None:
    """Send a reminder for upcoming deadlines.

    tasks: list of dicts with keys 'text', 'client_name', 'due_date'.
    """
    from app.services import email_service

    if not email_service.is_configured():
        return

    import resend

    settings = get_settings()
    resend.api_key = settings.resend_api_key

    count = len(tasks)
    subject = f"[Callwen] {count} task{'s' if count != 1 else ''} due soon"

    rows = ""
    for t in tasks:
        due_str = t["due_date"].strftime("%B %d, %Y") if isinstance(t["due_date"], date) else str(t["due_date"])
        client = t.get("client_name") or "\u2014"
        rows += f"""
        <tr>
          <td style="padding:10px 12px;border-bottom:1px solid #f1f5f9;color:#1e293b;font-size:14px;line-height:1.5;">{t['text'][:100]}</td>
          <td style="padding:10px 12px;border-bottom:1px solid #f1f5f9;color:#6b7280;font-size:14px;">{client}</td>
          <td style="padding:10px 12px;border-bottom:1px solid #f1f5f9;color:#6b7280;font-size:14px;white-space:nowrap;">{due_str}</td>
        </tr>
        """

    calendar_url = f"{settings.frontend_url}/dashboard/calendar"

    body_html = f"""
    <h2 style="margin:0 0 16px;color:#374151;font-size:18px;font-weight:600;">
      You have {count} task{'s' if count != 1 else ''} due soon
    </h2>
    <table width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 24px;">
      <tr style="background:#f8fafc;">
        <th style="padding:10px 12px;text-align:left;font-size:12px;font-weight:600;color:#64748b;text-transform:uppercase;letter-spacing:0.05em;">Task</th>
        <th style="padding:10px 12px;text-align:left;font-size:12px;font-weight:600;color:#64748b;text-transform:uppercase;letter-spacing:0.05em;">Client</th>
        <th style="padding:10px 12px;text-align:left;font-size:12px;font-weight:600;color:#64748b;text-transform:uppercase;letter-spacing:0.05em;">Due</th>
      </tr>
      {rows}
    </table>
    <table cellpadding="0" cellspacing="0" style="margin:0;">
    <tr><td style="background:#1e293b;border-radius:6px;">
      <a href="{calendar_url}" style="display:inline-block;padding:12px 28px;color:#d4a853;font-size:14px;font-weight:600;text-decoration:none;">
        View Calendar
      </a>
    </td></tr>
    </table>
    """

    html = _build_notification_html("Deadline Reminder", body_html)

    resend.Emails.send({
        "from": settings.resend_from_email,
        "to": [to_email],
        "subject": subject,
        "html": html,
    })
    logger.info("Deadline reminder email sent to %s (%d tasks)", to_email, count)


# ---------------------------------------------------------------------------
# Shared HTML template
# ---------------------------------------------------------------------------


def _build_notification_html(title: str, body_html: str) -> str:
    settings = get_settings()
    return f"""\
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;background:#f7f7f7;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f7f7f7;padding:40px 0;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.1);">

<!-- Header -->
<tr><td style="background:#1e293b;padding:24px 40px;">
  <span style="color:#d4a853;font-size:20px;font-weight:700;letter-spacing:0.02em;">Callwen</span>
  <span style="color:#94a3b8;font-size:14px;margin-left:12px;">{title}</span>
</td></tr>

<!-- Body -->
<tr><td style="padding:32px 40px;">
  {body_html}
</td></tr>

<!-- Footer -->
<tr><td style="padding:20px 40px;border-top:1px solid #e5e7eb;background:#f9fafb;">
  <p style="margin:0;color:#9ca3af;font-size:11px;line-height:1.5;">
    Manage your notification preferences in
    <a href="{settings.frontend_url}/dashboard/settings" style="color:#9ca3af;">Settings</a>.
    Sent by Callwen (callwen.com).
  </p>
</td></tr>

</table>
</td></tr>
</table>
</body>
</html>"""

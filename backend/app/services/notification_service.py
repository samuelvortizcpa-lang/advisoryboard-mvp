"""
Slack notification service for key business events.

Sends rich-formatted messages to a Slack incoming webhook.
Gracefully degrades when SLACK_WEBHOOK_URL is not configured —
notification failures never affect the main request.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


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

"""Support ticket endpoints — submit tickets and admin listing."""

from __future__ import annotations

import base64
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.support_ticket import SupportTicket
from app.services.notification_service import notify_support_ticket

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

VALID_CATEGORIES = {"bug", "question", "feature_request", "general"}


class TicketCreate(BaseModel):
    category: str = Field(..., max_length=30)
    subject: str = Field(..., max_length=500)
    description: str
    page_url: Optional[str] = Field(None, max_length=500)
    screenshot_base64: Optional[str] = None


class TicketResponse(BaseModel):
    id: str
    user_id: str
    user_email: Optional[str]
    user_name: Optional[str]
    category: str
    subject: str
    description: str
    page_url: Optional[str]
    screenshot_url: Optional[str]
    status: str
    priority: Optional[str]
    admin_notes: Optional[str]
    created_at: str
    updated_at: Optional[str]

    model_config = {"from_attributes": True}


def _ticket_to_response(ticket: SupportTicket) -> TicketResponse:
    return TicketResponse(
        id=str(ticket.id),
        user_id=ticket.user_id,
        user_email=ticket.user_email,
        user_name=ticket.user_name,
        category=ticket.category,
        subject=ticket.subject,
        description=ticket.description,
        page_url=ticket.page_url,
        screenshot_url=ticket.screenshot_url,
        status=ticket.status,
        priority=ticket.priority,
        admin_notes=ticket.admin_notes,
        created_at=ticket.created_at.isoformat() if ticket.created_at else "",
        updated_at=ticket.updated_at.isoformat() if ticket.updated_at else None,
    )


# ---------------------------------------------------------------------------
# Admin guard (same pattern as admin.py)
# ---------------------------------------------------------------------------

import hmac

from app.core.auth import verify_clerk_token
from app.core.config import get_settings


async def verify_admin_access(request: Request) -> None:
    """Allow access via X-Admin-Key or Clerk JWT with admin user ID."""
    settings = get_settings()

    api_key = request.headers.get("X-Admin-Key")
    if api_key and settings.admin_api_key and hmac.compare_digest(
        api_key.encode("utf-8"), settings.admin_api_key.encode("utf-8")
    ):
        return

    from fastapi.security import HTTPBearer

    bearer = HTTPBearer(auto_error=False)
    credentials = await bearer(request)
    if credentials:
        try:
            payload = await verify_clerk_token(credentials.credentials)
            user_id = payload.get("sub")
            if settings.admin_user_id and user_id and hmac.compare_digest(
                user_id.encode("utf-8"), settings.admin_user_id.encode("utf-8")
            ):
                return
        except HTTPException:
            pass

    raise HTTPException(status_code=403, detail="Admin access required")


# ---------------------------------------------------------------------------
# Screenshot upload helper
# ---------------------------------------------------------------------------

SCREENSHOT_BUCKET = "support-screenshots"


def _upload_screenshot(ticket_id: str, screenshot_b64: str) -> str | None:
    """Decode base64 screenshot, upload to Supabase Storage, return public URL."""
    try:
        import os

        from supabase import create_client

        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_KEY")
        if not url or not key:
            logger.warning("Supabase not configured — skipping screenshot upload")
            return None

        image_bytes = base64.b64decode(screenshot_b64)
        if len(image_bytes) > 10 * 1024 * 1024:  # 10 MB limit
            logger.warning("Screenshot too large (%d bytes), skipping", len(image_bytes))
            return None

        client = create_client(url, key)

        # Ensure bucket exists (idempotent)
        try:
            client.storage.create_bucket(
                SCREENSHOT_BUCKET, options={"public": True}
            )
        except Exception:
            pass  # Bucket likely already exists

        storage_path = f"{ticket_id}.png"
        client.storage.from_(SCREENSHOT_BUCKET).upload(
            path=storage_path,
            file=image_bytes,
            file_options={"content-type": "image/png"},
        )

        public_url = f"{url}/storage/v1/object/public/{SCREENSHOT_BUCKET}/{storage_path}"
        return public_url

    except Exception:
        logger.exception("Failed to upload screenshot for ticket %s", ticket_id)
        return None


# ---------------------------------------------------------------------------
# Email notification helper
# ---------------------------------------------------------------------------


def _send_support_email(ticket: SupportTicket) -> None:
    """Send email notification to support inbox via Resend."""
    try:
        import resend

        settings = get_settings()
        if not settings.resend_api_key or not settings.resend_from_email:
            return

        resend.api_key = settings.resend_api_key

        category_label = ticket.category.replace("_", " ").title()
        timestamp = ticket.created_at.strftime("%Y-%m-%d %H:%M UTC") if ticket.created_at else "N/A"
        user_display = ticket.user_name or ticket.user_email or ticket.user_id

        page_row = ""
        if ticket.page_url:
            page_row = f'<tr><td style="padding:6px 12px;color:#6b7280;font-size:13px;">Page</td><td style="padding:6px 12px;font-size:13px;">{ticket.page_url}</td></tr>'

        screenshot_row = ""
        if ticket.screenshot_url:
            screenshot_row = f'<tr><td style="padding:6px 12px;color:#6b7280;font-size:13px;">Screenshot</td><td style="padding:6px 12px;font-size:13px;"><a href="{ticket.screenshot_url}">View screenshot</a></td></tr>'

        category_color = {"bug": "#dc2626", "feature_request": "#2563eb", "question": "#6b7280"}.get(ticket.category, "#6b7280")

        html = f"""\
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f7f7f7;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f7f7f7;padding:40px 0;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.1);">
<tr><td style="background:#1e222e;padding:24px 32px;">
  <h1 style="margin:0;color:#f0ede6;font-size:18px;font-weight:600;">New Support Ticket</h1>
</td></tr>
<tr><td style="padding:24px 32px;">
  <p style="margin:0 0 16px;">
    <span style="display:inline-block;padding:3px 10px;border-radius:4px;background:{category_color};color:#fff;font-size:12px;font-weight:500;">{category_label}</span>
  </p>
  <h2 style="margin:0 0 12px;font-size:16px;color:#1e222e;">{ticket.subject}</h2>
  <p style="margin:0 0 20px;color:#374151;font-size:14px;line-height:1.6;white-space:pre-wrap;">{ticket.description}</p>
  <table cellpadding="0" cellspacing="0" style="width:100%;border-top:1px solid #e5e7eb;">
    <tr><td style="padding:6px 12px;color:#6b7280;font-size:13px;">From</td><td style="padding:6px 12px;font-size:13px;">{user_display} ({ticket.user_email or "no email"})</td></tr>
    <tr><td style="padding:6px 12px;color:#6b7280;font-size:13px;">Submitted</td><td style="padding:6px 12px;font-size:13px;">{timestamp}</td></tr>
    {page_row}
    {screenshot_row}
  </table>
</td></tr>
<tr><td style="padding:16px 32px;border-top:1px solid #e5e7eb;background:#f9fafb;">
  <p style="margin:0;color:#9ca3af;font-size:11px;">Ticket ID: {ticket.id}</p>
</td></tr>
</table>
</td></tr>
</table>
</body>
</html>"""

        send_params: dict = {
            "from": settings.resend_from_email,
            "to": ["info@callwen.com"],
            "subject": f"[Callwen Support] {category_label}: {ticket.subject}",
            "html": html,
        }
        if ticket.user_email:
            send_params["reply_to"] = ticket.user_email

        resend.Emails.send(send_params)
        logger.info("Support email sent for ticket %s", ticket.id)

    except Exception:
        logger.exception("Failed to send support email for ticket %s", ticket.id)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/support/tickets", status_code=status.HTTP_201_CREATED)
async def create_ticket(
    body: TicketCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> TicketResponse:
    """Submit a new support ticket."""
    if body.category not in VALID_CATEGORIES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid category. Must be one of: {', '.join(sorted(VALID_CATEGORIES))}",
        )

    user_id = current_user["user_id"]
    user_email = current_user.get("email")
    first = current_user.get("first_name") or ""
    last = current_user.get("last_name") or ""
    user_name = f"{first} {last}".strip() or None

    ticket_id = uuid.uuid4()

    # Handle optional screenshot
    screenshot_url = None
    if body.screenshot_base64:
        screenshot_url = _upload_screenshot(str(ticket_id), body.screenshot_base64)

    ticket = SupportTicket(
        id=ticket_id,
        user_id=user_id,
        user_email=user_email,
        user_name=user_name,
        category=body.category,
        subject=body.subject,
        description=body.description,
        page_url=body.page_url,
        screenshot_url=screenshot_url,
        status="open",
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)

    # Fire-and-forget notifications
    notify_support_ticket(ticket)
    _send_support_email(ticket)

    return _ticket_to_response(ticket)


@router.get("/support/tickets")
async def list_tickets(
    _admin: None = Depends(verify_admin_access),
    db: Session = Depends(get_db),
    ticket_status: Optional[str] = Query(None, alias="status"),
    category: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[TicketResponse]:
    """List support tickets (admin only)."""
    query = db.query(SupportTicket)

    if ticket_status:
        query = query.filter(SupportTicket.status == ticket_status)
    if category:
        query = query.filter(SupportTicket.category == category)
    if date_from:
        try:
            dt = datetime.fromisoformat(date_from)
            query = query.filter(SupportTicket.created_at >= dt)
        except ValueError:
            pass
    if date_to:
        try:
            dt = datetime.fromisoformat(date_to)
            query = query.filter(SupportTicket.created_at <= dt)
        except ValueError:
            pass

    tickets = (
        query.order_by(SupportTicket.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return [_ticket_to_response(t) for t in tickets]

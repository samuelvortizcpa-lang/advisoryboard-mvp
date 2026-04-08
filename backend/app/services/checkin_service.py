"""
Client check-in service — template CRUD, sending, submission, and retrieval.

CPAs send customizable questionnaires to clients before meetings. Clients
complete them via a tokenized public link (no login required). Completed
responses are embedded via pgvector and flow into the AI context assembler.
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from openai import AsyncOpenAI
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.checkin_response import CheckinResponse
from app.models.checkin_template import CheckinTemplate
from app.models.client import Client
from app.models.organization import Organization
from app.models.user import User
from app.schemas.checkin import CheckinTemplateCreate, CheckinTemplateUpdate

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-3-small"

# Tier limits for custom templates (org-created, is_default=false)
_TEMPLATE_LIMITS: dict[str, int | None] = {
    "free": 0,
    "starter": 3,
    "professional": None,  # unlimited
    "firm": None,
}

# Tier limits for monthly check-ins sent
_MONTHLY_SEND_LIMITS: dict[str, int | None] = {
    "free": 5,
    "starter": 25,
    "professional": 100,
    "firm": None,  # unlimited
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_org_tier(db: Session, org_id: UUID | None, user_id: str) -> str:
    """Return the subscription tier for the org (or user fallback)."""
    from app.services.subscription_service import get_or_create_subscription

    sub = get_or_create_subscription(db, user_id, org_id=org_id)
    return sub.tier


def _openai() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=get_settings().openai_api_key)


async def _embed_text(text: str) -> list[float]:
    """Return a 1536-dim embedding for *text*."""
    client = _openai()
    response = await client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text.replace("\n", " "),
    )
    return response.data[0].embedding


# ---------------------------------------------------------------------------
# 1. Template management
# ---------------------------------------------------------------------------


def get_templates(db: Session, org_id: UUID | None) -> list[CheckinTemplate]:
    """Return all active templates visible to this org (org-specific + defaults)."""
    q = db.query(CheckinTemplate).filter(CheckinTemplate.is_active.is_(True))

    if org_id is not None:
        q = q.filter(
            (CheckinTemplate.org_id == org_id) | (CheckinTemplate.is_default.is_(True))
        )
    else:
        q = q.filter(CheckinTemplate.is_default.is_(True))

    return q.order_by(CheckinTemplate.is_default.desc(), CheckinTemplate.name).all()


def create_template(
    db: Session,
    org_id: UUID,
    user_id: str,
    data: CheckinTemplateCreate,
) -> CheckinTemplate:
    """Create a custom template for this org, enforcing tier limits."""
    tier = _get_org_tier(db, org_id, user_id)
    limit = _TEMPLATE_LIMITS.get(tier)

    if limit is not None:
        current_count = (
            db.query(func.count(CheckinTemplate.id))
            .filter(
                CheckinTemplate.org_id == org_id,
                CheckinTemplate.is_default.is_(False),
                CheckinTemplate.is_active.is_(True),
            )
            .scalar()
        )
        if current_count >= limit:
            if limit == 0:
                raise ValueError(
                    "Custom check-in templates are not available on the Free plan. "
                    "Upgrade to Starter or above to create custom templates."
                )
            raise ValueError(
                f"You've reached the limit of {limit} custom templates on the "
                f"{tier.title()} plan. Upgrade to Professional for unlimited templates."
            )

    questions_data = [q.model_dump() for q in data.questions]
    template = CheckinTemplate(
        org_id=org_id,
        created_by=user_id,
        name=data.name,
        description=data.description,
        questions=questions_data,
        is_default=False,
        is_active=True,
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return template


def update_template(
    db: Session,
    template_id: UUID,
    org_id: UUID,
    data: CheckinTemplateUpdate,
) -> CheckinTemplate:
    """Update an org-owned template. System defaults cannot be edited."""
    template = (
        db.query(CheckinTemplate)
        .filter(CheckinTemplate.id == template_id, CheckinTemplate.org_id == org_id)
        .first()
    )
    if template is None:
        raise FileNotFoundError("Template not found")
    if template.is_default:
        raise PermissionError("System default templates cannot be edited")

    if data.name is not None:
        template.name = data.name
    if data.description is not None:
        template.description = data.description
    if data.questions is not None:
        template.questions = [q.model_dump() for q in data.questions]
    if data.is_active is not None:
        template.is_active = data.is_active

    db.commit()
    db.refresh(template)
    return template


def delete_template(db: Session, template_id: UUID, org_id: UUID) -> None:
    """Soft-delete an org-owned template. System defaults cannot be deleted."""
    template = (
        db.query(CheckinTemplate)
        .filter(CheckinTemplate.id == template_id, CheckinTemplate.org_id == org_id)
        .first()
    )
    if template is None:
        raise FileNotFoundError("Template not found")
    if template.is_default:
        raise PermissionError("System default templates cannot be deleted")

    template.is_active = False
    db.commit()


# ---------------------------------------------------------------------------
# 2. Sending check-ins
# ---------------------------------------------------------------------------


def send_checkin(
    db: Session,
    client_id: UUID,
    org_id: UUID,
    user_id: str,
    template_id: UUID,
    client_email: str,
    client_name: str | None = None,
) -> CheckinResponse:
    """Send a check-in questionnaire to a client and return the response record."""
    import resend

    settings = get_settings()

    # ── Tier limit check ──────────────────────────────────────────────
    tier = _get_org_tier(db, org_id, user_id)
    limit = _MONTHLY_SEND_LIMITS.get(tier)

    if limit is not None:
        now = datetime.now(timezone.utc)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        sent_this_month = (
            db.query(func.count(CheckinResponse.id))
            .join(CheckinTemplate, CheckinResponse.template_id == CheckinTemplate.id)
            .filter(
                CheckinTemplate.org_id == org_id,
                CheckinResponse.sent_at >= month_start,
            )
            .scalar()
        )
        # Also count check-ins sent from default templates by users in this org
        from app.models.organization_member import OrganizationMember

        org_user_ids = [
            r[0]
            for r in db.query(OrganizationMember.user_id)
            .filter(OrganizationMember.org_id == org_id)
            .all()
        ]
        default_sent = (
            db.query(func.count(CheckinResponse.id))
            .filter(
                CheckinResponse.sent_by.in_(org_user_ids),
                CheckinResponse.sent_at >= month_start,
                CheckinResponse.template_id.in_(
                    db.query(CheckinTemplate.id).filter(CheckinTemplate.is_default.is_(True))
                ),
            )
            .scalar()
        ) if org_user_ids else 0

        total_sent = (sent_this_month or 0) + (default_sent or 0)

        if total_sent >= limit:
            raise ValueError(
                f"You've reached the limit of {limit} check-ins per month on the "
                f"{tier.title()} plan. Upgrade for more."
            )

    # ── Validate template ─────────────────────────────────────────────
    template = db.query(CheckinTemplate).filter(CheckinTemplate.id == template_id).first()
    if template is None:
        raise FileNotFoundError("Template not found")

    # ── Validate client access ────────────────────────────────────────
    client = db.query(Client).filter(Client.id == client_id).first()
    if client is None:
        raise FileNotFoundError("Client not found")

    # ── Sender info ───────────────────────────────────────────────────
    db_user = db.query(User).filter(User.clerk_id == user_id).first()
    sender_name = ""
    if db_user:
        parts = [db_user.first_name or "", db_user.last_name or ""]
        sender_name = " ".join(p for p in parts if p).strip()

    org = db.query(Organization).filter(Organization.id == org_id).first()
    org_name = org.name if org else "your advisory team"

    # ── Create response record ────────────────────────────────────────
    access_token = secrets.token_urlsafe(48)
    expires_at = datetime.now(timezone.utc) + timedelta(days=14)

    checkin = CheckinResponse(
        client_id=client_id,
        template_id=template_id,
        sent_by=user_id,
        sent_to_email=client_email,
        sent_to_name=client_name,
        access_token=access_token,
        status="pending",
        expires_at=expires_at,
    )
    db.add(checkin)
    db.flush()  # get the ID before sending email

    # ── Build and send email ──────────────────────────────────────────
    frontend_url = settings.frontend_url
    checkin_url = f"{frontend_url}/checkin/{access_token}"
    greeting = client_name or "there"

    body_html = _build_checkin_email_html(
        greeting=greeting,
        sender_name=sender_name or "Your advisor",
        org_name=org_name,
        checkin_url=checkin_url,
        template_name=template.name,
    )

    subject = f"Check-in: {template.name}"

    if settings.resend_api_key and settings.resend_from_email:
        try:
            resend.api_key = settings.resend_api_key
            from_address = settings.resend_from_email
            if sender_name:
                from_address = f"{sender_name} via Callwen <{settings.resend_from_email}>"

            resend.Emails.send(
                {
                    "from": from_address,
                    "to": [client_email],
                    "subject": subject,
                    "html": body_html,
                }
            )
            logger.info(
                "Check-in email sent to %s for client %s (template=%s)",
                client_email,
                client_id,
                template.name,
            )
        except Exception:
            logger.exception(
                "Failed to send check-in email to %s for client %s",
                client_email,
                client_id,
            )
    else:
        logger.warning("Resend not configured — check-in email to %s not sent", client_email)

    # ── Audit log ─────────────────────────────────────────────────────
    from app.models.audit_log import AuditLog

    try:
        audit = AuditLog(
            user_id=user_id,
            org_id=org_id,
            action="checkin_sent",
            resource_type="checkin_response",
            resource_id=str(checkin.id),
            detail={
                "template_id": str(template_id),
                "template_name": template.name,
                "client_email": client_email,
            },
        )
        db.add(audit)
    except Exception:
        logger.warning("Failed to write audit log for checkin_sent", exc_info=True)

    db.commit()
    db.refresh(checkin)
    return checkin


# ---------------------------------------------------------------------------
# 3. Processing submissions
# ---------------------------------------------------------------------------


async def submit_checkin(
    db: Session,
    access_token: str,
    submitted_responses: list[dict[str, Any]],
) -> CheckinResponse:
    """Process a client's check-in submission: store answers, embed, mark complete."""
    checkin = (
        db.query(CheckinResponse)
        .filter(CheckinResponse.access_token == access_token)
        .first()
    )
    if checkin is None:
        raise FileNotFoundError("Check-in not found")

    if checkin.status != "pending":
        raise ValueError("This check-in has already been completed or expired")

    now = datetime.now(timezone.utc)
    if checkin.expires_at.tzinfo is None:
        expires_at = checkin.expires_at.replace(tzinfo=timezone.utc)
    else:
        expires_at = checkin.expires_at

    if expires_at < now:
        checkin.status = "expired"
        db.commit()
        raise ValueError("This check-in link has expired")

    # ── Store raw responses ───────────────────────────────────────────
    checkin.responses = submitted_responses

    # ── Flatten into text for RAG ─────────────────────────────────────
    template = (
        db.query(CheckinTemplate)
        .filter(CheckinTemplate.id == checkin.template_id)
        .first()
    )

    response_map = {r["question_id"]: r["answer"] for r in submitted_responses}
    lines: list[str] = []

    if template and template.questions:
        for question in template.questions:
            qid = question.get("id", "")
            qtext = question.get("text", "")
            answer = response_map.get(qid, "")
            if isinstance(answer, list):
                answer = ", ".join(str(a) for a in answer)
            lines.append(f"Q: {qtext}\nA: {answer}\n")

    response_text = "\n".join(lines)
    checkin.response_text = response_text

    # ── Generate embedding ────────────────────────────────────────────
    if response_text.strip():
        try:
            embedding = await _embed_text(response_text)
            checkin.response_embedding = embedding
        except Exception:
            logger.exception("Failed to generate embedding for check-in %s", checkin.id)

    # ── Mark complete ─────────────────────────────────────────────────
    checkin.status = "completed"
    checkin.completed_at = now
    db.commit()
    db.refresh(checkin)
    return checkin


# ---------------------------------------------------------------------------
# 4. Retrieval
# ---------------------------------------------------------------------------


def get_client_checkins(
    db: Session,
    client_id: UUID,
    org_id: UUID,
) -> list[dict[str, Any]]:
    """Return all check-in responses for a client with template names."""
    rows = (
        db.query(CheckinResponse, CheckinTemplate.name)
        .join(CheckinTemplate, CheckinResponse.template_id == CheckinTemplate.id)
        .filter(CheckinResponse.client_id == client_id)
        .order_by(CheckinResponse.sent_at.desc())
        .all()
    )

    results = []
    for checkin, template_name in rows:
        results.append({
            "id": checkin.id,
            "client_id": checkin.client_id,
            "template_id": checkin.template_id,
            "template_name": template_name,
            "sent_by": checkin.sent_by,
            "sent_to_email": checkin.sent_to_email,
            "sent_to_name": checkin.sent_to_name,
            "access_token": checkin.access_token,
            "status": checkin.status,
            "responses": checkin.responses,
            "response_text": checkin.response_text,
            "completed_at": checkin.completed_at,
            "expires_at": checkin.expires_at,
            "sent_at": checkin.sent_at,
            "created_at": checkin.created_at,
        })

    return results


def get_checkin_detail(
    db: Session,
    checkin_id: UUID,
    org_id: UUID,
) -> dict[str, Any] | None:
    """Return a single check-in with full Q&A (template questions merged with answers)."""
    row = (
        db.query(CheckinResponse, CheckinTemplate)
        .join(CheckinTemplate, CheckinResponse.template_id == CheckinTemplate.id)
        .filter(CheckinResponse.id == checkin_id)
        .first()
    )
    if row is None:
        return None

    checkin, template = row

    # Merge template questions with response answers
    response_map: dict[str, Any] = {}
    if checkin.responses:
        response_map = {r["question_id"]: r["answer"] for r in checkin.responses}

    questions_with_answers = []
    if template.questions:
        for question in template.questions:
            qid = question.get("id", "")
            questions_with_answers.append({
                "id": qid,
                "text": question.get("text", ""),
                "type": question.get("type", "text"),
                "options": question.get("options"),
                "answer": response_map.get(qid),
            })

    return {
        "id": checkin.id,
        "client_id": checkin.client_id,
        "template_id": checkin.template_id,
        "template_name": template.name,
        "sent_by": checkin.sent_by,
        "sent_to_email": checkin.sent_to_email,
        "sent_to_name": checkin.sent_to_name,
        "access_token": checkin.access_token,
        "status": checkin.status,
        "questions": questions_with_answers,
        "response_text": checkin.response_text,
        "completed_at": checkin.completed_at,
        "expires_at": checkin.expires_at,
        "sent_at": checkin.sent_at,
        "created_at": checkin.created_at,
    }


def get_pending_count(db: Session, client_id: UUID) -> int:
    """Count pending, non-expired check-ins for a client."""
    now = datetime.now(timezone.utc)
    return (
        db.query(func.count(CheckinResponse.id))
        .filter(
            CheckinResponse.client_id == client_id,
            CheckinResponse.status == "pending",
            CheckinResponse.expires_at > now,
        )
        .scalar()
    ) or 0


# ---------------------------------------------------------------------------
# Email template
# ---------------------------------------------------------------------------


def _build_checkin_email_html(
    greeting: str,
    sender_name: str,
    org_name: str,
    checkin_url: str,
    template_name: str,
) -> str:
    """Build the HTML email body for a check-in invitation."""
    return f"""\
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;background:#f7f7f7;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f7f7f7;padding:40px 0;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.1);">

<!-- Header -->
<tr><td style="background:#2563eb;padding:24px 40px;">
  <span style="color:#ffffff;font-size:18px;font-weight:700;">Client Check-in</span>
</td></tr>

<!-- Body -->
<tr><td style="padding:32px 40px;">
  <p style="margin:0 0 16px;color:#1f2937;font-size:16px;line-height:1.6;">
    Hi {greeting},
  </p>
  <p style="margin:0 0 16px;color:#1f2937;font-size:16px;line-height:1.6;">
    {sender_name} from {org_name} would like you to complete a brief check-in
    before your next meeting.
  </p>
  <p style="margin:0 0 24px;color:#6b7280;font-size:14px;line-height:1.6;">
    This should only take a few minutes and helps us prepare to make the most
    of our time together.
  </p>

  <!-- CTA Button -->
  <table cellpadding="0" cellspacing="0" style="margin:0 auto 24px;">
  <tr><td style="background:#0d9488;border-radius:6px;">
    <a href="{checkin_url}"
       style="display:inline-block;padding:14px 32px;color:#ffffff;font-size:16px;font-weight:600;text-decoration:none;">
      Complete Check-in
    </a>
  </td></tr>
  </table>

  <p style="margin:0;color:#9ca3af;font-size:13px;line-height:1.5;">
    This link expires in 14 days. If you have questions, reply to this email.
  </p>
</td></tr>

<!-- Footer -->
<tr><td style="padding:20px 40px;border-top:1px solid #e5e7eb;background:#f9fafb;">
  <p style="margin:0;color:#9ca3af;font-size:11px;line-height:1.5;">
    Sent via Callwen
  </p>
</td></tr>

</table>
</td></tr>
</table>
</body>
</html>"""

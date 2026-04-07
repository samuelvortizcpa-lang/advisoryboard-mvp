"""
Client communication service — send emails, render templates, manage history.

Uses Resend for delivery (same pattern as email_service.py) and logs every
outbound message in client_communications.
"""

from __future__ import annotations

import html
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from uuid import UUID

from app.core.config import get_settings
from app.models.action_item import ActionItem
from app.models.client import Client
from app.models.client_communication import ClientCommunication
from app.models.document import Document
from app.models.email_template import EmailTemplate
from app.models.organization import Organization
from app.models.organization_member import OrganizationMember
from app.models.user import User
from app.schemas.communication import OpenItem

logger = logging.getLogger(__name__)

VALID_TEMPLATE_TYPES = {
    "meeting_request",
    "follow_up",
    "document_request",
    "engagement_update",
    "year_end",
    "custom",
}


# ---------------------------------------------------------------------------
# 1. Send email
# ---------------------------------------------------------------------------


def send_client_email(
    user_id: str,
    client_id: uuid.UUID,
    subject: str,
    body_html: str,
    recipient_email: str,
    recipient_name: Optional[str],
    template_id: Optional[uuid.UUID],
    metadata: Optional[Dict[str, Any]],
    db: Session,
    *,
    thread_id: Optional[uuid.UUID] = None,
    thread_type: Optional[str] = None,
    thread_year: Optional[int] = None,
    thread_quarter: Optional[int] = None,
) -> ClientCommunication:
    """Send an email via Resend and log it in client_communications."""
    import resend

    settings = get_settings()

    # Build sender line with user's name if available
    db_user = db.query(User).filter(User.clerk_id == user_id).first()
    from_address = settings.resend_from_email
    if db_user:
        parts = [db_user.first_name or "", db_user.last_name or ""]
        user_name = " ".join(p for p in parts if p).strip()
        if user_name:
            # Resend "Name <email>" format
            from_address = f"{user_name} via Callwen <{settings.resend_from_email}>"

    # Generate plain text fallback
    body_text = _html_to_text(body_html)

    comm_id = uuid.uuid4()
    resend_message_id = None
    email_status = "sent"

    if settings.resend_api_key and settings.resend_from_email:
        try:
            resend.api_key = settings.resend_api_key
            result = resend.Emails.send(
                {
                    "from": from_address,
                    "to": [recipient_email],
                    "subject": subject,
                    "html": body_html,
                    "text": body_text,
                }
            )
            resend_message_id = result.get("id") if isinstance(result, dict) else None
            logger.info(
                "Email sent to %s for client %s (resend_id=%s)",
                recipient_email,
                client_id,
                resend_message_id,
            )
        except Exception:
            email_status = "failed"
            logger.exception(
                "Failed to send email to %s for client %s",
                recipient_email,
                client_id,
            )
    else:
        email_status = "failed"
        logger.warning("Resend not configured — email to %s not sent", recipient_email)

    comm = ClientCommunication(
        id=comm_id,
        client_id=client_id,
        user_id=user_id,
        communication_type="email",
        subject=subject,
        body_html=body_html,
        body_text=body_text,
        recipient_email=recipient_email,
        recipient_name=recipient_name,
        template_id=template_id,
        status=email_status,
        resend_message_id=resend_message_id,
        metadata_=metadata,
        thread_id=thread_id,
        thread_type=thread_type,
        thread_year=thread_year,
        thread_quarter=thread_quarter,
    )
    db.add(comm)
    db.commit()
    db.refresh(comm)

    # Journal entry for sent email
    journal_metadata: Dict[str, Any] = {"recipient": recipient_email, "subject": subject}
    if email_status == "sent":
        # Extract open items if this email is part of a thread
        if thread_id:
            try:
                extracted = extract_open_items_from_email(body_text or "")
                if extracted:
                    now = datetime.now(timezone.utc)
                    open_items_data = [
                        {
                            "question": item["question"],
                            "asked_in_email_id": str(comm.id),
                            "asked_date": now.isoformat(),
                            "status": "open",
                            "resolved_in_email_id": None,
                            "resolved_date": None,
                        }
                        for item in extracted
                    ]
                    comm.open_items = open_items_data
                    db.commit()
                    journal_metadata["open_items_count"] = len(open_items_data)
                    journal_metadata["thread_id"] = str(thread_id)
            except Exception:
                logger.warning("Open item extraction failed (non-fatal)", exc_info=True)

        try:
            from app.services.journal_service import create_auto_entry

            create_auto_entry(
                db=db,
                client_id=client_id,
                user_id=user_id,
                entry_type="communication",
                category="general",
                title=f"Email sent: {subject}",
                content=(body_text or "")[:200] or None,
                source_type="email",
                source_id=comm.id,
                metadata=journal_metadata,
            )
        except Exception:
            logger.warning("Journal entry for communication failed (non-fatal)", exc_info=True)

    return comm


# ---------------------------------------------------------------------------
# 2. Render template
# ---------------------------------------------------------------------------


def render_template(
    template_id: uuid.UUID,
    user_id: str,
    client_id: uuid.UUID,
    db: Session,
    extra_vars: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """
    Render an email template with merge variables filled in.

    Returns {"subject": ..., "body_html": ...}.
    """
    template = db.query(EmailTemplate).filter(EmailTemplate.id == template_id).first()
    if template is None:
        raise ValueError("Template not found")

    client = db.query(Client).filter(Client.id == client_id).first()
    if client is None:
        raise ValueError("Client not found")

    db_user = db.query(User).filter(User.clerk_id == user_id).first()

    # Build preparer name / firm
    preparer_name = ""
    preparer_firm = ""
    scheduling_link = ""
    if db_user:
        parts = [db_user.first_name or "", db_user.last_name or ""]
        preparer_name = " ".join(p for p in parts if p).strip() or "Your advisor"
        scheduling_link = db_user.scheduling_url or ""

        # Try to get firm name from org
        member = (
            db.query(OrganizationMember)
            .filter(
                OrganizationMember.user_id == user_id,
                OrganizationMember.is_active.is_(True),
            )
            .first()
        )
        if member:
            org = db.query(Organization).filter(Organization.id == member.org_id).first()
            if org and org.org_type != "personal":
                preparer_firm = org.name
    else:
        preparer_name = "Your advisor"

    # Client context
    pending_items = (
        db.query(ActionItem)
        .filter(
            ActionItem.client_id == client_id,
            ActionItem.status == "pending",
        )
        .order_by(ActionItem.due_date.asc().nulls_last())
        .all()
    )

    open_items_count = str(len(pending_items))

    # Next deadline
    next_deadline = "No upcoming deadlines"
    for item in pending_items:
        if item.due_date:
            next_deadline = item.due_date.strftime("%B %d, %Y")
            break

    # Action items summary (bulleted HTML list)
    if pending_items:
        bullets = "".join(
            f"<li>{html.escape(item.text)}"
            + (f" (due {item.due_date.strftime('%b %d, %Y')})" if item.due_date else "")
            + "</li>"
            for item in pending_items[:10]
        )
        action_items_summary = f"<ul>{bullets}</ul>"
    else:
        action_items_summary = "No pending action items."

    # Last contact date
    last_comm = (
        db.query(ClientCommunication)
        .filter(
            ClientCommunication.client_id == client_id,
            ClientCommunication.status == "sent",
        )
        .order_by(ClientCommunication.sent_at.desc())
        .first()
    )
    last_contact_date = (
        last_comm.sent_at.strftime("%B %d, %Y") if last_comm else "No prior emails"
    )

    # Document count
    doc_count = (
        db.query(func.count(Document.id))
        .filter(Document.client_id == client_id)
        .scalar()
        or 0
    )

    # Build variable map
    variables = {
        "client_name": client.name,
        "client_email": client.email or "",
        "client_business": client.business_name or client.name,
        "preparer_name": preparer_name,
        "preparer_firm": preparer_firm,
        "scheduling_link": scheduling_link,
        "open_items_count": open_items_count,
        "next_deadline": next_deadline,
        "last_contact_date": last_contact_date,
        "action_items_summary": action_items_summary,
        "document_count": str(doc_count),
    }
    if extra_vars:
        variables.update(extra_vars)

    # Render subject (simple replacement)
    rendered_subject = _replace_vars(template.subject_template, variables)

    # Render body (with conditional block handling for scheduling_link)
    rendered_body = _render_body(template.body_template, variables)

    return {"subject": rendered_subject, "body_html": rendered_body}


# ---------------------------------------------------------------------------
# 3. Communication history
# ---------------------------------------------------------------------------


def get_communication_history(
    client_id: uuid.UUID,
    user_id: str,
    db: Session,
    limit: int = 20,
) -> List[ClientCommunication]:
    """Return recent emails sent to this client, newest first."""
    return (
        db.query(ClientCommunication)
        .filter(ClientCommunication.client_id == client_id)
        .order_by(ClientCommunication.sent_at.desc())
        .limit(limit)
        .all()
    )


# ---------------------------------------------------------------------------
# 4. List templates
# ---------------------------------------------------------------------------


def get_templates(user_id: str, db: Session) -> List[EmailTemplate]:
    """Return system defaults + user's custom templates, sorted by usage."""
    return (
        db.query(EmailTemplate)
        .filter(
            EmailTemplate.is_active.is_(True),
            (EmailTemplate.is_default.is_(True)) | (EmailTemplate.user_id == user_id),
        )
        .order_by(EmailTemplate.usage_count.desc(), EmailTemplate.name.asc())
        .all()
    )


# ---------------------------------------------------------------------------
# 5. Create template
# ---------------------------------------------------------------------------


def create_template(
    user_id: str,
    name: str,
    subject_template: str,
    body_template: str,
    template_type: str,
    db: Session,
) -> EmailTemplate:
    """Create a custom email template for the user."""
    if template_type not in VALID_TEMPLATE_TYPES:
        raise ValueError(
            f"Invalid template_type. Must be one of: {', '.join(sorted(VALID_TEMPLATE_TYPES))}"
        )

    template = EmailTemplate(
        id=uuid.uuid4(),
        user_id=user_id,
        name=name,
        subject_template=subject_template,
        body_template=body_template,
        template_type=template_type,
        is_default=False,
        is_active=True,
        usage_count=0,
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return template


# ---------------------------------------------------------------------------
# 6. Update template
# ---------------------------------------------------------------------------


def update_template(
    template_id: uuid.UUID,
    user_id: str,
    updates: Dict[str, Any],
    db: Session,
) -> EmailTemplate:
    """Update a custom template. System defaults cannot be edited."""
    template = db.query(EmailTemplate).filter(EmailTemplate.id == template_id).first()
    if template is None:
        raise ValueError("Template not found")
    if template.is_default:
        raise PermissionError("System default templates cannot be edited")
    if template.user_id != user_id:
        raise PermissionError("You can only edit your own templates")

    if "template_type" in updates and updates["template_type"] is not None:
        if updates["template_type"] not in VALID_TEMPLATE_TYPES:
            raise ValueError(
                f"Invalid template_type. Must be one of: {', '.join(sorted(VALID_TEMPLATE_TYPES))}"
            )

    for key, value in updates.items():
        if value is not None and hasattr(template, key):
            setattr(template, key, value)

    db.commit()
    db.refresh(template)
    return template


# ---------------------------------------------------------------------------
# 7. Delete template (soft delete)
# ---------------------------------------------------------------------------


def delete_template(
    template_id: uuid.UUID,
    user_id: str,
    db: Session,
) -> None:
    """Soft-delete a custom template (set is_active=False)."""
    template = db.query(EmailTemplate).filter(EmailTemplate.id == template_id).first()
    if template is None:
        raise ValueError("Template not found")
    if template.is_default:
        raise PermissionError("System default templates cannot be deleted")
    if template.user_id != user_id:
        raise PermissionError("You can only delete your own templates")

    template.is_active = False
    db.commit()


# ---------------------------------------------------------------------------
# 8. Increment usage count
# ---------------------------------------------------------------------------


def increment_template_usage(template_id: uuid.UUID, db: Session) -> None:
    """Bump the usage_count by 1 after a send."""
    template = db.query(EmailTemplate).filter(EmailTemplate.id == template_id).first()
    if template:
        template.usage_count = (template.usage_count or 0) + 1
        db.commit()


# ---------------------------------------------------------------------------
# 9. AI-drafted email
# ---------------------------------------------------------------------------

_DRAFT_SYSTEM_PROMPT = (
    "You are an email drafting assistant for a CPA/financial advisor. "
    "Draft a professional, warm, and concise client email. The email should:\n"
    "- Be 100-200 words (short and actionable)\n"
    "- Use a warm but professional tone appropriate for a CPA-client relationship\n"
    "- Reference specific details from the client context when relevant\n"
    "- Include a clear call-to-action (schedule meeting, send documents, confirm, etc.)\n"
    "- Not include a subject line (that will be generated separately)\n"
    "- Not include a greeting or sign-off (those will be added by the template wrapper)\n"
    "- If a scheduling link is available, mention it naturally\n"
    "Return ONLY the email body text. No markdown formatting, no extra commentary."
)

_SUBJECT_SYSTEM_PROMPT = (
    "Given this email body, generate a professional email subject line. "
    "5-10 words. Include the client name. Return ONLY the subject line."
)


async def draft_email_with_ai(
    user_id: str,
    client_id: uuid.UUID,
    purpose: str,
    db: Session,
    additional_context: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Use GPT-4o to draft a contextual email based on the client's actual data.

    Returns {"subject": ..., "body_html": ..., "body_text": ..., "ai_drafted": True}.
    """
    from openai import AsyncOpenAI

    settings = get_settings()
    openai_client = AsyncOpenAI(api_key=settings.openai_api_key)

    # --- Gather context ---
    client = db.query(Client).filter(Client.id == client_id).first()
    if client is None:
        raise ValueError("Client not found")

    db_user = db.query(User).filter(User.clerk_id == user_id).first()

    preparer_name = "Your advisor"
    preparer_firm = ""
    scheduling_url = ""
    if db_user:
        parts = [db_user.first_name or "", db_user.last_name or ""]
        preparer_name = " ".join(p for p in parts if p).strip() or "Your advisor"
        scheduling_url = db_user.scheduling_url or ""

        member = (
            db.query(OrganizationMember)
            .filter(
                OrganizationMember.user_id == user_id,
                OrganizationMember.is_active.is_(True),
            )
            .first()
        )
        if member:
            org = db.query(Organization).filter(Organization.id == member.org_id).first()
            if org and org.org_type != "personal":
                preparer_firm = org.name

    # --- Assemble client context via the unified context assembler ---
    from app.services.context_assembler import (
        ContextPurpose,
        assemble_context,
        format_context_for_prompt,
    )

    ai_ctx = await assemble_context(
        db, client_id=client_id, user_id=user_id,
        purpose=ContextPurpose.EMAIL_DRAFT,
    )
    formatted_context = format_context_for_prompt(ai_ctx, ContextPurpose.EMAIL_DRAFT)

    # --- Build user message ---
    context_parts = [
        f"PURPOSE: {purpose}",
        "",
        formatted_context,
        "",
        "ADVISOR INFORMATION:",
        f"  Name: {preparer_name}",
    ]
    if preparer_firm:
        context_parts.append(f"  Firm: {preparer_firm}")
    if scheduling_url:
        context_parts.append(f"  Scheduling link: {scheduling_url}")

    if additional_context:
        context_parts.append("")
        context_parts.append(f"ADDITIONAL INSTRUCTIONS: {additional_context}")

    user_message = "\n".join(context_parts)

    # --- Call GPT-4o for body ---
    body_response = await openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": _DRAFT_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        temperature=0.7,
        max_tokens=500,
    )
    ai_body = body_response.choices[0].message.content.strip()

    # --- Call GPT-4o for subject line ---
    subject_response = await openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": _SUBJECT_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Client name: {client.name}\n\nEmail body:\n{ai_body}",
            },
        ],
        temperature=0.5,
        max_tokens=30,
    )
    ai_subject = subject_response.choices[0].message.content.strip().strip('"')

    # --- Wrap in HTML template ---
    body_html = _build_email_html(
        client_name=client.name,
        body_text=ai_body,
        preparer_name=preparer_name,
        preparer_firm=preparer_firm,
        scheduling_url=scheduling_url,
    )

    body_text_plain = (
        f"Hi {client.name},\n\n"
        f"{ai_body}\n\n"
        f"Best regards,\n{preparer_name}"
        + (f"\n{preparer_firm}" if preparer_firm else "")
    )

    return {
        "subject": ai_subject,
        "body_html": body_html,
        "body_text": body_text_plain,
        "ai_drafted": True,
    }


def _build_email_html(
    client_name: str,
    body_text: str,
    preparer_name: str,
    preparer_firm: str,
    scheduling_url: str,
) -> str:
    """Wrap AI-drafted body in the standard Callwen email template."""
    # Convert plain text paragraphs to HTML
    paragraphs = body_text.split("\n\n")
    body_paragraphs = ""
    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        escaped = html.escape(p).replace("\n", "<br>")
        body_paragraphs += (
            f'  <p style="margin:0 0 16px;color:#374151;font-size:15px;line-height:1.6;">'
            f"{escaped}</p>\n"
        )

    scheduling_block = ""
    if scheduling_url:
        scheduling_block = f"""\
  <table cellpadding="0" cellspacing="0" style="margin:16px 0 24px;">
  <tr><td style="background:#1e40af;border-radius:6px;">
    <a href="{html.escape(scheduling_url)}"
       style="display:inline-block;padding:12px 28px;color:#ffffff;font-size:15px;font-weight:600;text-decoration:none;">
      Book a Time
    </a>
  </td></tr>
  </table>
"""

    firm_line = f"<br>{html.escape(preparer_firm)}" if preparer_firm else ""

    return f"""\
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;background:#f7f7f7;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f7f7f7;padding:40px 0;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.1);">
<tr><td style="background:#1e40af;padding:28px 40px;">
  <h1 style="margin:0;color:#ffffff;font-size:20px;font-weight:600;">{html.escape(preparer_name)}</h1>
</td></tr>
<tr><td style="padding:32px 40px;">
  <p style="margin:0 0 16px;color:#374151;font-size:15px;line-height:1.6;">
    Hi {html.escape(client_name)},
  </p>
{body_paragraphs}\
{scheduling_block}\
  <p style="margin:24px 0 0;color:#374151;font-size:15px;line-height:1.6;">
    Best regards,<br>
    <strong>{html.escape(preparer_name)}</strong>{firm_line}
  </p>
</td></tr>
<tr><td style="padding:24px 40px;border-top:1px solid #e5e7eb;background:#f9fafb;">
  <p style="margin:0;color:#9ca3af;font-size:11px;line-height:1.5;">
    Sent by {html.escape(preparer_name)} via Callwen. If you have questions, reply directly to this email.
  </p>
</td></tr>
</table>
</td></tr>
</table>
</body>
</html>"""


# ---------------------------------------------------------------------------
# 10. Thread management
# ---------------------------------------------------------------------------


def get_or_create_thread(
    db: Session,
    client_id: uuid.UUID,
    thread_type: str,
    thread_year: int,
    thread_quarter: Optional[int] = None,
) -> uuid.UUID:
    """
    Return the existing thread_id for a client+type+year+quarter combination,
    or generate a new UUID if no thread exists yet.
    """
    q = db.query(ClientCommunication.thread_id).filter(
        ClientCommunication.client_id == client_id,
        ClientCommunication.thread_type == thread_type,
        ClientCommunication.thread_year == thread_year,
        ClientCommunication.thread_id.isnot(None),
    )
    if thread_quarter is not None:
        q = q.filter(ClientCommunication.thread_quarter == thread_quarter)
    else:
        q = q.filter(ClientCommunication.thread_quarter.is_(None))

    row = q.first()
    if row and row[0]:
        return row[0]

    return uuid.uuid4()


def get_thread_history(
    db: Session,
    client_id: uuid.UUID,
    thread_id: uuid.UUID,
) -> List[ClientCommunication]:
    """Return all communications in a thread, ordered chronologically."""
    return (
        db.query(ClientCommunication)
        .filter(
            ClientCommunication.client_id == client_id,
            ClientCommunication.thread_id == thread_id,
        )
        .order_by(ClientCommunication.sent_at.asc())
        .all()
    )


def get_thread_open_items(
    db: Session,
    client_id: uuid.UUID,
    thread_id: uuid.UUID,
) -> List[OpenItem]:
    """
    Scan all communications in a thread and return only open items.

    Aggregates open_items from each email, then cross-references against
    open_items_resolved in later emails to exclude resolved ones.
    """
    comms = get_thread_history(db, client_id, thread_id)

    # Collect all resolved email IDs from resolved items across the thread
    resolved_keys: set[tuple[str, str]] = set()
    for comm in comms:
        for item in (comm.open_items_resolved or []):
            # Key: (question, asked_in_email_id) to match against open items
            resolved_keys.add((
                item.get("question", ""),
                item.get("asked_in_email_id", ""),
            ))

    # Collect open items that haven't been resolved
    result: List[OpenItem] = []
    for comm in comms:
        for item in (comm.open_items or []):
            if item.get("status") == "resolved":
                continue
            key = (item.get("question", ""), item.get("asked_in_email_id", str(comm.id)))
            if key in resolved_keys:
                continue
            result.append(OpenItem(
                question=item["question"],
                asked_in_email_id=uuid.UUID(item.get("asked_in_email_id", str(comm.id))),
                asked_date=datetime.fromisoformat(item["asked_date"])
                if "asked_date" in item
                else comm.sent_at,
                status="open",
                resolved_in_email_id=None,
                resolved_date=None,
            ))

    return result


def extract_open_items_from_email(email_body: str) -> List[Dict[str, str]]:
    """
    Use GPT-4o-mini to extract questions and action items from an email body
    that are directed at the recipient (client).

    Returns a list of dicts: [{"question": "...", "category": "awaiting_response"}]
    """
    if not email_body or len(email_body.strip()) < 20:
        return []

    settings = get_settings()
    if not settings.openai_api_key:
        return []

    try:
        import json as _json

        from openai import OpenAI

        client = OpenAI(api_key=settings.openai_api_key)

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Extract questions and action items from this email that the sender "
                        "is asking the recipient to answer or do. Return a JSON array of objects "
                        'with "question" (the question/request text) and "category" '
                        '(one of: "awaiting_response", "document_request", "confirmation_needed", '
                        '"scheduling", "information_request"). '
                        "Only include items that clearly require a response or action from the "
                        "recipient. Return [] if there are no actionable items. "
                        "Return ONLY the JSON array, no other text."
                    ),
                },
                {"role": "user", "content": email_body[:3000]},
            ],
            temperature=0.1,
            max_tokens=500,
        )

        content = response.choices[0].message.content.strip()
        # Strip markdown code fences if present
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*", "", content)
            content = re.sub(r"\s*```$", "", content)

        items = _json.loads(content)
        if not isinstance(items, list):
            return []

        # Validate structure
        return [
            {"question": item["question"], "category": item.get("category", "awaiting_response")}
            for item in items
            if isinstance(item, dict) and "question" in item
        ]

    except Exception:
        logger.warning("Failed to extract open items from email (non-fatal)", exc_info=True)
        return []


def resolve_open_items(
    db: Session,
    thread_id: uuid.UUID,
    resolved_items: List[Dict[str, Any]],
    resolving_email_id: uuid.UUID,
) -> int:
    """
    Mark specified open items as resolved.

    Updates the open_items JSONB on the original email that asked each question.
    Also stores the resolution record on the resolving email's open_items_resolved.

    *resolved_items* is a list of dicts with at minimum:
      {"question": "...", "asked_in_email_id": "..."}

    Returns the number of items resolved.
    """
    if not resolved_items:
        return 0

    now = datetime.now(timezone.utc)
    resolved_count = 0

    # Group resolved items by the email they were asked in
    by_email: Dict[str, List[Dict[str, Any]]] = {}
    for item in resolved_items:
        email_id = item.get("asked_in_email_id", "")
        if email_id:
            by_email.setdefault(email_id, []).append(item)

    # Update the original emails' open_items to mark as resolved
    for email_id_str, items_to_resolve in by_email.items():
        try:
            email_uuid = uuid.UUID(email_id_str)
        except (ValueError, TypeError):
            continue

        original = (
            db.query(ClientCommunication)
            .filter(ClientCommunication.id == email_uuid)
            .first()
        )
        if not original or not original.open_items:
            continue

        questions_to_resolve = {item["question"] for item in items_to_resolve}
        updated_items = []
        for oi in original.open_items:
            if oi.get("question") in questions_to_resolve and oi.get("status") != "resolved":
                oi["status"] = "resolved"
                oi["resolved_in_email_id"] = str(resolving_email_id)
                oi["resolved_date"] = now.isoformat()
                resolved_count += 1
            updated_items.append(oi)

        original.open_items = updated_items

    # Store resolution records on the resolving email
    resolving_comm = (
        db.query(ClientCommunication)
        .filter(ClientCommunication.id == resolving_email_id)
        .first()
    )
    if resolving_comm:
        resolution_records = [
            {
                "question": item["question"],
                "asked_in_email_id": item.get("asked_in_email_id", ""),
                "resolved_date": now.isoformat(),
            }
            for item in resolved_items
        ]
        resolving_comm.open_items_resolved = resolution_records

    db.commit()
    return resolved_count


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _html_to_text(html_content: str) -> str:
    """Strip HTML tags for a plain text email fallback."""
    # Remove style/script blocks
    text = re.sub(r"<(style|script)[^>]*>.*?</\1>", "", html_content, flags=re.DOTALL | re.IGNORECASE)
    # Convert <br>, <p>, <div>, <tr>, <li> to newlines
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</?(p|div|tr|table|h[1-6])[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<li[^>]*>", "\n• ", text, flags=re.IGNORECASE)
    # Extract link text with URL
    text = re.sub(r'<a[^>]+href="([^"]*)"[^>]*>(.*?)</a>', r"\2 (\1)", text, flags=re.IGNORECASE)
    # Strip remaining tags
    text = re.sub(r"<[^>]+>", "", text)
    # Decode HTML entities
    text = html.unescape(text)
    # Clean up whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _replace_vars(template_str: str, variables: Dict[str, str]) -> str:
    """Replace {{var_name}} placeholders with values."""
    def replacer(match: re.Match) -> str:
        key = match.group(1).strip()
        return variables.get(key, match.group(0))

    return re.sub(r"\{\{(\w+)\}\}", replacer, template_str)


def _render_body(body_template: str, variables: Dict[str, str]) -> str:
    """
    Render body template with variable replacement and conditional blocks.

    Supports mustache-style conditionals:
      {{#var_name}}...shown if var_name is truthy...{{/var_name}}
      {{^var_name}}...shown if var_name is falsy...{{/var_name}}
    """
    result = body_template

    # Handle conditional blocks: {{#key}}...{{/key}} (show if truthy)
    def handle_truthy(match: re.Match) -> str:
        key = match.group(1)
        content = match.group(2)
        value = variables.get(key, "")
        return content if value else ""

    result = re.sub(
        r"\{\{#(\w+)\}\}(.*?)\{\{/\1\}\}",
        handle_truthy,
        result,
        flags=re.DOTALL,
    )

    # Handle inverse blocks: {{^key}}...{{/key}} (show if falsy)
    def handle_falsy(match: re.Match) -> str:
        key = match.group(1)
        content = match.group(2)
        value = variables.get(key, "")
        return content if not value else ""

    result = re.sub(
        r"\{\{\^(\w+)\}\}(.*?)\{\{/\1\}\}",
        handle_falsy,
        result,
        flags=re.DOTALL,
    )

    # Replace simple variables
    result = _replace_vars(result, variables)

    return result

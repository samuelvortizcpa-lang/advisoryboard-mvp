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

from app.core.config import get_settings
from app.models.action_item import ActionItem
from app.models.client import Client
from app.models.client_communication import ClientCommunication
from app.models.document import Document
from app.models.email_template import EmailTemplate
from app.models.organization import Organization
from app.models.organization_member import OrganizationMember
from app.models.user import User

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
    )
    db.add(comm)
    db.commit()
    db.refresh(comm)
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

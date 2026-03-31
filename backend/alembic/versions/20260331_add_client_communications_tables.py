"""add client_communications, email_templates, follow_up_reminders tables

Revision ID: e0f1a2b3c4d5
Revises: d9e0f1a2b3c4
Create Date: 2026-03-31

Client email communication system: outbound email logging, reusable
templates with merge variables, and follow-up reminders.
Also adds scheduling_url to users table.
"""

import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "e0f1a2b3c4d5"
down_revision = "d9e0f1a2b3c4"


def upgrade() -> None:
    # ------------------------------------------------------------------
    # email_templates (created first — referenced by client_communications)
    # ------------------------------------------------------------------
    op.create_table(
        "email_templates",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("user_id", sa.String(255), nullable=True, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("subject_template", sa.String(500), nullable=False),
        sa.Column("body_template", sa.Text(), nullable=False),
        sa.Column("template_type", sa.String(50), nullable=False),
        sa.Column(
            "is_default", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default="true"
        ),
        sa.Column(
            "usage_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("user_id", "name", name="uq_email_templates_user_name"),
    )

    # ------------------------------------------------------------------
    # client_communications
    # ------------------------------------------------------------------
    op.create_table(
        "client_communications",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column(
            "client_id",
            UUID(as_uuid=True),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("user_id", sa.String(255), nullable=False, index=True),
        sa.Column(
            "communication_type",
            sa.String(50),
            nullable=False,
            server_default="email",
        ),
        sa.Column("subject", sa.String(500), nullable=False),
        sa.Column("body_html", sa.Text(), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("recipient_email", sa.String(255), nullable=False),
        sa.Column("recipient_name", sa.String(255), nullable=True),
        sa.Column(
            "template_id",
            UUID(as_uuid=True),
            sa.ForeignKey("email_templates.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "status", sa.String(50), nullable=False, server_default="sent"
        ),
        sa.Column("resend_message_id", sa.String(255), nullable=True),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column(
            "sent_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # ------------------------------------------------------------------
    # follow_up_reminders
    # ------------------------------------------------------------------
    op.create_table(
        "follow_up_reminders",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column(
            "communication_id",
            UUID(as_uuid=True),
            sa.ForeignKey("client_communications.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "client_id",
            UUID(as_uuid=True),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("user_id", sa.String(255), nullable=False, index=True),
        sa.Column(
            "remind_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column(
            "status", sa.String(50), nullable=False, server_default="pending"
        ),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    # Index for the scheduler query: pending reminders that are due
    op.create_index(
        "ix_follow_up_reminders_pending_due",
        "follow_up_reminders",
        ["status", "remind_at"],
    )

    # ------------------------------------------------------------------
    # users.scheduling_url
    # ------------------------------------------------------------------
    op.add_column(
        "users",
        sa.Column("scheduling_url", sa.String(500), nullable=True),
    )

    # ------------------------------------------------------------------
    # Seed 5 default email templates
    # ------------------------------------------------------------------
    templates_table = sa.table(
        "email_templates",
        sa.column("id", UUID(as_uuid=True)),
        sa.column("user_id", sa.String),
        sa.column("name", sa.String),
        sa.column("subject_template", sa.String),
        sa.column("body_template", sa.Text),
        sa.column("template_type", sa.String),
        sa.column("is_default", sa.Boolean),
        sa.column("is_active", sa.Boolean),
        sa.column("usage_count", sa.Integer),
    )

    op.bulk_insert(templates_table, [
        {
            "id": uuid.uuid4(),
            "user_id": None,
            "name": "Quarterly Review Meeting",
            "subject_template": "{{preparer_name}} \u2014 Quarterly Review for {{client_name}}",
            "body_template": _template_quarterly_review(),
            "template_type": "meeting_request",
            "is_default": True,
            "is_active": True,
            "usage_count": 0,
        },
        {
            "id": uuid.uuid4(),
            "user_id": None,
            "name": "Follow-Up After Meeting",
            "subject_template": "Following Up \u2014 {{client_name}}",
            "body_template": _template_follow_up(),
            "template_type": "follow_up",
            "is_default": True,
            "is_active": True,
            "usage_count": 0,
        },
        {
            "id": uuid.uuid4(),
            "user_id": None,
            "name": "Document Request",
            "subject_template": "Documents Needed \u2014 {{client_name}}",
            "body_template": _template_document_request(),
            "template_type": "document_request",
            "is_default": True,
            "is_active": True,
            "usage_count": 0,
        },
        {
            "id": uuid.uuid4(),
            "user_id": None,
            "name": "Engagement Status Update",
            "subject_template": "Engagement Update \u2014 {{client_name}}",
            "body_template": _template_engagement_update(),
            "template_type": "engagement_update",
            "is_default": True,
            "is_active": True,
            "usage_count": 0,
        },
        {
            "id": uuid.uuid4(),
            "user_id": None,
            "name": "Year-End Planning Outreach",
            "subject_template": "Year-End Tax Planning \u2014 {{client_name}}",
            "body_template": _template_year_end(),
            "template_type": "year_end",
            "is_default": True,
            "is_active": True,
            "usage_count": 0,
        },
    ])


def downgrade() -> None:
    op.drop_index("ix_follow_up_reminders_pending_due", table_name="follow_up_reminders")
    op.drop_table("follow_up_reminders")
    op.drop_table("client_communications")
    op.drop_table("email_templates")
    op.drop_column("users", "scheduling_url")


# ---------------------------------------------------------------------------
# Template HTML builders — matches the consent email visual style:
# blue header bar (#1e40af), white body, gray footer, inline styles.
# ---------------------------------------------------------------------------

_WRAPPER_START = """\
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;background:#f7f7f7;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f7f7f7;padding:40px 0;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.1);">"""

_FOOTER = """\
<tr><td style="padding:24px 40px;border-top:1px solid #e5e7eb;background:#f9fafb;">
  <p style="margin:0;color:#9ca3af;font-size:11px;line-height:1.5;">
    Sent by {{preparer_name}} via Callwen. If you have questions, reply directly to this email.
  </p>
</td></tr>
</table>
</td></tr>
</table>
</body>
</html>"""


def _wrap(header: str, body: str) -> str:
    return (
        _WRAPPER_START
        + f'\n<tr><td style="background:#1e40af;padding:28px 40px;">'
        f'\n  <h1 style="margin:0;color:#ffffff;font-size:20px;font-weight:600;">{header}</h1>'
        f"\n</td></tr>"
        f'\n<tr><td style="padding:32px 40px;">'
        f"\n{body}"
        f"\n</td></tr>\n"
        + _FOOTER
    )


def _template_quarterly_review() -> str:
    return _wrap(
        "Quarterly Review",
        """\
  <p style="margin:0 0 16px;color:#374151;font-size:15px;line-height:1.6;">
    Dear {{client_name}},
  </p>
  <p style="margin:0 0 16px;color:#374151;font-size:15px;line-height:1.6;">
    It's time for our quarterly review. I'd like to go over your recent financial
    activity, discuss any upcoming deadlines, and explore planning opportunities
    that may benefit you this quarter.
  </p>
  <p style="margin:0 0 16px;color:#374151;font-size:15px;line-height:1.6;">
    Topics we'll cover:
  </p>
  <ul style="margin:0 0 16px;padding-left:20px;color:#374151;font-size:15px;line-height:1.8;">
    <li>Review of recent transactions and financial activity</li>
    <li>Upcoming tax deadlines and filing requirements</li>
    <li>Tax planning strategies and optimization opportunities</li>
    <li>Any questions or concerns you may have</li>
  </ul>
  <p style="margin:0 0 24px;color:#374151;font-size:15px;line-height:1.6;">
    Please schedule a time that works for you:
  </p>
  {{#scheduling_link}}
  <table cellpadding="0" cellspacing="0" style="margin:0 auto 24px;">
  <tr><td style="background:#1e40af;border-radius:6px;">
    <a href="{{scheduling_link}}"
       style="display:inline-block;padding:14px 32px;color:#ffffff;font-size:16px;font-weight:600;text-decoration:none;">
      Schedule Meeting
    </a>
  </td></tr>
  </table>
  {{/scheduling_link}}
  {{^scheduling_link}}
  <p style="margin:0 0 24px;color:#374151;font-size:15px;line-height:1.6;">
    <strong>Reply to this email</strong> with a few dates and times that work for you, and I'll get us set up.
  </p>
  {{/scheduling_link}}
  <p style="margin:0;color:#6b7280;font-size:13px;line-height:1.5;">
    Looking forward to connecting with you.
  </p>""",
    )


def _template_follow_up() -> str:
    return _wrap(
        "Following Up",
        """\
  <p style="margin:0 0 16px;color:#374151;font-size:15px;line-height:1.6;">
    Dear {{client_name}},
  </p>
  <p style="margin:0 0 16px;color:#374151;font-size:15px;line-height:1.6;">
    Thank you for taking the time to meet. I wanted to follow up with a summary
    of what we discussed and outline our next steps.
  </p>
  <p style="margin:0 0 8px;color:#374151;font-size:15px;font-weight:600;">
    Key Takeaways:
  </p>
  <p style="margin:0 0 16px;color:#374151;font-size:15px;line-height:1.6;">
    {{meeting_summary}}
  </p>
  <p style="margin:0 0 8px;color:#374151;font-size:15px;font-weight:600;">
    Action Items:
  </p>
  <p style="margin:0 0 16px;color:#374151;font-size:15px;line-height:1.6;">
    {{action_items_summary}}
  </p>
  <p style="margin:0 0 16px;color:#374151;font-size:15px;line-height:1.6;">
    If you have any questions about the items above, don't hesitate to reach out.
    I'll follow up on my action items and keep you posted on progress.
  </p>
  <p style="margin:0;color:#6b7280;font-size:13px;line-height:1.5;">
    Best regards,<br>{{preparer_name}}
  </p>""",
    )


def _template_document_request() -> str:
    return _wrap(
        "Documents Needed",
        """\
  <p style="margin:0 0 16px;color:#374151;font-size:15px;line-height:1.6;">
    Dear {{client_name}},
  </p>
  <p style="margin:0 0 16px;color:#374151;font-size:15px;line-height:1.6;">
    To continue working on your engagement, I need the following documents
    at your earliest convenience:
  </p>
  <div style="margin:0 0 16px;padding:16px 20px;background:#f3f4f6;border-radius:6px;border-left:4px solid #1e40af;">
    <p style="margin:0;color:#374151;font-size:15px;line-height:1.8;">
      {{document_list}}
    </p>
  </div>
  {{#deadline}}
  <p style="margin:0 0 16px;color:#374151;font-size:15px;line-height:1.6;">
    <strong>Please submit these by {{deadline}}</strong> so we can stay on track
    with our timeline.
  </p>
  {{/deadline}}
  <p style="margin:0 0 16px;color:#374151;font-size:15px;line-height:1.6;">
    You can securely upload your documents by replying to this email with
    attachments, or I can provide a secure upload link if you prefer.
  </p>
  <p style="margin:0 0 16px;color:#374151;font-size:15px;line-height:1.6;">
    If you have any questions about what's needed, just let me know.
  </p>
  <p style="margin:0;color:#6b7280;font-size:13px;line-height:1.5;">
    Thank you,<br>{{preparer_name}}
  </p>""",
    )


def _template_engagement_update() -> str:
    return _wrap(
        "Engagement Update",
        """\
  <p style="margin:0 0 16px;color:#374151;font-size:15px;line-height:1.6;">
    Dear {{client_name}},
  </p>
  <p style="margin:0 0 16px;color:#374151;font-size:15px;line-height:1.6;">
    I wanted to provide you with an update on where things stand with
    your current engagement.
  </p>
  <table cellpadding="0" cellspacing="0" style="width:100%;margin:0 0 20px;border:1px solid #e5e7eb;border-radius:6px;overflow:hidden;">
    <tr style="background:#f9fafb;">
      <td style="padding:12px 16px;color:#6b7280;font-size:13px;font-weight:600;">Open Items</td>
      <td style="padding:12px 16px;color:#374151;font-size:15px;font-weight:600;">{{open_items_count}}</td>
    </tr>
    <tr>
      <td style="padding:12px 16px;color:#6b7280;font-size:13px;font-weight:600;border-top:1px solid #e5e7eb;">Next Deadline</td>
      <td style="padding:12px 16px;color:#374151;font-size:15px;border-top:1px solid #e5e7eb;">{{next_deadline}}</td>
    </tr>
  </table>
  <p style="margin:0 0 16px;color:#374151;font-size:15px;line-height:1.6;">
    Everything is progressing well. I'm actively working through the remaining
    items and will keep you informed of any developments. If anything on your
    end has changed or if you have questions, please don't hesitate to reach out.
  </p>
  <p style="margin:0;color:#6b7280;font-size:13px;line-height:1.5;">
    Best regards,<br>{{preparer_name}}
  </p>""",
    )


def _template_year_end() -> str:
    return _wrap(
        "Year-End Tax Planning",
        """\
  <p style="margin:0 0 16px;color:#374151;font-size:15px;line-height:1.6;">
    Dear {{client_name}},
  </p>
  <p style="margin:0 0 16px;color:#374151;font-size:15px;line-height:1.6;">
    As we approach year-end, I wanted to reach out about tax planning
    opportunities that could benefit you before December 31st.
  </p>
  <p style="margin:0 0 8px;color:#374151;font-size:15px;font-weight:600;">
    Common year-end strategies to discuss:
  </p>
  <ul style="margin:0 0 16px;padding-left:20px;color:#374151;font-size:15px;line-height:1.8;">
    <li>Income timing and deferral opportunities</li>
    <li>Retirement contribution maximization</li>
    <li>Charitable giving strategies</li>
    <li>Capital gains and loss harvesting</li>
    <li>Business expense acceleration</li>
  </ul>
  <p style="margin:0 0 16px;color:#374151;font-size:15px;line-height:1.6;">
    I'd like to schedule a planning session to review your specific situation
    and identify the strategies that make the most sense for you this year.
  </p>
  {{#scheduling_link}}
  <table cellpadding="0" cellspacing="0" style="margin:0 auto 24px;">
  <tr><td style="background:#1e40af;border-radius:6px;">
    <a href="{{scheduling_link}}"
       style="display:inline-block;padding:14px 32px;color:#ffffff;font-size:16px;font-weight:600;text-decoration:none;">
      Schedule Planning Session
    </a>
  </td></tr>
  </table>
  {{/scheduling_link}}
  {{^scheduling_link}}
  <p style="margin:0 0 24px;color:#374151;font-size:15px;line-height:1.6;">
    <strong>Reply to this email</strong> with a few times that work for you, and I'll get a session on the calendar.
  </p>
  {{/scheduling_link}}
  <p style="margin:0;color:#6b7280;font-size:13px;line-height:1.5;">
    The sooner we connect, the more options we'll have. Looking forward to it.
  </p>""",
    )

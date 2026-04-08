"""Add checkin_templates and checkin_responses tables with default templates

Revision ID: l2m3n4o5p6q7
Revises: k1l2m3n4o5p6
Create Date: 2026-04-07
"""

import json

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision = "l2m3n4o5p6q7"
down_revision = "k1l2m3n4o5p6"
branch_labels = None
depends_on = None

# ---------------------------------------------------------------------------
# Default template seed data
# ---------------------------------------------------------------------------

DEFAULT_TEMPLATES = [
    {
        "name": "Quarterly Advisory Check-in",
        "description": "A comprehensive pre-meeting questionnaire for quarterly advisory sessions.",
        "questions": [
            {"id": "q1", "text": "How would you rate your overall business health right now?", "type": "rating"},
            {"id": "q2", "text": "What's the single biggest win in your business since we last spoke?", "type": "textarea"},
            {"id": "q3", "text": "What's keeping you up at night? Any concerns or challenges?", "type": "textarea"},
            {
                "id": "q4",
                "text": "Have there been any major changes since we last met?",
                "type": "multiselect",
                "options": [
                    "New hire",
                    "Lost key employee",
                    "New revenue stream",
                    "Major expense",
                    "Legal/regulatory issue",
                    "Personal life event",
                    "None",
                ],
            },
            {"id": "q5", "text": "What would you most like to discuss in our next meeting?", "type": "textarea"},
            {"id": "q6", "text": "Anything else I should know before we meet?", "type": "textarea"},
        ],
    },
    {
        "name": "Tax Season Intake",
        "description": "Pre-filing questionnaire to capture life events, income changes, and tax concerns.",
        "questions": [
            {
                "id": "q1",
                "text": "Did you have any major life events this year?",
                "type": "multiselect",
                "options": [
                    "Marriage",
                    "Divorce",
                    "New child",
                    "Home purchase or sale",
                    "Job change",
                    "Retirement",
                    "Inheritance",
                    "None",
                ],
            },
            {"id": "q2", "text": "Any new sources of income or changes to existing income?", "type": "textarea"},
            {
                "id": "q3",
                "text": "Did you start, buy, or sell a business this year?",
                "type": "select",
                "options": ["Yes", "No"],
            },
            {"id": "q4", "text": "Any large purchases, investments, or charitable donations?", "type": "textarea"},
            {"id": "q5", "text": "Are there specific tax concerns or questions you want me to address?", "type": "textarea"},
        ],
    },
    {
        "name": "Quick Pulse Check",
        "description": "A short 3-question check-in for lightweight touchpoints between meetings.",
        "questions": [
            {"id": "q1", "text": "On a scale of 1\u20135, how confident are you about your financial direction?", "type": "rating"},
            {"id": "q2", "text": "One thing going well:", "type": "text"},
            {"id": "q3", "text": "One thing you need help with:", "type": "text"},
        ],
    },
]


def upgrade() -> None:
    # ── checkin_templates ──────────────────────────────────────────────
    op.create_table(
        "checkin_templates",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("questions", JSONB, nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_checkin_templates_org_id", "checkin_templates", ["org_id"])

    # ── checkin_responses ──────────────────────────────────────────────
    op.create_table(
        "checkin_responses",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("client_id", UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("template_id", UUID(as_uuid=True), sa.ForeignKey("checkin_templates.id"), nullable=False),
        sa.Column("sent_by", sa.String(255), nullable=False),
        sa.Column("sent_to_email", sa.String(255), nullable=False),
        sa.Column("sent_to_name", sa.String(255), nullable=True),
        sa.Column("access_token", sa.String(64), nullable=False, unique=True),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("responses", JSONB, nullable=True),
        sa.Column("response_text", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # pgvector column — added via raw SQL (same pattern as chat_sessions migration)
    op.execute("ALTER TABLE checkin_responses ADD COLUMN response_embedding vector(1536)")

    op.create_index("ix_checkin_responses_client_id", "checkin_responses", ["client_id"])
    op.create_index("ix_checkin_responses_template_id", "checkin_responses", ["template_id"])
    op.create_index("ix_checkin_responses_status", "checkin_responses", ["status"])

    # ── Seed default templates ─────────────────────────────────────────
    checkin_templates = sa.table(
        "checkin_templates",
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("questions", JSONB),
        sa.column("is_default", sa.Boolean),
        sa.column("is_active", sa.Boolean),
    )
    for tmpl in DEFAULT_TEMPLATES:
        op.execute(
            checkin_templates.insert().values(
                name=tmpl["name"],
                description=tmpl["description"],
                questions=json.dumps(tmpl["questions"]),
                is_default=True,
                is_active=True,
            )
        )


def downgrade() -> None:
    op.drop_table("checkin_responses")
    op.drop_table("checkin_templates")

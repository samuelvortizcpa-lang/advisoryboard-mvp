"""add engagement_templates, engagement_template_tasks, and client_engagements

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-04-06

Recurring deadline automation: engagement templates define the standard
task calendar for each entity type, template_tasks hold the individual
deadlines, and client_engagements link clients to templates.
"""

import json
import uuid

import sqlalchemy as sa
from alembic import op

revision = "e2f3a4b5c6d7"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── engagement_templates ──────────────────────────────────────────────
    op.create_table(
        "engagement_templates",
        sa.Column(
            "id", sa.UUID(), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("entity_types", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column(
            "is_system", sa.Boolean(), nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # ── engagement_template_tasks ─────────────────────────────────────────
    op.create_table(
        "engagement_template_tasks",
        sa.Column(
            "id", sa.UUID(), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "template_id", sa.UUID(),
            sa.ForeignKey("engagement_templates.id", ondelete="CASCADE"),
            nullable=False, index=True,
        ),
        sa.Column("task_name", sa.String(300), nullable=False),
        sa.Column("category", sa.String(50), nullable=True),
        sa.Column("recurrence", sa.String(20), nullable=False),
        sa.Column("month", sa.Integer(), nullable=True),
        sa.Column("day", sa.Integer(), nullable=True),
        sa.Column(
            "lead_days", sa.Integer(), nullable=False,
            server_default=sa.text("21"),
        ),
        sa.Column(
            "priority", sa.String(10), nullable=False,
            server_default="medium",
        ),
        sa.Column(
            "linked_email_template_id", sa.UUID(),
            sa.ForeignKey("email_templates.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "display_order", sa.Integer(), nullable=False,
            server_default=sa.text("0"),
        ),
    )

    # ── client_engagements ────────────────────────────────────────────────
    op.create_table(
        "client_engagements",
        sa.Column(
            "id", sa.UUID(), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "client_id", sa.UUID(),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "template_id", sa.UUID(),
            sa.ForeignKey("engagement_templates.id"),
            nullable=False,
        ),
        sa.Column("start_year", sa.Integer(), nullable=False),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "custom_overrides", sa.dialects.postgresql.JSONB(), nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.UniqueConstraint(
            "client_id", "template_id",
            name="uq_client_engagement",
        ),
    )

    # ── Seed 5 system templates ───────────────────────────────────────────
    _seed_templates()


def downgrade() -> None:
    op.drop_table("client_engagements")
    op.drop_table("engagement_template_tasks")
    op.drop_table("engagement_templates")


# ---------------------------------------------------------------------------
# Seed data
# ---------------------------------------------------------------------------

def _seed_templates() -> None:
    conn = op.get_bind()
    templates_table = sa.table(
        "engagement_templates",
        sa.column("id", sa.UUID()),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("entity_types", sa.dialects.postgresql.JSONB),
        sa.column("is_system", sa.Boolean),
    )
    tasks_table = sa.table(
        "engagement_template_tasks",
        sa.column("id", sa.UUID()),
        sa.column("template_id", sa.UUID()),
        sa.column("task_name", sa.String),
        sa.column("category", sa.String),
        sa.column("recurrence", sa.String),
        sa.column("month", sa.Integer),
        sa.column("day", sa.Integer),
        sa.column("lead_days", sa.Integer),
        sa.column("priority", sa.String),
        sa.column("display_order", sa.Integer),
    )

    TEMPLATES = [
        {
            "name": "1040 Individual Tax Client",
            "description": "Standard annual engagement for individual (Form 1040) tax clients including quarterly estimates, return filing, and year-end planning.",
            "entity_types": ["individual"],
            "tasks": [
                ("Document request sent to client", "annual_return", "annual", 1, 15, 0, "high"),
                ("Annual return prep window opens", "annual_return", "annual", 2, 1, 0, "medium"),
                ("Q1 estimated tax prep", "quarterly_estimate", "annual", 3, 25, 21, "high"),
                ("Q1 estimated payment due", "quarterly_estimate", "annual", 4, 15, 0, "high"),
                ("Annual return deadline / extension decision", "annual_return", "annual", 4, 15, 14, "high"),
                ("Q2 estimated tax prep", "quarterly_estimate", "annual", 5, 25, 21, "high"),
                ("Q2 estimated payment due", "quarterly_estimate", "annual", 6, 15, 0, "high"),
                ("Q3 estimated tax prep", "quarterly_estimate", "annual", 8, 25, 21, "high"),
                ("Q3 estimated payment due", "quarterly_estimate", "annual", 9, 15, 0, "high"),
                ("Year-end planning review", "planning", "annual", 10, 15, 21, "medium"),
                ("Extension deadline", "extension", "annual", 10, 15, 14, "high"),
                ("Q4 estimated tax prep", "quarterly_estimate", "annual", 12, 15, 21, "high"),
                ("Q4 estimated payment due", "quarterly_estimate", "annual", 1, 15, 0, "high"),
            ],
        },
        {
            "name": "1120-S S-Corporation",
            "description": "S-Corporation engagement including return filing, quarterly payroll, K-1 distribution, and year-end planning.",
            "entity_types": ["s_corp"],
            "tasks": [
                ("S-Corp return due (Form 1120-S)", "annual_return", "annual", 3, 15, 14, "high"),
                ("K-1 distribution to shareholders", "compliance", "annual", 3, 15, 7, "high"),
                ("Q1 payroll tax deposit", "compliance", "quarterly", 4, 30, 7, "medium"),
                ("Q2 payroll tax deposit", "compliance", "quarterly", 7, 31, 7, "medium"),
                ("Q3 payroll tax deposit", "compliance", "quarterly", 10, 31, 7, "medium"),
                ("Q4 payroll tax deposit", "compliance", "quarterly", 1, 31, 7, "medium"),
                ("Extension deadline (Form 1120-S)", "extension", "annual", 9, 15, 14, "high"),
                ("Year-end planning review", "planning", "annual", 10, 15, 21, "medium"),
                ("Reasonable compensation review", "review", "annual", 11, 15, 21, "medium"),
            ],
        },
        {
            "name": "1065 Partnership",
            "description": "Partnership/LLC engagement including return filing, K-1 prep, and capital account review.",
            "entity_types": ["partnership", "llc"],
            "tasks": [
                ("Partnership return due (Form 1065)", "annual_return", "annual", 3, 15, 14, "high"),
                ("K-1 prep and distribution", "compliance", "annual", 3, 15, 7, "high"),
                ("Extension deadline (Form 1065)", "extension", "annual", 9, 15, 14, "high"),
                ("Capital account review", "review", "annual", 10, 1, 21, "medium"),
                ("Year-end planning review", "planning", "annual", 11, 1, 21, "medium"),
                ("Partner allocation review", "review", "annual", 12, 1, 14, "medium"),
            ],
        },
        {
            "name": "1041 Trust/Estate",
            "description": "Trust and estate engagement including return filing, distribution planning, and RMD deadlines.",
            "entity_types": ["trust", "estate"],
            "tasks": [
                ("Trust/estate return due (Form 1041)", "annual_return", "annual", 4, 15, 14, "high"),
                ("Extension deadline (Form 1041)", "extension", "annual", 10, 15, 14, "high"),
                ("Distribution planning review", "planning", "annual", 9, 1, 21, "medium"),
                ("RMD calculation and distribution", "compliance", "annual", 11, 1, 30, "high"),
                ("Year-end distribution decisions", "planning", "annual", 12, 1, 21, "medium"),
            ],
        },
        {
            "name": "Quarterly Advisory Review",
            "description": "General quarterly advisory check-ins and annual strategy review applicable to all client types.",
            "entity_types": None,
            "tasks": [
                ("Q1 advisory check-in", "review", "quarterly", 3, 15, 14, "medium"),
                ("Q2 advisory check-in", "review", "quarterly", 6, 15, 14, "medium"),
                ("Q3 advisory check-in", "review", "quarterly", 9, 15, 14, "medium"),
                ("Q4 advisory check-in", "review", "quarterly", 12, 15, 14, "medium"),
                ("Annual strategy matrix review", "planning", "annual", 11, 1, 21, "medium"),
            ],
        },
    ]

    for tpl in TEMPLATES:
        tpl_id = uuid.uuid4()
        conn.execute(
            templates_table.insert().values(
                id=tpl_id,
                name=tpl["name"],
                description=tpl["description"],
                entity_types=json.dumps(tpl["entity_types"]) if tpl["entity_types"] else None,
                is_system=True,
            )
        )
        for order, task in enumerate(tpl["tasks"], 1):
            task_name, category, recurrence, month, day, lead_days, priority = task
            conn.execute(
                tasks_table.insert().values(
                    id=uuid.uuid4(),
                    template_id=tpl_id,
                    task_name=task_name,
                    category=category,
                    recurrence=recurrence,
                    month=month,
                    day=day,
                    lead_days=lead_days,
                    priority=priority,
                    display_order=order,
                )
            )

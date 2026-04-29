"""add strategy implementation tasks

Revision ID: 53efd7171075
Revises: 4c43b5b65697
Create Date: 2026-04-29 00:51:00.000000+00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic
revision: str = '53efd7171075'
down_revision: Union[str, None] = '4c43b5b65697'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create strategy_implementation_tasks table
    op.create_table(
        'strategy_implementation_tasks',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('strategy_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('tax_strategies.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('task_name', sa.String(300), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('default_owner_role', sa.String(20), nullable=False),
        sa.Column('default_owner_external_label', sa.String(200), nullable=True),
        sa.Column('default_lead_days', sa.Integer, nullable=False,
                  server_default='0'),
        sa.Column('required_documents', postgresql.JSONB, nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column('display_order', sa.Integer, nullable=False,
                  server_default='0'),
        sa.Column('is_active', sa.Boolean, nullable=False,
                  server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.CheckConstraint(
            "default_owner_role IN ('cpa', 'client', 'third_party')",
            name='ck_sit_default_owner_role',
        ),
    )
    op.create_index('ix_sit_strategy_id', 'strategy_implementation_tasks',
                    ['strategy_id'])

    # 2. Add 4 columns to action_items
    op.add_column('action_items', sa.Column(
        'strategy_implementation_task_id', postgresql.UUID(as_uuid=True),
        sa.ForeignKey('strategy_implementation_tasks.id'), nullable=True))
    op.add_column('action_items', sa.Column(
        'client_strategy_status_id', postgresql.UUID(as_uuid=True),
        sa.ForeignKey('client_strategy_status.id'), nullable=True))
    op.add_column('action_items', sa.Column(
        'owner_role', sa.String(20), nullable=False, server_default='cpa'))
    op.add_column('action_items', sa.Column(
        'owner_external_label', sa.String(200), nullable=True))

    op.create_index('ix_action_items_strategy_implementation_task_id',
                    'action_items', ['strategy_implementation_task_id'])
    op.create_index('ix_action_items_client_strategy_status_id',
                    'action_items', ['client_strategy_status_id'])
    op.create_check_constraint(
        'ck_action_items_owner_role', 'action_items',
        "owner_role IN ('cpa', 'client', 'third_party')")

    # 3. Seed 21 rows (7 tasks x 3 strategies)
    conn = op.get_bind()

    augusta_id = conn.execute(
        sa.text("SELECT id FROM tax_strategies WHERE name = :name"),
        {"name": "Augusta Rule (Section 280A)"},
    ).scalar_one()

    cost_seg_id = conn.execute(
        sa.text("SELECT id FROM tax_strategies WHERE name = :name"),
        {"name": "Cost Segregation Study"},
    ).scalar_one()

    reasonable_comp_id = conn.execute(
        sa.text("SELECT id FROM tax_strategies WHERE name = :name"),
        {"name": "Reasonable Compensation Analysis"},
    ).scalar_one()

    sit = sa.table(
        'strategy_implementation_tasks',
        sa.column('strategy_id', postgresql.UUID),
        sa.column('task_name', sa.String),
        sa.column('description', sa.Text),
        sa.column('default_owner_role', sa.String),
        sa.column('default_owner_external_label', sa.String),
        sa.column('default_lead_days', sa.Integer),
        sa.column('required_documents', postgresql.JSONB),
        sa.column('display_order', sa.Integer),
        sa.column('is_active', sa.Boolean),
    )

    # Augusta Rule (Section 280A)
    augusta_tasks = [
        {
            "strategy_id": augusta_id,
            "task_name": "Verify primary residence eligibility under §280A",
            "description": None,
            "default_owner_role": "cpa",
            "default_owner_external_label": None,
            "default_lead_days": 0,
            "required_documents": [{"document_type": "legal", "document_subtype": "deed", "label": "Property deed or title"}],
            "display_order": 1,
            "is_active": True,
        },
        {
            "strategy_id": augusta_id,
            "task_name": "Establish documented business purpose for rental days",
            "description": None,
            "default_owner_role": "cpa",
            "default_owner_external_label": None,
            "default_lead_days": 7,
            "required_documents": [{"document_type": "legal", "document_subtype": "corporate_minutes", "label": "Corporate minutes template"}],
            "display_order": 2,
            "is_active": True,
        },
        {
            "strategy_id": augusta_id,
            "task_name": "Determine fair market rental rate from 3 comparable quotes",
            "description": None,
            "default_owner_role": "cpa",
            "default_owner_external_label": None,
            "default_lead_days": 14,
            "required_documents": [{"document_type": "supporting", "document_subtype": "rental_comp", "label": "3 comparable rental quotes"}],
            "display_order": 3,
            "is_active": True,
        },
        {
            "strategy_id": augusta_id,
            "task_name": "Draft and execute rental agreement between business and owner",
            "description": None,
            "default_owner_role": "cpa",
            "default_owner_external_label": None,
            "default_lead_days": 21,
            "required_documents": [{"document_type": "legal", "document_subtype": "rental_agreement", "label": "Executed rental agreement"}],
            "display_order": 4,
            "is_active": True,
        },
        {
            "strategy_id": augusta_id,
            "task_name": "Document business meetings held at residence (\u226414 days/year)",
            "description": None,
            "default_owner_role": "client",
            "default_owner_external_label": None,
            "default_lead_days": 30,
            "required_documents": [{"document_type": "supporting", "document_subtype": "meeting_minutes", "label": "Meeting agendas + minutes per session"}],
            "display_order": 5,
            "is_active": True,
        },
        {
            "strategy_id": augusta_id,
            "task_name": "Issue 1099-MISC from business entity to owner if required",
            "description": None,
            "default_owner_role": "cpa",
            "default_owner_external_label": None,
            "default_lead_days": 365,
            "required_documents": [{"document_type": "tax_form", "document_subtype": "1099_misc", "label": "1099-MISC issued to owner"}],
            "display_order": 6,
            "is_active": True,
        },
        {
            "strategy_id": augusta_id,
            "task_name": "Apply §280A exclusion on personal Form 1040 at filing",
            "description": None,
            "default_owner_role": "cpa",
            "default_owner_external_label": None,
            "default_lead_days": 365,
            "required_documents": [{"document_type": "tax_form", "document_subtype": "1040", "label": "Filed Form 1040"}],
            "display_order": 7,
            "is_active": True,
        },
    ]

    # Cost Segregation Study
    cost_seg_tasks = [
        {
            "strategy_id": cost_seg_id,
            "task_name": "Identify qualifying property and confirm acquisition basis",
            "description": None,
            "default_owner_role": "cpa",
            "default_owner_external_label": None,
            "default_lead_days": 0,
            "required_documents": [
                {"document_type": "legal", "document_subtype": "closing_statement", "label": "Property closing statement"},
                {"document_type": "supporting", "document_subtype": "depreciation_schedule", "label": "Current depreciation schedule"},
            ],
            "display_order": 1,
            "is_active": True,
        },
        {
            "strategy_id": cost_seg_id,
            "task_name": "Engage cost segregation engineering firm",
            "description": None,
            "default_owner_role": "cpa",
            "default_owner_external_label": None,
            "default_lead_days": 14,
            "required_documents": [{"document_type": "legal", "document_subtype": "engagement_letter", "label": "Cost-seg vendor proposal + engagement letter"}],
            "display_order": 2,
            "is_active": True,
        },
        {
            "strategy_id": cost_seg_id,
            "task_name": "Schedule property walkthrough with cost-seg engineer",
            "description": None,
            "default_owner_role": "client",
            "default_owner_external_label": None,
            "default_lead_days": 30,
            "required_documents": [],
            "display_order": 3,
            "is_active": True,
        },
        {
            "strategy_id": cost_seg_id,
            "task_name": "Receive cost segregation study report",
            "description": None,
            "default_owner_role": "third_party",
            "default_owner_external_label": "Cost Seg Engineering Firm",
            "default_lead_days": 90,
            "required_documents": [{"document_type": "supporting", "document_subtype": "cost_seg_study", "label": "Cost segregation study PDF"}],
            "display_order": 4,
            "is_active": True,
        },
        {
            "strategy_id": cost_seg_id,
            "task_name": "Update fixed asset schedule and depreciation method",
            "description": None,
            "default_owner_role": "cpa",
            "default_owner_external_label": None,
            "default_lead_days": 120,
            "required_documents": [{"document_type": "supporting", "document_subtype": "depreciation_schedule", "label": "Revised depreciation schedule"}],
            "display_order": 5,
            "is_active": True,
        },
        {
            "strategy_id": cost_seg_id,
            "task_name": "File Form 3115 if change in accounting method required",
            "description": None,
            "default_owner_role": "cpa",
            "default_owner_external_label": None,
            "default_lead_days": 150,
            "required_documents": [{"document_type": "tax_form", "document_subtype": "3115", "label": "Form 3115"}],
            "display_order": 6,
            "is_active": True,
        },
        {
            "strategy_id": cost_seg_id,
            "task_name": "Apply accelerated depreciation on tax return at filing",
            "description": None,
            "default_owner_role": "cpa",
            "default_owner_external_label": None,
            "default_lead_days": 365,
            "required_documents": [{"document_type": "tax_form", "document_subtype": "1040", "label": "Filed return with revised depreciation"}],
            "display_order": 7,
            "is_active": True,
        },
    ]

    # Reasonable Compensation Analysis
    reasonable_comp_tasks = [
        {
            "strategy_id": reasonable_comp_id,
            "task_name": "Confirm S-Corp election filed (Form 2553) and accepted",
            "description": None,
            "default_owner_role": "cpa",
            "default_owner_external_label": None,
            "default_lead_days": 0,
            "required_documents": [{"document_type": "correspondence", "document_subtype": "irs_notice", "label": "Form 2553 acknowledgment / IRS CP261"}],
            "display_order": 1,
            "is_active": True,
        },
        {
            "strategy_id": reasonable_comp_id,
            "task_name": "Conduct reasonable compensation study",
            "description": None,
            "default_owner_role": "cpa",
            "default_owner_external_label": None,
            "default_lead_days": 14,
            "required_documents": [{"document_type": "supporting", "document_subtype": "comp_study", "label": "Industry compensation data + prior officer comp"}],
            "display_order": 2,
            "is_active": True,
        },
        {
            "strategy_id": reasonable_comp_id,
            "task_name": "Establish target salary range and document methodology",
            "description": None,
            "default_owner_role": "cpa",
            "default_owner_external_label": None,
            "default_lead_days": 21,
            "required_documents": [{"document_type": "supporting", "document_subtype": "comp_study", "label": "Comp study output with target range"}],
            "display_order": 3,
            "is_active": True,
        },
        {
            "strategy_id": reasonable_comp_id,
            "task_name": "Set up payroll processing for officer W-2 wages",
            "description": None,
            "default_owner_role": "client",
            "default_owner_external_label": None,
            "default_lead_days": 30,
            "required_documents": [{"document_type": "correspondence", "document_subtype": "vendor_setup", "label": "Payroll provider setup confirmation"}],
            "display_order": 4,
            "is_active": True,
        },
        {
            "strategy_id": reasonable_comp_id,
            "task_name": "Document board resolution / officer compensation decision",
            "description": None,
            "default_owner_role": "cpa",
            "default_owner_external_label": None,
            "default_lead_days": 30,
            "required_documents": [{"document_type": "legal", "document_subtype": "corporate_minutes", "label": "Board resolution / officer comp minutes"}],
            "display_order": 5,
            "is_active": True,
        },
        {
            "strategy_id": reasonable_comp_id,
            "task_name": "Establish quarterly Form 941 filing schedule",
            "description": None,
            "default_owner_role": "cpa",
            "default_owner_external_label": None,
            "default_lead_days": 60,
            "required_documents": [{"document_type": "tax_form", "document_subtype": "941", "label": "Quarterly 941 calendar"}],
            "display_order": 6,
            "is_active": True,
        },
        {
            "strategy_id": reasonable_comp_id,
            "task_name": "Issue year-end W-2 to officer",
            "description": None,
            "default_owner_role": "cpa",
            "default_owner_external_label": None,
            "default_lead_days": 365,
            "required_documents": [{"document_type": "tax_form", "document_subtype": "w2", "label": "Year-end W-2 issued to officer"}],
            "display_order": 7,
            "is_active": True,
        },
    ]

    op.bulk_insert(sit, augusta_tasks + cost_seg_tasks + reasonable_comp_tasks)


def downgrade() -> None:
    # 1. Drop indexes on action_items
    op.drop_constraint('ck_action_items_owner_role', 'action_items',
                       type_='check')
    op.drop_index('ix_action_items_client_strategy_status_id',
                  table_name='action_items')
    op.drop_index('ix_action_items_strategy_implementation_task_id',
                  table_name='action_items')

    # 2. Drop 4 columns from action_items
    op.drop_column('action_items', 'owner_external_label')
    op.drop_column('action_items', 'owner_role')
    op.drop_column('action_items', 'client_strategy_status_id')
    op.drop_column('action_items', 'strategy_implementation_task_id')

    # 3. Drop strategy_implementation_tasks
    op.drop_index('ix_sit_strategy_id',
                  table_name='strategy_implementation_tasks')
    op.drop_table('strategy_implementation_tasks')

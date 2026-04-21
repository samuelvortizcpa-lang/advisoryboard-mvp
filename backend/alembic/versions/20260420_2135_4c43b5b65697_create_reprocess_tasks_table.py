"""create reprocess_tasks table

Revision ID: 4c43b5b65697
Revises: 14ae485b1dec
Create Date: 2026-04-20 21:35:48.783777+00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic
revision: str = '4c43b5b65697'
down_revision: Union[str, None] = '14ae485b1dec'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'reprocess_tasks',
        sa.Column(
            'task_id',
            postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column('total', sa.Integer, nullable=False),
        sa.Column(
            'completed',
            sa.Integer,
            nullable=False,
            server_default='0',
        ),
        sa.Column(
            'errors',
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            'status',
            sa.Text,
            nullable=False,
            server_default='running',
        ),
        sa.Column(
            'started_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column('task_metadata', postgresql.JSONB, nullable=True),
    )
    op.create_index(
        'idx_reprocess_tasks_status_started',
        'reprocess_tasks',
        ['status', 'started_at'],
    )


def downgrade() -> None:
    op.drop_index('idx_reprocess_tasks_status_started')
    op.drop_table('reprocess_tasks')

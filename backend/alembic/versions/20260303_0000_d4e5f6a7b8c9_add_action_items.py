"""add_action_items

Revision ID: d4e5f6a7b8c9
Revises: c788a4bcb26a
Create Date: 2026-03-03 00:00:00.000000+00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op


# revision identifiers, used by Alembic
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c788a4bcb26a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'action_items',
        sa.Column(
            'id',
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text('gen_random_uuid()'),
        ),
        sa.Column(
            'document_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('documents.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'client_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('clients.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column(
            'status',
            sa.String(20),
            nullable=False,
            server_default='pending',
        ),
        sa.Column('priority', sa.String(10), nullable=True),
        sa.Column('due_date', sa.Date(), nullable=True),
        sa.Column(
            'extracted_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
    )
    op.create_index('ix_action_items_document_id', 'action_items', ['document_id'])
    op.create_index('ix_action_items_client_id', 'action_items', ['client_id'])


def downgrade() -> None:
    op.drop_index('ix_action_items_client_id', table_name='action_items')
    op.drop_index('ix_action_items_document_id', table_name='action_items')
    op.drop_table('action_items')

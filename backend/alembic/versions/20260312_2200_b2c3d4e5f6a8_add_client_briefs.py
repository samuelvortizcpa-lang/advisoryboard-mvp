"""add_client_briefs

Revision ID: b2c3d4e5f6a8
Revises: a1b2c3d4e5f7
Create Date: 2026-03-12 22:00:00.000000+00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID


# revision identifiers, used by Alembic
revision: str = 'b2c3d4e5f6a8'
down_revision: Union[str, None] = 'a1b2c3d4e5f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'client_briefs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('client_id', UUID(as_uuid=True), sa.ForeignKey('clients.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('user_id', sa.String(255), nullable=False),
        sa.Column('content', sa.Text, nullable=False),
        sa.Column('generated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('document_count', sa.Integer, nullable=True),
        sa.Column('action_item_count', sa.Integer, nullable=True),
        sa.Column('metadata_', JSONB, nullable=True),
    )
    op.create_index('ix_client_briefs_generated_at', 'client_briefs', ['generated_at'])


def downgrade() -> None:
    op.drop_index('ix_client_briefs_generated_at', table_name='client_briefs')
    op.drop_table('client_briefs')

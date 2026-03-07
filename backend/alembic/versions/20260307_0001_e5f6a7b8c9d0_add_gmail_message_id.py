"""add_gmail_message_id

Revision ID: e5f6a7b8c9d0
Revises: c3d4e5f6a7b8
Create Date: 2026-03-07 00:01:00.000000+00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'documents',
        sa.Column('gmail_message_id', sa.String(255), nullable=True),
    )
    op.create_index(
        'ix_documents_gmail_message_id', 'documents', ['gmail_message_id'],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index('ix_documents_gmail_message_id', table_name='documents')
    op.drop_column('documents', 'gmail_message_id')

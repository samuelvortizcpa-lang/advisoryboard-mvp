"""alter action_items source to varchar 30

Revision ID: b59e25367fcc
Revises: 53efd7171075
Create Date: 2026-04-29 17:25:22.699948+00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic
revision: str = 'b59e25367fcc'
down_revision: Union[str, None] = '53efd7171075'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        'action_items',
        'source',
        existing_type=sa.String(20),
        type_=sa.String(30),
        existing_nullable=False,
        existing_server_default=sa.text("'ai_extracted'"),
    )


def downgrade() -> None:
    op.alter_column(
        'action_items',
        'source',
        existing_type=sa.String(30),
        type_=sa.String(20),
        existing_nullable=False,
        existing_server_default=sa.text("'ai_extracted'"),
    )

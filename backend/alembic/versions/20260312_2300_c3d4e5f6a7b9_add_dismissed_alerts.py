"""add_dismissed_alerts

Revision ID: c3d4e5f6a7b9
Revises: b2c3d4e5f6a8
Create Date: 2026-03-12 23:00:00.000000+00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic
revision: str = 'c3d4e5f6a7b9'
down_revision: Union[str, None] = 'b2c3d4e5f6a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'dismissed_alerts',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', sa.String(255), nullable=False),
        sa.Column('alert_type', sa.String(50), nullable=False),
        sa.Column('related_id', UUID(as_uuid=True), nullable=True),
        sa.Column('dismissed_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_dismissed_alerts_user_id', 'dismissed_alerts', ['user_id'])
    op.create_unique_constraint(
        'uq_dismissed_alerts_user_type_related',
        'dismissed_alerts',
        ['user_id', 'alert_type', 'related_id'],
    )


def downgrade() -> None:
    op.drop_constraint('uq_dismissed_alerts_user_type_related', 'dismissed_alerts')
    op.drop_index('ix_dismissed_alerts_user_id', table_name='dismissed_alerts')
    op.drop_table('dismissed_alerts')

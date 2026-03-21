"""Add zoom_meeting_rules table

Revision ID: z0o0m1r2u3l4
Revises: h7i8j9k0l1m2
Create Date: 2026-03-20 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision = "z0o0m1r2u3l4"
down_revision = "h7i8j9k0l1m2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "zoom_meeting_rules",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.String(255), nullable=False, index=True),
        sa.Column("match_field", sa.String(50), nullable=False),
        sa.Column("match_value", sa.String(500), nullable=False),
        sa.Column(
            "client_id",
            UUID(as_uuid=True),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "is_active",
            sa.Boolean,
            server_default="true",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "user_id", "match_value", "match_field",
            name="uq_zoom_meeting_rules_user_value_field",
        ),
    )


def downgrade() -> None:
    op.drop_table("zoom_meeting_rules")

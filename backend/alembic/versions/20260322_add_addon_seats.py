"""add addon_seats column to user_subscriptions

Revision ID: b4c8d2e6f7a3
Revises: a3b7c9d1e5f2
Create Date: 2026-03-22

Tracks the number of additional seats purchased beyond the tier's
included base_seats.  Used by the hybrid Firm pricing model where
$349/mo includes 3 seats and each add-on seat is $79/mo.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b4c8d2e6f7a3"
down_revision: Union[str, None] = "a3b7c9d1e5f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user_subscriptions",
        sa.Column("addon_seats", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("user_subscriptions", "addon_seats")

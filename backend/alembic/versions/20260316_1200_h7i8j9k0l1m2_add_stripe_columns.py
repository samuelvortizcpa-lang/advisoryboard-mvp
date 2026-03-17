"""Add Stripe columns to user_subscriptions

Revision ID: h7i8j9k0l1m2
Revises: g6h7i8j9k0l1
Create Date: 2026-03-16 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "h7i8j9k0l1m2"
down_revision = "g6h7i8j9k0l1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user_subscriptions", sa.Column("stripe_customer_id", sa.String(255), nullable=True))
    op.add_column("user_subscriptions", sa.Column("stripe_subscription_id", sa.String(255), nullable=True))
    op.add_column("user_subscriptions", sa.Column("stripe_status", sa.String(50), nullable=True, server_default="none"))


def downgrade() -> None:
    op.drop_column("user_subscriptions", "stripe_status")
    op.drop_column("user_subscriptions", "stripe_subscription_id")
    op.drop_column("user_subscriptions", "stripe_customer_id")

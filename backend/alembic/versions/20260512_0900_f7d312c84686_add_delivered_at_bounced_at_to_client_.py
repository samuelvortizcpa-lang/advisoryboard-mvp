"""add delivered_at bounced_at to client_communications

Revision ID: f7d312c84686
Revises: f9b8137f2294
Create Date: 2026-05-12 09:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "f7d312c84686"
down_revision = "f9b8137f2294"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "client_communications",
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "client_communications",
        sa.Column("bounced_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("client_communications", "bounced_at")
    op.drop_column("client_communications", "delivered_at")

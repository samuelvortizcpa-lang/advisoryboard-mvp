"""Add client_assignments table.

Revision ID: c5d9e3f7a8b4
Revises: b4c8d2e6f7a3
Create Date: 2026-03-22
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "c5d9e3f7a8b4"
down_revision: Union[str, None] = "b4c8d2e6f7a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "client_assignments",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("client_id", UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("org_id", UUID(as_uuid=True), nullable=False),
        sa.Column("assigned_by", sa.String(255), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("role", sa.String(50), server_default="assigned", nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("client_id", "user_id", "org_id", name="uq_client_user_org"),
    )
    op.create_index("ix_client_assignments_org_id", "client_assignments", ["org_id"])
    op.create_index("ix_client_assignments_user_id", "client_assignments", ["user_id"])
    op.create_index("ix_client_assignments_client_id", "client_assignments", ["client_id"])


def downgrade() -> None:
    op.drop_index("ix_client_assignments_client_id", table_name="client_assignments")
    op.drop_index("ix_client_assignments_user_id", table_name="client_assignments")
    op.drop_index("ix_client_assignments_org_id", table_name="client_assignments")
    op.drop_table("client_assignments")

"""Add indexes on organization_members and client_access lookup columns.

These tables are queried on every authenticated request. Missing indexes
cause full table scans that degrade with user growth.

Revision ID: b2c3d4e5f6a9
Revises: a1b2c3d4e5f8
Create Date: 2026-03-28
"""

from typing import Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a9"
down_revision: Union[str, None] = "a1b2c3d4e5f8"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.create_index("ix_organization_members_user_id", "organization_members", ["user_id"])
    op.create_index("ix_organization_members_org_id", "organization_members", ["org_id"])
    op.create_index("ix_client_access_client_id", "client_access", ["client_id"])
    op.create_index("ix_client_access_user_id", "client_access", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_client_access_user_id", table_name="client_access")
    op.drop_index("ix_client_access_client_id", table_name="client_access")
    op.drop_index("ix_organization_members_org_id", table_name="organization_members")
    op.drop_index("ix_organization_members_user_id", table_name="organization_members")

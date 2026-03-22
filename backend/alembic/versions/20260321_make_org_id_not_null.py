"""make clients.org_id NOT NULL after backfill

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-03-21

Run the backfill script FIRST:
    DATABASE_URL="..." python scripts/migrate_to_orgs.py

Only apply this migration after verifying all clients have org_id set.
owner_id is intentionally kept for one more release as a safety net.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Safety check: abort if any clients still have NULL org_id
    conn = op.get_bind()
    result = conn.execute(sa.text("SELECT count(*) FROM clients WHERE org_id IS NULL"))
    null_count = result.scalar()
    if null_count > 0:
        raise RuntimeError(
            f"Cannot make org_id NOT NULL: {null_count} clients still have "
            f"org_id IS NULL. Run scripts/migrate_to_orgs.py first."
        )

    op.alter_column("clients", "org_id", nullable=False)

    # NOTE: owner_id is intentionally NOT dropped. It will be removed in a
    # future migration after one release cycle as a safety net.


def downgrade() -> None:
    op.alter_column("clients", "org_id", nullable=True)

"""make clients.org_id NOT NULL with inline backfill

Revision ID: a3b7c9d1e5f2
Revises: 51092342ecf4
Create Date: 2026-03-22

Performs the org backfill inline so that `alembic upgrade head` works in a
single pass on a fresh deploy (Railway).  No separate script needed.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a3b7c9d1e5f2"
down_revision: Union[str, None] = "51092342ecf4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # ------------------------------------------------------------------
    # 1. Create a personal org for every user who doesn't have one yet
    # ------------------------------------------------------------------
    conn.execute(sa.text("""
        INSERT INTO organizations (name, slug, owner_user_id, org_type, max_members, settings)
        SELECT
            COALESCE(u.email, 'Personal'),
            'personal-' || LEFT(u.clerk_id, 8),
            u.clerk_id,
            'personal',
            1,
            '{}'::jsonb
        FROM users u
        WHERE NOT EXISTS (
            SELECT 1 FROM organizations o
            WHERE o.owner_user_id = u.clerk_id
              AND o.org_type = 'personal'
        )
    """))

    # ------------------------------------------------------------------
    # 2. Add organization_members rows for users missing them
    # ------------------------------------------------------------------
    conn.execute(sa.text("""
        INSERT INTO organization_members (org_id, user_id, role)
        SELECT o.id, o.owner_user_id, 'admin'
        FROM organizations o
        WHERE o.org_type = 'personal'
          AND NOT EXISTS (
              SELECT 1 FROM organization_members om
              WHERE om.org_id = o.id
                AND om.user_id = o.owner_user_id
          )
    """))

    # ------------------------------------------------------------------
    # 3. Backfill clients.org_id and clients.created_by
    # ------------------------------------------------------------------
    conn.execute(sa.text("""
        UPDATE clients
        SET org_id = orgs.id
        FROM users u
        JOIN organizations orgs
            ON orgs.owner_user_id = u.clerk_id
            AND orgs.org_type = 'personal'
        WHERE clients.owner_id = u.id
          AND clients.org_id IS NULL
    """))

    conn.execute(sa.text("""
        UPDATE clients
        SET created_by = u.clerk_id
        FROM users u
        WHERE clients.owner_id = u.id
          AND clients.created_by IS NULL
    """))

    # ------------------------------------------------------------------
    # 4. Backfill user_subscriptions.org_id
    # ------------------------------------------------------------------
    conn.execute(sa.text("""
        UPDATE user_subscriptions us
        SET org_id = orgs.id
        FROM organizations orgs
        WHERE orgs.owner_user_id = us.user_id
          AND orgs.org_type = 'personal'
          AND us.org_id IS NULL
    """))

    # ------------------------------------------------------------------
    # 5. Backfill token_usage.org_id
    # ------------------------------------------------------------------
    conn.execute(sa.text("""
        UPDATE token_usage tu
        SET org_id = orgs.id
        FROM organizations orgs
        WHERE orgs.owner_user_id = tu.user_id
          AND orgs.org_type = 'personal'
          AND tu.org_id IS NULL
    """))

    # ------------------------------------------------------------------
    # 6. Backfill integration_connections.org_id
    # ------------------------------------------------------------------
    conn.execute(sa.text("""
        UPDATE integration_connections ic
        SET org_id = orgs.id
        FROM organizations orgs
        WHERE orgs.owner_user_id = ic.user_id
          AND orgs.org_type = 'personal'
          AND ic.org_id IS NULL
    """))

    # ------------------------------------------------------------------
    # 7. Safety check — abort if any clients still have NULL org_id
    # ------------------------------------------------------------------
    result = conn.execute(sa.text("SELECT count(*) FROM clients WHERE org_id IS NULL"))
    null_count = result.scalar()
    if null_count > 0:
        raise RuntimeError(
            f"Backfill incomplete: {null_count} clients still have org_id IS NULL. "
            f"These clients may have owner_id values with no matching user row."
        )

    # ------------------------------------------------------------------
    # 8. Now safe to enforce NOT NULL
    # ------------------------------------------------------------------
    op.alter_column("clients", "org_id", nullable=False)


def downgrade() -> None:
    op.alter_column("clients", "org_id", nullable=True)

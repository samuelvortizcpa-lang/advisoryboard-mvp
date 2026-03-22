"""add organization tables and columns for multi-tenant support

Revision ID: 51092342ecf4
Revises: d348e822f38f
Create Date: 2026-03-21

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "51092342ecf4"
down_revision: Union[str, None] = "d348e822f38f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Create organizations table
    # ------------------------------------------------------------------
    op.create_table(
        "organizations",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), unique=True, nullable=False),
        sa.Column("clerk_org_id", sa.String(255), unique=True, nullable=True),
        sa.Column("owner_user_id", sa.String(255), nullable=False),
        sa.Column(
            "org_type",
            sa.String(50),
            nullable=False,
            server_default="personal",
        ),
        sa.Column("max_members", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("settings", JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # ------------------------------------------------------------------
    # 2. Create organization_members table
    # ------------------------------------------------------------------
    op.create_table(
        "organization_members",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column(
            "role",
            sa.String(50),
            nullable=False,
            server_default="member",
        ),
        sa.Column("invited_by", sa.String(255), nullable=True),
        sa.Column("invited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "joined_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("org_id", "user_id", name="uq_org_members_org_user"),
    )

    # ------------------------------------------------------------------
    # 3. Create client_access table
    # ------------------------------------------------------------------
    op.create_table(
        "client_access",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "client_id",
            UUID(as_uuid=True),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column(
            "access_level",
            sa.String(50),
            nullable=False,
            server_default="full",
        ),
        sa.Column("assigned_by", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "client_id", "user_id", name="uq_client_access_client_user"
        ),
    )

    # ------------------------------------------------------------------
    # 4. Add org_id and created_by to clients
    # ------------------------------------------------------------------
    op.add_column(
        "clients",
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.add_column(
        "clients",
        sa.Column("created_by", sa.String(255), nullable=True),
    )

    # ------------------------------------------------------------------
    # 5. Add org_id to user_subscriptions
    # ------------------------------------------------------------------
    op.add_column(
        "user_subscriptions",
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    # ------------------------------------------------------------------
    # 6. Add org_id to token_usage
    # ------------------------------------------------------------------
    op.add_column(
        "token_usage",
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    # ------------------------------------------------------------------
    # 7. Add org_id to integration_connections
    # ------------------------------------------------------------------
    op.add_column(
        "integration_connections",
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )

    # ------------------------------------------------------------------
    # 8. Indexes for query performance
    # ------------------------------------------------------------------
    op.create_index(
        "idx_org_members_user_id",
        "organization_members",
        ["user_id"],
    )
    op.create_index(
        "idx_org_members_org_id",
        "organization_members",
        ["org_id"],
    )
    op.create_index(
        "idx_client_access_user_id",
        "client_access",
        ["user_id"],
    )
    op.create_index(
        "idx_client_access_client_id",
        "client_access",
        ["client_id"],
    )
    op.create_index(
        "idx_clients_org_id",
        "clients",
        ["org_id"],
    )
    op.create_index(
        "idx_token_usage_org_id",
        "token_usage",
        ["org_id"],
    )


def downgrade() -> None:
    # Drop indexes
    op.drop_index("idx_token_usage_org_id", table_name="token_usage")
    op.drop_index("idx_clients_org_id", table_name="clients")
    op.drop_index("idx_client_access_client_id", table_name="client_access")
    op.drop_index("idx_client_access_user_id", table_name="client_access")
    op.drop_index("idx_org_members_org_id", table_name="organization_members")
    op.drop_index("idx_org_members_user_id", table_name="organization_members")

    # Drop added columns (reverse order)
    op.drop_column("integration_connections", "org_id")
    op.drop_column("token_usage", "org_id")
    op.drop_column("user_subscriptions", "org_id")
    op.drop_column("clients", "created_by")
    op.drop_column("clients", "org_id")

    # Drop new tables (reverse order)
    op.drop_table("client_access")
    op.drop_table("organization_members")
    op.drop_table("organizations")

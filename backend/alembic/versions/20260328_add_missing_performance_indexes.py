"""add missing performance indexes

Revision ID: a7f8b9c0d1e2
Revises: b2c3d4e5f6a9
Create Date: 2026-03-28

Adds indexes on columns used in hot query paths (alerts, RAG, consent lookups)
that were missing despite high query frequency. See AUDIT-2026-03-28.md H5/H6.
"""

from alembic import op

revision = "a7f8b9c0d1e2"
down_revision = "b2c3d4e5f6a9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- clients: composite for org-scoped owner queries --
    op.create_index(
        "ix_clients_owner_id_org_id",
        "clients",
        ["owner_id", "org_id"],
    )

    # -- documents: unprocessed document alerts --
    op.create_index(
        "ix_documents_processed",
        "documents",
        ["processed"],
    )

    # -- action_items: alert queries filter by client + status --
    op.create_index(
        "ix_action_items_client_id_status",
        "action_items",
        ["client_id", "status"],
    )

    # -- action_items: overdue/upcoming deadline partial index --
    op.create_index(
        "ix_action_items_due_date_pending",
        "action_items",
        ["due_date"],
        postgresql_where="status = 'pending' AND due_date IS NOT NULL",
    )

    # -- chat_messages: user activity queries --
    op.create_index(
        "ix_chat_messages_user_id",
        "chat_messages",
        ["user_id"],
    )

    # -- client_consents: expiring consent alert queries --
    op.create_index(
        "ix_client_consents_status_expiration",
        "client_consents",
        ["status", "expiration_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_client_consents_status_expiration", table_name="client_consents")
    op.drop_index("ix_chat_messages_user_id", table_name="chat_messages")
    op.drop_index("ix_action_items_due_date_pending", table_name="action_items")
    op.drop_index("ix_action_items_client_id_status", table_name="action_items")
    op.drop_index("ix_documents_processed", table_name="documents")
    op.drop_index("ix_clients_owner_id_org_id", table_name="clients")

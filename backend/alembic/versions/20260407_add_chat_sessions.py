"""Add chat_sessions table, session_id/pair columns on chat_messages, backfill sessions.

Revision ID: j0k1l2m3n4o5
Revises: i9j0k1l2m3n4
Create Date: 2026-04-07
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "j0k1l2m3n4o5"
down_revision = "i9j0k1l2m3n4"
branch_labels = None
depends_on = None

# 30-minute gap threshold for session boundaries (in seconds)
SESSION_GAP_SECONDS = 30 * 60


def upgrade() -> None:
    # 1. Create chat_sessions table (vector column added via raw SQL below)
    op.create_table(
        "chat_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("client_id", UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(200), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("message_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("key_topics", JSONB(), nullable=True),
        sa.Column("key_decisions", JSONB(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Add vector column via raw SQL (pgvector type not available in sa.Column)
    op.execute("ALTER TABLE chat_sessions ADD COLUMN summary_embedding vector(1536)")

    # 2. Add columns to chat_messages
    op.add_column(
        "chat_messages",
        sa.Column("session_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_chat_messages_session_id",
        "chat_messages",
        "chat_sessions",
        ["session_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.execute("ALTER TABLE chat_messages ADD COLUMN pair_embedding vector(1536)")
    op.add_column(
        "chat_messages",
        sa.Column("pair_index", sa.Integer(), nullable=True),
    )

    # 3. Create indexes
    op.create_index(
        "ix_chat_sessions_client_user_active",
        "chat_sessions",
        ["client_id", "user_id", "is_active"],
    )
    op.execute(
        "CREATE INDEX ix_chat_sessions_summary_embedding "
        "ON chat_sessions USING ivfflat (summary_embedding vector_cosine_ops) WITH (lists = 100)"
    )
    op.execute(
        "CREATE INDEX ix_chat_messages_pair_embedding "
        "ON chat_messages USING ivfflat (pair_embedding vector_cosine_ops) WITH (lists = 100)"
    )
    op.create_index("ix_chat_messages_session_id", "chat_messages", ["session_id"])

    # 4. Backfill: group existing messages into sessions by 30-min gaps
    conn = op.get_bind()

    # Fetch all messages ordered by client_id, user_id, created_at
    rows = conn.execute(
        sa.text(
            "SELECT id, client_id, user_id, role, content, created_at "
            "FROM chat_messages "
            "ORDER BY client_id, user_id, created_at ASC"
        )
    ).fetchall()

    if not rows:
        return

    sessions_to_insert = []
    message_updates = []  # (message_id, session_index, session_key)

    current_key = None  # (client_id, user_id)
    session_messages = []

    def flush_session(msgs):
        """Create a session record from a group of messages."""
        if not msgs:
            return
        first = msgs[0]
        last = msgs[-1]
        # Title = first user message truncated to 100 chars
        title = None
        for m in msgs:
            if m["role"] == "user":
                title = m["content"][:100]
                break
        session_idx = len(sessions_to_insert)
        sessions_to_insert.append({
            "client_id": first["client_id"],
            "user_id": first["user_id"],
            "started_at": first["created_at"],
            "ended_at": last["created_at"],
            "message_count": len(msgs),
            "is_active": False,
            "title": title,
        })
        # Track pair_index: sequential for assistant messages only
        pair_counter = 0
        for m in msgs:
            pi = None
            if m["role"] == "assistant":
                pi = pair_counter
                pair_counter += 1
            message_updates.append((m["id"], pi, session_idx))

    for row in rows:
        row_dict = {
            "id": row[0],
            "client_id": row[1],
            "user_id": row[2],
            "role": row[3],
            "content": row[4],
            "created_at": row[5],
        }
        key = (row_dict["client_id"], row_dict["user_id"])

        if current_key != key:
            # New client+user group — flush previous
            flush_session(session_messages)
            current_key = key
            session_messages = [row_dict]
        else:
            # Same client+user — check time gap
            prev_time = session_messages[-1]["created_at"]
            curr_time = row_dict["created_at"]
            gap = (curr_time - prev_time).total_seconds()
            if gap > SESSION_GAP_SECONDS:
                flush_session(session_messages)
                session_messages = [row_dict]
            else:
                session_messages.append(row_dict)

    # Flush the last group
    flush_session(session_messages)

    if not sessions_to_insert:
        return

    # Insert sessions one at a time to collect RETURNING ids
    session_ids = []
    for params in sessions_to_insert:
        result = conn.execute(
            sa.text(
                "INSERT INTO chat_sessions (client_id, user_id, started_at, ended_at, message_count, is_active, title) "
                "VALUES (:client_id, :user_id, :started_at, :ended_at, :message_count, :is_active, :title) "
                "RETURNING id"
            ),
            params,
        )
        session_ids.append(result.scalar())

    # Update each message with its session_id and pair_index
    for msg_id, pair_idx, session_idx in message_updates:
        conn.execute(
            sa.text(
                "UPDATE chat_messages SET session_id = :sid, pair_index = :pi WHERE id = :mid"
            ),
            {"sid": session_ids[session_idx], "pi": pair_idx, "mid": msg_id},
        )


def downgrade() -> None:
    op.drop_index("ix_chat_messages_session_id", table_name="chat_messages")
    op.execute("DROP INDEX IF EXISTS ix_chat_messages_pair_embedding")
    op.execute("DROP INDEX IF EXISTS ix_chat_sessions_summary_embedding")
    op.drop_index("ix_chat_sessions_client_user_active", table_name="chat_sessions")

    op.drop_column("chat_messages", "pair_index")
    op.execute("ALTER TABLE chat_messages DROP COLUMN IF EXISTS pair_embedding")
    op.drop_constraint("fk_chat_messages_session_id", "chat_messages", type_="foreignkey")
    op.drop_column("chat_messages", "session_id")

    op.drop_table("chat_sessions")

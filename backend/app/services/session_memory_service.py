"""
Session Memory: lifecycle management for chat sessions.

Groups chat messages into time-bounded sessions, generates summaries,
and embeds them for semantic search over past conversations.

Session boundary: 30 minutes of inactivity between messages.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.chat_message import ChatMessage
from app.models.chat_session import ChatSession

logger = logging.getLogger(__name__)

# 30-minute inactivity threshold for session boundaries
SESSION_GAP = timedelta(minutes=30)

SUMMARY_SYSTEM_PROMPT = (
    "You are summarizing a conversation between a CPA and an AI about a client. "
    "Return JSON with: summary (2-3 sentences), key_topics (array of short topic "
    "labels), key_decisions (array of decisions/conclusions reached, empty array if none)."
)


# ---------------------------------------------------------------------------
# Helpers — reuse rag_service's OpenAI client and embedding function
# ---------------------------------------------------------------------------


def _openai():
    from app.services.rag_service import _openai as _rag_openai
    return _rag_openai()


async def _embed(text: str) -> list[float]:
    from app.services.rag_service import embed_text
    return await embed_text(text)


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------


def get_or_create_session(
    client_id: UUID,
    user_id: str,
    org_id: UUID | None,
    db: Session,
) -> ChatSession:
    """Return the active session for this client+user, or create a new one.

    If the existing active session's last message is older than 30 minutes,
    the session is closed and a fresh one is started.
    """
    active = (
        db.query(ChatSession)
        .filter(
            ChatSession.client_id == client_id,
            ChatSession.user_id == user_id,
            ChatSession.is_active.is_(True),
        )
        .first()
    )

    now = datetime.now(timezone.utc)

    if active is not None:
        # Check the most recent message timestamp in this session
        last_msg = (
            db.query(ChatMessage.created_at)
            .filter(ChatMessage.session_id == active.id)
            .order_by(ChatMessage.created_at.desc())
            .first()
        )
        last_time = last_msg[0] if last_msg else active.started_at
        if now - last_time <= SESSION_GAP:
            return active
        # Session timed out — close it and start a new one
        _close_session_sync(active, db)

    session = ChatSession(
        client_id=client_id,
        user_id=user_id,
        org_id=org_id,
        is_active=True,
        started_at=now,
        message_count=0,
    )
    db.add(session)
    db.flush()  # assign id without committing
    return session


def attach_message_to_session(
    session_id: UUID,
    message_id: UUID,
    role: str,
    db: Session,
) -> None:
    """Link a chat message to its session and update session bookkeeping."""
    db.query(ChatMessage).filter(ChatMessage.id == message_id).update(
        {"session_id": session_id}
    )

    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if session is None:
        return

    session.message_count = (session.message_count or 0) + 1
    session.ended_at = datetime.now(timezone.utc)

    # Set title from first user message if not yet set
    if role == "user" and not session.title:
        msg = db.query(ChatMessage).filter(ChatMessage.id == message_id).first()
        if msg:
            session.title = msg.content[:100]


async def embed_qa_pair(
    session_id: UUID,
    user_message_content: str,
    assistant_message_content: str,
    assistant_message_id: UUID,
    pair_index: int,
    db: Session,
) -> None:
    """Embed a Q/A pair and store on the assistant message row."""
    try:
        combined = f"Q: {user_message_content}\nA: {assistant_message_content}"
        if len(combined) > 2000:
            combined = combined[:2000]

        embedding = await _embed(combined)

        db.query(ChatMessage).filter(
            ChatMessage.id == assistant_message_id
        ).update({"pair_embedding": embedding, "pair_index": pair_index})
        db.flush()
    except Exception:
        logger.exception("Failed to embed Q/A pair for session %s", session_id)


# ---------------------------------------------------------------------------
# Session closing & summary generation
# ---------------------------------------------------------------------------


def _close_session_sync(session: ChatSession, db: Session) -> None:
    """Mark session inactive. Summary generation is best-effort."""
    session.is_active = False
    db.flush()
    # Schedule async summary in a fire-and-forget task
    import asyncio
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_generate_session_summary(session.id, db))
    except RuntimeError:
        # No running loop — skip async summary (will be generated later)
        logger.info("No event loop for summary generation; session %s closed without summary", session.id)


async def close_session(session_id: UUID, db: Session) -> None:
    """Close a session and generate its summary."""
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if session is None:
        return
    session.is_active = False
    await _generate_session_summary(session_id, db)


async def _generate_session_summary(session_id: UUID, db: Session) -> None:
    """Generate an AI summary + embedding for a completed session.

    Best-effort: errors are logged but never block the chat flow.
    """
    try:
        messages = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.asc())
            .all()
        )
        if not messages:
            return

        # Build transcript (truncate to ~4000 chars to stay within token budget)
        transcript_parts = []
        total_len = 0
        for msg in messages:
            prefix = "User" if msg.role == "user" else "Assistant"
            line = f"{prefix}: {msg.content}"
            if total_len + len(line) > 4000:
                remaining = 4000 - total_len
                if remaining > 50:
                    transcript_parts.append(line[:remaining] + "…")
                break
            transcript_parts.append(line)
            total_len += len(line) + 1  # +1 for newline

        transcript = "\n".join(transcript_parts)

        client = _openai()
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": transcript},
            ],
            temperature=0.3,
            max_tokens=500,
            response_format={"type": "json_object"},
        )

        raw = response.choices[0].message.content or "{}"
        data = json.loads(raw)

        summary_text = data.get("summary", "")
        key_topics = data.get("key_topics", [])
        key_decisions = data.get("key_decisions", [])

        # Embed the summary for semantic search
        summary_embedding = await _embed(summary_text) if summary_text else None

        session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
        if session:
            session.summary = summary_text
            session.summary_embedding = summary_embedding
            session.key_topics = key_topics
            session.key_decisions = key_decisions
            db.flush()

        logger.info(
            "Generated summary for session %s: %d topics, %d decisions",
            session_id, len(key_topics), len(key_decisions),
        )

    except Exception:
        logger.exception("Failed to generate summary for session %s", session_id)

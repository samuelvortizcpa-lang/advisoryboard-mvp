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

        # ── Create journal entry for sessions with key decisions ──────
        if key_decisions and session:
            try:
                from app.services.journal_service import create_auto_entry

                decisions_text = "\n".join(f"- {d}" for d in key_decisions)
                journal_content = f"Session summary: {summary_text}\n\nDecisions:\n{decisions_text}"
                session_title = session.title or "Untitled conversation"

                create_auto_entry(
                    db=db,
                    client_id=session.client_id,
                    user_id=session.user_id,
                    entry_type="system",
                    category="general",
                    title=f"Advisory session: {session_title[:150]}",
                    content=journal_content,
                    source_type="chat",
                    source_id=session.id,
                    effective_date=session.started_at.date() if session.started_at else None,
                    metadata={"key_topics": key_topics, "message_count": session.message_count},
                )
                db.flush()
                logger.info("Created journal entry for session %s", session_id)
            except Exception:
                logger.exception("Failed to create journal entry for session %s", session_id)

        # ── Create follow-up alert for decisions mentioning follow-up ─
        if key_decisions and session:
            try:
                _create_follow_up_alerts(session, key_decisions, db)
            except Exception:
                logger.exception("Failed to create follow-up alerts for session %s", session_id)

    except Exception:
        logger.exception("Failed to generate summary for session %s", session_id)


# ---------------------------------------------------------------------------
# Follow-up alert detection
# ---------------------------------------------------------------------------

_FOLLOW_UP_KEYWORDS = [
    "follow up", "follow-up", "followup",
    "revisit", "next time", "come back to",
    "check on", "circle back", "touch base",
    "remind me", "don't forget",
]


def _create_follow_up_alerts(
    session: ChatSession,
    key_decisions: list[str],
    db: Session,
) -> None:
    """Create follow-up alerts for decisions that mention follow-up keywords.

    Best-effort heuristic — simple keyword matching, never blocks session flow.
    """
    from app.models.action_item import ActionItem

    trigger_date = (session.started_at or datetime.now(timezone.utc)) + timedelta(days=7)

    for decision in key_decisions:
        decision_lower = decision.lower()
        if not any(kw in decision_lower for kw in _FOLLOW_UP_KEYWORDS):
            continue

        # Create a pending action item as the follow-up reminder
        item = ActionItem(
            client_id=session.client_id,
            text=f"Follow up: {decision[:200]}",
            status="pending",
            priority="medium",
            source="ai",
            due_date=trigger_date.date(),
            created_by=session.user_id,
            assigned_to=session.user_id,
        )
        db.add(item)

    db.flush()
    logger.info(
        "Checked %d decisions for follow-up keywords in session %s",
        len(key_decisions), session.id,
    )


# ---------------------------------------------------------------------------
# Search & retrieval
# ---------------------------------------------------------------------------


async def search_sessions(
    client_id: UUID,
    user_id: str,
    query: str,
    db: Session,
    limit: int = 5,
) -> list[dict]:
    """Semantic search over session summaries using pgvector cosine distance."""
    embedding = await _embed(query)

    distance_col = ChatSession.summary_embedding.cosine_distance(embedding).label("distance")

    rows = (
        db.query(ChatSession, distance_col)
        .filter(
            ChatSession.client_id == client_id,
            ChatSession.user_id == user_id,
            ChatSession.is_active.is_(False),
            ChatSession.summary_embedding.isnot(None),
        )
        .order_by(distance_col)
        .limit(limit)
        .all()
    )

    results = []
    for session, distance in rows:
        score = (1 - distance / 2) * 100
        results.append({
            "id": session.id,
            "title": session.title,
            "summary": session.summary,
            "key_topics": session.key_topics,
            "key_decisions": session.key_decisions,
            "started_at": session.started_at,
            "ended_at": session.ended_at,
            "message_count": session.message_count,
            "similarity_score": round(score, 2),
        })
    return results


async def search_qa_pairs(
    client_id: UUID,
    user_id: str,
    query: str,
    db: Session,
    limit: int = 10,
) -> list[dict]:
    """Semantic search over embedded Q/A pairs in chat messages."""
    embedding = await _embed(query)

    distance_col = ChatMessage.pair_embedding.cosine_distance(embedding).label("distance")

    rows = (
        db.query(ChatMessage, ChatSession, distance_col)
        .join(ChatSession, ChatMessage.session_id == ChatSession.id)
        .filter(
            ChatSession.client_id == client_id,
            ChatSession.user_id == user_id,
            ChatMessage.pair_embedding.isnot(None),
        )
        .order_by(distance_col)
        .limit(limit)
        .all()
    )

    results = []
    for msg, session, distance in rows:
        score = (1 - distance / 2) * 100
        # Find the preceding user message in the same session
        user_msg = (
            db.query(ChatMessage.content)
            .filter(
                ChatMessage.session_id == session.id,
                ChatMessage.role == "user",
                ChatMessage.created_at < msg.created_at,
            )
            .order_by(ChatMessage.created_at.desc())
            .first()
        )
        results.append({
            "question": user_msg[0] if user_msg else "",
            "answer": msg.content,
            "session_id": session.id,
            "session_title": session.title,
            "session_date": session.started_at,
            "similarity_score": round(score, 2),
        })
    return results


def get_recent_sessions(
    client_id: UUID,
    user_id: str,
    db: Session,
    limit: int = 3,
) -> list[ChatSession]:
    """Return the most recent closed sessions for a client+user."""
    return (
        db.query(ChatSession)
        .filter(
            ChatSession.client_id == client_id,
            ChatSession.user_id == user_id,
            ChatSession.is_active.is_(False),
        )
        .order_by(ChatSession.ended_at.desc())
        .limit(limit)
        .all()
    )


def get_session_detail(
    session_id: UUID,
    user_id: str,
    db: Session,
) -> ChatSession | None:
    """Load a session with messages, verifying user access."""
    session = (
        db.query(ChatSession)
        .filter(
            ChatSession.id == session_id,
            ChatSession.user_id == user_id,
        )
        .first()
    )
    if session is None:
        return None

    # Eagerly load messages ordered by created_at
    session.messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    return session

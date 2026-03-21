"""
Front conversation sync service: fetches conversations from a connected
Front account and ingests them into AdvisoryBoard as documents.

Flow
----
sync_conversations(connection_id, user_id, db)
  ├─ get_valid_token()
  ├─ Front API: list conversations (since N hours)
  └─ for each conversation:
        ├─ fetch messages in thread
        ├─ deduplicate by external_id (front conversation ID)
        ├─ match to client via email routing rules or tag→client name
        ├─ build single document from entire thread
        ├─ upload to Supabase Storage
        ├─ create Document row
        └─ kick off RAG pipeline (embed + action items)

Dependencies:
  - httpx  (Front REST API)
"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional
from uuid import UUID

import httpx
from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.document import Document
from app.models.email_routing_rule import EmailRoutingRule
from app.models.integration_connection import IntegrationConnection
from app.models.sync_log import SyncLog
from app.models.user import User
from app.services import front_auth_service, storage_service

logger = logging.getLogger(__name__)

# Front API endpoints
FRONT_CONVERSATIONS_URL = "https://api2.frontapp.com/conversations"

# Front rate limit: 50 requests/minute on /conversations.
# 1.5s pause between per-conversation detail fetches keeps us well under.
_RATE_LIMIT_DELAY = 1.5


# ---------------------------------------------------------------------------
# HTML stripping (same pattern as outlook_sync_service)
# ---------------------------------------------------------------------------

class _HTMLTextExtractor(HTMLParser):
    """Minimal HTML→text converter using stdlib."""

    def __init__(self) -> None:
        super().__init__()
        self._pieces: list[str] = []

    def handle_data(self, data: str) -> None:
        self._pieces.append(data)

    def get_text(self) -> str:
        return "".join(self._pieces)


def _strip_html(html: str) -> str:
    """Remove HTML tags and collapse whitespace."""
    extractor = _HTMLTextExtractor()
    extractor.feed(html)
    text = extractor.get_text()
    text = re.sub(r" {2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Front API helpers
# ---------------------------------------------------------------------------

async def _fetch_conversations(
    access_token: str,
    since_timestamp: int,
    max_results: int,
    connection_id: UUID,
    db: Session,
) -> List[Dict]:
    """
    Fetch conversations from Front API with pagination and 401 retry.

    Returns a list of conversation objects.
    """
    params: Dict[str, Any] = {
        "q[after]": since_timestamp,
        "limit": min(max_results, 50),
    }

    all_conversations: list[Dict] = []
    token = access_token
    next_url: Optional[str] = None

    async with httpx.AsyncClient(timeout=30) as client:
        while len(all_conversations) < max_results:
            url = next_url or FRONT_CONVERSATIONS_URL
            # Only pass params on the first request; pagination URLs include them
            request_params = params if not next_url else None
            headers = {"Authorization": f"Bearer {token}"}

            response = await client.get(
                url, headers=headers, params=request_params,
            )

            # Handle 401: refresh token and retry once
            if response.status_code == 401 and not next_url:
                logger.info(
                    "Front API 401 for connection=%s — refreshing token",
                    connection_id,
                )
                conn = await front_auth_service.refresh_access_token(
                    connection_id, db
                )
                token = front_auth_service._decrypt(conn.access_token)
                headers = {"Authorization": f"Bearer {token}"}
                response = await client.get(
                    url, headers=headers, params=request_params,
                )

            response.raise_for_status()
            data = response.json()

            results = data.get("_results", [])
            remaining = max_results - len(all_conversations)
            all_conversations.extend(results[:remaining])

            # Check for next page
            pagination = data.get("_pagination", {})
            next_url = pagination.get("next")
            if not next_url or len(all_conversations) >= max_results:
                break

    return all_conversations


async def _fetch_conversation_messages(
    conversation_id: str,
    access_token: str,
) -> List[Dict]:
    """
    Fetch all messages in a Front conversation.

    Returns a list of message objects, oldest first.
    """
    url = f"{FRONT_CONVERSATIONS_URL}/{conversation_id}/messages"
    all_messages: list[Dict] = []
    next_url: Optional[str] = None

    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            request_url = next_url or url
            response = await client.get(
                request_url,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            response.raise_for_status()
            data = response.json()

            messages = data.get("_results", [])
            all_messages.extend(messages)

            pagination = data.get("_pagination", {})
            next_url = pagination.get("next")
            if not next_url:
                break

    # Front returns messages newest-first; reverse for chronological order
    all_messages.reverse()
    return all_messages


# ---------------------------------------------------------------------------
# Client matching
# ---------------------------------------------------------------------------

def _extract_email_addresses_from_messages(messages: List[Dict]) -> tuple[list[str], list[str]]:
    """
    Extract sender and recipient email addresses from Front messages.

    Returns (from_emails, to_emails) as deduplicated lists.
    """
    from_emails: list[str] = []
    to_emails: list[str] = []
    seen_from: set[str] = set()
    seen_to: set[str] = set()

    for msg in messages:
        # Author (sender)
        author = msg.get("author", {})
        if author:
            author_email = author.get("email", "")
            if author_email and author_email not in seen_from:
                from_emails.append(author_email)
                seen_from.add(author_email)

        # Recipients
        for recipient in msg.get("recipients", []):
            r_email = recipient.get("handle", "")
            if r_email and r_email not in seen_to:
                to_emails.append(r_email)
                seen_to.add(r_email)

    return from_emails, to_emails


def _match_conversation_to_client(
    conversation: Dict,
    messages: List[Dict],
    user_id: str,
    owner_id: uuid.UUID,
    db: Session,
) -> Optional[UUID]:
    """
    Try to match a Front conversation to a client.

    Priority:
      1. Email routing rules (sender/recipient emails from messages)
      2. Conversation contact email against routing rules
      3. Tag-to-client name match (Front tags often map to clients)

    Returns client_id or None.
    """
    from_emails, to_emails = _extract_email_addresses_from_messages(messages)

    # ── Pre-load routing rules ───────────────────────────────────────────
    routing_rules = (
        db.query(EmailRoutingRule)
        .filter(
            EmailRoutingRule.user_id == user_id,
            EmailRoutingRule.is_active == True,
        )
        .all()
    )
    rules_by_email: dict[str, EmailRoutingRule] = {}
    for rule in routing_rules:
        rules_by_email[rule.email_address.strip().lower()] = rule

    # ── Priority 1: message sender/recipient emails ──────────────────────
    # Check sender emails with 'from' or 'both' rules
    for email in from_emails:
        email_lower = email.strip().lower()
        rule = rules_by_email.get(email_lower)
        if rule and rule.match_type in ("from", "both"):
            return rule.client_id

    # Check recipient emails with 'to' or 'both' rules
    for email in to_emails:
        email_lower = email.strip().lower()
        rule = rules_by_email.get(email_lower)
        if rule and rule.match_type in ("to", "both"):
            return rule.client_id

    # ── Priority 2: conversation contact email ───────────────────────────
    # Front links conversations to contacts; the contact often has an email
    # (available via conversation.recipient.handle or conversation.contact)
    recipient = conversation.get("recipient", {})
    contact_email = ""
    if recipient:
        contact_email = (recipient.get("handle", "") or "").strip().lower()
    if contact_email:
        rule = rules_by_email.get(contact_email)
        if rule:
            return rule.client_id

    # ── Priority 3: tag → client name match ──────────────────────────────
    tags = conversation.get("tags", [])
    if tags:
        clients = (
            db.query(Client)
            .filter(Client.owner_id == owner_id)
            .all()
        )
        client_by_name_lower: dict[str, UUID] = {}
        for c in clients:
            if c.name:
                client_by_name_lower[c.name.strip().lower()] = c.id

        for tag in tags:
            tag_name = tag.get("name", "").strip().lower()
            if tag_name and tag_name in client_by_name_lower:
                return client_by_name_lower[tag_name]

    return None


# ---------------------------------------------------------------------------
# Document content formatting
# ---------------------------------------------------------------------------

def _safe_filename(subject: str, created_at: str) -> str:
    """Build a filesystem-safe filename from conversation subject and date."""
    clean_subject = re.sub(r"[^\w\s-]", "", subject or "conversation")
    clean_subject = re.sub(r"\s+", "_", clean_subject.strip())[:80]

    date_part = "unknown"
    if created_at:
        try:
            # Front timestamps are Unix epoch (integer)
            ts = float(created_at)
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            date_part = dt.strftime("%Y-%m-%d")
        except (ValueError, TypeError, OSError):
            date_part = re.sub(r"[^\w-]", "", str(created_at)[:10])

    return f"front_conversation_{clean_subject}_{date_part}.txt"


def build_conversation_document_content(
    conversation: Dict[str, Any],
    messages: List[Dict[str, Any]],
) -> str:
    """
    Format a Front conversation and its messages into a clean text document.

    Output format:
        Front Conversation: Subject line here
        Status: open
        Assignee: alice@company.com
        Tags: ClientA, Billing
        Created: 2024-01-15T10:00:00Z

        --- Messages ---

        [2024-01-15 10:00] alice@example.com:
        Message body text...

        [2024-01-15 10:15] bob@example.com:
        Reply body text...
    """
    subject = conversation.get("subject", "No Subject")
    conv_status = conversation.get("status", "unknown")
    created_at = conversation.get("created_at", "")

    # Assignee
    assignee = conversation.get("assignee", {})
    assignee_name = ""
    if assignee:
        assignee_name = assignee.get("email", "") or assignee.get("username", "")

    # Tags
    tags = conversation.get("tags", [])
    tag_names = ", ".join(t.get("name", "") for t in tags if t.get("name"))

    # Header
    header_lines: list[str] = []
    header_lines.append(f"Front Conversation: {subject}")
    header_lines.append(f"Status: {conv_status}")
    if assignee_name:
        header_lines.append(f"Assignee: {assignee_name}")
    if tag_names:
        header_lines.append(f"Tags: {tag_names}")
    if created_at:
        try:
            ts = float(created_at)
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            header_lines.append(f"Created: {dt.isoformat()}")
        except (ValueError, TypeError, OSError):
            header_lines.append(f"Created: {created_at}")

    parts = ["\n".join(header_lines)]

    # Messages
    message_lines: list[str] = []
    for msg in messages:
        # Author
        author = msg.get("author", {})
        author_email = ""
        if author:
            author_email = author.get("email", "") or author.get("username", "")

        # Timestamp
        msg_created = msg.get("created_at", "")
        timestamp_str = ""
        if msg_created:
            try:
                ts = float(msg_created)
                dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                timestamp_str = dt.strftime("%Y-%m-%d %H:%M")
            except (ValueError, TypeError, OSError):
                timestamp_str = str(msg_created)

        # Body — Front messages have HTML body
        body_html = msg.get("body", "")
        body_text = _strip_html(body_html) if body_html else ""

        if timestamp_str or author_email:
            message_lines.append(f"[{timestamp_str}] {author_email}:")
        if body_text:
            message_lines.append(body_text)
        message_lines.append("")  # blank line between messages

    if message_lines:
        parts.append("--- Messages ---\n\n" + "\n".join(message_lines).rstrip())

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# 1. Core sync function
# ---------------------------------------------------------------------------

async def sync_conversations(
    connection_id: UUID,
    user_id: str,
    db: Session,
    sync_type: str = "manual",
    max_results: int = 50,
    since_hours: int = 24,
) -> SyncLog:
    """
    Fetch recent conversations from Front and ingest them as documents.

    Steps:
      1. Get a valid access token
      2. List conversations from the last ``since_hours`` hours
      3. For each conversation: fetch messages, deduplicate, match, ingest
      4. Record results in a SyncLog

    Returns the SyncLog for this sync run.
    """
    # Reuse sync_log table: emails_found → conversations found, etc.
    sync_log = SyncLog(
        connection_id=connection_id,
        sync_type=sync_type,
        status="running",
    )
    db.add(sync_log)
    db.commit()
    db.refresh(sync_log)

    items_found = 0
    items_ingested = 0
    items_skipped = 0

    try:
        # ── Validate connection ownership ─────────────────────────────────
        connection = (
            db.query(IntegrationConnection)
            .filter(
                IntegrationConnection.id == connection_id,
                IntegrationConnection.user_id == user_id,
                IntegrationConnection.provider == "front",
                IntegrationConnection.is_active == True,
            )
            .first()
        )
        if not connection:
            raise ValueError(
                f"No active Front connection {connection_id} for user {user_id}"
            )

        # ── Get valid access token ────────────────────────────────────────
        access_token = await front_auth_service.get_valid_token(
            connection_id, db
        )

        # ── Resolve the owner User row ────────────────────────────────────
        owner = db.query(User).filter(User.clerk_id == user_id).first()
        if not owner:
            raise ValueError(f"User with clerk_id={user_id} not found")

        # ── Query Front conversations ─────────────────────────────────────
        since_epoch = int(
            (datetime.now(timezone.utc) - timedelta(hours=since_hours)).timestamp()
        )

        conversations = await _fetch_conversations(
            access_token=access_token,
            since_timestamp=since_epoch,
            max_results=max_results,
            connection_id=connection_id,
            db=db,
        )
        items_found = len(conversations)

        logger.info(
            "Front sync: found %d conversation(s) for connection=%s (since %dh)",
            items_found,
            connection_id,
            since_hours,
        )

        # ── Process each conversation ─────────────────────────────────────
        for conv in conversations:
            conv_id = conv.get("id", "")

            try:
                result = await _process_single_conversation(
                    conversation=conv,
                    access_token=access_token,
                    owner=owner,
                    user_id=user_id,
                    db=db,
                )
                if result == "ingested":
                    items_ingested += 1
                else:
                    items_skipped += 1
            except Exception as exc:
                logger.warning(
                    "Front sync: error processing conversation %s: %s",
                    conv_id,
                    exc,
                )
                items_skipped += 1

        # ── Update connection last_sync_at ────────────────────────────────
        connection.last_sync_at = datetime.now(timezone.utc)
        db.commit()

        # ── Finalise sync log ─────────────────────────────────────────────
        sync_log.status = "completed"
        sync_log.emails_found = items_found
        sync_log.emails_ingested = items_ingested
        sync_log.emails_skipped = items_skipped
        sync_log.completed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(sync_log)

        logger.info(
            "Front sync completed: found=%d ingested=%d skipped=%d",
            items_found,
            items_ingested,
            items_skipped,
        )

    except Exception as exc:
        logger.exception(
            "Front sync failed for connection=%s: %s", connection_id, exc
        )
        db.rollback()

        sync_log = db.query(SyncLog).filter(SyncLog.id == sync_log.id).first()
        if sync_log:
            sync_log.status = "failed"
            sync_log.emails_found = items_found
            sync_log.emails_ingested = items_ingested
            sync_log.emails_skipped = items_skipped
            sync_log.error_message = str(exc)[:1000]
            sync_log.completed_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(sync_log)

    return sync_log


# ---------------------------------------------------------------------------
# Internal: process one Front conversation
# ---------------------------------------------------------------------------

async def _process_single_conversation(
    conversation: Dict[str, Any],
    access_token: str,
    owner: User,
    user_id: str,
    db: Session,
) -> str:
    """
    Fetch messages, match to client, and ingest a single conversation.

    If the conversation was previously ingested but has new messages, the
    existing document is updated in-place (re-uploaded and re-processed)
    rather than creating a duplicate.

    Returns:
        "ingested" if the conversation was saved/updated as a document
        "skipped"  if it was empty or unmatched
    """
    conv_id = conversation.get("id", "")
    subject = conversation.get("subject", "No Subject")

    if not conv_id:
        return "skipped"

    # ── Rate-limit pause (Front: 50 req/min on /conversations) ────────────
    await asyncio.sleep(_RATE_LIMIT_DELAY)

    # ── Fetch messages ────────────────────────────────────────────────────
    messages = await _fetch_conversation_messages(conv_id, access_token)
    if not messages:
        logger.debug("Front sync: no messages in conversation %s", conv_id)
        return "skipped"

    # ── Match to client ───────────────────────────────────────────────────
    client_id = _match_conversation_to_client(
        conversation=conversation,
        messages=messages,
        user_id=user_id,
        owner_id=owner.id,
        db=db,
    )
    if client_id is None:
        logger.debug(
            "Front sync: no client match for conversation %s (subject=%r)",
            conv_id,
            subject,
        )
        return "skipped"

    # Verify the client belongs to this user
    client = (
        db.query(Client)
        .filter(Client.id == client_id, Client.owner_id == owner.id)
        .first()
    )
    if not client:
        logger.warning(
            "Front sync: matched client %s not owned by user %s",
            client_id,
            user_id,
        )
        return "skipped"

    # ── Build document content ────────────────────────────────────────────
    content_text = build_conversation_document_content(conversation, messages)
    content_bytes = content_text.encode("utf-8")

    # ── Check for existing document (update vs create) ────────────────────
    existing_doc = (
        db.query(Document)
        .filter(
            Document.source == "front",
            Document.external_id == conv_id,
        )
        .first()
    )

    if existing_doc:
        # Conversation was previously ingested — update with fresh content
        old_path = existing_doc.file_path

        file_id = str(uuid.uuid4())
        created_at = str(conversation.get("created_at", ""))
        filename = _safe_filename(subject, created_at)

        storage_path = storage_service.upload_file(
            user_id=str(owner.id),
            client_id=str(client_id),
            file_id=file_id,
            filename=filename,
            file_bytes=content_bytes,
            content_type="text/plain",
        )

        existing_doc.file_path = storage_path
        existing_doc.filename = filename
        existing_doc.file_size = len(content_bytes)
        existing_doc.client_id = client_id
        existing_doc.processed = False
        existing_doc.processing_error = None
        db.commit()
        db.refresh(existing_doc)

        # Clean up old storage file
        try:
            storage_service.delete_file(old_path)
        except Exception:
            pass  # non-fatal

        logger.info(
            "Front sync: updated conversation %s → document %s (client=%s, subject=%r)",
            conv_id,
            existing_doc.id,
            client_id,
            subject[:60],
        )

        # Re-run RAG pipeline on the updated document
        try:
            from app.services.rag_service import process_document

            await process_document(db, existing_doc)
        except Exception as rag_exc:
            logger.warning(
                "Front sync: RAG re-processing failed for document %s (non-fatal): %s",
                existing_doc.id,
                rag_exc,
            )

        return "ingested"

    # ── Upload new document to Supabase Storage ───────────────────────────
    file_id = str(uuid.uuid4())
    created_at = str(conversation.get("created_at", ""))
    filename = _safe_filename(subject, created_at)

    storage_path = storage_service.upload_file(
        user_id=str(owner.id),
        client_id=str(client_id),
        file_id=file_id,
        filename=filename,
        file_bytes=content_bytes,
        content_type="text/plain",
    )

    # ── Create Document row ───────────────────────────────────────────────
    try:
        document = Document(
            client_id=client_id,
            uploaded_by=owner.id,
            filename=filename,
            file_path=storage_path,
            file_type="txt",
            file_size=len(content_bytes),
            source="front",
            external_id=conv_id,
        )
        db.add(document)
        db.commit()
        db.refresh(document)
    except Exception:
        storage_service.delete_file(storage_path)
        db.rollback()
        raise

    logger.info(
        "Front sync: ingested conversation %s → document %s (client=%s, subject=%r)",
        conv_id,
        document.id,
        client_id,
        subject[:60],
    )

    # ── Kick off RAG pipeline ─────────────────────────────────────────────
    try:
        from app.services.rag_service import process_document

        await process_document(db, document)
    except Exception as rag_exc:
        logger.warning(
            "Front sync: RAG processing failed for document %s (non-fatal): %s",
            document.id,
            rag_exc,
        )

    return "ingested"


# ---------------------------------------------------------------------------
# 3. Sync history
# ---------------------------------------------------------------------------

def get_sync_history(
    user_id: str,
    connection_id: UUID,
    db: Session,
    limit: int = 20,
) -> List[SyncLog]:
    """
    Return recent sync logs for a connection, most recent first.

    Only returns logs for connections owned by the requesting user.
    """
    connection = (
        db.query(IntegrationConnection)
        .filter(
            IntegrationConnection.id == connection_id,
            IntegrationConnection.user_id == user_id,
        )
        .first()
    )
    if not connection:
        return []

    return (
        db.query(SyncLog)
        .filter(SyncLog.connection_id == connection_id)
        .order_by(SyncLog.started_at.desc())
        .limit(limit)
        .all()
    )

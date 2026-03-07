"""
Gmail sync service: fetches emails from a connected Gmail account and
ingests them into AdvisoryBoard as documents.

Flow
----
sync_emails(connection_id, user_id, db)
  ├─ get_valid_token()
  ├─ Gmail API: list messages (since N hours)
  └─ for each message:
        ├─ fetch full message
        ├─ extract headers + body
        ├─ deduplicate by gmail_message_id
        ├─ match sender → client via email_routing_rules
        ├─ upload to Supabase Storage
        ├─ create Document row
        └─ kick off RAG pipeline (embed + action items)

Dependencies:
  - google-api-python-client  (Gmail REST API)
  - google-auth               (Credentials wrapper)
"""

from __future__ import annotations

import base64
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from google.auth.credentials import Credentials as BaseCredentials
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.document import Document
from app.models.email_routing_rule import EmailRoutingRule
from app.models.integration_connection import IntegrationConnection
from app.models.sync_log import SyncLog
from app.models.user import User
from app.services import google_auth_service, storage_service
from app.services.email_extractor import _format_email, _strip_html

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Gmail API helpers
# ---------------------------------------------------------------------------


def _build_gmail_service(access_token: str):
    """Build a Gmail API service object using a raw access token."""
    creds = Credentials(token=access_token)
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _extract_header(headers: List[Dict], name: str) -> str:
    """Pull a header value from the Gmail message headers list."""
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def _extract_email_address(header_value: str) -> str:
    """
    Extract the bare email address from a header value.

    Handles formats like:
        "John Doe <john@example.com>"  →  "john@example.com"
        "john@example.com"             →  "john@example.com"
    """
    match = re.search(r"<([^>]+)>", header_value)
    if match:
        return match.group(1).strip().lower()
    # Might already be a bare address
    addr = header_value.strip().lower()
    if "@" in addr:
        return addr
    return ""


def _decode_body_part(part: Dict) -> str:
    """Decode a base64url-encoded MIME body part."""
    data = part.get("body", {}).get("data", "")
    if not data:
        return ""
    try:
        return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
    except Exception:
        return ""


def _extract_body(payload: Dict) -> str:
    """
    Walk the message payload tree and extract the body text.

    Prefers text/plain; falls back to text/html with tags stripped.
    """
    mime_type = payload.get("mimeType", "")
    parts = payload.get("parts", [])

    # Simple message (no parts)
    if not parts:
        body_text = _decode_body_part(payload)
        if mime_type == "text/plain":
            return body_text
        if mime_type == "text/html":
            return _strip_html(body_text)
        return body_text

    # Multipart — walk recursively
    plain_texts: list[str] = []
    html_texts: list[str] = []

    def _walk(node: Dict) -> None:
        node_mime = node.get("mimeType", "")
        node_parts = node.get("parts", [])

        if node_parts:
            for child in node_parts:
                _walk(child)
        else:
            text = _decode_body_part(node)
            if not text:
                return
            if node_mime == "text/plain":
                plain_texts.append(text)
            elif node_mime == "text/html":
                html_texts.append(text)

    for part in parts:
        _walk(part)

    if plain_texts:
        return "\n\n".join(plain_texts).strip()
    if html_texts:
        return _strip_html("\n\n".join(html_texts)).strip()
    return ""


def _safe_filename(subject: str, date_str: str) -> str:
    """Build a filesystem-safe filename from subject and date."""
    # Strip non-alphanumeric chars from subject, truncate
    clean_subject = re.sub(r"[^\w\s-]", "", subject or "no-subject")
    clean_subject = re.sub(r"\s+", "_", clean_subject.strip())[:80]

    # Extract date portion (YYYY-MM-DD) or use 'unknown'
    date_part = "unknown"
    if date_str:
        # Try to parse the RFC 2822 date
        try:
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(date_str)
            date_part = dt.strftime("%Y-%m-%d")
        except Exception:
            date_part = re.sub(r"[^\w-]", "", date_str[:10])

    return f"email_{clean_subject}_{date_part}.txt"


# ---------------------------------------------------------------------------
# 1. Core sync function
# ---------------------------------------------------------------------------


async def sync_emails(
    connection_id: UUID,
    user_id: str,
    db: Session,
    sync_type: str = "manual",
    max_results: int = 50,
    since_hours: int = 24,
) -> SyncLog:
    """
    Fetch recent emails from Gmail and ingest matched ones as documents.

    Steps:
      1. Get a valid access token
      2. List messages from the last ``since_hours`` hours
      3. For each message: extract, deduplicate, match, ingest
      4. Record results in a SyncLog

    Returns the SyncLog for this sync run.
    """
    # Create sync log early so we can track even if something fails
    sync_log = SyncLog(
        connection_id=connection_id,
        sync_type=sync_type,
        status="running",
    )
    db.add(sync_log)
    db.commit()
    db.refresh(sync_log)

    emails_found = 0
    emails_ingested = 0
    emails_skipped = 0

    try:
        # ── Validate connection ownership ─────────────────────────────────
        connection = (
            db.query(IntegrationConnection)
            .filter(
                IntegrationConnection.id == connection_id,
                IntegrationConnection.user_id == user_id,
                IntegrationConnection.is_active == True,
            )
            .first()
        )
        if not connection:
            raise ValueError(
                f"No active connection {connection_id} for user {user_id}"
            )

        # ── Get valid access token ────────────────────────────────────────
        access_token = await google_auth_service.get_valid_token(connection_id, db)

        # ── Resolve the owner User row (needed for document ownership) ────
        owner = db.query(User).filter(User.clerk_id == user_id).first()
        if not owner:
            raise ValueError(f"User with clerk_id={user_id} not found")

        # ── Pre-load routing rules for this user ──────────────────────────
        routing_rules = (
            db.query(EmailRoutingRule)
            .filter(
                EmailRoutingRule.user_id == user_id,
                EmailRoutingRule.is_active == True,
            )
            .all()
        )
        rules_by_email = _index_routing_rules(routing_rules)

        # ── Query Gmail ───────────────────────────────────────────────────
        service = _build_gmail_service(access_token)
        since_epoch = int(
            (datetime.now(timezone.utc) - timedelta(hours=since_hours)).timestamp()
        )

        try:
            response = (
                service.users()
                .messages()
                .list(
                    userId="me",
                    q=f"after:{since_epoch}",
                    maxResults=max_results,
                )
                .execute()
            )
        except HttpError as exc:
            raise RuntimeError(f"Gmail API list error: {exc}") from exc

        messages_meta = response.get("messages", [])
        emails_found = len(messages_meta)

        logger.info(
            "Gmail sync: found %d message(s) for connection=%s (since %dh)",
            emails_found,
            connection_id,
            since_hours,
        )

        # ── Process each message ──────────────────────────────────────────
        for msg_meta in messages_meta:
            gmail_msg_id = msg_meta["id"]

            try:
                result = await _process_single_message(
                    service=service,
                    gmail_msg_id=gmail_msg_id,
                    owner=owner,
                    user_id=user_id,
                    rules_by_email=rules_by_email,
                    db=db,
                )
                if result == "ingested":
                    emails_ingested += 1
                else:
                    emails_skipped += 1
            except Exception as msg_exc:
                logger.warning(
                    "Gmail sync: error processing message %s: %s",
                    gmail_msg_id,
                    msg_exc,
                )
                emails_skipped += 1

        # ── Update connection last_sync_at ────────────────────────────────
        connection.last_sync_at = datetime.now(timezone.utc)
        db.commit()

        # ── Finalise sync log ─────────────────────────────────────────────
        sync_log.status = "completed"
        sync_log.emails_found = emails_found
        sync_log.emails_ingested = emails_ingested
        sync_log.emails_skipped = emails_skipped
        sync_log.completed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(sync_log)

        logger.info(
            "Gmail sync completed: found=%d ingested=%d skipped=%d",
            emails_found,
            emails_ingested,
            emails_skipped,
        )

    except Exception as exc:
        logger.exception("Gmail sync failed for connection=%s: %s", connection_id, exc)
        db.rollback()

        # Re-fetch sync log after rollback
        sync_log = db.query(SyncLog).filter(SyncLog.id == sync_log.id).first()
        if sync_log:
            sync_log.status = "failed"
            sync_log.emails_found = emails_found
            sync_log.emails_ingested = emails_ingested
            sync_log.emails_skipped = emails_skipped
            sync_log.error_message = str(exc)[:1000]
            sync_log.completed_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(sync_log)

    return sync_log


# ---------------------------------------------------------------------------
# Internal: process one Gmail message
# ---------------------------------------------------------------------------


def _index_routing_rules(
    rules: List[EmailRoutingRule],
) -> Dict[str, List[EmailRoutingRule]]:
    """
    Build a lookup dict: lowercase email address → list of matching rules.
    """
    index: Dict[str, List[EmailRoutingRule]] = {}
    for rule in rules:
        key = rule.email_address.strip().lower()
        index.setdefault(key, []).append(rule)
    return index


def _match_client(
    from_addr: str,
    to_addrs: List[str],
    rules_by_email: Dict[str, List[EmailRoutingRule]],
) -> Optional[UUID]:
    """
    Try to match an email to a client using routing rules.

    Returns the client_id if a match is found, None otherwise.
    """
    from_lower = from_addr.lower()

    # Check 'from' and 'both' rules against the sender
    for rule in rules_by_email.get(from_lower, []):
        if rule.match_type in ("from", "both"):
            return rule.client_id

    # Check 'to' and 'both' rules against recipients
    for to_addr in to_addrs:
        to_lower = to_addr.lower()
        for rule in rules_by_email.get(to_lower, []):
            if rule.match_type in ("to", "both"):
                return rule.client_id

    return None


async def _process_single_message(
    service,
    gmail_msg_id: str,
    owner: User,
    user_id: str,
    rules_by_email: Dict[str, List[EmailRoutingRule]],
    db: Session,
) -> str:
    """
    Fetch, parse, and ingest a single Gmail message.

    Returns:
        "ingested" if the email was saved as a document
        "skipped"  if it was a duplicate or unmatched
    """
    # ── Deduplicate ───────────────────────────────────────────────────────
    existing = (
        db.query(Document.id)
        .filter(Document.gmail_message_id == gmail_msg_id)
        .first()
    )
    if existing:
        logger.debug("Gmail sync: skipping duplicate message %s", gmail_msg_id)
        return "skipped"

    # ── Fetch full message ────────────────────────────────────────────────
    try:
        msg = (
            service.users()
            .messages()
            .get(userId="me", id=gmail_msg_id, format="full")
            .execute()
        )
    except HttpError as exc:
        raise RuntimeError(f"Failed to fetch message {gmail_msg_id}: {exc}") from exc

    payload = msg.get("payload", {})
    headers = payload.get("headers", [])

    # ── Extract fields ────────────────────────────────────────────────────
    from_header = _extract_header(headers, "From")
    to_header = _extract_header(headers, "To")
    cc_header = _extract_header(headers, "Cc")
    subject = _extract_header(headers, "Subject")
    date_str = _extract_header(headers, "Date")
    body = _extract_body(payload)

    from_email = _extract_email_address(from_header)

    # Parse all recipient addresses
    to_emails: list[str] = []
    for raw in [to_header, cc_header]:
        if raw:
            for part in raw.split(","):
                addr = _extract_email_address(part.strip())
                if addr:
                    to_emails.append(addr)

    # ── Match to client ───────────────────────────────────────────────────
    client_id = _match_client(from_email, to_emails, rules_by_email)
    if client_id is None:
        logger.debug(
            "Gmail sync: no routing rule for message %s (from=%s)",
            gmail_msg_id,
            from_email,
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
            "Gmail sync: routing rule points to client %s which user %s does not own",
            client_id,
            user_id,
        )
        return "skipped"

    # ── Build document content ────────────────────────────────────────────
    content_text = build_email_document_content(
        from_addr=from_header,
        to_addr=to_header,
        cc_addr=cc_header,
        subject=subject,
        date=date_str,
        body=body,
    )
    content_bytes = content_text.encode("utf-8")

    # ── Upload to Supabase Storage ────────────────────────────────────────
    file_id = str(uuid.uuid4())
    filename = _safe_filename(subject, date_str)

    storage_path = storage_service.upload_file(
        user_id=str(owner.id),
        client_id=str(client_id),
        file_id=file_id,
        filename=filename,
        file_bytes=content_bytes,
        content_type="message/rfc822",
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
            gmail_message_id=gmail_msg_id,
            source="gmail",
            external_id=gmail_msg_id,
        )
        db.add(document)
        db.commit()
        db.refresh(document)
    except Exception:
        # Clean up the uploaded file on failure
        storage_service.delete_file(storage_path)
        db.rollback()
        raise

    logger.info(
        "Gmail sync: ingested message %s → document %s (client=%s, subject=%r)",
        gmail_msg_id,
        document.id,
        client_id,
        subject[:60],
    )

    # ── Kick off RAG pipeline in the background ───────────────────────────
    # Import here to avoid circular imports; runs async in-process
    try:
        from app.services.rag_service import process_document

        await process_document(db, document)
    except Exception as rag_exc:
        logger.warning(
            "Gmail sync: RAG processing failed for document %s (non-fatal): %s",
            document.id,
            rag_exc,
        )

    return "ingested"


# ---------------------------------------------------------------------------
# 2. Build email document content
# ---------------------------------------------------------------------------


def build_email_document_content(
    from_addr: str,
    to_addr: str,
    subject: str,
    date: str,
    body: str,
    cc_addr: str = "",
) -> str:
    """
    Format email data into a clean text document matching the format
    produced by email_extractor.py for .eml files.

    Output format:
        From: sender@example.com
        To: recipient@example.com
        Cc: cc@example.com
        Subject: Subject line here
        Date: Mon, 01 Jan 2024 10:00:00 +0000

        Body:
        Email body text...
    """
    header_lines: list[str] = []
    if from_addr:
        header_lines.append(f"From: {from_addr}")
    if to_addr:
        header_lines.append(f"To: {to_addr}")
    if cc_addr:
        header_lines.append(f"Cc: {cc_addr}")
    if subject:
        header_lines.append(f"Subject: {subject}")
    if date:
        header_lines.append(f"Date: {date}")

    parts = ["\n".join(header_lines)] if header_lines else []

    if body:
        parts.append(f"Body:\n{body}")

    return "\n\n".join(parts)


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
    # Verify the connection belongs to this user
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

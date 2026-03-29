"""
Outlook sync service: fetches emails from a connected Microsoft 365 account
and ingests them into Callwen as documents.

Flow
----
sync_emails(connection_id, user_id, db)
  ├─ get_valid_token()
  ├─ Microsoft Graph API: list messages (since N hours)
  └─ for each message:
        ├─ extract headers + body
        ├─ deduplicate by external_id (Graph message id)
        ├─ match sender → client via email_routing_rules
        ├─ upload to Supabase Storage
        ├─ create Document row
        └─ kick off RAG pipeline (embed + action items)

Dependencies:
  - httpx  (Microsoft Graph REST API)
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from io import StringIO
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
from app.services import microsoft_auth_service, storage_service

logger = logging.getLogger(__name__)

# Microsoft Graph API base
GRAPH_BASE = "https://graph.microsoft.com/v1.0"
GRAPH_MESSAGES_URL = f"{GRAPH_BASE}/me/messages"

# Fields to request from Graph API
GRAPH_SELECT_FIELDS = (
    "id,subject,from,toRecipients,ccRecipients,"
    "receivedDateTime,body,bodyPreview"
)


# ---------------------------------------------------------------------------
# HTML stripping helper
# ---------------------------------------------------------------------------

class _HTMLTextExtractor(HTMLParser):
    """Simple HTML→text converter via html.parser."""

    def __init__(self) -> None:
        super().__init__()
        self._result = StringIO()

    def handle_data(self, data: str) -> None:
        self._result.write(data)

    def get_text(self) -> str:
        return self._result.getvalue()


def _strip_html(html: str) -> str:
    """Remove HTML tags and collapse whitespace."""
    extractor = _HTMLTextExtractor()
    extractor.feed(html)
    text = extractor.get_text()
    text = re.sub(r" {2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Graph API helpers
# ---------------------------------------------------------------------------

def _extract_email_address(email_obj: Dict) -> str:
    """Extract email address from a Graph emailAddress object."""
    ea = email_obj.get("emailAddress", {})
    return (ea.get("address") or "").strip().lower()


def _extract_recipients(recipients: List[Dict]) -> List[str]:
    """Extract list of email addresses from Graph recipients array."""
    result: list[str] = []
    for r in (recipients or []):
        addr = _extract_email_address(r)
        if addr:
            result.append(addr)
    return result


def _format_recipients(recipients: List[Dict]) -> str:
    """Format recipients into a comma-separated header string."""
    parts: list[str] = []
    for r in (recipients or []):
        ea = r.get("emailAddress", {})
        name = ea.get("name", "")
        addr = ea.get("address", "")
        if name and addr:
            parts.append(f"{name} <{addr}>")
        elif addr:
            parts.append(addr)
    return ", ".join(parts)


def _safe_filename(subject: str, date_str: str) -> str:
    """Build a filesystem-safe filename from subject and date."""
    clean_subject = re.sub(r"[^\w\s-]", "", subject or "no-subject")
    clean_subject = re.sub(r"\s+", "_", clean_subject.strip())[:80]

    date_part = "unknown"
    if date_str:
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            date_part = dt.strftime("%Y-%m-%d")
        except Exception:
            date_part = re.sub(r"[^\w-]", "", date_str[:10])

    return f"outlook_email_{clean_subject}_{date_part}.txt"


# ---------------------------------------------------------------------------
# Graph API: fetch messages with pagination and retry on 401
# ---------------------------------------------------------------------------

async def _fetch_messages(
    access_token: str,
    since_dt: datetime,
    max_results: int,
    connection_id: UUID,
    db: Session,
) -> List[Dict]:
    """
    Fetch messages from Microsoft Graph, handling pagination and 401 retry.

    If the initial request returns 401, refreshes the token once and retries.
    Handles @odata.nextLink pagination when max_results > page size.
    """
    since_iso = since_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    params = {
        "$top": min(max_results, 50),
        "$orderby": "receivedDateTime desc",
        "$filter": f"receivedDateTime ge {since_iso}",
        "$select": GRAPH_SELECT_FIELDS,
    }

    all_messages: list[Dict] = []
    url: Optional[str] = GRAPH_MESSAGES_URL
    token = access_token

    async with httpx.AsyncClient(timeout=30) as client:
        while url and len(all_messages) < max_results:
            headers = {"Authorization": f"Bearer {token}"}

            if url == GRAPH_MESSAGES_URL:
                response = await client.get(url, headers=headers, params=params)
            else:
                # Pagination URL already contains query params
                response = await client.get(url, headers=headers)

            # Handle 401: refresh token and retry once
            if response.status_code == 401 and url == GRAPH_MESSAGES_URL:
                logger.info(
                    "Graph API 401 for connection=%s — refreshing token",
                    connection_id,
                )
                conn = await microsoft_auth_service.refresh_access_token(
                    connection_id, db
                )
                token = microsoft_auth_service._decrypt(conn.access_token)
                headers = {"Authorization": f"Bearer {token}"}
                response = await client.get(url, headers=headers, params=params)

            response.raise_for_status()
            data = response.json()

            messages = data.get("value", [])
            remaining = max_results - len(all_messages)
            all_messages.extend(messages[:remaining])

            # Follow pagination if we need more
            url = data.get("@odata.nextLink") if len(all_messages) < max_results else None

    return all_messages


# ---------------------------------------------------------------------------
# Routing-rule helpers (same as gmail_sync_service)
# ---------------------------------------------------------------------------

def _index_routing_rules(
    rules: List[EmailRoutingRule],
) -> Dict[str, List[EmailRoutingRule]]:
    """Build a lookup dict: lowercase email address → list of matching rules."""
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
    """Try to match an email to a client using routing rules."""
    from_lower = from_addr.lower()

    for rule in rules_by_email.get(from_lower, []):
        if rule.match_type in ("from", "both"):
            return rule.client_id

    for to_addr in to_addrs:
        to_lower = to_addr.lower()
        for rule in rules_by_email.get(to_lower, []):
            if rule.match_type in ("to", "both"):
                return rule.client_id

    return None


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
    Fetch recent emails from Outlook and ingest matched ones as documents.

    Steps:
      1. Get a valid access token
      2. List messages from the last ``since_hours`` hours
      3. For each message: extract, deduplicate, match, ingest
      4. Record results in a SyncLog

    Returns the SyncLog for this sync run.
    """
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
                IntegrationConnection.provider == "microsoft",
                IntegrationConnection.is_active == True,
            )
            .first()
        )
        if not connection:
            raise ValueError(
                f"No active Microsoft connection {connection_id} for user {user_id}"
            )

        # ── Get valid access token ────────────────────────────────────────
        access_token = await microsoft_auth_service.get_valid_token(
            connection_id, db
        )

        # ── Resolve the owner User row ────────────────────────────────────
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

        # ── Query Microsoft Graph ─────────────────────────────────────────
        since_dt = datetime.now(timezone.utc) - timedelta(hours=since_hours)
        messages = await _fetch_messages(
            access_token=access_token,
            since_dt=since_dt,
            max_results=max_results,
            connection_id=connection_id,
            db=db,
        )
        emails_found = len(messages)

        logger.info(
            "Outlook sync: found %d message(s) for connection=%s (since %dh)",
            emails_found,
            connection_id,
            since_hours,
        )

        # ── Process each message ──────────────────────────────────────────
        for msg in messages:
            graph_msg_id = msg.get("id", "")

            try:
                result = await _process_single_message(
                    message=msg,
                    graph_msg_id=graph_msg_id,
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
                    "Outlook sync: error processing message %s: %s",
                    graph_msg_id,
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
            "Outlook sync completed: found=%d ingested=%d skipped=%d",
            emails_found,
            emails_ingested,
            emails_skipped,
        )

    except Exception as exc:
        logger.exception(
            "Outlook sync failed for connection=%s: %s", connection_id, exc
        )
        db.rollback()

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
# Internal: process one Outlook message
# ---------------------------------------------------------------------------

async def _process_single_message(
    message: Dict[str, Any],
    graph_msg_id: str,
    owner: User,
    user_id: str,
    rules_by_email: Dict[str, List[EmailRoutingRule]],
    db: Session,
) -> str:
    """
    Parse and ingest a single Outlook message.

    Returns:
        "ingested" if the email was saved as a document
        "skipped"  if it was a duplicate or unmatched
    """
    # ── Deduplicate ───────────────────────────────────────────────────────
    existing = (
        db.query(Document.id)
        .filter(
            Document.source == "outlook",
            Document.external_id == graph_msg_id,
        )
        .first()
    )
    if existing:
        logger.debug("Outlook sync: skipping duplicate message %s", graph_msg_id)
        return "skipped"

    # ── Extract fields ────────────────────────────────────────────────────
    from_obj = message.get("from", {})
    from_email = _extract_email_address(from_obj)
    from_display = from_obj.get("emailAddress", {}).get("name", from_email)

    to_recipients = message.get("toRecipients", [])
    cc_recipients = message.get("ccRecipients", [])

    to_emails = _extract_recipients(to_recipients)
    cc_emails = _extract_recipients(cc_recipients)

    subject = message.get("subject", "")
    received_dt = message.get("receivedDateTime", "")

    # Extract body — strip HTML if needed
    body_obj = message.get("body", {})
    body_content = body_obj.get("content", "")
    if body_obj.get("contentType", "").lower() == "html":
        body_content = _strip_html(body_content)

    # ── Match to client ───────────────────────────────────────────────────
    all_to_addrs = to_emails + cc_emails
    client_id = _match_client(from_email, all_to_addrs, rules_by_email)
    if client_id is None:
        logger.debug(
            "Outlook sync: no routing rule for message %s (from=%s)",
            graph_msg_id,
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
            "Outlook sync: routing rule points to client %s which user %s does not own",
            client_id,
            user_id,
        )
        return "skipped"

    # ── Build document content ────────────────────────────────────────────
    from_header = f"{from_display} <{from_email}>" if from_display != from_email else from_email
    to_header = _format_recipients(to_recipients)
    cc_header = _format_recipients(cc_recipients)

    content_text = build_email_document_content(
        from_addr=from_header,
        to_addr=to_header,
        cc_addr=cc_header,
        subject=subject,
        date=received_dt,
        body=body_content,
    )
    content_bytes = content_text.encode("utf-8")

    # ── Upload to Supabase Storage ────────────────────────────────────────
    file_id = str(uuid.uuid4())
    filename = _safe_filename(subject, received_dt)

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
            source="outlook",
            external_id=graph_msg_id,
        )
        db.add(document)
        db.commit()
        db.refresh(document)
    except Exception:
        storage_service.delete_file(storage_path)
        db.rollback()
        raise

    logger.info(
        "Outlook sync: ingested message %s → document %s (client=%s, subject=%r)",
        graph_msg_id,
        document.id,
        client_id,
        subject[:60],
    )

    # ── Kick off RAG pipeline in the background ───────────────────────────
    try:
        from app.services.rag_service import process_document

        await process_document(db, document)
    except Exception as rag_exc:
        logger.warning(
            "Outlook sync: RAG processing failed for document %s (non-fatal): %s",
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
    Format email data into a clean text document matching the same format
    as gmail_sync_service.build_email_document_content().

    Output format:
        From: sender@example.com
        To: recipient@example.com
        Cc: cc@example.com
        Subject: Subject line here
        Date: 2024-01-01T10:00:00Z

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

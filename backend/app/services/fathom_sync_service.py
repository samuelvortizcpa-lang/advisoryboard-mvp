"""
Fathom meeting intelligence sync service: connects to the Fathom API to
pull meeting transcripts, or processes manually uploaded Fathom JSON exports.

Flow
----
sync_calls(connection_id, user_id, db)
  ├─ decrypt API key from integration_connections
  ├─ Fathom API: list recent calls
  └─ for each call:
        ├─ fetch transcript + summary + action items
        ├─ deduplicate by external_id (fathom call ID)
        ├─ match to client via email routing rules or title→client name
        ├─ build document from transcript + Fathom AI outputs
        ├─ upload to Supabase Storage
        ├─ create Document row
        └─ kick off RAG pipeline (embed + action items)

Dependencies:
  - httpx  (Fathom REST API)

NOTE: Fathom's API availability may be limited.  All API calls handle
connection/auth errors gracefully and suggest manual upload as a fallback.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import httpx
from cryptography.fernet import Fernet
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.client import Client
from app.models.document import Document
from app.models.email_routing_rule import EmailRoutingRule
from app.models.integration_connection import IntegrationConnection
from app.models.sync_log import SyncLog
from app.models.user import User
from app.services import storage_service

logger = logging.getLogger(__name__)

# Fathom API base URL
FATHOM_API_BASE = "https://api.fathom.video/v1"

# Be gentle with Fathom's API
_RATE_LIMIT_DELAY = 1.0


# ---------------------------------------------------------------------------
# Encryption helpers (same pattern as other auth services)
# ---------------------------------------------------------------------------

def _get_fernet() -> Fernet:
    settings = get_settings()
    key = settings.encryption_key
    if not key:
        raise RuntimeError("ENCRYPTION_KEY must be set in environment variables")
    return Fernet(key.encode())


def _encrypt(plaintext: str) -> str:
    return _get_fernet().encrypt(plaintext.encode()).decode()


def _decrypt(ciphertext: str) -> str:
    return _get_fernet().decrypt(ciphertext.encode()).decode()


# ---------------------------------------------------------------------------
# 1. Test API connection
# ---------------------------------------------------------------------------

async def test_api_connection(api_key: str) -> Tuple[bool, str]:
    """
    Test whether the Fathom API is accessible with the given key.

    Returns (success: bool, message: str).
    - (True, "Connected successfully") if the API responds with 2xx
    - (False, "error description") otherwise
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                f"{FATHOM_API_BASE}/calls",
                headers={"Authorization": f"Bearer {api_key}"},
                params={"limit": 1},
            )

        if response.status_code == 200:
            return True, "Connected successfully"
        if response.status_code in (401, 403):
            return False, "Invalid or expired API key"
        if response.status_code == 404:
            return False, "Fathom API endpoint not found — API may not be available"

        return False, f"Fathom API returned status {response.status_code}"

    except httpx.ConnectError:
        return False, "Could not connect to Fathom API — the API may not be publicly available yet"
    except httpx.TimeoutException:
        return False, "Fathom API request timed out"
    except httpx.RequestError as exc:
        return False, f"Network error: {exc}"


# ---------------------------------------------------------------------------
# 2. Connect (store API key)
# ---------------------------------------------------------------------------

async def handle_api_key_connection(
    user_id: str,
    api_key: str,
    db: Session,
) -> Tuple[IntegrationConnection, bool]:
    """
    Validate and store a Fathom API key.

    Returns (connection, api_available).
    - If the API is reachable and the key is valid, api_available=True.
    - If the API is unreachable but the key is well-formed, we still store
      the connection (for future use / manual import tracking) with api_available=False.

    Raises ValueError if the key is clearly invalid (empty, wrong format).
    """
    if not api_key or not api_key.strip():
        raise ValueError("API key must not be empty")

    api_key = api_key.strip()

    # Test the API connection
    api_ok, api_message = await test_api_connection(api_key)

    # If we got a clear auth rejection, don't store
    if not api_ok and "Invalid or expired" in api_message:
        raise ValueError(api_message)

    # Upsert the connection
    encrypted_key = _encrypt(api_key)

    existing = (
        db.query(IntegrationConnection)
        .filter(
            IntegrationConnection.user_id == user_id,
            IntegrationConnection.provider == "fathom",
        )
        .first()
    )

    if existing:
        existing.access_token = encrypted_key
        existing.refresh_token = None
        existing.token_expires_at = None
        existing.is_active = True
        db.commit()
        db.refresh(existing)
        logger.info(
            "Updated Fathom connection for user=%s (api_available=%s)",
            user_id, api_ok,
        )
        return existing, api_ok

    connection = IntegrationConnection(
        id=uuid.uuid4(),
        user_id=user_id,
        provider="fathom",
        provider_email=None,
        access_token=encrypted_key,
        refresh_token=None,
        token_expires_at=None,
        is_active=True,
    )
    db.add(connection)
    db.commit()
    db.refresh(connection)
    logger.info(
        "Created Fathom connection for user=%s (api_available=%s)",
        user_id, api_ok,
    )
    return connection, api_ok


# ---------------------------------------------------------------------------
# 3. Build document content
# ---------------------------------------------------------------------------

def build_fathom_document_content(
    call_data: Dict[str, Any],
    transcript_text: str,
) -> str:
    """
    Format Fathom call data and transcript into a clean document.

    Output format:
        Fathom Meeting: {title}
        Date: {date}
        Duration: {duration}
        Participants: {attendees}
        Source: Fathom (auto-synced)

        --- Summary (by Fathom) ---
        {summary}

        --- Action Items (by Fathom) ---
        {action_items}

        --- Full Transcript ---
        {transcript}
    """
    parts: list[str] = []

    # Header
    header: list[str] = []
    title = (
        call_data.get("title")
        or call_data.get("name")
        or call_data.get("meeting_title")
        or "Untitled Meeting"
    )
    header.append(f"Fathom Meeting: {title}")

    date_val = (
        call_data.get("date")
        or call_data.get("started_at")
        or call_data.get("start_time")
        or call_data.get("created_at")
    )
    if date_val:
        header.append(f"Date: {date_val}")

    duration = call_data.get("duration") or call_data.get("duration_seconds")
    if duration:
        # Convert seconds to human-readable if numeric
        if isinstance(duration, (int, float)) and duration > 0:
            mins = int(duration) // 60
            secs = int(duration) % 60
            header.append(f"Duration: {mins}m {secs}s")
        else:
            header.append(f"Duration: {duration}")

    attendees = (
        call_data.get("attendees")
        or call_data.get("participants")
        or call_data.get("speakers")
        or []
    )
    if isinstance(attendees, list) and attendees:
        names: list[str] = []
        for a in attendees:
            if isinstance(a, dict):
                name = a.get("name") or a.get("full_name") or a.get("email") or ""
                if name:
                    names.append(str(name))
            elif isinstance(a, str) and a:
                names.append(a)
        if names:
            header.append(f"Participants: {', '.join(names)}")

    header.append("Source: Fathom (auto-synced)")
    parts.append("\n".join(header))

    # Summary
    summary = (
        call_data.get("summary")
        or call_data.get("overview")
        or call_data.get("meeting_summary")
    )
    if isinstance(summary, str) and summary.strip():
        parts.append(f"--- Summary (by Fathom) ---\n{summary.strip()}")

    # Action items
    action_items = (
        call_data.get("action_items")
        or call_data.get("tasks")
        or call_data.get("follow_ups")
        or call_data.get("next_steps")
    )
    if action_items:
        ai_lines: list[str] = []
        if isinstance(action_items, list):
            for item in action_items:
                if isinstance(item, dict):
                    owner = (
                        item.get("owner")
                        or item.get("assignee")
                        or item.get("assigned_to")
                        or ""
                    )
                    desc = (
                        item.get("description")
                        or item.get("text")
                        or item.get("title")
                        or item.get("task")
                        or ""
                    )
                    desc = str(desc).strip()
                    if desc:
                        ai_lines.append(f"- {owner}: {desc}" if owner else f"- {desc}")
                elif isinstance(item, str) and item.strip():
                    ai_lines.append(f"- {item.strip()}")
        elif isinstance(action_items, str) and action_items.strip():
            ai_lines.append(action_items.strip())
        if ai_lines:
            parts.append("--- Action Items (by Fathom) ---\n" + "\n".join(ai_lines))

    # Transcript
    if transcript_text and transcript_text.strip():
        parts.append(f"--- Full Transcript ---\n{transcript_text.strip()}")

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# 4. Parse a manually uploaded Fathom JSON file
# ---------------------------------------------------------------------------

def parse_fathom_json_upload(file_content: bytes | str) -> Dict[str, Any]:
    """
    Parse a Fathom JSON transcript export and return structured data.

    Reuses the same field-name variants as the existing _extract_fathom_json
    parser in text_extraction.py, but returns structured data instead of
    a flat text string.

    Returns:
        {
            "title": str,
            "date": str | None,
            "duration": str | None,
            "participants": list[str],
            "summary": str | None,
            "action_items": list[dict],  # [{owner, description}]
            "transcript_text": str,
            "raw_data": dict,            # original parsed JSON
        }
    """
    if isinstance(file_content, bytes):
        file_content = file_content.decode("utf-8", errors="replace")

    try:
        data = json.loads(file_content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(
            f"Expected a JSON object at the top level, got {type(data).__name__}"
        )

    # Title
    title = (
        data.get("title")
        or data.get("name")
        or data.get("meeting_title")
        or data.get("meeting_name")
        or "Untitled Meeting"
    )

    # Date
    date_val = (
        data.get("date")
        or data.get("meeting_date")
        or data.get("call_date")
        or data.get("start_time")
        or data.get("created_at")
    )

    # Duration
    duration = data.get("duration") or data.get("duration_seconds")

    # Participants
    attendees_raw = (
        data.get("attendees")
        or data.get("participants")
        or data.get("speakers")
        or []
    )
    participants: list[str] = []
    if isinstance(attendees_raw, list):
        for a in attendees_raw:
            if isinstance(a, dict):
                name = a.get("name") or a.get("full_name") or a.get("display_name") or ""
                if name:
                    participants.append(str(name))
            elif isinstance(a, str) and a:
                participants.append(a)

    # Summary
    summary = (
        data.get("summary")
        or data.get("overview")
        or data.get("meeting_summary")
        or data.get("description")
    )
    if isinstance(summary, str):
        summary = summary.strip() or None
    else:
        summary = None

    # Action items
    action_items_raw = (
        data.get("action_items")
        or data.get("tasks")
        or data.get("follow_ups")
        or data.get("next_steps")
        or data.get("todos")
    )
    action_items: list[dict] = []
    if isinstance(action_items_raw, list):
        for item in action_items_raw:
            if isinstance(item, dict):
                owner = (
                    item.get("owner")
                    or item.get("assignee")
                    or item.get("assigned_to")
                    or ""
                )
                desc = (
                    item.get("description")
                    or item.get("text")
                    or item.get("title")
                    or item.get("task")
                    or ""
                )
                if str(desc).strip():
                    action_items.append({
                        "owner": str(owner).strip(),
                        "description": str(desc).strip(),
                    })
            elif isinstance(item, str) and item.strip():
                action_items.append({"owner": "", "description": item.strip()})

    # Transcript → flat text
    transcript = (
        data.get("transcript")
        or data.get("transcript_entries")
        or data.get("entries")
        or data.get("utterances")
        or data.get("segments")
    )
    transcript_lines: list[str] = []
    if isinstance(transcript, list):
        for entry in transcript:
            if isinstance(entry, dict):
                speaker = (
                    entry.get("speaker")
                    or entry.get("speaker_name")
                    or entry.get("name")
                    or ""
                )
                text = (
                    entry.get("text")
                    or entry.get("content")
                    or entry.get("transcript")
                    or ""
                )
                timestamp = (
                    entry.get("start")
                    or entry.get("start_time")
                    or entry.get("timestamp")
                    or ""
                )
                text = str(text).strip()
                if not text:
                    continue
                if speaker:
                    prefix = f"[{timestamp}] {speaker}" if timestamp else str(speaker)
                    transcript_lines.append(f"{prefix}: {text}")
                else:
                    transcript_lines.append(text)
            elif isinstance(entry, str) and entry.strip():
                transcript_lines.append(entry.strip())
    elif isinstance(transcript, str) and transcript.strip():
        transcript_lines.append(transcript.strip())

    transcript_text = "\n".join(transcript_lines)

    return {
        "title": title,
        "date": str(date_val) if date_val else None,
        "duration": str(duration) if duration else None,
        "participants": participants,
        "summary": summary,
        "action_items": action_items,
        "transcript_text": transcript_text,
        "raw_data": data,
    }


# ---------------------------------------------------------------------------
# 5. Client matching
# ---------------------------------------------------------------------------

def _extract_attendee_emails(call_data: Dict[str, Any]) -> list[str]:
    """Extract email addresses from call attendees/participants."""
    attendees = (
        call_data.get("attendees")
        or call_data.get("participants")
        or call_data.get("speakers")
        or []
    )
    emails: list[str] = []
    if isinstance(attendees, list):
        for a in attendees:
            if isinstance(a, dict):
                email = a.get("email") or a.get("email_address") or ""
                if email and "@" in email:
                    emails.append(email.strip().lower())
            elif isinstance(a, str) and "@" in a:
                emails.append(a.strip().lower())
    return emails


def _match_call_to_client(
    call_data: Dict[str, Any],
    user_id: str,
    owner_id: uuid.UUID,
    db: Session,
) -> Optional[UUID]:
    """
    Try to match a Fathom call to a client.

    Priority:
      1. Attendee emails against email routing rules
      2. Call title against client names (case-insensitive substring match)

    Returns client_id or None.
    """
    # ── Pre-load routing rules ────────────────────────────────────────────
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

    # ── Priority 1: attendee emails vs routing rules ──────────────────────
    attendee_emails = _extract_attendee_emails(call_data)
    for email in attendee_emails:
        rule = rules_by_email.get(email)
        if rule:
            return rule.client_id

    # ── Priority 2: call title vs client names ────────────────────────────
    title = (
        call_data.get("title")
        or call_data.get("name")
        or call_data.get("meeting_title")
        or ""
    )
    title_lower = title.strip().lower()

    if title_lower:
        clients = (
            db.query(Client)
            .filter(Client.owner_id == owner_id)
            .all()
        )
        for c in clients:
            if c.name and c.name.strip().lower() in title_lower:
                return c.id

    return None


# ---------------------------------------------------------------------------
# 6. Core sync function
# ---------------------------------------------------------------------------

def _safe_filename(title: str, date_val: str | None) -> str:
    """Build a filesystem-safe filename from call title and date."""
    clean_title = re.sub(r"[^\w\s-]", "", title or "meeting")
    clean_title = re.sub(r"\s+", "_", clean_title.strip())[:80]

    date_part = "unknown"
    if date_val:
        date_part = re.sub(r"[^\w-]", "", str(date_val)[:10])

    return f"fathom_meeting_{clean_title}_{date_part}.txt"


async def sync_calls(
    connection_id: UUID,
    user_id: str,
    db: Session,
    sync_type: str = "manual",
    max_results: int = 30,
    since_hours: int = 168,  # 7 days
) -> SyncLog:
    """
    Fetch recent calls from Fathom API and ingest them as documents.

    If the API is unreachable, the sync will fail with a helpful message
    suggesting the user fall back to manual upload.

    Returns the SyncLog for this sync run.
    """
    import asyncio

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
        # ── Validate connection ───────────────────────────────────────────
        connection = (
            db.query(IntegrationConnection)
            .filter(
                IntegrationConnection.id == connection_id,
                IntegrationConnection.user_id == user_id,
                IntegrationConnection.provider == "fathom",
                IntegrationConnection.is_active == True,
            )
            .first()
        )
        if not connection:
            raise ValueError(
                f"No active Fathom connection {connection_id} for user {user_id}"
            )

        api_key = _decrypt(connection.access_token)

        # ── Resolve the owner User row ────────────────────────────────────
        owner = db.query(User).filter(User.clerk_id == user_id).first()
        if not owner:
            raise ValueError(f"User with clerk_id={user_id} not found")

        # ── Fetch calls from Fathom API ───────────────────────────────────
        since_dt = datetime.now(timezone.utc) - timedelta(hours=since_hours)

        calls = await _fetch_calls(
            api_key=api_key,
            since_dt=since_dt,
            max_results=max_results,
        )
        items_found = len(calls)

        logger.info(
            "Fathom sync: found %d call(s) for connection=%s (since %dh)",
            items_found, connection_id, since_hours,
        )

        # ── Process each call ─────────────────────────────────────────────
        for call in calls:
            call_id = call.get("id") or call.get("call_id") or ""
            if not call_id:
                items_skipped += 1
                continue

            try:
                result = await _process_single_call(
                    call_data=call,
                    call_id=str(call_id),
                    api_key=api_key,
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
                    "Fathom sync: error processing call %s: %s",
                    call_id, exc,
                )
                items_skipped += 1

            # Rate limit between calls
            await asyncio.sleep(_RATE_LIMIT_DELAY)

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
            "Fathom sync completed: found=%d ingested=%d skipped=%d",
            items_found, items_ingested, items_skipped,
        )

    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        logger.warning(
            "Fathom API unreachable during sync for connection=%s: %s",
            connection_id, exc,
        )
        db.rollback()
        sync_log = db.query(SyncLog).filter(SyncLog.id == sync_log.id).first()
        if sync_log:
            sync_log.status = "failed"
            sync_log.emails_found = items_found
            sync_log.emails_ingested = items_ingested
            sync_log.emails_skipped = items_skipped
            sync_log.error_message = (
                "Could not reach Fathom API. "
                "Use the manual import feature to upload Fathom JSON transcripts instead."
            )
            sync_log.completed_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(sync_log)

    except Exception as exc:
        logger.exception(
            "Fathom sync failed for connection=%s: %s", connection_id, exc,
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
# Fathom API helpers
# ---------------------------------------------------------------------------

async def _fetch_calls(
    api_key: str,
    since_dt: datetime,
    max_results: int,
) -> List[Dict]:
    """
    Fetch recent calls from the Fathom API.

    Handles pagination if supported, and gracefully errors if the API
    is unreachable.
    """
    all_calls: list[Dict] = []

    async with httpx.AsyncClient(timeout=30) as client:
        # Try to list calls with date filter
        params: Dict[str, Any] = {"limit": min(max_results, 50)}

        # Fathom may support date filtering via different param names
        since_iso = since_dt.isoformat()
        params["after"] = since_iso

        response = await client.get(
            f"{FATHOM_API_BASE}/calls",
            headers={"Authorization": f"Bearer {api_key}"},
            params=params,
        )

        if response.status_code in (401, 403):
            raise ValueError(
                "Fathom API key is invalid or expired. "
                "Please reconnect or use manual import."
            )
        if response.status_code == 404:
            raise ValueError(
                "Fathom API endpoint not found. "
                "The API may not be available — use manual import instead."
            )

        response.raise_for_status()
        data = response.json()

        # The response might be a list directly or an object with a data/calls key
        if isinstance(data, list):
            all_calls = data[:max_results]
        elif isinstance(data, dict):
            calls = (
                data.get("calls")
                or data.get("data")
                or data.get("results")
                or data.get("items")
                or []
            )
            all_calls = calls[:max_results]

            # Handle pagination
            next_cursor = data.get("next_cursor") or data.get("next")
            while next_cursor and len(all_calls) < max_results:
                params["cursor"] = next_cursor
                response = await client.get(
                    f"{FATHOM_API_BASE}/calls",
                    headers={"Authorization": f"Bearer {api_key}"},
                    params=params,
                )
                response.raise_for_status()
                page_data = response.json()

                if isinstance(page_data, dict):
                    page_calls = (
                        page_data.get("calls")
                        or page_data.get("data")
                        or page_data.get("results")
                        or page_data.get("items")
                        or []
                    )
                    remaining = max_results - len(all_calls)
                    all_calls.extend(page_calls[:remaining])
                    next_cursor = page_data.get("next_cursor") or page_data.get("next")
                else:
                    break

    return all_calls


async def _fetch_call_transcript(
    call_id: str,
    api_key: str,
) -> Optional[str]:
    """
    Fetch the transcript for a specific call.

    Returns the transcript as text, or None if not available.
    """
    async with httpx.AsyncClient(timeout=30) as client:
        # Try the transcript endpoint
        response = await client.get(
            f"{FATHOM_API_BASE}/calls/{call_id}/transcript",
            headers={"Authorization": f"Bearer {api_key}"},
        )

        if response.status_code == 404:
            # Transcript not available yet or endpoint doesn't exist
            return None
        if response.status_code in (401, 403):
            logger.warning("Fathom API auth failed fetching transcript for call %s", call_id)
            return None

        response.raise_for_status()
        data = response.json()

        # Parse transcript from response
        if isinstance(data, str):
            return data

        if isinstance(data, dict):
            # Could be structured transcript data
            transcript = (
                data.get("transcript")
                or data.get("text")
                or data.get("content")
            )
            if isinstance(transcript, str):
                return transcript
            if isinstance(transcript, list):
                lines: list[str] = []
                for entry in transcript:
                    if isinstance(entry, dict):
                        speaker = entry.get("speaker") or entry.get("name") or ""
                        text = entry.get("text") or entry.get("content") or ""
                        timestamp = entry.get("start") or entry.get("timestamp") or ""
                        text = str(text).strip()
                        if not text:
                            continue
                        if speaker:
                            prefix = f"[{timestamp}] {speaker}" if timestamp else str(speaker)
                            lines.append(f"{prefix}: {text}")
                        else:
                            lines.append(text)
                    elif isinstance(entry, str) and entry.strip():
                        lines.append(entry.strip())
                return "\n".join(lines)

        if isinstance(data, list):
            lines = []
            for entry in data:
                if isinstance(entry, dict):
                    speaker = entry.get("speaker") or entry.get("name") or ""
                    text = entry.get("text") or entry.get("content") or ""
                    timestamp = entry.get("start") or entry.get("timestamp") or ""
                    text = str(text).strip()
                    if not text:
                        continue
                    if speaker:
                        prefix = f"[{timestamp}] {speaker}" if timestamp else str(speaker)
                        lines.append(f"{prefix}: {text}")
                    else:
                        lines.append(text)
                elif isinstance(entry, str) and entry.strip():
                    lines.append(entry.strip())
            return "\n".join(lines) if lines else None

    return None


async def _fetch_call_details(
    call_id: str,
    api_key: str,
) -> Optional[Dict]:
    """Fetch full call details (summary, action items, attendees) from Fathom."""
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            f"{FATHOM_API_BASE}/calls/{call_id}",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        if response.status_code in (404, 401, 403):
            return None
        response.raise_for_status()
        return response.json()


# ---------------------------------------------------------------------------
# Process a single call
# ---------------------------------------------------------------------------

async def _process_single_call(
    call_data: Dict[str, Any],
    call_id: str,
    api_key: str,
    owner: User,
    user_id: str,
    db: Session,
) -> str:
    """
    Fetch transcript, match to client, and ingest a single Fathom call.

    Returns "ingested" or "skipped".
    """
    title = (
        call_data.get("title")
        or call_data.get("name")
        or call_data.get("meeting_title")
        or "Untitled Meeting"
    )

    # ── Fetch additional details if available ──────────────────────────────
    details = await _fetch_call_details(call_id, api_key)
    if details:
        # Merge details into call_data (details may have summary, action_items, etc.)
        for key in ("summary", "action_items", "tasks", "attendees", "participants",
                     "duration", "duration_seconds", "overview"):
            if key in details and key not in call_data:
                call_data[key] = details[key]

    # ── Fetch transcript ──────────────────────────────────────────────────
    transcript_text = await _fetch_call_transcript(call_id, api_key)

    if not transcript_text:
        # Try to build transcript from call_data itself (some APIs inline it)
        transcript_entries = (
            call_data.get("transcript")
            or call_data.get("transcript_entries")
            or call_data.get("utterances")
        )
        if isinstance(transcript_entries, list):
            lines: list[str] = []
            for entry in transcript_entries:
                if isinstance(entry, dict):
                    speaker = entry.get("speaker") or entry.get("name") or ""
                    text = entry.get("text") or entry.get("content") or ""
                    text = str(text).strip()
                    if text:
                        lines.append(f"{speaker}: {text}" if speaker else text)
            transcript_text = "\n".join(lines) if lines else None

    if not transcript_text:
        logger.debug("Fathom sync: no transcript for call %s (%s)", call_id, title)
        return "skipped"

    # ── Match to client ───────────────────────────────────────────────────
    client_id = _match_call_to_client(
        call_data=call_data,
        user_id=user_id,
        owner_id=owner.id,
        db=db,
    )
    if client_id is None:
        logger.debug(
            "Fathom sync: no client match for call %s (title=%r)",
            call_id, title,
        )
        return "skipped"

    # Verify client ownership
    client = (
        db.query(Client)
        .filter(Client.id == client_id, Client.owner_id == owner.id)
        .first()
    )
    if not client:
        return "skipped"

    # ── Build document content ────────────────────────────────────────────
    content_text = build_fathom_document_content(call_data, transcript_text)
    content_bytes = content_text.encode("utf-8")

    date_val = (
        call_data.get("date")
        or call_data.get("started_at")
        or call_data.get("start_time")
        or call_data.get("created_at")
    )
    filename = _safe_filename(title, str(date_val) if date_val else None)

    # ── Check for existing document (update vs create) ────────────────────
    existing_doc = (
        db.query(Document)
        .filter(
            Document.source == "fathom",
            Document.external_id == call_id,
        )
        .first()
    )

    if existing_doc:
        old_path = existing_doc.file_path
        file_id = str(uuid.uuid4())

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

        try:
            storage_service.delete_file(old_path)
        except Exception:
            logger.warning("Fathom sync: failed to delete old file %s", old_path, exc_info=True)

        logger.info(
            "Fathom sync: updated call %s → document %s (client=%s, title=%r)",
            call_id, existing_doc.id, client_id, title[:60],
        )

        try:
            from app.services.rag_service import process_document
            await process_document(db, existing_doc)
        except Exception as rag_exc:
            logger.warning(
                "Fathom sync: RAG re-processing failed for document %s: %s",
                existing_doc.id, rag_exc,
            )

        return "ingested"

    # ── Upload new document ───────────────────────────────────────────────
    file_id = str(uuid.uuid4())
    storage_path = storage_service.upload_file(
        user_id=str(owner.id),
        client_id=str(client_id),
        file_id=file_id,
        filename=filename,
        file_bytes=content_bytes,
        content_type="text/plain",
    )

    try:
        document = Document(
            client_id=client_id,
            uploaded_by=owner.id,
            filename=filename,
            file_path=storage_path,
            file_type="txt",
            file_size=len(content_bytes),
            source="fathom",
            external_id=call_id,
        )
        db.add(document)
        db.commit()
        db.refresh(document)
    except Exception:
        storage_service.delete_file(storage_path)
        db.rollback()
        raise

    logger.info(
        "Fathom sync: ingested call %s → document %s (client=%s, title=%r)",
        call_id, document.id, client_id, title[:60],
    )

    try:
        from app.services.rag_service import process_document
        await process_document(db, document)
    except Exception as rag_exc:
        logger.warning(
            "Fathom sync: RAG processing failed for document %s: %s",
            document.id, rag_exc,
        )

    return "ingested"


# ---------------------------------------------------------------------------
# 7. Sync history
# ---------------------------------------------------------------------------

def get_sync_history(
    user_id: str,
    connection_id: UUID,
    db: Session,
    limit: int = 20,
) -> List[SyncLog]:
    """
    Return recent sync logs for a Fathom connection, most recent first.
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

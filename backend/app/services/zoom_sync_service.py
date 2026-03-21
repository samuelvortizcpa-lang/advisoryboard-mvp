"""
Zoom recording sync service: fetches meeting recordings from a connected
Zoom account and ingests transcripts into AdvisoryBoard as documents.

Flow
----
sync_recordings(connection_id, user_id, db)
  ├─ get_valid_token()
  ├─ Zoom API: list recordings (last N days)
  └─ for each meeting:
        ├─ deduplicate by external_id (zoom meeting UUID)
        ├─ download transcript (VTT) or audio (M4A/MP4 → Whisper)
        ├─ match meeting → client via topic or participant emails
        ├─ upload to Supabase Storage
        ├─ create Document row
        └─ kick off RAG pipeline (embed + action items)

Dependencies:
  - httpx  (Zoom REST API)
  - audio_transcriber  (Whisper for fallback when no VTT transcript)
"""

from __future__ import annotations

import logging
import re
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
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
from app.services import storage_service, zoom_auth_service

logger = logging.getLogger(__name__)

# Zoom API endpoints
ZOOM_RECORDINGS_URL = "https://api.zoom.us/v2/users/me/recordings"


# ---------------------------------------------------------------------------
# VTT parsing
# ---------------------------------------------------------------------------

def _vtt_to_plain_text(vtt_content: str) -> str:
    """
    Convert WebVTT transcript content to plain text.

    Strips the WEBVTT header, cue identifiers, timestamp lines
    (e.g. "00:00:01.000 --> 00:00:05.000"), and NOTE blocks.
    Keeps only the spoken text lines.
    """
    lines: list[str] = []
    in_note = False

    for line in vtt_content.splitlines():
        stripped = line.strip()

        # Skip WEBVTT header and empty lines
        if stripped.startswith("WEBVTT") or stripped.startswith("Kind:") or stripped.startswith("Language:"):
            continue

        # Skip NOTE blocks
        if stripped.startswith("NOTE"):
            in_note = True
            continue
        if in_note:
            if stripped == "":
                in_note = False
            continue

        # Skip timestamp lines  (00:00:01.000 --> 00:00:05.000)
        if re.match(r"\d{2}:\d{2}:\d{2}\.\d{3}\s*-->", stripped):
            continue

        # Skip numeric cue identifiers
        if stripped.isdigit():
            continue

        # Skip empty lines
        if not stripped:
            continue

        # Strip inline VTT tags like <v Speaker Name>
        cleaned = re.sub(r"<[^>]+>", "", stripped)
        if cleaned.strip():
            lines.append(cleaned.strip())

    # Deduplicate consecutive identical lines (VTT often repeats)
    deduped: list[str] = []
    for line in lines:
        if not deduped or line != deduped[-1]:
            deduped.append(line)

    return "\n".join(deduped)


# ---------------------------------------------------------------------------
# Zoom API helpers
# ---------------------------------------------------------------------------

async def _fetch_recordings(
    access_token: str,
    from_date: str,
    to_date: str,
    max_results: int,
    connection_id: UUID,
    db: Session,
) -> List[Dict]:
    """
    Fetch meeting recordings from Zoom API with 401 retry.

    Returns a list of meeting objects from the API response.
    """
    params = {
        "from": from_date,
        "to": to_date,
        "page_size": min(max_results, 30),
    }

    all_meetings: list[Dict] = []
    next_page_token: Optional[str] = None
    token = access_token

    async with httpx.AsyncClient(timeout=30) as client:
        while len(all_meetings) < max_results:
            if next_page_token:
                params["next_page_token"] = next_page_token

            headers = {"Authorization": f"Bearer {token}"}
            response = await client.get(
                ZOOM_RECORDINGS_URL, headers=headers, params=params,
            )

            # Handle 401: refresh token and retry once
            if response.status_code == 401 and not next_page_token:
                logger.info(
                    "Zoom API 401 for connection=%s — refreshing token",
                    connection_id,
                )
                conn = await zoom_auth_service.refresh_access_token(
                    connection_id, db
                )
                token = zoom_auth_service._decrypt(conn.access_token)
                headers = {"Authorization": f"Bearer {token}"}
                response = await client.get(
                    ZOOM_RECORDINGS_URL, headers=headers, params=params,
                )

            response.raise_for_status()
            data = response.json()

            meetings = data.get("meetings", [])
            remaining = max_results - len(all_meetings)
            all_meetings.extend(meetings[:remaining])

            # Check for more pages
            next_page_token = data.get("next_page_token", "")
            if not next_page_token or len(all_meetings) >= max_results:
                break

    return all_meetings


async def _download_zoom_file(download_url: str, access_token: str) -> bytes:
    """
    Download a file from Zoom.  Zoom download URLs require the access_token
    as a query param and follow redirects.
    """
    url = f"{download_url}?access_token={access_token}"
    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.content


# ---------------------------------------------------------------------------
# Transcript extraction
# ---------------------------------------------------------------------------

async def download_transcript_vtt(
    download_url: str,
    access_token: str,
) -> str:
    """
    Download a VTT transcript file from Zoom and convert to plain text.

    Returns the plain text transcript.
    """
    vtt_bytes = await _download_zoom_file(download_url, access_token)
    vtt_text = vtt_bytes.decode("utf-8", errors="replace")
    return _vtt_to_plain_text(vtt_text)


async def download_and_transcribe_audio(
    download_url: str,
    access_token: str,
    file_type_ext: str,
) -> str:
    """
    Download an audio/video file from Zoom, transcribe with Whisper,
    and return the transcript text.
    """
    from app.services.audio_transcriber import transcribe_audio

    audio_bytes = await _download_zoom_file(download_url, access_token)

    with tempfile.NamedTemporaryFile(
        suffix=f".{file_type_ext}", delete=False
    ) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        transcript = transcribe_audio(tmp_path, file_type_ext)
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    return transcript


# ---------------------------------------------------------------------------
# Client matching
# ---------------------------------------------------------------------------

def match_meeting_to_client(
    meeting_topic: str,
    participant_emails: List[str],
    user_id: str,
    owner_id: uuid.UUID,
    db: Session,
    meeting_id: str = "",
) -> Optional[UUID]:
    """
    Try to match a Zoom meeting to a client.

    Priority (highest first):
      1. Explicit zoom_meeting_rules (topic_contains, participant_email,
         meeting_id_prefix)
      2. Email routing rules (participant emails)
      3. Fuzzy client name match (client name appears in topic)

    Returns client_id or None.
    """
    from app.models.zoom_meeting_rule import ZoomMeetingRule

    topic_lower = (meeting_topic or "").lower()
    meeting_id_str = str(meeting_id or "")

    # ── Priority 1: explicit zoom_meeting_rules ───────────────────────────
    zoom_rules = (
        db.query(ZoomMeetingRule)
        .filter(
            ZoomMeetingRule.user_id == user_id,
            ZoomMeetingRule.is_active == True,
        )
        .all()
    )

    for rule in zoom_rules:
        val_lower = rule.match_value.strip().lower()

        if rule.match_field == "topic_contains" and topic_lower:
            if val_lower in topic_lower:
                return rule.client_id

        elif rule.match_field == "participant_email" and participant_emails:
            for email in participant_emails:
                if email.strip().lower() == val_lower:
                    return rule.client_id

        elif rule.match_field == "meeting_id_prefix" and meeting_id_str:
            if meeting_id_str.startswith(rule.match_value.strip()):
                return rule.client_id

    # ── Priority 2: email routing rules ───────────────────────────────────
    if participant_emails:
        email_rules = (
            db.query(EmailRoutingRule)
            .filter(
                EmailRoutingRule.user_id == user_id,
                EmailRoutingRule.is_active == True,
            )
            .all()
        )
        rules_by_email: dict[str, UUID] = {}
        for rule in email_rules:
            rules_by_email[rule.email_address.strip().lower()] = rule.client_id

        for email in participant_emails:
            email_lower = email.strip().lower()
            if email_lower in rules_by_email:
                return rules_by_email[email_lower]

    # ── Priority 3: fuzzy client name match ───────────────────────────────
    if topic_lower:
        clients = (
            db.query(Client)
            .filter(Client.owner_id == owner_id)
            .all()
        )
        for client in clients:
            if client.name and client.name.lower() in topic_lower:
                return client.id

    return None


# ---------------------------------------------------------------------------
# Document content formatting
# ---------------------------------------------------------------------------

def _safe_filename(topic: str, date_str: str) -> str:
    """Build a filesystem-safe filename from meeting topic and date."""
    clean_topic = re.sub(r"[^\w\s-]", "", topic or "meeting")
    clean_topic = re.sub(r"\s+", "_", clean_topic.strip())[:80]

    date_part = "unknown"
    if date_str:
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            date_part = dt.strftime("%Y-%m-%d")
        except Exception:
            date_part = re.sub(r"[^\w-]", "", date_str[:10])

    return f"zoom_meeting_{clean_topic}_{date_part}.txt"


def build_meeting_document_content(
    meeting_data: Dict[str, Any],
    transcript_text: str,
) -> str:
    """
    Format meeting data and transcript into a clean text document.

    Output format:
        Meeting: Topic Here
        Date: 2024-01-15T10:00:00Z
        Duration: 45 minutes
        Participants: alice@example.com, bob@example.com
        Source: Zoom Recording

        --- Transcript ---

        ...transcript text...
    """
    topic = meeting_data.get("topic", "Untitled Meeting")
    start_time = meeting_data.get("start_time", "")
    duration = meeting_data.get("duration", 0)
    participants = meeting_data.get("participant_emails", [])

    header_lines: list[str] = []
    header_lines.append(f"Meeting: {topic}")
    if start_time:
        header_lines.append(f"Date: {start_time}")
    if duration:
        header_lines.append(f"Duration: {duration} minutes")
    if participants:
        header_lines.append(f"Participants: {', '.join(participants)}")
    header_lines.append("Source: Zoom Recording")

    parts = ["\n".join(header_lines)]

    if transcript_text:
        parts.append(f"--- Transcript ---\n\n{transcript_text}")

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# 1. Core sync function
# ---------------------------------------------------------------------------

async def sync_recordings(
    connection_id: UUID,
    user_id: str,
    db: Session,
    sync_type: str = "manual",
    days_back: int = 7,
    max_results: int = 30,
) -> SyncLog:
    """
    Fetch recent recordings from Zoom and ingest transcripts as documents.

    Steps:
      1. Get a valid access token
      2. List recordings from the last ``days_back`` days
      3. For each meeting: extract transcript, deduplicate, match, ingest
      4. Record results in a SyncLog

    Returns the SyncLog for this sync run.
    """
    # Reuse sync_log table: emails_found → recordings found, etc.
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
                IntegrationConnection.provider == "zoom",
                IntegrationConnection.is_active == True,
            )
            .first()
        )
        if not connection:
            raise ValueError(
                f"No active Zoom connection {connection_id} for user {user_id}"
            )

        # ── Get valid access token ────────────────────────────────────────
        access_token = await zoom_auth_service.get_valid_token(
            connection_id, db
        )

        # ── Resolve the owner User row ────────────────────────────────────
        owner = db.query(User).filter(User.clerk_id == user_id).first()
        if not owner:
            raise ValueError(f"User with clerk_id={user_id} not found")

        # ── Query Zoom recordings ─────────────────────────────────────────
        now = datetime.now(timezone.utc)
        from_date = (now - timedelta(days=days_back)).strftime("%Y-%m-%d")
        to_date = now.strftime("%Y-%m-%d")

        meetings = await _fetch_recordings(
            access_token=access_token,
            from_date=from_date,
            to_date=to_date,
            max_results=max_results,
            connection_id=connection_id,
            db=db,
        )
        items_found = len(meetings)

        logger.info(
            "Zoom sync: found %d meeting(s) for connection=%s (last %d days)",
            items_found,
            connection_id,
            days_back,
        )

        # ── Process each meeting ──────────────────────────────────────────
        for meeting in meetings:
            meeting_uuid = meeting.get("uuid", "")

            try:
                result = await _process_single_meeting(
                    meeting=meeting,
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
                    "Zoom sync: error processing meeting %s: %s",
                    meeting_uuid,
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
            "Zoom sync completed: found=%d ingested=%d skipped=%d",
            items_found,
            items_ingested,
            items_skipped,
        )

    except Exception as exc:
        logger.exception(
            "Zoom sync failed for connection=%s: %s", connection_id, exc
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
# Internal: process one Zoom meeting
# ---------------------------------------------------------------------------

async def _process_single_meeting(
    meeting: Dict[str, Any],
    access_token: str,
    owner: User,
    user_id: str,
    db: Session,
) -> str:
    """
    Extract transcript, match to client, and ingest a single meeting.

    Returns:
        "ingested" if the meeting was saved as a document
        "skipped"  if it was a duplicate, had no transcript, or was unmatched
    """
    meeting_uuid = meeting.get("uuid", "")
    meeting_id = str(meeting.get("id", meeting_uuid))
    topic = meeting.get("topic", "Untitled Meeting")
    start_time = meeting.get("start_time", "")
    duration = meeting.get("duration", 0)
    recording_files = meeting.get("recording_files", [])

    if not recording_files:
        logger.debug("Zoom sync: no recordings for meeting %s", meeting_uuid)
        return "skipped"

    # ── Deduplicate ───────────────────────────────────────────────────────
    # Use the meeting UUID as external_id for deduplication
    existing = (
        db.query(Document.id)
        .filter(
            Document.source == "zoom",
            Document.external_id == meeting_uuid,
        )
        .first()
    )
    if existing:
        logger.debug("Zoom sync: skipping duplicate meeting %s", meeting_uuid)
        return "skipped"

    # ── Extract transcript ────────────────────────────────────────────────
    transcript_text = ""

    # First, look for VTT transcript files
    transcript_files = [
        f for f in recording_files if f.get("file_type") == "TRANSCRIPT"
    ]
    if transcript_files:
        try:
            tf = transcript_files[0]
            transcript_text = await download_transcript_vtt(
                tf["download_url"], access_token
            )
        except Exception as exc:
            logger.warning(
                "Zoom sync: failed to download VTT for meeting %s: %s",
                meeting_uuid,
                exc,
            )

    # Fallback: transcribe audio/video via Whisper
    if not transcript_text:
        audio_files = [
            f for f in recording_files
            if f.get("file_type") in ("M4A", "MP4", "MP3")
        ]
        if audio_files:
            af = audio_files[0]
            file_ext = af["file_type"].lower()
            try:
                transcript_text = await download_and_transcribe_audio(
                    af["download_url"], access_token, file_ext
                )
            except Exception as exc:
                logger.warning(
                    "Zoom sync: failed to transcribe audio for meeting %s: %s",
                    meeting_uuid,
                    exc,
                )

    if not transcript_text:
        logger.debug(
            "Zoom sync: no transcript available for meeting %s", meeting_uuid
        )
        return "skipped"

    # ── Extract participant emails ────────────────────────────────────────
    participant_emails: list[str] = []
    # Zoom includes participant info in some recording responses
    for rf in recording_files:
        # The meeting-level data sometimes includes host email
        pass
    host_email = meeting.get("host_email", "")
    if host_email:
        participant_emails.append(host_email)

    # ── Match to client ───────────────────────────────────────────────────
    client_id = match_meeting_to_client(
        meeting_topic=topic,
        participant_emails=participant_emails,
        user_id=user_id,
        owner_id=owner.id,
        db=db,
        meeting_id=meeting_id,
    )
    if client_id is None:
        logger.debug(
            "Zoom sync: no client match for meeting %s (topic=%r)",
            meeting_uuid,
            topic,
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
            "Zoom sync: matched client %s not owned by user %s",
            client_id,
            user_id,
        )
        return "skipped"

    # ── Build document content ────────────────────────────────────────────
    meeting_data = {
        "topic": topic,
        "start_time": start_time,
        "duration": duration,
        "participant_emails": participant_emails,
    }
    content_text = build_meeting_document_content(meeting_data, transcript_text)
    content_bytes = content_text.encode("utf-8")

    # ── Upload to Supabase Storage ────────────────────────────────────────
    file_id = str(uuid.uuid4())
    filename = _safe_filename(topic, start_time)

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
            source="zoom",
            external_id=meeting_uuid,
        )
        db.add(document)
        db.commit()
        db.refresh(document)
    except Exception:
        storage_service.delete_file(storage_path)
        db.rollback()
        raise

    logger.info(
        "Zoom sync: ingested meeting %s → document %s (client=%s, topic=%r)",
        meeting_uuid,
        document.id,
        client_id,
        topic[:60],
    )

    # ── Kick off RAG pipeline ─────────────────────────────────────────────
    try:
        from app.services.rag_service import process_document

        await process_document(db, document)
    except Exception as rag_exc:
        logger.warning(
            "Zoom sync: RAG processing failed for document %s (non-fatal): %s",
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

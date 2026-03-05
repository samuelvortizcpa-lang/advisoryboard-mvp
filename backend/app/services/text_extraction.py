"""
Text extraction from uploaded documents.

Supported types:
  pdf        → pdfplumber (handles scanned-light PDFs, tables, columns)
  docx       → python-docx (paragraphs + tables)
  doc        → falls back to docx attempt, raises clear error if it fails
  txt        → plain UTF-8 read  (Fathom .txt exports work out of the box)
  csv        → rows joined as readable text
  json       → Fathom meeting transcript JSON export (title, date, attendees,
                transcript entries, action items)
  eml        → Python's built-in email library (RFC 2822 standard email)
  msg        → extract-msg library (Outlook/MAPI format)
  mp4/mov    → ffmpeg extracts audio → OpenAI Whisper transcription
  mp3/m4a/wav→ OpenAI Whisper transcription (chunked if > 24 MB)
  xlsx / xls / pptx → raises UnsupportedFileType so caller can mark gracefully
"""

from __future__ import annotations

import csv
import io
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Audio/video types are handled by the Whisper transcription service rather
# than a local text parser.
_AUDIO_TYPES: frozenset[str] = frozenset({"mp4", "m4a", "mp3", "wav"})


class ExtractionError(Exception):
    """Raised when text cannot be extracted from a file."""


class UnsupportedFileType(ExtractionError):
    """Raised for file types that cannot be processed into text."""


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def extract_text(file_path: str, file_type: str) -> str:
    """
    Extract raw text from *file_path*.

    Returns a (possibly empty) string.  Raises ExtractionError on hard failures.

    Audio/video files are transcribed via OpenAI Whisper (requires ffmpeg for
    video files and for audio files larger than 24 MB).
    """
    path = Path(file_path)
    if not path.exists():
        raise ExtractionError(f"File not found: {file_path}")

    ext = file_type.lower().lstrip(".")

    # --- audio/video: delegate to Whisper transcription service ---
    if ext in _AUDIO_TYPES:
        from app.services.audio_transcriber import transcribe_audio
        try:
            text = transcribe_audio(file_path, ext)
        except (RuntimeError, ValueError) as exc:
            raise ExtractionError(str(exc)) from exc
    else:
        # --- document types: local text parsers ---
        extractors = {
            "pdf": _extract_pdf,
            "docx": _extract_docx,
            "doc": _extract_docx,   # may fail for old binary .doc
            "txt": _extract_txt,
            "csv": _extract_csv,
            "json": _extract_fathom_json,
            "eml": _extract_email,
            "msg": _extract_email,
        }

        if ext in extractors:
            text = extractors[ext](path)
        else:
            raise UnsupportedFileType(
                f"File type '{ext}' is not supported for text extraction. "
                "Supported: pdf, docx, txt, csv, json, eml, msg, mp4, m4a, mp3, wav."
            )

    # Normalise: collapse 3+ blank lines → 2, strip leading/trailing whitespace
    import re
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


# ---------------------------------------------------------------------------
# Per-format extractors
# ---------------------------------------------------------------------------


def _extract_pdf(path: Path) -> str:
    try:
        import pdfplumber
    except ImportError as exc:
        raise ExtractionError("pdfplumber is not installed") from exc

    pages: list[str] = []
    try:
        with pdfplumber.open(str(path)) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text and text.strip():
                    pages.append(text.strip())
    except Exception as exc:
        raise ExtractionError(f"PDF extraction failed: {exc}") from exc

    return "\n\n".join(pages)


def _extract_docx(path: Path) -> str:
    try:
        from docx import Document as DocxDocument
    except ImportError as exc:
        raise ExtractionError("python-docx is not installed") from exc

    try:
        doc = DocxDocument(str(path))
    except Exception as exc:
        raise ExtractionError(f"DOCX extraction failed: {exc}") from exc

    parts: list[str] = []

    # Paragraphs
    for para in doc.paragraphs:
        t = para.text.strip()
        if t:
            parts.append(t)

    # Tables (row-per-line, cells tab-separated)
    for table in doc.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells:
                parts.append("\t".join(cells))

    return "\n\n".join(parts)


def _extract_txt(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        raise ExtractionError(f"TXT extraction failed: {exc}") from exc


def _extract_csv(path: Path) -> str:
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        reader = csv.reader(io.StringIO(content))
        rows = [", ".join(cell.strip() for cell in row) for row in reader if any(row)]
        return "\n".join(rows)
    except Exception as exc:
        raise ExtractionError(f"CSV extraction failed: {exc}") from exc


def _extract_fathom_json(path: Path) -> str:
    """
    Extract text from a Fathom meeting transcript JSON export.

    Produces a clean, readable document in this order:
        Meeting: <title>
        Date: <date>
        Attendees: <names>

        Summary:
        <summary>

        Transcript:
        [timestamp] Speaker: text
        ...

        Action Items:
        - Owner: description
        ...

    Field names are tried with common Fathom variants so the extractor
    stays robust across Fathom export versions.
    """
    import json as _json

    try:
        data = _json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except _json.JSONDecodeError as exc:
        raise ExtractionError(f"JSON parsing failed: {exc}") from exc

    if not isinstance(data, dict):
        raise ExtractionError(
            f"Expected a JSON object at the top level, got {type(data).__name__}"
        )

    parts: list[str] = []

    # ------------------------------------------------------------------
    # 1. Meeting metadata header
    # ------------------------------------------------------------------
    header: list[str] = []

    title = (
        data.get("title")
        or data.get("name")
        or data.get("meeting_title")
        or data.get("meeting_name")
    )
    if title:
        header.append(f"Meeting: {title}")

    date_val = (
        data.get("date")
        or data.get("meeting_date")
        or data.get("call_date")
        or data.get("start_time")
        or data.get("created_at")
    )
    if date_val:
        header.append(f"Date: {date_val}")

    attendees = (
        data.get("attendees")
        or data.get("participants")
        or data.get("speakers")
        or []
    )
    if isinstance(attendees, list) and attendees:
        names: list[str] = []
        for a in attendees:
            if isinstance(a, dict):
                name = (
                    a.get("name") or a.get("full_name") or a.get("display_name")
                )
                if name:
                    names.append(str(name))
            elif isinstance(a, str) and a:
                names.append(a)
        if names:
            header.append(f"Attendees: {', '.join(names)}")
    elif isinstance(attendees, str) and attendees:
        header.append(f"Attendees: {attendees}")

    duration = data.get("duration") or data.get("duration_seconds")
    if duration:
        header.append(f"Duration: {duration}")

    if header:
        parts.append("\n".join(header))

    # ------------------------------------------------------------------
    # 2. Summary / overview
    # ------------------------------------------------------------------
    summary = (
        data.get("summary")
        or data.get("overview")
        or data.get("meeting_summary")
        or data.get("description")
    )
    if isinstance(summary, str) and summary.strip():
        parts.append(f"Summary:\n{summary.strip()}")

    # ------------------------------------------------------------------
    # 3. Transcript entries
    # ------------------------------------------------------------------
    transcript = (
        data.get("transcript")
        or data.get("transcript_entries")
        or data.get("entries")
        or data.get("utterances")
        or data.get("segments")
    )
    if transcript:
        if isinstance(transcript, list):
            lines: list[str] = []
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
                        prefix = f"[{timestamp}] {speaker}" if timestamp else speaker
                        lines.append(f"{prefix}: {text}")
                    else:
                        lines.append(text)
                elif isinstance(entry, str) and entry.strip():
                    lines.append(entry.strip())
            if lines:
                parts.append("Transcript:\n" + "\n".join(lines))
        elif isinstance(transcript, str) and transcript.strip():
            parts.append(f"Transcript:\n{transcript.strip()}")

    # ------------------------------------------------------------------
    # 4. Action items
    # ------------------------------------------------------------------
    action_items = (
        data.get("action_items")
        or data.get("tasks")
        or data.get("follow_ups")
        or data.get("next_steps")
        or data.get("todos")
    )
    if action_items:
        if isinstance(action_items, list):
            items: list[str] = []
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
                    if not desc:
                        continue
                    items.append(f"- {owner}: {desc}" if owner else f"- {desc}")
                elif isinstance(item, str) and item.strip():
                    items.append(f"- {item.strip()}")
            if items:
                parts.append("Action Items:\n" + "\n".join(items))
        elif isinstance(action_items, str) and action_items.strip():
            parts.append(f"Action Items:\n{action_items.strip()}")

    if not parts:
        raise ExtractionError(
            "No readable content found in JSON. "
            "Expected Fathom transcript fields: title, date, attendees, "
            "transcript, action_items."
        )

    return "\n\n".join(parts)


def _extract_email(path: Path) -> str:
    """Extract text from .eml or .msg email files via email_extractor."""
    try:
        from app.services.email_extractor import extract_email_text
        return extract_email_text(str(path))
    except ValueError as exc:
        raise ExtractionError(f"Email extraction failed: {exc}") from exc
    except Exception as exc:
        raise ExtractionError(f"Email extraction failed: {exc}") from exc

"""
Text extraction from uploaded documents.

Supported types:
  pdf        → pdfplumber (handles scanned-light PDFs, tables, columns)
               with automatic Tesseract OCR fallback for garbled output
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
# Garbled-text detection (for PDF OCR fallback)
# ---------------------------------------------------------------------------

_COMMON_WORDS = {
    "the", "be", "to", "of", "and", "a", "in", "that", "have", "i",
    "it", "for", "not", "on", "with", "he", "as", "you", "do", "at",
    "this", "but", "his", "by", "from", "they", "we", "say", "her",
    "she", "or", "an", "will", "my", "one", "all", "would", "there",
    "their", "what", "so", "up", "out", "if", "about", "who", "get",
    "which", "go", "me", "when", "make", "can", "like", "time", "no",
    "just", "him", "know", "take", "people", "into", "year", "your",
    "good", "some", "could", "them", "see", "other", "than", "then",
    "now", "look", "only", "come", "its", "over", "think", "also",
    "back", "after", "use", "two", "how", "our", "work", "first",
    "well", "way", "even", "new", "want", "because", "any", "these",
    "give", "day", "most", "us", "is", "are", "was", "were", "been",
    "has", "had", "did", "does", "may", "shall", "should", "must",
    "form", "income", "tax", "total", "adjusted", "gross", "wages",
    "filing", "status", "exemptions", "deductions", "credits",
    "payment", "refund", "amount", "line", "schedule", "return",
    "federal", "state", "social", "security", "medicare", "withholding",
    "estimated", "balance", "due", "overpaid", "taxable", "net",
    "name", "address", "number", "date", "signature", "page",
    "department", "treasury", "internal", "revenue", "service",
}


def _is_garbled(text: str, threshold: float = 0.15) -> bool:
    """Detect whether extracted PDF text is garbled."""
    import re as _re

    if not text or len(text.strip()) < 20:
        return True

    words = _re.findall(r"[A-Za-z]{2,}", text)
    if len(words) < 5:
        return True

    # Check for reversed words (strong signal — e.g. "mroF" for "Form")
    reversed_hits = 0
    for w in words:
        if w.lower()[::-1] in _COMMON_WORDS and w.lower() not in _COMMON_WORDS:
            reversed_hits += 1
    if reversed_hits >= 2:
        logger.info(f"Garbled detection: found {reversed_hits} reversed words")
        return True

    # Check ratio of recognised words
    recognised = sum(1 for w in words if w.lower() in _COMMON_WORDS)
    ratio = recognised / len(words)
    if ratio < threshold:
        logger.info(
            f"Garbled detection: only {ratio:.1%} recognised words "
            f"({recognised}/{len(words)})"
        )
        return True

    return False


def _extract_pdf_ocr(path: Path) -> str:
    """Extract text from PDF using Tesseract OCR via pdf2image."""
    from pdf2image import convert_from_path
    import pytesseract

    logger.info(f"Running OCR extraction on {path.name}")
    pages: list[str] = []
    images = convert_from_path(str(path), dpi=150)

    for i, image in enumerate(images):
        page_text = pytesseract.image_to_string(image, config="--psm 6")
        if page_text and page_text.strip():
            pages.append(page_text.strip())
        logger.debug(f"OCR page {i + 1}: {len(page_text)} chars")

    full_text = "\n\n".join(pages)
    logger.info(f"OCR complete: {len(images)} pages, {len(full_text)} chars")
    return full_text


# ---------------------------------------------------------------------------
# Per-format extractors
# ---------------------------------------------------------------------------


def _extract_pdf(path: Path) -> str:
    """Extract text from PDF with automatic OCR fallback for garbled output."""
    try:
        import pdfplumber
    except ImportError as exc:
        raise ExtractionError("pdfplumber is not installed") from exc

    # Step 1: Try pdfplumber
    pages: list[str] = []
    try:
        with pdfplumber.open(str(path)) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text and text.strip():
                    pages.append(text.strip())
    except Exception as exc:
        raise ExtractionError(f"PDF extraction failed: {exc}") from exc

    pdfplumber_text = "\n\n".join(pages)

    # Step 2: Check quality — if pdfplumber output looks good, use it
    if not _is_garbled(pdfplumber_text):
        logger.info(f"PDF extraction: pdfplumber output OK for {path.name}")
        return pdfplumber_text

    # Step 3: Fall back to Tesseract OCR
    logger.warning(
        f"PDF extraction: pdfplumber output garbled for {path.name}, "
        "falling back to Tesseract OCR"
    )
    try:
        ocr_text = _extract_pdf_ocr(path)
        if ocr_text and len(ocr_text.strip()) > 100:
            logger.info("OCR produced good output")
            return ocr_text
        elif ocr_text and len(ocr_text.strip()) > len(pdfplumber_text.strip()):
            logger.warning("OCR output also marginal; using it (longer than pdfplumber)")
            return ocr_text
        else:
            logger.warning("OCR output also poor; returning pdfplumber result")
            return pdfplumber_text
    except Exception as e:
        logger.error(f"OCR fallback failed: {e}. Using pdfplumber output.")
        return pdfplumber_text


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

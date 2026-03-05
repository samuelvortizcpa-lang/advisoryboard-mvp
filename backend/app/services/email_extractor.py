"""
Email text extraction for .eml and .msg files.

Supported formats:
  .eml  → Python's built-in email library (RFC 2822)
  .msg  → extract-msg library (Outlook/MAPI format)

Output format (for both types):
  From: sender@example.com
  To: recipient@example.com
  Subject: Subject line here
  Date: Mon, 01 Jan 2024 10:00:00 +0000

  Body:
  Email body text...

  Attachments: file1.pdf, file2.docx
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract_email_metadata(file_path: str) -> dict:
    """
    Return a dict with From, To, Subject, Date fields.

    Keys are always present; values are empty strings when not found.
    """
    path = Path(file_path)
    ext = path.suffix.lower().lstrip(".")
    if ext == "eml":
        return _metadata_eml(path)
    elif ext == "msg":
        return _metadata_msg(path)
    else:
        return {"from": "", "to": "", "subject": "", "date": ""}


def extract_email_text(file_path: str) -> str:
    """
    Extract and format the full email as readable text.

    Returns a string in the format:
        From: ...
        To: ...
        Subject: ...
        Date: ...

        Body:
        <plain text body>

        Attachments: file1.pdf, file2.docx  (if any)
    """
    path = Path(file_path)
    ext = path.suffix.lower().lstrip(".")
    if ext == "eml":
        return _extract_eml(path)
    elif ext == "msg":
        return _extract_msg(path)
    else:
        raise ValueError(f"Unsupported email format: .{ext}")


# ---------------------------------------------------------------------------
# .eml (RFC 2822) extraction
# ---------------------------------------------------------------------------


def _metadata_eml(path: Path) -> dict:
    import email as _email

    try:
        raw = path.read_bytes()
        msg = _email.message_from_bytes(raw)
    except Exception as exc:
        logger.warning("Failed to parse .eml metadata from %s: %s", path, exc)
        return {"from": "", "to": "", "subject": "", "date": ""}

    return {
        "from": _decode_header_value(msg.get("From", "")),
        "to": _decode_header_value(msg.get("To", "")),
        "subject": _decode_header_value(msg.get("Subject", "")),
        "date": msg.get("Date", ""),
    }


def _extract_eml(path: Path) -> str:
    import email as _email

    try:
        raw = path.read_bytes()
        msg = _email.message_from_bytes(raw)
    except Exception as exc:
        raise ValueError(f"Failed to parse .eml file: {exc}") from exc

    from_addr = _decode_header_value(msg.get("From", ""))
    to_addr = _decode_header_value(msg.get("To", ""))
    subject = _decode_header_value(msg.get("Subject", ""))
    date = msg.get("Date", "")

    body = _get_eml_body(msg)
    attachments = _get_eml_attachments(msg)

    return _format_email(from_addr, to_addr, subject, date, body, attachments)


def _get_eml_body(msg) -> str:
    """Extract plain text body, falling back to HTML with tags stripped."""
    plain_parts: list[str] = []
    html_parts: list[str] = []

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = str(part.get("Content-Disposition", ""))
            # Skip attachments
            if "attachment" in disposition:
                continue
            if content_type == "text/plain":
                plain_parts.append(_decode_part(part))
            elif content_type == "text/html":
                html_parts.append(_decode_part(part))
    else:
        content_type = msg.get_content_type()
        if content_type == "text/plain":
            plain_parts.append(_decode_part(msg))
        elif content_type == "text/html":
            html_parts.append(_decode_part(msg))

    if plain_parts:
        return "\n\n".join(plain_parts).strip()
    if html_parts:
        return _strip_html("\n\n".join(html_parts)).strip()
    return ""


def _get_eml_attachments(msg) -> list[str]:
    """Return a list of attachment filenames."""
    names: list[str] = []
    if msg.is_multipart():
        for part in msg.walk():
            disposition = str(part.get("Content-Disposition", ""))
            if "attachment" in disposition:
                filename = part.get_filename()
                if filename:
                    names.append(_decode_header_value(filename))
    return names


def _decode_part(part) -> str:
    """Decode a MIME part payload to a string."""
    charset = part.get_content_charset() or "utf-8"
    try:
        payload = part.get_payload(decode=True)
        if payload is None:
            return ""
        return payload.decode(charset, errors="replace")
    except Exception:
        raw = part.get_payload(decode=True)
        return raw.decode("utf-8", errors="replace") if raw else ""


def _decode_header_value(value: str) -> str:
    """Decode RFC 2047-encoded header values (e.g. =?utf-8?b?...?=)."""
    import email.header as _eh

    try:
        parts = _eh.decode_header(value)
        decoded: list[str] = []
        for part_bytes, charset in parts:
            if isinstance(part_bytes, bytes):
                decoded.append(part_bytes.decode(charset or "utf-8", errors="replace"))
            else:
                decoded.append(str(part_bytes))
        return "".join(decoded)
    except Exception:
        return value


# ---------------------------------------------------------------------------
# .msg (Outlook/MAPI) extraction
# ---------------------------------------------------------------------------


def _metadata_msg(path: Path) -> dict:
    try:
        import extract_msg
    except ImportError:
        logger.error("extract-msg is not installed; cannot parse .msg files")
        return {"from": "", "to": "", "subject": "", "date": ""}

    try:
        with extract_msg.openMsg(str(path)) as msg:
            return {
                "from": msg.sender or "",
                "to": msg.to or "",
                "subject": msg.subject or "",
                "date": str(msg.date) if msg.date else "",
            }
    except Exception as exc:
        logger.warning("Failed to parse .msg metadata from %s: %s", path, exc)
        return {"from": "", "to": "", "subject": "", "date": ""}


def _extract_msg(path: Path) -> str:
    try:
        import extract_msg
    except ImportError as exc:
        raise ValueError(
            "extract-msg is not installed. Run: pip install extract-msg==0.48.0"
        ) from exc

    try:
        with extract_msg.openMsg(str(path)) as msg:
            from_addr = msg.sender or ""
            to_addr = msg.to or ""
            subject = msg.subject or ""
            date = str(msg.date) if msg.date else ""
            body = (msg.body or "").strip()
            attachments = [
                att.longFilename or att.shortFilename or "attachment"
                for att in (msg.attachments or [])
                if not getattr(att, "isAttachment", True) is False
            ]
    except Exception as exc:
        raise ValueError(f"Failed to parse .msg file: {exc}") from exc

    return _format_email(from_addr, to_addr, subject, date, body, attachments)


# ---------------------------------------------------------------------------
# Shared formatting
# ---------------------------------------------------------------------------


def _format_email(
    from_addr: str,
    to_addr: str,
    subject: str,
    date: str,
    body: str,
    attachments: list[str],
) -> str:
    """Assemble the canonical email text format used for RAG chunking."""
    header_lines = []
    if from_addr:
        header_lines.append(f"From: {from_addr}")
    if to_addr:
        header_lines.append(f"To: {to_addr}")
    if subject:
        header_lines.append(f"Subject: {subject}")
    if date:
        header_lines.append(f"Date: {date}")

    parts = ["\n".join(header_lines)] if header_lines else []

    if body:
        parts.append(f"Body:\n{body}")

    if attachments:
        parts.append(f"Attachments: {', '.join(attachments)}")

    return "\n\n".join(parts)


def _strip_html(html: str) -> str:
    """Remove HTML tags and decode common entities."""
    import re

    text = re.sub(r"<[^>]+>", " ", html)
    # Common HTML entities
    entities = {
        "&amp;": "&", "&lt;": "<", "&gt;": ">",
        "&nbsp;": " ", "&quot;": '"', "&#39;": "'",
    }
    for entity, char in entities.items():
        text = text.replace(entity, char)
    # Collapse whitespace
    text = re.sub(r" {2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

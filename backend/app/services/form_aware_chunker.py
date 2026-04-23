"""
Form-aware chunker for tax return documents.

State-machine chunker that detects IRS form boundaries, part/section
headers, and line-group headings within each page's extracted text.
Produces chunks with form-attribution prefixes and structured JSONB
metadata for the document_chunks table.

Boundary priority: form > part > section > size.
No overlap between chunks (unlike smart_chunk).

Reuses detect_voucher_chunk from chunking.py for 1040-ES detection.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from app.services.chunking import detect_voucher_chunk
from app.services.form_sections import (
    FORM_SECTIONS_REGISTRY,
    SectionEntry,
    lookup_section_for_line,
)

logger = logging.getLogger(__name__)

CHUNKER_VERSION = "form_aware_v2"

# ---------------------------------------------------------------------------
# Form header patterns — must be first non-whitespace on the line
# ---------------------------------------------------------------------------

# Order matters: check specific schedules/forms before generic "Form NNNN".
# Each tuple: (compiled regex, canonical form name extractor)
# The regex is anchored to start-of-line (after optional whitespace).

_FORM_PATTERNS: list[tuple[re.Pattern, str | None]] = [
    # Schedule X (Form NNNN) — e.g. "Schedule A (Form 1040)", "Schedule A (Form 8936)"
    # Generalized to accept any 3-5 digit parent form, not just 1040 variants.
    (
        re.compile(
            r"^\s*Schedule\s+([A-Z0-9]{1,4}(?:-[A-Z0-9]+)?)\s*\(Form\s+(\d{3,5}(?:-[A-Z]{1,3})?)\)",
            re.MULTILINE | re.IGNORECASE,
        ),
        None,  # dynamic — built from match groups
    ),
    # Schedule without parent form suffix — e.g. "Schedule D"
    (
        re.compile(
            r"^\s*Schedule\s+([A-Z0-9]{1,4}(?:-[A-Z0-9]+)?)\b",
            re.MULTILINE | re.IGNORECASE,
        ),
        None,
    ),
    # Form 1040-ES (voucher — handled separately but detected here)
    (
        re.compile(
            r"^\s*Form\s+1040-ES\b",
            re.MULTILINE | re.IGNORECASE,
        ),
        "Form 1040-ES",
    ),
    # Form 1040 variants: 1040, 1040-SR, 1040-X, 1040-NR
    (
        re.compile(
            r"^\s*Form\s+(1040(?:-[A-Z]{1,3})?)\b",
            re.MULTILINE | re.IGNORECASE,
        ),
        None,
    ),
    # State forms — whitelist of known prefixes.
    # Using a whitelist instead of a loose [A-Z]{1,3}[\s-]\d{2,4} pattern
    # to prevent false positives from OCR artifacts like "P 28", "REV 12".
    # Trade-off: new states require explicit enumeration here.
    None,  # placeholder — replaced by _STATE_FORM_RE below
    # Generic federal forms: Form NNNN or Form NNNN-X (3-5 digits)
    (
        re.compile(
            r"^\s*Form\s+(\d{3,5}(?:-[A-Z0-9]+)?)\b",
            re.MULTILINE | re.IGNORECASE,
        ),
        None,
    ),
]

# -- State form whitelist (FIX 2) --
# Known state form prefixes. Add new states here as needed.
_STATE_FORM_PREFIXES = [
    "D-400", "D-410", "D-422", "D-429",
    "NC-40", "NC-EDU", "NC-478",
    "IT-201", "IT-203", "IT-1040",
    "CA-540", "CA-540NR",
    "NY-IT", "NY-IT-201",
    "540", "540NR",
]
_STATE_FORM_RE = re.compile(
    r"^\s*(?:Form\s+)?(" + "|".join(re.escape(p) for p in _STATE_FORM_PREFIXES) +
    r")(?:-[A-Z0-9]+)?\b",
    re.MULTILINE,
)
# Replace the None placeholder with the actual state form pattern
_FORM_PATTERNS[4] = (_STATE_FORM_RE, None)

# ---------------------------------------------------------------------------
# Part / section detection
# ---------------------------------------------------------------------------

_PART_RE = re.compile(
    r"^\s*Part\s+([IVXLC]+)\b[.\s\-–—]*(.*)$",
    re.MULTILINE | re.IGNORECASE,
)

# Common section/line-group headings on major forms.
_SECTION_HEADINGS = [
    "Income",
    "Adjusted Gross Income",
    "Tax and Credits",
    "Payments",
    "Refund",
    "Amount You Owe",
    "Other Taxes",
    "Taxes You Paid",
    "Interest You Paid",
    "Gifts to Charity",
    "Casualty and Theft Losses",
    "Other Itemized Deductions",
    "Medical and Dental Expenses",
    "Interest and Ordinary Dividends",
    "Short-Term Capital Gains and Losses",
    "Long-Term Capital Gains and Losses",
    "Summary",
]

_SECTION_RE = re.compile(
    r"^\s*(" + "|".join(re.escape(h) for h in _SECTION_HEADINGS) + r")\s*$",
    re.MULTILINE | re.IGNORECASE,
)

# ============================================================================
# v2 section-aware splitting parameters
# ============================================================================

# Soft target for chunk size within a single section. v2 tries to respect
# section boundaries over size targets (spec §4).
V2_SECTION_TARGET_CHARS = 2000

# Hard ceiling: when a section exceeds this, we force a split with the
# section header injected into the subsequent chunk to preserve context.
V2_SECTION_HARD_CEILING = 2000

# Regex to detect line-number-prefixed lines in tax form OCR output.
# Matches "Line 11", "11.", "11)", "11a", "1a", "5d" at line start after
# optional whitespace. Captures just the line identifier.
# This is how we detect which line group we're currently in, so we can
# consult FORM_SECTIONS_REGISTRY.
_LINE_NUMBER_RE = re.compile(
    r"^\s*(?:Line\s+)?(\d{1,3}[a-z]?)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Transfer / cross-reference detection (for metadata, NOT state change)
# ---------------------------------------------------------------------------

_TRANSFER_RE = re.compile(
    r"(?:to|on|from|see|attach)\s+(?:Form\s+|Schedule\s+|Sch\.\s*)"
    r"([A-Z0-9](?:[A-Z0-9-]*)?(?:\s*\(Form\s+1040[^)]*\))?)"
    r"(?:[,\s]+[Ll]ine\s+(\d+[a-z]?))?",
    re.IGNORECASE,
)

# Lines covered pattern — "Line 5", "Lines 2-4", "Line 2b"
_LINE_RE = re.compile(r"[Ll]ines?\s+(\d+[a-z]?(?:\s*[-–—]\s*\d+[a-z]?)?)")


# ---------------------------------------------------------------------------
# Content-based Form 1040 fallback (for OCR-destroyed page headers)
# ---------------------------------------------------------------------------
#
# When a chunk would emit with form="Unknown" and contains multiple
# distinctive Form 1040 line-item phrases, we reclassify as Form 1040.
# This handles the case where OCR destroys the page header (e.g.
# "Form 1040" rendered as "51 0 40").
#
# Phrases chosen for specificity — they appear on Form 1040 page 1
# in the standard line-item structure and are unlikely to appear
# verbatim on other forms.

_FORM_1040_DISTINCTIVE_PHRASES = [
    re.compile(r"Total amount from Form\(s\)\s*W-?2", re.IGNORECASE),
    re.compile(r"This is your total income", re.IGNORECASE),
    re.compile(r"This is your adjusted gross income", re.IGNORECASE),
    re.compile(r"Standard deduction or itemized deductions", re.IGNORECASE),
    re.compile(r"This is your taxable income", re.IGNORECASE),
    re.compile(r"Qualified business income deduction", re.IGNORECASE),
    re.compile(r"This is your total tax", re.IGNORECASE),
    re.compile(r"This is the amount you owe", re.IGNORECASE),
    re.compile(r"the amount you overpaid", re.IGNORECASE),
]


def _infer_form_1040_from_content(text: str) -> bool:
    """Return True if chunk text contains >= 2 distinctive Form 1040 phrases.

    Used as an emit-time fallback when form detection via header failed
    (e.g., OCR destroyed the header). Does NOT update state — each chunk
    is evaluated independently.
    """
    matches = sum(1 for p in _FORM_1040_DISTINCTIVE_PHRASES if p.search(text))
    return matches >= 2


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _looks_like_header_tail(tail: str) -> bool:
    """Return True if *tail* (text after the form identifier) is consistent
    with a real form header line, False if it looks like a cross-reference.

    Empty or whitespace-only tail → accepted (form name alone on a line).
    """
    tail = tail.strip()
    if not tail:
        return True
    # Explicit reject: starts with lowercase, comma, or "line(s)"
    if re.match(r"^[a-z,]", tail) or re.match(r"^lines?\b", tail, re.IGNORECASE):
        return False
    return True


def _detect_form_header(line: str) -> tuple[str, str | None] | None:
    """Try to detect a form header at the start of *line*.

    Returns (canonical_form_name, parent_form | None) or None.
    The line must start with the form identifier (after optional whitespace)
    to count as a header — mid-line references are ignored.

    After matching the form identifier, the remainder of the line is
    inspected: if it starts with a lowercase word or comma (suggesting a
    cross-reference continuation like "Form 8283 to be attached"), the
    match is rejected.
    """
    stripped = line.strip()
    if not stripped:
        return None

    for pattern, static_name in _FORM_PATTERNS:
        m = pattern.match(line)
        if not m:
            continue

        # Text after the matched form identifier
        tail = line[m.end():]

        if static_name:
            if not _looks_like_header_tail(tail):
                continue
            parent = None
            return static_name, parent

        groups = m.groups()

        # Schedule X (Form YYYY) — tail check less critical since the
        # pattern already requires "(Form NNNN)" suffix, but apply anyway
        if "Schedule" in pattern.pattern and "Form" in pattern.pattern and len(groups) == 2:
            if not _looks_like_header_tail(tail):
                continue
            sched_letter = groups[0].upper()
            parent_form = f"Form {groups[1].upper()}"
            return f"Schedule {sched_letter} (Form {groups[1].upper()})", parent_form

        # Schedule X (no parent form in text)
        if "Schedule" in pattern.pattern and len(groups) == 1:
            if not _looks_like_header_tail(tail):
                continue
            sched_letter = groups[0].upper()
            return f"Schedule {sched_letter}", None

        # Form NNNN variant
        if len(groups) == 1:
            if not _looks_like_header_tail(tail):
                continue
            form_id = groups[0].upper()

            # FIX 1: Reject year-as-form — no real IRS form is 1900-2099.
            # OCR artifacts like "Form 2024" (from garbled "Form 8949 (2024)")
            # match the generic pattern but are not real form numbers.
            if form_id.isdigit() and 1900 <= int(form_id) <= 2099:
                continue

            # State form detection: has letters (e.g. D-400, IT-201)
            if re.match(r"[A-Z]", form_id) and re.search(r"\d", form_id):
                return f"Form {form_id}", None
            return f"Form {form_id}", None

    return None


def _detect_part(line: str) -> str | None:
    """Detect a Part header. Returns e.g. 'Part I Interest' or None."""
    m = _PART_RE.match(line)
    if m:
        part_num = m.group(1).upper()
        part_title = m.group(2).strip().rstrip(".")
        if part_title:
            return f"Part {part_num} {part_title}"
        return f"Part {part_num}"
    return None


def _detect_section(line: str) -> str | None:
    """Detect a section heading. Returns the heading text or None."""
    m = _SECTION_RE.match(line)
    if m:
        return m.group(1).strip()
    return None


def _detect_line_number(line: str) -> Optional[str]:
    """Extract the line identifier from a single line of OCR text if it
    looks like a tax form line-start.

    Returns the line identifier string (e.g., "11", "5d", "1a") or None
    if the line doesn't appear to start with a line number.

    Used by v2 splitting logic to track which form line the chunker is
    currently processing, so it can consult FORM_SECTIONS_REGISTRY.
    """
    if not line or not line.strip():
        return None
    m = _LINE_NUMBER_RE.match(line)
    if not m:
        return None
    line_id = m.group(1).lower()
    # Filter out OCR artifacts: bare 4-digit numbers are usually years,
    # not line numbers. Form lines rarely exceed 3 digits.
    if line_id.isdigit() and len(line_id) == 4:
        return None
    return line_id


def _lookup_section_v2(
    current_form: Optional[str],
    current_line: Optional[str],
) -> Optional[SectionEntry]:
    """Look up the section entry for the current (form, line) pair.

    Consults FORM_SECTIONS_REGISTRY via lookup_section_for_line.
    Returns None if form is unknown or line doesn't match any section.

    This is the core of v2's section detection: instead of matching
    against a hardcoded list of section header strings (v1 approach),
    we match observed line numbers against per-form line-group tables.
    """
    if not current_form or not current_line:
        return None
    return lookup_section_for_line(current_form, current_line)


def _extract_transfers(text: str) -> list[str]:
    """Extract cross-reference targets (e.g. 'Form 1040 Line 2b')."""
    transfers = []
    for m in _TRANSFER_RE.finditer(text):
        target = m.group(1).strip()
        line = m.group(2)
        if line:
            transfers.append(f"{target} Line {line}")
        else:
            transfers.append(target)
    return transfers


def _extract_lines_covered(text: str) -> list[str]:
    """Extract line references from chunk text."""
    return [m.group(1) for m in _LINE_RE.finditer(text)]


def _build_prefix(
    tax_year: int | None,
    form: str,
    page: int,
    section: str,
) -> str:
    """Build the form-attribution prefix string."""
    year_str = str(tax_year) if tax_year is not None else "UNKNOWN"
    return f"[TAX YEAR {year_str} | Form: {form} | Page {page} | Section: {section}]"


def _build_metadata(
    *,
    tax_year: int | None,
    form: str,
    parent_form: str | None,
    page: int,
    section: str,
    part: str | None,
    chunk_text: str,
    is_voucher: bool = False,
    voucher_continuation: bool = False,
    voucher_year: int | None = None,
) -> dict:
    """Build the JSONB metadata payload."""
    lines = _extract_lines_covered(chunk_text)
    transfers = _extract_transfers(chunk_text)
    return {
        "doc_type": "tax_return",
        "tax_year": tax_year,
        "form": form,
        "parent_form": parent_form,
        "page": page,
        "section": section,
        "part": part,
        "lines_covered": lines if lines else None,
        "transfers_to": transfers if transfers else None,
        "is_voucher": is_voucher,
        "voucher_continuation": voucher_continuation,
        "voucher_year": voucher_year,
        "chunker_version": CHUNKER_VERSION,
    }


def _resolve_page_form(
    page_text: str,
    current_form: str,
) -> tuple[str, str | None] | None:
    """Resolve a page's form identity before the line-by-line loop runs.

    Precedence:
      1. Scan the first 5 non-blank lines for a real form header.
         If found, return it.
      2. If no header, run content-based inference (currently Form 1040
         only). If matched, return ("Form 1040", None).
      3. Otherwise return None — caller keeps state from previous page.

    Returns (form, parent_form) or None.
    """
    lines = page_text.split("\n")
    nonblank_seen = 0
    for line in lines:
        if not line.strip():
            continue
        nonblank_seen += 1
        if nonblank_seen > 5:
            break
        header = _detect_form_header(line)
        if header:
            return header

    if _infer_form_1040_from_content(page_text):
        return ("Form 1040", None)

    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def form_aware_chunk(
    pages: list[dict],
    tax_year: Optional[int] = None,
    target_chars: int = 600,
    max_chars: int = 1200,
) -> list[dict]:
    """
    Structure- and form-aware chunker for tax return PDFs.

    Parameters
    ----------
    pages : list[dict]
        Each dict has ``page_number`` (int) and ``text`` (str), same shape
        as ``structure_aware_chunk`` input.
    tax_year : int | None
        Tax year extracted from filename or classifier.  Used in the prefix
        and for voucher detection.
    target_chars : int
        Soft target for chunk size in characters.
    max_chars : int
        Hard maximum — chunks exceeding this are force-split.

    Returns
    -------
    list[dict]
        Each dict: ``{"text": str, "page_number": int, "metadata": dict}``
        where ``text`` has the form-attribution prefix prepended.
    """
    if not pages:
        return []

    # State machine
    current_form: str = "Unknown"
    current_parent_form: str | None = None
    current_part: str | None = None
    current_section: str = "Unclassified"
    in_voucher_sequence: bool = False

    # Accumulator for the current chunk
    chunk_buf: list[str] = []
    chunk_len: int = 0
    chunk_page: int = pages[0].get("page_number", 1)

    # Snapshot of state at chunk start (for metadata/prefix)
    chunk_form: str = current_form
    chunk_parent: str | None = current_parent_form
    chunk_part: str | None = current_part
    chunk_section: str = current_section
    chunk_is_voucher: bool = False
    chunk_voucher_cont: bool = False
    chunk_voucher_year: int | None = None

    results: list[dict] = []

    def _flush():
        nonlocal chunk_buf, chunk_len
        if not chunk_buf:
            return
        body = "\n".join(chunk_buf).strip()
        if not body:
            chunk_buf = []
            chunk_len = 0
            return

        emit_form = chunk_form
        emit_parent = chunk_parent
        emit_section = chunk_section

        # Content-based Form 1040 fallback for OCR-destroyed headers
        if emit_form == "Unknown" and _infer_form_1040_from_content(body):
            emit_form = "Form 1040"
            emit_parent = None
            if emit_section == "Unclassified":
                emit_section = "Header"

        prefix = _build_prefix(tax_year, emit_form, chunk_page, emit_section)
        metadata = _build_metadata(
            tax_year=tax_year,
            form=emit_form,
            parent_form=emit_parent,
            page=chunk_page,
            section=emit_section,
            part=chunk_part,
            chunk_text=body,
            is_voucher=chunk_is_voucher,
            voucher_continuation=chunk_voucher_cont,
            voucher_year=chunk_voucher_year,
        )
        results.append({
            "text": f"{prefix}\n{body}",
            "page_number": chunk_page,
            "metadata": metadata,
        })
        chunk_buf = []
        chunk_len = 0

    def _snapshot_state():
        """Capture current state machine values for the new chunk."""
        nonlocal chunk_form, chunk_parent, chunk_part, chunk_section
        nonlocal chunk_page, chunk_is_voucher, chunk_voucher_cont, chunk_voucher_year
        chunk_form = current_form
        chunk_parent = current_parent_form
        chunk_part = current_part
        chunk_section = current_section
        chunk_is_voucher = in_voucher_sequence
        chunk_voucher_cont = False
        chunk_voucher_year = None

    for page in pages:
        page_num = page.get("page_number", 1)
        text = page.get("text", "")
        if not text.strip():
            continue

        # Check entire page for voucher status
        voucher_info = detect_voucher_chunk(text, return_tax_year=tax_year)
        page_is_voucher = voucher_info["is_voucher"]

        if page_is_voucher:
            # Entering or continuing voucher sequence
            if not in_voucher_sequence:
                # Flush any non-voucher content before entering voucher mode
                _flush()
                in_voucher_sequence = True
                current_form = "Form 1040-ES"
                current_parent_form = None
                current_part = None
                current_section = "Estimated Tax Payment Voucher"

            chunk_page = page_num
            _snapshot_state()
            chunk_is_voucher = True
            chunk_voucher_year = voucher_info.get("voucher_year")

            # Emit the whole voucher page as one chunk
            chunk_buf = [text.strip()]
            chunk_len = len(text.strip())
            _flush()
            continue

        # Not a voucher page — if we were in a voucher sequence, exit it
        if in_voucher_sequence:
            in_voucher_sequence = False
            # Reset form state — will be re-detected below if a header appears
            current_form = "Unknown"
            current_parent_form = None
            current_part = None
            current_section = "Unclassified"

        # Page-boundary flush: close any in-progress chunk so it's attributed
        # to the page it started on, and the next chunk begins cleanly on
        # the new page with the current state.
        if chunk_buf:
            _flush()
        chunk_page = page_num
        _snapshot_state()

        # Page-level form resolution: attempt to identify the page's form
        # once, before the line loop. Header scan first, content inference
        # as fallback. Updates state if a new form is resolved.
        resolved = _resolve_page_form(text, current_form)
        if resolved is not None:
            new_form, new_parent = resolved
            if new_form != current_form:
                current_form = new_form
                current_parent_form = new_parent
                current_part = None
                current_section = _default_section(new_form)
                _snapshot_state()

        lines = text.split("\n")

        for line in lines:
            # --- Check for form header ---
            form_info = _detect_form_header(line)
            if form_info:
                new_form, new_parent = form_info

                # Form boundary: flush current chunk, update state
                if new_form != current_form:
                    _flush()
                    current_form = new_form
                    current_parent_form = new_parent
                    current_part = None
                    current_section = _default_section(new_form)
                    chunk_page = page_num
                    _snapshot_state()

            # --- Check for part header ---
            part_info = _detect_part(line)
            if part_info and part_info != current_part:
                _flush()
                current_part = part_info
                current_section = part_info
                chunk_page = page_num
                _snapshot_state()

            # --- v2: Section detection via line-number lookup (primary) ---
            # If this line starts with a line number, look up which named
            # section that line belongs to. If it's a different section
            # than the current one, flush and update state BEFORE appending
            # the line. This ensures the line that introduces the new
            # section becomes the first line of the new chunk, preserving
            # label-to-content association (fixes Q7 Schedule A charity).
            line_num = _detect_line_number(line)
            if line_num:
                section_entry = _lookup_section_v2(current_form, line_num)
                if section_entry and section_entry["section"] != current_section:
                    _flush()
                    current_section = section_entry["section"]
                    chunk_page = page_num
                    _snapshot_state()

            # --- v1 section heading regex (fallback for non-numbered lines) ---
            # Keeps compatibility with content like "Gifts to Charity" header
            # text appearing before the first numbered line of a section.
            section_info = _detect_section(line)
            if section_info and section_info != current_section:
                _flush()
                current_section = section_info
                chunk_page = page_num
                _snapshot_state()

            # --- Accumulate line ---
            line_len = len(line) + 1  # +1 for newline

            # --- v2: Size gating depends on current_section ---
            # If we're inside a named section (not Header/Unclassified/part-header),
            # respect section atomicity up to V2_SECTION_HARD_CEILING.
            # Otherwise, fall back to v1 behavior: soft-split at target_chars
            # on blank lines, force-split at max_chars.
            in_named_section = current_section not in (
                "Header",
                "Unclassified",
                "Estimated Tax Payment Voucher",
            ) and not (current_part and current_section == current_part)

            if in_named_section:
                # v2 strict: only split at hard ceiling. Keep the section atomic.
                if chunk_len + line_len > V2_SECTION_HARD_CEILING and chunk_buf:
                    _flush()
                    chunk_page = page_num
                    _snapshot_state()
            else:
                # v1 fallback: force split at max_chars
                if chunk_len + line_len > max_chars and chunk_buf:
                    _flush()
                    chunk_page = page_num
                    _snapshot_state()

                # v1 fallback: soft split at target_chars on blank lines
                if (
                    chunk_len >= target_chars
                    and chunk_buf
                    and line.strip() == ""
                ):
                    _flush()
                    chunk_page = page_num
                    _snapshot_state()
                    continue  # skip the blank line itself

            chunk_buf.append(line)
            chunk_len += line_len

    # Flush remaining content
    _flush()

    # Warn about Unknown form chunks
    unknown_count = sum(1 for r in results if r["metadata"]["form"] == "Unknown")
    if unknown_count:
        logger.warning(
            "form_aware_chunk: %d chunk(s) have form=Unknown (no header detected)",
            unknown_count,
        )

    return results


def _default_section(form: str) -> str:
    """Return a sensible default section name for a form."""
    if "1040-ES" in form:
        return "Estimated Tax Payment Voucher"
    if "Schedule" in form:
        return "Header"
    return "Header"

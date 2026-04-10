"""
Semantic text chunking for RAG.

Strategy
--------
1. Split input on paragraph breaks (double newlines).
2. Accumulate paragraphs until the current chunk would exceed the target size.
3. When flushing, carry overlap chars of the previous chunk forward so
   context is preserved across boundaries.
4. Paragraphs that are individually larger than the target are further split
   at sentence boundaries using the same overlap logic.

Tuning (document-type-specific)
------
Financial:   600 chars / 100 overlap  (preserves line-item structure)
Transcript: 1800 chars / 200 overlap  (preserves conversational context)
Email:      1200 chars / 200 overlap  (medium — single-thread messages)
Default:    1200 chars / 200 overlap  (balanced for narrative documents)
MIN_CHUNK_LEN = 50  chars   — discard tiny noise fragments
"""

from __future__ import annotations

import re
from typing import Optional

# Legacy constants (kept for backward compat with any direct callers)
CHUNK_SIZE = 1_500
CHUNK_OVERLAP = 200
MIN_CHUNK_LEN = 50

# ── Voucher detection ────────────────────────────────────────────────────────

_VOUCHER_PATTERNS = [
    re.compile(r"form\s*1040-?es", re.IGNORECASE),
    re.compile(r"estimated\s+tax\s+(payment|voucher)", re.IGNORECASE),
    re.compile(r"payment\s+voucher", re.IGNORECASE),
]

_FUTURE_YEAR_PATTERN = re.compile(r"\b(20\d{2})\b")


def detect_voucher_chunk(
    chunk_text: str, return_tax_year: int | None = None
) -> dict:
    """
    Detect whether a chunk is a Form 1040-ES estimated-tax voucher for a future tax year.

    Returns a dict with:
      - is_voucher: bool
      - voucher_type: "1040-ES" | None
      - voucher_year: int | None (the tax year the voucher is for, if detectable)

    A chunk is flagged as a voucher only if BOTH conditions hold:
      1. At least one voucher pattern matches
      2. A year appears in the chunk that is >= (return_tax_year + 1) if return_tax_year
         is known, OR any 4-digit year in range 2025-2099 if not
    """
    has_voucher_pattern = any(p.search(chunk_text) for p in _VOUCHER_PATTERNS)
    if not has_voucher_pattern:
        return {"is_voucher": False, "voucher_type": None, "voucher_year": None}

    years_in_text = [int(y) for y in _FUTURE_YEAR_PATTERN.findall(chunk_text)]
    if not years_in_text:
        return {"is_voucher": False, "voucher_type": None, "voucher_year": None}

    if return_tax_year is not None:
        future_years = [y for y in years_in_text if y >= return_tax_year + 1]
    else:
        # Without a known return year, flag any year in 2025+ as potentially future
        future_years = [y for y in years_in_text if y >= 2025]

    if not future_years:
        return {"is_voucher": False, "voucher_type": None, "voucher_year": None}

    return {
        "is_voucher": True,
        "voucher_type": "1040-ES",
        "voucher_year": max(future_years),
    }

FINANCIAL_CHUNK_SIZE = 500
FINANCIAL_CHUNK_OVERLAP = 100

FINANCIAL_DOC_TYPES: set[str] = {
    "tax_return",
    "w2",
    "k1",
    "1099",
    "1040x",
    "1120",
    "1065",
    "financial_statement",
    "invoice",
}

TRANSCRIPT_DOC_TYPES: set[str] = {
    "meeting_transcript",
    "video_transcript",
}

EMAIL_DOC_TYPES: set[str] = {
    "email",
}


def get_chunk_params(document_type: Optional[str] = None) -> tuple[int, int]:
    """
    Return (chunk_size, overlap) appropriate for the document type.

    Financial document types get smaller chunks to preserve line-item
    structure; transcripts get larger chunks for context; everything else
    uses a balanced default.
    """
    dt = (document_type or "").lower()
    if dt in FINANCIAL_DOC_TYPES:
        return 600, 100
    if dt in TRANSCRIPT_DOC_TYPES:
        return 1800, 200
    if dt in EMAIL_DOC_TYPES:
        return 1200, 200
    return 1200, 200


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


_PAGE_MARKER_RE = re.compile(r"^\[Page\s+\d+\]", re.MULTILINE)


def smart_chunk(
    text: str,
    document_type: str = "general",
    max_chars: Optional[int] = None,
    overlap: int = 200,
) -> list[str]:
    """
    Structure-aware chunking that respects paragraph and section boundaries.

    Selects chunk size based on document_type, then delegates to the
    paragraph-aware chunking pipeline (which handles [Page N] markers,
    paragraph merging, sentence splitting for oversized paragraphs, and
    overlap carry-forward).

    Falls back to character-split for text that doesn't have clear structure.
    """
    if not text or not text.strip():
        return []

    # Determine sizing from document type if not explicitly provided
    if max_chars is None:
        max_chars, overlap = get_chunk_params(document_type)

    # Normalise: collapse runs of blank lines
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    # Delegate to page-marker-aware or plain paragraph chunking
    if _PAGE_MARKER_RE.search(text):
        return _chunk_with_page_markers(text, max_chars, overlap)

    return _chunk_plain(text, max_chars, overlap)


def chunk_text(
    text: str,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[str]:
    """
    Split *text* into overlapping chunks of at most *chunk_size* characters.

    If the text contains ``[Page N]`` markers (inserted by the PDF extractor),
    page boundaries act as hard chunk breaks so that page context is never
    lost across chunks.  Each chunk inherits the ``[Page N]`` header of the
    page it starts on.

    Returns a list of non-empty strings, each at least MIN_CHUNK_LEN chars.

    NOTE: Prefer smart_chunk() for new code — it selects sizing automatically
    based on document_type.
    """
    if not text or not text.strip():
        return []

    # Normalise: collapse runs of blank lines
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    # If page markers are present, split on them and chunk each page
    # independently so that page context is never lost across chunks.
    if _PAGE_MARKER_RE.search(text):
        return _chunk_with_page_markers(text, chunk_size, overlap)

    return _chunk_plain(text, chunk_size, overlap)


def _chunk_with_page_markers(
    text: str,
    chunk_size: int,
    overlap: int,
) -> list[str]:
    """Split text that contains [Page N] markers, keeping each page as a
    separate chunking unit so page headers propagate into every chunk."""
    # Split on [Page N] boundaries, keeping the marker with its content
    parts = _PAGE_MARKER_RE.split(text)
    markers = _PAGE_MARKER_RE.findall(text)

    # parts[0] is text before first marker (usually empty), then alternating
    # Build list of (marker, body) tuples
    pages: list[tuple[str, str]] = []
    for i, marker in enumerate(markers):
        body = parts[i + 1] if (i + 1) < len(parts) else ""
        body = body.strip()
        if body:
            pages.append((marker, body))

    all_chunks: list[str] = []
    for marker, body in pages:
        # Chunk this page's body normally
        page_chunks = _chunk_plain(body, chunk_size - len(marker) - 1, overlap)
        for pc in page_chunks:
            all_chunks.append(f"{marker}\n{pc}")
        # If the page body is small enough to not produce any chunks, include it whole
        if not page_chunks and len(body) >= MIN_CHUNK_LEN:
            all_chunks.append(f"{marker}\n{body}")

    return all_chunks


def _chunk_plain(
    text: str,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[str]:
    """Paragraph-based chunking for text without page markers."""
    # Split into paragraphs
    paragraphs = [p.strip() for p in re.split(r"\n\n+", text) if p.strip()]

    chunks: list[str] = []
    current_parts: list[str] = []
    current_len = 0

    for para in paragraphs:
        if len(para) > chunk_size:
            # Flush current accumulation before dealing with the jumbo paragraph
            if current_parts:
                chunks.append(_join(current_parts))
                current_parts, current_len = [], 0

            # Split the oversized paragraph at sentence boundaries
            for sent_chunk in _split_sentences(para, chunk_size, overlap):
                chunks.append(sent_chunk)

        elif current_len + len(para) + 2 > chunk_size and current_parts:
            # Flushing would overflow — emit current chunk
            chunks.append(_join(current_parts))

            # Carry overlap into the next chunk
            overlap_parts = _tail_parts(current_parts, overlap)
            current_parts = overlap_parts + [para]
            current_len = sum(len(p) for p in current_parts) + 2 * max(0, len(current_parts) - 1)

        else:
            current_parts.append(para)
            current_len += len(para) + 2  # +2 for the "\n\n" separator

    # Flush remainder
    if current_parts:
        chunks.append(_join(current_parts))

    return [c for c in chunks if len(c.strip()) >= MIN_CHUNK_LEN]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _join(parts: list[str]) -> str:
    return "\n\n".join(parts)


def _tail_parts(parts: list[str], max_chars: int) -> list[str]:
    """Return the trailing items of *parts* whose total length <= *max_chars*."""
    result: list[str] = []
    total = 0
    for part in reversed(parts):
        if total + len(part) <= max_chars:
            result.insert(0, part)
            total += len(part)
        else:
            break
    return result


def structure_aware_chunk(
    pages: list[dict],
    max_chars: int = 1200,
    overlap: int = 200,
) -> list[dict]:
    """
    Chunk based on document structure (page/block boundaries) from Document AI.

    Each block is a logical unit (paragraph, table, header).
    Merges small adjacent blocks, splits oversized ones.
    Returns list of {"text": str, "page_number": int} with [Page N] prefix.
    """
    chunks: list[dict] = []
    current_chunk = ""
    current_page: int | None = None

    for page in pages:
        page_num = page["page_number"]
        blocks = page.get("blocks", [{"text": page["text"], "type": "paragraph"}])

        for block in blocks:
            block_text = block["text"].strip()
            if not block_text:
                continue

            # Oversized block: flush current, then char-split the block
            if len(block_text) > max_chars:
                if current_chunk.strip():
                    chunks.append({"text": current_chunk.strip(), "page_number": current_page})
                    current_chunk = ""
                for i in range(0, len(block_text), max_chars - overlap):
                    chunk_slice = block_text[i : i + max_chars].strip()
                    if chunk_slice:
                        chunks.append({"text": chunk_slice, "page_number": page_num})
                continue

            # Would exceed max_chars: close current chunk, carry overlap
            if len(current_chunk) + len(block_text) + 2 > max_chars and current_chunk:
                chunks.append({"text": current_chunk.strip(), "page_number": current_page})
                if overlap and len(current_chunk) > overlap:
                    current_chunk = current_chunk[-overlap:] + "\n\n" + block_text
                else:
                    current_chunk = block_text
                current_page = page_num
            else:
                if current_chunk:
                    current_chunk += "\n\n" + block_text
                else:
                    current_chunk = block_text
                    current_page = page_num

    if current_chunk.strip():
        chunks.append({"text": current_chunk.strip(), "page_number": current_page})

    # Add page markers to match existing chunk format
    for chunk in chunks:
        if chunk["page_number"] is not None:
            chunk["text"] = f"[Page {chunk['page_number']}]\n{chunk['text']}"

    return chunks


def _split_sentences(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Split *text* at sentence boundaries, respecting *chunk_size* and *overlap*."""
    # Split on period/exclamation/question mark followed by whitespace
    sentences = re.split(r"(?<=[.!?])\s+", text)

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for sent in sentences:
        sent_len = len(sent) + 1  # +1 for space separator

        if current_len + sent_len > chunk_size and current:
            chunks.append(" ".join(current))
            # Carry overlap sentences forward
            overlap_sents: list[str] = []
            overlap_len = 0
            for s in reversed(current):
                if overlap_len + len(s) <= overlap:
                    overlap_sents.insert(0, s)
                    overlap_len += len(s)
                else:
                    break
            current = overlap_sents + [sent]
            current_len = sum(len(s) + 1 for s in current)
        else:
            current.append(sent)
            current_len += sent_len

    if current:
        chunks.append(" ".join(current))

    return [c for c in chunks if len(c.strip()) >= MIN_CHUNK_LEN]

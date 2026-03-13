"""
Semantic text chunking for RAG.

Strategy
--------
1. Split input on paragraph breaks (double newlines).
2. Accumulate paragraphs until the current chunk would exceed CHUNK_SIZE chars.
3. When flushing, carry CHUNK_OVERLAP chars of the previous chunk forward so
   context is preserved across boundaries.
4. Paragraphs that are individually larger than CHUNK_SIZE are further split
   at sentence boundaries using the same overlap logic.

Tuning
------
Default:  1 500 chars / 200 overlap  (good for narrative documents)
Financial: 500 chars / 100 overlap   (preserves line-item structure on
           tax returns, W-2s, K-1s, invoices, and financial statements)
MIN_CHUNK_LEN = 50  chars   — discard tiny noise fragments
"""

from __future__ import annotations

import re
from typing import Optional

CHUNK_SIZE = 1_500
CHUNK_OVERLAP = 200
MIN_CHUNK_LEN = 50

# Smaller chunks for structured financial documents so that individual
# line items, box values, and table rows stay intact within a single chunk.
FINANCIAL_CHUNK_SIZE = 500
FINANCIAL_CHUNK_OVERLAP = 100

FINANCIAL_DOC_TYPES: set[str] = {
    "tax_return",
    "w2",
    "k1",
    "financial_statement",
    "invoice",
}


def get_chunk_params(document_type: Optional[str] = None) -> tuple[int, int]:
    """
    Return (chunk_size, overlap) appropriate for the document type.

    Financial document types get smaller chunks to preserve line-item
    structure (500/100); everything else uses the default (1500/200).
    """
    if document_type and document_type.lower() in FINANCIAL_DOC_TYPES:
        return FINANCIAL_CHUNK_SIZE, FINANCIAL_CHUNK_OVERLAP
    return CHUNK_SIZE, CHUNK_OVERLAP


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def chunk_text(
    text: str,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[str]:
    """
    Split *text* into overlapping chunks of at most *chunk_size* characters.

    Returns a list of non-empty strings, each at least MIN_CHUNK_LEN chars.
    """
    if not text or not text.strip():
        return []

    # Normalise: collapse runs of blank lines
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

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

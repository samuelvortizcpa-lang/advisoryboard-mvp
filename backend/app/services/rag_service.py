"""
RAG service: embedding pipeline, semantic search, and Q&A over client documents.

Pipeline
--------
process_document_task(document_id)
  └─ opens its own DB session (safe for BackgroundTasks)
  └─ calls process_document(db, document)
        ├─ extract_text()        → raw string
        ├─ chunk_text()          → list[str]
        ├─ OpenAI batch embed    → list[list[float]]
        ├─ bulk-insert DocumentChunk rows
        └─ mark Document.processed = True

Query
-----
search_chunks(db, client_id, query, limit)
  └─ embed query → cosine-distance ORDER BY → top-k DocumentChunks

answer_question(db, client_id, question)
  └─ search_chunks → build context → gpt-4o chat completion (text only)
"""

from __future__ import annotations

import logging
import os
import re
from uuid import UUID

from openai import AsyncOpenAI
from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.models.client import Client
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.document_page_image import DocumentPageImage
from app.services import gemini_embeddings, storage_service
from app.services.chunking import chunk_text, get_chunk_params
from app.services.text_extraction import ExtractionError, UnsupportedFileType, extract_text

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

EMBEDDING_MODEL = "text-embedding-3-small"   # 1 536 dims, matches schema
CHAT_MODEL = "gpt-4o"
TOP_K = 5          # chunks retrieved per query
EMBED_BATCH = 100  # OpenAI allows up to 2 048 inputs per call

DEFAULT_SYSTEM_PROMPT = """\
You are an AI assistant for an advisory board platform used by CPA firms.
Your role is to help CPAs quickly understand their clients' financial and business situations.

Answer questions using ONLY the context provided below.
- If the answer is not in the context, say so clearly — do not guess.
- Be concise, accurate, and professional.
- Always name the specific document(s) you are drawing information from (e.g. "According to Q3-2024-PnL.pdf…").
- Clearly distinguish between direct citations from documents and your own inferences or interpretations. Use phrases like "The document states…" for citations and "Based on this, it appears…" for inferences.
- If no source passages are sufficiently relevant, decline to answer rather than speculate.

Financial document precision:
- When referencing tax returns, cite specific line numbers, box numbers, or schedule names (e.g. "Form 1040, Line 11" or "Schedule C, Line 31").
- Always quote exact dollar amounts as they appear in the source (e.g. "$142,350" not "about $142k").
- For W-2s and K-1s, reference specific box numbers (e.g. "Box 1: Wages" or "Box 14: Self-employment earnings").
- If a visual page image is available, note the page number for the user's reference (e.g. "See page 3 of the return").

IRS Form 1040 line reference:
- Line 9 = Total Income (sum of all income sources before adjustments).
- Line 11 = Adjusted Gross Income (AGI, after above-the-line adjustments).
- Line 15 = Taxable Income (after deductions).
These are DIFFERENT values. When asked about "total income", report Line 9.
When asked about "taxable income", report Line 15.
When asked about "AGI" or "adjusted gross income", report Line 11.
Always include the line number and exact dollar amount in your response.

Context:
{context}
"""


# ---------------------------------------------------------------------------
# OpenAI client helper
# ---------------------------------------------------------------------------


def _openai() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=get_settings().openai_api_key)


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------


async def embed_text(text: str) -> list[float]:
    """Return a 1 536-dim embedding for *text*."""
    client = _openai()
    response = await client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text.replace("\n", " "),
    )
    return response.data[0].embedding


# ---------------------------------------------------------------------------
# Document versioning
# ---------------------------------------------------------------------------


def _check_supersede(db: Session, new_doc: Document) -> None:
    """
    If an older document of the same type+subtype exists for the same client,
    and the new document has a more recent period, mark the older one as
    superseded.
    """
    older_docs = (
        db.query(Document)
        .filter(
            Document.client_id == new_doc.client_id,
            Document.id != new_doc.id,
            Document.document_type == new_doc.document_type,
            Document.document_subtype == new_doc.document_subtype,
            Document.document_period.isnot(None),
            Document.is_superseded == False,  # noqa: E712
        )
        .all()
    )

    for older in older_docs:
        # Simple string comparison works for formats like "2023", "2024",
        # "Q1 2024" < "Q2 2024", etc.
        if (older.document_period or "") < (new_doc.document_period or ""):
            older.is_superseded = True
            older.superseded_by = new_doc.id
            logger.info(
                "Versioning: %s (%s) superseded by %s (%s)",
                older.id, older.document_period,
                new_doc.id, new_doc.document_period,
            )

    db.commit()


# ---------------------------------------------------------------------------
# Document processing pipeline
# ---------------------------------------------------------------------------


async def process_document_task(document_id: UUID) -> None:
    """
    Background-task entry point.

    Creates its own database session so it can safely run after the HTTP
    request that triggered it has already closed its session.
    """
    from app.core.database import SessionLocal

    db: Session = SessionLocal()
    try:
        document = db.query(Document).filter(Document.id == document_id).first()
        if document is None:
            logger.warning("process_document_task: document %s not found", document_id)
            return
        await process_document(db, document)
    finally:
        db.close()


async def process_document(db: Session, document: Document) -> None:
    """
    Full pipeline: extract → chunk → embed → store.

    Marks *document.processed = True* on success, or stores an error message
    in *document.processing_error* on failure.
    """
    doc_label = f"{document.id} ({document.filename!r})"
    logger.info("RAG: starting processing for %s", doc_label)

    try:
        # 1. Extract text — download from Supabase Storage to a temp file
        temp_path = None
        try:
            temp_path = storage_service.get_temp_local_path(document.file_path)
            text = extract_text(temp_path, document.file_type)
        except UnsupportedFileType as exc:
            raise ValueError(str(exc)) from exc
        except ExtractionError as exc:
            raise ValueError(str(exc)) from exc
        finally:
            if temp_path:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass

        if not text.strip():
            raise ValueError("No text could be extracted from this document.")

        # 1b. Classify document (best-effort — never fails the pipeline)
        try:
            from app.services.document_classifier import classify_document
            classification = await classify_document(text)
            document.document_type = classification["document_type"]
            document.document_subtype = classification["document_subtype"]
            document.document_period = classification["document_period"]
            document.classification_confidence = classification["classification_confidence"]
            db.flush()
            logger.info(
                "RAG: classified %s as %s / %s (%.0f%%)",
                doc_label,
                classification["document_type"],
                classification["document_subtype"],
                classification["classification_confidence"],
            )
        except Exception as cls_exc:
            logger.warning(
                "RAG: classification failed for %s (non-fatal): %s",
                doc_label, cls_exc,
            )

        # 2. Chunk (use smaller chunks for financial documents)
        chunk_size, chunk_overlap = get_chunk_params(document.document_type)
        chunks = chunk_text(text, chunk_size=chunk_size, overlap=chunk_overlap)
        if not chunks:
            raise ValueError("Document produced no usable text chunks after extraction.")

        logger.info(
            "RAG: %s → %d chars, %d chunks (size=%d, overlap=%d, type=%s)",
            doc_label, len(text), len(chunks), chunk_size, chunk_overlap,
            document.document_type or "default",
        )

        # 3. Delete stale chunks (handles re-processing)
        db.query(DocumentChunk).filter(DocumentChunk.document_id == document.id).delete()
        db.flush()

        # 4. Batch embed + insert
        client = _openai()
        chunk_rows: list[DocumentChunk] = []

        for batch_start in range(0, len(chunks), EMBED_BATCH):
            batch = chunks[batch_start : batch_start + EMBED_BATCH]

            response = await client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=[c.replace("\n", " ") for c in batch],
            )

            for local_i, (chunk_text_val, emb_data) in enumerate(
                zip(batch, response.data)
            ):
                chunk_rows.append(
                    DocumentChunk(
                        document_id=document.id,
                        client_id=document.client_id,
                        chunk_text=chunk_text_val,
                        chunk_index=batch_start + local_i,
                        embedding=emb_data.embedding,
                    )
                )

        db.bulk_save_objects(chunk_rows)

        # 5. Mark processed
        document.processed = True
        document.processing_error = None
        db.commit()

        logger.info(
            "RAG: finished %s — %d chunks stored", doc_label, len(chunk_rows)
        )

        # 6. Extract action items (best-effort — never fails the pipeline)
        try:
            from app.services.action_item_extractor import extract_action_items
            extracted = await extract_action_items(
                db, text, document.id, document.client_id
            )
            logger.info(
                "RAG: extracted %d action item(s) for %s", len(extracted), doc_label
            )
        except Exception as ai_exc:
            logger.warning(
                "RAG: action item extraction failed for %s (non-fatal): %s",
                doc_label,
                ai_exc,
            )

        # 7. Version check — supersede older documents of same type+subtype
        try:
            if document.document_type and document.document_period:
                _check_supersede(db, document)
        except Exception as ver_exc:
            logger.warning(
                "RAG: versioning check failed for %s (non-fatal): %s",
                doc_label, ver_exc,
            )

        # 8. Page image processing for PDFs (best-effort — multimodal RAG)
        if document.file_type == "pdf":
            try:
                from app.services.page_image_service import process_page_images
                await process_page_images(db, document)
            except Exception as img_exc:
                logger.warning(
                    "RAG: page image processing failed for %s (non-fatal): %s",
                    doc_label, img_exc,
                )

    except Exception as exc:
        logger.error("RAG: failed to process %s: %s", doc_label, exc)
        db.rollback()

        # Persist the error message (fresh fetch after rollback)
        doc = db.query(Document).filter(Document.id == document.id).first()
        if doc:
            doc.processed = False
            doc.processing_error = str(exc)[:1000]
            db.commit()


# ---------------------------------------------------------------------------
# Semantic search
# ---------------------------------------------------------------------------


async def search_chunks(
    db: Session,
    client_id: UUID,
    query: str,
    limit: int = TOP_K,
) -> list[tuple[DocumentChunk, float]]:
    """
    Return the *limit* most semantically similar DocumentChunks for *query*
    within the given client's documents, along with a confidence score (0–100).

    Uses a JOIN through Document to double-verify client ownership — guards
    against any data-integrity drift in the denormalised client_id column.
    """
    if not query.strip():
        return []

    query_embedding = await embed_text(query)

    distance_col = DocumentChunk.embedding.cosine_distance(query_embedding).label("distance")

    rows = (
        db.query(DocumentChunk, distance_col)
        .join(Document, DocumentChunk.document_id == Document.id)
        .filter(
            DocumentChunk.client_id == client_id,
            Document.client_id == client_id,
            DocumentChunk.embedding.isnot(None),
        )
        .order_by(distance_col)
        .limit(limit)
        .all()
    )

    results: list[tuple[DocumentChunk, float]] = []
    for chunk, distance in rows:
        # Convert cosine distance (0–2) to confidence percentage (0–100)
        confidence = (1 - distance / 2) * 100

        # Recency boost: +5% for chunks from non-superseded (current) documents
        doc = chunk.document
        if doc and not doc.is_superseded:
            confidence = min(100.0, confidence + 5.0)

        results.append((chunk, round(confidence, 2)))

        # Defensive log: should never fire if data is consistent
        if chunk.client_id != client_id:
            logger.error(
                "ISOLATION BREACH: chunk %s has client_id=%s but query "
                "requested client_id=%s",
                chunk.id, chunk.client_id, client_id,
            )

    return results


# ---------------------------------------------------------------------------
# Visual page image search (Gemini multimodal)
# ---------------------------------------------------------------------------

IMAGE_TOP_K = 3   # page images retrieved per query


async def search_page_images(
    db: Session,
    client_id: UUID,
    query: str,
    limit: int = IMAGE_TOP_K,
) -> list[tuple[DocumentPageImage, float]]:
    """
    Return the most visually similar document page images for *query*.

    Uses Gemini text embeddings to search against page image embeddings.
    Returns an empty list when Gemini is not configured (graceful fallback).
    """
    if not query.strip():
        return []

    if not gemini_embeddings.is_available():
        return []

    try:
        query_embedding = gemini_embeddings.embed_text(query)
    except Exception as exc:
        logger.warning("Page image search: Gemini embed failed: %s", exc)
        return []

    distance_col = DocumentPageImage.image_embedding.cosine_distance(
        query_embedding
    ).label("distance")

    rows = (
        db.query(DocumentPageImage, distance_col)
        .join(Document, DocumentPageImage.document_id == Document.id)
        .filter(
            Document.client_id == client_id,
            DocumentPageImage.image_embedding.isnot(None),
        )
        .order_by(distance_col)
        .limit(limit)
        .all()
    )

    results: list[tuple[DocumentPageImage, float]] = []
    for page_img, distance in rows:
        confidence = (1 - distance / 2) * 100
        results.append((page_img, round(confidence, 2)))

    return results


# ---------------------------------------------------------------------------
# Q&A
# ---------------------------------------------------------------------------


def _compute_confidence_tier(scores: list[float]) -> str:
    """
    Determine confidence tier from a list of chunk confidence scores.

    HIGH:   best score >= 85 AND at least 2 chunks above 70
    MEDIUM: best score >= 65
    LOW:    everything else
    """
    if not scores:
        return "low"

    best = max(scores)
    above_70 = sum(1 for s in scores if s >= 70)

    if best >= 85 and above_70 >= 2:
        return "high"
    if best >= 65:
        return "medium"
    return "low"


async def answer_question(
    db: Session,
    client_id: UUID,
    question: str,
) -> dict:
    """
    RAG Q&A: retrieve relevant chunks then synthesise an answer.

    Returns::

        {
            "answer": str,
            "confidence_tier": "high" | "medium" | "low",
            "confidence_score": float,
            "sources": [{"document_id": str, "filename": str, "preview": str,
                         "score": float, "chunk_text": str, "chunk_index": int}]
        }
    """
    # Text chunk search is the PRIMARY retrieval method.
    # Page images are looked up after to supplement matching chunks.
    chunk_results = await search_chunks(db, client_id, question, limit=TOP_K)

    if not chunk_results:
        return {
            "answer": (
                "I couldn't find any processed documents for this client. "
                "Please upload documents and click 'Process Documents' first."
            ),
            "confidence_tier": "low",
            "confidence_score": 0.0,
            "sources": [],
        }

    all_scores = [score for _, score in chunk_results]
    best_score = max(all_scores)
    confidence_tier = _compute_confidence_tier(all_scores)

    # DEBUG: log what text GPT-4o will actually receive
    for i, (chunk, score) in enumerate(chunk_results):
        doc = chunk.document
        fname = doc.filename if doc else "?"
        preview = chunk.chunk_text[:300].replace("\n", " ")
        logger.info(
            "RAG-DEBUG chunk %d/%d [%.1f%%] %s idx=%d: %s",
            i + 1, len(chunk_results), score, fname, chunk.chunk_index, preview,
        )

    # ------------------------------------------------------------------
    # Pre-load page images for documents in results (for chunk→page mapping)
    # ------------------------------------------------------------------
    doc_ids_in_results = set(
        str(chunk.document_id) for chunk, _ in chunk_results
    )

    page_images_by_doc: dict[str, list[DocumentPageImage]] = {}
    if doc_ids_in_results:
        all_page_imgs = (
            db.query(DocumentPageImage)
            .filter(DocumentPageImage.document_id.in_(
                [UUID(did) for did in doc_ids_in_results]
            ))
            .order_by(DocumentPageImage.page_number)
            .all()
        )
        for pi in all_page_imgs:
            page_images_by_doc.setdefault(str(pi.document_id), []).append(pi)

    def _normalize_words(text: str) -> set[str]:
        """Lowercase, strip punctuation, return word set."""
        return set(re.sub(r"[^\w\s]", "", text.lower()).split())

    def _match_chunk_to_page(
        chunk_text_val: str, doc_id: str
    ) -> DocumentPageImage | None:
        """
        Match a text chunk to the best page using word overlap with
        page_text_preview.  Returns None if no confident match is found
        (we'd rather show no page than a wrong page).
        """
        pages = page_images_by_doc.get(doc_id, [])
        if not pages:
            return None

        chunk_words = _normalize_words(chunk_text_val)
        if not chunk_words:
            return None

        best_page: DocumentPageImage | None = None
        best_overlap = 0

        for pi in pages:
            if not pi.page_text_preview:
                continue
            page_words = _normalize_words(pi.page_text_preview)
            overlap = len(chunk_words & page_words)
            if overlap > best_overlap:
                best_overlap = overlap
                best_page = pi

        # Require at least 10 overlapping words for confident match —
        # better to show no page number than a wrong one.
        if best_overlap >= 10:
            return best_page
        return None

    # ------------------------------------------------------------------
    # Build text-only context for GPT-4o (NO vision images — text only)
    # ------------------------------------------------------------------
    context_parts: list[str] = []

    for chunk, score in chunk_results:
        doc = chunk.document
        filename = doc.filename if doc else "unknown"
        doc_meta = f"Source: {filename} | Relevance: {score:.1f}%"
        if doc and doc.document_type:
            doc_meta += f" | Type: {doc.document_type}"
            if doc.document_subtype:
                doc_meta += f" ({doc.document_subtype})"
            if doc.document_period:
                doc_meta += f" | Period: {doc.document_period}"
            if doc.is_superseded:
                doc_meta += " | SUPERSEDED"

        context_parts.append(f"[{doc_meta}]\n{chunk.chunk_text}")

    context = "\n\n---\n\n".join(context_parts)

    # Build dynamic system prompt from client type
    db_client = (
        db.query(Client)
        .options(joinedload(Client.client_type))
        .filter(Client.id == client_id)
        .first()
    )

    if db_client and db_client.client_type:
        system_prompt = db_client.client_type.system_prompt.format(context=context)
    else:
        system_prompt = DEFAULT_SYSTEM_PROMPT.format(context=context)

    if db_client and db_client.custom_instructions:
        system_prompt += (
            f"\n\nAdditional instructions for this specific client:\n"
            f"{db_client.custom_instructions}"
        )

    # If no chunks score above 50%, let the model know it should decline
    if best_score < 50:
        system_prompt += (
            "\n\nIMPORTANT: The retrieved context has very low relevance scores "
            "(all below 50%). Politely decline to answer and explain that the "
            "available documents do not contain sufficient information to "
            "reliably answer this question."
        )

    # Chat completion — TEXT ONLY (no vision images sent to GPT-4o).
    # Page images caused GPT-4o to ignore text context and say "not provided".
    # Images are kept for UI display only (source card thumbnails + lightbox).
    openai_client = _openai()
    response = await openai_client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ],
        temperature=0.1,
        max_tokens=1_500,
    )

    answer = response.choices[0].message.content or "No answer generated."

    # ------------------------------------------------------------------
    # Build deduplicated source list (1 card per unique document page)
    # Uses text-overlap matching (already computed above via
    # _match_chunk_to_page) instead of the old chunk_index heuristic.
    # ------------------------------------------------------------------

    # Year-based relevance boost: if the question mentions a specific year,
    # boost sources from documents whose period matches that year by +10%.
    year_match = re.search(r"\b(20\d{2})\b", question)
    question_year = year_match.group(1) if year_match else None

    # Dict keyed by (document_id, page_number) → best source
    deduped: dict[tuple[str, int], dict] = {}

    for chunk, score in chunk_results:
        doc = chunk.document
        doc_id_str = str(chunk.document_id)
        filename = doc.filename if doc else "unknown"

        chunk_preview = chunk.chunk_text[:200]
        if len(chunk.chunk_text) > 200:
            chunk_preview += "…"

        # Year-based boost: +10% if question mentions a year and doc period matches
        boosted_score = score
        if question_year and doc and doc.document_period:
            if question_year in doc.document_period:
                boosted_score = min(100.0, score + 10.0)

        source_entry: dict = {
            "document_id": doc_id_str,
            "filename": filename,
            "preview": chunk_preview,
            "score": boosted_score,
            "chunk_text": chunk_preview,
            "chunk_index": chunk.chunk_index,
        }

        # Match chunk to page via text overlap (same function used above)
        page_img = _match_chunk_to_page(chunk.chunk_text, doc_id_str)
        page_num = page_img.page_number if page_img else 0

        if page_img:
            source_entry["page_number"] = page_img.page_number
            source_entry["image_path"] = page_img.image_path

        key = (doc_id_str, page_num)
        existing = deduped.get(key)
        if not existing or boosted_score > existing["score"]:
            deduped[key] = source_entry

    # Sort by score descending, cap at 4 unique source cards
    sources = sorted(deduped.values(), key=lambda s: s["score"], reverse=True)[:4]

    return {
        "answer": answer,
        "confidence_tier": confidence_tier,
        "confidence_score": round(best_score, 2),
        "sources": sources,
    }

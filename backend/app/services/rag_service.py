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

import asyncio
import logging
import os
import re
from uuid import UUID

import sentry_sdk
from openai import AsyncOpenAI
from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.models.client import Client
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.document_page_image import DocumentPageImage
from app.services import storage_service
from app.services.chunking import chunk_text, get_chunk_params
from app.services.query_router import classify_query, route_completion, route_completion_stream
from app.services.tax_terms import expand_query as expand_financial_terms
from app.services.text_extraction import ExtractionError, UnsupportedFileType, extract_text

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

EMBEDDING_MODEL = "text-embedding-3-small"   # 1 536 dims, matches schema
CHAT_MODEL = "gpt-4o"
TOP_K = 10          # chunks retrieved per query
FETCH_K = 30        # over-fetch for keyword re-ranking
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
- Line 9 = Total Income, Line 11 = Adjusted Gross Income (AGI), Line 15 = Taxable Income.
- These are different values. When answering, cite the most specific line item available in the context.
- If the exact line requested is not in the context but a closely related figure is available (e.g., AGI when total income is asked for), provide the available figure and explain which line it comes from and how it differs.
- Never say information is "not provided" if related financial data exists in the context — instead provide what IS available and note any caveats.
- Always include the exact dollar amount and line number.

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


def process_document_sync(document_id: str, database_url: str) -> None:
    """Synchronous entry point for ProcessPoolExecutor.

    Runs the full async pipeline in a new event loop inside a subprocess.
    Creates its own DB engine + session since SQLAlchemy objects can't cross
    process boundaries.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(database_url)
    _Session = sessionmaker(bind=engine)
    db = _Session()

    try:
        document = db.query(Document).filter(Document.id == document_id).first()
        if document is None:
            logger.warning("process_document_sync: document %s not found", document_id)
            return
        asyncio.run(process_document(db, document))
    except Exception as exc:
        logger.error("process_document_sync failed for %s: %s", document_id, exc)
    finally:
        db.close()
        engine.dispose()


async def process_document(db: Session, document: Document) -> None:
    """
    Full pipeline: extract → chunk → embed → store.

    Marks *document.processed = True* on success, or stores an error message
    in *document.processing_error* on failure.
    """
    doc_label = f"{document.id} ({document.filename!r})"
    logger.info("RAG: starting processing for %s", doc_label)

    # Image files (screenshots, photos) have no extractable text — mark processed
    _IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff"}
    file_ext = ("." + (document.file_type or "").lower().lstrip("."))
    if file_ext in _IMAGE_EXTENSIONS:
        logger.info("RAG: image file detected for %s — skipping text extraction", doc_label)
        document.processed = True
        document.processing_error = None
        db.commit()
        return

    try:
        # 1. Extract text — download from Supabase Storage to a temp file
        temp_path = None
        try:
            temp_path = await asyncio.to_thread(
                storage_service.get_temp_local_path, document.file_path
            )
            text = await asyncio.to_thread(extract_text, temp_path, document.file_type)
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
            # Check if this is a tax document — trigger §7216 consent tracking
            try:
                from app.services.consent_service import check_tax_document_upload
                check_tax_document_upload(
                    document.client_id,
                    classification["document_type"],
                    db,
                )
            except Exception as consent_exc:
                logger.warning(
                    "RAG: consent check failed for %s (non-fatal): %s",
                    doc_label, consent_exc,
                )

        except Exception as cls_exc:
            logger.warning(
                "RAG: classification failed for %s (non-fatal): %s",
                doc_label, cls_exc,
            )

        # 1c. §7216 consent gate — skip embedding for tax docs without consent
        client_obj = db.query(Client).filter(Client.id == document.client_id).first()
        if (
            client_obj
            and client_obj.has_tax_documents
            and client_obj.consent_status not in ("obtained", "acknowledged", "not_required")
        ):
            document.processed = False
            document.processing_error = (
                "Awaiting IRC §7216 consent — document will be processed "
                "automatically when consent is obtained."
            )
            db.commit()
            logger.info(
                "RAG: skipping embedding for %s — consent status is %r",
                doc_label, client_obj.consent_status,
            )
            return

        # 2. Chunk (use smaller chunks for financial documents)
        chunk_size, chunk_overlap = get_chunk_params(document.document_type)
        chunks = await asyncio.to_thread(chunk_text, text, chunk_size, chunk_overlap)
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
        sentry_sdk.capture_exception(exc)
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

    Uses multi-query retrieval for financial terms: the original query is
    searched alongside an expanded query that includes synonym/line-number
    expansions (e.g. "AGI" → "Adjusted Gross Income, Line 11, Form 1040").
    Results are merged, deduplicated, and re-ranked with keyword + form
    boosting so that the chunk containing the actual answer rises to the top.
    """
    if not query.strip():
        return []

    # --- Financial term expansion ---
    expansion_terms, relevant_forms = expand_financial_terms(query)
    if expansion_terms:
        logger.info(
            "Term expansion: %s → expansions=%s, forms=%s",
            query, expansion_terms[:5], relevant_forms,
        )

    # --- Multi-query: embed original + expanded query ---
    queries_to_embed = [query]
    if expansion_terms:
        expanded_query = query + " " + " ".join(expansion_terms[:6])
        queries_to_embed.append(expanded_query)

    client = _openai()
    embed_response = await client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=[q.replace("\n", " ") for q in queries_to_embed],
    )
    embeddings = [d.embedding for d in embed_response.data]

    # --- Run vector search for each embedding and merge ---
    seen_chunk_ids: set = set()
    all_rows: list[tuple[DocumentChunk, float, str]] = []  # (chunk, distance, source)

    for embed_idx, query_embedding in enumerate(embeddings):
        source = "original" if embed_idx == 0 else "expanded"
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
            .limit(FETCH_K)
            .all()
        )

        for chunk, distance in rows:
            if chunk.id not in seen_chunk_ids:
                seen_chunk_ids.add(chunk.id)
                all_rows.append((chunk, distance, source))

    # --- Build keyword phrases from query for boosting ---
    query_lower = query.lower()
    tokens = query_lower.split()
    key_phrases: list[str] = []
    for n in (3, 2):
        for i in range(len(tokens) - n + 1):
            phrase = " ".join(tokens[i:i+n])
            if phrase not in ("of the", "on the", "is the", "what is",
                              "what are", "in the", "for the", "from the"):
                key_phrases.append(phrase)
    for t in tokens:
        if len(t) >= 4 and t not in ("what", "this", "that", "from",
                                      "with", "your", "about", "which"):
            key_phrases.append(t)

    # Also add expansion terms as keyword phrases for direct text matching
    for term in expansion_terms:
        if term.lower() not in {p.lower() for p in key_phrases}:
            key_phrases.append(term.lower())

    # --- Score and rank ---
    results: list[tuple[DocumentChunk, float]] = []
    for chunk, distance, source in all_rows:
        # Convert cosine distance (0–2) to confidence percentage (0–100)
        confidence = (1 - distance / 2) * 100

        # Recency boost: +5% for chunks from non-superseded (current) documents
        doc = chunk.document
        if doc and not doc.is_superseded:
            confidence = min(100.0, confidence + 5.0)

        # Keyword boost: +3% per matching query phrase, +5% per expansion term
        chunk_lower = (chunk.chunk_text or "").lower()
        keyword_boost = 0.0
        for phrase in key_phrases:
            if phrase in chunk_lower:
                # Expansion terms get a stronger boost since they represent
                # domain-specific matches (e.g. "line 11" in a chunk about AGI)
                if phrase in {e.lower() for e in expansion_terms}:
                    keyword_boost += 5.0
                else:
                    keyword_boost += 3.0
        confidence = min(100.0, confidence + keyword_boost)

        # Form-type boost: if chunk text mentions a relevant form, boost it.
        # Chunks with [Page N] markers that contain "Form 1040" should rank
        # higher when the user asks about AGI.
        if relevant_forms:
            form_boost = 0.0
            for form_name in relevant_forms:
                # Match "form 1040", "1040", "schedule c", "schedule a", etc.
                if form_name.lower() in chunk_lower:
                    form_boost += 5.0
            if form_boost > 0:
                confidence = min(100.0, confidence + form_boost)
                logger.info(
                    "Form boost +%.1f%% for chunk %d (forms: %s)",
                    form_boost, chunk.chunk_index, relevant_forms,
                )

        if keyword_boost > 0:
            logger.info(
                "Keyword boost +%.1f%% for chunk %d (%s query)",
                keyword_boost, chunk.chunk_index, source,
            )

        results.append((chunk, round(confidence, 2)))

        # Defensive log: should never fire if data is consistent
        if chunk.client_id != client_id:
            logger.error(
                "ISOLATION BREACH: chunk %s has client_id=%s but query "
                "requested client_id=%s",
                chunk.id, chunk.client_id, client_id,
            )

    # Re-rank by boosted confidence and return top *limit*
    results.sort(key=lambda r: r[1], reverse=True)
    return results[:limit]


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


def _sanitize_user_input(text: str, max_length: int = 2000) -> str:
    """
    Sanitize user input before including it in LLM prompts.

    - Truncates to max_length to prevent token abuse
    - Strips common prompt injection delimiters
    """
    text = text[:max_length]
    # Strip sequences that attempt to override system instructions
    for marker in ("```system", "```assistant", "<|im_start|>", "<|im_end|>",
                   "<<SYS>>", "<</SYS>>", "[INST]", "[/INST]"):
        text = text.replace(marker, "")
    return text.strip()


async def answer_question(
    db: Session,
    client_id: UUID,
    question: str,
    user_id: str | None = None,
    model_override: str | None = None,
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
    question = _sanitize_user_input(question)
    chunk_results = await search_chunks(db, client_id, question, limit=TOP_K)

    # ---- Keyword fallback: direct text search for specific phrases ----
    # Vector search alone struggles with structured forms (tax returns) where
    # many chunks have near-identical embeddings.  Search for:
    #   1. Query bigrams (e.g. "2024 agi")
    #   2. Financial term expansions (e.g. "adjusted gross income", "line 11")
    import re as _re_kw
    _kw_tokens = question.lower().split()
    _kw_bigrams = [
        " ".join(_kw_tokens[i:i+2])
        for i in range(len(_kw_tokens) - 1)
    ]
    # Keep only meaningful bigrams (skip stop-word pairs)
    _stop_bigrams = {"what is", "is the", "of the", "on the", "in the", "for the", "from the"}
    _kw_bigrams = [b for b in _kw_bigrams if b not in _stop_bigrams and len(b) > 5]

    # Add financial term expansions to the keyword search
    _expansion_terms, _relevant_forms = expand_financial_terms(question)
    _kw_search_phrases = list(_kw_bigrams)
    for term in _expansion_terms:
        if len(term) >= 4 and term.lower() not in {b.lower() for b in _kw_search_phrases}:
            _kw_search_phrases.append(term.lower())

    # Track which keyword phrase matched each fallback chunk (for page matching)
    _keyword_for_chunk: dict[int, str] = {}

    if _kw_search_phrases:
        existing_chunk_ids = {id(c) for c, _ in chunk_results}
        for phrase in _kw_search_phrases[:8]:  # search up to 8 phrases
            pattern = f"%{phrase}%"
            keyword_rows = (
                db.query(DocumentChunk)
                .join(Document, DocumentChunk.document_id == Document.id)
                .filter(
                    DocumentChunk.client_id == client_id,
                    Document.client_id == client_id,
                    DocumentChunk.chunk_text.ilike(pattern),
                )
                .limit(5)
                .all()
            )
            for kw_chunk in keyword_rows:
                if id(kw_chunk) not in existing_chunk_ids:
                    existing_chunk_ids.add(id(kw_chunk))
                    _keyword_for_chunk[id(kw_chunk)] = phrase
                    # Expansion-matched chunks get high confidence
                    kw_score = 92.0 if phrase in {e.lower() for e in _expansion_terms} else 90.0
                    chunk_results.append((kw_chunk, kw_score))
                    logger.info(
                        "Keyword fallback: added chunk %d from %s (matched '%s')",
                        kw_chunk.chunk_index,
                        kw_chunk.document.filename if kw_chunk.document else "?",
                        phrase,
                    )

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

    # Even with low-scoring chunks, prefer providing available data over declining
    if best_score < 50:
        system_prompt += (
            "\n\nNote: The retrieved context has low relevance scores. "
            "If the context contains relevant financial data, always provide "
            "the best answer possible from available information rather than "
            "declining to answer. Only decline if the context is truly unrelated "
            "to the question."
        )

    # Classify and route to appropriate model
    if model_override == "fast":
        query_type = "factual"
    elif model_override == "balanced":
        query_type = "strategic"
    elif model_override == "opus":
        query_type = "opus"
    else:
        query_type = await classify_query(
            question, db=db, user_id=user_id, client_id=client_id
        )
    # Resolve client type name for domain-specific prompts
    _client_type_name = (
        db_client.client_type.name
        if db_client and db_client.client_type
        else None
    )
    route_result = await route_completion(
        query_type, system_prompt, question,
        db=db, user_id=user_id, client_id=client_id,
        client_type=_client_type_name,
    )
    answer = route_result["answer"]
    model_used = route_result["model_used"]
    quota_remaining = route_result.get("quota_remaining")
    quota_warning = route_result.get("quota_warning")

    # ------------------------------------------------------------------
    # Build deduplicated source list — answer-aware page matching
    #
    # Instead of mapping chunks→pages (unreliable on tax forms where many
    # pages share vocabulary), we directly scan page_text_preview for:
    #   (a) dollar values extracted from the AI answer
    #   (b) key phrases from the question (reuse _kw_bigrams)
    # Pages that contain the actual answer values are prioritised.
    # ------------------------------------------------------------------

    year_match = re.search(r"\b(20\d{2})\b", question)
    question_year = year_match.group(1) if year_match else None

    # --- Extract dollar values from the AI answer ---
    # "$164,195" → {"164,195", "164195"}
    answer_dollar_hits = re.findall(r"\$[\d,]+(?:\.\d+)?", answer)
    answer_values: set[str] = set()
    for raw in answer_dollar_hits:
        cleaned = raw.lstrip("$")           # "164,195"
        answer_values.add(cleaned)
        answer_values.add(cleaned.replace(",", ""))  # "164195"

    # --- Build relevance phrases from the question ---
    # Reuse _kw_bigrams (e.g. "total income", "line 9") already computed above.
    # Also include financial term expansions and "line N" patterns.
    question_phrases: list[str] = list(_kw_bigrams)
    for term in _expansion_terms:
        if term.lower() not in {p.lower() for p in question_phrases}:
            question_phrases.append(term.lower())
    line_match = re.search(r"line\s+\d+", question, re.IGNORECASE)
    if line_match:
        question_phrases.append(line_match.group(0).lower())

    def _page_relevance_score(
        page_text: str, page_number: int = 1
    ) -> tuple[int, bool]:
        """
        Score a page's text preview by how many answer values and question
        phrases it contains.

        Returns (total_score, has_answer_value).

        Scoring:
        - Each answer-value match:  10 pts
        - Each question-phrase match: 5 pts
        - If a page has BOTH value + phrase hits: 3× multiplier on value pts
          (the page where the line item lives, not just a cross-reference)
        - Early-page bonus: pages 1-3 get +20 pts, pages 4-5 get +10 pts
          (tax return summary data is always on early pages)
        """
        pt = page_text.lower()
        value_pts = sum(10 for val in answer_values if val in pt)
        phrase_pts = sum(5 for phrase in question_phrases if phrase in pt)

        has_value = value_pts > 0

        # 3× multiplier on value points when the page also has phrase matches
        if value_pts and phrase_pts:
            value_pts *= 3

        # Early-page bonus: summary pages (1040 page 1-2) get strong preference
        if page_number <= 3:
            page_bonus = 20
        elif page_number <= 5:
            page_bonus = 10
        else:
            page_bonus = 0

        return value_pts + phrase_pts + page_bonus, has_value

    # --- Collect candidate documents (year-filtered) ---
    doc_map: dict[str, Document] = {}       # doc_id_str → Document
    best_chunk_score: dict[str, float] = {} # doc_id_str → best boosted score
    best_chunk_preview: dict[str, str] = {} # doc_id_str → preview text
    best_chunk_index: dict[str, int] = {}   # doc_id_str → chunk_index

    for chunk, score in chunk_results:
        doc = chunk.document
        doc_id_str = str(chunk.document_id)
        filename = doc.filename if doc else "unknown"

        # Year filtering
        if question_year:
            year_in_filename = question_year in filename
            year_in_period = doc and doc.document_period and question_year in doc.document_period
            if not year_in_filename and not year_in_period:
                continue

        boosted_score = score
        if question_year and doc and doc.document_period:
            if question_year in doc.document_period:
                boosted_score = min(100.0, score + 10.0)

        doc_map[doc_id_str] = doc
        if boosted_score > best_chunk_score.get(doc_id_str, 0):
            best_chunk_score[doc_id_str] = boosted_score
            preview = chunk.chunk_text[:200]
            if len(chunk.chunk_text) > 200:
                preview += "…"
            best_chunk_preview[doc_id_str] = preview
            best_chunk_index[doc_id_str] = chunk.chunk_index

    # --- Score every page of each candidate document ---
    # Two tiers: pages with answer values (preferred) and phrase-only pages (fallback)
    value_pages: list[tuple[int, int, str, DocumentPageImage]] = []
    phrase_only_pages: list[tuple[int, int, str, DocumentPageImage]] = []
    # Each tuple: (relevance_score, page_number, doc_id_str, page_image)

    for doc_id_str in doc_map:
        pages = page_images_by_doc.get(doc_id_str, [])
        for pi in pages:
            if not pi.page_text_preview:
                continue
            rel, has_value = _page_relevance_score(pi.page_text_preview, pi.page_number)
            if rel > 0:
                entry = (rel, pi.page_number, doc_id_str, pi)
                if has_value:
                    value_pages.append(entry)
                else:
                    phrase_only_pages.append(entry)

    # Log top 3 scored pages for debugging source card selection
    all_scored = value_pages + phrase_only_pages
    all_scored.sort(key=lambda t: (-t[0], t[1]))
    for rel, pg, did, _ in all_scored[:3]:
        logger.info("Page scoring: doc=%s page=%d score=%d", did, pg, rel)

    # Prefer pages that contain answer values; fall back to phrase-only
    # pages when no value-matching pages exist (e.g. non-financial questions).
    scored_pages = value_pages if value_pages else phrase_only_pages

    # Sort: highest relevance first, then lowest page number (earlier pages
    # preferred — e.g. page 1 of 1040 has summary lines).
    scored_pages.sort(key=lambda t: (-t[0], t[1]))

    # --- Build source cards from the best pages (max 3 total, max 2 per doc) ---
    sources: list[dict] = []
    seen_doc_pages: set[tuple[str, int]] = set()
    doc_card_count: dict[str, int] = {}     # doc_id → cards shown

    for rel, page_num, doc_id_str, pi in scored_pages:
        if len(sources) >= 3:
            break
        if doc_card_count.get(doc_id_str, 0) >= 2:
            continue
        key = (doc_id_str, page_num)
        if key in seen_doc_pages:
            continue
        seen_doc_pages.add(key)
        doc_card_count[doc_id_str] = doc_card_count.get(doc_id_str, 0) + 1

        doc = doc_map[doc_id_str]
        # Use page text preview snippet as the card preview
        page_preview = pi.page_text_preview[:200]
        if len(pi.page_text_preview) > 200:
            page_preview += "…"

        sources.append({
            "document_id": doc_id_str,
            "filename": doc.filename if doc else "unknown",
            "preview": page_preview,
            "score": best_chunk_score.get(doc_id_str, 0),
            "chunk_text": best_chunk_preview.get(doc_id_str, page_preview),
            "chunk_index": best_chunk_index.get(doc_id_str, 0),
            "page_number": pi.page_number,
            "image_path": pi.image_path,
        })

    # --- Fallback for documents with no page images (e.g. not yet processed) ---
    if not sources:
        for doc_id_str, doc in doc_map.items():
            if len(sources) >= 3:
                break
            preview = best_chunk_preview.get(doc_id_str, "")
            sources.append({
                "document_id": doc_id_str,
                "filename": doc.filename if doc else "unknown",
                "preview": preview,
                "score": best_chunk_score.get(doc_id_str, 0),
                "chunk_text": preview,
                "chunk_index": best_chunk_index.get(doc_id_str, 0),
                "page_number": 1,
            })

    return {
        "answer": answer,
        "confidence_tier": confidence_tier,
        "confidence_score": round(best_score, 2),
        "sources": sources,
        "model_used": model_used,
        "query_type": query_type,
        "quota_remaining": quota_remaining,
        "quota_warning": quota_warning,
    }


async def answer_question_stream(
    db: Session,
    client_id: UUID,
    question: str,
    user_id: str | None = None,
    model_override: str | None = None,
):
    """
    Streaming variant of answer_question. Yields SSE-formatted strings.

    Reuses all the same retrieval/context logic, but streams the LLM
    response token-by-token. Sends sources as a final SSE event.
    """
    import json as _json

    question = _sanitize_user_input(question)

    # ── Retrieval phase (identical to answer_question) ──
    chunk_results = await search_chunks(db, client_id, question, limit=TOP_K)

    # Keyword fallback
    _kw_tokens = question.lower().split()
    _kw_bigrams = [
        " ".join(_kw_tokens[i:i+2]) for i in range(len(_kw_tokens) - 1)
    ]
    _stop_bigrams = {"what is", "is the", "of the", "on the", "in the", "for the", "from the"}
    _kw_bigrams = [b for b in _kw_bigrams if b not in _stop_bigrams and len(b) > 5]

    _expansion_terms, _relevant_forms = expand_financial_terms(question)
    _kw_search_phrases = list(_kw_bigrams)
    for term in _expansion_terms:
        if len(term) >= 4 and term.lower() not in {b.lower() for b in _kw_search_phrases}:
            _kw_search_phrases.append(term.lower())

    if _kw_search_phrases:
        existing_chunk_ids = {id(c) for c, _ in chunk_results}
        for phrase in _kw_search_phrases[:8]:
            pattern = f"%{phrase}%"
            keyword_rows = (
                db.query(DocumentChunk)
                .join(Document, DocumentChunk.document_id == Document.id)
                .filter(
                    DocumentChunk.client_id == client_id,
                    Document.client_id == client_id,
                    DocumentChunk.chunk_text.ilike(pattern),
                )
                .limit(5)
                .all()
            )
            for kw_chunk in keyword_rows:
                if id(kw_chunk) not in existing_chunk_ids:
                    existing_chunk_ids.add(id(kw_chunk))
                    kw_score = 92.0 if phrase in {e.lower() for e in _expansion_terms} else 90.0
                    chunk_results.append((kw_chunk, kw_score))

    if not chunk_results:
        yield 'data: {"type":"token","content":"I couldn\'t find any processed documents for this client."}\n\n'
        yield 'data: {"type":"done","sources":[],"confidence_tier":"low","confidence_score":0.0,"model_used":"none","query_type":"factual"}\n\n'
        return

    all_scores = [score for _, score in chunk_results]
    best_score = max(all_scores)
    confidence_tier = _compute_confidence_tier(all_scores)

    # ── Build context (same as answer_question) ──
    context_parts: list[str] = []
    for chunk, score in chunk_results:
        doc = chunk.document
        filename = doc.filename if doc else "unknown"
        doc_meta = f"Source: {filename} | Relevance: {score:.1f}%"
        if doc and doc.document_type:
            doc_meta += f" | Type: {doc.document_type}"
        context_parts.append(f"[{doc_meta}]\n{chunk.chunk_text}")

    context = "\n\n---\n\n".join(context_parts)

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
        system_prompt += f"\n\nAdditional instructions for this specific client:\n{db_client.custom_instructions}"

    if best_score < 50:
        system_prompt += (
            "\n\nNote: The retrieved context has low relevance scores. "
            "If the context contains relevant financial data, always provide "
            "the best answer possible from available information rather than "
            "declining to answer."
        )

    # ── Classify query type ──
    if model_override == "fast":
        query_type = "factual"
    elif model_override == "balanced":
        query_type = "strategic"
    else:
        query_type = await classify_query(
            question, db=db, user_id=user_id, client_id=client_id
        )

    _client_type_name = (
        db_client.client_type.name if db_client and db_client.client_type else None
    )

    # ── Stream the LLM response ──
    full_answer = ""
    model_used = "gpt-4o-mini"
    quota_remaining = None
    quota_warning = None

    async for token, metadata in route_completion_stream(
        query_type, system_prompt, question,
        db=db, user_id=user_id, client_id=client_id,
        client_type=_client_type_name,
    ):
        if token is not None:
            full_answer += token
            yield f'data: {_json.dumps({"type": "token", "content": token})}\n\n'
        elif metadata is not None:
            model_used = metadata.get("model_used", "gpt-4o-mini")
            quota_remaining = metadata.get("quota_remaining")
            quota_warning = metadata.get("quota_warning")

    # ── Build sources (simplified — skip page image scoring for streaming) ──
    year_match = re.search(r"\b(20\d{2})\b", question)
    question_year = year_match.group(1) if year_match else None

    doc_map: dict[str, Document] = {}
    best_chunk_score: dict[str, float] = {}
    best_chunk_preview: dict[str, str] = {}
    best_chunk_index: dict[str, int] = {}

    for chunk, score in chunk_results:
        doc = chunk.document
        doc_id_str = str(chunk.document_id)
        filename = doc.filename if doc else "unknown"

        if question_year:
            year_in_filename = question_year in filename
            year_in_period = doc and doc.document_period and question_year in doc.document_period
            if not year_in_filename and not year_in_period:
                continue

        boosted_score = score
        if question_year and doc and doc.document_period and question_year in doc.document_period:
            boosted_score = min(100.0, score + 10.0)

        doc_map[doc_id_str] = doc
        if boosted_score > best_chunk_score.get(doc_id_str, 0):
            best_chunk_score[doc_id_str] = boosted_score
            preview = chunk.chunk_text[:200]
            if len(chunk.chunk_text) > 200:
                preview += "…"
            best_chunk_preview[doc_id_str] = preview
            best_chunk_index[doc_id_str] = chunk.chunk_index

    # Page image matching for sources
    doc_ids_in_results = set(doc_map.keys())
    page_images_by_doc: dict[str, list[DocumentPageImage]] = {}
    if doc_ids_in_results:
        all_page_imgs = (
            db.query(DocumentPageImage)
            .filter(DocumentPageImage.document_id.in_([UUID(did) for did in doc_ids_in_results]))
            .order_by(DocumentPageImage.page_number)
            .all()
        )
        for pi in all_page_imgs:
            page_images_by_doc.setdefault(str(pi.document_id), []).append(pi)

    # Build source cards (max 3)
    sources: list[dict] = []
    for doc_id_str, doc in list(doc_map.items())[:3]:
        source = {
            "document_id": doc_id_str,
            "filename": doc.filename if doc else "unknown",
            "preview": best_chunk_preview.get(doc_id_str, ""),
            "score": best_chunk_score.get(doc_id_str, 0),
            "chunk_text": best_chunk_preview.get(doc_id_str, ""),
            "chunk_index": best_chunk_index.get(doc_id_str, 0),
        }

        # Try to find the best page image
        pages = page_images_by_doc.get(doc_id_str, [])
        if pages:
            source["page_number"] = pages[0].page_number
            if pages[0].image_path:
                try:
                    source["image_url"] = storage_service.get_signed_url(
                        pages[0].image_path, expires_in=3600
                    )
                except Exception:
                    pass
                source["image_path"] = pages[0].image_path
        else:
            source["page_number"] = 1

        sources.append(source)

    # Persist chat messages
    from app.models.chat_message import ChatMessage
    db.add(ChatMessage(
        client_id=client_id, user_id=user_id, role="user",
        content=question, sources=None,
    ))
    db.add(ChatMessage(
        client_id=client_id, user_id=user_id, role="assistant",
        content=full_answer, sources=sources or None,
    ))
    db.commit()

    # Send final event with metadata
    yield f'data: {_json.dumps({"type": "done", "sources": sources, "confidence_tier": confidence_tier, "confidence_score": round(best_score, 2), "model_used": model_used, "query_type": query_type, "quota_remaining": quota_remaining, "quota_warning": quota_warning})}\n\n'

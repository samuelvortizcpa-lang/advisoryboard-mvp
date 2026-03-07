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
  └─ search_chunks → build context → gpt-4o-mini chat completion
"""

from __future__ import annotations

import logging
import os
from uuid import UUID

from openai import AsyncOpenAI
from sqlalchemy.orm import Session

from sqlalchemy.orm import joinedload

from app.core.config import get_settings
from app.models.client import Client
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.services import storage_service
from app.services.chunking import chunk_text
from app.services.text_extraction import ExtractionError, UnsupportedFileType, extract_text

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

EMBEDDING_MODEL = "text-embedding-3-small"   # 1 536 dims, matches schema
CHAT_MODEL = "gpt-4o-mini"
TOP_K = 5          # chunks retrieved per query
EMBED_BATCH = 100  # OpenAI allows up to 2 048 inputs per call

DEFAULT_SYSTEM_PROMPT = """\
You are an AI assistant for an advisory board platform used by CPA firms.
Your role is to help CPAs quickly understand their clients' financial and business situations.

Answer questions using ONLY the context provided below.
- If the answer is not in the context, say so clearly — do not guess.
- Be concise, accurate, and professional.
- When relevant, mention which document the information comes from.

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

        # 2. Chunk
        chunks = chunk_text(text)
        if not chunks:
            raise ValueError("Document produced no usable text chunks after extraction.")

        logger.info(
            "RAG: %s → %d chars, %d chunks", doc_label, len(text), len(chunks)
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
) -> list[DocumentChunk]:
    """
    Return the *limit* most semantically similar DocumentChunks for *query*
    within the given client's documents.

    Uses a JOIN through Document to double-verify client ownership — guards
    against any data-integrity drift in the denormalised client_id column.
    """
    if not query.strip():
        return []

    query_embedding = await embed_text(query)

    results = (
        db.query(DocumentChunk)
        .join(Document, DocumentChunk.document_id == Document.id)
        .filter(
            DocumentChunk.client_id == client_id,
            Document.client_id == client_id,
            DocumentChunk.embedding.isnot(None),
        )
        .order_by(DocumentChunk.embedding.cosine_distance(query_embedding))
        .limit(limit)
        .all()
    )

    # Defensive log: should never fire if data is consistent
    for chunk in results:
        if chunk.client_id != client_id:
            logger.error(
                "ISOLATION BREACH: chunk %s has client_id=%s but query "
                "requested client_id=%s",
                chunk.id, chunk.client_id, client_id,
            )

    return results


# ---------------------------------------------------------------------------
# Q&A
# ---------------------------------------------------------------------------


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
            "sources": [{"document_id": str, "filename": str, "preview": str}]
        }
    """
    chunks = await search_chunks(db, client_id, question, limit=TOP_K)

    if not chunks:
        return {
            "answer": (
                "I couldn't find any processed documents for this client. "
                "Please upload documents and click 'Process Documents' first."
            ),
            "sources": [],
        }

    # Build context with source labels
    context_parts: list[str] = []
    for chunk in chunks:
        filename = chunk.document.filename if chunk.document else "unknown"
        context_parts.append(f"[Source: {filename}]\n{chunk.chunk_text}")

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

    # Chat completion
    openai_client = _openai()
    response = await openai_client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ],
        temperature=0.1,
        max_tokens=1_000,
    )

    answer = response.choices[0].message.content or "No answer generated."

    # Build deduplicated source list
    seen: set[str] = set()
    sources: list[dict] = []
    for chunk in chunks:
        doc_id = str(chunk.document_id)
        if doc_id not in seen:
            seen.add(doc_id)
            filename = chunk.document.filename if chunk.document else "unknown"
            preview = chunk.chunk_text[:200]
            if len(chunk.chunk_text) > 200:
                preview += "…"
            sources.append(
                {"document_id": doc_id, "filename": filename, "preview": preview}
            )

    return {"answer": answer, "sources": sources}

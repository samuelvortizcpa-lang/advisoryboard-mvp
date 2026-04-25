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
import time as _time
from uuid import UUID

import sentry_sdk
from openai import AsyncOpenAI
import sqlalchemy as sa
from sqlalchemy import func, text
from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.models.client import Client
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.document_page_image import DocumentPageImage
from app.models.checkin_response import CheckinResponse
from app.models.checkin_template import CheckinTemplate
from app.services import storage_service
from app.services.chunking import chunk_text, detect_voucher_chunk, flag_voucher_continuations, get_chunk_params, smart_chunk, structure_aware_chunk
from app.services.form_aware_chunker import form_aware_chunk
from app.services.reranker import rerank_chunks
from app.services.context_assembler import (
    ContextPurpose,
    assemble_context,
    format_context_for_prompt,
)
from app.services.query_router import classify_query, route_completion, route_completion_stream
from app.services.tax_terms import expand_query as expand_financial_terms
from app.services.hybrid_search import reciprocal_rank_fusion
from app.services.text_extraction import ExtractionError, UnsupportedFileType, extract_text

logger = logging.getLogger(__name__)

# DIAGNOSTIC (P0 env-var propagation, April 21 2026): remove after resolved
_form_aware_raw = os.environ.get("USE_FORM_AWARE_CHUNKER")
logger.info(
    "STARTUP: USE_FORM_AWARE_CHUNKER raw=%r lowered=%r total_env_keys=%d",
    _form_aware_raw,
    (_form_aware_raw or "").lower(),
    len(os.environ),
)
pipeline_logger = logging.getLogger("rag_pipeline")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

EMBEDDING_MODEL = "text-embedding-3-small"   # 1 536 dims, matches schema
CHAT_MODEL = "gpt-4o"
TOP_K = 10          # chunks retrieved per query
FETCH_K = 30        # over-fetch for keyword re-ranking
EMBED_BATCH = 100  # OpenAI allows up to 2 048 inputs per call

# Last search stats — populated by search_chunks, read by answer_question.
# Not thread-safe, but fine for async single-threaded uvicorn.
_last_search_stats: dict = {}

# ---------------------------------------------------------------------------
# Mode-specific prompt modules
# ---------------------------------------------------------------------------
# Each module is injected immediately before the "Context:" block in the
# system prompt by _assemble_system_prompt(). Modules refine LLM behavior
# for specific question types without altering the base prompt.

MODE_PROMPT_MODULES: dict[str, str] = {
    "factual": """\
When answering a factual lookup question:

- Return ONE specific value with its citation (form + line + page).
- When citing a form or schedule in your answer, use the EXACT form name that appears after `Form:` in the chunk's prefix `[TAX YEAR ... | Form: ... | Page: ... | Section: ...]`. Do not substitute a parent form name from your knowledge of tax-form hierarchy; the chunk prefix is the citation source of truth.
- When a financial total exists alongside its decomposition (e.g., total capital gains on Form 1040 Line 7 vs short-term + long-term on Schedule D Lines 7 and 15), return the TOTAL value with a citation to the summary line. Decomposition belongs in follow-up questions, not the primary answer.
- If the answer requires multiple values to be complete, that is a signal the question may be a synthesis question, not a factual lookup; answer the literal value asked for and note that more detail is available.""",
}

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

Adjacent-number disambiguation:
- Tax forms contain multiple numbers in close proximity on the same page or even the same line of OCR output. When extracting a specific value, ALWAYS verify you are reading the correct line number, not an adjacent line.
- Example: Line 2a (tax-exempt interest) and Line 2b (taxable interest) appear side by side. "$136" on line 2a is NOT the same as "$7" on line 2b. Always confirm the line label matches the question.
- Example: Line 24 (total tax) and Line 25a (federal withholding) appear in sequence. These are different amounts with different meanings.
- If multiple numbers could plausibly answer the question and you cannot disambiguate them from the line labels in the context, state the ambiguity and provide both values with their line labels rather than picking one.

Prior conversation awareness:
- You have access to summaries of prior conversations about this client.
- When the user references past discussions ("what did we talk about", "last time", "previously"), use the session history context to answer.
- When making recommendations, note if they build on or contradict prior decisions.

Data contradiction awareness:
- When data contradictions are listed in the context, proactively mention them if relevant to the user's question.
- For example, if the user asks about a metric that has a contradiction, flag the discrepancy and explain both values.
- Suggest resolution steps when appropriate (e.g. "You may want to verify which source is correct").

Determining the tax year of a document:
When a user asks about a specific tax year (e.g., "What is the AGI for 2024?"), determine which year the document covers using this priority order:
1. Filename — the document filename is the most reliable signal. A file named "2024 Tax Return.pdf" is the 2024 return, period.
2. Primary form header — the year printed in the form header (e.g., "Form 1040 (2024)").
3. Page context — most lines describe the current tax year unless explicitly labeled otherwise.
Do NOT infer the tax year from secondary forward-looking references:
- "Apply overpayment to [YEAR] estimated tax" (Form 1040 line 36) — this is a forward-looking election for the NEXT year
- "Prior year excess contributions" or carryforward language on Form 5329, Schedule D, etc.
- "Estimated tax payments for [YEAR]" sections
- Form 1040-ES voucher references (these are for the NEXT tax year, not the current one)
If the filename and primary header clearly indicate year X, answer using the data in the document — do not refuse or claim the document is for year X+1 just because secondary forward references mention that year.

Response formatting — IMPORTANT:

The retrieved context includes bracketed metadata headers like
"[TAX YEAR 2024 | Document: filename.pdf | Page 5 | Relevance: 100.0% | Type: ... | Period: ...]"
at the start of each excerpt. These headers are for your reasoning only.

NEVER copy, quote, or paraphrase these brackets in your response.
NEVER write "Relevance:", "Period:", "Type:", or bracketed tags in your answer.
NEVER begin a citation with "[".

Instead, when citing a source, ALWAYS name the specific IRS form or schedule and line number:
  ✓ "Form 1040, Line 11 shows AGI of $293,600."
  ✓ "Schedule K, Line 1 reports ordinary business income of $556,379."
  ✓ "Form 1120-S, Line 22 shows ordinary business income of $556,379."
  ✗ "According to page 5 of the 2024 Tax Return, ..." (too vague — name the form)
  ✗ "[TAX YEAR 2024 | Document: ...] shows ..." (never echo bracketed headers)

ALWAYS prefer "Form [name], Line [number]" or "Schedule [name], Line [number]" over generic page references. The source chunks contain form names and line numbers — use them.

Cite the MOST SPECIFIC form or schedule:
When a value appears on both a main return (Form 1040, Form 1120-S) and a supporting schedule or attachment (Schedule L, Schedule M-2, Form 1125-E, Form 7203, Form 5329, Schedule A, etc.), always cite the supporting schedule — not the parent return. For example, cite "Schedule L, Line 24" for retained earnings, not "Form 1120-S, Line 24". The supporting schedule is where the detailed calculation lives.

ALWAYS include the line number when citing a form. Write "Form 100S, Line 30" — never just "Form 100S" without a line reference. If you cannot determine the specific line number from the context, state which form and describe where on the form the value appears.

Federal vs. state disambiguation:
When the question asks about a federal figure, cite the federal form — not the California or other state equivalent. For example, cite "Form 1120-S, Line 21" for total deductions, not "CA Form 100S" or "Schedule F". Conversely, when the question asks about a state tax amount, cite the state form specifically.

Context:
{context}
"""

# Tax-year disambiguation guidance — appended to client_type prompts that
# don't include DEFAULT_SYSTEM_PROMPT (which already has it inline).
_TAX_YEAR_GUIDANCE = """

MANDATORY TAX YEAR RULE:
Every chunk header begins with [TAX YEAR YYYY]. That tag is the AUTHORITATIVE tax year for the data in that chunk. Do NOT override it based on any text inside the chunk.

Specifically:
- If a chunk says [TAX YEAR 2024], ALL dollar amounts and line items in that chunk belong to the 2024 tax year, regardless of any mention of other years inside the text.
- Forward-looking references (e.g., "Apply overpayment to 2025 estimated tax", Form 1040-ES vouchers, "Prior year excess contributions") are NOT evidence that the chunk is from a different tax year. They are secondary references within the return for the year stated in the TAX YEAR tag.
- NEVER refuse to answer by claiming the available data is for the wrong year when the TAX YEAR tag matches what the user asked for.

LINE-ITEM PRECISION:
- When answering questions about tax amounts, you MUST cite the specific Form line number (e.g., "Form 1040, Line 11: $142,350").
- Quote exact dollar amounts as they appear — never round or approximate (e.g., "$142,350" not "about $142k").
- If the exact line asked about is not in the chunks but a related figure is, provide what IS available and explain which line it comes from and how it differs.
- For W-2s and K-1s, cite box numbers (e.g., "Box 1: $95,000").
- Adjacent numbers: tax forms place multiple values in close proximity. Always verify you are reading the correct line label, not an adjacent one (e.g., line 2a tax-exempt vs. line 2b taxable interest; line 24 total tax vs. line 25a withholding). If ambiguous, state both values with their line labels.

Response formatting — IMPORTANT:

The retrieved context includes bracketed metadata headers like
"[TAX YEAR 2024 | Document: filename.pdf | Page 5 | Relevance: 100.0% | Type: ... | Period: ...]"
at the start of each excerpt. These headers are for your reasoning only.

NEVER copy, quote, or paraphrase these brackets in your response.
NEVER write "Relevance:", "Period:", "Type:", or bracketed tags in your answer.
NEVER begin a citation with "[".

Instead, when citing a source, ALWAYS name the specific IRS form or schedule and line number:
  ✓ "Form 1040, Line 11 shows AGI of $293,600."
  ✓ "Schedule K, Line 1 reports ordinary business income of $556,379."
  ✓ "Form 1120-S, Line 22 shows ordinary business income of $556,379."
  ✗ "According to page 5 of the 2024 Tax Return, ..." (too vague — name the form)
  ✗ "[TAX YEAR 2024 | Document: ...] shows ..." (never echo bracketed headers)

ALWAYS prefer "Form [name], Line [number]" or "Schedule [name], Line [number]" over generic page references. The source chunks contain form names and line numbers — use them.

Cite the MOST SPECIFIC form or schedule:
When a value appears on both a main return (Form 1040, Form 1120-S) and a supporting schedule or attachment (Schedule L, Schedule M-2, Form 1125-E, Form 7203, Form 5329, Schedule A, etc.), always cite the supporting schedule — not the parent return. For example, cite "Schedule L, Line 24" for retained earnings, not "Form 1120-S, Line 24". The supporting schedule is where the detailed calculation lives.

ALWAYS include the line number when citing a form. Write "Form 100S, Line 30" — never just "Form 100S" without a line reference. If you cannot determine the specific line number from the context, state which form and describe where on the form the value appears.

Federal vs. state disambiguation:
When the question asks about a federal figure, cite the federal form — not the California or other state equivalent. For example, cite "Form 1120-S, Line 21" for total deductions, not "CA Form 100S" or "Schedule F". Conversely, when the question asks about a state tax amount, cite the state form specifically.
"""


def _assemble_system_prompt(
    prompt_template: str, context: str, mode: str = "factual",
) -> str:
    """Insert mode-specific guidance before the Context block, then format.

    Targets the unique 'Context:\\n{context}' placeholder marker rather
    than the bare 'Context:' substring, to avoid replacing any incidental
    'Context:' occurrences inside injected guidance blocks.
    """
    module = MODE_PROMPT_MODULES.get(mode, "")
    if module:
        marker = "Context:\n{context}"
        if marker in prompt_template:
            prompt_template = prompt_template.replace(
                marker,
                f"{module}\n\n{marker}",
                1,
            )
        else:
            # Defensive fallback — module prepended.
            prompt_template = f"{module}\n\n{prompt_template}"
    return prompt_template.format(context=context)


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
    Mark older documents as superseded when a newer version arrives.

    Case 1 — Same type+subtype, more recent period supersedes older period.
    Case 2 — Amendment superseding: a document with amends_subtype set
             (e.g. 1040X amends Form 1040) supersedes the original form
             for the same client and period.
    """
    # ── Case 1: newer period supersedes older period (same type+subtype) ──
    if new_doc.document_subtype and new_doc.document_period:
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

    # ── Case 2: amendment supersedes original (or prior amendment) ────────
    if new_doc.amends_subtype and new_doc.document_period:
        # Find the most recent non-superseded document that this amends
        original = (
            db.query(Document)
            .filter(
                Document.client_id == new_doc.client_id,
                Document.id != new_doc.id,
                Document.document_subtype == new_doc.amends_subtype,
                Document.document_period == new_doc.document_period,
                Document.is_superseded == False,  # noqa: E712
            )
            .order_by(Document.upload_date.desc())
            .first()
        )

        if original:
            if original.document_period != new_doc.document_period:
                # Should never happen given the query filter, but guard anyway
                logger.warning(
                    "Amendment period mismatch: new %s period=%s vs original %s period=%s — skipping",
                    new_doc.id, new_doc.document_period,
                    original.id, original.document_period,
                )
            else:
                original.is_superseded = True
                original.superseded_by = new_doc.id
                logger.info(
                    "Amendment: %s (%s) supersedes %s (%s) for period %s",
                    new_doc.id, new_doc.document_subtype,
                    original.id, original.document_subtype,
                    new_doc.document_period,
                )

                # Journal entry for amended return filing
                try:
                    from app.services.journal_service import create_auto_entry

                    subtype = new_doc.document_subtype or "return"
                    period = new_doc.document_period or "unknown year"
                    create_auto_entry(
                        db=db,
                        client_id=new_doc.client_id,
                        user_id="system",
                        entry_type="financial_change",
                        category="compliance",
                        title=f"Amended {period} return ({subtype}) filed",
                        content=(
                            f"Amended return ({subtype}) supersedes original "
                            f"({original.document_subtype}) for period {period}."
                        ),
                        source_type="document",
                        source_id=new_doc.id,
                        metadata={
                            "original_document_id": str(original.id),
                            "amends_subtype": new_doc.amends_subtype,
                            "period": period,
                        },
                    )
                except Exception:
                    logger.warning("Journal entry for amendment failed (non-fatal)", exc_info=True)

        # Also check for prior amendments (e.g., 1040X #1 superseded by #2)
        prior_amendment = (
            db.query(Document)
            .filter(
                Document.client_id == new_doc.client_id,
                Document.id != new_doc.id,
                Document.amends_subtype == new_doc.amends_subtype,
                Document.document_period == new_doc.document_period,
                Document.is_superseded == False,  # noqa: E712
            )
            .order_by(Document.upload_date.desc())
            .first()
        )

        if prior_amendment:
            prior_amendment.is_superseded = True
            prior_amendment.superseded_by = new_doc.id
            logger.info(
                "Amendment chain: %s supersedes prior amendment %s for period %s",
                new_doc.id, prior_amendment.id, new_doc.document_period,
            )

        # Auto-set amendment_number based on existing amendments
        existing_count = (
            db.query(Document)
            .filter(
                Document.client_id == new_doc.client_id,
                Document.id != new_doc.id,
                Document.amends_subtype == new_doc.amends_subtype,
                Document.document_period == new_doc.document_period,
            )
            .count()
        )
        new_doc.amendment_number = existing_count + 1

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
        # Mark document so it doesn't stay stuck at "(processing...)" forever
        try:
            doc = db.query(Document).filter(Document.id == document_id).first()
            if doc and not doc.processed:
                doc.processed = True
                doc.processing_error = f"Processing failed: {str(exc)[:500]}"
                db.commit()
                logger.info("Marked document %s as processed with error", document_id)
        except Exception:
            logger.exception("Could not update stuck document %s", document_id)
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
        file_bytes = None  # cached for Document AI re-extraction
        try:
            temp_path = await asyncio.to_thread(
                storage_service.get_temp_local_path, document.file_path
            )
            # Cache file bytes before deletion (avoids second Supabase download)
            if document.file_type == "pdf" and temp_path:
                try:
                    with open(temp_path, "rb") as f:
                        file_bytes = f.read()
                except OSError:
                    pass
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

            # Filter 1040-ES voucher pages before classification.
            # Voucher pages contain strong signals for the NEXT tax year
            # ("Form 1040-ES", future due dates) that contaminate the
            # classifier's first-2000-char snippet and cause the document
            # to be mis-classified as 1040-ES / future year. Filter them
            # out so the classifier sees the actual return content.
            classify_text = text
            try:
                pages = re.split(r'(?=\[Page \d+\])', text)
                pages = [p for p in pages if p.strip()]
                non_voucher_pages = [
                    p for p in pages
                    if not detect_voucher_chunk(p).get("is_voucher")
                ]
                filtered_count = len(pages) - len(non_voucher_pages)
                if non_voucher_pages and filtered_count > 0:
                    classify_text = "\n\n".join(non_voucher_pages)
                    logger.info(
                        "RAG: filtered %d voucher page(s) from classifier input for %s (%d pages remain)",
                        filtered_count, doc_label, len(non_voucher_pages),
                    )
                elif filtered_count > 0 and not non_voucher_pages:
                    logger.warning(
                        "RAG: all %d pages flagged as vouchers for %s — falling back to unfiltered text",
                        filtered_count, doc_label,
                    )
            except Exception as filter_exc:
                logger.warning(
                    "RAG: voucher page filter failed for %s (falling back to unfiltered text): %s",
                    doc_label, filter_exc,
                )

            classification = await classify_document(classify_text)
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

        # 1d. Re-extract with Document AI if available (best-effort)
        docai_result = None
        if document.file_type == "pdf" and file_bytes:
            try:
                from app.services.text_extraction import extract_text_with_docai
                docai_result = await asyncio.to_thread(
                    extract_text_with_docai, file_bytes, document.document_type
                )
                if docai_result:
                    text = docai_result["text"]
                    logger.info(
                        "RAG: using Document AI extraction for %s (type: %s)",
                        doc_label, document.document_type,
                    )
            except Exception:
                logger.warning(
                    "RAG: Document AI extraction failed for %s, using pdfplumber text",
                    doc_label, exc_info=True,
                )

        # 2. Chunk (document-type-specific sizing)
        # Extract return tax year (e.g., "2024" from document_period)
        # Moved above chunking block so form_aware_chunk can use it.
        _return_tax_year: int | None = None
        if document.document_period:
            import re as _re_year
            _year_match = _re_year.search(r"\b(20\d{2})\b", document.document_period)
            if _year_match:
                _return_tax_year = int(_year_match.group(1))

        chunk_metadatas: list[dict | None] = []  # parallel to chunks; None = legacy path
        chunk_size, chunk_overlap = get_chunk_params(document.document_type)

        _use_form_aware = (
            os.environ.get("USE_FORM_AWARE_CHUNKER", "").lower() == "true"
            and (document.document_type or "").lower() == "tax_return"
            and docai_result
            and docai_result.get("pages")
        )

        if _use_form_aware:
            fa_result = form_aware_chunk(
                docai_result["pages"], tax_year=_return_tax_year
            )
            chunks = [c["text"] for c in fa_result]
            chunk_metadatas = [c["metadata"] for c in fa_result]
            logger.info(
                "RAG: form-aware chunking: %d chunks from %d pages (tax_year=%s)",
                len(chunks), len(docai_result["pages"]), _return_tax_year,
            )
        elif docai_result and docai_result.get("pages"):
            # Structure-aware chunking from Document AI
            structured_chunks = structure_aware_chunk(
                docai_result["pages"], max_chars=chunk_size, overlap=chunk_overlap
            )
            chunks = [c["text"] for c in structured_chunks]
            chunk_metadatas = [None] * len(chunks)
            logger.info(
                "RAG: structure-aware chunking: %d chunks from %d pages (size=%d, overlap=%d)",
                len(chunks), len(docai_result["pages"]), chunk_size, chunk_overlap,
            )
        else:
            # Smart chunking: respects paragraph/section boundaries with
            # document-type-specific sizing (financial=600, transcript=1800, etc.)
            doc_type = document.document_type or "general"
            chunks = await asyncio.to_thread(smart_chunk, text, doc_type)
            chunk_metadatas = [None] * len(chunks)
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
                chunk_metadata = chunk_metadatas[batch_start + local_i]
                if chunk_metadata is None:
                    # Legacy path: per-chunk voucher detection
                    voucher_info = detect_voucher_chunk(chunk_text_val, _return_tax_year)
                    if voucher_info["is_voucher"]:
                        chunk_metadata = {
                            "is_voucher": True,
                            "voucher_type": voucher_info["voucher_type"],
                            "voucher_year": voucher_info["voucher_year"],
                        }

                chunk_rows.append(
                    DocumentChunk(
                        document_id=document.id,
                        client_id=document.client_id,
                        chunk_text=chunk_text_val,
                        chunk_index=batch_start + local_i,
                        embedding=emb_data.embedding,
                        chunk_metadata=chunk_metadata,
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
        #    Also triggers for amendments (amends_subtype set)
        try:
            if (document.document_type and document.document_period) or document.amends_subtype:
                _check_supersede(db, document)
        except Exception as ver_exc:
            logger.warning(
                "RAG: versioning check failed for %s (non-fatal): %s",
                doc_label, ver_exc,
            )

        # 8. Financial metric extraction (best-effort — structured data)
        if document.document_type in ("tax_return", "financial_statement"):
            try:
                from app.services.financial_extraction_service import (
                    extract_financial_metrics,
                )
                metrics = await extract_financial_metrics(
                    db, document.id, document.client_id,
                )
                if metrics:
                    logger.info(
                        "RAG: extracted %d financial metric(s) for %s",
                        len(metrics), doc_label,
                    )
            except Exception as fin_exc:
                logger.warning(
                    "RAG: financial extraction failed for %s (non-fatal): %s",
                    doc_label, fin_exc,
                )

        # 9. Page image processing for PDFs (best-effort — multimodal RAG)
        if document.file_type == "pdf":
            try:
                from app.services.page_image_service import process_page_images
                await process_page_images(db, document)
            except Exception as img_exc:
                logger.warning(
                    "RAG: page image processing failed for %s (non-fatal): %s",
                    doc_label, img_exc,
                )

        # 10. Journal entry for document upload (best-effort)
        try:
            from app.services.journal_service import create_auto_entry

            subtype = document.document_subtype or document.document_type or "document"
            period = document.document_period or ""
            period_label = f" for {period}" if period else ""
            title = f"New document uploaded: {subtype}{period_label}"

            parts = []
            if document.document_type:
                parts.append(f"Type: {document.document_type}")
            if document.document_subtype:
                parts.append(f"Subtype: {subtype}")
            if period:
                parts.append(f"Period: {period}")
            if document.classification_confidence:
                parts.append(f"Classification confidence: {document.classification_confidence:.0%}")
            content = "\n".join(parts) if parts else None

            create_auto_entry(
                db=db,
                client_id=document.client_id,
                user_id=document.owner_id or "system",
                entry_type="document_insight",
                category="general",
                title=title,
                content=content,
                source_type="document",
                source_id=document.id,
                metadata={
                    "filename": document.filename,
                    "document_type": document.document_type,
                    "document_subtype": document.document_subtype,
                    "document_period": period or None,
                },
            )
        except Exception as journal_exc:
            logger.warning(
                "RAG: journal entry failed for %s (non-fatal): %s",
                doc_label, journal_exc,
            )

    except Exception as exc:
        logger.error("RAG: failed to process %s: %s", doc_label, exc)
        sentry_sdk.capture_exception(exc)
        db.rollback()

        # Mark as processed with error so it doesn't stay stuck at "(processing...)"
        try:
            doc = db.query(Document).filter(Document.id == document.id).first()
            if doc:
                doc.processed = True
                doc.processing_error = str(exc)[:1000]
                db.commit()
        except Exception:
            logger.exception("RAG: could not persist error for %s", doc_label)


# ---------------------------------------------------------------------------
# Semantic search
# ---------------------------------------------------------------------------


def _build_bm25_or_tsquery_string(query: str) -> str | None:
    """Build an OR-joined tsquery string from a natural-language query.

    Returns a string suitable for to_tsquery('english', ...), or None
    if the query has no usable tokens.

    Example:
        'What is Michael's AGI for 2024?' -> 'what | michael | agi | 2024'

    Note: tokens are passed through to_tsquery, which applies english
    config (stopword removal, stemming). So 'what' will be dropped as a
    stopword by to_tsquery itself; we don't pre-filter stopwords here.
    We do filter pure single-character tokens to avoid degenerate queries.
    """
    # Extract alphanumeric tokens, lowercase
    raw_tokens = re.findall(r"[a-zA-Z0-9]+", query.lower())
    # Drop single-character tokens (won't help, may degrade ranking)
    tokens = [t for t in raw_tokens if len(t) >= 2]
    if not tokens:
        return None
    # Deduplicate while preserving order (helps ts_rank_cd stability)
    seen: set[str] = set()
    deduped: list[str] = []
    for t in tokens:
        if t not in seen:
            seen.add(t)
            deduped.append(t)
    return " | ".join(deduped)


async def search_chunks(
    db: Session,
    client_id: UUID,
    query: str,
    limit: int = TOP_K,
    *,
    include_vouchers: bool = False,
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

    _search_start = _time.monotonic()

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

    # Build voucher exclusion filter (exclude chunks with chunk_metadata->>'is_voucher' = 'true')
    # Uses IS DISTINCT FROM to correctly handle SQL NULL, JSONB null, and JSONB objects
    # without an is_voucher key — all of which should be treated as "not a voucher."
    # Previous OR-based filter silently dropped JSONB null rows due to three-valued logic.
    _voucher_filter = (
        DocumentChunk.chunk_metadata["is_voucher"].astext.is_distinct_from("true")
        if not include_vouchers
        else sa.true()
    )

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
                _voucher_filter,
            )
            .order_by(distance_col)
            .limit(FETCH_K)
            .all()
        )

        for chunk, distance in rows:
            if chunk.id not in seen_chunk_ids:
                seen_chunk_ids.add(chunk.id)
                all_rows.append((chunk, distance, source))

    # --- BM25 full-text search via tsvector (OR-joined ranker) ---
    bm25_results: list[dict] = []
    try:
        # Build OR-joined tsquery so BM25 acts as a ranker (any term matches)
        # rather than a filter (all terms must match). ts_rank_cd scores by
        # how many terms hit and their proximity — more matches rank higher.
        or_query_str = _build_bm25_or_tsquery_string(query)
        if or_query_str is None:
            # No usable tokens; skip BM25 entirely (vector + keyword carry)
            bm25_rows = []
        else:
            tsquery = func.to_tsquery("english", or_query_str)
            bm25_score_col = func.ts_rank_cd(
                DocumentChunk.search_vector, tsquery
            ).label("bm25_score")

            bm25_rows = (
                db.query(DocumentChunk, bm25_score_col)
                .join(Document, DocumentChunk.document_id == Document.id)
                .filter(
                    DocumentChunk.client_id == client_id,
                    Document.client_id == client_id,
                    DocumentChunk.search_vector.op("@@")(tsquery),
                    _voucher_filter,
                )
                .order_by(bm25_score_col.desc())
                .limit(FETCH_K)
                .all()
            )

        for chunk, bm25_score in bm25_rows:
            bm25_results.append({
                "id": chunk.id,
                "chunk": chunk,
                "score": float(bm25_score),
            })
    except Exception:
        logger.warning("BM25 full-text search failed; continuing with vector-only", exc_info=True)

    # --- Format vector results for RRF ---
    vector_results: list[dict] = []
    for chunk, distance, _source in all_rows:
        vector_results.append({
            "id": chunk.id,
            "chunk": chunk,
            "score": float(distance),
        })

    # --- Merge with Reciprocal Rank Fusion ---
    if bm25_results:
        merged = reciprocal_rank_fusion([vector_results, bm25_results])
    else:
        merged = reciprocal_rank_fusion([vector_results])

    _search_ms = (_time.monotonic() - _search_start) * 1000
    pipeline_logger.info(
        "  Hybrid search: %d vector + %d BM25 → %d merged | %.0fms",
        len(vector_results), len(bm25_results), len(merged), _search_ms,
    )

    # --- Cross-encoder reranking (optional) ---
    _rerank_start = _time.monotonic()
    rerank_input = [
        {"chunk_text": item["chunk"].chunk_text, **item}
        for item in merged
    ]
    reranked_chunks_list, did_rerank = await rerank_chunks(
        query=query, chunks=rerank_input, top_k=limit * 2,
    )
    merged = reranked_chunks_list
    _rerank_ms = (_time.monotonic() - _rerank_start) * 1000
    if did_rerank:
        pipeline_logger.info(
            "  Reranking: %d → %d | %.0fms",
            len(rerank_input), len(merged), _rerank_ms,
        )

    # Capture stats for pipeline_stats in ChatResponse
    _last_search_stats.update({
        "vector_results": len(vector_results),
        "bm25_results": len(bm25_results),
        "merged_results": len(merged),
        "reranked": did_rerank,
        "rerank_model": "rerank-v3.5" if did_rerank else None,
    })

    # Build a lookup from chunk id to the original vector distance (for confidence scoring)
    distance_by_id: dict[str, float] = {
        str(chunk.id): distance for chunk, distance, _ in all_rows
    }

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
    for item in merged:
        chunk = item["chunk"]
        chunk_id_str = str(item["id"])

        # Use vector distance if available; otherwise assign a default mid-range distance
        distance = distance_by_id.get(chunk_id_str, 0.5)

        # Convert cosine distance (0–2) to confidence percentage (0–100)
        confidence = (1 - distance / 2) * 100

        # RRF boost: chunks appearing in both lists get a higher RRF score.
        # Scale the RRF score into a small additive boost (0–5%)
        rrf_score = item.get("rrf_score", 0.0)
        # Max possible single-list RRF score is 1/(60+1) ≈ 0.0164
        # Two-list top-1 max is ~0.0328. Normalize to 0–5% range.
        rrf_boost = min(5.0, rrf_score * 200)
        confidence = min(100.0, confidence + rrf_boost)

        # Rerank boost: if Cohere reranking scored this chunk, use it.
        # rerank_score is 0-1 (relevance_score from Cohere). Scale to 0-15% boost.
        rerank_score = item.get("rerank_score")
        if rerank_score is not None:
            rerank_boost = rerank_score * 15.0
            confidence = min(100.0, confidence + rerank_boost)

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
                "Keyword boost +%.1f%% for chunk %d",
                keyword_boost, chunk.chunk_index,
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


_TAX_YEAR_FROM_FILENAME_RE = re.compile(r"(?<!\d)(20\d{2})(?!\d)")


def extract_tax_year_from_filename(filename: str) -> int | None:
    """Extract a 4-digit tax year (20xx) from a document filename.

    Uses a non-word-boundary pattern so years embedded in names like
    ``TaxReturn2024.pdf`` are still captured.  Returns the *last* match
    so that ``2023_amended_2024.pdf`` yields 2024.
    """
    matches = _TAX_YEAR_FROM_FILENAME_RE.findall(filename or "")
    if not matches:
        return None
    return int(matches[-1])


# ---------------------------------------------------------------------------
# Form detection for chunk header enrichment
# ---------------------------------------------------------------------------

# Ordered: more-specific patterns first so "Form 1120-S" beats "Form 1120".
_FORM_DETECT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Federal forms — specific variants before base forms
    (re.compile(r"Form\s+1120[\s-]?S\b", re.IGNORECASE), "Form 1120-S"),
    (re.compile(r"Form\s+1120\b", re.IGNORECASE), "Form 1120"),
    (re.compile(r"Form\s+1040[\s-]?SR\b", re.IGNORECASE), "Form 1040-SR"),
    (re.compile(r"Form\s+1040[\s-]?NR\b", re.IGNORECASE), "Form 1040-NR"),
    (re.compile(r"Form\s+1040\b", re.IGNORECASE), "Form 1040"),
    (re.compile(r"Form\s+1065\b", re.IGNORECASE), "Form 1065"),
    (re.compile(r"Form\s+990\b", re.IGNORECASE), "Form 990"),
    # Supporting federal forms
    (re.compile(r"Form\s+8889\b", re.IGNORECASE), "Form 8889"),
    (re.compile(r"Form\s+5329\b", re.IGNORECASE), "Form 5329"),
    (re.compile(r"Form\s+7203\b", re.IGNORECASE), "Form 7203"),
    (re.compile(r"Form\s+5806\b", re.IGNORECASE), "Form 5806"),
    (re.compile(r"Form\s+4562\b", re.IGNORECASE), "Form 4562"),
    (re.compile(r"Form\s+1125[\s-]?E\b", re.IGNORECASE), "Form 1125-E"),
    (re.compile(r"Form\s+8879", re.IGNORECASE), "Form 8879"),
    # Schedules (federal)
    (re.compile(r"Schedule\s+K-1\b", re.IGNORECASE), "Schedule K-1"),
    (re.compile(r"Schedule\s+K\b", re.IGNORECASE), "Schedule K"),
    (re.compile(r"Schedule\s+L\b", re.IGNORECASE), "Schedule L"),
    (re.compile(r"Schedule\s+M-2\b", re.IGNORECASE), "Schedule M-2"),
    (re.compile(r"Schedule\s+M-1\b", re.IGNORECASE), "Schedule M-1"),
    (re.compile(r"Schedule\s+A\b", re.IGNORECASE), "Schedule A"),
    (re.compile(r"Schedule\s+B\b", re.IGNORECASE), "Schedule B"),
    (re.compile(r"Schedule\s+C\b", re.IGNORECASE), "Schedule C"),
    (re.compile(r"Schedule\s+D\b", re.IGNORECASE), "Schedule D"),
    (re.compile(r"Schedule\s+E\b", re.IGNORECASE), "Schedule E"),
    # California state forms
    (re.compile(r"Form\s+100S\b", re.IGNORECASE), "Form 100S"),
    (re.compile(r"Form\s+100\b", re.IGNORECASE), "Form 100"),
    (re.compile(r"Form\s+568\b", re.IGNORECASE), "Form 568"),
    (re.compile(r"Form\s+540\b", re.IGNORECASE), "Form 540"),
    (re.compile(r"Form\s+3893\b", re.IGNORECASE), "Form 3893"),
]

# California state forms — used for federal/state tagging
_CA_FORM_NAMES = frozenset({
    "Form 100S", "Form 100", "Form 568", "Form 540", "Form 3893",
    "Form 5806",
})

# If the chunk text mentions California explicitly, that's a state signal too
_CA_TEXT_RE = re.compile(
    r"\bCalifornia\s+(?:Franchise\s+Tax|FTB|Secretary\s+of\s+State)\b"
    r"|\bFranchise\s+Tax\s+Board\b"
    r"|\bFTB\b",
    re.IGNORECASE,
)


def _detect_form_name(chunk_text: str) -> str | None:
    """
    Best-effort detection of the primary IRS/state form referenced in a chunk.

    Returns a canonical form name (e.g. "Form 1120-S", "Schedule K") or None.
    First match wins — patterns are ordered most-specific-first.
    """
    for pattern, canonical_name in _FORM_DETECT_PATTERNS:
        if pattern.search(chunk_text):
            return canonical_name
    return None


def _is_state_form(form_name: str | None, chunk_text: str) -> bool:
    """Return True if the chunk appears to be from a state (not federal) form."""
    if form_name and form_name in _CA_FORM_NAMES:
        return True
    if _CA_TEXT_RE.search(chunk_text):
        return True
    return False


def _build_context_with_attribution(
    chunk_results: list[tuple[DocumentChunk, float]],
    checkin_context_parts: list[str] | None = None,
) -> str:
    """
    Build the text context string sent to the LLM with document attribution.

    Each chunk is prefixed with a header like::

        [TAX YEAR YYYY | FEDERAL Form 1120-S | Document: <filename> | Page N | Relevance: X%]

    When a form name is detected in the chunk text, it is included with a
    FEDERAL/STATE jurisdiction tag.  A preamble listing distinct source
    documents is prepended.
    """
    if not chunk_results and not checkin_context_parts:
        return ""

    # Collect distinct filenames and their tax years (preserving insertion order)
    distinct_docs: dict[str, int | None] = {}
    for chunk, _score in chunk_results:
        doc = chunk.document
        fname = doc.filename if doc else "unknown"
        if fname not in distinct_docs:
            distinct_docs[fname] = extract_tax_year_from_filename(fname)

    # Preamble: inventory of documents with tax year
    preamble_lines = [
        "The following document(s) are available to answer the user's question:\n"
    ]
    for fname, tax_year in distinct_docs.items():
        year_tag = f" [Tax Year {tax_year}]" if tax_year else ""
        preamble_lines.append(f"- {fname}{year_tag}")
    preamble_lines.append(
        "\nUse the TAX YEAR tag in each chunk header as the authoritative tax year "
        "for that excerpt. Below are the relevant excerpts:"
    )
    preamble = "\n".join(preamble_lines)

    # Build per-chunk sections
    context_parts: list[str] = []
    for chunk, score in chunk_results:
        doc = chunk.document
        filename = doc.filename if doc else "unknown"
        tax_year = distinct_docs.get(filename)
        chunk_text = chunk.chunk_text

        # Extract page number from [Page N] marker if present
        page_match = re.search(r"\[Page\s+(\d+)\]", chunk_text)
        if page_match:
            page_num = page_match.group(1)
            # Strip the original [Page N] line from the chunk text
            chunk_text = re.sub(r"\[Page\s+\d+\]\n?", "", chunk_text, count=1).lstrip()
            header = f"[Document: {filename} | Page {page_num} | Relevance: {score:.1f}%]"
        else:
            header = f"[Document: {filename} | Relevance: {score:.1f}%]"

        # Detect form name and federal/state jurisdiction
        detected_form = _detect_form_name(chunk_text)
        is_state = _is_state_form(detected_form, chunk_text)
        if detected_form:
            jurisdiction = "STATE " if is_state else "FEDERAL "
            form_tag = f"{jurisdiction}{detected_form} | "
        else:
            form_tag = ""

        # Prepend TAX YEAR tag (and form tag if detected)
        if tax_year:
            header = f"[TAX YEAR {tax_year} | {form_tag}" + header[1:]
        elif form_tag:
            header = f"[{form_tag}" + header[1:]

        if doc and doc.document_type:
            type_info = f" | Type: {doc.document_type}"
            if doc.document_subtype:
                type_info += f" ({doc.document_subtype})"
            if doc.document_period:
                type_info += f" | Period: {doc.document_period}"
            if doc.is_superseded:
                type_info += " | SUPERSEDED"
            # Insert type info before the closing bracket
            header = header[:-1] + type_info + "]"

        context_parts.append(f"{header}\n{chunk_text}")

    # Append check-in context
    if checkin_context_parts:
        context_parts.extend(checkin_context_parts)

    context = preamble + "\n\n---\n\n" + "\n\n---\n\n".join(context_parts)

    logger.info(
        "Built RAG context with %d chunks from %d documents (%d chars)",
        len(chunk_results), len(distinct_docs), len(context),
    )

    return context


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
    *,
    include_debug_chunks: bool = False,
    is_admin_eval: bool = False,
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
    _pipeline_start = _time.monotonic()
    question = _sanitize_user_input(question)
    pipeline_logger.info(
        "RAG query: '%s' | client=%s",
        question[:80], client_id,
    )

    # Check if user is explicitly asking about estimated tax / vouchers
    _voucher_keywords = ["1040-es", "1040es", "estimated tax", "estimated payment", "quarterly payment", "voucher"]
    _include_vouchers = any(kw in question.lower() for kw in _voucher_keywords)

    chunk_results = await search_chunks(db, client_id, question, limit=TOP_K, include_vouchers=_include_vouchers)

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
    # Expansion terms FIRST (domain-specific IRS vocabulary — high signal on tax forms).
    # Bigrams SECOND (colloquial English — lower signal, but broader coverage).
    # The [:8] slice below caps total phrases searched; putting expansions first
    # guarantees they are searched before bigrams crowd them out on long queries.
    _kw_search_phrases: list[str] = []
    for term in _expansion_terms:
        if len(term) >= 4 and term.lower() not in {p.lower() for p in _kw_search_phrases}:
            _kw_search_phrases.append(term.lower())
    for bigram in _kw_bigrams:
        if bigram.lower() not in {p.lower() for p in _kw_search_phrases}:
            _kw_search_phrases.append(bigram.lower())

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

    # ------------------------------------------------------------------
    # Check-in response embedding search
    # ------------------------------------------------------------------
    checkin_context_parts: list[str] = []
    try:
        # Reuse the first embedding (original query) from search_chunks
        query_embedding = embeddings[0] if "embeddings" in dir() else None
        if query_embedding is None:
            _oai = _openai()
            _embed_resp = await _oai.embeddings.create(
                model=EMBEDDING_MODEL,
                input=[question.replace("\n", " ")],
            )
            query_embedding = _embed_resp.data[0].embedding

        ci_distance = CheckinResponse.response_embedding.cosine_distance(
            query_embedding
        ).label("ci_distance")
        ci_rows = (
            db.query(CheckinResponse, CheckinTemplate.name, ci_distance)
            .join(CheckinTemplate, CheckinResponse.template_id == CheckinTemplate.id)
            .filter(
                CheckinResponse.client_id == client_id,
                CheckinResponse.status == "completed",
                CheckinResponse.response_embedding.isnot(None),
            )
            .order_by(ci_distance)
            .limit(3)
            .all()
        )
        for ci, template_name, distance in ci_rows:
            confidence = (1 - distance / 2) * 100
            if confidence >= 50:
                completed = ci.completed_at.strftime("%Y-%m-%d") if ci.completed_at else "unknown"
                checkin_context_parts.append(
                    f"[Check-in: {template_name} — {completed}]\n{ci.response_text}"
                )
                logger.info(
                    "Check-in match: %s (%.1f%%) completed %s",
                    template_name, confidence, completed,
                )
    except Exception:
        logger.warning("Check-in embedding search failed; continuing without", exc_info=True)

    if not chunk_results and not checkin_context_parts:
        return {
            "answer": (
                "I couldn't find any processed documents for this client. "
                "Please upload documents and click 'Process Documents' first."
            ),
            "confidence_tier": "low",
            "confidence_score": 0.0,
            "sources": [],
        }

    all_scores = [score for _, score in chunk_results] if chunk_results else [50.0]
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
    context = _build_context_with_attribution(chunk_results, checkin_context_parts)

    # Build dynamic system prompt from client type
    db_client = (
        db.query(Client)
        .options(joinedload(Client.client_type))
        .filter(Client.id == client_id)
        .first()
    )

    if db_client and db_client.client_type:
        # Insert citation guidance BEFORE {context} so it's in a high-attention
        # position, matching DEFAULT_SYSTEM_PROMPT layout.
        patched_template = db_client.client_type.system_prompt.replace(
            "Context:\n{context}", _TAX_YEAR_GUIDANCE + "\nContext:\n{context}"
        )
        system_prompt = _assemble_system_prompt(patched_template, context)
    else:
        system_prompt = _assemble_system_prompt(DEFAULT_SYSTEM_PROMPT, context)

    if db_client and db_client.custom_instructions:
        system_prompt += (
            f"\n\nAdditional instructions for this specific client:\n"
            f"{db_client.custom_instructions}"
        )

    # Assemble supplementary context (action items, comms, strategies, session history)
    try:
        ai_ctx = await assemble_context(
            db,
            client_id=client_id,
            user_id=user_id or "",
            purpose=ContextPurpose.CHAT,
            options={"rag_chunks": []},  # RAG chunks already in system prompt
            current_query=question,
        )
        # Format only the non-RAG sections
        supplementary = format_context_for_prompt(ai_ctx, ContextPurpose.CHAT)
        # Strip the client profile section — already covered by client_type prompt
        # Keep action items, communications, strategy status, and session history
        _sup_parts = []
        for block in supplementary.split("\n\n"):
            if block.startswith("=== CLIENT PROFILE"):
                continue
            if block.startswith("=== RELEVANT DOCUMENT"):
                continue
            if block.strip():
                _sup_parts.append(block)
        if _sup_parts:
            system_prompt += (
                "\n\nSupplementary client context (use only if relevant to the question):\n"
                + "\n\n".join(_sup_parts)
            )
    except Exception:
        logger.warning("Context assembler failed; continuing without supplementary context", exc_info=True)

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
    _gen_start = _time.monotonic()
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
        is_admin_eval=is_admin_eval,
    )
    answer = route_result["answer"]
    model_used = route_result["model_used"]
    analysis_tier = route_result.get("analysis_tier", "standard")
    query_type = route_result.get("query_type", query_type)
    quota_remaining = route_result.get("quota_remaining")
    quota_warning = route_result.get("quota_warning")
    quota_warning_message = route_result.get("quota_warning_message")

    _gen_ms = (_time.monotonic() - _gen_start) * 1000
    pipeline_logger.info(
        "  Generation: model=%s | type=%s | %.0fms",
        model_used, query_type, _gen_ms,
    )

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

    _total_ms = (_time.monotonic() - _pipeline_start) * 1000
    pipeline_logger.info(
        "  Total pipeline: %.0fms | confidence=%s (%.1f) | sources=%d",
        _total_ms, confidence_tier, best_score, len(sources),
    )

    result = {
        "answer": answer,
        "confidence_tier": confidence_tier,
        "confidence_score": round(best_score, 2),
        "sources": sources,
        "model_used": model_used,
        "query_type": query_type,
        "analysis_tier": analysis_tier,
        "quota_remaining": quota_remaining,
        "quota_warning": quota_warning,
        "quota_warning_message": quota_warning_message,
        "pipeline_stats": {
            **_last_search_stats,
            "total_latency_ms": round(_total_ms),
        },
    }

    if include_debug_chunks:
        result["retrieved_chunks_debug"] = [
            {
                "chunk_text": chunk.chunk_text,
                "document_id": str(chunk.document_id),
                "chunk_index": chunk.chunk_index,
                "score": score,
                "rank": rank,
            }
            for rank, (chunk, score) in enumerate(chunk_results)
        ]

    return result


async def answer_question_stream(
    db: Session,
    client_id: UUID,
    question: str,
    user_id: str | None = None,
    *,
    include_debug_chunks: bool = False,
):
    """
    Streaming variant of answer_question. Yields SSE-formatted strings.

    Reuses all the same retrieval/context logic, but streams the LLM
    response token-by-token. Sends sources as a final SSE event.
    """
    import json as _json

    question = _sanitize_user_input(question)

    # ── Retrieval phase (identical to answer_question) ──
    _voucher_keywords = ["1040-es", "1040es", "estimated tax", "estimated payment", "quarterly payment", "voucher"]
    _include_vouchers = any(kw in question.lower() for kw in _voucher_keywords)
    chunk_results = await search_chunks(db, client_id, question, limit=TOP_K, include_vouchers=_include_vouchers)

    logger.info("STREAM SOURCE DEBUG: search_chunks returned %d results, reranked=%s, rerank_model=%s",
                len(chunk_results), _last_search_stats.get("reranked"),
                _last_search_stats.get("rerank_model"))

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

    # Check-in response embedding search (streaming)
    checkin_context_parts: list[str] = []
    try:
        _oai = _openai()
        _embed_resp = await _oai.embeddings.create(
            model=EMBEDDING_MODEL,
            input=[question.replace("\n", " ")],
        )
        _q_embedding = _embed_resp.data[0].embedding

        ci_distance = CheckinResponse.response_embedding.cosine_distance(
            _q_embedding
        ).label("ci_distance")
        ci_rows = (
            db.query(CheckinResponse, CheckinTemplate.name, ci_distance)
            .join(CheckinTemplate, CheckinResponse.template_id == CheckinTemplate.id)
            .filter(
                CheckinResponse.client_id == client_id,
                CheckinResponse.status == "completed",
                CheckinResponse.response_embedding.isnot(None),
            )
            .order_by(ci_distance)
            .limit(3)
            .all()
        )
        for ci, template_name, distance in ci_rows:
            confidence = (1 - distance / 2) * 100
            if confidence >= 50:
                completed = ci.completed_at.strftime("%Y-%m-%d") if ci.completed_at else "unknown"
                checkin_context_parts.append(
                    f"[Check-in: {template_name} — {completed}]\n{ci.response_text}"
                )
    except Exception:
        logger.warning("Check-in embedding search failed (stream); continuing without", exc_info=True)

    if not chunk_results and not checkin_context_parts:
        yield 'data: {"type":"token","content":"I couldn\'t find any processed documents for this client."}\n\n'
        yield 'data: {"type":"done","sources":[],"confidence_tier":"low","confidence_score":0.0,"model_used":"none","query_type":"factual"}\n\n'
        return

    all_scores = [score for _, score in chunk_results] if chunk_results else [50.0]
    best_score = max(all_scores)
    confidence_tier = _compute_confidence_tier(all_scores)

    # ── Build context (same as answer_question) ──
    context = _build_context_with_attribution(chunk_results, checkin_context_parts)

    db_client = (
        db.query(Client)
        .options(joinedload(Client.client_type))
        .filter(Client.id == client_id)
        .first()
    )

    if db_client and db_client.client_type:
        # Insert citation guidance BEFORE {context} — high-attention position.
        patched_template = db_client.client_type.system_prompt.replace(
            "Context:\n{context}", _TAX_YEAR_GUIDANCE + "\nContext:\n{context}"
        )
        system_prompt = _assemble_system_prompt(patched_template, context)
    else:
        system_prompt = _assemble_system_prompt(DEFAULT_SYSTEM_PROMPT, context)

    if db_client and db_client.custom_instructions:
        system_prompt += f"\n\nAdditional instructions for this specific client:\n{db_client.custom_instructions}"

    # Assemble supplementary context (action items, comms, strategies, session history)
    try:
        ai_ctx = await assemble_context(
            db,
            client_id=client_id,
            user_id=user_id or "",
            purpose=ContextPurpose.CHAT,
            options={"rag_chunks": []},
            current_query=question,
        )
        supplementary = format_context_for_prompt(ai_ctx, ContextPurpose.CHAT)
        _sup_parts = []
        for block in supplementary.split("\n\n"):
            if block.startswith("=== CLIENT PROFILE") or block.startswith("=== RELEVANT DOCUMENT"):
                continue
            if block.strip():
                _sup_parts.append(block)
        if _sup_parts:
            system_prompt += (
                "\n\nSupplementary client context (use only if relevant to the question):\n"
                + "\n\n".join(_sup_parts)
            )
    except Exception:
        logger.warning("Context assembler failed; continuing without supplementary context", exc_info=True)

    if best_score < 50:
        system_prompt += (
            "\n\nNote: The retrieved context has low relevance scores. "
            "If the context contains relevant financial data, always provide "
            "the best answer possible from available information rather than "
            "declining to answer."
        )

    # ── Classify query type ──
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
    best_chunk_full_text: dict[str, str] = {}   # full text for [Page N] parsing
    best_chunk_index: dict[str, int] = {}

    logger.info("STREAM SOURCE DEBUG: %d raw chunk_results for question: %s",
                len(chunk_results), question[:80])

    for i, (chunk, score) in enumerate(chunk_results):
        doc = chunk.document
        doc_id_str = str(chunk.document_id)
        filename = doc.filename if doc else "unknown"

        logger.info("STREAM SOURCE DEBUG: chunk[%d] score=%.1f doc=%s idx=%d text=%.200s",
                     i, score, filename, chunk.chunk_index, chunk.chunk_text[:200])

        if question_year:
            year_in_filename = question_year in filename
            year_in_period = doc and doc.document_period and question_year in doc.document_period
            if not year_in_filename and not year_in_period:
                logger.info("STREAM SOURCE DEBUG: chunk[%d] SKIPPED (year filter, want %s)", i, question_year)
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
            best_chunk_full_text[doc_id_str] = chunk.chunk_text
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

        # Find the correct page for this chunk
        pages = page_images_by_doc.get(doc_id_str, [])
        if pages:
            full_text = best_chunk_full_text.get(doc_id_str, "")
            best_page = pages[0]  # ultimate fallback
            page_method = "fallback(pages[0])"

            # 1) Parse ALL [Page N] markers from the full chunk text
            all_markers = re.findall(r'\[Page\s+(\d+)\]', full_text) if full_text else []
            logger.info("STREAM SOURCE DEBUG: doc=%s markers_found=%s in chunk (len=%d)",
                        doc_id_str[:8], all_markers, len(full_text))

            if all_markers:
                # Use the LAST marker — for chunks spanning pages, the content
                # the LLM references is typically near the end of the chunk
                target_page = int(all_markers[-1])
                logger.info("STREAM SOURCE DEBUG: picking last marker [Page %d] from %s",
                            target_page, all_markers)
                for pi in pages:
                    if pi.page_number == target_page:
                        best_page = pi
                        page_method = f"marker([Page {target_page}])"
                        break
                else:
                    logger.info("STREAM SOURCE DEBUG: page %d not found in page_images (have pages %s)",
                                target_page, [p.page_number for p in pages])
            elif full_text:
                # 2) Fallback: text-overlap matching for old chunks without markers
                best_overlap = 0
                chunk_lower = full_text.lower()
                for pi in pages:
                    if pi.page_text_preview:
                        page_lower = pi.page_text_preview.lower()
                        if chunk_lower[:150] in page_lower:
                            best_page = pi
                            page_method = f"text-overlap(substring)"
                            break
                        chunk_words = set(chunk_lower.split())
                        page_words = set(page_lower.split())
                        overlap = len(chunk_words & page_words)
                        if overlap > best_overlap:
                            best_overlap = overlap
                            best_page = pi
                            page_method = f"text-overlap(words={overlap})"

            logger.info("STREAM SOURCE DEBUG: doc=%s → page=%d method=%s (available pages: %s)",
                        doc_id_str[:8], best_page.page_number, page_method,
                        [p.page_number for p in pages])

            source["page_number"] = best_page.page_number
            if best_page.image_path:
                try:
                    source["image_url"] = storage_service.get_signed_url(
                        best_page.image_path, expires_in=3600
                    )
                except Exception:
                    pass
                source["image_path"] = best_page.image_path
        else:
            source["page_number"] = 1
            logger.info("STREAM SOURCE DEBUG: doc=%s → page=1 (no page images)", doc_id_str[:8])

        sources.append(source)

    # Persist chat messages with session tracking
    from app.models.chat_message import ChatMessage
    from app.services.session_memory_service import (
        attach_message_to_session,
        embed_qa_pair,
        get_or_create_session,
    )

    # Resolve org_id from client
    _org_id = db_client.org_id if db_client else None

    session = get_or_create_session(client_id, user_id or "", _org_id, db)

    user_msg = ChatMessage(
        client_id=client_id, user_id=user_id, role="user",
        content=question, sources=None,
    )
    db.add(user_msg)
    db.flush()
    attach_message_to_session(session.id, user_msg.id, "user", db)

    assistant_msg = ChatMessage(
        client_id=client_id, user_id=user_id, role="assistant",
        content=full_answer, sources=sources or None,
    )
    db.add(assistant_msg)
    db.flush()
    attach_message_to_session(session.id, assistant_msg.id, "assistant", db)

    pair_idx = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.session_id == session.id,
            ChatMessage.role == "assistant",
        )
        .count()
        - 1
    )

    db.commit()

    # Embed Q/A pair (fire-and-forget)
    asyncio.create_task(
        embed_qa_pair(
            session.id, question, full_answer,
            assistant_msg.id, pair_idx, db,
        )
    )

    # Send final event with metadata
    yield f'data: {_json.dumps({"type": "done", "sources": sources, "confidence_tier": confidence_tier, "confidence_score": round(best_score, 2), "model_used": model_used, "query_type": query_type, "quota_remaining": quota_remaining, "quota_warning": quota_warning, "session_id": str(session.id), "message_id": str(assistant_msg.id)})}\n\n'

# Callwen RAG — Architecture Reference

Load this when you need the full pipeline, file paths, or commit history context. For the short version and the debugging disciplines, see `SKILL.md` first.

## Pipeline breakdown

### Ingestion

**Upload** → POST `/api/clients/{id}/documents` stores the file in Supabase Storage under the org-scoped path, creates a `documents` row, kicks off async processing.

**Classification** — `document_classifier.py` uses GPT-4o-mini to classify by filename + first-page text. 12 known types (1040, 1040X, W-2, K-1, 1099, etc.). Tax year extracted from filename when present and stamped on every chunk header. Known issue class: voucher-heavy PDFs (Form 1040-ES vouchers at the front of a 1040 return) can contaminate document-level classification — the document ends up labeled `Form 1040-ES / Period: 2025` even though it's a 2024 return. Mitigated but not fully eliminated as of April 16.

**Extraction** — `text_extraction.py` dispatches based on mime type:
- **Financial PDF (1040, W-2, K-1, 1099, etc.)** → Google Document AI Form Parser. Extracts structured key-value pairs, tables, page-level blocks. Processor ID in env as `DOCAI_FORM_PARSER_ID`. 15-page limit per call.
- **Other PDF** → Google Document AI OCR (higher quality than Tesseract). Processor ID in env as `DOCAI_OCR_PROCESSOR_ID`.
- **Fallback** → pdfplumber + Tesseract (for pages where garbled text is detected via reversed-word or `(cid:N)` heuristics). Per-page, not document-level — this was a March 22 fix.
- All pages get `[Page N]` markers inserted into the extracted text. These are hard boundaries for chunking.

**Smart chunking** — `chunking.py`. Page-aware (never crosses a `[Page N]` boundary). Type-specific sizes — financial docs target ~600 chars, other types larger. Every chunk header is stamped with `TAX YEAR YYYY | Type: ... | Period: ...`. Voucher chunks flagged via `detect_voucher_chunk` → stored in `chunk_metadata` as `{"is_voucher": true}`; non-voucher chunks store SQL NULL (see JSONB caveat in `known-gotchas.md`).

**Embedding** — OpenAI `text-embedding-3-small`, 1536 dimensions, stored as `pgvector` in `document_chunks.embedding`.

**BM25 vector** — On INSERT/UPDATE, a Postgres trigger (`trg_update_search_vector`) auto-populates `document_chunks.search_vector` (TSVECTOR) from the chunk content. GIN index for fast `@@` matching.

### Query path

**Query router** — `query_router.py`. GPT-4o-mini classifies the query as factual vs strategic, routes to the appropriate model (GPT-4o-mini for factual/chat, Claude Sonnet for strategic, Claude Opus reserved for deep analysis).

**Hybrid search** — `hybrid_search.py`. Runs vector + BM25 in parallel, merges via Reciprocal Rank Fusion with `k=60`. BM25 wrapped in try/except; vector-only fallback if it fails.

- Vector: `pgvector` cosine distance on the query embedding vs chunk embeddings, filtered by `client_id` (or client group via the recursive CTE if linking is enabled).
- BM25: `to_tsquery('english', or_query_str)` with `@@` match and `ts_rank_cd` ranking. Query string is built by `_build_bm25_or_tsquery_string` in `rag_service.py` — extracts alphanumeric tokens, filters single-character tokens, deduplicates, joins with ` | ` (OR). This is the April 15 late-night rewrite (`41c54a7`); prior code used `plainto_tsquery` which AND-joins and returned zero for most CPA queries because chunks don't contain every token in a natural question.

**Reranking** — `reranker.py`. Cohere Rerank v3.5 via async client, 5s timeout, lazy init. Takes top-20 merged hits, returns top-5 ranked by cross-encoder relevance. Rerank score factors into confidence scoring (0-15% boost). Fully optional — skips gracefully if `COHERE_API_KEY` is unset or the call fails. Known breakage mode: Cohere SDK v2 removed the `return_documents` kwarg that v1 accepted. Do not reintroduce it.

**Context assembly** — `context_assembler.py`. Unified assembler used by every AI feature (chat, email draft, brief, quarterly estimate, strategy suggest). Purpose-based token budgets:

| Purpose | Budget | Priority order |
|---|---|---|
| chat | 8,000 | RAG chunks > actions > comms > journal > financials |
| email_draft | 4,000 | Comms > actions > journal > financials > strategies |
| quarterly_estimate | 6,000 | Prior estimates > comms thread > financials > open questions > journal |
| brief | 12,000 | Documents > financials > actions > strategies > comms > journal |
| strategy_suggest | 6,000 | Documents > financials > flags > strategies > actions |

**LLM generation** — Dispatches to the routed model. Returns answer + sources (chunk-level citations with page attribution) + confidence (derived from vector similarity, BM25 score, and rerank score) + pipeline stats (in debug/admin mode).

**Response shaping** — Source cards are deduplicated to pages, limited to top 2 by default, and filtered to those containing the answer's dollar values + query keywords for clean attribution.

### Eval path

**Ground-truth fixtures** — `rag_eval_fixtures.py` holds per-client test questions. Schema per question: `{question, expected_pages: [int], expected_answer_contains: [str], notes: str}`. Currently only Michael Tjahjadi has a fixture set; generalizing to a second client is a known open item.

**Runner** — `rag_evaluator.py`, `run_ground_truth_evaluation`. POST `/api/admin/evaluate-rag-ground-truth/{client_id}` triggers. Runs each question through `answer_question`, captures retrieved chunks, retrieved pages, response text, latency, confidence. Returns per-question debug payload + aggregate scores.

**Scoring** — Two numbers:
- **Retrieval hit rate** — fraction of questions where the expected page is in the retrieved set.
- **Response keyword rate** — fraction where `expected_answer_contains` tokens appear in the response text.

Both should be trusted as of April 16 (rubric validated). Prior to that, rubric bugs on Q4/Q8/Q9 understated real accuracy.

## File map

Core services (`backend/app/services/`):

| File | Role |
|---|---|
| `rag_service.py` | Main pipeline. `answer_question`, hybrid search entry, keyword fallback, source card logic, `_build_bm25_or_tsquery_string`. |
| `hybrid_search.py` | Vector + BM25 merge via RRF. |
| `reranker.py` | Cohere Rerank v3.5 client. |
| `chunking.py` | Smart chunking, page-aware boundaries, voucher-metadata stamping. |
| `text_extraction.py` | Document AI + pdfplumber + Tesseract dispatch. |
| `document_ai_service.py` | Form Parser + OCR processors. |
| `tax_terms.py` | `TERM_EXPANSIONS` dict — query expansions (AGI → adjusted gross income / line 11 / form 1040). Used by keyword fallback. |
| `context_assembler.py` | Purpose-based unified context builder. |
| `query_router.py` | Factual vs strategic classification and model routing. |
| `page_image_service.py` | PDF → page images for source card thumbnails, full OCR text stored. |
| `rag_evaluator.py` | Ground-truth eval runner. |
| `rag_eval_fixtures.py` | Per-client test fixtures. |
| `reprocess_service.py` | Background reprocess with progress tracking. |
| `brief_generator.py` | Client brief — uses context assembler with `purpose=brief`. |
| `communication_service.py` | Email drafts — uses context assembler with `purpose=email_draft` or `quarterly_estimate`. |
| `strategy_ai_service.py` | Strategy suggestions — uses context assembler with `purpose=strategy_suggest`. |

Models (`backend/app/models/`):

| File | Notes |
|---|---|
| `document.py` | `documents` — file metadata, classification fields. |
| `document_chunk.py` | `document_chunks` — content, embedding (VECTOR 1536), search_vector (TSVECTOR), chunk_metadata (JSONB with `none_as_null=True` — this flag is load-bearing, see known-gotchas). |

APIs (`backend/app/api/`):

| File | Endpoints |
|---|---|
| `rag.py` | `/api/clients/{id}/rag/chat`, `/rag/status`, `/rag/process`, `/rag/search`, `/rag/compare`, chat history endpoints. |
| `admin.py` | `/api/admin/reprocess-documents`, `/api/admin/reprocess-status/{task_id}`, `/api/admin/evaluate-rag-ground-truth/{client_id}`, `/api/admin/evaluate-rag/{client_id}`. |

Frontend (`frontend/components/rag/`):

| File | Role |
|---|---|
| `ClientChat.tsx` | Chat UI — messages, confidence badges, source cards, model indicator, pipeline stats in admin mode. |
| `MarkdownContent.tsx` | Lightweight markdown renderer (no react-markdown dependency). |

## Tech stack

- **Backend:** FastAPI, Python 3.12, SQLAlchemy 2.0, Alembic, uvicorn 2 workers on Railway.
- **DB:** Postgres on Supabase + pgvector + tsvector + GIN index.
- **Embeddings:** OpenAI `text-embedding-3-small`, 1536 dims.
- **LLMs:** OpenAI (GPT-4o, GPT-4o-mini), Anthropic (Claude Sonnet, Claude Opus).
- **Reranker:** Cohere Rerank v3.5 (trial key in Railway; apply for production key when pricing review allows).
- **Document AI:** Google Cloud Document AI — Form Parser + OCR processors, region `us`, project `advisoryboard-489516`.
- **Storage:** Supabase Storage (`documents` bucket for uploads, `exports` bucket for server-side PDF caching).
- **Frontend:** Next.js 14, TypeScript, Tailwind, Clerk auth, hosted on Vercel.

## Deployment workflow

```bash
cd ~/advisoryboard-mvp-code
git add -A
git commit -m "feat: description"  # or fix:, feat(rag):, etc.
git push origin main            # Railway (backend)
git push vercel-deploy main     # Vercel (frontend)
```

Run migrations on production:
```bash
cd backend && source venv/bin/activate
railway run alembic upgrade head
```

Pre-commit hook runs `tsc --noEmit`. Two GitHub remotes: `origin` (Railway) and `vercel-deploy` (Vercel).

## Major RAG rebuild commit history

Reference this when a session summary or a user question references a specific commit.

| Commit | Date | What it did |
|---|---|---|
| `dc3b24a` | Apr 9 | Hybrid search — added search_vector TSVECTOR + GIN + trigger, hybrid_search.py with RRF. |
| `71a2c8a` | Apr 9 | Cohere reranker + Document AI integration (Form Parser + OCR). |
| `a97afdc` | Apr 9 | RAG evaluation framework (`rag_evaluations` table). |
| `b045a4a` | Apr 9 | Batch document reprocessing service. |
| `6e17b68` | Apr 9 | Pipeline logging at every stage + `PipelineStats` in ChatResponse. |
| `80e2af3` | Apr 9 late | Ground-truth evaluation with per-client fixtures. |
| `1916018` | Apr 9 late | Detect and filter 1040-ES voucher chunks. |
| `9d0f752` | Apr 12 | Suppress chunk header echoing in responses. |
| `f3c7659` | Apr 14 late | Defensive consumer-side fix for JSONB-null literal (voucher filter). |
| `2530895` | Apr 15 | Prioritize expansion terms over bigrams in keyword fallback. |
| `72fe10a` | Apr 15 late | **JSONB(none_as_null=True) on chunk_metadata model** — producer fix for the JSONB-null literal bug. |
| `c237b4a` | Apr 15 late | Migration: backfill chunk_metadata JSONB null to SQL NULL. |
| `41c54a7` | Apr 15 late | **BM25 OR-joined ranker** — replaces AND-joined `plainto_tsquery` with token-OR `to_tsquery`. This fixed vector+BM25 returning zero. |
| `7b876f0` | Apr 16 | Eval rubric fix Q4/Q8/Q9 + adjacent-number prompt guidance. |

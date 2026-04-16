# Callwen RAG — Known Gotchas

A catalog of failure modes observed at least once. Each entry: the symptom, the mechanism, the fix pattern, and the session/commit where it was resolved.

Use this as a first lookup when a symptom feels familiar. If the same symptom pattern has been seen before, the mechanism is likely similar even if not identical.

## 1. Vector search and BM25 both returning zero

**Symptom:** Log shows `Hybrid search: 0 vector + 0 BM25 → 0 merged` on every query, including simple ones. Keyword fallback "carries" the system invisibly.

**Mechanism (April 15 finding):** Two separate bugs layered over each other.
- BM25: `plainto_tsquery` AND-joined every token. Tax chunks say `1a 271,792.` and don't contain words like "Michael" or "much", so the AND-filter dropped everything. Real hit rate per query was 0-3 matches.
- Vector: was in fact working in some windows; the prior session's "vector also broken" read was misattribution — vector returned legitimately low on queries whose expected chunks were short numeric strings like `11  293,600.` with weak semantic signal.

**Fix pattern:** SQL pre-flight before code change (`references/methodology.md`). Compare AND-join vs OR-join hit counts. If OR-join dramatically outperforms, rewrite to use `to_tsquery` with a token-OR string. Commit `41c54a7` has the implementation — `_build_bm25_or_tsquery_string` in `rag_service.py`.

**How to not be fooled again:** When retrieval looks like it "works sometimes," suspect that a different path is actually doing the retrieval. Grep logs for `Keyword fallback triggered` — if it fires on every query, the primary retrieval path is dead.

## 2. JSONB null literal vs SQL NULL — the producer bug

**Symptom:** Voucher filter using `chunk_metadata->>'is_voucher' IS DISTINCT FROM 'true'` behaves as expected, but legitimate non-voucher chunks are being treated as having metadata. Database rows show `jsonb_typeof = 'null'` instead of SQL `NULL`.

**Mechanism (April 15 late night):** SQLAlchemy's `JSONB` type defaults to `none_as_null=False`. With that default, Python `None` assigned to a `JSONB` column is serialized as the JSONB literal `null`, not as SQL `NULL`. The `DocumentChunk` model used bare `JSONB` without the flag, so every non-voucher chunk was written with the wrong null representation.

**Fix pattern (two parts):**
```python
# backend/app/models/document_chunk.py
chunk_metadata: Mapped[Optional[dict]] = mapped_column(
    "chunk_metadata",
    JSONB(none_as_null=True),  # load-bearing flag
    nullable=True,
)
```
Plus an Alembic backfill migration converting existing JSONB-null rows to SQL NULL, with pre/post counts that raise hard if conversion is incomplete. Commits `72fe10a` + `c237b4a`.

**How to not be fooled again:** When `IS NULL` comparisons behave unexpectedly on a JSONB column, check the producer, not just the consumer. REPL-verify the type's default (`JSONB().none_as_null`) before assuming the framework does the sensible thing.

## 3. Cohere SDK v2 kwarg breakage

**Symptom:** Every chat query logs `TypeError: AsyncV2Client.rerank() got an unexpected keyword argument 'return_documents'`. Reranker silently falls back to unranked top-K. Precision drops by 15-30% across the board, often invisibly.

**Mechanism (April 9 evening):** Cohere SDK v2 removed the `return_documents` kwarg that v1 accepted. The reranker service code was written against v1.

**Fix pattern:** Remove the kwarg from the `client.rerank()` call in `reranker.py`. Keep all other parameters. Re-test by grepping Railway logs for `TypeError` — should be absent.

**How to not be fooled again:** Cohere is on rapid SDK iteration. When a reranker-related bug surfaces, check the SDK version in `requirements.txt` against Cohere's current docs before assuming the bug is in our code.

## 4. Alembic migration cycle / duplicate revision ID

**Symptom:** Railway deploy fails with "Multiple head revisions" or "Revision X is present more than once" or "Can't locate revision identified by Y."

**Mechanism:** Migration chain accumulated two files with the same revision ID, or the production DB was stamped at a revision that doesn't exist locally, or a stub migration collided with an existing file.

**Fix patterns:**
- Duplicate ID collision: delete the duplicate file, keep the original, re-push.
- Missing revision in codebase (DB stamped, file missing): create a stub migration file at the missing revision ID so Alembic's chain resolves.
- Schema already applied but migration tries to create: `railway run alembic stamp <revision>` to mark as applied without running.

**How to not be fooled again:** Before committing a new migration, `alembic heads` should return exactly one. `alembic current` on production should match the latest file-system revision post-deploy.

## 5. Embedding dimensionality mismatch

**Symptom:** Vector search consistently returns zero matches despite embeddings being populated on chunks.

**Mechanism:** Query embedder produces N-dimensional vectors; chunk embeddings are M-dimensional. `pgvector` cosine distance across mismatched dimensions returns zero on every row.

**Prevention:** Do not swap embedding models without a migration plan. The column is `VECTOR(1536)` for `text-embedding-3-small`. A swap to Gemini (3072) or BGE-large (1024) requires:
1. Column type change migration
2. Full re-embed of every chunk in the database (expensive, runs at embedding API rate limits)
3. Coordinated deploy so query-side embedder updates simultaneously

This is why the Gemini multimodal migration is deferred — not hard, just not urgent enough to justify the re-embed cost yet.

## 6. Voucher classification contamination

**Symptom:** A 2024 Form 1040 upload ends up classified as `Form 1040-ES / Period: 2025` in document-level metadata. Chunk headers carry the wrong tax year even though the return is for 2024. LLM confuses years in responses.

**Mechanism:** Many 1040 PDFs have 1040-ES vouchers bound at the front. The document classifier runs against the first page(s) and sees the voucher first. Voucher chunks are filtered from retrieval but document-level classification is set once at ingest and persists.

**Mitigation:** Per-chunk `TAX YEAR YYYY` stamping from filename extraction (April 9 late). The chunk header is authoritative in the LLM prompt. Document-level classification is now a hint, not a truth.

**Remaining caveat:** The LLM can still be confused by `Period: YYYY` in the header if the year disagrees with the `TAX YEAR` tag. This is behind the Q1-AGI-specific year confusion observed on April 9 and partially mitigated by the April 9 late prompt changes.

## 7. Reprocess doesn't re-run financial metric extraction

**Symptom (unconfirmed):** After a reprocess, financial metrics tables are stale — they still show values extracted from an older version of the document.

**Mechanism (hypothesis):** `reprocess_service.py` re-runs text extraction, chunking, and embedding, but may not invoke the financial metric extractor. This is carried over from prior sessions unverified.

**Fix pattern (to verify):** Grep `reprocess_service.py` for `financial_metric` or `financial_extraction`. If absent, hook the extraction into the reprocess flow.

## 8. In-memory task tracking loss on redeploy

**Symptom:** After a Railway redeploy, `GET /api/admin/reprocess-status/{task_id}` returns 404 for recently-started tasks.

**Mechanism:** `REPROCESS_TASKS` is a module-level dict in `reprocess_service.py`. Dict is lost when the Python process restarts.

**Fix pattern (not yet implemented):** Persist task state to Postgres — either a `background_tasks` table or a JSON column on a pre-existing table. Known open item.

## 9. Eval quota gate false positive on synthetic user

**Symptom:** Ground-truth eval endpoint returns `HTTP 200` with every per-question response as "You've reached your monthly query limit."

**Mechanism:** The `eval_ground_truth` user is quota-gated like a real user. Internal chat calls during the eval count against quota. After ~5 eval runs, the total-query limit (50) is hit and the gate fires on every subsequent call, invisibly.

**Current workaround:** One-time `DELETE FROM token_usage WHERE user_id = 'eval_ground_truth'` to reset the counter.

**Proper fix (pending):** Add `is_admin_eval` context flag through `route_completion` → `check_total_query_quota`. Eval endpoint sets the flag on internal chat calls, gate short-circuits. Also tag eval rows with `is_eval = true` so `_count_chat_usage` filters them out.

## 10. Raw output collapsed during live debugging

**Symptom:** `+100 lines (ctrl+o to expand)` or `[function shown]` in a tool result. Five to fifteen minutes of back-and-forth to recover the hidden content.

**Mitigation (operational, not a code fix):** Write to file first, then `sed -n` in ≤40-line chunks. See `methodology.md`.

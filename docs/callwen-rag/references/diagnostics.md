# Callwen RAG — Diagnostics Reference

Load this when actively debugging a retrieval bug, a bad eval result, or an upload that went wrong. For the debugging discipline that tells you *when* to run each of these, see `methodology.md`.

## Table of contents

1. [Railway log patterns to grep for](#railway-log-patterns)
2. [SQL: chunk population and embedding sanity](#sql-chunk-population)
3. [SQL: BM25 / tsvector sanity](#sql-bm25-tsvector)
4. [SQL: client_id and document_id consistency](#sql-consistency)
5. [SQL: chunk_metadata distribution](#sql-metadata)
6. [SQL: tsquery behavior pre-flight](#sql-tsquery-preflight)
7. [Railway CLI patterns](#railway-cli)
8. [Live eval run](#live-eval)
9. [Reprocess a client's documents](#reprocess)

---

## Railway log patterns {#railway-log-patterns}

Every query flows through structured logging. Grep the Railway logs for these lines to understand what the pipeline did.

| Pattern | What it tells you |
|---|---|
| `Hybrid search: N vector + N BM25 → N merged \| Xms` | How many hits each path returned and the merge count. `0 vector + 0 BM25` is the pre-April-15 signature of the AND-join BM25 bug + any vector issue. After `41c54a7`, BM25 should almost never be zero on a populated client. Vector can legitimately be zero on very short queries. |
| `Reranker: N → N (Xms)` | Top-K in vs top-5 out. If this line is missing entirely, check whether `COHERE_API_KEY` is set and whether the Cohere client initialized. |
| `Keyword fallback triggered: query=X phrases=[...]` | Fallback path engaged. The old "keyword carrying the system" signature is this line firing on every query. Post-April 15 this should be rare. |
| `Total query limit reached for user X (used=N/M)` | Quota gate hit. If this shows up on the synthetic `eval_ground_truth` user, see `references/eval.md` — there's a known quota gate false-positive pattern. |

Capture logs historically, not via stream. Streaming `railway logs` dies after ~500 lines silently; `railway logs --since Nm > /tmp/capture.log` is deterministic.

## SQL: chunk population and embedding sanity {#sql-chunk-population}

Is the chunk data actually there?

```sql
-- How many chunks does the document have, and are embeddings populated?
SELECT
  COUNT(*) AS total_chunks,
  COUNT(embedding) AS chunks_with_embedding,
  COUNT(*) - COUNT(embedding) AS chunks_missing_embedding
FROM document_chunks
WHERE document_id = '<document_id>';
```

If `chunks_missing_embedding` is nonzero, reprocess did not finish or embedding writes failed. Look for `OpenAI rate limit` or write errors in logs for the relevant time window.

```sql
-- Are the embeddings the right dimensionality?
SELECT array_length(embedding::real[], 1) AS dims
FROM document_chunks
WHERE document_id = '<document_id>' AND embedding IS NOT NULL
LIMIT 3;
```

Vector column is `VECTOR(1536)` for `text-embedding-3-small`. If this returns 3072 or 768, either the column was altered or chunks were embedded with the wrong model — either is a real bug. Query embeddings must match chunk embeddings or `pgvector` returns zero results on every cosine query.

## SQL: BM25 / tsvector sanity {#sql-bm25-tsvector}

Is the full-text column populated?

```sql
SELECT
  COUNT(*) AS total_chunks,
  COUNT(search_vector) AS chunks_with_tsvector,
  COUNT(*) - COUNT(search_vector) AS chunks_missing_tsvector
FROM document_chunks
WHERE document_id = '<document_id>';
```

As of April 15 late night, whole-table is `393/393/0` — zero missing. If new chunks come in with NULL `search_vector`, the `trg_update_search_vector` trigger did not fire on INSERT. Check the trigger exists:

```sql
SELECT tgname, tgrelid::regclass, tgfoid::regproc
FROM pg_trigger
WHERE tgrelid = 'document_chunks'::regclass;
```

## SQL: client_id and document_id consistency {#sql-consistency}

Did the IDs drift?

```sql
SELECT DISTINCT client_id
FROM document_chunks
WHERE document_id = '<document_id>';
```

Should return exactly one client_id, matching what the eval / chat call is filtering on. A mismatch here means the retrieval filter excludes all chunks.

For Michael Tjahjadi (the reference eval client):
- `client_id`: `92574da3-13ca-4017-a233-54c99d2ae2ae`
- `document_id` (2024 1040): `af525dbe-2daa-4b93-bfde-0f9ed9814e41`
- Chunk count: 236

## SQL: chunk_metadata distribution {#sql-metadata}

The JSONB-null-vs-SQL-NULL distinction matters here. After the April 15 fix (`72fe10a` + `c237b4a`), non-voucher chunks store SQL NULL and voucher chunks store a JSONB object with `is_voucher: true`. No chunk should store the JSONB literal `null`.

```sql
-- How is chunk_metadata distributed?
SELECT
  jsonb_typeof(chunk_metadata) AS jtype,
  chunk_metadata->>'is_voucher' AS is_voucher,
  COUNT(*)
FROM document_chunks
GROUP BY jtype, is_voucher
ORDER BY COUNT(*) DESC;
```

Expected post-April-15 distribution: `NULL/NULL/~388` + `object/true/5`. A row showing `null/null/N` with N>0 means the JSONB-null regression is back and the `none_as_null=True` flag was lost somehow.

## SQL: tsquery behavior pre-flight {#sql-tsquery-preflight}

Before changing BM25 tokenization code, establish whether the proposed change would actually help. This is the April-15-late-night pattern — it gated a code change that turned out to be worth doing.

```sql
-- Compare AND-join (plainto_tsquery) vs OR-join (to_tsquery) hit counts
-- for a single query against a single document.

-- AND-join baseline (pre-April-15 behavior):
SELECT COUNT(*) FROM document_chunks
WHERE document_id = '<document_id>'
  AND search_vector @@ plainto_tsquery('english', '<user query>');

-- OR-join with alphanumeric token extraction (current behavior):
SELECT COUNT(*) FROM document_chunks
WHERE document_id = '<document_id>'
  AND search_vector @@ to_tsquery('english', '<token1> | <token2> | <token3>');
```

If the OR-join doesn't dramatically change hit counts, the hypothesis that tokenization is the issue is wrong — look elsewhere before changing code.

## Railway CLI patterns {#railway-cli}

```bash
# Historical log capture (reliable)
railway logs --since 5m > /tmp/capture.log
wc -l /tmp/capture.log
sed -n '1,40p' /tmp/capture.log     # read in 40-line chunks

# Run a migration on production
railway run alembic upgrade head

# Stamp a migration as applied without running it
# (Use when prod DB already has the schema from a manual SQL apply)
railway run alembic stamp <revision_id>

# Run an admin endpoint as a one-off
railway run python -c "..."
```

**Do not** `railway logs` as a background stream for diagnostics. It disconnects silently after ~500 lines. Trigger the event (eval run, chat query), wait for completion, then historical-fetch the window.

## Live eval run {#live-eval}

```bash
# Run the ground-truth eval against a client
curl -X POST "$CALLWEN_BACKEND_URL/api/admin/evaluate-rag-ground-truth/<client_id>" \
  -H "X-Admin-Key: $ADMIN_API_KEY" \
  -H "Content-Type: application/json"
```

The response includes:
- `eval_id` — UUID for later lookup in `rag_evaluations` table
- `retrieval_hit_rate`, `response_keyword_rate` — headline scores
- `per_question` — array of debug payloads with retrieved chunks, retrieved pages, response, latency, confidence

Compare eval IDs across runs to measure deltas. Eval history for reference:

| Eval ID | Date | Retrieval / Keyword | Real correctness |
|---|---|---|---|
| `daa9a463` | Apr 9 | 100% / 80% | 7/10 |
| `2401ff0a` | Apr 12 | 100% / 100% | 9/10 |
| `60c2f234` | Apr 12 | 100% / 100% | 9/10 (headers suppressed) |
| `17b8ee57` | Apr 16 03:20 UTC | **100% / 100%** | **100%** (rubric corrected) |

## Reprocess a client's documents {#reprocess}

```bash
# Force reprocess — re-extracts, re-chunks, re-embeds
curl -X POST "$CALLWEN_BACKEND_URL/api/admin/reprocess-documents" \
  -H "X-Admin-Key: $ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"client_id": "<client_id>", "force": true}'
```

Returns a `task_id`. Poll status:

```bash
curl "$CALLWEN_BACKEND_URL/api/admin/reprocess-status/<task_id>" \
  -H "X-Admin-Key: $ADMIN_API_KEY"
```

Known caveat: `REPROCESS_TASKS` is an in-memory dict. Status is lost on Railway redeploys. Persistence is a known open item. Another known caveat: reprocess may not re-run financial metric extraction (observed, not confirmed — grep `financial_metric|financial_extraction` in `reprocess_service.py` to verify before relying on it).

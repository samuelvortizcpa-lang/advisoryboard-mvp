---
name: callwen-rag
description: Architecture, debugging patterns, and methodology for Callwen's RAG pipeline — the CPA document intelligence system on FastAPI/pgvector with hybrid search (vector + BM25 + RRF), Cohere reranking, Google Document AI, and a ground-truth eval framework. Use whenever the user asks about Callwen's retrieval system, RAG chat quality, chunking, embeddings, eval runs, Document AI, the context assembler, `rag_service.py`, `hybrid_search.py`, `reranker.py`, `chunking.py`, `rag_eval_fixtures.py`, or says things like "why is retrieval returning X," "our RAG is doing Y," "the eval shows Z." Use even when the user doesn't say "RAG" — if they mention a retrieval bug, wrong answer on a tax question, chunk issue, vector search oddity, or Cohere/BM25/pgvector question in the Callwen context, this is the reference. Use when writing Claude Code prompts touching the retrieval layer, drafting session summaries about RAG work, or planning new RAG features. Not for non-Callwen RAG or general theory.
---

# Callwen RAG — Architecture, Debugging, and Methodology

This skill is the canonical reference for Callwen's RAG system. It exists because the retrieval layer has been rebuilt and tuned across dozens of sessions, and every new piece of work on it needs the same context: the current architecture, the known caveats, the diagnostic patterns, and — most importantly — the debugging discipline that has consistently found real bugs while a looser approach has consistently invented wrong ones.

Read this first. Then decide which reference file to load for the task at hand.

## When to consult this skill

- User asks about retrieval quality, eval scores, chunking, embeddings, BM25, reranking, or Document AI
- User is debugging a wrong answer from the chat, a missing source card, or a confidence score anomaly
- User is writing a Claude Code prompt that touches `rag_service.py`, `hybrid_search.py`, `reranker.py`, `chunking.py`, `text_extraction.py`, `document_ai_service.py`, `tax_terms.py`, `rag_evaluator.py`, `rag_eval_fixtures.py`, or `context_assembler.py`
- User is planning RAG feature work (synonym dictionary, multimodal, new document type, new eval fixture client)
- User wants to understand what the eval numbers mean or whether a change moved the needle

## Current state (as of April 16, 2026)

The retrieval layer is structurally sound end-to-end. Eval on the reference client (Michael Tjahjadi, 2024 Form 1040, `client_id 92574da3-13ca-4017-a233-54c99d2ae2ae`, 236 chunks) now measures three metrics across the 10-question ground-truth set:

- **Retrieval hit rate: 1.0** — holds steady. Every expected page appears in the retrieved chunks.
- **Keyword hit rate: 0.9–1.0** — hovers depending on Q4's LLM nondeterminism (see caveats). The prior 100% floor was partly artifact: Q4's old rubric `["$7", "7"]` matched bare "7" in incidental text. Tightened to `["$7.00", "$7."]` in `e641cb8`.
- **Citation hit rate: 0.6** — new metric as of `4b53a59`. Measures whether the LLM's emitted (Form X, Line Y) pair matches the ground-truthed `expected_citations` in `rag_eval_fixtures.py`. Strict: line-only or page-only = miss.
- **Avg latency: ~2.9s** (≤4.3s floor).

Latest eval: `d1fb0a2e` (Apr 16 04:25 UTC). Latest Railway deploy: commit `4b53a59`. Previous reference eval `17b8ee57` (100/100/3.8s on commit `7b876f0`) remains valid for retrieval/keyword comparison but predates the citation metric.

What these numbers mean and how to trust them is covered in `references/eval.md`. The short version: the eval is real signal, not rubric noise, because the rubric itself was ground-truthed against the source document. The citation metric is the newest addition — it catches cases where the LLM gives the right number but cites the wrong form or line.

## The pipeline in one breath

```
Upload → Classify (GPT-4o-mini or Document AI)
  → Financial PDF → Document AI Form Parser (structured KV)
  → Other PDF    → Document AI OCR (or pdfplumber fallback)
  → Smart chunking (page-aware, type-specific sizes, [Page N] markers)
  → Embed (OpenAI text-embedding-3-small, 1536 dims)
  → Store in pgvector + trigger auto-populates BM25 tsvector

Query → Query router (factual vs strategic model selection)
  → Hybrid search (vector + BM25 OR-ranker merged via RRF k=60)
  → Cohere Rerank v3.5 (top-20 → top-5, optional/graceful)
  → Context assembler (purpose-based token budgets)
  → LLM generation (GPT-4o-mini / Claude Sonnet / Claude Opus)
  → Response + source cards + confidence badge + pipeline stats
```

For the detailed component breakdown, commit history, and file map, load `references/architecture.md`.

## The load-bearing rule

**Data first, hypothesis second.** Every failed debugging session on this codebase has started with a confident hypothesis and skipped the data check. Every successful one has started with a SQL query, a log capture, or a chunk inspection, and let the data shape the hypothesis. The April 14 morning session killed three hypotheses in a row before finding the real bug by forcing itself to read the full query log end to end. The April 15 late-night session found the JSONB producer bug by reading the model column definition line by line after a REPL check falsified the column-default assumption.

When a new hypothesis forms the moment the data arrives, that is the tell to stop and re-read the data. If you skip this step, you will spend 2-3x more time and likely fix the wrong thing.

The full methodology, with the specific disciplines that have repeatedly paid off (raw output discipline, historical log fetch, verify-before-edit, SQL pre-flight gates, carryover-as-bug-class-not-line-list, resist-momentum gates), lives in `references/methodology.md`. Load it before any live debugging session, not after the debugging has gone off the rails.

## When the user reports a retrieval bug

Work in this order. Do not skip steps.

1. **Capture the exact failure.** What was the query, what was the response, which client, which document, which eval ID if applicable. Get the Railway log snippet — specifically the `Hybrid search: N vector + N BM25 → N merged | Xms` line for the failing query. Without this, every next step is guessing.

2. **Locate the chunks that should have matched.** Pull the document's chunks from Postgres and find the chunk that contains the correct answer. You're establishing whether this is a retrieval miss (the right chunk exists, vector + BM25 didn't find it) or an upstream miss (the chunk doesn't exist, or exists but doesn't contain the expected text because extraction lost it).

3. **Now form a hypothesis.** Only now. Cross-reference the log line against the code path. If vector returned 0, is the embedding populated? Is dimensionality right? If BM25 returned 0, does `to_tsquery` produce tokens that appear in `search_vector`? If both returned results but the right one wasn't in top-5, is reranking actually running (no `return_documents` kwarg crash)?

4. **Pre-flight the fix in SQL before changing code.** If you think switching from AND-join to OR-join will help, run the SQL manually against production first. If it doesn't change the picture, the code change isn't worth doing. This gate has saved at least one session from shipping a useless change.

5. **Regression-test locally, then eval post-deploy.** Add a unit test that fails before the fix and passes after. After deploy, run the ground-truth eval. The eval is trustworthy now — believe the delta.

For the specific diagnostic SQL queries, log patterns, and Railway commands used repeatedly in RAG debugging, load `references/diagnostics.md`.

## Known caveats (current)

Things working correctly but with known limitations. Do not treat these as bugs without checking the carryover first.

- **Acronym/long-form vocabulary mismatch.** BM25 matches literal tokens. Tax docs say "Adjusted Gross Income"; users type "AGI." Vector search handles the semantic bridge today. A synonym layer (postgres text search synonym config, or LLM query expansion) is a future option but not urgent.
- **Q6 and Q9 explanation noise.** Numbers are correct; LLM explanations sometimes pull adjacent instructional text (e.g., age-55 HSA conditional, "Line 7" standard-deduction confusion). Prompt refinement territory, not retrieval.
- **Q4 taxable interest is fragile.** $7 on Form 1040 line 2b is adjacent to $136 on line 2a and $7 on Form 8960 line 1. LLM answers vary run-to-run ($0, $7, sometimes others). Two samples so far; reliability unknown until characterized over more eval runs.
- **Citation accuracy is a new metric (0.6 baseline).** `citation_hit_rate` measures whether the LLM's emitted (Form X, Line Y) pair matches an `expected_citations` entry in the rubric. Strict scoring: both Form and Line required, page-only or line-only citations = miss. Most misses are the LLM saying "page N of the 2024 Tax Return" without naming the form — not a retrieval or correctness bug, but a citation-specificity gap.
- **`flag_voucher_continuations` imported but uncalled in the upload path** (`rag_service.py:47`). Only the admin batch scanner invokes it. Continuation chunks adjacent to voucher pages aren't flagged at upload time. Separate session.
- **SQLite/TSVECTOR test infrastructure gap.** 58 baseline test "errors" come from SQLite inability to compile TSVECTOR. Chunk-pipeline tests currently inert against the real schema.
- **Reprocess doesn't re-run financial metric extraction.** Observed but not confirmed; grep `financial_metric|financial_extraction` in `reprocess_service.py` to verify before acting.

Full caveat catalog with history in `references/known-gotchas.md`.

## Reference files

Load these only when the task demands them. They exist so this top-level file stays navigable.

- **`references/architecture.md`** — Full pipeline breakdown, file map (all service paths), commit history of the major rebuilds, tech stack reference, deployment workflow.
- **`references/diagnostics.md`** — SQL queries (chunk counts, embedding populatedness, search_vector sanity, client_id consistency, tsquery behavior), log patterns to grep for, Railway CLI patterns (historical fetch not streaming).
- **`references/methodology.md`** — The debugging disciplines. Read before live debugging. Includes raw output discipline, verify-before-edit pattern, SQL pre-flight gate, resist-momentum gates, carryover-as-bug-class principle.
- **`references/eval.md`** — How the ground-truth eval works, what the fixtures look like (`rag_eval_fixtures.py`), which fields in the fixture matter (`expected_page`, `expected_answer_contains`, `expected_citations`, `notes`), how to interpret retrieval vs keyword vs citation vs real correctness, how to add a new client fixture.
- **`references/known-gotchas.md`** — Catalog of failure modes observed at least once: Cohere SDK v2 breakage, Alembic duplicate revision IDs, embedding dimension mismatches, SQLAlchemy JSONB `none_as_null` default, AND-joined tsquery failure mode, stale `search_vector` hypothesis class, voucher classification contamination from front-of-PDF pages. Includes the fix pattern for each.

## What not to do

- **Don't trust a carryover's line-number list without checking the bug class first.** The April 15 late-night session found the JSONB producer bug in a file the previous carryover didn't list. The carryover was right about the *class* (producer writing JSONB null) and wrong about the *location*. Use carryovers as hypothesis starters, not scavenger hunts.
- **Don't fix Q6/Q9 prompt noise inline with other work.** Prompts have a budget. Every added constraint risks collapse on untested queries. Do prompt refinement as a dedicated session with its own eval against a broader question set.
- **Don't skip the eval after a retrieval-layer change.** The eval is real signal now. An unverified change lands without knowing whether the score moved.
- **Don't ship an embedding model swap casually.** Vector column is 1536 dims. Switching models is a migration + full re-embed. Defer until user volume or quality justifies it; see `AdvisoryBoard_OpenSource_FineTuning_Strategy.docx` for the full analysis.
- **Don't use bare single-digit keywords in `expected_answer_contains`.** A value like `"7"` matches incidental 7s in page numbers, line numbers, and other numeric text — producing false positives that inflate `keyword_hit_rate`. Include the `$` prefix or trailing punctuation (`"$7.00"`, `"$7."`) so normalization doesn't collapse to a single-digit substring. This bit the Q4 rubric; fixed in `e641cb8`.

## Recent commits (eval layer)

- `e641cb8` — feat(eval): add expected_citations to ground-truth rubric
- `4b53a59` — feat(eval): add citation_hit_rate as third eval metric

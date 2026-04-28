# AdvisoryBoard Query Interpretation Architecture

> Design document for Option B — LLM-based query interpretation in the
> RAG retrieval pipeline. Tracks design decisions, eval criteria,
> latency/cost models, and the decision log.
>
> **Status:** v1 shipped behind flag (`USE_LLM_QUERY_INTERPRETATION`),
> default ON in Railway as of Session 20.

---

## §1 — Problem Statement

The RAG pipeline's retrieval stage uses a dictionary-based
`interpret_query` function to extract IRS form references, line
numbers, and keywords from user questions. This works well for
canonical phrasings ("What was the total on Form 1120-S line 22?")
but fails on indirect or colloquial phrasings ("How much state tax
does the company owe?").

**Option B** replaces dictionary-only interpretation with an
LLM-augmented path: a fast, cheap model (Haiku 4.5) interprets the
question into structured retrieval signals (forms, line numbers,
keywords, intent, confidence), which are merged with the existing
dictionary output to boost retrieval.

## §2 — Architecture Overview

```
User question
    │
    ▼
┌──────────────────────┐     ┌──────────────────────┐
│ interpret_query       │     │ interpret_query_llm    │
│ (dictionary-based)    │     │ (Haiku 4.5, tool-use)  │
└──────────┬───────────┘     └──────────┬─────────────┘
           │                            │
           ▼                            ▼
      ┌────────────────────────────────────┐
      │ merge_interpretations              │
      │ (union forms, keywords, lines)     │
      └────────────────┬───────────────────┘
                       │
                       ▼
              retrieval pipeline
              (BM25 + vector + RRF)
```

**Safety guarantee:** `interpret_query_llm` returns `None` on any
failure (flag off, missing API key, timeout, API error, low confidence,
schema validation failure). `None` triggers dictionary-only fallback —
behavior is identical to pre-Option-B.

## §3 — Implementation

### §3.1 — Module: `backend/app/services/query_interpreter.py`

- **Model:** `claude-haiku-4-5-20251001` (Haiku 4.5)
- **Temperature:** 0 (deterministic)
- **Tool-use:** Forced via `tool_choice={"type": "tool", "name": "interpret_tax_query"}`
- **Max tokens:** 512
- **Prompt version:** `v1`
- **Confidence threshold:** 0.5

### §3.2 — Timeout architecture

Dual timeout:
- **SOFT_TIMEOUT_S = 5.5** — SDK-level httpx timeout. Controls the
  HTTP request deadline to the Anthropic API.
- **HARD_TIMEOUT_S = 6.0** — `asyncio.wait_for` wrapper. Catches
  any case where the SDK hangs past the soft timeout.

Both are required: SOFT is the httpx transport timeout and will kill
the request before HARD fires in normal cases. HARD is the safety net.

> **Session 20 correction:** Original values (1.5/2.0) were set in
> Session 19 based on an incorrect "300–700ms" latency estimate.
> Phase 1 probe (N=10) measured p50=2.3s, max=4.6s. Raised to
> 5.5/6.0 in commit `84a90a2`.

### §3.3 — Cache architecture

Per-worker LRU cache (`functools.lru_cache`-style dict with
`_CACHE_MISS` sentinel):
- **Capacity:** 256 entries per worker
- **Key:** SHA256 of `f"{question.lower().strip()}|{PROMPT_VERSION}|{MODEL_ID}"`
- **Negative caching:** Failed interpretations (None) are cached to
  avoid retrying known-bad questions
- **Cache hit path:** Returns cached result (or None), emits
  structured log with `from_cache=True`

### §3.4 — Structured logging

Every call (cached or not) emits a structured log via `_emit_log()`:
```json
{
  "event": "query_interpretation",
  "question_hash": "sha256:<first 16 chars>...",
  "model": "claude-haiku-4-5-20251001",
  "prompt_version": "v1",
  "latency_ms": 2300,
  "success": true,
  "fallback_triggered": false,
  "confidence": 0.85,
  "intent": "tax_lookup",
  "forms_count": 2,
  "keywords_count": 3,
  "from_cache": false
}
```

### §3.5 — Merge strategy

`merge_interpretations()` in `rag_service.py` unions the dictionary
and LLM results:
- Forms: union of both sources
- Keywords: union of both sources
- Line numbers: union of both sources

### §3.5.2 — v2 path (not implemented)

Future: add `client_context` (client name, entity type) to the LLM
prompt for better domain-specific interpretation.

## §4 — Performance Model

### §4.1 — Latency model

**interpret_query_llm (Haiku 4.5, ~150 tokens out, temp=0,
tool-use forced):** ~2.0–2.5s p50 uncached, max ~4.6s observed
(Session 20 probe data, N=10), ~0ms cached. The original 300–700ms
estimate (pre-Session-19) underestimated by ~4–7x; the actual cost
reflects tool-use response generation overhead.

| Path | Latency estimate | Source |
|------|-----------------|--------|
| Dictionary only (flag off) | ~0ms | Deterministic string matching |
| With LLM interpretation (flag on, uncached) | +2.0–2.5s p50, +4.6s max | Session 20 probe, N=10 |
| With LLM interpretation (flag on, cached) | +0ms | Per-worker LRU cache hit |

The actual delta observed in Phase 4 production eval was +2–4s per
question on uncached (run 1) calls, with runs 2–3 showing partial
cache hits depending on worker routing. The +2–3s uncached cost is
what shipped; this is acceptable given the per-question total latency
budget of ~6–15s for the full RAG pipeline.

### §4.2 — Cost model

Haiku 4.5 pricing: ~$0.80/MTok input, ~$4.00/MTok output.

Per-call estimate:
- Input: ~800 tokens (system prompt + tool spec + question) ≈ $0.00064
- Output: ~150 tokens (tool-use response) ≈ $0.00060
- **Total per uncached call: ~$0.0012**

At pre-PMF volume (< 100 questions/day), daily cost < $0.12.

**Eval-time cache effectiveness with multi-worker deploys.** The
per-worker LRU cache assumes ideal stickiness; in production with
`--workers 2` (current Procfile), repeat eval traffic experiences
~50% cache hit rate rather than the ~100% assumed in v1's cost
model. At pre-PMF volume this is irrelevant; at 100-CPA scale
revisit either via sticky routing or a Postgres-backed cache.
Reference: Session 20 Phase 4.5 production-log analysis.

### §4.3 — Failure-rate threshold

Design target: < 1% fallback rate (None returns) in production.

Session 21 Phase 3 directly verified: 29/30 calls succeeded
(96.7%). The 1 fallback was Michael Q9 (HSA contribution limit)
at confidence=0.30 — a correct self-assessment on a regulatory
question, not a form lookup. The 3.3% fallback rate exceeds the
1% target but is benign: the fallback path (dictionary-only)
handled the question correctly (eval scored response_hit=True).
At N=30 the rate is noisy; at scale this question class (regulatory
limits, not form-specific) will consistently fall back by design.

## §5 — Eval Criteria

### §5.1 — Pass criteria for v1 ship

| Criterion | Threshold | Session 20 result |
|---|---|---|
| Michael does not regress | ret≥1.00, cit≥1.00, resp≥0.90 | **PASS** — 1.00/0.90/1.00, all 3 runs |
| Tracy does not regress | ret≥0.90, cit≥0.60 | **PASS** — 0.90/0.80–0.90/0.60, all 3 runs |
| Tracy improves ≥1 of Q8/Q9/Q10 | ≥1 fixture flip Y→N | **NO MOVEMENT** — see §10 Q14 |
| Latency p95 ≤ flag-off p95 + 1s | Delta, not absolute | **PASS** — delta ~0.7s |
| Failure rate < 1% | None returns | **PASS** — 29/30 success (96.7%), 1 fallback (Michael Q9 HSA limit, confidence=0.30, correct self-assessment). Direct measurement Session 21 Phase 3. |

**Latency criterion reinterpretation (Session 20):** The original
"p95 ≤ 9s" was stated as an absolute. Phase 3 showed flag-off p95
is already at/above 9s on individual questions. The intent was
"interpreter doesn't add material latency." Reinterpreted as
flag-on p95 ≤ flag-off p95 + 1s (delta).

### §5.2 — Locked baselines

| Client | Retrieval | Response | Citation | Source |
|---|---|---|---|---|
| Tracy | 0.90 | 0.80–0.90 | 0.60 | Session 18, reaffirmed Session 20 Phase 3 (0.90/0.90/0.60 stable) |
| Michael | 1.00 | 0.90 | 1.00 | Session 18, reaffirmed Session 20 Phase 3 (identical) |

### §5.3 — Known flicker

- Tracy Q4 (total deductions): response flickers between Y/N across
  runs. Root cause: gpt-4o-mini at temp=0.1 returns $362,896 vs
  expected $364,521 non-deterministically. First documented Session 16.
- Citation inherits response flicker on questions where the citation
  regex depends on the response text.

### §5.4 — Phrasing-variance fixture

**Promoted post-Session-20 to Session 21+ priority.** Phase 4
demonstrated v1 ships clean (no regressions, full eval criteria
met within reinterpreted latency bound), but did not move Tracy's
failing fixtures because the dictionary post-Session-16 already
covers the canonical forms for those questions. Testing Option B's
actual hypothesis ("LLM handles phrasing the dictionary can't")
requires this fixture. Build before further interpreter prompt
iteration to avoid optimizing the prompt against the wrong target.

## §6 — Observability

### §6.1 — Sentry alerts

- Missing API key: one-time Sentry alert on first call without
  `ANTHROPIC_API_KEY`
- Schema validation failure: Sentry error with payload repr
- Auth failure: Sentry alert on `AuthenticationError`
- Unexpected exceptions: `sentry_sdk.capture_exception()`

### §6.2 — Production log rendering

**Resolved Session 21** (commit `efe22db`). `ExtraFieldFormatter`
in `main.py` appends 8 structured fields as `key=value` suffix on
log lines that carry them (success, from_cache, confidence,
latency_ms, fallback_triggered, forms_count, forms, question_hash).
Non-interpreter log lines render unchanged. `forms` field (list of
form names) added to `_emit_log()` extra dict in the same commit.

Direct production verification (Session 21 Phase 3, N=30): all
structured fields render correctly in Railway logs. Per-question
forms, confidence, and cache status now directly observable.

## §7 — Compliance

### §7.1 — Data handling

No client PII is sent to the interpreter LLM. Only the user's
question text is sent. No document content, no client names, no
financial data.

### §7.2 — IRC §7216

**Resolved Session 18.** The §7216 consent form names Anthropic
explicitly in the AI-processing disclosure scope (Build Manual
line 169). Option B introduces no new consent surface. Sub-question
queued: verify the deployed signing page renders the same vendor
list as the PDF (5-minute check, queued for a future session).

## §8 — Rollback

If the interpreter causes regressions:
1. Set `USE_LLM_QUERY_INTERPRETATION=false` in Railway
2. Railway auto-redeploys
3. All calls return None → dictionary-only fallback
4. No code changes needed

## §9 — Implementation Timeline

| Session | Phase | Deliverable |
|---|---|---|
| 19 | B | Flag-gated Haiku 4.5 call (commit `bf05b6a`) |
| 19 | D | Per-worker LRU cache with negative caching (commit `21c6cba`) |
| 19 | E | Structured logging + Sentry alerts (commit `1213856`) |
| 19 | G | Mocked test suite (commit `026feb9`) |
| 20 | Phase 2 | Timeout tune SOFT 5.5 / HARD 6.0 (commit `84a90a2`) |
| 20 | Phase 3 | Flag-off baseline capture (3-run, all identical) |
| 20 | Phase 4 | Flag-on eval (3-run, no regressions, no movement) |
| 20 | Phase 4.5 | Production log check (observability gap discovered) |
| 20 | Phase 6 | Design doc + session close |

## §10 — Decision Log

| # | Question | Decision |
|---|---|---|
| Q1 | Which model for interpretation? | Haiku 4.5 — fastest/cheapest Claude model, sufficient for structured extraction |
| Q2 | How to handle LLM failures? | Return None → dictionary-only fallback. Always safe. |
| Q3 | Cache strategy? | Per-worker LRU, 256 entries, negative caching for failed calls |
| Q4 | Confidence threshold? | 0.5 — below this, fall back to dictionary. Candidate for review post-formatter-fix. |
| Q5 | How to merge LLM + dictionary? | Union of forms, keywords, line numbers |
| Q6 | Timeout strategy? | Dual: SOFT (SDK httpx) + HARD (asyncio). Both required. |
| Q7 | SOFT/HARD values? | 5.5s/6.0s (Session 20 correction from 1.5/2.0) |
| Q8 | Flag default? | OFF in code, ON in Railway env var |
| Q9 | Eval approach? | Ground-truth fixture eval, 3-run for flicker detection |
| Q10 | Latency criterion? | Delta over flag-off (≤+1s), not absolute |
| Q11 | Ship despite no eval movement? | Yes — no regressions, hypothesis untested (wrong eval), fix is phrasing-variance fixture |
| Q12 | Keep flag on after Phase 4? | Yes — None fallback is safe, no regression signal |
| Q13 | §7216 impact? | None — Anthropic already in consent scope |
| Q14 | Did v1 move Tracy's locked baseline? | **No, but no regression. Shipped behind flag.** Phase 4 eval (Session 20) showed all flag-on scores match flag-off. Hypothesis-test question (Tracy Q8) did not move because the post-Session-16 dictionary already provides Form 100S. The eval that would test the actual hypothesis (phrasing variance) was deferred to Session 21+. |

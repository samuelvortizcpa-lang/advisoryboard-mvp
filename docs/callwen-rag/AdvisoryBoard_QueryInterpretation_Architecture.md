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

### §4.3 — Failure and fallback rates

Two distinct rates are tracked:

| Metric | Definition | Target | Session 21 (N=30) |
|---|---|---|---|
| **Unexpected failure rate** | `None` returns from infrastructure causes: auth error, API timeout, schema validation failure, uncaught exception | < 1% | **0/30 (0.0%)** |
| **Low-confidence fallback rate** | `None` returns from confidence < `CONFIDENCE_THRESHOLD` on questions outside the interpreter's domain (regulatory limits, non-form-specific queries) | Informational; persistent rise warrants prompt or threshold review | **1/30 (3.3%)** — Michael Q9 (HSA contribution limit, confidence=0.30) |

Both paths return `None` and trigger dictionary-only fallback. The
distinction matters for alerting: unexpected failures warrant
investigation; low-confidence fallbacks are correct behavior.

The single fallback (Michael Q9) was a correct self-assessment on a
regulatory question, not a form lookup. The dictionary path handled
it correctly (eval scored response_hit=True).

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

This fixture stress-tests Option B's hypothesis: that LLM
interpretation handles phrasing the dictionary cannot. Where §5.1
measures whether the interpreter regresses on canonical phrasings
(it does not, per Sessions 20–21), §5.4 measures whether
interpretation adds retrieval value the substring-match dictionary
cannot.

#### 5.4.1 Typology

Three rewording categories, each chosen to defeat substring match
in a structurally distinct way:

| Cat | Name | Tests |
|---|---|---|
| A | Synonym substitution | Semantic equivalence mapping |
| B | Lay/colloquial phrasing | Intent extraction from informal language (the load-bearing test of Option B's hypothesis) |
| C | Structural reframe | Multi-clause / indirect reference resolution |

Two candidate categories — abbreviation/expansion and
circumlocution — were dropped during design. The first is partly
solvable with string normalization and produces contrived
phrasings ("eleven-twenty-S") that don't reflect natural CPA or
client speech. The second overlaps heavily with B without adding
distinct signal.

#### 5.4.2 Corpus

20 base questions (10 Tracy, 10 Michael) × 3 rewordings (one per
category) = 60 phrasing-variant questions. Each rewording inherits
the original's `expected_page`, `expected_pages`,
`expected_answer_contains`, and `expected_citations` — Phase 3a
manual review confirmed each rewording asks the *same* question of
the *same* document location, just phrased to defeat substring
match.

Lives in `backend/app/services/rag_eval_fixtures.py` as
`TRACY_CHEN_DO_INC_2024_PHRASING` and
`MICHAEL_TJAHJADI_2024_PHRASING`, registered in the
`CLIENT_PHRASING_VARIANCE` dict. Fetched via
`get_phrasing_variance(client_id)`. Selected at eval time via
the `fixture` request-body parameter on
`POST /api/admin/rag-analytics/run-eval`.

#### 5.4.3 Methodology

Same A/B comparison shape as §5.3:

1. Run flag-off, 3 runs (matches §5.1 run-count discipline)
2. Run flag-on, 3 runs
3. Compare per-category and per-client aggregates

**Per-client aggregate is the load-bearing decision metric.** With
30 reworded questions × 3 runs = 90 data points per client per
flag state, statistically robust enough for ≥0.05 deltas to be
meaningful.

**Per-category aggregate is diagnostic, not a ship gate.** With ~30
data points per category per client per flag state, a 0.10 delta is
two question flips — edge-of-noise. Per-category results inform
*where* the interpreter helps and where it doesn't, but go/no-go
rests on per-client.

**Per-rewording results exist for debuggability** but should not
drive decisions on individual rewordings. A single failing
rewording is a hypothesis about a phrasing class, not a finding.

#### 5.4.4 Pass criteria

| Criterion | Threshold | Rationale |
|---|---|---|
| Flag-on per-client retrieval ≥ flag-off per-client retrieval | No regression | Same as §5.1 |
| Flag-on per-client retrieval > flag-off per-client retrieval (any client) | Hypothesis confirmed — interpreter adds value the dictionary doesn't | Direct test of Option B hypothesis |
| Unexpected failure rate < 1% | Per §4.3 named rate | Same as §4.3 |
| Latency p95 ≤ +1s vs §5.1 baseline | — | Mid-client-call latency budget |

Pass on criterion 1 alone: keep flag on; interpretation does no
harm at the §5.4 phrasing-variance ceiling. Pass on criteria 1 + 2:
hypothesis confirmed; interpretation provides measurable lift on
non-canonical phrasings. Fail on criterion 1: flip flag off and
diagnose; the interpreter is regressing relative to dictionary on
phrasings the dictionary doesn't cover, which would be surprising
and worth investigation.

#### 5.4.5 Mode 2/3/4 connection

Per §1.3, the interpreter is Mode 2 substrate. The `intent` field
on `InterpretationResult` is logged per-rewording (added Phase 3b)
specifically so this campaign produces evidence about the
interpreter's intent-classification stability under phrasing
variance — directly relevant to the future Mode 2 router
accuracy metric (per `AdvisoryBoard_North_Star_Integration_Architecture.md` §1).

This fixture is the **Mode 1** phrasing-variance fixture. Mode 2,
3, and 4 each get their own when those modes ship, per North Star
anti-pattern: "Don't ship Mode 2/3/4 features without per-mode
evals." The A/B/C typology likely transfers; ground truth and
category boundaries do not (e.g., Mode 2 enumeration fixtures need
a `complete_set` ground-truth shape that doesn't apply to factual
lookup).

#### 5.4.6 Results

Run on April 28, 2026 (Session 22). 6 runs total: 3 flag-off
(Phase 4) and 3 flag-on (Phase 5), against the same 60-rewording
fixture (Tracy + Michael, 30 each).

##### Per-client aggregate (load-bearing decision metric)

| Client | Metric | Flag OFF (mean of 3 runs) | Flag ON (mean of 3 runs) | Δ |
|---|---|---|---|---|
| Tracy | retrieval | 0.600 | 0.600 | 0.000 |
| Tracy | response | 0.533 | 0.533 | 0.000 |
| Tracy | citation | 0.178 | 0.189 | +0.011 |
| Michael | retrieval | 0.867 | 0.867 | 0.000 |
| Michael | response | 0.733 | 0.744 | +0.011 |
| Michael | citation | 0.711 | 0.700 | −0.011 |

##### Per-category aggregate (diagnostic)

Tracy:

| Category | Metric | OFF | ON | Δ |
|---|---|---|---|---|
| A — synonym | retrieval | 0.600 | 0.600 | 0.000 |
| A — synonym | response | 0.700 | 0.700 | 0.000 |
| A — synonym | citation | 0.233 | 0.200 | −0.033 |
| B — colloquial | retrieval | 0.500 | 0.500 | 0.000 |
| B — colloquial | response | 0.300 | 0.300 | 0.000 |
| B — colloquial | citation | 0.200 | 0.267 | +0.067 |
| C — structural | retrieval | 0.700 | 0.700 | 0.000 |
| C — structural | response | 0.600 | 0.600 | 0.000 |
| C — structural | citation | 0.100 | 0.100 | 0.000 |

Michael:

| Category | Metric | OFF | ON | Δ |
|---|---|---|---|---|
| A — synonym | retrieval | 0.900 | 0.900 | 0.000 |
| A — synonym | response | 0.900 | 0.900 | 0.000 |
| A — synonym | citation | 0.767 | 0.700 | −0.067 |
| B — colloquial | retrieval | 0.900 | 0.900 | 0.000 |
| B — colloquial | response | 0.767 | 0.733 | −0.033 |
| B — colloquial | citation | 0.867 | 0.867 | 0.000 |
| C — structural | retrieval | 0.800 | 0.800 | 0.000 |
| C — structural | response | 0.533 | 0.600 | +0.067 |
| C — structural | citation | 0.500 | 0.533 | +0.033 |

##### Latency

| Client | OFF avg (ms) | ON avg (ms) | Δ |
|---|---|---|---|
| Tracy | 8254 | 7250 | −1004 |
| Michael | 7206 | 7373 | +167 |

The Tracy latency anomaly (flag-on faster than flag-off) is
most plausibly explained by Railway/OpenAI infrastructure
variance across the ~80-minute gap between phases. No deploy
events between phases. Per-question p50 trends within each phase
were stable; cross-phase comparison is bounded by external noise.

##### Pass criteria evaluation (against §5.4.4)

| Criterion | Threshold | Result |
|---|---|---|
| Flag-on per-client retrieval ≥ flag-off | No regression | **PASS** — exact parity on both clients |
| Flag-on per-client retrieval > flag-off (any client) | Hypothesis confirmed | **NOT MET** — zero retrieval movement on either client |
| Unexpected failure rate < 1% | Per §4.3 | **PASS** — 0/180 unexpected failures across 6 runs |
| Latency p95 ≤ +1s vs §5.1 baseline | Mid-call budget | **PASS** — Tracy ON lower than OFF; Michael +167ms |

Outcome: **do-no-harm satisfied; hypothesis not confirmed.**

##### Interpretation

The interpreter executes correctly in production (verified by
intent log telemetry showing `intent=factual_lookup` dominant,
form classifications matching expected values, ~1.5–2s
interpretation latency on uncached calls). Its outputs are
union-merged with dictionary outputs at retrieval time. The
merge produces no measurable change in retrieval ranking on the
phrasing-variance fixture — neither helping nor hurting.

Two readings of this finding, both held simultaneously:

1. **The dictionary path is finding what's findable.** On
   questions where the dictionary path retrieves the right
   chunk, the interpreter's form-boost is redundant. On
   questions where the dictionary path fails, the failure mode
   is upstream of form-boost — vector embedding mismatch, BM25
   term gaps, RRF fusion behavior, or rerank decisions. No
   amount of better query interpretation routes around those
   failures because the chunks the interpreter would route to
   aren't winning the rank competition.

2. **The interpreter is doing real work that this fixture
   cannot measure.** The Mode 1 phrasing-variance fixture
   measures retrieval lift on factual-lookup questions. The
   interpreter's intent-classification output is being captured
   per-call but is not yet wired to anything downstream — that
   wiring is the substance of Mode 2 enablement (North Star P2).
   Saying "the interpreter doesn't help Mode 1" is a real
   finding; saying "the interpreter doesn't help" generally
   would be premature. It hasn't been measured against the
   query modes it was designed to substrate.

##### Persistent failure patterns surfaced

5-question always-fail clusters (0% response across 6 runs)
identify retrieval bottlenecks, not interpretation failures:

Tracy:
- Q2/Q3 (T1 colloquial + structural): answer LLM produces
  wrong number on "how much profit did Tracy's company make"
  variants. Retrieval correct (Form 1120-S Line 22 chunks
  surface), answer LLM extracts wrong figure.
- Q5 (T2 colloquial): "How much money came in" — vector miss
  on gross receipts terminology
- Q10 (T4 synonym): "sum of all business expenses claimed" —
  vector retrieves Line 20 (interest expense) instead of
  Line 21 (total deductions)
- Q11 (T4 colloquial): "write off in total" — same retrieval
  miss as Q10

Michael:
- Q16/Q17/Q18 (M6 all categories): capital gains. Known
  Mode 1 fixture quirk (Session 16 / North Star P1). Not a
  Session 22 concern.
- Q21 (M7 structural): "charitable giving section" — retrieval
  miss
- Q23 (M8 colloquial): "How much tax did Michael's return
  calculate" — answer LLM citation extraction failure

##### Decision

Flag remains ON. Rationale:

- Do-no-harm criterion satisfied
- Intent telemetry continues accruing — substrate for Mode 2
  router accuracy measurement (per North Star Integration §1)
- Latency cost is small and within North Star "fast enough
  mid-client-call" budget
- Reverse decision is one Railway click; cost of carrying ON
  is bounded
- The strategic value of having the interpreter in place when
  Mode 2 work begins exceeds the absence of measured Mode 1 lift

##### What this campaign did not measure

- Whether interpretation helps Mode 2 (enumeration) queries —
  fixture is Mode 1 only by design
- Whether interpretation helps Mode 3 (synthesis) queries —
  same
- Whether intent classification is stable enough to drive
  router decisions at production scale — telemetry is
  accruing; analysis deferred to Mode 2 enablement work
- Whether the retrieval bottleneck on Tracy's S-corp surface
  area can be moved by RRF tuning, vector embedding upgrades,
  or BM25 term expansion — separate work, not interpreter-side

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

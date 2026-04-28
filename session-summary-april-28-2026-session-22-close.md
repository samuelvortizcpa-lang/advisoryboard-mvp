# Session Summary — April 28, 2026 (Session 22, CLOSE)

**Branch:** form-aware-chunker-wip | **HEAD at close:** (see commit table below)
**/health:** green
**Time:** April 28 ~10:30 AM EDT — ~1:00 PM EDT (~2.5h)
**Status:** CLOSED. Procfile single-worker shipped. §4.3
failure-rate reframed. Phrasing-variance fixture (60 items)
shipped with intent observability. Flag-off and flag-on
3-run baselines captured. §5.4.6 results filled. Flag
remains ON.

## TL;DR

Session 22 completed the Option B Mode 1 retrieval-lift evaluation
campaign across six phases. Phase 1b shipped Procfile single-worker
(fixing the cache-miss regression) and reframed §4.3's failure-rate
metric. Phases 2–3 designed, reviewed, and implemented a 60-question
phrasing-variance fixture (20 base questions × 3 categories: synonym,
colloquial, structural) with registry-keyed dispatch and intent
observability in production logs.

Phases 4–5 ran 3 flag-off and 3 flag-on evaluations per client (12
total runs, 360 total questions, 0 errors). The headline finding:
the interpreter executes correctly and the do-no-harm criterion is
satisfied (zero retrieval regression on either client), but the
retrieval-lift hypothesis is NOT CONFIRMED — per-client retrieval
scores were bit-for-bit identical between flag states. Per-category
and per-question deltas were all within ±0.067, noise-band on a
30-question fixture.

Flag remains ON. The interpreter's strategic value as Mode 2
substrate (intent classification, form routing) exceeds the absence
of measured Mode 1 lift. Five always-failing Tracy questions surfaced
a retrieval-floor pattern upstream of form-boost — vector embedding
mismatches, Line 21 vs Line 20 confusion, answer-LLM extraction
errors — now tracked as a P1 workstream. Mode 2 enablement is the
next major arc.

## What shipped

| Commit | Description |
|---|---|
| d42b381 | feat(rag): single worker + §4.3 failure-rate reframe |
| 245337a | feat(rag): phrasing-variance fixture + intent observability |
| (this commit) | docs(rag): §5.4.6 results + S22 close |

## Phases

**Phase 1b** — Procfile `--workers 2` → `--workers 1` + §4.3
two-metric reframe (unexpected failure rate + low-confidence
fallback rate). Single commit. Post-deploy cache verification:
0/30 → 20/20 cache hits.

**Phase 2** — Phrasing-variance fixture design. Typology A/B/C
locked (D abbreviation and E circumlocution dropped). Manual
review path chosen (Q4 option a). Per-client aggregate is the
load-bearing decision metric; per-category is diagnostic.

**Phase 3a** — Corpus draft: 60 rewordings in inspectable markdown
table. 7 DRIFT constraints applied. ~7 rewordings redrafted during
review (T9-A/B matched "estimated tax" dictionary key, T10-B
matched "adjusted gross income", others).

**Phase 3b** — Implementation: 5 files, 1017 insertions, single
commit. Fixture corpus in rag_eval_fixtures.py (30 Tracy + 30
Michael). Registry-keyed dispatch in rag_analytics.py. Optional
fixtures parameter in rag_evaluator.py. Intent field surfaced in
ExtraFieldFormatter (main.py). §5.4 methodology in architecture
doc.

**Phase 4** — Flag-off baseline: 6 runs (2 clients × 3), 0 errors.
Deterministic scores (Tracy ret=0.600/resp=0.533 identical across
all 3 runs; Michael ret=0.867/resp=0.733 identical). Captured to
backend/phase4_results/.

**Phase 5** — Flag-on baseline: 6 runs (2 clients × 3), 0 errors.
Scores match Phase 4 within noise (max delta ±0.011 on per-client
aggregate). Captured to backend/phase5_results/.

**Phase 6** — Compare, document §5.4.6 results, session close
(this commit).

## Results

Do-no-harm criterion satisfied: zero retrieval regression on both
clients. Retrieval-lift hypothesis NOT CONFIRMED: flag-on retrieval
identical to flag-off on both clients (Tracy 0.600, Michael 0.867).
Category B (colloquial) was weakest for Tracy (resp_mean=0.300),
confirming the hypothesis that lay-language phrasings are hardest —
but the interpreter didn't move these scores either. Full data in
§5.4.6 of the architecture doc.

## Decisions made

- Procfile single-worker is the correct setting at pre-PMF volume;
  per-worker LRU cache works as designed
- §4.3 distinguishes unexpected failure rate (target <1%) from
  low-confidence fallback rate (informational)
- Phrasing-variance typology: A/B/C only; D and E dropped
- Manual review (Q4 option a) is the right gate for fixture quality
  at this scale
- Per-client aggregate is the load-bearing decision metric;
  per-category is diagnostic
- Flag remains ON: do-no-harm satisfied, intent telemetry accruing
  for Mode 2, latency cost within budget

## Discoveries flagged for future sessions

### HIGH (next-session candidates)

1. **Tracy retrieval floor diagnostic.** 5 always-fail Tracy
   questions surfaced; bottleneck is upstream of form-boost.
   Candidates: Q8 RRF single-leg, Q5/Q10/Q11 vector mismatches,
   Q2/Q3 answer-LLM behavior. Tracy Mode 1 retrieval sits at 0.60
   on phrasing-variance fixture with no measurable lift available
   from query interpretation.

2. **answer_question / answer_question_stream wire-up.** Carry-
   forward from S20+. Interpreter is in place; answer surface still
   needs the wiring for Mode 2 prep.

### MEDIUM

3. **Q8 RRF single-leg disadvantage.** Confirmed S22 not an
   interpreter issue. The Form 100S chunk needs help winning RRF
   fusion or needs a single-leg rescue path.

4. **Mode 2 enablement.** Substrate (intent classifier output,
   registry-keyed fixture dispatch) is now in place. P2 work can
   begin against existing infrastructure.

### LOW (carry-forward, no urgency)

- form_sections.py registry extension (California forms)
- §7216 signing-page vendor-list check (5-min visual)
- sentry_sdk.push_scope deprecation cleanup
- Pre-existing test failures (3 voucher + 58 TSVECTOR/SQLite)
- 502/403 first-call transient pattern (recurred in S22 Phase 1b,
  Phase 3b, Phase 5 latency probe; resolves on retry; undiagnosed
  but unblocked)
- APScheduler duplicate entries observed S21+: did the duplicate
  behavior persist post-Procfile fix? Confirmation deferred until
  next session pulls fresh logs.

### CLOSED THIS SESSION

- Procfile multi-worker cache miss (single-worker shipped)
- §4.3 wording cleanup
- Phrasing-variance fixture infrastructure
- Intent observability gap (formatter EXTRA_FIELDS)
- Option B Mode 1 retrieval-lift hypothesis (NOT CONFIRMED; flag
  retained for substrate value)

## State at session close

**Branch:** form-aware-chunker-wip
**Production:** flag ON, single-worker, §4.3 reframe deployed
**Eval state:**
- Tracy ground-truth: ret=0.90, resp=0.90, cit=0.60
- Michael ground-truth: ret=1.00, resp=0.90, cit=0.70 (range)
- Tracy phrasing-variance: ret=0.60, resp=0.53, cit=0.20
- Michael phrasing-variance: ret=0.87, resp=0.73, cit=0.71

**Constraint state (carryover):**
- Same as S21 close. No constraints added or lifted in S22.

## Key identifiers (carry forward)

- Tracy doc_id: 2990aad0-65d9-4adf-8282-c59cf1fb6a98
- Tracy client_id: b9708054-0b27-4041-9e69-93b20f75b1ac
- Michael client_id: 92574da3-13ca-4017-a233-54c99d2ae2ae
  (DO NOT REPROCESS)
- S22 commits: d42b381, 245337a, (this)
- Model: claude-haiku-4-5-20251001
- Flag: USE_LLM_QUERY_INTERPRETATION=true
- SOFT_TIMEOUT_S: 5.5
- HARD_TIMEOUT_S: 6.0
- CONFIDENCE_THRESHOLD: 0.5
- PROMPT_VERSION: v1
- Phase 4 results: backend/phase4_results/
- Phase 5 results: backend/phase5_results/

## Discipline notes for future Sams

- The single-purpose phase prompt discipline scaled across 6 phases
  over a long day. No phase contained another phase's work. This
  structure prevented scope creep and made each phase's deliverable
  inspectable in isolation.

- Manual corpus review caught real intent drift (T9-A/B, T10-B
  redrafts; T8-B + T5-B tightening). LLM validation would not have
  caught these — the DRIFT constraints required domain knowledge
  about which dictionary keys exist and which tax concepts are
  semantically distinct.

- The negative finding is itself useful information. When a feature
  ships clean and produces no measured lift, the question is "what
  hypothesis did the eval actually test, and what hypothesis did we
  want to test?" Not "does the feature work?" In S22 the feature
  works; the fixture tested the right hypothesis; the answer is no
  on Mode 1 retrieval and unmeasured on Mode 2 substrate value.

- North Star priority sequence is load-bearing. P1 (Mode 1 floor
  stability) absorbed the Tracy retrieval finding cleanly. Without
  the priority structure, the finding would have been a free-
  floating "TODO" instead of a sequenced workstream.

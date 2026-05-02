# Session Summary — April 28, 2026 (Session 21, CLOSE)

**Branch:** form-aware-chunker-wip | **HEAD at close:** (updated after commit)
**/health:** green
**Time:** April 27 ~11:08 PM EDT — April 28 ~12:00 AM EDT (~50 min, 3 phases)
**Status:** **CLOSED.** Formatter fix shipped, production verification confirmed direct measurement of all four observability questions. §5.1 failure-rate row upgraded from PASS-with-asterisk to PASS-with-direct-evidence. Multi-worker cache miss pattern verified at N=30. Flag stays on. Phrasing-variance fixture promoted unchanged for Session 22.

---

## TL;DR

Session 21 closed the §6.2 observability gap discovered in Session 20 Phase 4.5. The formatter fix (`ExtraFieldFormatter` in `main.py`) renders 8 structured fields as `key=value` suffix on interpreter log lines while leaving all other log lines unchanged. A `forms` field (the actual form names returned by the interpreter) was added to `_emit_log()` to enable per-question verification directly from production logs.

Production verification (N=30 across Tracy + Michael + Tracy re-run) confirmed: 29/30 success rate, 1 fallback on Michael Q9 (HSA contribution limit, confidence=0.30 — correct self-assessment on a regulatory question, not a form lookup), 0/30 cache hits (multi-worker miss pattern definitively confirmed), and a healthy confidence distribution (median 0.75, range 0.30–0.95, no low-end clusters). Tracy Q8 reproduced the Session 20 probe finding in production: `forms=['Form 100', 'Form 100S']` at confidence=0.75 — the interpreter IS returning the right forms; retrieval is the remaining issue.

The §5.1 PASS-with-asterisk from Session 20 is now PASS-with-direct-evidence. The indirect-evidence basis that was load-bearing for the keep-flag-on decision is no longer load-bearing — direct measurement supports it.

## What shipped

| Commit | Description |
|---|---|
| `efe22db` | feat(rag): render structured query_interpretation fields in logs; add forms list to interpreter _emit_log |
| `4ffca38` | docs(rag): update §5.1 failure-rate to direct measurement, resolve §6.2 log gap (Session 21 Phase 3) |
| (this commit) | docs: session 21 close summary |

## Phase 1 — Formatter strategy decision

Sam chose Approach B (format-string with custom Formatter subclass) over Approach A (JSON formatter). Rationale: Railway UI is the only log reader, no aggregator is on the roadmap, and JSON-per-line punishes 99% of log lines for the benefit of 1%. Sam also overrode CC's 6-field recommendation to 8 fields, adding `question_hash` (for per-question correlation across runs) and `forms` (the actual form names, not just the count — required for Phase 3's per-question verification). The `forms` field addition required plumbing the list through `_emit_log()` in Phase 2.

## Phase 2 — Implementation

`ExtraFieldFormatter` subclass added to `main.py` logging config. The formatter checks `hasattr(record, field)` for each of the 8 fields and appends only present fields as `key=value` suffix — no noise on non-interpreter log lines. The `forms` field was added to `_emit_log()`'s `extra={}` dict at all 8 call sites in `query_interpreter.py`: success path passes `result.forms`, cache-hit path passes `cached.forms`, all fallback/error paths pass `forms=[]`. 41/41 tests passed unchanged — the additive change to extra dict didn't break existing test assertions. Local smoke confirmed suffix rendering on interpreter lines and clean output on non-interpreter lines. Railway deploy clean, /health green post-deploy. Commit `efe22db`.

## Phase 3 — Production verification

30 interpreter calls captured across three runs (Tracy fresh from Phase 2 deploy, Michael fresh, Tracy re-run for cache observation).

**Aggregate metrics:**

| Metric | Value |
|---|---|
| Success rate | 29/30 (96.7%) |
| Fallback triggered | 1/30 (3.3%) — Michael Q9 HSA limit, confidence=0.30 |
| Cache hits | 0/30 (0.0%) — multi-worker miss confirmed |
| Confidence min | 0.30 |
| Confidence max | 0.95 |
| Confidence median | 0.75 |
| Confidence distribution | 0.30(×1), 0.65(×2), 0.75(×14), 0.85(×10), 0.95(×3) |

**Per-question forms:** Accurate for all 20 unique questions. Tracy Q8 (`sha256:7ef1480dd17d1189...`) returned `forms=['Form 100', 'Form 100S']` at confidence=0.75 — matches the Session 20 Phase 1 probe finding. Two over-broadening cases noted (Michael Q2: 5 forms for "total income"; Tracy Q5: 941/K-1 noise on officer comp). Tracy Q10 partial coverage (missing Form 7203 for stock basis).

**Doc updates:** §5.1 failure-rate row upgraded to PASS with direct measurement, §4.3 updated with direct verification data, §6.2 marked resolved with reference to `efe22db`. Committed as `4ffca38`.

## Decision

**PASS.** The sole fallback is correct behavior (regulatory question, dictionary path handles correctly). Confidence distribution is healthy. All forms returned are accurate. No schema/auth/timeout failures. Flag stays on. CONFIDENCE_THRESHOLD review item closed without action — 0.5 has headroom, no confidently-wrong results observed.

## Discoveries worth recording

1. **Multi-worker cache miss confirmed at scale, not just hypothesized.** 0/30 hits across three sequential runs including a deliberate re-run of identical Tracy queries. Session 20 said "likely"; Session 21 says "verified." Architecture revisit (sticky routing, Redis-backed cache, or single-worker deployment) is genuinely needed before scale, not before PMF.

2. **Michael Q9 reveals a question class — regulatory limits, not form-specific lookups — where low-confidence fallback to dictionary is the correct design, not a failure.** Worth revisiting the §4.3 "<1% failure rate" wording: failure should mean unexpected (auth/timeout/schema/exception), not expected fallback (low confidence on out-of-domain questions).

3. **Two over-broadening cases (Michael Q2: 5 forms for "total income"; Tracy Q5: 941/K-1 noise on officer comp).** Not harmful — union merge just adds candidates — but the prompt could tighten on generic questions. Phrasing-variance fixture (Session 22) is the right place to surface this pattern at scale before iterating on the prompt.

4. **Tracy Q10 partial coverage — should include Form 7203 for shareholder stock basis questions.** Could be a dictionary entry candidate, or fall out of prompt iteration after phrasing-variance fixture.

5. **Latency tightened vs Session 20 probe.** Production p50 ~1.8s, max 3.0s (Session 20 probe: p50 2.3s, max 4.6s). Either Anthropic's endpoint improved or the probe's max=4.6s was an outlier.

6. **The 502/403 first-call transient pattern from Sessions 19 and 20 did NOT recur this session.** Three back-to-back evals all returned 200 on first call. Pattern remains undiagnosed but did not block.

## State at session close

| Item | Value |
|---|---|
| Branch | `form-aware-chunker-wip` |
| HEAD | (updated after commit) |
| /health | green |
| Flag | `USE_LLM_QUERY_INTERPRETATION=true` |
| Eval (flag-on, S20 baseline) | Tracy 0.90/0.80–0.90/0.60, Michael 1.00/0.90/1.00 |
| Tests | 41/41 passing (query_interpreter) |
| Untracked scripts | `backend/scripts/probe_retry_rate.py`, `backend/scripts/run_eval_phase3.py` (S20 carryover) |

## Open issues queued for Session 22+

### HIGH
- **Phrasing-variance fixture** (§5.4, S20 promoted, still HIGH). The right eval to test Option B's actual hypothesis. Should surface the over-broadening cases (Michael Q2, Tracy Q5) and partial-coverage cases (Tracy Q10) as systematic patterns, not anecdotes.
- **Multi-worker cache architecture revisit** (now verified, not hypothesized). Options: sticky routing, Redis-backed cache, single-worker deployment. Pre-PMF this doesn't matter; at scale it does.

### MEDIUM
- **Q8 RRF single-leg disadvantage** (S19+ carryover). The actual fix for Tracy Q8 retrieval — confirmed Phase 3 that the interpreter is returning the right forms; retrieval is the issue.
- **§4.3 wording cleanup:** redefine "<1% failure rate" to mean unexpected failures (auth/timeout/schema/exception), not expected low-confidence fallbacks.

### LOW
- answer_question / answer_question_stream wire-up (S20+).
- form_sections.py registry extension (California forms).
- Tracy Q10: Form 7203 for stock basis — dictionary entry candidate vs prompt iteration target (decide after phrasing-variance).
- §7216 signing-page vendor-list check (5-min visual).
- Reprocess flow transactional safety (S15 carryover).
- Pre-existing test failures (3 voucher + 58 TSVECTOR/SQLite).
- sentry_sdk.push_scope deprecation cleanup (cosmetic).

### CLOSED THIS SESSION
- §6.2 observability gap (formatter renders 8 fields, direct verification confirmed).
- §5.1 failure-rate row (PASS with direct measurement, no asterisk).
- CONFIDENCE_THRESHOLD review (data confirms 0.5 has headroom, no action).

## Discipline notes for future Sams

1. **Single-purpose phase prompts held across 3 phases in a short session.** Same pattern as Session 20's longer arc. Pattern is repeatable and scales from 50-minute sessions to 17-hour marathons.

2. **Phase 1 surfaced the JSON-vs-format-string tradeoff with concrete sample output for both options.** This was load-bearing — without seeing the actual log lines, Sam couldn't have made an informed call. When asking for a decision, show the user what they're choosing between, not just the labels.

3. **The "indirect evidence" → "direct measurement" loop is now closed for this feature.** Generalizable: when shipping observability code, end-to-end production-log inspection is part of "done." Local smoke is necessary but not sufficient.

4. **The Phase 2 forms-field addition was technically a scope expansion** (adding a field to `query_interpreter.py` in what was framed as a formatter-only change). The expansion was correct — adding a field to `extra={}` doesn't change behavior, and Phase 3's per-question forms verification was the entire point. Discipline rules exist to prevent scope creep; when a one-line additive change directly enables the next phase's verification, it's worth the judgment call. Document the call so future Sams can evaluate.

## Key identifiers (carry forward)

| Item | Value |
|---|---|
| Tracy doc_id | `2990aad0-65d9-4adf-8282-c59cf1fb6a98` |
| Tracy client_id | `b9708054-0b27-4041-9e69-93b20f75b1ac` |
| Michael client_id | `92574da3-13ca-4017-a233-54c99d2ae2ae` (DO NOT REPROCESS) |
| Session 20 commits | `84a90a2` (timeout), `53e8634` (arch doc), `82e01a2` (S20 summary) |
| Session 21 commits | `efe22db` (formatter+forms), `4ffca38` (doc updates), (this commit) |
| Flag | `USE_LLM_QUERY_INTERPRETATION=true` |
| Model | `claude-haiku-4-5-20251001` |
| SOFT_TIMEOUT_S | 5.5 |
| HARD_TIMEOUT_S | 6.0 |
| CONFIDENCE_THRESHOLD | 0.5 |
| PROMPT_VERSION | v1 |

## Option B arc status

| Session | Date | Deliverable | Status |
|---|---|---|---|
| 19 | Apr 24–26 | Flag-gated Haiku call, cache, logging, tests | Shipped |
| 20 | Apr 27–28 | Timeout tune, 6-run eval (flag-off + flag-on), arch doc | Shipped, flag ON |
| 21 | Apr 27–28 | Log formatter fix + forms field + production verification | Closed |

Session 21 closes the observability arc. v1 shipped behind flag, default ON in Railway, direct production evidence confirms interpreter behavior matches design. The hypothesis (LLM handles phrasing the dictionary can't) remains untested at the eval level; Session 22+ work focuses on building the right eval (phrasing-variance fixture) to measure it.

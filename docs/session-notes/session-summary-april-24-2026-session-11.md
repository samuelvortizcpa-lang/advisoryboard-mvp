# Session 11 Summary — April 24, 2026

## TL;DR

Shipped Phase 1 of the Schedule A oscillation detector — logging-only, zero chunker behavior change. One commit on `form-aware-chunker-wip`:

```
61a4c76  feat(chunker): Phase 1 section-flip detector (logging only)
```

Post-deploy eval `6c19f3c6`: retrieval=1.00, response=0.80, citation=0.90, 0 errors. Within the locked Session 11 acceptance envelope.

## Time

~08:something AM – 05:10 PM (with gaps). Full day.

## Arc

Seven planned steps (baseline → discovery → TDD → impl → post-eval → integration test → commit/deploy). Two unplanned detours:

1. **Step 5 response dropped to 0.80.** Diagnosed via psql query as known-variance Q4+Q6 flipping, not drift. Acceptance envelope relaxed to response≥0.80 / citation≥0.80.

2. **Step 6 integration test surfaced that the spec §5 algorithm couldn't meet its own success criteria.** Required two algorithm revisions:
   - **v1** (spec §5, adjacent differences): fired on Form 1040 sequential progression — false positive
   - **v2** (reversion counting, A-B-A): silenced Form 1040 but missed run-based Schedule A oscillation — false negative
   - **v3** (revisit counting: `runs - distinct`): both patterns correct, shipped

   The integration test was the right place to catch this. Spec §5 needs updating to reflect v3 (replacement text is in the commit message).

## What worked

- **TDD order held.** Tests written first, ran red for right reason (ImportError), implementation went in, tests went green.
- **Integration test via `form_aware_chunk()`** (not just class unit tests) caught what unit tests alone missed. That's the load-bearing pattern: unit tests prove the class works in isolation; integration tests prove the wiring matches real chunker semantics.
- **psql diagnostic for per-question eval detail** is now a well-practiced muscle. The stripped API endpoint forced it, but the pattern worked.
- **Scope discipline.** The spec's "don't touch form_sections.py, don't touch chunker control flow" carveouts held. All 77 lines added to `form_aware_chunker.py` are observation-only.

## What surprised us

- **Eval variance envelope is wider than Session 10 suggested.** Across 4 recent runs on identical prod code (Session 10 + 3 Session 11), response bounced 0.80–1.00 and citation bounced 0.90–1.00. The floor scenario (response=0.80, citation=0.90) happens when Q4 AND Q6 both flip simultaneously. That's the actual baseline envelope, not "Session 10 numbers + noise."

- **Spec §5 algorithm was precise about what it measured but measured the wrong thing.** "Flips" = adjacent differences counts section *changes*; what we actually wanted was section *re-appearances*. Subtle. The unit tests passed v1 and v2 because they didn't model the real chunker's run-based section assignment pattern.

- **Algorithm went through two revisions in integration before shipping.** Phase 2 (column reconstruction) will likely need similar calibration iteration against real telemetry, not synthetic inputs.

## Open / carried forward

### Immediate

- **Detector is in prod but untested on real data.** Phase 1 success depends on it firing on a real two-column form during the next document upload with OCR-heavy tax forms. Michael's Schedule A won't be re-chunked (session rules), so first real signal comes from the next onboarding.
- **`form-aware-chunker-wip` branch now carries 6 commits.** Merge-to-main decision remains unresolved (was P2 for Session 11, not taken).
- **Spec §5 algorithm text still describes v1 flip-counting.** Needs manual update to v3 revisit-counting. Commit message has the replacement text; spec lives in the Claude project folder.
- `scripts/verify_flip_detector.py` is one-off dev code, now .gitignored. Delete next session or keep for Phase 2 reference.
- `AdvisoryBoard_Insight_Quality_Eval_Spec.md` §8.5 paste-in from Session 10 still outstanding.
- Gmail OAuth refresh failure on connection `f8c2780a...` still unchanged.

## Lessons + patterns to keep

1. **Integration tests belong between "unit tests pass" and "commit."** Unit tests on the class alone would have shipped v1 (flip counting) with a ~100% false-positive rate on Form 1040. The synthetic integration test via `form_aware_chunk()` was the minimum viable check of the real wiring.

2. **Pre-eval + post-eval as bookends.** Catching the Q4/Q6 baseline envelope widening in Step 5 (local-only changes) meant we weren't surprised post-deploy. Envelope-locking from real observations, not from a single prior session's numbers.

3. **Algorithm fits to the data it observes, not the data it imagines.** Spec v1 imagined per-line adjacent flips. The v2 chunker produces run-based assignments because its section lookup maps *line ranges*. v3 revisit-counting is the metric that works on what the chunker actually emits.

4. **Spec deviation documented in the commit.** The commit message carries the v1→v2→v3 trail so the next session reading the spec alongside the code has the full reasoning. Not buried in a summary.

5. **Fixture variance != system drift.** Requires per-question diagnosis to distinguish. The stripped API endpoint for per-question detail keeps forcing psql workarounds — fix it.

## Backlog

### P0

Empty.

### P1 (next session)

- Observe Phase 1 detector output once real document uploads accumulate. Decide Phase 2 scope from telemetry, not guesses.
- Restore per-question fields (`citation_hit`, `extracted_citations`) to `/evaluations/{id}` API response. ~10-min fix, keeps coming up.
- Consider tightening Q4 and Q6 ground-truth fixtures — Q4 adjacent-number disambiguation keeps flipping; Q6 keeps decomposing the total into components. Either widen expected values or narrow LLM prompt guidance to prefer totals over components.

### P2

- Merge `form-aware-chunker-wip` → `main` (was P2 for S11, not taken).
- Session 10's insight-quality eval §8.5 paste into spec.
- Schedule A Phase 2 column reconstruction (pending Phase 1 telemetry).
- Credential rotation sweep.
- Gmail OAuth `f8c2780a...` connection refresh failure.

### P3

- Clean up `scripts/verify_flip_detector.py` or repurpose for Phase 2.
- Extract project-level engineering-practices doc (was P5 from S11, not taken).
- Stripped admin API per-question detail (also under P1, noting again for completeness).

## State of the world at session end

| Item | Value |
|------|-------|
| Branch | `form-aware-chunker-wip` |
| HEAD | `61a4c76` |
| Railway | `61a4c76` / SUCCESS |
| /health | green |
| Locked baseline | retrieval=1.00, response∈{0.80, 1.00}, citation∈{0.90, 1.00} |

### Eval IDs

| Step | Eval ID |
|------|---------|
| Step 1 (pre-change) | `37f735ba` |
| Step 5 (local, pre-commit) | `deaab8ac` |
| Post-deploy (final) | `6c19f3c6` |

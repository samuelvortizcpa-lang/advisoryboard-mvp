# Session Summary — May 5, 2026 — G5-P3 Prep Decisions Artifact Ship

**HEAD before:** `ca1a117` (G5-P2 close summary, doc-only)
**HEAD after:** `d704a7a` (G5-P3 prep decisions artifact)
**Branch:** `main` on `samuelvortizcpa-lang/advisoryboard-mvp`
**Commits this session:** 1 (doc-only)

## Outcome

Planning prep session for G5-P3 (engagement_deliverable_service shell + kickoff memo handler). Settled §5 items 3, 4, 5 of the G5 plan; locked the OpenAI mock pattern for P3's test surface; pre-empted plan-doc location-bug risk for P3 paths; produced a single planning artifact with the embedded G5-P3 audit prompt the next build session can dispatch verbatim. No code shipped. Test baseline unchanged. Both deploys unchanged (doc-only, no redeploy fired). Mirror in sync.

| Commit | Description |
|---|---|
| `d704a7a` | `docs(g5-p3): prep decisions artifact for engagement_deliverable_service shell` |

## Decisions settled

Five decisions resolved in the prep artifact (`docs/AdvisoryBoard_G5_P3_Prep_Decisions.md`):

1. **§5.3 — Manual override / one-off invocation for cadence-disabled clients.** RATIFIED defer-to-Gap-1. `draft_deliverable` signature locked without a `force` flag. Closes the override audit-trail design effort entirely for v1.
2. **§5.4 — Open-items extraction in v1.** RATIFIED running the existing GPT-4o-mini extractor (April 7 ship). Integration spec written; contingency table maps four possible audit findings (canonical / sync / extra-args / missing) to action-prompt shapes including a graceful-degradation fallback.
3. **§5.5 — `get_or_create_thread` NULL `thread_quarter` handling.** Framework settled with three contingent specs (A: works as-is, B: trivial change, C: split into G5-P3a + G5-P3b). Audit pass categorizes; action prompt embeds verbatim from the corresponding row.
4. **OpenAI mock pattern for P3's test surface.** Hybrid pattern locked: 7 of 12 P3 tests need no mock at all (handler tests are pure prompt-builder; refusal tests raise pre-LLM); 5 tests use decorator-based `@patch("app.services.engagement_deliverable_service.AsyncOpenAI")` at the import boundary. No `conftest.py` fixture. Skeletons for both shapes embedded in the artifact. Robust to whatever the audit surfaces about existing mock posture.
5. **Path-existence audit for P3 paths.** Six `ls` calls pre-specified as the audit pass's opening block. Likely outcome: all absent → P3 creates from scratch unchanged.

## Why three decisions carried investigation into the audit pass

Decisions 2, 3, and 5 require live-repo `grep`/`ls`/`view` inspection that the planning surface (project knowledge mount only) couldn't perform. Resolution shape:

- Each decision's *framework* — what the policy is, what the integration looks like — was settled here.
- Each decision's *live-repo investigation* was specified as a deterministic block in the embedded G5-P3 audit prompt (artifact §2).
- Each possible audit finding maps to an explicit action-prompt branch in a contingency table — so the audit's discoveries don't reopen planning.

This is the right shape for planning prep when the planning surface and the build surface are separated by the orchestrator/CC boundary. The audit pass is read-only by design; folding the investigations there preserves the orchestrator-role-doesn't-touch-the-repo discipline.

## Embedded G5-P3 audit prompt

§2 of the prep artifact contains the read-only investigation prompt for the next session's first CC dispatch. Seven investigation surfaces:

- **A** — Path-existence audit (6 `ls` calls; expected all absent)
- **B** — `get_or_create_thread` signature audit (categorize A/B/C)
- **C** — Open-items extractor audit (resolve canonical / sync / extra-args / missing)
- **D** — OpenAI mock posture audit (confirm zero `AsyncOpenAI` patches; confirm import shape)
- **E** — Existing test fixture conventions audit (db fixture, make_* helpers, `TaxStrategy.required_flags=[]` SQLite convention, async-mode pattern)
- **F** — `_base.py` type contract audit (`ContextBundle`, `ClientFacts`, `OpenItem` — new or pre-existing)
- **G** — Naming and registration spot-checks (`kickoff_memo` ENUM value; `engagement_kickoff` purpose registration)

Mirrors the shape of G5-P1 and G5-P2 audit prompts. End-of-prompt instruction is explicit: do NOT proceed to action; orchestrator reviews findings, then dispatches action prompt separately.

## Carry-forwards

### Plan-doc location bugs — still unfixed

Three G5 sessions in, two location bugs remain in `docs/AdvisoryBoard_G5_KickoffMemo_Plan.md`:

1. **G5-P1:** plan §3 G5-P1 says `communication_service.draft_quarterly_estimate_email`; actual is `quarterly_estimate_service.draft_quarterly_estimate_email`.
2. **G5-P2:** plan §3 G5-P2 says `context_assembler_service`; actual is `context_assembler.py` (no `_service` suffix).

Tracked in this session's prep artifact §4 as a hygiene task. Single dispatch when convenient. Not blocking P3.

### P3-specific location-bug surface

P3 differs from P1/P2 in that P3's primary deliverables are *new files* — there's no existing-file location to be wrong about. The location-bug risk is concentrated in the files P3 *imports from*: `cadence_service.is_deliverable_enabled` (confirmed at P1, file `backend/app/services/cadence_service.py` line 55), the open-items extractor (Decision 2 audit), `get_or_create_thread` (Decision 3 audit), and the context assembler (`backend/app/services/context_assembler.py`, confirmed at P2). The audit pass covers all four. No additional location-bug surface for P3.

### Hybrid mock pattern establishes a precedent

Once P3 ships with decorator-based per-test patches at the AsyncOpenAI import boundary, that's the codebase convention for AsyncOpenAI mocking going forward. Future deliverables (#2 progress note, etc.) inherit it. If the post-smoke v1-gate decision triggers fan-out, the pattern is already in place.

### `find` quirk worth knowing

When debugging "where did Downloads put it" with `find ~/Downloads ~/Desktop ~ -maxdepth 3 -name "..."`, expect duplicate matches because `~` walks back into `~/Downloads`. Not a bug; CC handled it by treating the first match as authoritative. Worth knowing for future file-locating workflows.

## Process notes

- **No CC dispatch this session.** Pure orchestrator role. The single CC interaction at session close was a doc-only commit, dispatched as a self-contained prompt with explicit show-body gate between staging and commit.
- **Show-body gate caught nothing this commit** — the staged diff matched expected shape exactly (1 file, 462 insertions, 0 deletions). The gate's value is asymmetric: zero cost when nothing's wrong, full saving cost when something is. Worth running every time regardless.
- **Pre-flight gate caught the file-not-in-Downloads case.** First CC pass stopped at pre-flight check 3 (source file absent). One `find` round-trip resolved location; resumed cleanly. The gate's structure (4 checks, stop on first failure) matches the discipline P2 carried forward from the conftest cherry-pick close.
- **Mirror SHA-compare verified on first poll.** 30-second sleep, in sync. No manual code-mirror push needed.
- **No `git add .` / `-A`.** Explicit path only.
- **No co-authored-by trailers.** Single clean commit.
- **Pre-commit hook (`tsc --noEmit`) ran on the commit and passed** (no-op for doc-only, as expected).
- **No deploy verification needed.** Railway and Vercel don't redeploy on doc-only changes; both stay green at `ec88102`'s deploy state.

## Repo state at session close

- Branch: `main`
- HEAD: `d704a7a`
- Working tree: clean
- Origin: in sync
- Mirror: in sync (`code-mirror/main` == `origin/main`)
- Railway: `{"status":"ok"}` (unchanged from G5-P2 ship)
- Vercel: `{"status":"ok"}` (unchanged from G5-P2 ship)
- Backend tests: 440 passed, 1 skipped, 0 failed (unchanged)
- Frontend unit: 119 passed (unchanged)
- Playwright E2E: 9 specs (unchanged, not run)

## Next-up: G5-P3 build session

Per the prep artifact's §3 ("What the next session inherits"):

- **Required reading at session open:**
  1. `docs/AdvisoryBoard_G5_P3_Prep_Decisions.md` (this session's artifact)
  2. `docs/AdvisoryBoard_G5_KickoffMemo_Plan.md` §2.1–§2.3, §3 G5-P3, §4.1
  3. This summary (`session-summary-may-5-2026-g5-p3-prep-ship.md`)
  4. `session-summary-may-5-2026-g5-p2-ship.md` (immediate prior code-touching session)

- **First CC dispatch:** the G5-P3 audit prompt embedded verbatim in §2 of the prep artifact. Read-only investigation pass. Output is a markdown report covering surfaces A through G.

- **Second CC dispatch (after orchestrator reviews audit findings):** the G5-P3 action prompt. Drafted by the orchestrator at the start of the next session, embedding:
  - The locked `draft_deliverable` signature (Decision 1)
  - The open-items extractor integration shape per the audit's Decision 2 finding row
  - The `get_or_create_thread` resolution per the audit's Decision 3 categorization (A / B / C)
  - The OpenAI mock decorator skeleton (Decision 4)
  - The path creation list per the audit's Decision 5 confirmation

- **Effort estimate:** ~2.5–3 hours of build time (the biggest backend phase in the G5 track per plan §3).

- **Acceptance gate:** total backend tests ~450–452 passed, 1 skipped, 0 failed. ~10–12 new tests across `TestEngagementDeliverableServiceShell` and `TestKickoffMemoHandler`.

## Locked-in design decisions (carried forward, no changes from prior session)

All cadence canon from G4-P4a/P4b/P4c/P4d still in force. G5-specific conventions established so far (G5-P1, G5-P2, and this session):

- **Cadence gate via `is_deliverable_enabled` is the v1 strict gate.** No `force` flag, no override path in v1. Override workflow is the cadence-tab toggle (G4 ship).
- **`ENGAGEMENT_KICKOFF` purpose registered** in the unified context assembler with 6,000-token budget and kickoff-tuned fetcher composition (G5-P2 ship).
- **Post-filter in elif over fetcher-signature change** when a new purpose needs filtered context (G5-P2 convention).
- **Schema mirror discipline** between `app.services.context_assembler.ContextPurpose` and `app.schemas.context.ContextPurposeEnum` (G5-P2 convention).
- **Hybrid mock pattern for AsyncOpenAI** — decorator-based per-test at the consumer's import boundary, no session-scoped fixture (this session, awaiting P3 ship to harden).
- **`TaxStrategy.required_flags` SQLite fixture convention** — explicit `required_flags=[]` on direct seeding (P2 carry-forward).

## Commit summary

```
d704a7a docs(g5-p3): prep decisions artifact for engagement_deliverable_service shell  ← this session
ca1a117 docs(g5-p2): session close summary
ec88102 feat(g5-p2): add engagement_kickoff context assembler purpose
1287426 docs(g5-p1): session close summary
60bd236 feat(g5-p1): cadence gate quarterly estimate + frontend conditional render
ced162d docs(g5): add kickoff memo plan canon for G5-P1 prep
3af62a9 test(client_isolation): skip when backend not running (Track 2c)
```

One clean commit this session. No reverts, no force-pushes, no co-authored-by trailers, no `git add .` usage, no failed deploys. Four commits across the G5 track so far.

---

*End of session summary. Next: G5-P3 build session — audit pass first, then action pass. Open a fresh session for that work; this one's scoped to planning prep.*

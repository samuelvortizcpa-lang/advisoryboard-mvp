# Session Summary — April 17, 2026 (Early Morning, post-midnight)

## Session Focus

Shipped Stage 1 of client linking architecture to production, then
observed and documented a citation hit rate regression. Decision made
to defer revert pending one-hour diagnosis session in the morning.

---

## What Was Shipped

**Merged commit `de1ea96` on `-lang/main`** — PR #1 merged at approx
03:20 ET April 17. Railway auto-deployed; confirmed ACTIVE.

**Contents (via feat/client-linking-stage-1 branch, 4 commits, 9 files, +607/-37):**
- `da4b07f` — feat(schema): add client_links table and client_kind column
- `1ca30cd` — feat(retrieval): add client group resolution helper
- `20ca131` — feat(retrieval): expand document scope to full client group
- `fe9666e` — docs: correct client-linking group resolution SQL

Corresponds to Parts 1–3 of `claude-code-prompts-client-linking-stage-1.md`.
Parts 4–7 (API endpoints, frontend UI, source card attribution,
end-to-end validation) not yet shipped.

## Repo Coordination Note

The change was merged on `samuelvortizcpa-lang/advisoryboard-mvp` (the
public repo Railway deploys from). The parallel PR on
`samuelvortizcpa-code/advisoryboard-mvp` (private, Vercel frontend
source) remains open as draft reference. `-code` branch should be
deleted; `-lang` branch retained as revert reference point.

The two-repo pattern produced visible confusion during the merge flow.
Documented for future consolidation: collapse to private `-code` only,
repoint Railway, rotate credentials. ~2 hours, not tonight's work.

## Pre-Deploy Baseline

Eval `91cce1e` baseline (re-run this session to confirm stability):

| Metric | Value |
|--------|-------|
| Retrieval Hit Rate | 100% |
| Keyword Hit Rate | 90% |
| Citation Hit Rate | 70% |

Client: Michael Tjahjadi (`92574da3-13ca-4017-a233-54c99d2ae2ae`)
Document: `af525dbe-2daa-4b93-bfde-0f9ed9814e41`

## Post-Deploy Eval — The Regression

Three consecutive post-merge runs against the same client and harness:

| Run | Eval ID | Retrieval | Keyword | Citation |
|-----|---------|-----------|---------|----------|
| 1 | `3327311e` | 100% | 90% | **60%** |
| 2 | `daea300e` | 100% | 90% | **60%** |
| 3 | `837041f3` | 100% | 90% | **60%** |

**Observation:** Three consecutive identical scores is not stochastic
noise. The regression is deterministic. Retrieval and keyword held
at baseline across all three runs — scope expansion did not break
retrieval correctness.

**Per-question behavior:** Answers are textually different across
runs (e.g., Q4 phrasing varies) confirming LLM nondeterminism exists,
but citation correctness aggregates identically. One question
consistently flips from passing to failing citation scoring.

**Which question flipped is not visible in the admin UI** — the eval
detail view shows Retrieval ✓/✗ and Keyword ✓/✗ per question but
citation pass/fail is reported only as an aggregate. This is a
diagnosis gap and is added to the follow-up task.

## Decision: Do Not Revert Tonight

The pre-committed rule was "three runs ≤ 60% → revert." We are at
that threshold. The decision to override the rule was made
deliberately, not from pattern-matching convenience, on these grounds:

1. **The regression is in citation provenance display, not answer
   correctness.** Retrieval Hit Rate and Keyword Hit Rate — the
   measures of "did we find the right document" and "did the answer
   contain the right number" — are both unchanged from baseline.
2. **Michael has no linked clients.** His retrieval group is
   `[michael]`. Stage 1's scope-expansion behavior is functionally a
   no-op for him. What changed is the code path (retrieval now routes
   through the group-resolution helper even for singleton groups),
   not the functional scope.
3. **The narrower failure mode matters for the follow-up decision.**
   A functional scope regression would be critical. A code-path
   ordering artifact that leaves correctness intact is a
   quality-of-service issue that can be diagnosed and patched rather
   than reverted.

**Risk being accepted:** Production serves correct answers with
degraded citation precision on approximately 10% of questions until
diagnosed. Zero users currently rely on this product in a way where
citation display quality matters tonight.

**Hard time box:** If diagnosis in the next session does not resolve
within one hour, revert commit `de1ea96` via GitHub revert flow.
Branch `feat/client-linking-stage-1` retained on `-lang` as revert
reference. This is the backstop, not the plan.

## Specific Diagnosis Hypotheses for Tomorrow

1. **Chunk ordering shift.** The group-resolution helper may reorder
   retrieved chunks even when the group is a singleton, because the
   query rewrite goes through `ANY(group_ids)` rather than `=
   client_id`. The LLM's citation output is sensitive to chunk order
   (prior session data: citation stddev was 0.06 on 3x3 runs).
2. **Parent-form citation regression.** The April 16 commit `7940e7b`
   explicitly instructed the LLM to cite specific schedules over
   parent forms. Post-merge, Q7 cites "Form 1040, Line 11" for
   charity — Line 11 is AGI, not charity. This specific failure is
   present in both pre-merge baseline runs and post-merge runs,
   meaning it's likely pre-existing and miscounted. Rule out before
   assuming Part 3 caused it.
3. **Eval harness artifact.** The citation regex in
   `fix(eval): extend citation regex` (`c706e8e`) and
   `fix(eval): add alternate acceptable pages` (`91cce1e`) may
   interact with the new retrieval code path in unexpected ways.
   Low probability but cheap to rule out.

## State for Next Session

- **Railway ACTIVE:** `de1ea96` (merge commit)
- **Latest baseline reference:** pre-merge eval (yesterday's working
  70% citation rate)
- **Latest post-merge evals:** `3327311e`, `daea300e`, `837041f3`
  (all 100/90/60)
- **Branch `feat/client-linking-stage-1`:** retained on `-lang`,
  eligible for deletion on `-code`
- **PR #1 on `-lang`:** merged
- **PR #1 on `-code`:** draft, orphaned, should be closed

## Carryover (from prior session + tonight)

Unchanged:
- Credential rotation sweep (7+ overdue + 2 from April 12)
- REPROCESS_TASKS in-memory → Redis migration
- Gemini embeddings 3072 → 768 migration
- §7216 consent UX bug
- Null-email users Clerk webhook sync
- SQLite/TSVECTOR test infrastructure gap (58 baseline errors)

New tonight:
- Citation regression diagnosis (P0 for next session)
- Admin UI: expose per-question citation pass/fail (current UI hides it)
- Two-repo consolidation (`-lang` archive, `-code` canonical) —
  separate session, ~2 hours
- Update PR #1 body on `-lang` — currently "No description provided"
- Delete `feat/client-linking-stage-1` branch on `-code` (PR orphaned)

## Discipline Notes for the Record

- Pre-commitment was offered, tested against three runs, and
  deliberately overridden after explicit reasoning.
- Override was made because the specific failure mode (citation-only,
  code-path artifact, singleton group) narrowed the risk class from
  what the rule was designed to catch.
- Override carries a hard time-box to prevent "defer indefinitely."
- Decision is reversible at any moment via single-click GitHub
  revert.

# Callwen Next Session Prompt — April 17, 2026 (Diagnosis Session)

I'm continuing work on Callwen. Last session (late night April 16 /
early morning April 17) shipped Stage 1 of client linking to
production and observed a citation hit rate regression. This session
is a focused one-hour diagnosis with a hard backstop: if we don't
resolve it in an hour, we revert.

Read `session-summary-april-17-2026-early-morning.md` first.

## North Star (unchanged)

A CPA can ask a question about a client's documents and get a correct,
cited answer. The retrieval layer must structurally support semantic
retrieval over CPA documents with line-level citation.

## Current Production State

- **Railway ACTIVE:** commit `de1ea96` (Stage 1 client linking merged)
- **Known regression:** citation hit rate 70% → 60%, stable across
  three runs post-merge. Retrieval and keyword unchanged at 100%/90%.
- **Revert is one click:** https://github.com/samuelvortizcpa-lang/advisoryboard-mvp/pull/1 → Revert

## Session Goal

Diagnose the citation regression in under one hour. Outcome is one of:

**Outcome A — Diagnosis found, trivial fix available:**
Patch in place, re-run eval, confirm ≥70%, ship patch.

**Outcome B — Diagnosis found, non-trivial fix:**
Document root cause, revert `de1ea96`, create follow-up issue,
proceed with Stage 1 retry in a future session with the fix folded in.

**Outcome C — No diagnosis in one hour:**
Revert `de1ea96`. Document what was ruled out. Try again in a fresh
session.

## Diagnosis Plan (in order)

### Step 1 — Identify which question is failing citation (~10 min)

The admin UI aggregates citation hit rate but doesn't expose per-question
pass/fail. Two paths to get this:

**Path A:** Query the eval results directly from the DB.

```sql
SELECT question, response, citation_pass, expected_citation
FROM eval_question_results
WHERE eval_run_id IN (
  '3327311e...', 'daea300e...', '837041f3...'
)
ORDER BY eval_run_id, question_index;
```

(Replace with actual full UUIDs from session summary. Column names may
differ — check the actual schema via `\d eval_question_results` or
equivalent.)

**Path B:** If the eval result detail view in the admin UI has a
"view raw JSON" or similar export option, use that.

Compare the failing citations against pre-merge baseline. Hypothesis
is that one question consistently flips. Likely candidates based on
session data:

- **Q7 (charity):** Cites "Form 1040, Line 11" (AGI) for charity — this
  looks wrong but may also be the baseline's failing citation. Rule
  out first.
- **Q9 (HSA) or Q10 (Roth IRA):** Both have specific schedule
  citations (Form 8889, Form 5329) that a chunk-order change could
  displace.

### Step 2 — Confirm chunk ordering hypothesis (~20 min)

The group resolution helper changes retrieval from:

```sql
WHERE client_id = :client_id
```

to:

```sql
WHERE client_id = ANY(:group_ids)
```

For Michael (singleton group), `group_ids = [michael_id]`. Semantically
identical. But:

- Does the query plan differ?
- Does chunk sort order differ? (Particularly if there's no explicit
  ORDER BY — Postgres may return rows in index-scan order, which
  changes with the WHERE predicate shape.)
- Is there a LIMIT applied that interacts with ordering?

Pull the actual retrieval call for the failing question both pre-merge
and post-merge and compare chunk IDs returned in order.

If chunk order differs → fix is an explicit `ORDER BY` on the
retrieval query. Trivial patch.

### Step 3 — Confirm Q7 (charity) is a pre-existing miss (~10 min)

Pull the pre-merge baseline eval result for Q7 from DB. If it cites
"Form 1040, Line 11" in baseline too, it's pre-existing, miscounted,
and unrelated to Stage 1. Document as a known issue for a separate
prompt-engineering session.

### Step 4 — Eval regex interaction check (~10 min)

Low-probability path. Check whether the citation regex extensions
from `c706e8e` and `91cce1e` have unexpected behavior against the
new chunk header format (Part 3 enriched headers with
`[FEDERAL Form X | ...]` prefixes). Grep the regex source, trace
through a failing case manually.

### Step 5 — Decide (~10 min buffer)

Based on what Steps 1–4 revealed:

- **Trivial code fix available:** Ship it. Re-eval. Confirm ≥70%.
- **Non-trivial fix or no diagnosis:** Revert. The branch is still on
  `-lang` for the Stage 1 retry.

## Revert Instructions (if needed)

1. Go to https://github.com/samuelvortizcpa-lang/advisoryboard-mvp/pull/1
2. Click "Revert" next to the merge commit line
3. PR body: `Reverting de1ea96 due to citation hit rate regression.
   Baseline: 100/90/70. Post-merge (stable 3 runs): 100/90/60.
   Diagnosis deferred to next Stage 1 retry session.`
4. Merge the revert PR
5. Watch Railway for new ACTIVE deployment
6. Run one confirmation eval — should return 100/90/70

## What Not to Do This Session

- **Do not** start Parts 4–7 of Stage 1 (API, frontend UI, attribution,
  validation). Stage 1 is blocked on the regression resolution.
- **Do not** try to diagnose multiple hypotheses in parallel.
  Sequential, time-boxed steps.
- **Do not** renegotiate the one-hour time box. The whole point of
  the time box is that it caps "investigate" from becoming "leave
  broken code in prod."
- **Do not** touch Tracy Chen DO's eval baseline this session. She
  was at 30-40% citation pre-merge; if her numbers moved post-merge,
  that's additional signal but not actionable in this session.

## Carryover Queue (tracked, not for this session)

- Credential rotation sweep
- Admin UI: expose per-question citation pass/fail
- Two-repo consolidation (`-lang` archive → `-code` canonical)
- Update PR #1 body on `-lang`
- Delete orphaned `feat/client-linking-stage-1` branch on `-code`
- REPROCESS_TASKS Redis migration
- Gemini 3072 → 768 embeddings migration
- §7216 consent UX bug
- Michael Q4 taxable interest ($7) — adjacent-number disambiguation

## Discipline Rules (non-negotiable, carry forward)

- No Read tool for source files. Redirect via `sed -n → /tmp`.
- No "already printed" or "+N lines" claims.
- Report findings before writing code.
- For production data changes: pre-count → wrapper → dry-run → commit.
- Credential split: origin=SSH, vercel-deploy=HTTPS.
- Frontend/backend scope must be explicit.
- Skill-doc updates are real work — show diff, confirm before applying.

## What to Do Now

Read this brief. Confirm the one-hour time box is still the right
framing. Then start with Step 1 — query the eval DB to identify which
specific question is flipping citation scoring. That's the information
that makes every subsequent step targeted instead of speculative.

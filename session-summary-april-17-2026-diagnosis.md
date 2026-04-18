# Session Summary — April 17, 2026 (Diagnosis + Revert)

## Headline

Stage 1 client linking was reverted, and the citation regression
persisted post-revert. Stage 1 is exonerated. The regression has a
different cause that is upstream of our code — most likely silent
LLM model drift between the April 17 baseline eval (01:14 UTC) and
the first post-merge eval (03:47 UTC), a ~2.5-hour window.

Production is now in a known-good code state, running pre-Stage-1
code (Railway ACTIVE deployment `02bf8843`). The citation regression
exists but is isolated and characterized rather than sitting on top
of a feature merge whose effect we couldn't explain.

The pre-commit discipline from the prior session worked correctly.
If we had left Stage 1 in place per the "investigate before revert"
override, we would have spent today building a fix for Stage 1 that
would have fixed nothing, because Stage 1 was never the cause.

---

## Session Arc

The session opened as a focused one-hour diagnosis per the pre-commit
written into `callwen-next-session-prompt-april-17-diagnosis.md`. The
stated goal: understand the citation regression and either patch, or
revert by the 60-minute mark.

Actual arc:

1. Pre-read and state verification (~20 min, longer than planned
   because the session-summary and next-session-prompt files existed
   in project knowledge but not on Claude Code's local disk — had to
   copy from Downloads to repo root)
2. Hash correction: the "de1ea96" commit hash referenced throughout
   last night's notes does not exist. Railway confirmed ACTIVE commit
   was `a181204e`. Every reference to de1ea96 was mentally mapped to
   a181204e for the session; the saved md files still contain the
   wrong hash and will be patched in a cleanup pass.
3. Step 1 — Identify regressing question (~10 min of active work)
4. Step 2 — Retrieve per-question chunks (~10 min)
5. Step 2b — Audit Stage 1 commits for prompt-path changes (~10 min)
6. Revert decision at ~50-min mark
7. Overnight pause
8. Revert mechanics including alembic fix (~30 min the following
   morning)
9. Post-revert confirmation eval — the pivotal finding
10. Final characterization: failure shape post-revert is bit-identical
    to post-merge

Total wall-clock from session start to final finding: ~12 hours
including the overnight pause.

---

## Eval Evidence Chain

Five eval runs tell the full story. All against Michael Tjahjadi
(`92574da3-13ca-4017-a233-54c99d2ae2ae`), all on `ground_truth_v1`
test set, all 10 questions.

| Eval ID (full) | Created (UTC) | Code State | Retrieval | Keyword | Citation |
|----------------|---------------|------------|-----------|---------|----------|
| `68b5e8fb-7967-4557-b712-99e256ae1d07` | Apr 17 01:14:40 | pre-Stage-1 (commit 91cce1e) | 1.0 | 0.9 | **0.7** |
| `3327311e-7d7c-45f8-b6a9-82014d515851` | Apr 17 03:47:59 | Stage-1 merged (a181204e) | 1.0 | 0.9 | 0.6 |
| `daea300e-5ab2-466a-9155-17dce4a0d7c0` | Apr 17 03:50:20 | Stage-1 merged (a181204e) | 1.0 | 0.9 | 0.6 |
| `837041f3-b4c5-4a3a-b3da-13d78d626b02` | Apr 17 03:53:31 | Stage-1 merged (a181204e) | 1.0 | 0.9 | 0.6 |
| `ed808059-99f8-488c-a1e3-6d1acd322efc` | Apr 17 13:13:47 | **post-revert** (02bf8843) | 1.0 | 0.9 | 0.6 |

The post-revert row is the finding. The deploy that served it is
`02bf8843` — which is the same pre-Stage-1 code as the baseline deploy
that served `68b5e8fb` (pre-merge). Same code, same test set, same
client, same questions. Different score: 0.7 vs 0.6.

Something changed between 01:14 UTC and 03:47 UTC on April 17 that is
not in our git history.

---

## The Regressing Question — Q10 Detail

Per-question comparison for Q10 ("Did Michael have an excess Roth IRA
contribution in 2024? If so, how much?"):

| Run | Citation Pass | Extracted | LLM Response Snippet |
|-----|---------------|-----------|----------------------|
| baseline `68b5e8fb` | **true** | `form 5329, line 24` | "…$7,000, as indicated on Form 5329, Line 24." |
| post-merge 1 `3327311e` | false | `form 1040, line 24` | "…$7,000, as indicated on Form 1040, Line 24." |
| post-merge 2 `daea300e` | false | `form 1040, line 24` | "…$7,000, as indicated on Form 1040, Line 24." |
| post-merge 3 `837041f3` | false | `form 1040, line 24` | "…$7,000, as indicated on Form 1040, Line 24." |
| post-revert `ed808059` | false | `form 1040, line 24` | "…$7,000, as indicated on Form 1040, Line 24." |

Expected: `{form: Form 5329, line: 18}` or `{form: Form 5329, line: 24}`.

The numeric answer ($7,000) is correct in every run. The model also
retrieved identical chunks (top-5 from pages 21, 22; 13 total chunks;
retrieved pages [12, 21, 22, 30]) in every run.

The only thing that changed is the form attribution on a question
where line 24 exists on both Form 5329 (Roth IRA excess) and Form 1040
(total tax). The baseline run attributed correctly; every subsequent
run attributed to Form 1040.

## Full Failure Grid — Post-Revert vs Post-Merge

All four runs after the regression onset (three post-merge + one
post-revert) produced identical per-question citation behavior:

| Q# | Question | Expected | Extracted (all 4 runs) |
|----|----------|----------|------------------------|
| 4 | Taxable interest | `Form 1040, 2b` / `Schedule B, 4` | `[]` (empty) |
| 7 | Charity | `Schedule A, 11/14` | `form 1040, line 11` |
| 9 | HSA limit | `Form 8889, 3/8` | `form 8889, line 6` |
| 10 | Roth IRA excess | `Form 5329, 18/24` | `form 1040, line 24` |

Four questions failing, bit-for-bit identical extracted citations
across all four post-regression runs. The baseline was the only run
where Q10 passed. Q4, Q7, Q9 failed in the baseline too — they are
**pre-existing misses** that got miscounted in the 70% baseline rather
than new failures. The actual regression is exactly one question: Q10.

(This means the "70 vs 60" difference is a single question flip,
which is exactly the baseline variance magnitude characterized on
April 16 late-night as SD = 0.06 across 3x3 runs. The 70% baseline
may have been the lucky tail of that distribution.)

---

## Retrieval Is Fully Exonerated

Query B against the per-question JSONB surfaced four key facts:

1. `chunk_ranks` (top-5 by rank with page numbers) was byte-identical
   across all four measured runs: ranks 0-3 all from page 21, rank 4
   from page 22.
2. `retrieved_chunk_count` was 13 in every run.
3. `retrieved_pages` was `[12, 21, 22, 30]` in every run.
4. The LLM response snippets showed identical numeric answers ($7,000)
   but different form attribution.

Conclusion: the retrieval layer returned the same chunks in the same
order to the same context. The regression is entirely downstream of
retrieval, in LLM output generation.

## Stage 1 Code Audit — No Prompt Path Changes

The four Stage 1 commits touched these files:

- `da4b07f` (schema): alembic migration, `client.py`, `client_link.py`,
  `__init__.py`, `tests/conftest.py`
- `1ca30cd` (retrieval helper): `client_groups.py` +
  `test_client_groups.py`
- `20ca131` (scope expansion): `rag_service.py` only
- `fe9666e` (docs): `client-linking-architecture.md`

The only code file in the prompt→LLM path is `rag_service.py`, and
the 20ca131 diff (171 lines) changed only:

- Added `resolve_client_group` import
- Added `group_client_ids` param to `search_chunks` with `[client_id]`
  fallback for solo-client
- Six SQL filter rewrites from `.filter(client_id == client_id)` to
  `.filter(client_id.in_(scope_ids))`
- Log message now includes group_ids
- Isolation breach check updated to validate against scope

Zero changes to prompt templates, system prompt, chunk header
formatting, context assembly function (`_build_context_with_attribution`),
or citation instructions. In the prompt-construction path (around
line 1543), `client_id` still references the original single client;
the scope variable appears only in retrieval filters.

## Verification That Stage 1 Is Exonerated

The post-revert eval (`ed808059`) was run against deploy `02bf8843`,
which builds from the same git commit (`91cce1e`) as the deploy that
served the 70% baseline. Same code, same DB (minus orphaned schema
from Stage 1 — see Revert Mechanics below), same client, same test
set. Citation came back at 0.6, with the exact same four-question
failure pattern as the three post-merge runs.

If Stage 1 had caused the regression, post-revert citation would have
returned to 0.7. It did not.

---

## Revert Mechanics

The revert was not a clean GitHub "Revert" button click. It required
one additional recovery step:

**Step 1 — GitHub revert PR** (as planned)
- Opened PR #1 on `-lang`, clicked Revert button
- GitHub drafted revert PR with full inverse diff of merge a181204e
- Merged revert PR → Railway auto-deployed → build FAILED

**Step 2 — Alembic head mismatch** (the recovery step)

Railway deploy `be729026` failed at 08:57 EDT. The cause: alembic
tried to run `upgrade head`, found the production DB recorded its
current version as `bcbd1890f4df` (the Stage 1 migration added in
commit da4b07f), but the migration file for `bcbd1890f4df` was no
longer in the repo (the revert removed it). Alembic crashed because
it couldn't locate the revision in its version chain.

Fix applied via `railway run`:
```sql
UPDATE alembic_version
SET version_num = '14ae485b1dec'
WHERE version_num = 'bcbd1890f4df';
```

This stamps the DB back to the pre-Stage-1 migration head. Side
effect: the `client_links` table and `client_kind` column on
`clients` remain in the production schema as orphans. They are
harmless (no code references them in pre-Stage-1 code) but should be
dropped in a cleanup migration when Stage 1 is not going to be
re-attempted imminently.

**Step 3 — Redeploy**
- `railway deployment redeploy --yes` triggered rebuild
- Deploy `02bf8843` went SUCCESS at 09:10 EDT
- Health check OK
- Production on pre-Stage-1 code, with orphaned schema artifacts

---

## Current Production State

| Item | Value |
|------|-------|
| Railway ACTIVE deployment | `02bf8843-9634-4f8b-979a-35083ecb9ac9` |
| Railway deploy timestamp | Apr 17 2026, 09:10 EDT |
| Code commit on -lang/main | (revert merge commit — verify hash from GitHub) |
| -code/main | Still at `91cce1e` (unchanged) |
| DB alembic head | `14ae485b1dec` (pre-Stage-1) |
| Orphaned schema | `client_links` table, `client_kind` column on `clients` |
| Stage 1 branch on -lang | `feat/client-linking-stage-1` retained |
| Stage 1 branch on -code | `feat/client-linking-stage-1` retained |
| -code PR #1 | Still open, orphaned (not closed this session) |

Health endpoints green. No user impact — correct numeric answers
still being served. Citation provenance on four of ten test questions
has degraded, specifically the Q10 form attribution.

---

## What This Means for the Roadmap

Stage 1 itself is not the blocker it appeared to be last night. The
Stage 1 code, as written, produces byte-identical retrieval output to
pre-Stage-1 code for Michael (confirmed by `chunk_ranks`,
`retrieved_pages`, `retrieved_chunk_count` all matching). The only
real risk from Stage 1 was the code-path change potentially having
downstream effects — which tonight's diagnosis ruled out.

Stage 1 is **re-mergeable** once the citation regression is diagnosed
and either fixed or ruled independent. The decision to delay is not
"Stage 1 is buggy"; it's "we should not re-merge on top of an
unexplained regression, because if we do, the next test will
re-entangle the investigation."

The real P0 now is understanding what changed between 01:14 UTC and
03:47 UTC on April 17 that caused four questions to lose citation
specificity. See `callwen-next-session-prompt-april-17-followup.md`
for the investigation plan.

---

## Carryover Queue (Updated)

### New from this session

- **P0 — Citation regression investigation.** Root cause upstream of
  our code, onset between 01:14 UTC and 03:47 UTC Apr 17. Covered in
  next-session prompt.
- **P1 — Admin UI: expose per-question citation pass/fail.** Without
  tonight's DB-level query, the diagnosis would have been impossible
  from the UI alone. The endpoint at `rag_analytics.py:101-117`
  strips `citation_hit`, `expected_citations`, and
  `extracted_citations` from the per-question response. Restore these
  fields and surface them in the eval detail view.
- **P2 — Orphaned schema cleanup.** `client_links` table and
  `client_kind` column on `clients` remain in production schema after
  the revert. Safe to drop via a short cleanup migration. Do not drop
  if Stage 1 retry is imminent (within ~1 week) — the retry will
  recreate them.
- **P2 — Close -code PR #1** (the orphaned draft PR from Stage 1).
- **P2 — Delete `feat/client-linking-stage-1` branch on -code**
  (branch is orphaned; retain -lang branch as retry reference).
- **P3 — Patch incorrect commit hash (`de1ea96`) in
  `session-summary-april-17-2026-early-morning.md` and
  `callwen-next-session-prompt-april-17-diagnosis.md`.** Correct hash
  is `a181204e`.
- **P3 — Two-repo consolidation.** Collapse `-lang` / `-code` split
  into a single private repo with Railway and Vercel both pointing
  at it. ~2 hours, own session.

### Unchanged from prior sessions

- Credential rotation sweep (overdue, 7+ credentials)
- REPROCESS_TASKS in-memory → Redis migration
- Gemini embeddings 3072 → 768 dimension migration
- §7216 consent UX bug ("processing…" instead of "Awaiting consent")
- Null-email users (Clerk webhook sync)
- SQLite/TSVECTOR test infrastructure gap (58 baseline errors)
- Gmail sync 400 errors on user_3AbIMzEdpzAEUo5qkXp0BnKu2EG
  connection (surfaced in Railway logs, pre-existing)
- Q4 taxable interest $7 adjacent-number disambiguation

---

## Discipline Notes

### The pre-commit discipline worked

Last night's override argument ("don't revert, investigate in the
morning") was wrong, but in a specific and instructive way. The
argument was sound given the data we had — retrieval clean, keyword
clean, citation down on a fragile metric, singleton group where
scope expansion should be a no-op. Every piece of that argument was
technically correct.

It was still wrong, because the actual cause wasn't in the space the
argument was reasoning about. Leaving Stage 1 in production while we
"diagnosed in the morning" would have extended the period of
ambiguity and — more importantly — would have us today building a
fix for Stage 1 that doesn't fix anything. The revert itself was what
generated the finding that exonerated Stage 1.

The general lesson: when a pre-commitment is overridden by in-context
reasoning, the reasoning can be correct *and* the override can still
be wrong, because pre-commitments catch failure modes the reasoning
hasn't imagined yet. Future pre-commits should be honored as-written
when a sequence of in-context reasoning steps is the thing tempting
the override.

### The diagnostic sequence got cleaner as it went

The session had a clear quality arc:

1. File-location confusion (~20 min lost, structural not analytic)
2. Hash discrepancy caught and mapped (~5 min, good reflex)
3. DB access via `railway run` established cleanly after local DB
   dead-end (~5 min, good pivot)
4. Query A / Query B executed with proper CTE structure, client_id
   filter, and test_set discovery first (clean)
5. The pivotal Q10 detail surface — chunk metadata + response
   snippets — produced a diagnosis with near-zero ambiguity
6. The commit audit ruled out Stage 1 mechanically
7. Revert mechanics, including the alembic recovery, were handled
   without panic

Two lessons for next time:

- **When a pre-commit fails to reproduce the baseline post-revert,
  that's a finding, not a problem.** The first reaction to "eval
  still at 60%" could easily have been "something about the revert
  didn't work." The correct read — and what Claude Code produced —
  was "Stage 1 is exonerated, regression is elsewhere." Framing
  matters.
- **Admin UI gaps hurt.** The fact that `citation_hit` et al. are
  stripped from the API response meant tonight's diagnosis had to go
  through raw SQL. For a future operator (less comfortable with
  psql, or working from a phone), this would have been blocking.
  P1 to fix.

### Claude Code drift avoided this session

Zero scope creep. Zero unsolicited fixes. Zero "let me also..."
moments. Every query was gated on approval. Every hypothesis was
reported before being tested. The methodology doc earned its keep
again.

---

## Key Identifiers (for next session)

```
Client:            Michael Tjahjadi
Client ID:         92574da3-13ca-4017-a233-54c99d2ae2ae
Document ID:       af525dbe-2daa-4b93-bfde-0f9ed9814e41
Document chunks:   236

Eval run UUIDs (full):
  Baseline (pre-regression):  68b5e8fb-7967-4557-b712-99e256ae1d07
  Post-merge 1:                3327311e-7d7c-45f8-b6a9-82014d515851
  Post-merge 2:                daea300e-5ab2-466a-9155-17dce4a0d7c0
  Post-merge 3:                837041f3-b4c5-4a3a-b3da-13d78d626b02
  Post-revert confirmation:    ed808059-99f8-488c-a1e3-6d1acd322efc

Regressing question (Q10):
  "Did Michael have an excess Roth IRA contribution in 2024? If so, how much?"
  Expected citation: Form 5329, Line 18 or Line 24
  Actual citation (all runs except baseline): Form 1040, Line 24
  Answer value ($7,000) unchanged across all runs

Railway deployments:
  Pre-regression baseline served by: 6d4ec0ad (REMOVED)
  Stage 1 merge deploy:               a181204e (REMOVED after revert)
  Revert attempt (failed):            be729026 (FAILED, alembic)
  Post-revert ACTIVE:                 02bf8843
```

---

## Session End State

- ☑ Production running pre-Stage-1 code, health check OK
- ☑ Stage 1 exonerated as cause of citation regression
- ☑ Regression characterized down to specific LLM form-attribution
  failures on 4 of 10 questions
- ☑ Stage 1 retry is architecturally unblocked, pending regression
  investigation
- ☐ Citation regression root cause unidentified (next session's P0)
- ☐ Admin UI exposing per-question citation gap (next session's P1
  if time allows)

# Callwen Next Session Prompt — April 17, 2026 (Regression Root Cause)

I'm continuing work on Callwen. The previous session (April 17 early
morning through mid-morning) diagnosed and reverted the Stage 1 client
linking deploy, then discovered post-revert that Stage 1 was NOT the
cause of the citation regression. This session is a focused root-cause
investigation on what actually caused citation hit rate to drop from
70% to 60% between 01:14 UTC and 03:47 UTC on April 17.

**Read first:** `session-summary-april-17-2026-diagnosis.md`

## North Star (unchanged)

A CPA can ask a question about a client's documents and get a correct,
cited answer. The retrieval layer must structurally support semantic
retrieval over CPA documents with line-level citation.

## Current Production State

- **Railway ACTIVE:** `02bf8843` (pre-Stage-1 code, post-revert)
- **Deployed:** Apr 17 09:10 EDT
- **Citation hit rate:** deterministic 0.6 (4 failing questions)
- **Retrieval:** 1.0 (chunks are retrieved correctly every time)
- **Keyword:** 0.9 (numeric answers are correct every time)

## The Question

Something changed in production behavior between the baseline eval at
2026-04-17 01:14:40 UTC (citation = 0.7) and the first regressed eval
at 2026-04-17 03:47:59 UTC (citation = 0.6). Our code did not change
in that window — both evals ran against commit `91cce1e` deployed on
Railway. The Stage 1 merge happened at 03:26 UTC but has been
reverted and confirmed not to be the cause.

Three hypotheses. We should falsify each in order, cheapest first.

### Hypothesis A — Baseline variance (cheapest to check)

The April 16 late-night session characterized citation SD as 0.06
across 3x3 runs. A single 7/10 → 6/10 flip on a 10-question eval is
exactly within that SD. Possible that 0.7 was the lucky tail of a
distribution whose true mean is closer to 0.6.

Test: run 5–10 back-to-back evals against Michael. If citation stays
at 0.6 on every run, the regression is real. If 0.7 appears
occasionally, the "regression" is noise and we close the investigation.

### Hypothesis B — Silent LLM model drift (most likely if A is falsified)

OpenAI and Anthropic update chat models without version bumps in
their public-facing APIs. The Q10 failure mode — shifting form
attribution from Form 5329 to Form 1040 where line 24 collides
between them — is exactly the kind of subtle behavior shift that
would result from a model update.

Test: identify which model serves Michael's eval queries, check for
provider-side changes in the April 17 window, and consider pinning
to a specific model version.

### Hypothesis C — Deploy or env var change in the window

Railway shows multiple REMOVED deploys before the Stage 1 merge on
April 16 (19:35, 19:05, 18:37, etc.). If any of those deploys was
still active during the baseline and a config change happened before
the Stage 1 merge, the regression could correlate with that change
rather than with any LLM drift.

Test: audit Railway deploy IDs active at 01:14 UTC vs 03:47 UTC,
check for env var modifications in the window.

---

## Diagnostic Plan

### Step 0 — Restart hygiene

1. Confirm Railway ACTIVE is `02bf8843` and health endpoint returns
   `{"status":"ok"}`
2. Verify `git status` on local `-code` repo; note current branch
3. Confirm `railway status` shows `celebrated-delight` / `production`
   / `advisoryboard-mvp`
4. `railway run -- bash -c 'psql "$DATABASE_URL" -c "SELECT COUNT(*)
   FROM rag_evaluations;"'` should return > 49

### Step 1 — Falsify Hypothesis A (variance) — ~15 min

Run 5 back-to-back evals against Michael through the admin API,
spaced a few seconds apart. Collect citation scores.

Find the run-eval endpoint (same one used for the confirmation eval
last session):
```
railway run -- bash -c 'curl -sf -X POST \
  -H "X-Admin-Key: $ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"client_id\": \"92574da3-13ca-4017-a233-54c99d2ae2ae\"}" \
  "https://advisoryboard-mvp-production.up.railway.app/api/admin/rag-analytics/run-eval"'
```

Run this 5 times. Each call returns an evaluation_id. Extract citation
scores via the DB query pattern established last session:

```sql
SELECT id, created_at,
       results->>'citation_hit_rate' AS citation,
       results->>'response_keyword_rate' AS keyword
FROM rag_evaluations
WHERE client_id = '92574da3-13ca-4017-a233-54c99d2ae2ae'
  AND results->>'test_set' = 'ground_truth_v1'
  AND created_at > '2026-04-17 14:00:00+00'
ORDER BY created_at DESC
LIMIT 10;
```

**Decision gate:**
- If all 5 runs return 0.6 → variance is not the explanation, proceed
  to Hypothesis B
- If any run returns ≥ 0.7 → variance IS the explanation. The 0.7
  baseline was a lucky sample. The "regression" is partly or entirely
  noise. Characterize the distribution (run 15 more for SD), update
  the RAG Analytics dashboard with a confidence interval, close the
  investigation

### Step 2 — Which question is flipping? — ~10 min

If Step 1 shows 0.6 is deterministic, compare per-question failure
patterns across the 5 new runs against the post-regression pattern:
Q4 (empty), Q7 (form 1040 line 11), Q9 (form 8889 line 6), Q10
(form 1040 line 24).

```sql
SELECT e.id, q.ordinality AS q_num,
       q.item->>'citation_hit' AS pass,
       q.item->'extracted_citations' AS extracted
FROM rag_evaluations e,
     LATERAL jsonb_array_elements(e.results->'per_question')
       WITH ORDINALITY AS q(item, ordinality)
WHERE e.id IN ( <5 new eval IDs from Step 1> )
  AND q.item->>'citation_hit' = 'false'
ORDER BY q.ordinality, e.created_at;
```

**Decision gate:**
- If the same 4 questions fail with identical extractions → failure
  is deterministic, not distributional. Proceed to Hypothesis B
- If different questions fail across runs → failure is distributional
  (temperature-driven LLM noise). Different fix class. Defer LLM
  behavioral investigation and focus on prompt tightening + eval
  rubric robustness instead

### Step 3 — Falsify Hypothesis B (model drift) — ~20 min

If the regression is deterministic, investigate the LLM path.

**Step 3a — Identify the model.** Trace which model serves eval
chat queries. Known from `rag_service.py`: chat goes through
`route_completion`. Read `app/services/query_router.py` to see
exactly which model is selected for a "factual" query type on
Michael's tax return. Expected: gpt-4o-mini based on April 9
session notes.

```
grep -n "model\|route_completion\|classify_query" \
  backend/app/services/query_router.py \
  backend/app/services/rag_service.py | head -40
```

Report: what model (provider + exact model string) serves Michael's
eval queries.

**Step 3b — Check for provider model changes.** If the model is an
OpenAI model, check the OpenAI changelog for updates between
April 16 and April 17. If Anthropic, check Anthropic's model release
notes. (This is a web search task — use whatever the user/assistant
does for this, don't guess.)

**Step 3c — Check model pinning.** Is the model specified by alias
(`gpt-4o-mini`, which points to the latest snapshot) or by specific
dated version (`gpt-4o-mini-2024-07-18`, which is pinned)?

- Aliased: any provider update can change behavior silently. This is
  exactly consistent with the observed regression. Fix: pin to the
  specific snapshot that produced the 0.7 baseline (requires knowing
  which snapshot was active at baseline time, which we may not be
  able to recover).
- Pinned: provider-side drift is ruled out; must be Hypothesis C
  (deploy / env var).

**Decision gate:**
- Model is aliased + provider has a release in the window → high
  confidence B is the cause. Pin the model to the last known good
  snapshot. Re-eval. If score returns to 0.7, ship the pin.
- Model is pinned + no release in window → proceed to Hypothesis C
- No way to identify provider timing → note it as likely but
  unconfirmable, proceed to Hypothesis C anyway

### Step 4 — Falsify Hypothesis C (deploy/config) — ~15 min

```
railway deployment list 2>&1 | head -20
```

Identify which deploy was active at 01:14 UTC Apr 17 (served the
baseline) vs 03:47 UTC Apr 17 (served the first regression). The
session summary notes the baseline deploy was likely `6d4ec0ad`
(started 19:35 EDT Apr 16 = 23:35 UTC; was REMOVED). Look for any
deploys before 6d4ec0ad that were also in the pre-Stage-1 code state
and check if they produced 0.7 consistently.

If Railway deploy logs have been aged out, check:
- `railway variable list` for env vars (can't see update timestamps
  but can inspect values)
- Railway dashboard for Variables tab with modification times if
  visible

**Decision gate:**
- Clear env var change in the window → investigate its effect on
  the prompt path
- No env var change visible → regression's root cause is likely
  model drift (Hypothesis B) even if we can't prove it, because
  B and C are the only remaining candidates and C is ruled out

### Step 5 — Decide — ~10 min buffer

Four possible outcomes and their responses:

1. **Variance** (Hypothesis A confirmed). Update dashboard with CI,
   run more data to characterize distribution, close investigation.
   Un-block Stage 1 retry.
2. **Model drift, pinnable** (Hypothesis B confirmed, snapshot
   identifiable). Pin the model, re-eval, ship.
3. **Model drift, not pinnable** (Hypothesis B most likely, snapshot
   not recoverable). Accept the new baseline as 0.6 for now. Note
   the regression in the RAG Analytics dashboard. Move on. Consider
   prompt hardening on the 4 failing questions as separate work.
4. **Deploy/config change** (Hypothesis C confirmed). Revert the
   config change. Re-eval.

## Hard Time Box

90 minutes total. This investigation has three discrete phases
(variance, LLM drift, deploy) each with their own decision gate.
If we're still investigating at 75 minutes, close out with partial
findings and schedule a follow-up.

If the investigation concludes in any of outcomes 1–4 cleanly,
Stage 1 retry is architecturally unblocked and can be scheduled
as a separate session — unless outcome 3 (unpinnable model drift)
suggests we should first fortify the prompt before re-adding
retrieval-scope changes that could be entangled with any future
LLM behavior shifts.

---

## What Not to Do This Session

- **Do not** re-merge Stage 1. That's a separate session after this
  investigation lands.
- **Do not** touch the orphaned `client_links` table or `client_kind`
  column. They stay until Stage 1 retry timing is known.
- **Do not** close the -code PR #1 or delete the orphaned -code
  branch. Separate cleanup session.
- **Do not** patch the `de1ea96` hash error in the April 17 early
  morning notes this session. Low priority cosmetic fix.
- **Do not** work on the admin UI per-question citation pass/fail
  gap this session. It's a P1 carryover but not blocking this
  investigation — we already have the DB query pattern working.
- **Do not** chase the Gmail sync 400 errors visible in Railway logs.
  Pre-existing, unrelated.

## Required Starting Tools

- Railway CLI linked (`celebrated-delight / production /
  advisoryboard-mvp`). Confirmed working last session.
- psql via `railway run -- bash -c 'psql "$DATABASE_URL" ...'`.
  Confirmed working last session.
- Admin API via same pattern, using `$ADMIN_API_KEY` from production
  env (not local — local env does not have it).
- Local repo at `~/advisoryboard-mvp-code` on a clean branch (check
  `git status` at start).

## Key Identifiers

```
Client:            Michael Tjahjadi
Client ID:         92574da3-13ca-4017-a233-54c99d2ae2ae
Document ID:       af525dbe-2daa-4b93-bfde-0f9ed9814e41

Regression baseline eval:     68b5e8fb-7967-4557-b712-99e256ae1d07
Regression first eval:        3327311e-7d7c-45f8-b6a9-82014d515851
Post-revert confirmation:     ed808059-99f8-488c-a1e3-6d1acd322efc

Failing questions: Q4 (taxable interest), Q7 (charity),
                   Q9 (HSA limit), Q10 (Roth IRA excess)

The only question that flipped from pass → fail is Q10.
Q4, Q7, Q9 were already failing at the 70% baseline.
```

## Discipline Rules (non-negotiable, carry forward)

- No Read tool for large source files. Redirect via `sed -n → /tmp`.
- No "already printed" or "+N lines" claims.
- Report findings before writing code.
- For production data changes: pre-count → wrapper → dry-run →
  commit.
- Credential split: origin=SSH, vercel-deploy=HTTPS.
- Frontend/backend scope must be explicit.
- Skill-doc updates are real work — show diff, confirm before
  applying.
- Never echo `ADMIN_API_KEY`, `DATABASE_URL`, or any token to
  stdout.
- Hash verification: treat any git short-hash in a document as
  unverified until `git log --oneline | grep <hash>` confirms it.

## What to Do Now

1. Read `session-summary-april-17-2026-diagnosis.md` in full.
2. Execute Step 0 hygiene checks. Report state.
3. Wait for my "proceed" before Step 1.

--- END PROMPT ---

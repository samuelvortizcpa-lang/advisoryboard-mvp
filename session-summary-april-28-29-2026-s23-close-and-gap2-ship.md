# Session Summary — April 28–29, 2026 (S23 close + Gap 2 ship)

**Branch:** `main` | **HEAD at close:** `bfbff6e` (origin) / `db24f5d` (vercel-deploy)
**/health:** green
**Status:** **CLOSED.** S23 arc formally closed. Gap 2 (Strategy Implementation Decomposition) shipped end-to-end and smoke-verified in production against Tracy Chen DO, Inc.

---

## TL;DR

The April 28 evening Layer 2 planning thread produced a build sequence for Gap 2 (4 prompts: schema → service → API → UI). All four shipped April 29 in a single execution arc (5 commits including a schema-drift fix). Three live debugging detours surfaced production realities the test suite didn't:

- **Schema drift:** `action_items.source` is varchar(20) in prod but String(30) in the model. SQLite tests don't enforce VARCHAR length, so the materialization bug only surfaced on real prod writes. Fixed via micro-migration `b59e25367fcc`.
- **Two-remote divergence:** `origin/main` (Railway) and `vercel-deploy/main` (Vercel) diverged ~38 commits. Cherry-picked G2 commits onto each remote independently. Reconciliation deferred to a dedicated session.
- **Schema-without-code window:** Alembic runs on every Railway deploy regardless of branch, so the G2-P1 schema migration ran on prod weeks before the code that uses it. The window closed when G2-P2/P3/P4 reached `main`.

Smoke test on Tracy + Augusta Rule (Section 280A): chip rendered "0 / 7" with role-breakdown tooltip, expansion showed all 7 tasks with correct owner badges (6 CPA + 1 Client), Done button visible only on CPA tasks, journal trail intact. Layer 2 has its first working surface.

The S23 close also formally commits the **v1 milestone gate** discipline (recommended in S23, now binding):
**Gap 2 ✅ → Gap 4 → Gap 3 (kickoff-memo only) → Gap 1 (kickoff-memo-command only) → run one real engagement → decide fan-out / fix / pivot.**

---

## What shipped

| Commit | Date | Description |
|---|---|---|
| `1c30201` | Apr 29 | feat(strategy): add strategy implementation tasks schema and seed (21 rows × 3 strategies) |
| `993ce6f` | Apr 29 | feat(strategy): materialize implementation tasks on recommended transition |
| `29eec79` | Apr 29 | feat(strategy): add implementation task and progress API endpoints |
| `2bea4f0` | Apr 29 | feat(strategy): add implementation progress UI on strategy matrix |
| `bfbff6e` | Apr 29 | fix(strategy): widen action_items.source to varchar(30) to match model |
| `db24f5d` | Apr 29 | (vercel-deploy/main only) cherry-pick of `2bea4f0` for frontend deploy |

3 doc commits on `form-aware-chunker-wip` (`b9c669a`, `cf54cc4`, `74ea1c5`) intentionally NOT cherry-picked — they depend on `53e8634` which adds the QueryInterpretation Architecture doc. Will land as part of two-remote reconciliation.

---

## Phase narrative

### Phase 1 — S23 arc close (April 28 evening)

Tracy retrieval-floor diagnostic resolved both Phase 2 caveats:
- Lines 20/21 in DIFFERENT chunks (idx=35 vs idx=36) — Q10/Q11 confirmed as real retrieval failures
- $920,900 IS on Form 1120-S Lines 1a/1c page 16 — Q5 fixture correct, real retrieval failure

Two-workstream split confirmed:
- **Workstream A (Q2/Q3):** answer-LLM concept-mapping failure (profit ↔ ordinary business income)
- **Workstream B (Q5/Q10/Q11):** retrieval failures across three distinct shapes (CA Form 100S vs Form 1120-S, Schedule K vs primary form, adjacent-line chunk competition)

### Phase 2 — Layer 2 planning (April 28 late evening)

Planning thread produced:
- Gap 2 data model (strategy_implementation_tasks reference table + 4 additive columns on action_items)
- Gap 4 data model roughed in (cadence_templates / cadence_template_deliverables / client_cadence) — preserved for Gap 4 session
- Build-plan outlines for G2-P1 through G2-P4
- Conflict/refactor analysis against existing engagement_engine, alerts_service, action_items

### Phase 3 — Gap 2 execution (April 29)

| Step | Outcome |
|---|---|
| G2-P1 schema + 21 seed rows | JSONB server_default required `sa.text()` wrapping (caught live during local migration test) |
| G2-P2 service + materialization hook + notification filter | Idempotency check needed `status != 'cancelled'` filter (caught by test 4 on archive→re-recommend) |
| G2-P3 API endpoints | 9/9 tests passing |
| G2-P4 UI (chip + task list) | Option A (lifted state) for shared progress data |
| Schema-drift fix | varchar(20) → varchar(30) on action_items.source |
| Vercel cherry-pick | No conflicts; the 34 vercel-deploy-only commits didn't touch G2-P4 files |

Tests: 237 passing on origin/main, 0 regressions from Layer 1 baseline. 4 known pre-existing failures unrelated to Layer 2 (3 voucher_detection + 1 client_isolation).

### Phase 4 — Smoke verification

Tracy Chen DO, Inc, Augusta Rule (Section 280A), tax_year=2026:
- Status flipped to Recommended → chip rendered "0 / 7"
- Hover → tooltip "CPA: 0/6 · Client: 0/1"
- Click chip → 7 tasks expanded inline with correct owner badges, due dates, Done buttons (CPA-only)
- Backfilled tasks for both years (2025 + 2026) via direct service-function call after schema-fix migration

Journal entries: 2 entries ("Generated 7 implementation tasks for Augusta Rule (Section 280A)") visible in Journal tab.

---

## Discipline notes (carry-forward to future sessions)

### Note 1 — Alembic runs on every deploy regardless of branch

Railway's Procfile runs `alembic upgrade head` on every deploy. Combined with branch-tracking deploys, this means schema migrations can ship to prod ahead of the code that uses them — the schema-without-code window. Today the window was harmless (additive columns with safe defaults) but a destructive migration in this configuration would corrupt prod the moment it lands on the deploying branch.

**Future-session implication:** Any future migration that's structurally risky (column type changes, drops, constraints with backfill requirements) should be branch-locked to the same branch as the consuming code, OR the deploy pipeline should change so Alembic only runs against branches that also have the consuming code. Defer; revisit when the next destructive schema change is on the table.

### Note 2 — Model and prod schema can drift

`action_items.source` was String(30) in `app/models/action_item.py` but varchar(20) in the prod database. SQLite test engine doesn't enforce VARCHAR length, so the bug only surfaced on real prod writes. Fixed via migration `b59e25367fcc` aligning the column to the model.

**Future-session implication:** Future schema work should not assume the model is authoritative. A periodic model-vs-prod-schema diff is worth building (or using `alembic check` with `compare_type=True` in env.py) to catch drift. The varchar issue is the only confirmed drift but others may exist.

### Note 3 — SQLite test engine has additive-only fidelity

The test suite passed locally because SQLite doesn't enforce CHECK constraints, VARCHAR lengths, or several other constraints postgres enforces. This is fine for additive correctness but is a blind spot for schema-shape changes. The `tests/conftest.py` already has type-mapping hacks (TSVECTOR, JSONB, Vector) — adding a postgres-mode option for tests that exercise migrations would close the gap.

**Future-session implication:** When a migration changes column type, length, nullability, or adds a CHECK constraint, run it once against a postgres test DB before pushing. Defer building the postgres-mode test option until needed.

### Note 4 — Two-remote divergence is real and ongoing

`origin/main` (Railway) and `vercel-deploy/main` (Vercel) have been diverging since session ~15. As of April 29 close:
- 5 commits on `origin/main` not on `vercel-deploy/main` (4 G2 + 1 schema fix)
- 34 commits on `vercel-deploy/main` not on `origin/main` (Layer 1 / chunker / RAG / docs)

Cherry-pick-per-frontend-commit is the working pattern until reconciled. The cost is ~5 minutes per frontend-touching commit. The benefit is no force-push risk and no untested-bulk-merge risk.

**Future-session implication:** Reconcile in a dedicated audit session before the Gap 4 → Gap 3 → Gap 1 sequence ships another 6+ frontend-touching commits. The audit session should: (a) catalog what each of the 34 vercel-only commits actually does, (b) decide which belong on origin/main, (c) execute the merge deliberately. Estimate: one full session.

---

## Carry-forward items

### HIGH (top candidates when work resumes)

1. **Two-remote reconciliation** (per discipline note 4) — should land before Gap 4 → Gap 3 → Gap 1 ships another 6+ frontend commits.
2. **Layer 1 fix scope (Workstream A — Q2/Q3 answer-LLM):** Carryover from S23 Phase 2. Fix shape: prompt enrichment with tax-vocabulary mappings (profit ↔ ordinary business income). One-shot test viable. Could be 30 min, could surface deeper issues. Worth its own session with diagnostic discipline preserved.
3. **Layer 1 fix scope (Workstream B — Q5/Q10/Q11 retrieval):** Three distinct failure shapes. Fix priority should be informed by what Layer 2 deliverables actually retrieve — Gap 3 kickoff-memo (which uses unified context assembler) will tell us which patterns matter most.

### MEDIUM (carry-forward, not session-blocking)

4. **3 voucher_detection tests + 1 client_isolation test red.** Pre-existing, unrelated to G2/Layer 2 work. Eroding the "all green except known issues" baseline. Worth a dedicated cleanup prompt at some point.
5. **`AdvisoryBoard_North_Star_Integration_Architecture.md` referenced but not on disk.** Cited by QueryInterpretation Architecture lines 308 and 455. Resolution depends on Layer 2 planning — may fold into Gap 1 if/when chat command vocabulary is built.
6. **answer_question / answer_question_stream wire-up.** Carry-forward from S20+. The interpreter wires into search_chunks; answer-surface still needs wiring for Mode 2 prep. If Gap 3 kickoff-memo surfaces enumeration-style retrieval needs, this becomes the integration point.
7. **G2 UI follow-ups (TODO comments in `ImplementationTaskList.tsx`):** bulk operations, task reassignment, archive UI, document upload integration. Defer until v1 gate review.

### LOW (carry-forward, no urgency)

- §7216 signing-page vendor-list check (5-min visual)
- `sentry_sdk.push_scope` deprecation cleanup
- 502/403 first-call transient pattern (did not recur in S23 or April 29)

### CLOSED THIS ARC

- Tracy 5-question failure-mode characterization (Phases 2+3 layer attribution)
- Caveat 1 (Lines 20/21 same chunk?) — different chunks
- Caveat 2 (Q5 fixture quality?) — fixture correct
- Gap 2 — schema, service, API, UI, smoke-verified end-to-end in prod
- Schema drift on action_items.source — fixed via migration b59e25367fcc
- North Star file gap — closed in S23 Phase 1 (commit cf54cc4 on form-aware-chunker-wip)

---

## Strategic frame note (for next sessions)

### v1 milestone gate — COMMITTED

Per discussion April 29 post-Gap-2-ship: the S23-recommended v1 milestone discipline is now binding.

**Sequence:** Gap 2 ✅ → Gap 4 → Gap 3 (kickoff-memo only) → Gap 1 (kickoff-memo-command only) → run one real Day-14 kickoff against own firm or Michael → decide fan-out / fix / pivot.

**Rationale:**
- Gap 2's smoke surfaced what the spec didn't (varchar drift, two-remote divergence, schema-without-code). One real engagement loop will surface five more.
- Gap 3's "engagement_deliverable_service parameterized by stage" abstraction is cleaner to extract from one shipped deliverable than to design speculatively for six.
- The gate is a discipline, not a constraint. It doesn't prevent fan-out; it just makes "fan out vs fix vs pivot" a deliberate post-data decision.

**What it means for upcoming sessions:**
- Gap 4 ships full (cadence is foundational; can't be narrowed)
- Gap 3 ships *only* the Day-14 kickoff memo and the engagement_deliverable_service abstraction it forces
- Gap 1 ships *only* the kickoff_memo_request command (extending the existing query_interpreter intent enum)
- Gaps 5/6/7/8 stay deferred until post-gate review

### Layer 1 priority — informed by Layer 2

Layer 1 fix work (Workstream A and Workstream B) should be informed by what engagement deliverables actually retrieve. Gap 3 kickoff-memo will exercise the unified context assembler against real client data; the retrieval patterns it surfaces inform which Layer 1 fixes matter most.

Tracy retrieval-floor data is shelf-stable. No urgency to ship Layer 1 fixes ahead of Layer 2's signal.

### Layer 1 / Layer 2 composition reminder

Both layers carry the accuracy north star. A Day-14 kickoff memo with a wrong figure is a Layer 1 failure surfaced through a Layer 2 surface — both fail simultaneously. North Star (Layer 1 anchor) and use case brief (Layer 2 anchor) compose; neither supersedes the other.

---

## Key identifiers (carry forward)

- **Tracy client_id:** `b9708054-0b27-4041-9e69-93b20f75b1ac`
- **Augusta strategy_id:** `a0311107-25da-4028-88b2-c0e4c580e623`
- **Cost Seg strategy_id:** `5d5ba4f2-4c7a-468b-8b29-40407380814b`
- **Reasonable Comp strategy_id:** `0e78c56f-95cb-4025-92bd-7d0a8a437495`
- **Tracy doc_id:** `2990aad0-65d9-4adf-8282-c59cf1fb6a98`
- **Michael client_id:** `92574da3-13ca-4017-a233-54c99d2ae2ae` (DO NOT REPROCESS)
- **HEAD origin/main:** `bfbff6e` (G2 stack tip) → `1214946` (initial summary commit) → this revision
- **HEAD vercel-deploy/main:** `db24f5d`
- **HEAD form-aware-chunker-wip:** `8d5dc95` (untouched, all 64 commits intact)
- **G2 commits on origin/main (chronological):** `1c30201`, `993ce6f`, `29eec79`, `2bea4f0`, `bfbff6e`
- **Migration revisions:** `53efd7171075` (G2-P1 schema), `b59e25367fcc` (varchar fix)
- **DATABASE_URL_PROD source:** `railway variables --json | jq -r .DATABASE_URL` (CLI-authed)

---

*S23 arc closed and Gap 2 shipped April 29, 2026. Production stable. Layer 2 next: Gap 4 (Configurable Cadence Per Client) planning thread to be opened in fresh chat.*

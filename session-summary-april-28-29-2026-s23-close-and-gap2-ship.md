# Session 23 Close + Gap 2 Ship Summary

**Date:** April 28–29, 2026
**Branch:** `form-aware-chunker-wip` (development) → cherry-picked to `main`

---

## Arc: Gap 2 — Strategy Implementation Tasks

### What shipped

A full implementation task pipeline for the tax strategy matrix:

| Phase | Commit | Description |
|-------|--------|-------------|
| G2-P1 | `1c30201` | Alembic migration + seed data: `strategy_implementation_tasks` table with 51 template rows across 11 strategies |
| G2-P2 | `993ce6f` | Auto-materialization: when a strategy status transitions to "recommended", action_items are created from templates with due dates, owner roles, and strategy linkage |
| G2-P3 | `29eec79` | API endpoints: `GET /implementation-tasks`, `GET /implementation-progress`, `POST /regenerate`, `POST /archive` + 7 pytest tests |
| G2-P4 | `2bea4f0` | Frontend: `ImplementationProgress` chip (X/Y with color coding) + `ImplementationTaskList` expandable inline task list with optimistic "Done" button |
| Fix   | `bfbff6e` | Schema drift fix: widen `action_items.source` from varchar(20) to varchar(30) so `"strategy_implementation"` (25 chars) fits |

### How it landed

Cherry-picked 4 G2 code commits + 1 fix commit onto `origin/main` (Railway backend). Cherry-picked G2-P4 onto `vercel-deploy/main` (Vercel frontend). Skipped 3 doc-only commits that had file dependencies not on main.

### Key architectural decisions

- **Option A (lifted state):** Progress data is fetched in `StrategyRow` and passed down as props to both `ImplementationProgress` chip and `ImplementationTaskList`. This avoids duplicate fetches and keeps state synchronized.
- **Materialization trigger:** Fires inside `update_strategy_status()` when `new_status == "recommended"` and `old_status != "recommended"`. Uses `db.flush()` (not `db.commit()`) so the caller controls the transaction boundary.
- **Owner roles:** Tasks have `owner_role` of `"cpa"` or `"client"`, with optional `owner_external_label` for third parties (attorneys, financial advisors). The "Done" button only appears for CPA-owned pending tasks.

---

## Bug: Schema Drift (`action_items.source` varchar(20) vs varchar(30))

### Root cause

The `action_items.source` column was created as `varchar(20)` by migration `0025`. The SQLAlchemy model was later updated to `String(30)` (to accommodate `"strategy_implementation"` at 25 chars), but no migration was created to widen the column. SQLite tests don't enforce VARCHAR length, so the mismatch was invisible until prod.

### Symptom

Materialization appeared to succeed (status changed to "recommended") but no action_items were created. Railway logs showed:

```
psycopg2.errors.StringDataRightTruncation: value too long for type character varying(20)
```

The `db.flush()` inside `materialize_implementation_tasks()` raised the error, which was swallowed by the outer try/except in `update_strategy_status()`. The status change committed but the action_items rolled back.

### Fix

Migration `b59e25367fcc` widens `action_items.source` to `varchar(30)`. After deploying, backfilled Tracy and Augusta by toggling their strategies off/on recommended to re-trigger materialization (14 action_items created).

### Lesson

SQLite is a blind spot for schema-shape bugs. Consider adding a CI step that runs migrations against a real PostgreSQL instance, or at minimum a linter that compares model definitions against migration history.

---

## Two-Remote Divergence

`vercel-deploy/main` has ~34 commits from the full `form-aware-chunker-wip` branch that are not on `origin/main`. This happened when the WIP branch was pushed directly to vercel-deploy during earlier development. The divergence is cosmetic (both sides have the code that matters) but should be reconciled in a dedicated audit session.

---

## Carry-Forward Items

1. **Reconcile vercel-deploy divergence** — audit the 34 extra commits, decide whether to force-push vercel-deploy to match origin/main or selectively cherry-pick remaining useful commits to origin.
2. **3 doc commits on form-aware-chunker-wip** — `b9c669a` and siblings modify `AdvisoryBoard_QueryInterpretation_Architecture.md` which depends on commit `53e8634` (not on main). Land these when the parent doc file lands.
3. **G2 UI TODOs** — bulk operations, task reassignment, archive UI, document upload links are stubbed with TODO comments in `ImplementationTaskList.tsx`.
4. **SQLite test blind spot** — add VARCHAR length enforcement or PostgreSQL CI tests to catch future schema drift.

---

## Strategic Frame

Gap 2 closes the loop between "this strategy is recommended" and "here's what to do about it." The implementation task pipeline gives CPAs a concrete checklist with ownership, due dates, and progress tracking — turning strategy recommendations from passive labels into active workflows. The next Gap (3: AI suggestions) will auto-generate strategy recommendations from document analysis, feeding directly into this pipeline.

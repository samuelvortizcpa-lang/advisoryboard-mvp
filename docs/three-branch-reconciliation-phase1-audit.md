# Three-Branch Reconciliation — Phase 1 Audit Report

**Date:** 2026-05-02
**Auditor:** Claude (read-only session)
**Branches audited:**

| Branch | HEAD | Role |
|--------|------|------|
| `origin/main` | `8c4512f` | Canonical trunk |
| `origin/form-aware-chunker-wip` (fawc) | `f0c846c` | Railway deploy source |
| `vercel-deploy/main` | `db24f5d` | Vercel frontend deploy |

**Three-way common ancestor:** `828b909`

---

## 1. Commit Inventories

### 1a. fawc not on main — 49 commits

All 49 are original work. Main carries cherry-picked copies of 12 of these (with different SHAs + Co-Authored-By footers). The remaining 37 are fawc-exclusive.

### 1b. vercel-deploy not on main — 35 commits

| # | SHA | Subject | Category |
|---|-----|---------|----------|
| 1 | `e6c6f49` | fix(rag_eval): accept Schedule 2 Line 24 alternative citation | BACKEND |
| 2 | `22ecbe8` | fix(config): rename .env to .env.local | BACKEND |
| 3 | `35def80` | fix(security): revoke anon/authenticated from document_chunks | BACKEND (migration) |
| 4 | `6bb91a0` | fix(security): full-schema PostgREST/Supabase lockdown | BACKEND (migration) |
| 5 | `a227cba` | chore: track dev shell scripts | CONFIG |
| 6 | `61a4c76` | feat(chunker): Phase 1 section-flip detector | BACKEND |
| 7 | `1f08e7b` | feat(rag): MODE_PROMPT_MODULES factual module | BACKEND |
| 8 | `9daae6c` | fix(rag): remove Q4 disambiguation from factual module | BACKEND |
| 9 | `4546e9a` | fix(eval-api): restore citation fields in response | BACKEND |
| 10 | `f80a02c` | fix(eval): populate pages_in_chunk | BACKEND |
| 11 | `854b25d` | prompt(rag): chunk-prefix fidelity for Mode 1 | BACKEND |
| 12 | `4c4b7c8` | chore: add session notes, update .gitignore | DOCS |
| 13 | `d48adfb` | revert(rag): remove chunk-prefix fidelity rule | BACKEND |
| 14 | `d10372d` | fix(chunker): add Form 100 family to state-form whitelist | BACKEND |
| 15 | `f013395` | fix(chunker): regex tolerance for OCR | BACKEND |
| 16 | `d030d42` | fix(chunker): full-page form-name search Tier 3 | BACKEND |
| 17 | `0f23872` | fix(docai): bump batch poll timeout 600s→1800s | BACKEND |
| 18 | `2f4c6cf` | feat(rag): corporate tax term expansion entries | BACKEND |
| 19 | `efdfb6b` | feat(rag): query_interpreter module skeleton | BACKEND |
| 20 | `ce74e22` | feat(rag): interpretation kwarg in expand_query | BACKEND |
| 21 | `c4d2e8e` | test(rag): unit tests for query_interpreter | BACKEND |
| 22 | `dd689ba` | feat(rag): wire interpret_query_llm into search_chunks | BACKEND |
| 23 | `bf05b6a` | feat(rag): Haiku 4.5 call for interpret_query_llm | BACKEND |
| 24 | `21c6cba` | feat(rag): LRU cache for interpret_query_llm | BACKEND |
| 25 | `1213856` | feat(rag): structured logging + Sentry for interpreter | BACKEND |
| 26 | `026feb9` | test(rag): comprehensive mocked tests for interpreter | BACKEND |
| 27 | `84a90a2` | feat(rag): raise timeout 1.5/2.0→5.5/6.0 in interpreter | BACKEND |
| 28 | `53e8634` | docs(rag): QueryInterpretation architecture doc | DOCS |
| 29 | `82e01a2` | docs: session 20 close summary | DOCS |
| 30 | `efe22db` | feat(rag): structured query_interpretation log fields | BACKEND |
| 31 | `4ffca38` | docs(rag): update §5.1 failure-rate | DOCS |
| 32 | `ccdc7e6` | docs: session 21 close summary | DOCS |
| 33 | `d42b381` | feat(rag): single worker + §4.3 failure-rate reframe | SHARED (Procfile + docs) |
| 34 | `245337a` | feat(rag): phrasing-variance fixture + intent observability | BACKEND |
| 35 | `db24f5d` | feat(strategy): implementation progress UI | FRONTEND |

**Category breakdown:** BACKEND: 26 | DOCS: 5 | CONFIG: 1 | SHARED: 1 | FRONTEND: 1 | migration: 1 (counted in BACKEND)

### 1c. main not on fawc — 14 commits

All 14 are accounted for:
- **12 cherry-picks** from fawc (verified by subject-match; different SHAs, Co-Authored-By footers)
- **2 docs-only** commits unique to main: `ea2f01d`, `1214946`

### 1d. main not on vercel — 14 commits (same set as 1c)

These must flow to vercel during reconciliation.

### 1e. vercel not on fawc — 1 commit

`db24f5d` (strategy progress UI) — already on main as cherry-pick `2bea4f0`. Content identical.

---

## 2. Conflict Surface

### 2a. File overlap

| Metric | Count |
|--------|-------|
| Files changed on fawc (vs main) | 66 |
| Files changed on vercel (vs main) | 38 |
| Overlapping files | 38 |
| fawc-unique files | 28 |
| vercel-unique files | **0** |

**Every file vercel touches, fawc also touches.** This means vercel-deploy is a strict subset of fawc's file surface.

### 2b. Content divergence analysis

Of the 38 overlapping files, blob-hash comparison shows:

| Status | Count | Files |
|--------|-------|-------|
| **IDENTICAL** (fawc == vercel) | 36 | All overlap files except 2 below |
| **THREE-WAY-DIVERGE** | 2 | `backend/main.py`, `docs/.../Architecture.md` |

### 2c. Three-way divergent files — detail

**`backend/main.py`:** fawc adds cadence router import + registration (2 lines). vercel doesn't have it. **Resolution: fawc wins (superset).** Trivial auto-merge.

**`docs/callwen-rag/AdvisoryBoard_QueryInterpretation_Architecture.md`:** fawc has 155 more lines than vercel. File doesn't exist on main. **Resolution: fawc wins (superset).** No conflict.

---

## 3. Landmines

### 3a. Alembic migrations

| Branch | Migrations (vs main) |
|--------|---------------------|
| fawc | 3 new migrations |
| vercel | 0 |

Migrations are fawc-only — no conflict. The 3 migrations:
1. `53efd717` — add strategy implementation tasks
2. `b59e2536` — alter action_items.source to varchar(30)
3. `f9b81372` — add cadence_templates, client_cadence

### 3b. Procfile

Both fawc and vercel have `--workers 1` (vs main's `--workers 2`). **Identical on both branches.** Main is stale — fawc/vercel value wins.

### 3c. Dependencies

`backend/requirements.txt` — **no divergence** across all three branches.

`frontend/package.json` — **no divergence** across all three branches.

### 3d. No lock file conflicts detected.

---

## 4. Prod-Active Commit Integrity

| Prod system | Deploy source | HEAD | Status |
|-------------|--------------|------|--------|
| Railway (backend) | fawc | `f0c846c` | All 49 fawc commits are live |
| Vercel (frontend) | vercel-deploy | `db24f5d` | All 35 vercel commits are live |

**Critical finding:** vercel-deploy is a proper ancestor of fawc (merge-base `245337a` is fawc's parent of HEAD). This means fawc is strictly ahead of vercel, with the only addition being the cadence G4-P3b commit. The frontend commit (`db24f5d`) exists on vercel-deploy but was cherry-picked to main as `2bea4f0`.

---

## 5. Merge Strategy Recommendation

### Why fawc-first, then vercel fast-forward

1. **vercel is a subset of fawc** — 0 vercel-unique files, 36/38 overlapping files identical
2. **Only 2 three-way divergences**, both trivially resolved (fawc wins as superset)
3. **fawc has the migrations** — must land first
4. **vercel's only unique commit** (`db24f5d`) is already on main via cherry-pick

### Proposed Phase 2 sequence

```
Step 1: merge fawc → main (will have 37 new commits + resolve 2 docs-only main commits)
Step 2: fast-forward vercel-deploy/main to main (vercel is behind fawc, this catches it up)
Step 3: verify all three HEADs are identical
Step 4: delete fawc branch (optional, after verification)
```

### Risk assessment

| Risk | Level | Mitigation |
|------|-------|------------|
| `backend/main.py` merge conflict | LOW | 2-line addition, auto-mergeable |
| Architecture.md conflict | NONE | File doesn't exist on main |
| Migration ordering | NONE | All on fawc, none on vercel |
| Procfile conflict | LOW | All three agree on final state |
| Cherry-pick duplication | LOW | Git handles identical-content cherry-picks gracefully |
| Test regression | LOW | All tests pass on fawc HEAD already |

### Expected merge conflicts: 1-2 files, all trivially resolvable.

---

## 6. Carry-Forward Notes

1. **`set_firm_default` has no `is_active` guard** — fix in future G4-P2.7
2. **Test fixture seeds 3 system templates** vs prod's 4 — cosmetic, not blocking
3. **2 docs-only commits on main** (`ea2f01d`, `1214946`) will create merge-commit noise but no content conflict
4. **Procfile `--workers 1`** is intentional (Session 21 change for interpreter cache locality) — do not revert to 2

---

*End of Phase 1 audit. Awaiting Sam's review before Phase 2 (merge execution).*

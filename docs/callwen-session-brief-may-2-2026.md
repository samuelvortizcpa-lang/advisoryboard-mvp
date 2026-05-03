# Callwen Session Brief — May 2, 2026

Supersedes any prior session brief. This is the canonical starting point for new sessions.

---

## Branch & Deploy Topology (Post-Reconciliation)

**Single canonical trunk:** `origin/main` on `samuelvortizcpa-lang/advisoryboard-mvp`.

All development happens on `origin/main`. No long-lived feature branches.

### Deploy targets

| Service | Watches | Repo | Branch | Trigger |
|---------|---------|------|--------|---------|
| **Railway** (backend) | directly | samuelvortizcpa-lang/advisoryboard-mvp | main | push to lang/main |
| **Vercel** (frontend) | via mirror | samuelvortizcpa-code/advisoryboard-mvp | main | GitHub Action mirrors lang/main → code/main on every push; Vercel auto-deploys from code/main |

### Mirror workflow

- File: `.github/workflows/mirror-to-code-repo.yml` on origin/main
- Trigger: every push to `main` on lang repo
- Action: force-push lang/main → code/main via deploy SSH key
- Lag: ~10-30 seconds from lang push to code mirror complete
- **Direct pushes to code repo are discouraged.** The mirror force-pushes on every lang/main change and will overwrite any divergence.

### Git remotes (local)

| Remote | URL | Role |
|--------|-----|------|
| `origin` | `git@github.com:samuelvortizcpa-lang/advisoryboard-mvp.git` | Canonical. All pushes go here. |
| `code-mirror` | `https://github.com/samuelvortizcpa-code/advisoryboard-mvp.git` | Emergency manual mirror. Normal sync handled by GitHub Action. |

---

## v1 Milestone Gate Progression

| Gate | Status |
|------|--------|
| Gap 2 (strategy implementation tasks) | Done |
| G4-P1 (cadence models + migration) | Done |
| G4-P2 (cadence service layer) | Done |
| Conftest fix (metadata isolation) | Done |
| G4-P2.5 (read helpers) | Done |
| G4-P3a (per-client cadence API, 4 endpoints, 23 tests) | Done |
| G4-P2.6 (cross-org scope guards) | Done |
| Bundled cherry-pick to main | Done |
| G4-P3b (org-level template management, 6 endpoints, 36 tests) | Done |
| G4-P3b cherry-pick to main | Done |
| Three-branch reconciliation (Phase 1 audit + Phase 2 merge + Phase 3 mirror) | Done |
| **G4-P4 (UI)** | **NEXT** |
| Gap 3 (kickoff-memo only) | After G4-P4 |
| Gap 1 (kickoff-memo-command only) | After Gap 3 |
| One real Day-14 kickoff | After Gap 1 |
| Fan-out / fix / pivot decision | After kickoff |

---

## Carry-Forwards

### Resolved this session

- **P1 — Three-branch divergence:** Resolved. Single-trunk with GitHub Actions mirror.
- **P0 — April-29-2026 brief stale:** Superseded by this brief.

### Active

- **P2 — `set_firm_default` has no `is_active` guard:** Service function accepts inactive templates. Fix in future G4-P2.7.
- **P3 — Test fixture seeds 3 system templates vs prod's 4:** Cosmetic, not blocking.
- **P3 — Mirror health monitoring:** GitHub Action runs need observation. If they fail silently, code/main goes stale and Vercel deploys an old build. Recommend: verify lang/main HEAD == code/main HEAD before claiming "deploys synchronized" in future sessions.
- **P3 — Sentry `push_scope` deprecation:** `query_interpreter.py:244` uses deprecated `sentry_sdk.push_scope`. Non-blocking; update when Sentry SDK is bumped.

---

## Test Baseline

- **Backend:** 427 passed, 4 failed (3 voucher_detection + 1 client_isolation — all pre-existing, non-blocking)
- **Run:** `cd backend && venv/bin/python -m pytest -q`

---

## Recovery Commands

### Restore form-aware-chunker-wip (if needed)
```bash
git push origin origin/archive/form-aware-chunker-wip-20260502:refs/heads/form-aware-chunker-wip
```

### Roll back the reconciliation merge
```bash
git reset --hard pre-reconciliation-main-20260502
git push origin main --force-with-lease
```

### Re-add vercel-deploy remote (if code-mirror remote was removed)
```bash
git remote add code-mirror https://github.com/samuelvortizcpa-code/advisoryboard-mvp.git
```

### Pre-reconciliation backup tags (on remotes)
| Tag | SHA | Remote |
|-----|-----|--------|
| `pre-reconciliation-main-20260502` | `8c4512f` | origin |
| `pre-reconciliation-fawc-20260502` | `f0c846c` | origin |
| `pre-reconciliation-vercel-20260502` | `db24f5d` | code-mirror (samuelvortizcpa-code repo on GitHub) |

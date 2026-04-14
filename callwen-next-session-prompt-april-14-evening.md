# Callwen — Next Session Pickup Prompt (April 14, 2026 Evening)

Use this file to start the next Claude Code session. Copy the block between BEGIN PROMPT and END PROMPT and paste it as the opening message.

---

<!-- BEGIN PROMPT -->

## Project setup

Project path: `/Users/samortiz/advisoryboard-mvp-code`
Branch: `main`

Before doing any work, read these three files in order:

1. `session-summary-april-13-2026-evening.md` — what happened last session, what shipped, what's blocked
2. `CLAUDE.md` — project conventions, deploy workflow (line 113: Railway watches origin/main, Vercel watches vercel-deploy remote)
3. `client-linking-architecture.md` — skim this; it becomes relevant after the voucher classifier ships

## Expected git state

Verify before proceeding:

```
git log --oneline -4
```

Expected:
```
8b3d381 feat(admin): add GET /api/admin/clients endpoint for eval dropdown
ca75c98 chore(admin): deprecate admin-dashboard directory
8da64d1 docs: session summary April 13 2026
3fdf320 security(admin): fail closed when ADMIN_USER_IDS is missing
```

Working tree should be clean except for two untracked files:
- `session-summary-april-13-2026-evening.md`
- `callwen-next-session-prompt-april-14-evening.md`
- Possibly `admin-dashboard/README.md` (scratch file, not tracked, ignore it)

Remote state:
- `vercel-deploy/main` is at ca75c98 (one commit behind local)
- `origin/main` is at ca75c98 according to last fetch — but cannot be pushed to with current credentials
- Local main is at 8b3d381 — two commits ahead of both remotes

Run `git remote -v` to confirm remotes:
- origin → samuelvortizcpa-lang/advisoryboard-mvp.git
- vercel-deploy → samuelvortizcpa-code/advisoryboard-mvp.git

## North star

The goal of all this work is a world-class RAG system for CPAs — correct answers, source-cited to the exact page, fast enough to use mid-client-call. Current baseline on Michael Tjahjadi's 2024 Form 1040: 100% retrieval hit rate, 10/10 header-clean, 9/10 real correctness. The 1/10 miss is the taxable interest extraction bug (carried since April 9).

Voucher classifier fix and client linking Stage 1 are the nearest-term levers. Stage 2+ work on business return extraction, multi-year reasoning, OCR quality, confidence calibration, and source-card UX are the bigger dimensions of "world-class" that deserve a dedicated strategy session. Note them in the session summary if they come up; don't let them get lost.

## Priorities for this session

### PRIORITY 1: Fix the origin credential problem

**Non-negotiable first task.** Nothing else ships until this works.

The Git credential helper is currently authenticated as samuelvortizcpa-code, which cannot push to origin (samuelvortizcpa-lang/advisoryboard-mvp). Railway watches origin/main for auto-deploy, so backend commits are stranded.

Options to fix:
- `gh auth login --web` with the samuelvortizcpa-lang GitHub account
- Change origin URL to SSH (`git remote set-url origin git@github.com:samuelvortizcpa-lang/advisoryboard-mvp.git`) with a properly configured SSH key
- Push via GitHub web UI as a last resort (create a PR from a fork or upload the commit manually)

**Verification:** Successfully run `git push origin main`. This should push both ca75c98 and 8b3d381 to origin. Confirm Railway auto-deploys the backend by checking the health endpoint:
```
curl -sf https://advisoryboard-mvp-production.up.railway.app/health
```

Do NOT proceed to any other work until origin push works and Railway has the new backend code.

### PRIORITY 2: Verify backend endpoint is live

After Railway deploys, verify GET /api/admin/clients is live and returning data.

Use the user's authenticated Chrome browser (not headless — Clerk auth requires real browser for prod). Navigate to callwen.com/admin, open browser dev tools, and run:
```javascript
fetch('/api/admin/clients').then(r => r.json()).then(console.log)
```

Expected response shape:
```json
[
  {
    "id": "uuid-string",
    "name": "Client Name",
    "owner_email": "user@example.com",
    "document_count": 3
  }
]
```

Spot-check: Michael Tjahjadi should appear with id `92574da3-13ca-4017-a233-54c99d2ae2ae`. List should be sorted alphabetically by name (case-insensitive).

### PRIORITY 3: Finish P4 frontend — wire Run Eval client dropdown

File: `frontend/app/admin/rag-analytics/page.tsx`

Replace the hardcoded `EVAL_CLIENTS` array (lines 71-74) with a `useEffect` that fetches `/api/admin/clients` on mount.

Requirements:
- Loading state while fetch is in flight
- Error state if fetch fails (show inline message, don't break the page)
- Empty state if no clients returned
- Default selected client: Michael Tjahjadi (id `92574da3-13ca-4017-a233-54c99d2ae2ae`) if present in the list, otherwise first client in the list
- Remove the TODO comment on line 71

Commit as: `feat(admin): wire Run Eval client dropdown to real endpoint`

Deploy: `git push vercel-deploy main`

Verify in prod: open callwen.com/admin/rag-analytics, click Run Eval, confirm the dropdown shows real clients from the database (not just Michael Tjahjadi hardcoded).

### PRIORITY 4: Voucher classifier contamination fix

This is the highest-leverage remaining RAG correctness work and unblocks client linking Stage 1.

**The problem:** Michael Tjahjadi's documents row currently reads `document_subtype: Form 1040-ES` (should be `Form 1040`). The classifier is being fed voucher chunks (1040-ES payment coupons) which contaminate its classification of the whole document.

**The fix:** Exclude voucher pages from classifier input using the existing `detect_voucher_chunk` / `_flag_voucher_continuations` functions from `backend/app/services/chunking.py`. These functions already exist and are used elsewhere — this is about using them at the classifier input stage too.

**Verification sequence:**
1. Reprocess Michael's document via the admin reprocess endpoint
2. SQL-verify the documents row now reads the correct subtype
3. Re-run eval via /admin/rag-analytics Run Eval button (now with real dropdown from P3)
4. Acceptance: 10/10 header-clean, 9/10+ real correctness (no regression from baseline)

Commit as: `fix(classifier): exclude voucher chunks from classifier input`

**This unblocks client linking Stage 1** because cross-entity testing needs a clean classifier baseline.

### PRIORITY 5 (stretch): Taxable interest extraction bug

The one real failure in the April 9 baseline (the 9/10 miss). Investigation only — fix may extend beyond one session.

Start with: `SELECT * FROM document_chunks WHERE content ILIKE '%interest%' AND client_id = '92574da3-13ca-4017-a233-54c99d2ae2ae'` to see what chunks exist and whether the interest data is being extracted at all.

### PRIORITY 6 (if time): Begin client linking Stage 1

ONLY if voucher classifier shipped cleanly, eval held, and energy remains.

Prompts file: `claude-code-prompts-client-linking-stage-1.md` (edited last session to remove deploy-path prerequisites).

Start with the Opening Context, then Part 1 (schema migration). Do not rush — this is multi-session work.

## Checkpoint discipline

If a reviewer is working alongside Claude Code in this session:
- Show actual diffs, not summaries. Use `git diff ... | cat` to force raw output.
- Push back on security smells — especially anything touching admin auth, API keys, or Clerk token handling.
- Stop when tired. Fatigued reviews miss things.
- Verify deploy paths before assuming pushes trigger rebuilds. Last session's biggest lesson.

## Carryovers not on tonight's priority list

These are tracked but not scheduled for this session:
- 58 pre-existing test failures (technical debt, not blocking)
- REPROCESS_TASKS in-memory dict needs persistence
- Gemini 3072 to 768 dimension migration
- Credential rotation sweep (7+ overdue plus 2 from April 12 exposures)

<!-- END PROMPT -->

# Session Summary — April 20, 2026 (Late Night)

## Headline

Phase 1 hygiene, Phase 2 integration, and partial Phase 3
production deployment executed. Integration commit `f3e3e5b`
shipped on `form-aware-chunker-wip` — wires `form_aware_chunk`
into `process_document` behind the `USE_FORM_AWARE_CHUNKER` env
var. Phase 3 blocked by Railway env var not propagating to the
Python process inside the container. Three separate reprocess
attempts (across three deployments) all fell through to
`structure_aware_chunk`. Michael's chunks remain at 236
(pre-session baseline, functionally unchanged).

---

## Session Arc

1. Phase 1 hygiene passed — network healthy, git clean,
   Railway healthy, backups confirmed (236 rows in
   `document_chunks_backup_20260421_pre_formaware`), baseline
   eval `11e499ec` citation 0.90
2. Phase 2a/2b: integration plan reviewed twice before code was
   written. `tax_year` ordering gap caught in review 2 (must
   extract before chunking block, not after). `form_aware_chunk`
   signature confirmed: `(pages, tax_year) → list[dict]`
3. Phase 2c: diff applied to `rag_service.py` in 4 hunks. CC
   caught and fixed its own typo (`is_voucker` → `is_voucher`)
   mid-apply
4. Phase 2c verification: `git diff` matched approved diff,
   syntax check passed, 54 chunker tests passed, broader suite
   regression check via `git stash` proved zero new failures
   (4 pre-existing FAILED, 58 pre-existing ERRORs — all
   consent/stripe/voucher, unrelated)
5. Phase 2d: three lightweight smoke tests
   (`test_form_aware_integration.py`) instead of heavy dispatch
   tests. Rationale: real dispatch behavior validated in
   production via Phase 3 flag-off deployment
6. Phase 2e: committed as `f3e3e5b`, pushed to
   `origin/form-aware-chunker-wip`
7. Phase 3a: backup table
   `document_chunks_backup_20260421_pre_formaware` created
   (236 rows, confirmed)
8. Phase 3b: flag-OFF verification eval `098c43e1` matched
   baseline (0.90 citation). **Diagnostic oversight:** this was
   actually running `aa53409` on `main`, not our new code — the
   gate passed for the wrong reason (both deployments are
   identical on non-flag paths)
9. Phase 3c attempt 1: flag flipped ON, reprocess triggered via
   `X-Admin-Key` auth (pivoted from Clerk JWT after 403). Went
   through `structure_aware_chunk` — deployment `88e779df` was
   built from `main`=`aa53409`, not our WIP branch
10. Diagnosis 1: `railway status --json` revealed
    `meta.branch=main`, `meta.commitHash=aa53409`. Changed
    Railway source to `form-aware-chunker-wip`. New deployment
    `c99c27e4` built from `f3e3e5b`
11. Phase 3c attempt 2: reprocess went through
    `structure_aware_chunk` despite correct commit deployed.
    Hypothesis: env var not re-read at container start
12. Diagnosis 2: user restarted container via Railway UI
    (deployment `710a88f6`), confirmed same commit `f3e3e5b`
13. Phase 3c attempt 3: reprocess again went through
    `structure_aware_chunk`. Env var confirmed in UI, but
    `os.environ.get("USE_FORM_AWARE_CHUNKER")` inside the
    running Python process is not returning `"true"`
14. Stopped at 12:40 AM. Three attempts, same result.

---

## What Shipped

- **Commit `f3e3e5b`** on `form-aware-chunker-wip` (pushed to
  origin)
  - `backend/app/services/rag_service.py`: +42/−18 lines.
    Dispatch behind `USE_FORM_AWARE_CHUNKER` flag. When flag is
    `"true"` AND `document_type == "tax_return"` AND Document AI
    pages are available, uses `form_aware_chunk` with per-chunk
    metadata. All other paths unchanged.
  - `backend/tests/test_form_aware_integration.py`: +42 lines,
    3 smoke tests (import hygiene with flag unset, import hygiene
    with flag true, env var predicate correctness)
- **Test results:** 54 chunker tests + 3 integration tests = 57
  total, all passing
- **Zero regressions:** verified by `git stash` baseline
  comparison — pre-existing FAILED/ERROR counts unchanged

---

## What Did Not Work

The `USE_FORM_AWARE_CHUNKER=true` variable is set in the Railway
Variables UI (confirmed by user, trailing whitespace ruled out)
but `os.environ.get("USE_FORM_AWARE_CHUNKER")` inside the running
Python process returns something that does not `.lower()` to
`"true"`. Evidence:

- Three separate reprocess attempts all emitted the
  `structure_aware_chunk` log line (`236 chunks (size=600,
  overlap=100, type=tax_return)`), never the `form-aware
  chunking` log line
- Commit `f3e3e5b` is confirmed deployed (`railway status` shows
  `branch=form-aware-chunker-wip`, `commit=f3e3e5bd`)
- `document_type` is `tax_return` (classifier logs 95%
  confidence)
- `docai_result["pages"]` is present (structure-aware chunking
  uses it successfully)
- The only remaining predicate condition is the env var

---

## Hypotheses To Test Next Session

1. **Service vs environment variable scope.** Railway has both
   "service-level" and "environment-level" variables. The
   variable may be defined at one level but not visible at the
   other.
2. **Variable shadowing.** A Railway-managed variable with the
   same name could shadow the user-defined one.
3. **Python `os.environ` caching.** If the process was forked
   before the variable was injected, the child process wouldn't
   see it. Unlikely with Uvicorn's worker model but not
   impossible.
4. **Build-time vs runtime scoping in `railway.toml`.** The
   `backend/railway.toml` config might scope variables
   differently.

**Diagnostic approach:** Add a one-line startup log in `main.py`
or module-level code printing
`os.environ.get("USE_FORM_AWARE_CHUNKER")`. Deploy, check log.
This will immediately reveal what the process actually sees.

---

## Production State At Session End

- Branch `form-aware-chunker-wip` HEAD: `f3e3e5b` (pushed)
- Railway source branch: `form-aware-chunker-wip` (changed from
  `main` during session)
- Railway active deployment: `710a88f6` (built from `f3e3e5b`),
  healthy
- `USE_FORM_AWARE_CHUNKER`: set in Railway UI but not reaching
  the Python process. **Should be set back to `false` before
  next session starts** to prevent accidental activation if the
  propagation issue self-resolves
- Michael's chunks: 236, pre-session baseline (verified
  unchanged — all three reprocess attempts went through
  structure-aware and produced identical 236-chunk output)
- Backup table
  `document_chunks_backup_20260421_pre_formaware`: intact,
  236 rows

---

## Key Identifiers

```
Client:                  Michael Tjahjadi
Client ID:               92574da3-13ca-4017-a233-54c99d2ae2ae
Document ID:             af525dbe-2daa-4b93-bfde-0f9ed9814e41
Production HEAD (main):  aa53409
WIP branch HEAD:         f3e3e5b (branch: form-aware-chunker-wip, pushed)
WIP branch prior HEAD:   b2f93a2
Integration commit:      f3e3e5b
Model pin:               gpt-4o-mini-2024-07-18
Embedding model:         text-embedding-3-small (1536 dim)

Deployments this session:
  88e779df  (main/aa53409 — structure-aware, wrong code)
  c99c27e4  (form-aware-chunker-wip/f3e3e5b — env var not reading)
  710a88f6  (form-aware-chunker-wip/f3e3e5b — restart, still not reading)

Reprocess task IDs this session:
  f7890744  (complete, structure-aware path)
  85241ba1  (complete, structure-aware path)
  eca0f847  (complete, structure-aware path)

Backup tables:
  document_chunks_backup_20260418_q7_experiment  (2 rows)
  document_chunks_backup_20260419_q4_experiment  (3 rows)
  document_chunks_backup_20260421_pre_formaware  (236 rows)

Evals this session:
  11e499ec  (baseline, citation 0.90)
  098c43e1  (flag-OFF verification, citation 0.90 — but note:
             actually from aa53409 on main, not f3e3e5b)
```

---

## Carryover Queue

### New from this session — P0

- **Resolve Railway env var propagation to container.** Diagnostic
  approach: add startup log line printing
  `os.environ.get("USE_FORM_AWARE_CHUNKER")` in `main.py` or
  `rag_service` module init, deploy, read log. This is the sole
  blocker for Phase 3.
- **After P0 resolved:** re-execute Phase 3c (reprocess Michael,
  verify 148 chunks and Schedule 2/3 visibility), Phase 3d
  (5 evals with decision criteria from April 19 brief), Phase
  3e/3f decision.

### New from this session — P1

- **Two-branch discipline gap.** Railway source was `main`
  (`aa53409`) throughout Phase 2 and initial Phase 3b. Flag-OFF
  "verification" at `098c43e1` therefore verified `aa53409`, not
  our new commit. The Phase 3b gate passed for the wrong reason.
  **Future sessions:** always confirm `railway status` commit
  matches expected before treating flag-OFF eval as a valid gate.
- **`'Document' object has no attribute 'owner_id'` warning** in
  journal entry flow (non-fatal, appeared three times this
  session, not related to chunker work).

### New from this session — P2

- **REPROCESS_TASKS in-memory store** still returns `?` responses
  during polling (task evicts between workers). Already in P2
  carryover but hit it three times this session, confirming
  Redis migration priority.
- **Railway Port 8080 mismatch** noted in UI (app runs
  `${PORT:-8000}` by default). Working somehow but investigate.
- **Delete four pre-existing `test_voucher_detection.py`
  failures** that appear to reflect April 20 voucher-detector
  hardening (tests weren't updated to match new 2-signal
  contract).
- **Watch Paths field empty in Railway** — every push to
  `form-aware-chunker-wip` will redeploy production. Add
  appropriate watch paths when chunker work lands on `main`.

### Carried forward (unchanged from April 20 morning)

- P1 — Retrieval scorer telemetry anomaly (Q7 chunks show ✗
  Retrieval with correct citation)
- P1 — Tighten Q5 expected citation in ground_truth_v1
- P1 — Admin UI: expose per-question citation pass/fail
- P2 — Schedule 2 tag inconsistency ("Schedule 2" vs
  "Schedule 2 (Form 1040)" depending on OCR)
- P2 — Page 7 mid-page transition to "Schedule A (Form 8936)"
  from cross-reference
- P2 — Content inference is Form 1040 only (other forms remain
  header-dependent)
- P2 — DEFAULT_SYSTEM_PROMPT lacks MANDATORY TAX YEAR RULE
- P2 — Prompt text duplication
- P2 — Pin Anthropic model aliases to dated snapshots
- P2 — Orphaned schema cleanup (`client_links`, `client_kind`)
- P2 — Close -code PR #1, delete orphaned -code branch
- P2 — `search_vector` auto-update trigger
- P2 — `flag_voucher_continuations` imported but not called
- P2 — Save AdvisoryBoard_FormAware_Chunker_Spec.md to project
  knowledge
- P2 — Safer production DB access patterns
- P3 — Fix stale log labels at query_router.py:103, 398, 608
- P3 — Update RAG Analytics dashboard baseline
- P3 — Two-repo consolidation
- P3 — Property-based tests (hypothesis)
- P3 — Multi-document verification corpus
- Credential rotation sweep (Supabase DB done; others pending)
- REPROCESS_TASKS in-memory → Redis migration
- Gemini embeddings 3072 → 768 dimension migration
- §7216 consent UX bug
- Null-email users (Clerk webhook sync)
- SQLite/TSVECTOR test infrastructure gap
- Gmail sync 400 errors
- Stage 1 client linking retry

---

## Discipline Notes

### What worked

- **Phase 2 integration plan reviewed twice before code.** The
  `tax_year` ordering gap (must extract before chunking block,
  not after) was caught in review 2, not in production.
- **CC's self-caught typo (`is_voucker`).** Would have propagated
  undetected had it not been spotted in the single-hunk edit log.
  Good argument for reviewing each edit hunk individually rather
  than batching.
- **X-Admin-Key pivot away from Clerk JWT.** Saved 30+ minutes
  of trying to work around the 403 admin access issue. The
  `verify_admin_access` dual-auth pattern (X-Admin-Key OR Clerk
  JWT) was confirmed by reading the source, not guessing.
- **Byte-identity check on Michael's chunks.** Between pre-deploy
  and flag-OFF verified the code path wasn't altered — even
  though the flag-OFF verification was technically verifying the
  wrong commit, the test design was correct.
- **Git stash regression check.** Stashing Phase 2c changes,
  re-running the full suite, and comparing FAILED/ERROR lists
  side-by-side proved zero regressions definitively. Better than
  "it looks the same."
- **Credential discipline.** Admin API key never appeared in
  session output — read into shell variable, used once, unset.
  Config files were 600-permissioned and cleaned up after use.

### What did not work

- **Flag-OFF verification at `098c43e1` was declared a pass
  without confirming the deployed commit was our new code.** It
  happened to pass "for free" because both deployments were
  identical on the non-flag paths, but the gate wasn't doing
  what we thought. The two-branch discipline gap (Railway on
  `main`, our code on WIP) was invisible until the first
  reprocess failed.
- **The 2.5-hour budget was blown by 2 hours.** Budget existed
  for exactly this reason — to limit scope creep into debugging
  infrastructure issues. Should have invoked the stop gate at
  the first failed reprocess attempt (step 9), not after three.
- **Credential file creation was sloppy.** Several nano failures,
  heredoc indentation bugs in early attempts, JWT file left on
  disk briefly between attempts. Multi-step file-creation flows
  should use `printf` or `pbpaste`, not `nano` heredocs.
- **Initial CC suggestion of `railway run` for accessing
  secrets.** CC confidently described `railway run` as "runs
  inside the container" when it actually pulls secrets into a
  local subprocess. Good user override, but the confident-wrong
  suggestion cost time and trust.
- **Polling loop didn't handle `"complete"` status.** First
  polling loop checked for `"completed"` but the API returns
  `"complete"`. Loop ran all 30 iterations instead of breaking.
  Fixed in subsequent attempts but wasted a few minutes.

### Claude Code drift this session

Moderate. Five notable events:
1. **`is_voucker` typo** in the embed-loop edit hunk. Caught and
   fixed immediately, but would have been a silent data bug in
   production (metadata key mismatch).
2. **`railway run` misdescription.** Described as container-side
   execution when it's local subprocess with injected secrets.
   User correctly overrode.
3. **Polling loop status check mismatch.** Checked `"completed"`
   instead of `"complete"`. Minor but avoidable.
4. **Confident diagnosis after first reprocess failure** ("the
   env var must not be set") when the actual root cause was
   wrong commit deployed. Good that it was diagnosed via
   `railway status --json`, but the initial hypothesis skipped
   the most obvious check.
5. **All three reprocess configs built correctly** with admin key
   discipline — no credential leaks in session output.

---

## Next Session Plan

1. Hygiene check as always (network, git, Railway, backups)
2. **Resolve P0** — figure out why `USE_FORM_AWARE_CHUNKER` isn't
   reaching the container. Add one-line startup log in `main.py`,
   deploy, check Railway logs for the printed value.
3. Once resolved: Phase 3c (reprocess Michael, verify 148 chunks
   and Schedule 2/3 visibility), Phase 3d (5 evals with April 19
   decision criteria), Phase 3e/3f
4. If env var issue can't be resolved in 30 min: merge WIP to
   `main` and deploy there (the flag behavior is moot if `main`
   is the WIP code). But investigate first — the env var issue
   may affect other variables too.
5. Before starting: set `USE_FORM_AWARE_CHUNKER=false` in Railway
   until ready to test, to prevent accidental activation.

Budget next session: 2 hours max. Hard gate at hour 1.

---

## Scratch Files on Local Machine

- `/tmp/verify_michael_chunker.py` — production verification
  script (read-only, from April 20 morning session)
- `/tmp/pages_5_6_text.py` — extracted page 5 and 6 text
- `/tmp/diagnose_probe.py` — focused probe script
- All credential/response files (`eval.curlcfg`,
  `reprocess.curlcfg`, `reprocess_response.json`,
  `reprocess_status.curlcfg`) cleaned up during session

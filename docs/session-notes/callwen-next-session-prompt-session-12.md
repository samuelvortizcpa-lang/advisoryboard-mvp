# Callwen — Session 12 Pickup

## Where we left off

Session 11 closed at ~5:10 PM April 24, 2026.

Branch: `form-aware-chunker-wip` (HEAD `61a4c76`)
Railway prod: `61a4c76` / SUCCESS, `/health` green.

One commit pushed since Session 10:

```
61a4c76  feat(chunker): Phase 1 section-flip detector (logging only)
```

Full commit stack from `form-aware-chunker-wip` vs `main`, pre-Session-9 base:

```
61a4c76  feat(chunker): Phase 1 section-flip detector (logging only)     [S11]
a227cba  chore: track dev shell scripts (setup, db_setup, run_tests)      [S10]
6bb91a0  fix(security): full-schema PostgREST/Supabase lockdown            [S10]
35def80  fix(security): revoke anon/authenticated from document_chunks    [S9]
22ecbe8  fix(config): rename backend/.env to .env.local                   [S9]
e6c6f49  fix(rag_eval): accept Schedule 2 Line 24 for Q10 Roth excess     [S9]
```

Last eval post-deploy: eval_id `6c19f3c6`, retrieval=1.00, response=0.80, citation=0.90, 0 errors. Within the locked Session 11 acceptance envelope (Q4 + Q6 known-variance flippers only — LLM non-determinism, not drift).

## Key context to carry forward

**Phase 1 section-flip detector is LIVE in prod, logging-only.** Algorithm is v3 revisit counting:

```
revisits = runs_of_same_section - distinct_sections_in_window
```

Window 10 lines, threshold=2. Fires on both per-line oscillation (A-B-A-B) and run-based oscillation (AAA-BBB-AAA). Quiet on sequential progression (A-B-C-D-E) found in normal multi-section forms.

Detector fires only when a real document is chunked — NOT on existing chunks. First real telemetry depends on next document upload or reprocess event. Michael and Tracy reprocess remains explicitly forbidden.

**Spec §5 is stale.** `AdvisoryBoard_ScheduleA_Oscillation_Spec.md` §5 still describes v1 flip-counting. The v3 formula and rationale (v1→v2→v3 trail) live in commit `61a4c76`'s commit message. Needs manual paste-in to the spec before Phase 2 design work starts. Spec lives in the Claude project folder (read-only from Claude Code's filesystem view).

**Eval variance envelope** (locked, empirical, 4-run sample):

| Metric | Range |
|--------|-------|
| retrieval | 1.00 (hard floor, never observed drop) |
| response | [0.80, 1.00] |
| citation | [0.90, 1.00] |

Q4 (interest $7, adjacent-number disambiguation) and Q6 (capital gains $7,584 decomposition) are the ONLY questions that flip on identical prod code. Worst case (both flip) = response=0.80, citation=0.90.

**psql is the load-bearing diagnostic channel** for per-question eval detail because `/evaluations/{id}` strips `citation_hit` and `extracted_citations` from the serialized response. Flagged three sessions running.

## Session 12 agenda (in priority order)

None of these are urgent. Session 11's P1 closed cleanly. Session 12 is polish / observability / Phase 2 prep depending on where Sam's head is.

### P1 — Observe detector output in prod logs

Goal: first real telemetry. Check Railway logs for `SECTION_FLIP_DETECTOR: N suspicious windows` warnings. Has any document been uploaded/processed since April 24 ~17:10 EDT?

- If yes: inspect alerts — which forms? Which pages? Does run-based oscillation surface at expected rate?
- If no uploads: item deferred until organic signal appears. Note the gap; don't force a test upload.

### P1 — Restore per-question fields in /evaluations/{id} API response

Every per-question diagnostic in Session 11 required psql queries because this endpoint strips `citation_hit` and `extracted_citations`. Flagged in Sessions 9, 10, 11. ~10-min fix in `backend/app/api/rag_analytics.py` (the `per_question` dict construction around line 101-117). Return `citation_hit`, `extracted_citations`, `expected_citations` in the normalized dict.

### P1 — Tighten Q4 and Q6 ground-truth fixtures

- **Q4 interest ($7):** LLM variance is structural (adjacent number disambiguation). Options: widen expected values to accept $0 with a flag-for-review, OR add prompt guidance to prefer the specific Line 2b value over adjacent numbers.
- **Q6 capital gains ($7,584):** LLM decomposes into components ($249 + $7,337). Options: accept decomposition via regex/sum match in scorer, OR add prompt guidance to prefer reported totals.

Either direction shrinks the envelope variance band. Quick win.

### P2 — Spec §5 paste-in

Update `AdvisoryBoard_ScheduleA_Oscillation_Spec.md` §5 to describe v3 revisit-counting. Replacement text lives in commit `61a4c76`. Spec file is in the Claude project folder (Sam paste).

### P2 — Merge form-aware-chunker-wip → main

Branch now 6 commits ahead. Railway-watched branch decision remains open:

- **Option X** — switch Railway to watch `main`, then merge (cleaner long-term, more moving parts in one go)
- **Option Y** — merge and leave Railway on `form-aware-chunker-wip` (smallest change; deploy branch stays a wip branch)

Either way, dry-run the merge as fast-forward first — if not ff, stop and report divergence.

### P2 — Spec §8.5 paste-in (Insight-Quality Eval)

Session 10 ratified the 6 open questions. Replacement text lives in Session 10 summary. Still outstanding.

### P3 — Engineering practices extraction

Preflight pattern (S9/S10), PUBLIC-inheritance gotcha (S10), negative-tests-as-load-bearing (S9), integration-tests-between-unit-and-commit (new from S11), algorithm-fits-real-data (new from S11). Target ~45 minutes, standalone doc under `docs/`.

### P3 — Decide fate of scripts/verify_flip_detector.py

`.gitignored` now. Keep as Phase 2 reference, repurpose for a broader chunker integration harness, or delete. Housekeeping.

### P3 — Gmail OAuth refresh failure on connection f8c2780a...

Pre-existing, unchanged, not blocking.

## What NOT to do

- Don't revert or loosen any Session 9/10 security lockdown.
- Don't touch `form_aware_chunker.py` OR `form_sections.py` outside the Schedule A oscillation spec scope. Phase 2 work carries its own carve-out when it starts; Session 12 is observation and polish.
- Don't re-reprocess Michael or Tracy.
- Don't flip `USE_FORM_AWARE_CHUNKER` off.
- Don't delete backup tables or migration files.
- Don't use Supabase SQL editor for DB state changes. psql with inline `RAISE EXCEPTION`, always.
- Don't implement Phase 2 column reconstruction until the Phase 1 detector has produced telemetry on ≥2 weeks of real documents, OR there's an explicit decision that synthetic evidence is sufficient.
- Don't tune detector thresholds in code on speculation. Let prod telemetry show whether threshold=2 is right before adjusting.

## Starting checklist

Before any work, verify known-good state:

```bash
cd ~/advisoryboard-mvp-code
git status --short
git log --oneline -5
git branch --show-current
# Expected: clean-ish (session-summary-april-20-2026-late-night.md
# likely still untracked), HEAD 61a4c76, on form-aware-chunker-wip

curl -s https://advisoryboard-mvp-production.up.railway.app/health

railway status --json 2>/dev/null | python3 -c "
import sys, json
d = json.load(sys.stdin)
for e in d.get('environments',{}).get('edges',[]):
    for s in e['node'].get('serviceInstances',{}).get('edges',[]):
        dep = s['node'].get('latestDeployment',{})
        meta = dep.get('meta',{})
        print(f\"{(meta.get('commitHash') or '')[:8]}|{dep.get('status','?')}\")"
# Expected: 61a4c76?|SUCCESS

# Confirm full-schema lockdown still holds. Reconstruct PGPASSFILE +
# PG* env vars from Railway DATABASE_URL (Python parse → /tmp/.pgpass,
# export PG* env vars; same helper pattern used in Sessions 10 and 11).
# Then:

psql -c "
  SELECT
    (SELECT COUNT(*) FROM information_schema.role_table_grants
       WHERE table_schema='public' AND grantee IN ('anon','authenticated')) AS t_grants,
    (SELECT COUNT(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
       WHERE n.nspname='public' AND c.relkind='r' AND NOT c.relrowsecurity) AS rls_off,
    (SELECT COUNT(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
       JOIN pg_roles o ON o.oid=p.proowner
       WHERE n.nspname='public' AND o.rolname='postgres'
         AND has_function_privilege('anon', p.oid, 'EXECUTE')) AS pg_fns_anon;"
# Expected: 0 | 0 | 0
rm -f /tmp/.pgpass

# If picking up P1 (observe detector telemetry):
railway logs 2>/dev/null | grep -i 'SECTION_FLIP_DETECTOR' | head -20
# If no output: either no uploads since S11 close OR no uploaded docs
# exhibit oscillation. Both are informative — report either way.
```

Report the output and wait for next instruction before doing anything else.

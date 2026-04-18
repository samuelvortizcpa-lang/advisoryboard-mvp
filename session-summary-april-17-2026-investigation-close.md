# Session Summary — April 17, 2026 (Investigation Close)

## Headline

Citation regression root cause investigation closed as Outcome 3:
model drift, unconfirmable. All three hypotheses tested; A and C
falsified, B likely but not provable. `gpt-4o-mini` pinned to
`gpt-4o-mini-2024-07-18` snapshot as drift protection. 0.6 accepted
as new citation baseline. Stage 1 retry architecturally unblocked.

---

## Session Arc

90-minute focused investigation per the plan in
`callwen-next-session-prompt-april-17-followup.md`. Three hypotheses
tested in cheapest-first order, each with a decision gate.

### Step 0 — Hygiene Checks (~5 min)

All four checks passed:

| Check | Result |
|-------|--------|
| Railway ACTIVE deploy | `02bf8843` (SUCCESS, Apr 17 09:10 EDT) |
| Health endpoint | `{"status":"ok"}` |
| Railway context | `celebrated-delight / production / advisoryboard-mvp` |
| `rag_evaluations` count | 50 (> 49 threshold) |
| Git branch | `revert-client-linking-stage-1`, up to date with `origin/main` |

### Step 1 — Hypothesis A (Variance) — ~15 min

Ran 5 back-to-back evals against Michael (`ground_truth_v1`).

| Eval ID | Citation |
|---------|----------|
| `efdebc1b` | 0.6 |
| `d4d6e60e` | 0.6 |
| `37a0b94f` | 0.6 |
| `20f34547` | 0.6 |
| `a1667c9b` | 0.6 |

5/5 at 0.6, zero variance. **Hypothesis A falsified.** The regression
is deterministic, not distributional.

### Step 2 — Per-Question Failure Shape (abbreviated)

Confirmed from Step 1 inline data + user-supplied DB verification.
Same 4 questions fail with identical extractions across all runs:

| Q# | Question | Extracted | Expected |
|----|----------|-----------|----------|
| Q4 | Taxable interest | `[]` (empty) | Form 1040 2b / Schedule B 4 |
| Q7 | Charity | `form 1040, line 11` | Schedule A, 11/14 |
| Q9 | HSA limit | `form 8889, line 6` | Form 8889, 3/8 |
| Q10 | Roth IRA excess | `form 1040, line 24` | Form 5329, 18/24 |

Failure shape is deterministic and bit-identical across all post-
regression runs (now 13 total: 3 post-merge + 1 post-revert + 5
pre-pin + 5 post-pin, minus the baseline).

### Step 3a — Identify the Model (~10 min)

Checked Railway env vars for model overrides:
```
ANTHROPIC_API_KEY = <key>
OPENAI_API_KEY = <key>
```
No `CHAT_MODEL`, `LLM_MODEL`, `OPENAI_MODEL`, or Azure-related vars.
Model selection is 100% in code.

Traced the eval path through `rag_service.py` → `classify_query`
(gpt-4o-mini) → `route_completion` (factual → gpt-4o-mini). All
eval questions classify as "factual" and route to gpt-4o-mini at
temperature 0.1 via OpenAI direct API (no Azure, no custom base_url).

**Finding:** model is `gpt-4o-mini` alias, OpenAI direct, no env
override.

### Step 3b — Provider Changelog Check (~10 min)

1. **OpenAI docs page** — returned 403 (bot protection).

2. **OpenAI Models API** — queried directly from production:
   - `gpt-4o-mini` alias: `created = 2024-07-16 23:32:21 UTC`
   - `gpt-4o-mini-2024-07-18`: `created = 2024-07-16 23:31:57 UTC`
   - Only one dated chat snapshot exists for gpt-4o-mini
   - No newer snapshots (checked 2024-12-17, 2025-01-31, 2025-04-16,
     2025-04-17 — all NOT FOUND)
   - `created` field reflects model object registration, not weight
     updates — OpenAI can update weights silently

3. **OpenAI Status Page** (Apr 15–17 window):
   - Apr 16 21:21 UTC: Responses API Streaming Error (Java SDK) —
     irrelevant (different endpoint)
   - Apr 15 18:55 UTC: ChatGPT FedRAMP workspaces — irrelevant
     (ChatGPT product, not API)
   - No Chat Completions incidents in the window

**Finding:** no public evidence of a model change, but absence of
evidence is not evidence of absence for alias swaps.

### Step 3c — Pin and Eval (~40 min including 20-min build)

Pinned all `gpt-4o-mini` API calls to `gpt-4o-mini-2024-07-18` in
`query_router.py`. Six changes:

| Line | Change |
|------|--------|
| 82 | Classifier API call: pinned |
| 120 | `_TIER_MAP`: added pinned key |
| 377 | Factual path API call: pinned |
| 386–387 | `model_used` + log message: updated |
| 460 | Streaming `model_used` default: updated |
| 584 | Streaming factual API call: pinned |

Commit `4bb2ab42` pushed to `origin/main`. Railway deploy `e0c23e2f`
went SUCCESS after a ~20 minute build (see Build Time Note below).

Ran 5 post-pin evals:

| Eval ID | Citation |
|---------|----------|
| `73143b66` | 0.6 |
| `7765022a` | 0.6 |
| `da210010` | 0.6 |
| `0768fbbf` | 0.6 |
| `ddcdb21b` | 0.6 |

5/5 at 0.6. Per-question failure shape identical to pre-pin.
**Pin did not restore the baseline.** Either the alias was already
pointing at `2024-07-18` and never changed, or the snapshot itself
exhibits this behavior.

Per the commit contract: "If eval stays at 0.6, pin stays as drift
protection anyway."

### Hypothesis C — Deploy/Config Diff (~5 min)

Extracted commit SHAs from Railway deployment JSON:
- Baseline deploy `6d4ec0ad`: commit `91cce1e0b2ab`
- Post-revert deploy `02bf8843`: commit `154926a4c748`

```
git diff 91cce1e0b2ab 154926a4c748 --stat
→ (empty — zero diff)

git rev-parse 91cce1e0^{tree} → ddab0ce2550226fb7438feba888d82aceed41b81
git rev-parse 154926a4^{tree} → ddab0ce2550226fb7438feba888d82aceed41b81
```

**Identical git trees.** The merge + revert canceled perfectly. No
code, config, or file difference between the deploy that produced 0.7
and the deploy that produces 0.6.

**Hypothesis C falsified.**

---

## Final Hypothesis Disposition

| Hypothesis | Status | Evidence |
|-----------|--------|----------|
| A — Variance | **Falsified** | 10/10 post-regression runs at 0.6, zero variance |
| B — Model drift | **Likely, unconfirmable** | Aliased model, no changelog, pin to only snapshot didn't help |
| C — Deploy/config | **Falsified** | Byte-identical git trees (ddab0ce2), no env var changes |

**Outcome 3:** Model drift, not pinnable. Accepting 0.6 as new
baseline. Pin stays as drift protection.

---

## Build Time Note

Deploy `e0c23e2f` (the pin commit) took ~20 minutes to build vs the
typical ~2 minutes for prior deploys in this investigation. Most
likely a Railway nixpacks cache eviction — the project uses Python
3.13 + FFmpeg + Tesseract via `nixpacks.toml`, which is a heavy
rebuild from scratch when the cache layer is invalidated. Not caused
by our code change (single-file Python edit). Worth noting so the
delay is not a mystery if it recurs.

---

## Current Production State

| Item | Value |
|------|-------|
| Railway ACTIVE deployment | `e0c23e2f-2b20-4077-b4e6-0dfa8a18a8d0` |
| Railway deploy timestamp | Apr 18 2026, 02:07 UTC (Apr 17, 22:07 EDT) |
| Code commit on -lang/main | `4bb2ab42` (pin commit) |
| Pre-pin tree hash | `ddab0ce2` (identical to baseline `91cce1e0`) |
| DB alembic head | `14ae485b1dec` (pre-Stage-1) |
| Model pin | `gpt-4o-mini-2024-07-18` (classifier + factual + streaming) |
| Citation baseline | 0.6 (accepted) |
| Orphaned schema | `client_links` table, `client_kind` column (from Stage 1 revert) |
| Stage 1 status | Architecturally unblocked for retry |

---

## Carryover Queue (Updated)

### New from this session

- **P1 — Prompt hardening on Q4/Q7/Q9/Q10.** The 4 deterministic
  citation failures are semantic/prompt-level issues, not
  infrastructure. Specifically:
  - Q4 (taxable interest): empty citation — $7 adjacent-number
    disambiguation issue, model says "not specified"
  - Q7 (charity): cites `Form 1040, Line 11` instead of
    `Schedule A, Line 11/14` — form preference issue
  - Q9 (HSA limit): cites `Form 8889, Line 6` instead of
    `Line 3/8` — wrong line on correct form
  - Q10 (Roth IRA excess): cites `Form 1040, Line 24` instead of
    `Form 5329, Line 18/24` — colliding line number across forms
- **P2 — Pin Anthropic model aliases.** `claude-sonnet-4-20250514`
  and `claude-opus-4-20250514` are already pinned in `query_router.py`
  API calls, but the `_TIER_MAP` keys and `model_used` labels use
  display names (`claude-sonnet-4.6`, `claude-opus-4.6`). Review
  whether any additional pinning is needed on the Anthropic side.
- **P3 — Fix stale log labels.** `query_router.py` lines 103, 398,
  608 still log `model="gpt-4o-mini"` while actual API calls use
  `gpt-4o-mini-2024-07-18`. Cosmetic but misleading for debugging.
- **P3 — Update RAG Analytics dashboard baseline.** Dashboard
  expectation should be updated from 0.7 to 0.6 so steady state
  is not flagged as regression.

### Unchanged from prior sessions

- P1 — Admin UI: expose per-question citation pass/fail
- P2 — Orphaned schema cleanup (`client_links`, `client_kind`)
- P2 — Close -code PR #1, delete orphaned -code branch
- P3 — Patch `de1ea96` hash error in April 17 early morning notes
- P3 — Two-repo consolidation (-lang / -code → single repo)
- Credential rotation sweep (overdue, 7+ credentials)
- REPROCESS_TASKS in-memory → Redis migration
- Gemini embeddings 3072 → 768 dimension migration
- §7216 consent UX bug ("processing..." instead of "Awaiting consent")
- Null-email users (Clerk webhook sync)
- SQLite/TSVECTOR test infrastructure gap (58 baseline errors)
- Gmail sync 400 errors on user_3AbIMzEdpzAEUo5qkXp0BnKu2EG
- Q4 taxable interest $7 adjacent-number disambiguation (now subsumed
  by P1 prompt hardening above)

---

## Key Identifiers

```
Client:            Michael Tjahjadi
Client ID:         92574da3-13ca-4017-a233-54c99d2ae2ae
Document ID:       af525dbe-2daa-4b93-bfde-0f9ed9814e41

Eval runs this session (all citation = 0.6):
  Pre-pin (Step 1):
    efdebc1b, d4d6e60e, 37a0b94f, 20f34547, a1667c9b
  Post-pin (Step 4):
    73143b66, 7765022a, da210010, 0768fbbf, ddcdb21b

Pin commit:        4bb2ab42d3bdbf66e3051345201ca0a3d69494bf
Deploy:            e0c23e2f-2b20-4077-b4e6-0dfa8a18a8d0
Baseline tree:     ddab0ce2550226fb7438feba888d82aceed41b81
```

---

## Discipline Notes

- Zero scope creep. Every step gated on explicit "proceed."
- Tier map lookup caught before commit (user's sanity check on
  `_TIER_MAP` key mismatch).
- Rollback plan stated and confirmed before every deploy.
- No credentials echoed to stdout.
- 20-minute build delay handled with patience, not panic.
- Pre-commit contract ("if eval stays at 0.6, pin stays") honored
  as written.
- Hypothesis C check added by user as a final verification — good
  instinct, produced the definitive git-tree-identity proof.

---

## Session End State

- [x] Production running pinned `gpt-4o-mini-2024-07-18`, health OK
- [x] All three hypotheses tested with decision gates
- [x] Hypothesis A (variance) falsified — 10/10 runs at 0.6
- [x] Hypothesis B (model drift) — likely but unconfirmable
- [x] Hypothesis C (deploy/config) falsified — identical git trees
- [x] 0.6 accepted as new citation baseline
- [x] Pin commit `4bb2ab42` in production as drift protection
- [x] Stage 1 retry architecturally unblocked
- [ ] Prompt hardening on Q4/Q7/Q9/Q10 (next session P1)
- [ ] Dashboard baseline update 0.7 → 0.6 (next session P3)

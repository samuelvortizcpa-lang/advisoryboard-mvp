# Session Summary — May 5, 2026 — G5-P1 Ship (Quarterly Estimate Cadence Gate Retrofit)

**HEAD before:** `3af62a9` (Track 2c — client isolation skip)
**HEAD after:** `60bd236` (G5-P1 — cadence gate quarterly estimate + frontend conditional render)
**Branch:** `main` on `samuelvortizcpa-lang/advisoryboard-mvp`
**Commits this session:** 2 (one doc, one feature)

## Outcome

G5 build track opened. Plan doc canon committed to the repo, then G5-P1 shipped end-to-end with smoke verification on Tracy Chen DO. Cadence-gate pattern validated in practice for a known-shipped deliverable before extension to the new kickoff memo deliverable in G5-P2 onward.

| Commit | Description |
|---|---|
| `ced162d` | `docs(g5): add kickoff memo plan canon for G5-P1 prep` (824-line plan doc to `docs/`) |
| `60bd236` | `feat(g5-p1): cadence gate quarterly estimate + frontend conditional render` |

## Commit 1 — Plan doc to repo (`ced162d`)

824-line plan doc copied verbatim from project knowledge to `docs/AdvisoryBoard_G5_KickoffMemo_Plan.md`. md5 byte-identity verified pre-stage (`3853d52ae7ce509920f9788e011d8a1d`). Single explicit-path stage, single commit, no co-authored-by trailer, pre-commit hook green.

Doc-only commit with two purposes: (1) canon lives in the repo for future sessions to `view` directly without dragging from project knowledge, alongside the May 4 hygiene Track 2a/2b audits already in `docs/`; (2) low-risk validation of the mirror pipeline before any code change. Mirror SHA-compare in sync on first poll (~30s). Deploys are no-op for `docs/` content.

## Commit 2 — G5-P1 (`60bd236`)

Two-pass dispatch: read-only audit prompt first, action prompt second.

### Audit findings (informed action prompt)

The audit surfaced one plan-doc bug and three ground-truth confirmations:

1. **File location mismatch.** Plan §3 G5-P1 asserts the function lives in `communication_service.draft_quarterly_estimate_email`. Actual location is `backend/app/services/quarterly_estimate_service.py` — a dedicated service file, not communication_service. Action prompt corrected to target the right file. Plan doc edit deferred to next planning prep session, NOT mid-build.
2. `is_deliverable_enabled` signature `(db, client_id, deliverable_key) -> bool` confirmed at `backend/app/services/cadence_service.py:55`. Matches plan exactly.
3. `SendEmailModal` already destructures `clientId` from props at line 43 — no prop threading needed. Quarterly approach card renders at lines 358-371.
4. `getEnabledDeliverables(clientId)` confirmed exposed via `createCadenceApi(getToken).getEnabledDeliverables(clientId)` at `frontend/lib/api.ts:3221`, returns `{ enabled: DeliverableKey[] }`. G4-P3a shipped this; G5-P1 is its first consumer.

Both `is_deliverable_enabled` and `getEnabledDeliverables` had zero existing call sites pre-G5-P1 — defined and tested but unused. G5-P1 is the first production caller of both, validating the plan's framing of P1 as "cadence-gate pattern proving" before P2-P5 build new surfaces on top.

### Backend changes — `quarterly_estimate_service.py`

- Added import: `from app.services.cadence_service import is_deliverable_enabled` (alphabetically placed between `app.models.user` and `app.services.communication_service`).
- Inserted gate immediately after the client existence check, before the user resolution block:
  ```python
  if not is_deliverable_enabled(db, client_id, "quarterly_memo"):
      raise PermissionError(
          f"quarterly_memo deliverable not enabled for client_id={client_id}"
      )
  ```
- Net: +6 lines added, 0 deleted on the service file.

### Backend tests — new file `test_quarterly_estimate_service.py`

131-line test file mirroring the `test_cadence_service.py` idiom (db fixture from conftest, `make_user`/`make_org`/`make_client` helpers, model imports). Two tests:

- `test_draft_quarterly_estimate_refuses_when_cadence_disabled` — seeds a template with `quarterly_memo` disabled, asserts `PermissionError` raised with `match="quarterly_memo"`.
- `test_draft_quarterly_estimate_succeeds_when_cadence_enabled` — defensive test ensuring the gate isn't accidentally always-blocking. Seeds a template with `quarterly_memo` enabled, asserts no `PermissionError` raised. Catches PermissionError as a fail, ignores any other downstream exception.

The defensive test surfaced an interesting observation on first run: with `quarterly_memo` enabled, `draft_quarterly_estimate_email` ran to completion without raising any exception, suggesting either a global OpenAI mock in `conftest.py` or a fallback path in the function. Test was reshaped from `pytest.raises(Exception)` to a try/except pattern accepting any non-PermissionError outcome. Worth understanding before P3 writes the much heavier `engagement_deliverable_service` test surface — that suite will need explicit OpenAI mocking patterns established. Captured in carry-forwards.

### Frontend changes — `SendEmailModal.tsx`

- Extended `@/lib/api` named-import list to include `createCadenceApi` and `DeliverableKey` (alphabetically maintained).
- Added state: `const [enabledDeliverables, setEnabledDeliverables] = useState<DeliverableKey[]>([])` alongside other useState declarations.
- Added a fetch useEffect placed immediately above the existing escape-key useEffect:
  ```tsx
  useEffect(() => {
    let mounted = true;
    createCadenceApi(getToken)
      .getEnabledDeliverables(clientId)
      .then((res) => { if (mounted) setEnabledDeliverables(res.enabled); })
      .catch(() => { /* fail-safe: leave empty; quarterly card stays hidden */ });
    return () => { mounted = false; };
  }, [clientId, getToken]);
  ```
- Wrapped the quarterly approach card (lines 358-371) in `{enabledDeliverables.includes("quarterly_memo") && (...)}`. Inner JSX preserved exactly; only the conditional wrap added.
- Net: +24 lines added, 1 deleted on the modal.

### Combined commit, not split

Plan §3 G5-P1 specifies "1 commit on main directly." Backend gate and frontend conditional render are two faces of one feature; splitting would create a window where one side gates and the other doesn't. May 4's "two logical commits when surfaces are independent" rule didn't apply here — surfaces are tightly coupled.

## Test baseline transition

| | Before today | After G5-P1 |
|---|---|---|
| Passed | 435 | 437 |
| Failed | 0 | 0 |
| Skipped | 1 | 1 |
| Total tests | 436 | 438 |

Math closed: 435 baseline + 2 new = 437 passed, skipped count unchanged. Expected line `437 passed, 1 skipped, 26 warnings in 28.21s` matched exactly at C1 gate.

Frontend unit (119 passed) and Playwright E2E (9 specs) baselines unchanged — neither was run as part of this commit per scope.

## Deploy verification

Both services confirmed green at `60bd236`:

- **Railway:** Deploy ID `ae5ef3db-c3b2-401f-95d0-5cf8603d0ad5`, status SUCCESS at 2026-05-05 13:19:39 UTC. Backend health endpoint `{"status":"ok"}`. Push completed ~13:19 UTC, deploy fired within seconds — normal webhook latency.
- **Vercel:** Deploy `advisoryboard-mvp-v2-r168v7fdz-samuelvortizcpa-codes-projects.vercel.app`, status Ready/Production, deployed ~13:20 UTC. Frontend serving HTTP/2 200 with fresh date header.

Sequential push timestamps map cleanly to sequential deploy timestamps. No batching, no stuck deploys.

## Manual smoke — Tracy Chen DO (`b9708054-0b27-4041-9e69-93b20f75b1ac`)

Pass on both directions of the cadence toggle:

- **Cadence-disabled state:** `quarterly_memo` toggled off via override on Tracy's cadence. SendEmailModal opens. Approach selection shows three cards (Template / AI Draft / Scratch). Quarterly Estimate card hidden. ✓
- **Cadence-enabled state:** `quarterly_memo` toggled back on. SendEmailModal opens. Four cards visible including Quarterly Estimate. Click proceeds into the existing draft flow normally. ✓

No flicker, no race condition between modal render and async cadence fetch. Either the cadence API responds fast enough that the initial empty `[]` state never paints the card, or the modal's outer transition masks the brief gap.

This is the validation event for the cadence-gate pattern. Same canonical fixture used for the April 29 Gap 2 production smoke, now proven against the gate-on-existing-deliverable path. P2-P5 can build new surfaces on top with confidence the pattern works in practice.

## Discipline observations

- **Two-pass dispatch (audit → action) earned its cost.** The audit caught the plan's file-location bug before any code was written. Without the audit, CC would have grepped `communication_service.py`, found nothing, and either improvised or stopped — either way wasting time. The audit's read-only spot-checks cost ~3 minutes of CC time and prevented a much messier action-prompt iteration loop.
- **Show-body gate before commit caught zero issues — same as May 4.** When the work is small enough and the audit is thorough, the show-body gate is largely confirmatory. Still worth running every time; the value is asymmetric (cheap to do, expensive to skip when something's wrong).
- **CC stopped correctly at the missing-file precondition.** First commit-1 dispatch hit the porcelain gate finding `(empty — clean)` instead of the expected untracked file, stopped, and reported. Manual file placement, then re-dispatched the same prompt verbatim. The "stop and report rather than improvise" discipline held.
- **Mirror SHA-compare verification on both commits.** First-poll IN SYNC on both pushes within the 30-second window. 12 successful non-trivial pushes since the May 2-3 reconciliation. Pipeline still rock-solid. Never relied on "Everything up-to-date" from manual code-mirror push.
- **No `git add .` / `-A`.** All staging used explicit paths.
- **No co-authored-by trailers.** Both commits clean.
- **Pre-commit hook (`tsc --noEmit`) ran on both commits and passed.**
- **Targeted backend test run after backend changes** caught the test-2 over-strict assertion before commit (the `pytest.raises(Exception) DID NOT RAISE` failure). Fixed in-place, re-ran, both tests green. The cheap confidence check earned its cost.

## Mirror pipeline status

12 successful non-trivial pushes since the May 2-3 reconciliation. Considered rock-solid. Continue using `git fetch code-mirror && git log <branch> -1 --format="%H"` SHA compare as the verification, never "Everything up-to-date" from a manual push to code-mirror.

## Repo state at session close

- Branch: `main`
- HEAD: `60bd236`
- Working tree: clean
- Origin: in sync
- Mirror: in sync
- Railway: `{"status":"ok"}` (deploy `ae5ef3db`)
- Vercel: HTTP/2 200 (deploy `advisoryboard-mvp-v2-r168v7fdz`)
- Backend tests: 437 passed, 1 skipped, 0 failed
- Frontend unit: 119 passed (unchanged)
- Playwright E2E: 9 specs (unchanged, not run this session)

## Carry-forwards

### Plan doc location bug — `AdvisoryBoard_G5_KickoffMemo_Plan.md` §3 G5-P1

Plan asserts `communication_service.draft_quarterly_estimate_email`; actual is `quarterly_estimate_service.draft_quarterly_estimate_email`. Audit caught it; action prompt targeted the correct file. **Plan doc edit deferred to next planning prep session, NOT mid-build, per dispatch rules.** Whoever opens the next planning prep should edit the plan doc to reflect actual file structure before P2 dispatch.

### `initialQuarterly` bypass risk

Frontend gates the approach-card visibility but does NOT gate the `initialQuarterly`-prop entry path. If someone navigates to a deep link that pre-sets `initialQuarterly` on a cadence-disabled client, the modal opens directly into the quarterly draft flow, skipping the card-hidden state. Backend gate is the source of truth — Generate call would 403 — so this is a UX wart not a security/data hole. Worth a small follow-up to either (a) gate the `initialQuarterly` path with the same `enabledDeliverables.includes` check before initial render, or (b) refuse to set the prop from upstream callers when cadence-disabled.

Not in scope for G5-P1 (plan literal scope is "approach card conditional render"). Capture as a P5 or post-smoke follow-up — likely cheap to fix when the same conditional render lands for kickoff memo's button visibility.

### OpenAI mock observation for P3 prep

Test `test_draft_quarterly_estimate_succeeds_when_cadence_enabled` ran the function to completion without any exception when the gate passed, suggesting either a global OpenAI mock in `conftest.py` or a fallback in `draft_quarterly_estimate_email` itself. Need to understand the mock posture before P3 writes ~10-12 service tests for `engagement_deliverable_service` — those tests will exercise the OpenAI client directly via the kickoff memo handler's prompt builder. P3 dispatch should include an audit step to inspect `conftest.py` and any session-scoped fixtures that might be patching `AsyncOpenAI`.

### Long-tail product gaps (deferred, no change from May 4)

- **No firm-org creation flow in product UI.** Surfaces during multi-employee onboarding. G5+ scope item.
- **`enabled_count` not on `CadenceTemplateSummary`.** Backend hygiene if pain warrants; otherwise defer.

Neither touched G5-P1; neither is near-term action.

## Next-up candidate: G5-P2 — Context assembler `engagement_kickoff` purpose

Per plan §3 G5-P2:

- **Type:** Backend-only. Single-file change to `context_assembler` service.
- **Scope:** Add `engagement_kickoff` to the assembler's purpose table with budget=6,000 and priority order: strategies (recommended) > implementation tasks (client-facing) > journal (last 30 days) > financials (current + prior year) > open action items > prior comms. Plus 3 new service tests.
- **Effort:** ~45 min.
- **Acceptance:** 3 new tests pass. Total: 440 passed, 1 skipped, 0 failed.
- **No design questions outstanding.** Straight build dispatch when ready.

## Locked-in design decisions (carried forward, no changes from prior session)

All cadence canon from G4-P4a/P4b/P4c/P4d still in force. New conventions added by G5-P1:

- **Cadence-gate pattern in production:** `is_deliverable_enabled(db, client_id, "<key>")` raises `PermissionError(f"<key> deliverable not enabled for client_id={client_id}")` when disabled. Fires after client existence validation, before any other work. Mirrored on the frontend with `createCadenceApi(getToken).getEnabledDeliverables(clientId)` returning `{ enabled: DeliverableKey[] }` to drive UI conditional rendering. This is the canonical pattern for all deliverable gating going forward — kickoff memo (G5-P5) will use the same shape, P3 will encode it as `engagement_deliverable_service.draft_deliverable`'s top-of-function guard.
- **`PermissionError` exception taxonomy confirmed in production code paths,** not just service tests. Action prompt's gate raises `PermissionError`, matching the plan's locked-in §2.7 convention (cadence-disabled = PermissionError; invalid input = ValueError; missing references = LookupError).

## Commit summary

```
60bd236 feat(g5-p1): cadence gate quarterly estimate + frontend conditional render
ced162d docs(g5): add kickoff memo plan canon for G5-P1 prep
3af62a9 test(client_isolation): skip when backend not running (Track 2c)  ← previous HEAD at session start
```

Two clean commits in a single session across the G5 track open. No reverts, no force-pushes, no co-authored-by trailers, no `git add .` usage, no failed deploys.

---

*End of session summary. Next: G5-P2 — context assembler `engagement_kickoff` purpose. ~45 min build, no planning prep needed.*

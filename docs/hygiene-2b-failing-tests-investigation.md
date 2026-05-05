# Hygiene 2b — Pre-existing Failing Tests Investigation

**Investigated at HEAD:** 87987cb
**Date:** 2026-05-04
**Scope:** 4 pre-existing failing backend tests (3 voucher_detection + 1 client_isolation).
**Pass type:** Read-only investigation. No fixes attempted.

## Summary

3 of 4 failures are **FIXTURE DRIFT** — the voucher detection function was tightened from a 1-pattern threshold to a 2-pattern threshold (commit `b2f93a2`, Apr 19) but the 3 tests added in `7800c8b` (Apr 10) were never updated. The remaining failure is an **ENV ISSUE** — the client isolation test is an integration test that requires a running local backend on port 8000.

Orchestrator resolutions (2026-05-04): T1 — self-contained skip on connection failure; T2/T3 — add second corroborating signal to each fixture; T4 — delete the test (lockbox detection was intentionally moved to the continuation pass, and that path already has coverage). Fix execution will be in a separate Hygiene 2c session.

## Per-test diagnosis

### T1: `tests/test_client_isolation.py::test_client_isolation`

**Last test change:** `22ecbe8` (2026-04-23) — config rename (.env to .env.local), no logic change
**Last module change:** N/A — test hits live HTTP endpoints, not a specific module
**Failure:** `httpx.ConnectError: [Errno 61] Connection refused` connecting to `http://localhost:8000`
**Classification:** ENV ISSUE
**Rationale:** This is a full integration test that creates an `httpx.Client(base_url="http://localhost:8000")` and issues real HTTP requests against the backend API. It requires a running backend with `TEST_MODE=true` in `.env.local`. The pytest suite runs without a backend server, so it always fails. The test's own docstring says "Requires TEST_MODE=true in backend/.env.local" — it was designed for manual/CI execution with a live server, not for the unit test suite.
**Resolution:** Self-contained skip-on-connection-failure inside the test wrapper. Add an httpx GET against `/health` with a 2-second timeout in a try/except; on `ConnectError` or `TimeoutException`, call `pytest.skip(...)` with a reason mentioning the BASE_URL. NOT a pytest.ini marker change — that would silently affect `test_reprocess_tasks_db.py` which already carries `pytestmark = pytest.mark.integration`.

### T2: `tests/test_voucher_detection.py::test_voucher_without_return_year`

**Last test change:** `7800c8b` (2026-04-10) — test was added in this commit
**Last module change:** `b2f93a2` (2026-04-19) — tightened threshold from `any()` to `sum() >= 2`
**Failure:** `assert False is True` — `detect_voucher_chunk()` returns `is_voucher: False`
**Classification:** FIXTURE DRIFT
**Rationale:** The test input is `"Payment Voucher\nEstimated tax for tax year 2026\nAmount: $5,000\n"`. This matches only 1 pattern (`payment\s+voucher`). The phrase "Estimated tax for tax year" does NOT match pattern 1 (`estimated\s+tax\s+(payment|voucher)`) because the word after "tax" is "for", not "payment"/"voucher". When the test was written (Apr 10), the threshold was `>= 1` pattern. Commit `b2f93a2` (Apr 19) raised it to `>= 2` but didn't update this test.
**Resolution:** Update the test fixture to change "Estimated tax for tax year 2026" → "Estimated tax payment for tax year 2026". This makes the input match both `payment\s+voucher` AND `estimated\s+tax\s+(payment|voucher)`, satisfying the >= 2 threshold.

### T3: `tests/test_voucher_detection.py::test_calendar_year_due_pattern_flagged`

**Last test change:** `7800c8b` (2026-04-10) — test was added in this commit
**Last module change:** `b2f93a2` (2026-04-19) — same tightening as T2
**Failure:** `assert False is True` — `detect_voucher_chunk()` returns `is_voucher: False`
**Classification:** FIXTURE DRIFT
**Rationale:** The test input is `"Calendar year—Due April 15, 2025\nAmount of estimated tax: $8,000\n"`. This matches only 1 pattern (`calendar\s+year.{0,5}due\s`). Same root cause as T2 — threshold raised to `>= 2` without updating the test fixture.
**Resolution:** Update the test fixture to add a "Form 1040-ES" line. This makes the input match both `calendar\s+year.{0,5}due\s` AND `form\s*1040-?es`, satisfying the >= 2 threshold.

### T4: `tests/test_voucher_detection.py::test_irs_lockbox_routing_flagged`

**Last test change:** `7800c8b` (2026-04-10) — test was added in this commit
**Last module change:** `b2f93a2` (2026-04-19) — removed IRS lockbox pattern AND raised threshold
**Failure:** `assert False is True` — `detect_voucher_chunk()` returns `is_voucher: False`
**Classification:** FIXTURE DRIFT
**Rationale:** The test input contains `"3 3 4 0 0 0 3"` (IRS lockbox routing number) and `"United States Treasury"`. Commit `b2f93a2` explicitly removed the lockbox digit pattern (`3\s*3\s*4\s*0\s*0\s*0\s*3`) from `_VOUCHER_PATTERNS` because it was causing false positives on Michael Tjahjadi's refund account number. The remaining text matches zero `_VOUCHER_PATTERNS` entries — "United States Treasury" is only in `_VOUCHER_CONTINUATION_PATTERNS`, not the primary list. So the test now matches 0 of 4 patterns (needs 2).
**Resolution:** DELETE the test. The lockbox digit pattern was intentionally removed from `_VOUCHER_PATTERNS` in `b2f93a2` because it false-positived on real refund account numbers. The continuation pass (`flag_voucher_continuations` + `_VOUCHER_CONTINUATION_PATTERNS`) handles IRS routing language for adjacent chunks, and that path is already covered by `test_continuation_chunk_flagged`. A rewritten continuation-flavored version would be redundant.

## Cross-cutting observations

- All 3 voucher_detection failures share the same root cause: commit `b2f93a2` (Apr 19) raised the pattern-match threshold from 1 to 2 and removed the lockbox pattern, but only updated the production code, not the tests. The commit message mentions "motivated by misclassification of pages 5 and 6 of Michael Tjahjadi's 2024 tax return" — the tightening was intentional and correct.
- The client_isolation failure is completely independent — it's an infrastructure issue (no running server), not a logic issue.
- The 5 passing voucher tests (`test_real_voucher_chunk_flagged`, `test_1040_page_mentioning_estimated_tax_not_flagged`, `test_form_1040es_without_future_year_not_flagged`, `test_schedule_a_not_flagged`, `test_voucher_picks_max_future_year`, `test_continuation_chunk_flagged`) all pass because their fixtures either contain 2+ corroborating signals or correctly assert `is_voucher: False`.

## Resolutions (orchestrator-decided, 2026-05-04)

1. **T4 — DELETE.** Lockbox detection was deliberately removed from primary patterns in `b2f93a2` due to false positives on real account numbers. Continuation coverage exists via `test_continuation_chunk_flagged`. No replacement test needed.

2. **T1 — Self-contained skip.** Add try/except around an httpx health-check at the top of `test_client_isolation()`; call `pytest.skip(...)` on `ConnectError`/`TimeoutException`. Not a pytest.ini-level marker change, because `test_reprocess_tasks_db.py` already carries `pytestmark = pytest.mark.integration` (currently unregistered, runs harmlessly) and a global `-m "not integration"` filter would silently skip that whole module.

Fix execution scheduled as Hygiene 2c — separate session, separate commit(s).

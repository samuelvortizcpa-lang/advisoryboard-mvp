# Send-Path Remediation Plan

**Status:** Planning. Not a build prompt.
**Prereq:** None. Working tree clean at `99fb868`. Backend tests 460 passed + 1 skipped, frontend unit 132 passed.
**Scope:** v1 milestone remediation following the May 9, 2026 smoke event. Fixes the four fan-out triggers (FT-1 through FT-4) surfaced at smoke and unblocks a re-smoke that resolves the v1 ship-blocked state. **Does NOT include:** Gap 1 (chat command, deferred indefinitely until this lands), 2B (Resend webhook for delivered/bounced — explicitly named as the immediate post-v1 dispatch), or any of Gap 5/6/7/8.
**Reference state:** `origin/main` HEAD `99fb868` (G5-P5 — kickoff memo modal + header trigger). Mirror in sync. Vercel + Railway green. Working tree clean.

This doc contains seven artifacts: §1 architecture and copy decisions, §2 schema and status semantics, §3 build sequence, §4 test surface, §5 open questions and parking lot, §6 FT sequencing matrix, §7 re-smoke criteria.

---

## §1 — Architecture and copy decisions

### v1 send infrastructure: Resend (Q1=A, settled)

The v1 deliverable surface sends through Resend's transactional API. Gmail OAuth is not coupled to outbound deliverables in v1; it remains in Settings → Email Sync as an inbound-sync surface only. The "Send via Gmail" copy that smoke surfaced as misleading reflected an architectural intention that was never wired — the actual code path has always been Resend. v1 reconciles the copy to the reality rather than reconciling the reality to the copy.

**Why this is the right v1 answer (carry-forward to plan-doc readers):**

- The trust model permits a Callwen-branded sender. The deliverable's correctness comes from the system telling the truth about what happened, not from which provider sent the email.
- Gmail OAuth as the outbound path is currently blocked by an unstarted Google app verification process (the smoke surfaced "Google hasn't verified this app" when the OAuth flow was tested).
- No timeline pressure forces the longer path to be attempted in parallel.
- The schema and service shapes in this plan stay friendly to a future Gmail OAuth migration — `client_communications` already has `metadata_` JSONB that can hold a `gmail_message_id` post-migration, and the `record_deliverable_sent` service signature stays generic over provider.

**Meta-observation flagged at the planning session:** The North Star and North Star Integration Architecture docs scope entirely to the chat/query surface (Modes 1-4). Neither addresses Layer 2's deliverable architecture. This plan is the canonical reference for the deliverable send-path architecture until either (a) the North Star is extended with a Layer 2 section, or (b) a separate Layer 2 architecture doc absorbs it. See §5 item 5.

### Copy changes

Three copy strings change in v1:

1. **`KickoffMemoDraftModal.tsx` send button** — `"Send via Gmail"` → `"Send Email"`. The button's behavior doesn't change; only the label.
2. **`KickoffMemoDraftModal.tsx` failure toast** — replaces today's success-toast-on-200 lie. New copy: `"Failed to send. Please try again or check the recipient address."` Generic enough to handle both Resend API errors and unexpected exceptions.
3. **Settings → Email Sync, "Connect Gmail" button caption** — add caption beneath the button: `"Connect Gmail to sync inbound client emails into the timeline. Outbound deliverables send through Callwen's email infrastructure."` (Exact placement to be confirmed during R-P3 audit; the precise wording may be tightened.)

### Modal states

The kickoff memo modal already implements the loading / editable / error state machine per G5-P5. v1 adds explicit semantics to the *post-Send* states:

- **Sending.** Send button disabled (`sending` state already exists per G5-P5). Spinner inline on the button.
- **Success.** Existing G5-P5 behavior holds: success toast → 1.2s delay → `onClose()`. (The smoke noted modal didn't auto-close; that's a separate fix-later nit, not part of FT-1.)
- **Failure.** Failure toast fires; modal stays open with current draft contents preserved; CPA can edit and retry by hitting Send again. The G5-P5 modal-stays-open-on-error convention already exists; no new component scope.

The toast pattern itself (`useState<{message, type} | null>`, panel-absolute-positioned div) is unchanged; only the conditions firing it change.

### Scope boundary on this section

Out of scope for §1:
- Modal auto-close fix-later nit (the G5-P5 reference to `gmail_message_id` and the auto-close timing observation). Both go to a hygiene pass.
- After-the-moment failure surfacing (timeline badge, banner, etc.). Bundled with the post-v1 2B dispatch per Q3 settling.
- Idempotency at send boundary (the smoke produced two send attempts, two rows). The frontend `sending`-state guard already disables the button while in-flight; backend-side dedup is a separate concern not v1-blocking. See §5 item 4.

### Reconciliation note (added post-R-P3 ship)

Two §1 framings diverged from R-P3's actual execution and are reconciled here for plan-doc readers carrying this forward:

1. **R-P3 frontend scope collapsed at audit.** §1's Modal states subsection above frames R-P3 as adding explicit post-Send-state semantics on top of G5-P5's foundation. R-P3 audit revealed G5-P5's catch branch was already correctly wired for the 502 failure path — the existing `try/catch` around `sendKickoffMemo(...)` plus the `useState<{message,type} | null>` toast pattern already routed non-2xx into a failure-toast / modal-stays-open shape. R-P2's backend rewrite was the load-bearing fix. R-P3 therefore shipped as a copy-only change (button label, failure-toast literal, Email Sync caption) plus a regression-guard test (`renders failure toast and keeps modal open on send rejection`). Treat the §1 Modal states description as the *design intent* the team would have implemented had G5-P5 not already covered it — not as net-new work R-P3 performed.

2. **Failure-toast literal lineage.** §1's Copy changes subsection above specifies `"Failed to send. Please try again or check the recipient address."` G5-P5 had already coded the shorter `"Failed to send. Please try again."` This divergence was identified at R-P3 audit; R-P3 shipped the longer §1-locked literal, so the codebase now matches the plan-doc as written. The historical mismatch is closed at the code layer; this note exists only for traceability.

---

## §2 — Schema and status semantics

### v1 status semantics (Q2=2A, settled)

The synchronous send-call result is the source of truth. The write happens *after* the send call returns, with the result baked in. No `pending` state.

| State | When written | Required fields | Semantics |
|---|---|---|---|
| `sent` | Synchronously, after Resend returns success | `resend_message_id` populated, `sent_at` populated, `metadata_` may include provider response details | Resend accepted the API call. NB: this does not mean the recipient's mail server accepted delivery — that observability lands with 2B. |
| `failed` | Synchronously, after Resend returns error or call throws | `resend_message_id = NULL`, `sent_at = NULL`, `metadata_` populated with error envelope | Send call did not succeed. The CPA was informed via toast; the row exists for audit. |

`sent_at` is populated only on `sent`. A `failed` row's `sent_at` stays NULL — the column reflects "when delivery succeeded," not "when an attempt was made." Attempt timestamp goes in `metadata_.attempted_at` (see error envelope below).

### Error envelope (`metadata_` JSONB shape on `failed` rows)

```json
{
  "send_error": {
    "attempted_at": "2026-05-09T20:46:29.123Z",
    "provider": "resend",
    "kind": "api_error" | "exception" | "timeout",
    "status_code": 422,
    "message": "Recipient address invalid",
    "raw": { ... }
  }
}
```

- `kind=api_error`: Resend returned a non-2xx; `status_code` and `message` populated from the response.
- `kind=exception`: send call threw; `message` populated from the exception, `status_code` may be omitted.
- `kind=timeout`: send call exceeded its budget; the timeout policy is part of the Resend wrapper module's existing config (audit confirms during R-P2).
- `raw` carries the provider response body, structured if available, for debugging. Bounded in size.

The error envelope is a Pydantic model on the service-layer side (typed, validated) and serializes to JSONB on the way to the DB. The `metadata_` column may already carry other unrelated fields; the error envelope nests under `send_error` to avoid namespace collisions.

### Migration shape

A single Alembic migration in R-P2:

1. **`client_communications.status`** — extend the allowed values. Today only `'sent'` is observed; `'failed'` is added. Implementation depends on whether the column is currently a CHECK-constrained string (most likely) or a Postgres ENUM type (less likely given the smoke summary's "DB is Supabase Postgres" finding and the team's general Pydantic-over-enum pattern). Audit step in R-P2 confirms the actual constraint shape before the migration is written.
2. **No new columns added.** `metadata_` already exists as JSONB and can carry the error envelope. `resend_message_id` already exists and is nullable. `sent_at` already exists and is nullable. The schema changes are minimal.

The migration is reversible (the `down_revision` path drops the `'failed'` value back to `'sent'`-only, with a safety check that no rows currently have `status='failed'` — if any exist, the downgrade fails loudly rather than silently coercing). This is standard Alembic discipline.

### Service-layer rewrite (write-after-send pattern)

`engagement_deliverable_service.send_deliverable` (or whatever the equivalent function name is — confirm at R-P2 audit) currently:
1. Inserts a `client_communications` row with `status='sent'`.
2. Calls Resend.
3. Returns 200 regardless.

After R-P2:
1. Calls Resend (with its existing wrapper / error handling).
2. On success: inserts `client_communications` row with `status='sent'`, `resend_message_id` populated, `sent_at` populated.
3. On failure: inserts `client_communications` row with `status='failed'`, error envelope in `metadata_.send_error`. Re-raises a typed exception that the API layer catches and maps to 502.
4. Returns the row ID on success only.

The journal-entry write (per G5-P3 carry-forward) should be conditional on the success branch — a journal entry that says "Engagement kickoff memo sent to Tracy Chen DO" should not be written on a failed send. R-P2 audit confirms current journal-write placement and adjusts.

### API contract (Q3 sub-question, settled: pattern (a))

`POST /api/clients/{id}/deliverables/kickoff-memo/send`:

- **200**: send succeeded. Body: `{client_communication_id: str}` (existing shape).
- **502**: send failed. Mirrors the existing G5-P4 convention for upstream provider failures (`OpenAI exception → 502 with logger.exception`). `logger.exception` captures the exception chain server-side. Body: standard error shape (message, no internal stack details). The `client_communications` row with `status='failed'` was written; the row ID is *not* returned in the 502 body for v1 — the toast handles the user-facing surface, and audit access goes through the DB or a future timeline badge.
- **422 / 403 / 404**: unchanged input-validation and auth-gate behavior.

Frontend's `KickoffMemoDraftModal` catches non-2xx from the existing fetch helper and routes to the failure-toast path. No new frontend error-handling surface needed — the modal already has an error state shape.

---

## §3 — Build sequence

Five phases. R-P0 is optional; R-P1 through R-P3 are sequential build phases; the final phase is the re-smoke event (not a build session).

Each build phase follows the audit→action two-pass dispatch pattern that became canonical through G4 and G5: a read-only audit prompt establishes file paths, line numbers, conventions, and any plan-doc divergences before the build prompt is issued. Show-body gates between sub-phases.

### R-P0 — Plan-doc hygiene *(optional pre-work, ~30 minutes)*

Five+ accumulated plan-doc bugs through G5 + smoke. Single hygiene dispatch fixing all in one pass. Doc commits only; zero code.

**Bugs to fix:**

1. G5-P1: plan §3 G5-P1 says `communication_service.draft_quarterly_estimate_email`; actual is `quarterly_estimate_service.draft_quarterly_estimate_email`.
2. G5-P2: plan §3 G5-P2 says `context_assembler_service`; actual is `context_assembler.py`.
3. G5-P4: plan §3 G5-P4 says cross-org returns 404; actual is 403. Plan §4.2 test name also wrong.
4. G5-P5: plan §1 references `isDeliverableEnabled(client_id, "kickoff_memo")` as if it exists; it doesn't. Real pattern is `getEnabledDeliverables` + `Array.includes`.
5. G5-P5 ship summary: references `gmail_message_id` as a verification field; actual schema column is `resend_message_id`.
6. G5-P3 (or wherever): plan §4.4 references journal table as `journal_entries`; actual is `client_journal_entries`.
7. North Star scope note: implies Railway Postgres for production DB; actual is Supabase Postgres. Architectural reconciliation deferred to §5 item 5; the scope-note correction is the v1-relevant slice.

**Effort:** ~30 minutes. Single CC dispatch with explicit file/line targets and replacement strings. One commit, e.g., `docs: hygiene pass — plan-doc location bugs across G5 + scope note correction`.

**Why optional:** plan-doc bugs don't block R-P1's CC dispatch. CC can navigate plan-doc inaccuracies if it has to. But fixing these first means the R-P1 prompt is cleaner and downstream prompts reference correct sections.

### R-P1 — Service-layer narrow fixes (FT-2 + FT-3)

**Type:** Backend, service-layer only. No schema migrations, no API contract changes, no frontend changes.

**Scope:** Fix the two service-layer bugs in `engagement_deliverable_service.draft_deliverable`'s reference assembly path:

- **FT-2 — Empty-ID strategy reference inconsistency.** Per G5-P4 carry-forward fix candidate (1): move the empty-ID filter inside `_extract_strategies_and_tasks` (or wherever the typed-filter currently sits) so the warnings check sees the post-filter list. This eliminates the `references.strategies == []` AND `warnings == []` simultaneously inconsistency. Decision deferred from G5-P4: confirm at R-P1 audit whether candidate (1), (2), or (3) is actually the right shape — the audit should pull `_fetch_strategy_status`'s actual return shape and decide.
- **FT-3 — Duplicate task in chip list.** Investigate `_fetch_action_items` (or whatever the task-pull path is named — confirm at audit). Either de-duplication is missing or a join is fanning out somewhere. Likely a `DISTINCT` clause or a `SELECT ... GROUP BY task_id` adjustment, possibly a `set()`-based dedup in Python if the shape is already deduplicated upstream and only the in-Python list is duplicating.

**Audit step (Gate 1 of CC dispatch):**

- View `engagement_deliverable_service.py` — locate `_fetch_strategy_status`, `_extract_strategies_and_tasks`, `_fetch_action_items` (names approximate; confirm).
- For FT-2: read the typed filter and the warnings-check side-by-side. Identify the seam. Decide between candidates (1) / (2) / (3) — locked for build.
- For FT-3: read the task-pull path. Identify whether duplication is at the SQL layer or the in-Python aggregation layer.
- Surface any plan-doc divergences (which become R-P0 candidates if R-P0 hasn't run yet).

**Action step (Gate 2):**

- Apply the FT-2 fix per the locked candidate.
- Apply the FT-3 dedup.
- Run the existing service test suite (`test_engagement_deliverable_service.py`) — should pass unchanged.
- Add or update tests per §4.

**Effort:** ~1-2 hours. Single dispatch, possibly two commits if FT-2 and FT-3 fix surfaces are independent enough that splitting blame is useful (commit 1: `fix(g5): strategy reference filter consistency`; commit 2: `fix(g5): dedup tasks in kickoff memo handler`). Orchestrator's call at audit time.

**Acceptance:** backend tests baseline 460 → ~462-464 (small bump for FT-2 and FT-3 regression-guards). All existing tests continue to pass. No frontend changes; no Vercel deploy expected.

### R-P2 — FT-1 backend (schema + service rewrite + API contract)

**Type:** Backend, schema-touching. The architecturally load-bearing phase.

**Scope:** All backend work for the truthfulness fix:

1. **Alembic migration:** extend `client_communications.status` allowed values to include `'failed'`. Reversible. Audit confirms whether the current constraint is CHECK-string or ENUM-type.
2. **Service-layer rewrite:** `engagement_deliverable_service.send_deliverable` follows the write-after-send pattern. Resend wrapper call first, then row insert with the right status and metadata. Typed exception on failure that the API layer catches.
3. **Resend wrapper module audit:** read whatever the existing Resend client wrapper is (likely `email_service.py`, `resend_client.py`, or similar — name TBD at audit). Confirm its current behavior on send-success and send-error. If the wrapper currently swallows errors silently (returning `None` on failure rather than raising), the wrapper itself needs a small fix to raise typed exceptions. R-P2 audit decides whether the wrapper change is in-scope or whether the service layer wraps-and-translates around the existing surface.
4. **API contract:** `POST /api/clients/{id}/deliverables/kickoff-memo/send` returns 502 on send failure (per G5-P4 error-mapping convention, `logger.exception`). 200 on success unchanged.
5. **Journal-entry placement:** confirm the journal write fires only on the success branch, not on failed sends.

**Audit step (Gate 1):**

- View `engagement_deliverable_service.py` — `send_deliverable` function in full.
- View the Resend wrapper module — confirm its name and surface.
- View the current Alembic migration history to confirm the `client_communications.status` constraint shape.
- View `backend/app/api/deliverables.py` — confirm current error mapping per G5-P4 convention.
- Surface any plan-doc divergences.

**Action step (Gate 2):**

- Write the Alembic migration. Run it locally; confirm it applies and reverses cleanly.
- Rewrite `send_deliverable` per the service-layer plan above. Use the typed `SendError` envelope (or similar) to carry the failure metadata.
- Update API endpoint to catch the typed exception and map to 502 with `logger.exception`.
- Add or update service-level tests per §4.
- Update `test_deliverables_api.py` to cover the 502 path.

**Effort:** ~3-4 hours. Largest phase. Single commit for backend-only change, e.g., `feat(remediation-r2): truthful send-path semantics`.

**Acceptance:** Alembic migration applies cleanly to local dev DB and to production at deploy. Backend tests baseline ~462-464 → ~470-475 (bump for new send-success / send-failure / journal-conditional / 502-API tests). All existing tests continue to pass. Railway deploy succeeds; Vercel no-op.

### R-P3 — FT-1 frontend + FT-4 copy

**Type:** Frontend-only. The user-facing surface for the truthfulness fix plus the FT-4 copy reconciliation.

**Scope:**

1. **`KickoffMemoDraftModal.tsx` failure-path wiring:** the existing `try/catch` around `sendKickoffMemo(...)` already exists (per G5-P5 ship summary's "error toast → modal stays open" convention). Confirm at audit that 502 maps cleanly into the catch branch — most fetch helpers route non-2xx into rejected promises by default.
2. **Failure toast copy:** the new string per §1.
3. **Send button copy:** "Send via Gmail" → "Send Email".
4. **Email Sync surface caption:** add the inbound-only clarifying caption beneath "Connect Gmail" button.
5. **Component tests:** update `KickoffMemoDraftModal.test.tsx` to cover the failure-path render (toast appears, modal stays open, send button re-enabled for retry).

**Audit step (Gate 1):**

- View `KickoffMemoDraftModal.tsx` — confirm the existing send-error path. View the existing toast pattern.
- View `frontend/lib/api.ts` — confirm `createDeliverablesApi(...)` and the `sendKickoffMemo` method shape. Confirm how non-2xx is propagated (whether the `boundFetch` helper already throws on non-2xx — most do).
- Locate the Email Sync settings surface — `frontend/app/dashboard/settings/integrations/page.tsx`. The `email-sync` URL path redirects to this file. Audit confirms exact path and the "Connect Gmail" button location.

**Action step (Gate 2):**

- Update modal failure-path logic and toast copy.
- Update send button copy.
- Add inbound-only caption to Email Sync surface.
- Update component tests per §4.

**Effort:** ~2 hours. Single commit, e.g., `feat(remediation-r3): truthful failure surfacing + copy reconciliation`.

**Acceptance:** frontend unit tests baseline 132 → ~134-136. All existing tests pass. Vercel deploy succeeds.

### Re-smoke event

Manual end-to-end exercise of the kickoff memo deliverable, mirroring the May 9 smoke checklist. Not a build session. See §7 for criteria.

---

## §4 — Test surface

### R-P1 (FT-2 + FT-3) backend coverage

**Service-level (`test_engagement_deliverable_service.py`):**

- **FT-2 regression:** `test_draft_kickoff_memo_strategy_references_round_trip_with_recommended_strategies` — seed a `recommended` strategy with a populated `id`, assert `references.strategies` is non-empty AND `warnings` is empty. Then explicitly seed an empty-ID case (whatever the production failure mode looks like — likely a missing `client_strategy_status` join) and assert post-fix behavior: either the strategy is captured with a stable ID or the warnings field surfaces the inconsistency. The exact shape depends on which fix candidate (1 / 2 / 3) is locked at audit.
- **FT-3 regression:** `test_draft_kickoff_memo_no_duplicate_tasks` — seed a strategy with multiple implementation tasks linked to it, assert the modal-facing tasks list contains each task exactly once.

**No API or frontend tests required for R-P1** — the bugs are confined to the service layer; API tests are thin contract-shape verification per the G5-P4 settled coverage philosophy.

### R-P2 (FT-1 backend) coverage

**Service-level (`test_engagement_deliverable_service.py`):**

- `test_send_deliverable_writes_sent_row_on_resend_success` — Resend mock returns success; assert `client_communications` row written with `status='sent'`, `resend_message_id` populated, `sent_at` populated, `metadata_.send_error` not present. Journal entry written.
- `test_send_deliverable_writes_failed_row_on_resend_api_error` — Resend mock returns 4xx/5xx; assert row written with `status='failed'`, `resend_message_id=NULL`, `sent_at=NULL`, `metadata_.send_error.kind='api_error'` populated. **Journal entry NOT written.** Service raises typed exception.
- `test_send_deliverable_writes_failed_row_on_resend_exception` — Resend mock raises; same assertion shape with `metadata_.send_error.kind='exception'`. Service raises typed exception.
- `test_send_deliverable_does_not_write_journal_entry_on_failure` — explicit assertion that journal is untouched on failure. Defense in depth.

**API-level (`test_deliverables_api.py`):**

- `test_send_kickoff_memo_502_on_send_failure` — patches the service-layer to raise the typed send exception; asserts 502 response, asserts `logger.exception` was called.
- Existing 200 happy-path test continues to pass with the new shape; possibly tightens assertion to verify `resend_message_id` populated in the persisted row.

**Migration test (optional, depending on existing migration test discipline):**

- If the project has an Alembic migration test pattern, add one that confirms the `status` constraint accepts `'failed'` post-migration and the downgrade rejects when `'failed'` rows exist.

### R-P3 (FT-1 frontend + FT-4) coverage

**Component-level (`KickoffMemoDraftModal.test.tsx`):**

- `renders failure state on send rejection` — mock `sendKickoffMemo` to reject; assert failure toast renders with the new copy, modal stays open, send button is re-enabled (`sending` state cleared).
- `renders correct send button copy` — assert button text is `"Send Email"` not `"Send via Gmail"`. Trivial but locks the regression.

**No additional Email Sync component tests** unless the caption addition surfaces a structural change in that component. Likely a 1-line text addition; no new tests required.

### Re-smoke as the integration test

The plan deliberately does not invest in Playwright E2E coverage for the send path. The re-smoke event (§7) is the integration test for v1 — it exercises the full path against real Resend, real DB, real frontend, with a deliberately-invalid recipient as the negative-path control.

### Coverage philosophy carry-forward

Mirrors G4 and G5's settled coverage philosophy:

- Service-level tests are the load-bearing layer — concentrated coverage of the truthfulness logic.
- API tests are thin contract-shape verification.
- Component tests are render-gate verification.
- E2E (Playwright) deferred until smoke shows it's needed.

---

## §5 — Open questions / parking lot

Decisions deferred from this plan, with explicit rationale.

### 1. The 2B dispatch (Resend webhook for delivered/bounced)

**Status:** Explicitly named. Post-v1.

**Scope:** Resend webhook endpoint with signature verification, idempotency on duplicate fires, status transitions to `delivered` and `bounced`. Schema change extends `client_communications.status` to accept those values. Adds `webhook_received_at` timestamp column.

**Effort estimate:** ~1-2 hours. Single phase, single dispatch.

**Migration shape from 2A:** purely additive. The status constraint extension is a one-line update. The webhook endpoint is new but doesn't touch the synchronous send path. Pre-2B `sent` rows never transition to `delivered`/`bounced`, which is acceptable as a "pre-observability epoch" — no backfill required.

**Trigger condition for kickoff:** post-re-smoke, before any new deliverable type (#2 progress note, etc.) is built. The discipline is "deliverable platform tells the truth all the way through" before we add more deliverables that lean on the same truthfulness layer.

### 2. After-the-moment failure surfacing in the timeline

**Status:** Bundled with the 2B dispatch.

**Scope:** Status badge on `client_communications` rows in the timeline UI surface. Single coherent design covering both `failed` (synchronous) and `bounced` (async) states.

**Why bundled with 2B:** doing the badge work twice (once for synchronous, then again for async) is more code paths than doing it once. After 2B, the timeline observes the full status set.

### 3. Idempotency at the send boundary

**Status:** Fix-later if it surfaces in re-smoke.

**Observation from May 9 smoke:** two send attempts produced two `client_communications` rows. No idempotency at the synchronous boundary.

**v1 mitigation:** the `KickoffMemoDraftModal`'s existing `sending` state disables the send button while the request is in flight. This handles the human-error double-click case.

**Not v1-blocking because:** the failure mode requires a network round-trip during which the user double-clicks, which the disabled-button guard handles. Backend-side idempotency would require a request-ID convention or content-hash dedup; not worth the scope unless re-smoke reproduces the double-row.

### 4. Modal auto-close fix-later nit

**Status:** Fix-later. Not part of FT-1.

**Observation from May 9 smoke:** the G5-P5 success-toast → 1.2s delay → onClose convention didn't fire. Either the auto-close logic is broken or the screenshot was captured pre-close.

**Triage:** if re-smoke reproduces, fold into a fix-later dispatch. Otherwise, defer until it surfaces again.

### 5. Where does the deliverable architecture story live long-term?

**Status:** Open. Worth deciding before too many post-v1 dispatches accumulate.

**Observation:** the North Star and Integration Architecture docs are entirely scoped to the chat/query surface (Modes 1-4). The deliverable surface — the entire Layer 2 work — has no canonical architectural home.

**Three options:**

- (a) Extend `AdvisoryBoard_North_Star.md` with a "Layer 2 — Deliverables" section that mirrors the four-mode framing for deliverables (engagement-stage taxonomy + send-path architecture + observability layer).
- (b) Create a separate `AdvisoryBoard_Deliverables_Architecture.md` document at the same level as the integration architecture doc.
- (c) Let this remediation plan be the de facto canonical reference until a larger architectural fork forces (a) or (b).

**Recommendation:** decide post-re-smoke. The pre-2B state of the architecture is in flux; pinning a canonical doc to a transitional state is premature. After 2B ships, a small "Layer 2 architecture" doc that absorbs this plan + 2B's design + the Gap 1 chat-command coupling story is the right next move.

### 6. Migration test pattern for status enum extension

**Status:** Confirm at R-P2 audit.

**Question:** does the project have an existing Alembic migration-test pattern? If yes, add a test for the `status` constraint extension. If no, skip — adding migration tests as a one-off for this work is overkill.

### 7. Resend wrapper module shape

**Status:** Confirm at R-P2 audit.

**Question:** does the existing Resend wrapper raise on send failure, or swallow and return `None`? If it swallows, R-P2 includes a small wrapper-side fix to raise typed exceptions. If it raises, the service layer wraps-and-translates around the existing surface. The audit determines which.

### 8. Next-deliverable planning gating

**Status:** Locked. Deliverable #2 (Day-60 progress note) is gated on re-smoke PASS + 2B ship.

The April 29 brief's binding sequence held: Gap 4 ✅ → Gap 3 (kickoff-memo only) → smoke → fan-out / fix / pivot. The pivot signal raised the planning gate; this plan is the fan-out / fix / pivot resolution. Deliverable #2 doesn't enter planning until Layer 2's foundational truthfulness layer holds end-to-end.

### 9. Gap 1 (chat command) status

**Status:** Deferred indefinitely until v1 ships. Per the May 9 smoke decision: shipping a chat-command surface that drives the same broken send path doubles the harm vector. Resumes planning post-re-smoke.

---

## §6 — FT sequencing matrix

| Phase | FT(s) addressed | Surface | Effort | Required for re-smoke? |
|---|---|---|---|---|
| **R-P0** *(optional)* | Plan-doc bugs (not FTs) | Plan docs only | ~30min | No |
| **R-P1** | FT-2, FT-3 | `engagement_deliverable_service.py` (service layer) | ~1-2h | **Yes** — both must pass at re-smoke |
| **R-P2** | FT-1 (backend portion) | Alembic migration + service rewrite + API contract | ~3-4h | **Yes** — load-bearing for the truthfulness fix |
| **R-P3** | FT-1 (frontend), FT-4 | `KickoffMemoDraftModal.tsx`, Email Sync settings surface | ~2h | **Yes** — failure surface + copy reconciliation |
| **Re-smoke** | All four FTs evaluated | Manual end-to-end against own firm or Michael | ~1h | (the gate itself) |

**Total v1 build effort:** ~6-8 hours of CC work across three sequential phases, plus ~1 hour for re-smoke.

**Parallelization:** None. Single canonical trunk discipline holds. R-P1 → R-P2 → R-P3 is strictly sequential because R-P3 depends on R-P2's API contract change and the test baseline transitions cleanly only when phases land in order.

**FT-to-phase rationale:**

- FT-2 + FT-3 in R-P1 because both are service-layer narrow fixes, independent of FT-1's architecture, and clean up the smoke's side observations before the re-smoke validates FT-1.
- FT-1 split across R-P2 and R-P3 along the natural backend/frontend seam — same pattern as G5's P1-P5 split. R-P2 is the load-bearing change; R-P3 is the user-facing wiring.
- FT-4 in R-P3 because it's pure copy and the copy lives in the same files R-P3 touches anyway. Bundling avoids a separate trivial dispatch.
- R-P0 is optional because plan-doc bugs don't block CC dispatches; they're hygiene that improves prompt clarity.

---

## §7 — Re-smoke criteria

Re-smoke is the v1 milestone gate's re-evaluation. Same shape as the May 9 smoke event: not a build session, manual end-to-end exercise, mirrored against the original smoke checklist's sections A-H but with explicit pass/fail criteria for each FT.

### Test setup

Same as the original smoke:

- Real production environment (Vercel + Railway + Supabase).
- Test client: Tracy Chen DO, Inc. (`b9708054-0b27-4041-9e69-93b20f75b1ac`) or own firm if available.
- Two recipient/methodology cases:
  - **Positive control:** `samuelvortizcpa@gmail.com` — known-good inbox.
  - **Negative control (canonical methodology — env-var corruption):** Temporarily set `RESEND_API_KEY` to an obviously-invalid value on Railway (e.g., a known-bad string). Force the synchronous Resend call to fail at the credential-check layer. Restore the original value at the end of the re-smoke. Rationale: (a) doesn't touch application code, (b) fully reversible within-session, (c) exercises the exact code path the locked FT-1 PASS criteria target, (d) generalizes to future deliverable-smoke negative controls. **This adaptation was locked at the May 10 evening re-smoke** after the originally-proposed `.invalid` reserved-TLD recipient (e.g., `nonexistent@invaliddomain-callwen-test.invalid`) proved insufficient — Resend accepts `.invalid` as syntactically valid at the API layer, returns a real message ID, and the synchronous rejection branch is never exercised. The `.invalid` approach is preserved here only as a historical note; **env-var corruption is the canonical methodology going forward** for all deliverable-smoke negative controls.
- Cadence pre-flight: `kickoff_memo` enabled. Admin role.

### FT-1 PASS criteria

**Positive control (valid recipient):**

- Click Send → success toast fires with the existing G5-P5 copy.
- Modal closes after the 1.2s delay (confirms the auto-close fix-later nit either was a one-time observation or got fixed; if it persists, log as a fix-later for a hygiene dispatch but does not block re-smoke PASS).
- Email arrives in the recipient's inbox (Inbox or appropriate folder).
- DB query: `client_communications` row written with `status='sent'`, `resend_message_id` populated (non-null), `sent_at` populated, `metadata.send_error` not present, `thread_type='engagement_year'`.
- Journal entry written for the deliverable.

**Negative control (invalid recipient):**

- Click Send → failure toast fires with the new copy: *"Failed to send. Please try again or check the recipient address."*
- Modal stays open. Draft contents preserved.
- DB query: `client_communications` row written with `status='failed'`, `resend_message_id IS NULL`, `metadata.send_error` populated with `kind`, `status_code` (or omitted for exception), `message`, `attempted_at`. (Note: `sent_at` is `NOT NULL` in the live schema; R-P2's failure branch writes `now()` or `attempted_at` to satisfy the constraint. `resend_message_id IS NULL` is the disambiguator between `sent` and `failed` rows — `sent_at` is not.)
- **Journal entry NOT written** for the failed deliverable.
- Send button re-enables; CPA can edit recipient and retry.

**FT-1 FAIL** = any of the above doesn't hold. Examples: success toast on negative control (the original lie); `resend_message_id` null on positive control's `status='sent'` row; journal entry written on the failure path; modal closes on failure.

### FT-2 PASS criteria

- Open the kickoff memo modal for Tracy.
- Strategies chip list renders the strategies that are `recommended` for Tracy (Augusta Rule, at minimum).
- The body and the chip list agree — if the body discusses Augusta Rule, the chip list shows Augusta Rule.
- Warnings banner is empty unless an actual warnable condition exists (e.g., a strategy was filtered out for a real reason).

**FT-2 FAIL** = chip list shows "No strategies referenced" while the body discusses real strategies, OR warnings banner is silent when a typed-filter strip happened.

### FT-3 PASS criteria

- Tasks chip list shows each client-facing implementation task exactly once.
- Tracy's known 7 implementation tasks for Augusta Rule render as 7 distinct entries (or whatever the correct count is — re-confirm at re-smoke against the Action Items tab).

**FT-3 FAIL** = duplicate entries in the task chip list.

### FT-4 PASS criteria

- Send button text reads "Send Email" (or whatever the locked v1 copy is).
- Settings → Email Sync, "Connect Gmail" button has the inbound-only caption beneath it.
- No reference to "Send via Gmail" remains in the deliverable surface.

**FT-4 FAIL** = "Send via Gmail" copy still present anywhere in the deliverable flow.

### Adjacent observation criteria (not FTs but worth noting)

- The double-row idempotency observation: re-smoke should NOT produce two rows for a single Send click. If it does, the disabled-button guard isn't holding and §5 item 3 escalates from fix-later to v1-blocking.
- Cache-bust observation: hard refresh should not be required for the Draft Kickoff button to render. If it is, that's a separate fix-later (cache-control header tuning). Not blocking.
- Timeline tab 422 observation: pre-existing, not part of v1. Re-smoke does not gate on it.
- Plan-doc location bugs: if R-P0 didn't run before re-smoke, log any new ones surfaced and roll into a post-re-smoke hygiene dispatch.

### Re-smoke decision matrix

| Outcome | Next action |
|---|---|
| All four FTs PASS, no new pivot signals | v1 ships. Next planning conversation is the 2B dispatch + Gap 1 (chat command) re-evaluation. |
| One or two FTs FAIL with bounded scope | Targeted fix dispatch for the specific FT(s). Re-smoke after. Single canonical trunk discipline holds. |
| Any FT surfaces a deeper architectural concern (analogous to FT-1 vs FT-4 coupling on May 9) | New pivot signal. New planning conversation. Update this plan. |
| Adjacent observation escalates (e.g., idempotency reproduces) | Fold into a follow-up R-P4 fix dispatch; re-smoke after. |

### Re-smoke logistics carry-forward

- Halt at the first FT FAIL or after section H, whichever comes first. The May 9 smoke halted at section F because section F's findings made later sections non-informative; same discipline applies.
- DB schema lookup before queries (`information_schema.columns` first). Per the May 9 carry-forward.
- Diagnose before classifying. Don't classify a failure as "FT-1 still broken" without verifying which surface is actually lying.
- Adapt session scope explicitly if needed (e.g., own firm vs Tracy as source). Log the adaptation.

---

## Discipline reminders for the build sessions

Carrying forward from G4 / G5 conventions, applicable to every R-P CC prompt:

- Show-body gates between audit and action steps. Use `sed -n` for narrow slices when a file is too long for the Read tool to display verbatim.
- `--force-with-lease` only if any force is needed; never plain `--force`.
- Single canonical trunk: push to `origin/main` only; the GitHub Action handles `code/main` mirror.
- Verify branch HEAD via `/commits/<branch>` URL, not `/tree/<branch>/<path>`.
- After each R-P deploy: verify Railway deploy ID + Vercel deploy ID + `lang/main HEAD == code/main HEAD` before claiming "synchronized."
- Mirror SHA-compare verification: `git fetch code-mirror && git log <branch> -1 --format="%H"` then string-match.
- No `git add .` / `-A`. Explicit paths only.
- No co-authored-by trailers.
- Targeted test runs after each surface as cheap confidence checks.
- Embed the expected pytest-line in each phase's CC prompt as the gate (e.g., R-P1 expects `462 passed, 1 skipped` or similar — the precise number is locked when R-P1 audit finalizes the test count).

---

*End of Send-Path Remediation Plan. Save to project knowledge as `Send_Path_Remediation_Plan.md`. Doc commits to `docs/Send_Path_Remediation_Plan.md` on `origin/main` in a separate CC dispatch when convenient (probably bundled with R-P0's hygiene pass).*

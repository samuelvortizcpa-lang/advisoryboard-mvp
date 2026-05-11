# Post-V1 Sequencing Plan

**Status:** Planning. Not a build prompt.
**Prereq:** None. Working tree clean at `2484afa`. Backend tests 468 passed + 1 skipped, frontend 133 passed.
**Scope:** Post-v1 sequencing following the May 10, 2026 re-smoke PASS that cleared the April 29 v1 milestone gate. Covers 2B (Resend webhook for `delivered` / `bounced` / `complaint`), the eight-item hygiene bundle from the send-path remediation arc, and Layer 2 deliverable #2 entry (Day-60 progress note). **Does NOT include:** Layer 2 #2 scoping (sequenced as the next planning chat after 2B ships), Gap 1 (re-deferred pending Layer 2 #2 — see §5), or any of Gap 5/6/7/8/9.
**Reference state:** `origin/main` HEAD `2484afa` (R-P3 ship — frontend close-out + copy reconciliation). Mirror in sync at `2484afa92051c1c0853bff7e18777d47eeca04ba`. Vercel + Railway green. April 29 v1 milestone gate **cleared at PASS**.

This doc contains eight artifacts: §1 post-v1 scope and predecessor reference, §2 2B architecture and decisions, §3 build sequence, §4 2B test surface, §5 open questions and parking lot, §6 phase sequencing matrix, §7 2B smoke criteria and decision matrix, §8 Layer 2 #2 entry.

---

## §1 — Post-v1 scope and predecessor reference

### What this plan covers

The post-v1 phase begins at re-smoke PASS (May 10, 2026 evening). The send-path remediation arc — R-P0 through R-P3, plus the v1 re-smoke gate — landed all four FTs from the May 9 v1 smoke event end-to-end against the real production stack. The April 29 v1 milestone gate framework's terminal "ship" outcome is reached. Layer 2 deliverable #1 (kickoff memo) ships.

This plan locks the next post-v1 work:

1. **2B — Resend webhook for `delivered` / `bounced` / `complaint`.** The async half of the truthfulness contract that R-P2 + R-P3 closed at the synchronous layer. The re-smoke's positive control had to verify delivery manually via the human inbox; 2B is what makes that automatic. Scoped at this planning session per §2.
2. **Hygiene bundle.** Eight items accumulated across the remediation arc, allocated across the build sequence per §3. Five items bundle as a plan-doc-only dispatch (R-P0-shaped); the rest fold into 2B's build, Layer 2 #2's planning, or a separate triage track.
3. **Layer 2 deliverable #2 — Day-60 progress note.** Forward-looking commitment, locked identity, not yet scoped. Planning chat opens after 2B ships and 2B's own smoke event PASSes.

### What this plan does NOT cover

- **Layer 2 #2 detailed scoping** — opens at the post-2B planning chat. This plan names #2 as the next planning commitment but does not lock its architectural decisions.
- **Gap 1 (chat command) build** — re-deferred at this planning session pending Layer 2 #2 ship. See §5 item 1 for the full deferral rationale.
- **Gap 5 / 6 / 7 / 8 / 9** — remain in the use-case brief §5 build order. Not entered into planning until Layer 2 #2 ships and the deliverable inventory grows beyond two.
- **Layer 3 / Layer 4 strategic work** — out of scope.

### Predecessor reference

This plan inherits the structural conventions of `Send_Path_Remediation_Plan.md`:

- §-numbered sections, with explicit purpose statement per section
- Phase sequencing matrix table (§6)
- Smoke criteria + decision matrix at close (§7)
- Open questions and parking lot in dedicated section (§5)
- Acceptance criteria per build phase

The conventions are load-bearing because the CC build dispatches that follow this plan depend on its predictable structure (audit prompts cite §-numbers, acceptance criteria are quoted into action prompts, the phase sequencing matrix drives session-to-session sequencing).

`Send_Path_Remediation_Plan.md` itself remains canonical for the remediation arc through the re-smoke close. The hygiene dispatch (step 1 of §3) corrects four §7 items in that doc but does not supersede it. After Layer 2 #2 ships, the question of a consolidated Layer 2 architecture doc (per `Send_Path_Remediation_Plan.md` §5 item 5) re-opens.

---

## §2 — 2B architecture and decisions

All eight planning questions for 2B locked at this session. Decisions and rationale below.

### Q1 — Event scope: `delivered` + `bounced` + `complaint`

All three transactional events subscribe at the webhook. Engagement telemetry (`opened`, `clicked`) deferred to a later cycle with its own scoping conversation.

**Rationale:**

- **`delivered`** — confirms what the re-smoke's positive control verified manually via the human inbox. Net new information beyond R-P2's synchronous `'sent'`. Closes the async half of the truthfulness loop.
- **`bounced`** — *structurally load-bearing.* A bounce flips a row R-P2 just wrote as `status='sent'` into something more like `status='bounced'`. That's the post-send half of R-P2's contract: the synchronous send said "Resend accepted it," the async event says "the recipient's mail server rejected it after acceptance." Without `bounced` handling, the UI continues to claim a kickoff memo was sent when it wasn't received — structurally the same lying-toast failure mode R-P3 closed at the synchronous layer, just delayed to the async leg.
- **`complaint`** — sender-reputation protection. Low-frequency in CPA-to-client transactional mail but high-blast-radius if it does fire (Resend will throttle or suspend the sender). Captured but with no human-visible alert surface in v1.1.
- **`opened` / `clicked`** — different product surface entirely. Does the CPA see open rates? Where? Is it audit-noisy? Does it leak read-receipt-style info to clients via tracking pixels? Out of scope.

### Q2 — Endpoint placement: new route at `/api/webhooks/resend`

Clean per-provider separation, REST-y placement, easy to add per-provider webhook routing later (Stripe webhooks for billing, calendar webhooks if Google sync resumes).

**Audit deferral:** confirm there isn't already a `webhooks/` directory pattern in the FastAPI router setup. If there is, follow that convention; if not, this route is the first one.

### Q3 — Signature verification: HMAC-SHA256 with new env var `RESEND_WEBHOOK_SECRET`

Not a real decision — yes, verify, document the env var.

Mechanics:
- HMAC-SHA256 over raw request body, comparison against signature header (exact header name confirmed at audit; Resend's standard webhook spec uses `Resend-Signature` or `Svix-Signature` depending on dispatch infrastructure version)
- Reject with 401 on signature mismatch; log the rejection with structured fields
- New env var `RESEND_WEBHOOK_SECRET` documented in the credential-rotation checklist alongside `RESEND_API_KEY`
- Local-dev fallback: if the env var is unset, log a warning and skip verification (for testing only — production env vars in Railway are unset-failsafe via the same pattern as `RESEND_API_KEY`)

### Q4 — `delivered` event handling: column update, no journal

On a `delivered` event for a `client_communications` row:
- Set `delivered_at = NOW()`
- Append the event record to `metadata.webhook_events[]` for forensic audit
- **No journal entry.** The send-success event is already journaled at R-P2's write-after-send. Adding a second journal entry per successful send is journal-spam; the column captures the data, the existing journal entry captures the operational signal.

### Q5 — `bounced` event handling: column update + status flip + journal entry + minimal UI surface

On a `bounced` event for a `client_communications` row:
- Flip `status` from `'sent'` to `'bounced'`
- Set `bounced_at = NOW()`
- Write `metadata.bounce = {reason, raw_response, bounce_type, ...}` mirroring R-P2's `metadata.send_error` envelope shape
- Append the event record to `metadata.webhook_events[]`
- **Write a journal entry.** A bounce is the inverse of a memo-sent event — it semantically un-sends. Per use-case brief §7: *"Every new auto-generated artifact (memo sent, deliverable produced, strategy task completed, cadence changed) should write a journal entry."* The bounce is the operational inverse and journal-worthy on the same logic.

**UI surface (minimal, in 2B scope):**
- Comm row in the client Timeline tab renders `status='bounced'` with a visual distinction (red/warning state, same surface affordance R-P3 wired for `'failed'`)
- Kickoff-memo deliverable surface (and any future deliverable surface, since they inherit the same data) shows the bounced state with the bounce-reason text

**UI surface (NOT in 2B scope):**
- Separate notifications inbox
- Dashboard alert widget
- Email-the-CPA-when-a-bounce-happens flow
- Open-rate / click-rate displays

Each of those is its own product-surface conversation, opened only if appetite emerges post-2B.

### Q5 (complaint sub-decision) — `complaint` event handling: capture-only

On a `complaint` event for a `client_communications` row:
- Append the event record to `metadata.webhook_events[]`
- **No status change.** A complaint doesn't change what happened to the message; the message was delivered, the recipient marked it as spam after-the-fact.
- **No journal entry.** No operational signal yet — there's no CPA-facing alert surface to fire against.
- **No dedicated column.** Capture in JSONB. If a future cycle adds sender-reputation alerts or a complaint-tracking dashboard, the data is queryable in JSONB and can be migrated to a dedicated column then.

### Q6 — Idempotency: `metadata.webhook_events[]` array with `event_id` dedup check

Each event record stored as a JSONB object: `{event_id, event_type, received_at, payload_snapshot}`. Idempotency check: before any side effect (column update, status flip, journal write), check if `event_id` already exists in the array. If yes, no-op (return 200 with body indicating "already processed"). If no, append and proceed.

**Why JSONB array, not separate table:**
- Audit log is bookkeeping, not first-class semantic state. Events are append-only-ish and almost never queried in product code.
- Idempotency check is single-row scope (within one `client_communication`). A separate table would buy structural cleanliness at the cost of a join on every event read and a second migration surface to maintain.
- YAGNI: if at v1.2 or later the queryability becomes painful, migrate then. The data lives in JSONB until that pressure exists.

### Q7 — Migration appetite: UP, bounded

**Migration content:**
- One Alembic up/down adding two nullable timestamp columns to `client_communications`:
  - `delivered_at` (TIMESTAMP, nullable)
  - `bounced_at` (TIMESTAMP, nullable)
- No new table
- No constraint change (R-P2 audit confirmed `status` is `String(50)` with no constraint — accepts `'bounced'` as a new value)
- Reversible (drop the two columns on down)

**Why this shape, not the "fully structurally explicit" alternative (new event table, dedicated `complaint_received_at` column, etc.):**
- `delivered_at` and `bounced_at` are *first-class semantic state* — they describe what happened to the message, same as `sent_at` already does. Read by product code (Timeline display, deliverable surface state). Indexable. Queryable for downstream reporting. Justify dedicated columns.
- `complaint_received_at` is *bookkeeping* — no product code reads it today, no surface displays it. Doesn't justify a dedicated column until the surface exists. JSONB until then.
- Event audit log is bookkeeping. Doesn't justify a dedicated table. JSONB until queryability pressure exists.

### Q8 — Effort estimate: ~4 hours of CC work

Composition:
- **Migration** (~15 min) — one Alembic up/down adding two nullable timestamp columns.
- **Webhook handler** (~1.5 hours) — route, signature verification, event dispatch, idempotency check, row updates per event class, journal write on bounce.
- **UI surface** (~1 hour) — bounce state rendering on Timeline tab and deliverable surface. Status enum extension in frontend types.
- **Tests** (~1 hour) — webhook handler unit tests (per event class), signature verification tests (positive + negative), idempotency test (same event_id twice → no-op), frontend bounce-state render test.

**Smoke event sequenced separately**, ~30-45 minutes manual end-to-end exercise.

**Build session shape:** single audit-then-action two-pass CC dispatch on the locked R-P pattern. Same shape as R-P2 was supposed to be (and actually shipped in ~1 hour — R-P2's surprise was the no-migration finding). 2B's surprise candidates are at the audit step: webhook directory convention (Q2), exact Resend signature header name (Q3), existing webhook test patterns (Q8 tests).

---

## §3 — Build sequence

Five-step sequence post-planning. Each step's dependencies, scope, and acceptance criteria locked.

### Step 1 — Plan-doc hygiene dispatch (~30 min)

**Scope:**
- Correct `Send_Path_Remediation_Plan.md` §7 four items (hygiene bundle #1, #2, #3 from re-smoke summary):
  - §7 `sent_at IS NULL` criterion — schema is NOT NULL; replace with `resend_message_id IS NULL` or equivalent achievable check
  - §7 `.invalid` negative-control recipient insufficient — document env-var-corruption as the canonical methodology adaptation for future deliverable smoke events
  - §7 column-name samples — `metadata_` vs `metadata`, `to_address` vs `recipient_email` — corrected to match implementation reality
- Correct R-P3 plan-doc divergences (hygiene bundle #5 — three sub-items):
  - Plan §1 framed FT-1 frontend wiring as substantive work; actual was a one-line copy edit
  - Plan §3 R-P3 referenced `email-sync/` URL path; actual is `integrations/page.tsx`
  - Plan §1 failure-toast literal slightly mismatched G5-P5's already-coded text
- Update `callwen-advisory-engagement-use-case-brief.md` §4:
  - Gap 3 status → production-resolved (kickoff memo v1 shipped at re-smoke PASS)
  - Gap 1 status → un-deferred-then-re-deferred-pending-Layer-2-#2 (with both rationales recorded)
  - 2B → entered scope as immediate-next post-v1 dispatch
  - Day-60 progress note → named as Layer 2 #2 with sequencing after 2B
- Commit this plan-doc (`Post_V1_Sequencing_Plan.md`) into the repo
- Commit the session summary (`session-summary-may-10-2026-post-v1-planning.md`)

**Hygiene bundle #6 (R-P0 residual project-knowledge files) is a USER ACTION**, not a CC dispatch: the user re-uploads corrected `session-summary-may-8-2026-g5-p5-ship.md` and `north-star-scope-note.md` to project knowledge directly. Flagged in the dispatch as out-of-CC-scope so it doesn't get assumed-handled.

**Effort:** ~30 min CC work, single commit. Mirrors R-P0's shape.

**Dependencies:** none. Working tree clean at `2484afa`.

**Acceptance:**
- All plan-doc edits applied as locked above
- Working tree clean post-commit
- Mirror in sync at the new HEAD
- Backend/frontend test baselines unchanged (no code touched)
- Single commit on `origin/main`

### Step 2 — 2B build (~4 hours)

**Scope:** per §2 above (architecture and decisions).

**Audit pass** confirms:
- Existing `webhooks/` directory convention (or absence — confirms Q2)
- Resend SDK version and exact signature header name (Q3)
- Existing webhook test patterns in the codebase (Q8 test scope)
- Resend wrapper module shape (hygiene bundle #4 fold-in — is there a typed exception class to narrow R-P2's `Exception` catch against?)
- `metadata` JSONB field shape (R-P2 wrote to `metadata`, audit confirms whether the column is `metadata` or `metadata_` — locking the column name once-and-for-all)
- Frontend status-enum location and add `'bounced'` to the type union

**Action pass** applies:
- Alembic migration (two nullable timestamp columns)
- Webhook handler implementation per §2 Q1-Q6
- UI bounce-state rendering per §2 Q5
- Test suite expansion
- Hygiene bundle #4 fold-in: if typed exception class found, narrow the catch and populate `raw` + `status_code` in `metadata.send_error`

**Dependencies:** Step 1 (plan-doc hygiene) shipped. Working tree clean at the post-hygiene HEAD.

**Acceptance:**
- Backend tests pass with new webhook + idempotency + signature-verification coverage; target ~475-480 passed (from current 468)
- Frontend tests pass with new bounce-state render test; target ~135-137 passed (from current 133)
- Migration applies and reverses cleanly in local + Railway
- Vercel + Railway green at the new HEAD
- Mirror in sync
- `RESEND_WEBHOOK_SECRET` env var documented in `credential-rotation-checklist.md`
- Single audit commit + single action commit (the two-pass pattern), or one combined commit per orchestrator preference at session open

### Step 3 — 2B smoke event (~30-45 min)

**Type:** Manual end-to-end exercise, not a build session. Same discipline as the v1 smoke / re-smoke per §7.

**Scope:** Verify the three event classes end-to-end against the real production stack at the post-2B HEAD.

**Test setup:**
- Real production environment (Vercel + Railway + Supabase) at the new HEAD
- Webhook endpoint registered in the Resend dashboard with `RESEND_WEBHOOK_SECRET` configured
- Test client: Tracy Chen DO, Inc. (`b9708054-0b27-4041-9e69-93b20f75b1ac`) or own firm if available

**Three test cases (positive control + two negative controls):**

1. **`delivered` positive control** — send a kickoff memo to a known-good inbox (`samuelvortizcpa@gmail.com`). Verify:
   - Initial `client_communications` row writes with `status='sent'`, `sent_at` populated, `resend_message_id` populated
   - Within ~30 seconds, Resend fires `delivered` webhook → row updates with `delivered_at` populated, `metadata.webhook_events[]` contains the event record
   - Timeline tab displays the comm as delivered (visual distinction from sent-but-not-yet-delivered)
   - No journal entry created on `delivered` (per Q4)

2. **`bounced` negative control** — send to a recipient that produces a hard bounce. Two methodology options:
   - Option A: a real non-existent address at a real domain (e.g., a randomly-generated string at a known-test-friendly domain). Risk: variable bounce timing.
   - Option B: a Resend-provided bounce simulator endpoint if one exists (audit at smoke prep). Cleaner.
   - Verify: initial row writes `status='sent'` → bounce event flips to `status='bounced'`, `bounced_at` populated, `metadata.bounce` envelope populated, journal entry written
   - Timeline tab displays the comm as bounced (red/warning state)
   - Modal/deliverable surface displays the bounced state with reason text

3. **`complaint` capture** — `complaint` events are hard to trigger on demand (require a real inbox user marking spam). Verify-by-construction:
   - Use Resend's webhook test dispatch (sends a synthetic event payload signed with the same secret) to fire a `complaint` event for an existing comm row
   - Verify: `metadata.webhook_events[]` contains the synthetic event record, no status change, no journal entry, no UI surface change

**Plus idempotency verification:** fire the same `delivered` event twice (Resend dashboard supports event redelivery for testing). Verify second fire is a no-op — no duplicate `delivered_at` overwrite, no duplicate event in `metadata.webhook_events[]`.

**Plus signature verification negative control:** POST a malformed-signature webhook payload. Verify 401 response, no row touched.

**Acceptance per §7 (decision matrix below).**

### Step 4 — Engagement-templates 500 triage dispatch (~30 min, audit-only)

**Scope:** CC audit-only dispatch (no action). Diagnose the pre-existing `engagement-templates 500` error visible in re-smoke devtools. Output: root-cause diagnosis + sized fix recommendation. No code touched in this step.

**Dependencies:** Step 3 (2B smoke) PASSes. 2B's success removes the "more urgent thing" argument; this triage now slots cleanly.

**Acceptance:**
- Diagnosis recorded in a triage note (lives in the repo or project knowledge per orchestrator preference)
- Fix recommendation sized (small / medium / multi-session) with scope boundary
- Decision: dispatch the fix now, defer to a maintenance cycle, or escalate to a planning conversation if the diagnosis surfaces architectural questions

### Step 5 — Layer 2 #2 planning chat

**Type:** Planning conversation, not a build session. Mirrors this session's shape.

**Scope:** Open Day-60 progress note's architectural decisions per §8 below.

**Dependencies:** Step 3 (2B smoke) PASSes. The 2B work has shipped, the async observability layer is live, and Day-60 inherits truthful async semantics for free.

**Output:** Either a canonical scoping doc (`Layer_2_#2_Day-60_Plan.md` or similar) modeled on `Send_Path_Remediation_Plan.md`'s structure, or an explicit build-session fan-out captured in the session summary. Decision at #2's planning session.

---

## §4 — 2B test surface

### Backend tests (expected delta: 468 → ~475-480)

New test files / additions:

1. **`test_resend_webhook_handler.py`** (new file) — handler unit tests per event class:
   - `test_delivered_event_updates_row` — happy path for `delivered`
   - `test_bounced_event_flips_status_and_writes_journal` — happy path for `bounced`
   - `test_complaint_event_captures_in_metadata_only` — happy path for `complaint`
   - `test_unknown_event_type_logs_and_no_ops` — defensive case for future Resend events Callwen doesn't subscribe to
   - `test_event_for_unknown_resend_message_id_returns_200_with_warning` — webhook receives an event for a row Callwen doesn't have (e.g., test events from Resend dashboard for never-existed message IDs)

2. **`test_resend_webhook_signature.py`** (new file) — signature verification:
   - `test_valid_signature_accepts_payload`
   - `test_invalid_signature_returns_401`
   - `test_missing_signature_header_returns_401`
   - `test_unset_secret_in_local_dev_warns_and_skips` — for local-dev fallback per Q3

3. **`test_resend_webhook_idempotency.py`** (new file) — idempotency:
   - `test_same_event_id_twice_is_noop`
   - `test_different_event_ids_for_same_comm_both_process`

4. **`test_alembic_migration_2b.py`** (new file, conditional) — only if existing migration test pattern exists per `Send_Path_Remediation_Plan.md` §5 item 6. Audit confirms; if no existing pattern, skip this file.

### Frontend tests (expected delta: 133 → ~135-137)

1. **`KickoffMemoDraftModal.test.tsx`** extension — add bounce-state render test (mirrors the existing `failed`-state test from R-P3 wired with a `'bounced'` status fixture).

2. **`ClientTimeline.test.tsx`** (or whichever component renders comm rows in the Timeline tab) — add bounce-state render test.

### Smoke event coverage

Manual end-to-end exercise per §3 Step 3. Not part of automated test baselines. Functions as the integration test analogous to the v1 re-smoke.

---

## §5 — Open questions and parking lot

### 1. Gap 1 (chat command) — re-deferred pending Layer 2 #2

**Status:** Parking lot. Un-deferred status preserved (scope-ready), but not next-in-line.

**Two-version deferral rationale (recorded for the next planning conversation that picks up Gap 1):**

**Version 1 — May 9, 2026, `Send_Path_Remediation_Plan.md` §5 item 9:** *"Shipping a chat-command surface that drives the same broken send path doubles the harm vector."* Resolved at re-smoke PASS — the harm vector closed.

**Version 2 — This planning session, May 10, 2026 evening:** Sequence after Layer 2 #2 (Day-60 progress note) ships, for two reasons:

1. **Vocabulary value scales with deliverable count.** Use-case brief §4 Gap 1 frames the assistant as a "stage-aware engagement assistant" — a command vocabulary. Vocabularies are valuable when they have multiple words. With one deliverable (kickoff memo), the vocabulary is one command. With kickoff + Day-60 it's two commands and a shared router pattern that's worth the abstraction cost. Use-case brief §5 build order positions Gap 1 at step 4, after Gap 3's deliverable framework is extended.
2. **Design information from #2.** Each new deliverable likely teaches us something about chat-command shape (parameter syntax, preview UX, error modes). Building Gap 1 against one deliverable risks locking in a design that fights Day-60's needs. Sequencing #2 first is *cheaper*, not more expensive, because it's information for the Gap 1 design rather than work that gets duplicated.

**Re-entry trigger:** Layer 2 #2 ships and its smoke event PASSes. Gap 1 then enters its own planning conversation.

### 2. Engagement-templates 500 — pre-diagnosis

**Status:** Sized as a separate triage dispatch (§3 Step 4). No diagnosis at planning time.

**Observed symptoms:** 500 error visible in re-smoke devtools Network tab during F.2 (a request adjacent to but not part of the send-path flow). Tracy's banner reads *"No engagement template assigned. Assign one to auto-generate recurring tasks."* — consistent with pre-existing state.

**Why not diagnosed at planning:** diagnose-before-classifying. Without root-cause investigation we don't know whether the fix is a one-line null-check, an architectural correction to the engagement-template assignment flow, or a deeper integrity issue with the engagement-template table state. Scoping a fix before diagnosis violates the same discipline that the v1 smoke event's FT-1 diagnosis required.

**Risk if deferred:** low. Pre-existing, user-facing banner handles the visible state, no regression introduced by recent work. Audit-only dispatch at §3 Step 4 is the right shape.

### 3. R-P2 typed-exception narrowing — folded into 2B audit

**Status:** Hygiene bundle item #4. Folded into §3 Step 2 (2B build) audit pass, not a separate dispatch.

**Why folded, not separate:** 2B is already touching `engagement_deliverable_service.send_deliverable`-adjacent surface. The webhook handler writes back to the same `client_communications` rows; the `metadata` envelope pattern is shared with `metadata.send_error` from R-P2. The audit step of 2B's build will need to re-read the Resend wrapper module to wire the webhook signature verification — that's exactly the surface where the typed exception class lives (if it exists). Investigating it once for 2B and once for #4 doubles the audit cost for no architectural gain.

**Outcome paths at 2B audit:**
- **Typed exception class found** → narrow the catch in R-P2's send path, populate `raw` and `status_code` in `metadata.send_error`. Fix-laters #1 and #2 close.
- **No typed exception class** → log as confirmed-no-typed-exception-available-in-current-Resend-SDK. Fix-laters #1 and #2 close as "won't fix without upstream Resend SDK change." Re-open if Resend ships typed exceptions in a future SDK version.

### 4. GPT-4o prompt-tuning ("a couple of tasks" plural overcommit) — folded into Layer 2 #2 planning

**Status:** Hygiene bundle item #7. Folded into §3 Step 5 (Layer 2 #2 planning).

**Why folded:** Prompt-tuning candidates accumulate. One prompt tweak isn't worth a dispatch. Day-60 progress note (Layer 2 #2) will need its own prompt-engineering pass during planning. That's the natural place to bundle a kickoff-memo prose nit alongside, treating prompt-tuning as a category rather than a one-off and avoiding the "every cosmetic nit becomes a dispatch" pattern.

### 5. Future Layer 2 architecture doc consolidation

**Status:** Carried forward from `Send_Path_Remediation_Plan.md` §5 item 5.

**Question:** does Layer 2's deliverable architecture get a dedicated canonical doc, and if so, when?

**Three options (unchanged from predecessor plan):**
- (a) Extend `AdvisoryBoard_North_Star.md` with a "Layer 2 — Deliverables" section
- (b) Create a separate `AdvisoryBoard_Deliverables_Architecture.md` document
- (c) Let `Send_Path_Remediation_Plan.md` + this plan + future plan-docs serve as the de facto canonical reference

**This plan's recommendation:** unchanged from predecessor — decide after 2B ships and Layer 2 #2's planning chat opens. At that point the architectural surface has stabilized through 2B's async layer and Day-60's deliverable extension, and a consolidation doc has enough material to be worth authoring. Pre-2B is still too transitional to pin a canonical doc to.

### 6. Layer 2 #2 (Day-60 progress note) — forward-looking commitment

**Status:** §8 below. Locked identity, locked sequencing, not yet scoped.

### 7. Open-rate / click-rate telemetry — deferred indefinitely

**Status:** Out of 2B scope per Q1. Re-enters scope only if appetite emerges from a CPA-facing product question ("can I see open rates?"). No timeline commitment.

### 8. Notification surface for bounces / complaints — out of 2B scope

**Status:** §2 Q5 explicitly excludes notification inbox / dashboard alert widget / email-the-CPA flows from 2B. These are their own product-surface conversations.

**Re-entry trigger:** if 2B's smoke event surfaces a usability gap (e.g., bounces happen but the CPA misses them because the Timeline tab isn't a primary surface), open a notification-surface planning conversation. Otherwise stays parking lot.

### 9. Idempotency on the modal Send button — fix-later, not v1.1-blocking

**Status:** Inherited from R-P2 carry-forward. The May 9 v1 smoke surfaced a double-row reproduction; the cause was the disabled-button guard not firing reliably under certain network conditions. Mitigation was the `sending`-state pattern in G5-P5, but the carry-forward flagged this as fix-later if a more robust idempotency-key pattern is needed.

**Why not now:** the re-smoke didn't reproduce a double-row. The current `sending`-state pattern appears sufficient. If a future smoke event (2B's or a later one) reproduces a double-row, this escalates from fix-later to v1.x-blocking and gets its own dispatch.

---

## §6 — Phase sequencing matrix

| Phase | Scope | Effort | Required for next step? | Dependencies | Notes |
|---|---|---|---|---|---|
| Step 1 — Plan-doc hygiene | Plan-doc + brief edits, commit Post_V1_Sequencing_Plan + session summary | ~30 min | Yes (provides clean reference state for Step 2 audit) | None | R-P0-shaped, single commit |
| Step 2 — 2B build | Migration + webhook handler + UI bounce surface + test suite | ~4 hours | Yes (Step 3 verifies Step 2's output) | Step 1 shipped | Two-pass audit→action on locked R-P pattern; folds in hygiene #4 |
| Step 3 — 2B smoke event | Manual end-to-end verification of three event classes + idempotency + signature | ~30-45 min | Yes (gates Steps 4 + 5) | Step 2 shipped + Resend dashboard webhook configured | Mirrors v1 re-smoke discipline; not a build session |
| Step 4 — engagement-templates 500 triage | CC audit-only diagnosis + fix sizing | ~30 min | No (parallel-allowable with Step 5 prep) | Step 3 PASS | Action sized post-diagnosis; may slot anywhere after Step 3 |
| Step 5 — Layer 2 #2 planning chat | Open Day-60 progress note architectural decisions | Planning conversation | N/A (terminal step in this plan's scope) | Step 3 PASS | Output: plan doc or build-session fan-out for #2 |

---

## §7 — 2B smoke criteria and decision matrix

### Pre-smoke setup

- HEAD at the post-Step-2 SHA, Vercel + Railway green, working tree clean
- Webhook endpoint `/api/webhooks/resend` registered in the Resend dashboard
- `RESEND_WEBHOOK_SECRET` configured in Railway production env
- Test client: Tracy Chen DO, Inc. or own firm
- Browser devtools open, Network tab + Console tab visible
- Supabase SQL editor open for direct row inspection
- Resend dashboard open for webhook delivery logs + event redelivery + signature inspection

### Pass criteria

**`delivered` PASS:**
- Send a kickoff memo to a known-good inbox.
- Within ~30 seconds, the `client_communications` row updates with `delivered_at` populated (non-null) and `metadata.webhook_events[]` contains the delivered event record with `event_id`, `event_type='delivered'`, `received_at`.
- Timeline tab visual state changes from "sent" to "delivered" (or whatever the locked v1.1 copy / state styling is at audit lock).
- No new journal entry created (per Q4).
- Resend dashboard shows webhook delivery succeeded with 200 response.

**`bounced` PASS:**
- Send a kickoff memo to a hard-bounce recipient.
- Initial row writes with `status='sent'`, `sent_at` populated, `resend_message_id` populated.
- Within Resend's bounce window (~minutes to ~hours depending on the recipient mail server), the row updates:
  - `status='bounced'`
  - `bounced_at` populated
  - `metadata.bounce` envelope populated with `reason`, `raw_response`, `bounce_type`
  - `metadata.webhook_events[]` contains the bounce event record
- Journal entry written for the bounce event (verify via journal tab or direct query on `journal_entries`).
- Timeline tab renders the comm row with bounced visual state (red/warning).
- Kickoff-memo deliverable surface shows bounced state with reason text.

**`complaint` PASS (synthetic):**
- Fire a synthetic `complaint` event via Resend dashboard's webhook test dispatch for an existing comm row.
- `metadata.webhook_events[]` contains the complaint event record.
- No status change on the row.
- No journal entry created.
- No UI surface change.

**Idempotency PASS:**
- Trigger Resend to redeliver an already-processed `delivered` event for a comm row.
- Second fire is a no-op: `delivered_at` not overwritten (timestamp unchanged from first fire), `metadata.webhook_events[]` has the event recorded only once.
- Webhook handler returns 200 with a body indicating "already processed" (or equivalent).

**Signature PASS:**
- POST a malformed-signature webhook payload to `/api/webhooks/resend`.
- Response: 401.
- No row touched, no log entry of processed event.
- Log entry of rejected payload with structured fields.

### FAIL definitions

- **`delivered` FAIL:** `delivered_at` not populated within ~5 minutes of a known-good send, OR Timeline tab visual state not changing, OR webhook delivery failing at the Resend dashboard with non-2xx response.
- **`bounced` FAIL:** `status` not flipping to `'bounced'`, OR `metadata.bounce` not populated, OR journal entry missing, OR UI not rendering bounced state.
- **`complaint` FAIL:** synthetic complaint event not captured in `metadata.webhook_events[]`.
- **Idempotency FAIL:** second `delivered` fire overwrites `delivered_at` or duplicates event in `metadata.webhook_events[]`.
- **Signature FAIL:** malformed-signature payload accepted as valid, OR row touched on malformed payload.

### Adjacent observations (not gating but worth noting)

- **Bounce timing variance.** Real-world bounce timing depends on the receiving mail server. Some bounce in seconds; some take hours. The smoke event should tolerate this and confirm async row-update mechanics rather than time-bounded SLAs.
- **Complaint events are rare in transactional CPA-to-client mail.** The synthetic test confirms the wire-up, but real-world complaint frequency will be low. Don't infer architecture decisions from complaint patterns at smoke; let production usage be the signal source.
- **Event ordering.** If `delivered` and a follow-up event (e.g., a late `complaint` for the same message) arrive close in time, idempotency on `event_id` handles deduplication but doesn't guarantee ordering. The current architecture doesn't depend on ordering, but log if out-of-order delivery is observed.
- **Webhook retry behavior.** Resend retries on non-2xx response. The smoke should observe whether transient 5xx (e.g., from a Railway cold start) triggers retries. Currently expected: retries happen, idempotency catches them, no harm.

### Decision matrix

| Outcome | Next action |
|---|---|
| All event classes PASS + idempotency PASS + signature PASS, no new pivot signals | **2B ships.** Proceed to Step 4 (engagement-templates 500 triage) and Step 5 (Layer 2 #2 planning chat). |
| One event class FAILs with bounded scope | Targeted fix dispatch for that event class. Re-smoke the affected case. Single canonical trunk discipline holds. |
| Idempotency or signature FAILs | More urgent than event-class FAIL — security/integrity surface. Immediate fix dispatch, full re-smoke required (not just the affected case). |
| Bounce timing wildly out of expectation (e.g., bounces silently lost) | Architectural concern. Open a planning conversation. Update this plan. |
| Adjacent observation escalates (e.g., webhook retries cause row-update races despite idempotency) | New pivot signal. Planning conversation. |

### Smoke logistics carry-forward

- Halt at the first FAIL or after all five test cases complete, whichever comes first.
- DB schema lookup before queries (`information_schema.columns` first). Per the May 9 / May 10 carry-forward.
- Diagnose before classifying. Don't classify a failure as "delivered event broken" without verifying which surface is actually lying (the Resend dashboard's webhook delivery log + Railway's logs + the row state in Supabase are the three sources of truth; reconcile them before naming a fault).
- Document the env-var-corruption methodology adaptation as the canonical pattern for forcing negative-control failures in deliverable smoke events (per re-smoke summary §"Locked findings" item 2). For 2B, the analogous adaptation may be malformed webhook signature corruption — the principle generalizes.

### What 2B smoke is NOT

- Not a build session. No CC dispatches. No code edits. No commits.
- Not a code-coverage exercise. The unit/integration tests from Step 2 are the automated coverage; smoke is the production end-to-end gate.
- Not the place to absorb adjacent strategic observations into committed scope — apply light triage per the May 9 evening pattern.

---

## §8 — Layer 2 deliverable #2 entry

### Locked identity

**Day-60 progress note.** Locked per:
- `Send_Path_Remediation_Plan.md` §5 item 8: *"Deliverable #2 (Day-60 progress note) is gated on re-smoke PASS + 2B ship."*
- `callwen-advisory-engagement-use-case-brief.md` §5 build order point 3: *"Order: Day-14 Kickoff Memo → Day-60 Progress Note → Mid-Year Tune-Up → Year-End Strategy Recap → cross-department handoffs."*

### Locked sequencing

After 2B ships and 2B's smoke event PASSes. Rationale per §3 Step 5 and agenda walk at planning close:

1. **2B closes the known async truthfulness gap.** Every deliverable sent in production has an unverified async leg until 2B ships. Day-60 would double that exposed surface.
2. **2B teaches the async pattern.** Day-60 inherits the async observability for free if 2B ships first. If Day-60 ships first, the 2B work later has to retrofit semantics across two deliverables.
3. **Effort asymmetry favors smaller-first.** 2B is ~4 hours; Day-60 is ~6-8 hours. Smaller load-bearing ship first preserves momentum.

### Forward-looking scope notes (not yet locked, refines at Step 5 planning)

**Architectural reuse expected from #1:**
- Send-path contract (R-P2 + R-P3 + 2B's webhook layer) — provider-agnostic, deliverable-agnostic
- `client_communications` schema and journal-write pattern
- Modal infrastructure (the React component structure with draft → edit → send → toast/failure)
- Cadence-template gating (Gap 4 already lands the configurability layer)

**Net-new construction expected:**
- New handler class for Day-60 progress note's content-assembly logic
- New prompt template (different stage, different context inputs — "what has the client completed since kickoff" vs "what's the engagement plan")
- New context-assembler purpose key (use-case brief §4 Gap 1 framing references the precedent pattern alongside `QUARTERLY_ESTIMATE`)
- Possibly a parameterized modal component vs a sibling-modal — open question, audit-time decision at Step 5 planning

**Effort estimate range:** ~6-8 hours across 2-3 build sessions. Refines at Step 5 planning.

**What Step 5 planning will lock:**
- The handler architecture (per-deliverable handler classes vs polymorphic dispatch)
- The prompt-engineering approach (Day-60 prompt template + the kickoff-memo "a couple of tasks" prose nit folded in, per hygiene bundle #7)
- The modal architecture decision (parameterized vs sibling)
- The cadence-template trigger logic (Day-60 auto-fires on day 60 of engagement vs CPA-initiated, vs both)
- The test surface
- The smoke event criteria (Day-60's smoke mirrors v1 re-smoke / 2B smoke patterns)

### Not yet in scope for this plan

- Layer 2 #2's full architectural decisions (open at Step 5)
- Layer 2 deliverable #3 onward (Mid-Year Tune-Up etc. — opens after #2 ships)
- Gap 1 re-entry (opens after Layer 2 #2 ships per §5 item 1)
- Cross-department handoff deliverables per use-case brief Gap 8 (opens after Gap 6 ships)

---

## Discipline reminders for downstream build sessions

Carrying forward from G4 / G5 / R-P conventions, applicable to every Step 1-5 dispatch:

- **Show-body gates between audit and action steps.** Two-pass dispatch is the load-bearing pattern; do not collapse to one-pass without explicit reason.
- **DB schema lookup before queries** (`information_schema.columns` first). Don't trust column-name memory.
- **Diagnose before classifying.** Pattern-matching a problem to a fix without verifying the problem's actual shape is the canonical failure mode (v1 smoke FT-1 was the prime example; re-smoke F.1's lying-toast moment was the load-bearing lesson).
- **Light triage of strategic observations.** Capture as canonical-brief gap notes or parking-lot entries rather than expanding the in-flight session.
- **Single canonical trunk discipline holds.** Every commit on `origin/main`; no long-lived feature branches.
- **Working tree clean at every session start.** No build session inherits a dirty tree.
- **Mirror in sync at every session close.** Verify the SHA explicitly; don't assume.
- **The April 29 v1 milestone gate framework remains load-bearing in its post-v1 carry-forward state.** Smoke events follow the fan-out / fix / pivot decision-making. 2B's smoke event will produce one of those four outcomes per §7's decision matrix; the next planning conversation opens at the smoke result.

---

*End of plan-doc. Next event: Step 1 — plan-doc hygiene dispatch. The plan-doc lands in the repo as part of Step 1's commit, alongside the hygiene corrections and the canonical-brief update.*

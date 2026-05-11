# Session Summary — May 10, 2026 — Post-V1 Planning Conversation

**Session type:** Planning conversation (not a build session)
**HEAD at start and close:** `2484afa` (R-P3 ship — frontend close-out + copy reconciliation). No code changes this session.
**Branch:** `main` on `samuelvortizcpa-lang/advisoryboard-mvp`
**Commits this session:** 0 (planning session, by design)
**Decision at close:** All four agenda items locked. `Post_V1_Sequencing_Plan.md` authored. Build-session sequence locked at 5 steps. Next event is Step 1 (plan-doc hygiene dispatch).

---

## Outcome

Followed the May 10, 2026 evening re-smoke PASS into the post-v1 planning conversation that the April 29 brief's framework called for in its terminal "ship" outcome. Walked the four-item agenda sequentially (2B → Gap 1 → hygiene → Layer 2 #2), surfaced open questions per item, applied diagnose-before-classifying discipline to scope decisions, and locked all decisions explicitly before each item closed. Closing scope held tight to the agenda — no strategic observations surfaced that warranted brief-extension this session (the May 9 evening planning's Gap 9 + Gap 2 sub-extension pattern remained the precedent but didn't fire here).

The plan doc authored covers 2B's eight architectural decisions, the five-step build sequence from plan-doc hygiene through Layer 2 #2 planning, the 2B test surface, the 2B smoke criteria with decision matrix, and the Layer 2 #2 forward-looking commitment. Gap 1 returns to the parking lot with un-deferred status preserved (scope-ready but not next-in-line) and a two-version deferral rationale recorded. The eight hygiene items from the remediation arc are allocated across the build sequence — five fold into Step 1's plan-doc dispatch, one folds into 2B's build audit, one folds into Layer 2 #2's planning, one becomes its own triage dispatch.

The discipline of "post-v1 → planning conversation → plan doc → build sequence" held cleanly. Output shape A (canonical scoping doc) locked over shape B (decision fan-out) because 2B and Gap 1 share send-path-contract architecture and the cross-agenda sequencing dependency on Day-60 #2 — these benefit from one canonical reference rather than scattered ad-hoc notes.

---

## Context loaded

Read in order per the next-session prompt's required reading list:

1. `session-summary-may-10-2026-re-smoke-pass.md` — immediate predecessor. Confirmed v1 ship, full FT PASS picture, eight-item hygiene bundle from §"Locked findings," env-var-corruption methodology adaptation captured for canonicalization.
2. `Send_Path_Remediation_Plan.md` §5, §7, §9 — re-smoke criteria, decision matrix, Gap 1 deferral rationale, open items. Plan-doc's structure confirmed as the template for the new plan doc.
3. `session-summary-may-9-2026-remediation-planning.md` — May 9 evening planning shape. One-question-at-a-time sequencing, locked-as-we-go discipline, light triage on strategic observations (Gap 9 + Gap 2 sub-extension precedent).
4. `callwen-advisory-engagement-use-case-brief.md` §4 + §5 — gap framing + build order. Day-60 progress note locked as Layer 2 #2 per §5 build order point 3.
5. `session-summary-may-10-2026-r-p2-ship.md` §"Adjacent observations" — typed-exception narrowing fix-laters #1 and #2 confirmed at re-smoke.

`AdvisoryBoard_Master_Roadmap.docx` skim deferred — the brief and remediation plan are already aligned on Day-60 as #2, so the roadmap doc isn't load-bearing for this session's locks.

---

## Agenda walk — four items locked

### Agenda item 1 — 2B: Resend webhook for delivered / bounced / complaint

Opened with the recommended question sequence per next-session prompt: Q1 first (event scope), Q7 next (migration appetite). Both answers fan out the rest.

**Q1 locked: Option B — `delivered` + `bounced` + `complaint`.**

Diagnostic underneath the surface "which events" framing: each event class differs not just in frequency but in what downstream UI / row-state work each one drags in. `delivered` confirms what the re-smoke's positive control verified manually. `bounced` is structurally load-bearing — it's the post-send half of R-P2's truthfulness contract, semantically equivalent to FT-1's lying-toast failure mode at the async layer. `complaint` is reputation-protective with no human-visible alert surface in v1.1 (capture-only). `opened` / `clicked` defer to a later cycle — different product surface entirely.

**Q7 locked: UP appetite, bounded.** Two nullable timestamp columns (`delivered_at`, `bounced_at`), no separate event audit table, no `status` constraint change (R-P2 audit confirmed schema is permissive), JSONB array `metadata.webhook_events[]` for the event audit log.

Q7's diagnostic decomposed into three sub-questions: Q7a (new columns for timestamps — yes, first-class semantic state), Q7b (separate event table — no, bookkeeping doesn't justify the join cost or migration surface), Q7c (status constraint extension — no change needed).

**Q2-Q6 + Q8 locked at the close-out batch:**
- Q2: new route `/api/webhooks/resend` (audit confirms convention)
- Q3: HMAC-SHA256 signature verification, new env var `RESEND_WEBHOOK_SECRET`, local-dev fallback warns and skips
- Q4: `delivered_at` column update, no journal entry (avoids journal-spam on already-journaled sends)
- Q5: `bounced` flips status + sets `bounced_at` + writes `metadata.bounce` envelope + writes journal entry + minimal UI surface on Timeline tab and deliverable surface. `complaint` is capture-only.
- Q6: idempotency via `metadata.webhook_events[]` array with `event_id` dedup check
- Q8: ~4 hours total CC work, single audit-then-action two-pass build session on the locked R-P pattern

Effort lock midpoint of the prompt's range — `complaint` is one extra case branch with no architectural cost over the minimum-viable option, and the UI surface is minimal (mirrors R-P3's `'failed'`-state affordance).

### Agenda item 2 — Gap 1: chat command surface re-evaluation

Opened with a sequencing question first per diagnose-before-classifying: before walking Q1-Q6 of Gap 1's scope, is Gap 1 actually next-in-line or does it sit in the parking lot until after Layer 2 #2 ships?

**Locked: defer Gap 1 again.**

Un-deferred status preserved (scope-ready), but not next-in-line. Re-enters planning after Layer 2 #2 (Day-60 progress note) ships.

Two reasons recorded in the plan doc:

1. **Vocabulary value scales with deliverable count.** Use-case brief §4 frames Gap 1 as a "stage-aware engagement assistant" — a command vocabulary. With one deliverable, the vocabulary is one command. With kickoff + Day-60 it's two commands and a shared router pattern worth the abstraction cost. Brief §5 build order positions Gap 1 at step 4, after Gap 3's deliverable framework is extended.
2. **Design information from #2.** Each new deliverable likely teaches us something about chat-command shape (parameter syntax, preview UX, error modes). Sequencing #2 first is *cheaper*, not more expensive, because it's design information rather than work that gets duplicated.

Agenda item 2 closed without walking Q1-Q6 — those open at the post-#2 Gap 1 planning chat. The plan doc records both deferral rationales (May 9 plan §9 + this session) so future planning has the full reasoning trail.

### Agenda item 3 — Hygiene bundle (eight items)

**Decision 1 — split locked:**

- **Plan-doc hygiene dispatch** (items #1, #2, #3, #5, #6) — bundleable into a single R-P0-shaped CC dispatch. Pure plan-doc edits + project-knowledge file re-uploads. Single commit, zero code touched.
  - Note: item #6 (R-P0 residual project-knowledge files) is a USER ACTION, not CC scope — re-uploads of corrected `session-summary-may-8-2026-g5-p5-ship.md` and `north-star-scope-name.md` happen via project knowledge directly. Flagged in the dispatch prompt so it doesn't get assumed-handled.
- **Code-touching items** allocated individually:
  - **#4 R-P2 typed-exception narrowing** → folded into 2B's audit step as while-we're-here candidate. Not a separate dispatch. Reasoning: 2B is already touching the same `engagement_deliverable_service` + Resend wrapper surface; investigating typed exceptions once doubles for both 2B's signature verification audit and #4's catch-narrowing audit.
  - **#7 GPT-4o prompt-tuning** → folded into Layer 2 #2's planning cycle. Reasoning: prompt-tuning candidates accumulate; bundling with Day-60's own prompt-engineering pass is cleaner than one-off dispatches.
  - **#8 engagement-templates 500** → separate triage dispatch (audit-only) after 2B ships. Reasoning: diagnose-before-classifying. Without root-cause investigation, fix-sizing is premature.

**Decision 2 — sequencing locked:**

Plan-doc hygiene **before** 2B. Reasoning:
1. Plan-doc edits include corrections to `Send_Path_Remediation_Plan.md` §7 — the structural reference for this session's new plan doc. Authoring against a corrected reference doc is cheap insurance.
2. ~30-min dispatch barely competes for calendar time.
3. R-P0's warm-up convention is the precedent.

Plus: the canonical-brief §4 update (Gap 3 production-resolved, Gap 1 re-deferred, 2B entering scope, Day-60 named as Layer 2 #2) bundles into the same dispatch.

### Agenda item 4 — Layer 2 deliverable #2 entry

**Q1 pre-locked at session open** via calibration flag: Day-60 progress note. Both `Send_Path_Remediation_Plan.md` §5 item 8 and `callwen-advisory-engagement-use-case-brief.md` §5 build order point 3 already name #2 as Day-60. Prompt's framing as open question was already resolved in canonical docs.

**Q2 — architecture reuse:** Significant reuse from #1 (send-path contract, comms schema, journal pattern, modal infrastructure, cadence gating). Net-new construction: handler class, prompt template, context-assembler purpose key, possibly parameterized modal component (audit decision at #2 planning).

**Q3 — effort lock: ~6-8 hours across 2-3 build sessions.** Lower end of prompt's range because kickoff memo absorbed the abstraction-building cost; Day-60 inherits the abstraction and only builds the deliverable. Prompt-engineering Day-60's content is the genuine net-new work where the time goes.

**Q4 — sequencing locked: 2B before Layer 2 #2.** Three reasons:
1. 2B closes the known async truthfulness gap; shipping Day-60 first doubles the unverified-async-leg surface.
2. 2B teaches the async pattern; Day-60 inherits it for free if 2B ships first.
3. Effort asymmetry favors smaller-first (2B is ~4h, Day-60 is ~6-8h).

**Q5 — defer #2 detailed scoping to its own planning chat post-2B.** This session's agenda is already full; #2's planning chat opens after 2B ships with the additional context of 2B's smoke event (which teaches the post-v1 smoke-event shape).

---

## Cross-agenda sequencing — build-session sequence locked

Five-step sequence post-planning:

1. **Step 1 — Plan-doc hygiene dispatch** (~30 min) — R-P0-shaped, hygiene bundle items #1/#2/#3/#5 + canonical-brief §4 update + commit Post_V1_Sequencing_Plan + session summary. Item #6 flagged as user-action.
2. **Step 2 — 2B build** (~4 hours) — Resend webhook for delivered/bounced/complaint. Two-pass audit-then-action dispatch. Folds in hygiene item #4 at audit.
3. **Step 3 — 2B smoke event** (~30-45 min) — manual end-to-end exercise. Three event classes + idempotency + signature verification. Mirrors v1 re-smoke discipline.
4. **Step 4 — engagement-templates 500 triage dispatch** (~30 min, audit-only) — diagnostic CC audit. Action sized post-diagnosis.
5. **Step 5 — Layer 2 #2 planning chat** — opens Day-60 progress note's architectural decisions. Mirrors this session's planning shape.

Gap 1 sits in the parking lot, re-enters planning after Layer 2 #2 ships.

---

## Success shape — Shape A locked

Canonical scoping doc authored: **`Post_V1_Sequencing_Plan.md`** at `/mnt/user-data/outputs/`. Eight §-sections following `Send_Path_Remediation_Plan.md` structural conventions:

- §1 — Post-v1 scope and predecessor reference
- §2 — 2B architecture and decisions (Q1–Q8 locked)
- §3 — Build sequence (five steps with effort, dependencies, acceptance)
- §4 — 2B test surface (backend + frontend test deltas)
- §5 — Open questions and parking lot (Gap 1 re-deferral, engagement-templates 500 pre-diagnosis, typed-exception narrowing fold-in, future Layer 2 architecture doc, etc.)
- §6 — Phase sequencing matrix (table)
- §7 — 2B smoke criteria and decision matrix
- §8 — Layer 2 #2 entry (forward-looking commitment)

Shape A locked over Shape B (decision fan-out without doc) because 2B and Gap 1 share send-path-contract architecture, the cross-agenda sequencing has Layer 2 #2 as a downstream dependency on 2B, and the hygiene bundle's allocation across the sequence benefits from one canonical reference.

---

## Repo state at session close

- Branch: `main`
- HEAD: `2484afa` (unchanged from session start)
- Working tree: clean (no edits this session)
- Origin: in sync
- Mirror: in sync at `2484afa92051c1c0853bff7e18777d47eeca04ba`
- Vercel: green at `2484afa`
- Railway: green at `2484afa`
- Backend tests: 468 passed, 1 skipped, 0 failed (unchanged)
- Frontend tests: 133 passed (unchanged)

---

## v1 milestone status — Layer 2 #1 production-validated, post-v1 sequence locked

Per the April 29, 2026 v1 milestone gate framework:

- ✅ Gap 2 shipped (April 29)
- ✅ Gap 4 shipped (G4-P4d)
- ✅ Gap 3 (kickoff-memo only) — production-validated at re-smoke PASS
- ✅ v1 milestone gate CLEARED at PASS (May 10 evening)
- 🚧 **Post-v1 sequence authored (this session)**
- 🚧 Step 1 — plan-doc hygiene dispatch (next event)
- 🚧 Step 2 — 2B build
- 🚧 Step 3 — 2B smoke event
- 🚧 Step 4 — engagement-templates 500 triage
- 🚧 Step 5 — Layer 2 #2 planning chat
- 🚫 Gap 1 (chat command) — re-deferred pending Layer 2 #2 ship

April 29's binding sequence held through v1: Gap 4 ✅ → Gap 3 (kickoff-memo only) ✅ → smoke → fan-out/fix/pivot → re-smoke PASS → v1 ships. Post-v1 sequence now opens with 2B as the next load-bearing work.

---

## Carry-forwards for the next session

### Locked plan inputs (do not re-derive)

- 2B Q1 = B: `delivered` + `bounced` + `complaint`
- 2B Q7 = UP-bounded: two nullable timestamp columns, no event table, no constraint change, JSONB events array
- 2B Q2 = new route `/api/webhooks/resend`
- 2B Q3 = HMAC-SHA256 + `RESEND_WEBHOOK_SECRET`
- 2B Q4 = column update on delivered, no journal
- 2B Q5 = status flip + column + journal + minimal UI on bounce; capture-only on complaint
- 2B Q6 = JSONB array idempotency
- 2B Q8 = ~4 hours single audit-action dispatch
- Gap 1 deferred again pending Layer 2 #2 ship
- Layer 2 #2 = Day-60 progress note, sequenced after 2B, ~6-8 hours across 2-3 build sessions

### Audit-resolved open questions (per Post_V1_Sequencing_Plan.md §2 + §3)

These resolve at 2B audit gate, not before:

- Existing `webhooks/` directory convention in FastAPI router setup (Q2 confirms)
- Resend SDK version + exact signature header name (Q3)
- Existing webhook test patterns in the codebase (Q8 test scope)
- Resend wrapper module's typed-exception class availability (folds in hygiene #4)
- `metadata` JSONB column name (`metadata` vs `metadata_` — locked once at audit)
- Frontend status-enum location for adding `'bounced'`

### Hygiene allocations

- Items #1, #2, #3, #5 → Step 1 plan-doc dispatch (CC scope)
- Item #6 → Step 1 dispatch flags as user-action (project knowledge re-upload)
- Item #4 → Step 2 2B audit fold-in
- Item #7 → Step 5 Layer 2 #2 planning fold-in
- Item #8 → Step 4 separate triage dispatch (audit-only)

### Next event: Step 1 — plan-doc hygiene CC build dispatch

Build session, not planning. Orchestrator chat opens with the plan-doc hygiene prompt that authors the CC dispatch. Working tree clean at `2484afa`. Acceptance: single commit on `origin/main`, all plan-doc edits applied as locked in Post_V1_Sequencing_Plan.md §3 Step 1, mirror in sync at new HEAD, backend/frontend test baselines unchanged.

---

*End of session summary. Next: Step 1 plan-doc hygiene CC build dispatch. Planning discipline holds; next session resumes the orchestrator → CC audit → CC action → review pattern under the April 29 v1 milestone gate framework's post-v1 carry-forward state.*

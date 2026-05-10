# G5 Planning — Kickoff Memo

**Status:** Planning. Not a build prompt.
**Prereq:** None. Hygiene track closed; backend frozen-clean.
**Scope:** Day-14 Implementation Kickoff Memo as the first instance of the `engagement_deliverable_service` abstraction. One deliverable, one modal, five sub-phases (P1–P5). Per the v1 milestone gate (April 29, 2026), Gap 3 ships ONLY this deliverable plus the abstraction it forces — the other five medium-layer deliverables stay deferred until post-smoke decision.
**Reference state:** `origin/main` HEAD `3af62a9`, working tree clean, 435 backend tests passed + 1 skipped, 119 frontend unit, 9 Playwright specs (all green on-demand), Railway + Vercel green, mirror in sync.

This doc contains five artifacts: §1 UI design, §2 schema + service abstraction, §3 build sequence, §4 test surface, §5 open questions to confirm before P1.

---

## §1 — UI design

### Surface — Inline trigger on the Day-14 task

**Placement decision.** The kickoff memo draft trigger lives on the Day-14 engagement task in the action items list, surfaced via `TaskDetailPanel`. This mirrors the existing "Draft Q2 Estimate Email" button on quarterly estimate prep tasks — known-good pattern, zero new top-level surface area for v1.

For v1 (manual-only, per Q2=A), the entry point is **a one-off "Draft kickoff memo" button on the client detail header's actions menu** — *not* on an auto-created Day-14 task, because no such task auto-creates yet. The task-list inline button is where this lives once auto-creation ships in a follow-up. v1 ships the click path via the header.

Structurally: same draft flow, different invocation surface for v1 vs. post-auto-create. The service layer (`engagement_deliverable_service`) is invoked the same way from both.

### v1 invocation — client header actions menu

**Placement.** The client detail page header already has an actions area (the "..." or explicit action buttons depending on what's there today — confirm during build via spot-check). Add a "Draft kickoff memo" entry, admin-and-cadence-gated:

- Visible only when `is_deliverable_enabled(client_id, "kickoff_memo")` is true (cadence respected from day one)
- Visible only to admin role (matches quarterly estimate's admin gate)
- **Hidden when admin sees a client with the deliverable cadence-disabled** (per §5 item 1: hide entirely, not show-disabled)

**Click behavior.** Opens a dedicated `KickoffMemoDraftModal`, NOT a 5th approach card on the existing `SendEmailModal`. The kickoff memo's content shape (strategies-discussed + client-facing tasks block) differs enough from quarterly estimate that fitting it into the same modal forces conditional rendering branches that hurt readability for both.

### Draft modal — single screen

```
┌─ Draft kickoff memo ─────────────────────────────────────┐
│  Client: Tracy Chen DO, Inc                              │
│  Engagement year: 2026                                   │
│                                                          │
│  ┌─ Generating draft... ───────────────────────────────┐ │
│  │  Pulling strategies, tasks, and client context...   │ │
│  │  [spinner]                                          │ │
│  └─────────────────────────────────────────────────────┘ │
│                                                          │
│  [appears once draft ready:]                             │
│                                                          │
│  Subject: [editable input]                               │
│  ┌──────────────────────────────────────────────────────┐│
│  │ [editable textarea, ~20 rows, monospace optional]    ││
│  │                                                      ││
│  │ Hi Tracy,                                            ││
│  │                                                      ││
│  │ Following up on our strategy meeting...              ││
│  │ [strategies block]                                   ││
│  │ [client-facing tasks block]                          ││
│  │ [open questions / next steps]                        ││
│  │                                                      ││
│  └──────────────────────────────────────────────────────┘│
│                                                          │
│  Strategies referenced (3):                              │
│  • Augusta Rule                                          │
│  • Cost Segregation Study                                │
│  • Reasonable Compensation Analysis                      │
│                                                          │
│  Client-facing tasks (4):                                │
│  • Confirm 14-day rental usage records [Augusta]         │
│  • Engage cost seg engineering firm [Cost Seg]           │
│  • Provide 2024 W-2 for owner [Reas Comp]                │
│  • Review draft articles [Reas Comp]                     │
│                                                          │
│  ─────────────                                           │
│  [Send via Gmail]   [Save as draft]   [Cancel]           │
└──────────────────────────────────────────────────────────┘
```

**Notes on the layout:**

- Strategies + tasks blocks render as **review chips below the editable body**, not as duplicate content. The CPA can see what the AI pulled vs. what's in the email body, but the body is the source of truth at send time.
- Subject line pre-populated as `Engagement kickoff — [client_name] — [tax_year]` (same shape as quarterly estimate's pre-pop pattern).
- Body is a plain textarea, not a rich editor. Quarterly estimate uses plain textarea; matching keeps the abstraction clean.

### Behavior

**On modal open:**

1. Modal renders shell immediately with "Generating draft..." state.
2. Frontend calls `POST /api/clients/{id}/deliverables/kickoff-memo/draft` with `{ tax_year }` (defaulting to current calendar year per §5 item 6).
3. Backend runs the deliverable service: context assembly via `purpose=engagement_kickoff`, strategy + client-facing tasks pull, GPT-4o draft generation. Returns `{ subject, body, strategies_referenced, tasks_referenced, warnings }`.
4. Modal swaps to editable state with returned values pre-populated.

**On "Send via Gmail":**

1. Frontend calls existing Gmail send path (already used by quarterly estimate flow).
2. Backend, post-Gmail-send, writes a `client_communications` row with `thread_type='engagement_year'`, `thread_year=<tax_year>`, `thread_quarter=NULL`, the standard sender/recipient/subject/body fields, and `open_items` JSONB populated by the open-items extractor (per §5 item 4: extractor runs in v1).
3. Journal entry written: `category='deliverable'`, message like "Engagement kickoff memo sent to Tracy Chen DO".
4. Modal closes; toast confirms send.

**On "Save as draft":**

- Out of scope for v1. Quarterly estimate workflow has no save-as-draft path either; the precedent is "draft is generated server-side, lives in the modal until sent or cancelled, no persistence between modal opens."

**On "Cancel":**

- Closes modal. No persistence. Same as quarterly estimate.

### Edge cases

1. **Cadence-disabled.** Header menu item hidden. Modal cannot be opened.
2. **No strategies in `recommended` status.** The deliverable service returns `strategies_referenced: []` and the LLM prompt template handles this with copy like "We're still finalizing recommendations." Send-able but probably not sent. Modal renders normally; CPA can decide.
3. **No client-facing implementation tasks.** Same handling: `tasks_referenced: []`, LLM template handles. Possible if all `recommended` strategies have only CPA-owned tasks.
4. **Strategies recommended but tasks not yet materialized.** Surface a warning banner in the modal: "3 strategies recommended but no implementation tasks found. The kickoff memo will reference strategies only." Don't block; warn. This is a Layer 2 stress-test signal worth catching.
5. **Generation failure (LLM error, context overflow).** Modal renders error state with retry CTA. No partial draft.
6. **Non-admin user.** Header menu item hidden (matches admin gate).
7. **Cross-org client_id.** Existing client access guard handles; modal cannot be opened from a foreign client's URL.
8. **Re-invocation after a kickoff memo was already sent.** Allowed. The thread is `engagement_year` keyed by `(client_id, tax_year)`; a second kickoff memo writes a second row in the same thread. CPA judgment governs whether to send. Same forgiveness as quarterly estimate.

### Component tree

New components in `frontend/components/deliverables/`:

- `DraftKickoffMemoButton.tsx` — header menu entry, handles cadence + admin gating, opens modal. Small.
- `KickoffMemoDraftModal.tsx` — the modal itself. Manages state for generation → review → send. Calls the deliverable API.
- `StrategiesReferencedList.tsx` — small read-only chip list. Reused for progress note when that ships.
- `ClientFacingTasksList.tsx` — small read-only chip list. Same reuse path.

Modified files:

- `frontend/lib/api.ts` — add types + `createDeliverablesApi(getToken, orgId)` factory with the kickoff-memo draft + send methods. Naming follows the `createCadenceApi` precedent.
- `frontend/app/dashboard/clients/[id]/page.tsx` — add the header menu entry render block.

### Admin-vs-non-admin states

**Non-admin:** Header menu item not rendered. Direct API call to the draft endpoint returns 403 (defense in depth — backend enforces). No client-detail-page disruption beyond the missing menu item.

**Admin:** Full access conditional on `is_deliverable_enabled(client_id, "kickoff_memo")`.

### What this surface deliberately doesn't have

- **No preview step before sending.** The CPA edits the body directly in the modal; that *is* the review.
- **No multi-step wizard.** One modal, one screen. Quarterly estimate uses the same pattern.
- **No "edit and resend" history.** If the CPA sends, then realizes they want to redraft, they hit "Draft kickoff memo" again — opens a fresh modal, fresh generation. Versioning is a Gap 1+ concern.
- **No engagement-engine task surface.** Per Q2=A, no Day-14 task auto-creates in v1.

### Forward-compatibility notes (without designing for them)

- The `engagement_year` thread type means progress note + year-end recap will join the same thread automatically when they ship. No retrofit.
- The `engagement_deliverable_service` shell ships parameterized by `deliverable_key`, so the second deliverable plugs in at the service layer without UI work for this kickoff-memo modal.
- The auto-create path doesn't change the modal — only how it's triggered. The `TaskDetailPanel` inline button can be added in a follow-up without touching the modal component.

---

## §2 — Schema + service abstraction

### §2.1 — Schema changes

**Net schema delta: zero new tables, zero new columns.**

What v1 reads from / writes to (all already exists):

- **Reads:** `clients`, `tax_strategies`, `client_strategy_status`, `strategy_implementation_tasks` (Gap 2 ship), `action_items` (Gap 2 columns: `strategy_implementation_task_id`, `client_strategy_status_id`, `owner_role`), `cadence_template_deliverables`, `client_cadence`, `client_journal_entries`, `client_financial_metrics`, `client_communications`.
- **Writes:** `client_communications` (one row per sent kickoff memo), `client_journal_entries` (one row per draft generation + one per send).

The Gap 2 schema is exactly the data the kickoff memo needs to render the client-facing tasks block. This is Gap 2 paying off — the kickoff memo build is where Gap 2's data first becomes load-bearing for a deliverable.

**Soft-schema item.** `client_communications.thread_type` is `VARCHAR(30)`. The new value `engagement_year` is 15 chars — fits cleanly. No schema change needed.

### §2.2 — `engagement_deliverable_service` shell

**File:** `backend/app/services/engagement_deliverable_service.py` (new).

**The abstraction's contract.** A deliverable is `(deliverable_key, context_purpose, prompt_template_fn, post_processing_fn)`. The service exposes three public functions; deliverable-specific logic lives in modules registered against `deliverable_key`.

```python
# Public surface

def draft_deliverable(
    db: Session,
    client_id: UUID,
    deliverable_key: str,         # must match a registered deliverable
    tax_year: int,
    requested_by: UUID,
) -> DeliverableDraft:
    """
    Cadence-gated draft generation.
    1. Validates deliverable_key is registered.
    2. Gates on is_deliverable_enabled(db, client_id, deliverable_key); raises
       PermissionError if disabled. Strict gate — manual override deferred to
       Gap 1 per §5 item 3.
    3. Calls the registered handler's context_purpose into the unified context
       assembler.
    4. Calls the registered handler's prompt_template_fn(context, client_data).
    5. Sends to GPT-4o, returns DeliverableDraft (subject, body, references_payload, warnings).
    6. Writes a journal entry: category='deliverable', message describes draft action.
    """

def record_deliverable_sent(
    db: Session,
    client_id: UUID,
    deliverable_key: str,
    tax_year: int,
    subject: str,
    body: str,
    sent_by: UUID,
    gmail_message_id: str | None = None,
) -> ClientCommunication:
    """
    Post-send tracking.
    1. Resolves thread_type from the registered handler.
    2. Resolves or creates the thread row via existing get_or_create_thread.
    3. Writes client_communications row with thread params.
    4. Calls registered handler's post_processing_fn (e.g., kickoff memo's
       open-items extraction).
    5. Writes journal entry: category='deliverable', "Engagement kickoff memo sent".
    """

def list_deliverable_history(
    db: Session,
    client_id: UUID,
    deliverable_key: str,
    tax_year: int | None = None,
) -> list[ClientCommunication]:
    """
    Reads prior communications matching the deliverable's thread_type for the
    client. Used by drafts to reference 'in our prior kickoff memo we said X'
    once deliverable #2+ ships. v1 kickoff memo doesn't use this directly but
    the abstraction provides it for the next deliverable.
    """
```

**The handler registration pattern:**

```python
# backend/app/services/deliverables/__init__.py

from .kickoff_memo import KICKOFF_MEMO_HANDLER

DELIVERABLE_HANDLERS = {
    "kickoff_memo": KICKOFF_MEMO_HANDLER,
}

def get_handler(deliverable_key: str) -> DeliverableHandler:
    if deliverable_key not in DELIVERABLE_HANDLERS:
        raise ValueError(f"No handler registered for deliverable_key={deliverable_key}")
    return DELIVERABLE_HANDLERS[deliverable_key]
```

**The handler shape (typed contract):**

```python
# backend/app/services/deliverables/_base.py

@dataclass(frozen=True)
class DeliverableHandler:
    deliverable_key: str           # must match the cadence ENUM value
    context_purpose: str           # passed to context_assembler
    thread_type: str               # passed to client_communications row
    build_prompt: Callable[[ContextBundle, ClientFacts], str]
    extract_references: Callable[[ContextBundle, ClientFacts], dict]
    extract_open_items: Callable[[str], list[OpenItem]] | None  # optional
```

**What the shell deliberately does NOT do:**

- It does NOT support deliverable-specific UI surfaces. Each deliverable's frontend integration is its own concern; the service is API-only.
- It does NOT auto-create engagement-engine tasks. Per Q2=A, kickoff memo is manual-only in v1. When auto-creation arrives, the engagement engine calls `draft_deliverable` directly from a scheduled job.
- It does NOT version drafts. A redraft = a new generation + new journal entry.
- It does NOT hold any state between calls. All state lives in `client_communications` + `client_journal_entries`. The service is pure orchestration.
- **It does NOT register quarterly estimate as a handler.** Per Q4=b, the existing quarterly estimate workflow is left in `communication_service` untouched. The shell is provisional; deliverable #2 will surface what the abstraction actually needs.

### §2.3 — Kickoff memo handler (concrete instance)

**File:** `backend/app/services/deliverables/kickoff_memo.py`.

```python
KICKOFF_MEMO_HANDLER = DeliverableHandler(
    deliverable_key="kickoff_memo",
    context_purpose="engagement_kickoff",  # new purpose key for the assembler
    thread_type="engagement_year",
    build_prompt=_build_kickoff_prompt,
    extract_references=_extract_strategies_and_tasks,
    extract_open_items=_extract_open_items_from_kickoff,
)
```

**New context assembler purpose: `engagement_kickoff`.**

One new entry in the assembler's purpose table. Budget + priority order (matches the April 7 assembler's existing pattern):

| Purpose | Token Budget | Priority Order |
|---------|--------------|----------------|
| engagement_kickoff | 6,000 | strategies (recommended) > implementation tasks (client-facing) > journal (last 30 days) > financials (current + prior year) > open action items > prior comms (if any) |

Per Q2=A (manual-only, no `strategy_meeting_completed_at`): journal pull is "last 30 days" rather than "since strategy meeting." Simple time-based filter.

**Prompt template (`_build_kickoff_prompt`).**

Pulls from the assembled context bundle and produces a GPT-4o prompt with sections:

- **System role:** CPA voice, professional but personal, no tax-calculation hallucination, no advice the documents don't support.
- **Client facts:** name, entity type, tax year.
- **Strategies block:** for each `client_strategy_status` row with `status='recommended'`, render `{strategy_name, brief_description, why_relevant_to_this_client}`. Brief description pulled from `tax_strategies.description`; why-relevant pulled from journal entries category=strategy or from the strategy row itself.
- **Client-facing tasks block:** for each `action_items` row joined to a recommended strategy via `client_strategy_status_id` AND `owner_role IN ('client', 'third_party')`, render `{task_name, due_date, what_we_need_from_you}`. Filter excludes CPA-owned tasks per Q6.
- **Output instruction:** Draft an engagement kickoff email with sections (greeting, "following up on our recent strategy conversation", strategies-we-recommended, what-we-need-from-you-in-the-next-30-days, open-questions-for-you, signoff). Subject pre-filled as `Engagement kickoff — [client_name] — [tax_year]`.

**`_extract_strategies_and_tasks`** returns the `references_payload` for the modal's review chips:

```python
{
    "strategies": [{"id": ..., "name": "Augusta Rule"}, ...],
    "tasks": [{"id": ..., "name": "Confirm 14-day rental usage records",
               "owner_role": "client", "due_date": ..., "strategy_name": "Augusta Rule"}, ...],
}
```

**`_extract_open_items_from_kickoff`** runs the existing GPT-4o-mini open-items extractor (April 7 precedent) over the sent email body, populates `client_communications.open_items` JSONB. Identical pattern to quarterly estimate's open-items extraction.

### §2.4 — Q5 retrofit: cadence gate on existing quarterly estimate flow

**Surface.** `quarterly_estimate_service.draft_quarterly_estimate_email()` (confirm exact function name during build).

**Change.** Single guard at the top of the function:

```python
def draft_quarterly_estimate_email(db, client_id, tax_year, quarter, ...):
    if not cadence_service.is_deliverable_enabled(db, client_id, "quarterly_memo"):
        raise PermissionError(
            f"quarterly_memo deliverable not enabled for client_id={client_id}"
        )
    # ... existing 5-step flow unchanged ...
```

**Frontend implication.** The existing `SendEmailModal`'s "Quarterly Estimate" approach card needs the same visibility gate as the new kickoff memo button — hide when `is_deliverable_enabled(client_id, "quarterly_memo")` is false. This is a tiny change to the modal's approach-card render logic.

**Test surface.** Two new service tests (`test_draft_quarterly_estimate_refuses_when_cadence_disabled` and `test_draft_quarterly_estimate_succeeds_when_cadence_enabled`). Plus a frontend test that the approach card is conditionally rendered. Both small.

**No journal entry semantics change.** The retrofit only refuses; existing successful-draft journal behavior is unchanged.

### §2.5 — API surface (Pydantic + FastAPI)

**New endpoints, mounted at `/api/clients/{client_id}/deliverables`:**

```
POST   /api/clients/{client_id}/deliverables/kickoff-memo/draft
  Body: { tax_year: int }
  Returns: { subject, body, references: { strategies, tasks }, warnings }
  Errors: 403 if non-admin; 403 if cadence-disabled; 200-with-warnings if no
          recommended strategies (modal renders warning, doesn't block).

POST   /api/clients/{client_id}/deliverables/kickoff-memo/send
  Body: { tax_year, subject, body, gmail_message_id (optional) }
  Returns: { client_communication_id }
  Errors: 403 if non-admin; 403 if cadence-disabled
```

The `draft` endpoint is stateless — it generates and returns; nothing persists between draft and send other than what the CPA copies into the modal state. Matches the quarterly estimate flow's stateless draft pattern.

**Pydantic schemas** in `backend/app/schemas/deliverables.py`. Naming follows the existing `cadence.py` and `strategy.py` schema conventions.

### §2.6 — Service-internal pieces

Building blocks v1 needs that the build sequence references:

1. **Context-assembler purpose addition.** `purpose='engagement_kickoff'` registered in the assembler's purpose table with the budget + priority above. Single-file change.
2. **Strategy + task pull helpers.** Two query helpers in `kickoff_memo.py`:
   - `_get_recommended_strategies(db, client_id) -> list[StrategyWithContext]`
   - `_get_client_facing_tasks_for_strategies(db, strategy_status_ids) -> list[ActionItemWithStrategy]`
   Both leverage existing models (Gap 2 ship). No new queries, no N+1 concerns expected at v1 client volumes.
3. **Prompt template** in `kickoff_memo.py`. String constant + `build_prompt` function that interpolates context.
4. **Handler registration** in `deliverables/__init__.py`. One line.

### §2.7 — Locked-in patterns from prior canon

Carry forward without restating in the build sequence:

- **Idempotent UPSERT-by-SELECT-then-update** for any DB writes that could be re-fired. Match the `materialize_implementation_tasks` precedent.
- **Journal entries on per-client state changes only.** Draft generation = journal entry. Send = journal entry. No journal on the GET history call. Mirrors cadence_service P2.
- **Validation before any DB write.** Cadence gate fires before context assembly. Reference-resolution failures refuse before LLM call.
- **`PermissionError` for cadence-disabled, `ValueError` for invalid input, `LookupError` for missing references** — exception taxonomy matches strategy_service + cadence_service.
- **Structured logging on draft + send** — match the cadence_service logging shape.

---

## §3 — Build sequence decomposition

### Sub-phase overview

Five sub-phases, sequenced for independent shippability and lowest-risk warm-up first:

| Phase | Description | Type | Surfaces touched |
|---|---|---|---|
| G5-P1 | Q5 retrofit — quarterly estimate cadence gate | Backend + tiny frontend | `quarterly_estimate_service`, `SendEmailModal` |
| G5-P2 | Context assembler `engagement_kickoff` purpose | Backend-only | `context_assembler` |
| G5-P3 | `engagement_deliverable_service` shell + kickoff memo handler | Backend-only | New service file, new handler module, schemas |
| G5-P4 | Kickoff memo API endpoints | Backend-only | New FastAPI router |
| G5-P5 | Kickoff memo modal + header trigger | Frontend-only | New components, header menu, `lib/api.ts` |

Total estimated effort: **5–7 hours of build time**. Each phase is one CC dispatch.

### G5-P1 — Quarterly estimate cadence gate retrofit

**Type:** Backend hygiene + tiny frontend. Single commit, single deploy. Lowest-risk phase; ships first to validate the cadence-gate pattern works in practice for a known-shipped deliverable before using it for a brand-new one.

**Scope.**

- Modify `quarterly_estimate_service.draft_quarterly_estimate_email()` (confirm exact function name during build via spot-check). Add `is_deliverable_enabled(db, client_id, "quarterly_memo")` guard at the top. Raise `PermissionError` if disabled.
- Add 2 service tests:
  - `test_draft_quarterly_estimate_refuses_when_cadence_disabled`
  - `test_draft_quarterly_estimate_succeeds_when_cadence_enabled` (defensive — ensures the gate isn't accidentally always-blocking)
- Update `SendEmailModal` to conditionally render the "Quarterly Estimate" approach card based on a new `enabledDeliverables` prop or a hook call to `getEnabledDeliverables(client_id)`. The cadence API endpoint already exists from G4-P3a; reuse it.
- 1 commit on `main` directly.

**Effort:** ~45 min.

**Acceptance:**
- 2 new backend tests pass
- Total backend tests: 437 passed, 1 skipped, 0 failed
- Frontend conditional render verified via component test or manual smoke
- Railway + Vercel deploys succeed
- Manual smoke: pick a client with cadence that disables `quarterly_memo`, verify the approach card hides; pick one where it's enabled, verify it shows

**Show-body gate:** confirm the diff is approximately ~10 backend lines + 2 tests + ~15 frontend lines before commit.

### G5-P2 — Context assembler `engagement_kickoff` purpose

**Type:** Backend-only. Single-file change to the unified context assembler.

**Scope.**

- Add `engagement_kickoff` to the assembler's purpose table with budget=6,000 and priority order: strategies (recommended) > implementation tasks (client-facing) > journal (last 30 days) > financials (current + prior year) > open action items > prior comms.
- Add 3 service tests:
  - `test_assembler_engagement_kickoff_returns_recommended_strategies`
  - `test_assembler_engagement_kickoff_filters_client_facing_tasks`
  - `test_assembler_engagement_kickoff_respects_token_budget`
- 1 commit.

**Effort:** ~45 min.

**Show-body gates.**
1. After writing the purpose entry + priority logic, before tests.
2. After writing tests, before commit.

**Acceptance.**
- 3 new tests pass
- Total: 440 passed, 1 skipped, 0 failed
- Existing assembler tests for other purposes unchanged

**Out of scope.** No frontend work, no API work, no new endpoints.

### G5-P3 — `engagement_deliverable_service` shell + kickoff memo handler

**Type:** Backend-only. New service file, new handler module, new Pydantic schemas. The biggest backend phase.

**Scope.**

- New file `backend/app/services/engagement_deliverable_service.py` with the three public functions per §2.2.
- New module `backend/app/services/deliverables/` with:
  - `__init__.py` registering `DELIVERABLE_HANDLERS = {"kickoff_memo": KICKOFF_MEMO_HANDLER}`
  - `_base.py` with the `DeliverableHandler` dataclass and `OpenItem` / `ContextBundle` / `ClientFacts` types
  - `kickoff_memo.py` with the handler, prompt builder, reference extractor, open-items extractor
- New schemas in `backend/app/schemas/deliverables.py`:
  - `DeliverableDraftResponse` (subject, body, references, warnings)
  - `RecordDeliverableSentRequest` (tax_year, subject, body, gmail_message_id?)
  - `ReferencesPayload`, `StrategyReference`, `TaskReference`
- Service tests in `backend/tests/services/test_engagement_deliverable_service.py` (~10–12 tests):
  - shell: cadence-gate refusal, unknown deliverable_key refusal, journal entry on draft, journal entry on send, send creates `client_communications` row with correct thread params, send creates thread row via `get_or_create_thread`, send idempotent under retry
  - handler: prompt includes recommended strategies, prompt excludes non-recommended, prompt excludes CPA-owned tasks, references payload shape, open-items extraction roundtrip, no recommended strategies returns warning
- 1 commit.

**Effort:** ~2.5–3 hours.

**Show-body gates.**
1. After writing `_base.py` + `kickoff_memo.py` (handler + prompt + extractors), before the shell service.
2. After writing `engagement_deliverable_service.py` (shell), before tests.
3. After writing tests, before commit.

**Acceptance.**
- ~10–12 new tests pass
- Total: ~450–452 passed, 1 skipped, 0 failed
- LLM-touching tests use the existing OpenAI mock pattern
- No regressions in existing service tests

**Out of scope.** No API endpoints (P4), no frontend (P5), no quarterly estimate refactor into the shell (Q4=b).

**Dependency.** P2 must ship first.

**Spot-check during build (per §5 item 5).** Confirm `get_or_create_thread`'s signature handles `thread_quarter=NULL` cleanly. If it doesn't, extend it to handle NULL — one source of truth for thread creation.

### G5-P4 — Kickoff memo API endpoints

**Type:** Backend-only. Thin FastAPI surface over the P3 service.

**Scope.**

- New router `backend/app/api/deliverables.py` mounted at `/api/clients/{client_id}/deliverables`:
  - `POST /kickoff-memo/draft` → calls `engagement_deliverable_service.draft_deliverable(deliverable_key="kickoff_memo")`
  - `POST /kickoff-memo/send` → calls `engagement_deliverable_service.record_deliverable_sent(deliverable_key="kickoff_memo")`
- Both endpoints require admin role (existing role-check decorator/dependency); both leverage the existing client access guard.
- Register the router in `backend/main.py`.
- API tests in `backend/tests/api/test_deliverables.py` (~6–8 tests):
  - 200 path for draft
  - 200 path for send
  - 200-with-warnings when no recommended strategies
  - 403 non-admin
  - 403 cadence-disabled (PermissionError → 403)
  - 403 cross-org client_id
  - 422 invalid `tax_year`
  - 403 cadence-disabled on send (symmetric gate)
- 1 commit.

**Effort:** ~1.5 hours.

**Show-body gates.**
1. After writing the router, before tests.
2. After writing tests, before commit.

**Acceptance.**
- ~6–8 new tests pass
- Total: ~456–460 passed, 1 skipped, 0 failed
- OpenAPI docs at `/docs` show the new endpoints
- Manual smoke: hit the draft endpoint via curl/httpie against a real client; verify response shape matches `DeliverableDraftResponse`

**Dependency.** P3 must ship first.

### G5-P5 — Kickoff memo modal + header trigger

**Type:** Frontend-only. The user-facing surface.

**Scope.**

- Add types + `createDeliverablesApi(getToken, orgId)` factory to `frontend/lib/api.ts`. Two methods: `draftKickoffMemo(clientId, taxYear)` and `sendKickoffMemo(clientId, payload)`. Match the `createCadenceApi` precedent shape.
- New components in `frontend/components/deliverables/`:
  - `DraftKickoffMemoButton.tsx` — header menu entry, gates on admin + `getEnabledDeliverables(clientId).includes("kickoff_memo")`
  - `KickoffMemoDraftModal.tsx` — the modal (generation state → review state → send state)
  - `StrategiesReferencedList.tsx` — chip list
  - `ClientFacingTasksList.tsx` — chip list
- Modify `frontend/app/dashboard/clients/[id]/page.tsx`: add the header menu entry render block. (Contingency: if the page header doesn't have a clean actions area, redirect placement to the Tax Strategies tab — show-body gate 1 below catches this.)
- Component tests in `frontend/__tests__/components/deliverables/` (~8–12 tests).
- 1 commit.

**Effort:** ~2 hours.

**Show-body gates.**
1. **Before any component code:** spot-check `frontend/app/dashboard/clients/[id]/page.tsx` to confirm the header has a clean actions area. If not, redirect placement to the Tax Strategies tab. Report finding.
2. After writing types + factory in `lib/api.ts`, before component work begins.
3. After writing all 4 components, before tests.
4. After writing tests, before commit.

**Acceptance.**
- ~8–12 new component tests pass
- Frontend unit total: ~127–131 passed
- Manual smoke on a real client (Tracy or own firm): cadence has `kickoff_memo` enabled, click the header button, modal opens, draft generates, modal renders strategies + tasks chips, edit subject/body, click Send, verify `client_communications` row written with `thread_type='engagement_year'`, verify journal entry written
- Visual QA: modal layout matches §1 sketch; chips read cleanly; loading/error states render
- Cross-deploy verify: Vercel deploy succeeds; Railway deploy unchanged

**Dependency.** P4 must ship first.

**Out of scope.**
- Playwright E2E for kickoff memo
- Save-as-draft persistence
- TaskDetailPanel inline button

### Sequence rationale

- **P1 first** — smallest, lowest-risk, validates the cadence-gate pattern on a known-shipped deliverable, ships a real product improvement.
- **P2 before P3** — P3's service depends on P2's assembler purpose existing.
- **P3 before P4** — P4 is a thin wrapper.
- **P4 before P5** — P5 needs real endpoints.
- **P5 last** — riskiest; if it surfaces "this should be on the Tax Strategies tab not the header," it's an isolated frontend-only redo.

### Total

~5–7 hours of build time across G5-P1 through G5-P5. Each phase independently shippable, independently revertible, show-body gates at the natural seams.

---

## §4 — Test surface plan

### Scope of this section

§3 itemizes per-phase tests as part of each phase's acceptance criteria. §4 provides the cross-cutting view: total coverage v1 is aiming for, what behaviors each test layer is load-bearing for, expected baseline arithmetic at session close, and what's deliberately out of scope.

### Test layers

| Layer | Test count (new) | Load-bearing for |
|---|---|---|
| Backend service unit | ~15–17 | Cadence gating, prompt construction, reference filtering, journal semantics, post-send tracking |
| Backend API integration | ~6–8 | HTTP surface contract, role gates, error shapes, OpenAPI accuracy |
| Frontend component unit | ~8–12 | Render gates, modal state machine, conditional UI based on cadence + role |

No Playwright. No backend integration tests (the existing `test_client_isolation` skip pattern continues). Manual smoke is the gate.

### §4.1 — Backend service unit (~15–17 new tests)

**G5-P1 (2 tests):**
- `test_draft_quarterly_estimate_refuses_when_cadence_disabled` — load-bearing for: the retrofit actually closes the gap.
- `test_draft_quarterly_estimate_succeeds_when_cadence_enabled` — load-bearing for: the gate isn't accidentally always-blocking.

**G5-P2 (3 tests):**
- `test_assembler_engagement_kickoff_returns_recommended_strategies`
- `test_assembler_engagement_kickoff_filters_client_facing_tasks`
- `test_assembler_engagement_kickoff_respects_token_budget`

**G5-P3 (~10–12 tests, two test classes):**

*`TestEngagementDeliverableServiceShell`:*
- `test_draft_refuses_when_cadence_disabled`
- `test_draft_refuses_unknown_deliverable_key`
- `test_draft_writes_journal_entry`
- `test_send_creates_client_communications_row_with_correct_thread_params`
- `test_send_creates_thread_via_get_or_create_thread`
- `test_send_writes_journal_entry`
- `test_send_idempotent_under_retry`

*`TestKickoffMemoHandler`:*
- `test_handler_prompt_includes_recommended_strategies`
- `test_handler_prompt_excludes_non_recommended_strategies`
- `test_handler_prompt_excludes_cpa_owned_tasks`
- `test_handler_references_payload_shape`
- `test_handler_no_recommended_strategies_returns_warning`

**What service tests deliberately don't cover:**
- The actual GPT-4o output quality. LLM responses are mocked; we test prompt construction and post-processing.
- Open-items extraction *correctness*. One roundtrip test included; semantic correctness mocked.
- Cross-org access. API-layer concern, not service-layer.

### §4.2 — Backend API integration (~6–8 new tests)

**G5-P4 (`test_deliverables_api.py`):**

- `test_draft_kickoff_memo_200_admin_enabled_with_strategies`
- `test_draft_kickoff_memo_200_with_warnings_when_no_recommended_strategies`
- `test_draft_kickoff_memo_403_non_admin`
- `test_draft_kickoff_memo_403_cadence_disabled`
- `test_draft_kickoff_memo_403_cross_org_client_id`
- `test_draft_kickoff_memo_422_invalid_tax_year`
- `test_send_kickoff_memo_200_writes_communication_row`
- `test_send_kickoff_memo_403_cadence_disabled`

**What API tests deliberately don't cover:**
- Database transaction rollback semantics
- Gmail send actual behavior

### §4.3 — Frontend component unit (~8–12 new tests)

**G5-P5 (`frontend/__tests__/components/deliverables/`):**

`DraftKickoffMemoButton.test.tsx` (3 tests):
- hidden when non-admin
- hidden when cadence-disabled
- visible + clickable when admin AND enabled; click invokes modal-open callback

`KickoffMemoDraftModal.test.tsx` (5–6 tests):
- renders "Generating draft..." state immediately on mount
- renders editable state with subject + body + chip lists when fetch resolves
- renders warnings banner when API returns non-empty `warnings` array
- renders error state with retry CTA on fetch failure
- "Send" button calls `sendKickoffMemo` API; on success, closes modal + emits success toast
- "Cancel" closes modal without API call

`StrategiesReferencedList.test.tsx` (1–2 tests):
- renders empty state when array is empty
- renders one chip per strategy

`ClientFacingTasksList.test.tsx` (1–2 tests):
- renders empty state when array is empty
- renders chip per task with owner_role badge + due date

### §4.4 — Manual smoke checklist (post-P5 deploy, before claiming v1 ship complete)

This is the v1 gate's actual evaluation. Per the April 29 brief, "ship one real Day-14 kickoff against own firm or Michael" is the data point that informs fan-out / fix / pivot.

- [ ] On a real client, header menu shows "Draft kickoff memo" entry (admin, cadence-enabled)
- [ ] Click opens modal in generating state
- [ ] Draft resolves within reasonable latency (<30s; flag if longer)
- [ ] Subject pre-fills correctly: `Engagement kickoff — [client_name] — [tax_year]`
- [ ] Body contains greeting, strategies block, client-facing tasks block, open questions, signoff
- [ ] Strategies chip list reflects only `recommended` strategies
- [ ] Tasks chip list reflects only client-facing tasks (no CPA-owned tasks visible)
- [ ] Edit subject + body inline; changes hold
- [ ] Click "Send via Gmail"; verify Gmail send fires
- [ ] `client_communications` row written with `thread_type='engagement_year'`, `thread_year=<tax_year>`, correct sender/recipient/subject/body
- [ ] `client_journal_entries` row written: category=`deliverable`
- [ ] Modal closes; success toast shows
- [ ] Re-invoke "Draft kickoff memo" — modal re-opens with fresh draft
- [ ] Disable `kickoff_memo` in the client's cadence; verify header menu entry hides
- [ ] Disable `quarterly_memo` in cadence; verify the existing `SendEmailModal` "Quarterly Estimate" approach card hides (P1 retrofit smoke)
- [ ] Non-admin user: header menu entry not rendered; direct API call returns 403

**The send is the gate.** Once a real kickoff memo is sent and the CPA reviews how it landed, the v1 milestone gate's "fan-out / fix / pivot" decision can be made. That review is its own session; this plan ends at the point where that review is possible.

### §4.5 — Test baseline arithmetic

| Phase | Backend tests added | Frontend unit added | Running backend total |
|---|---|---|---|
| Baseline (HEAD `3af62a9`) | — | — | 435 passed, 1 skipped |
| G5-P1 | +2 | tested via component test in P5 OR a tiny inline test (negligible) | 437 passed, 1 skipped |
| G5-P2 | +3 | — | 440 passed, 1 skipped |
| G5-P3 | +10 to +12 | — | 450–452 passed, 1 skipped |
| G5-P4 | +6 to +8 | — | 456–460 passed, 1 skipped |
| G5-P5 | — | +8 to +12 | 456–460 passed, 1 skipped (frontend: 127–131) |

**Expected end state at G5 close: ~458 backend tests passed, 1 skipped, 0 failed; ~129 frontend unit passed.**

Each phase's CC prompt should embed its expected-line as the gate (matching the discipline from the hygiene track's "Phase 3 expected-line" arithmetic catch).

### §4.6 — Tests deliberately NOT in scope for G5 v1

- Playwright E2E for kickoff memo
- Auto-create engagement-engine integration tests
- Cross-deliverable thread tests
- Quarterly estimate refactor tests
- GPT-4o output quality regression tests
- Performance / load tests
- Audit-log review tests

### §4.7 — Coverage philosophy

Service-level unit tests are the load-bearing layer; API tests are thin contract-shape verification; component tests are render-gate verification. Matches the cadence track's coverage shape (G4-P2 had 40 service tests vs. G4-P3 had ~12 API tests vs. G4-P4 had ~30 component tests).

The kickoff memo's logic is concentrated in:
- The cadence gate (P1 + P3 service tests cover it)
- The reference filtering (P2 + P3 service tests cover it twice — defense in depth)
- The post-send tracking (P3 service tests cover it)

These are the places a regression would silently break the deliverable. The tests above cover them at the right layer.

---

## §5 — Open questions / decisions to confirm before P1 build

These are the decisions still open in the plan as drafted. Each has a recommendation; flagging them here means no decision needs to be re-made mid-build session, and CC prompts can reference settled state.

### 1. Header menu entry posture for cadence-disabled clients

**Recommendation: hide entirely.** Aligns with G4-P4 settled pattern (Subscriptions / Organization sidebar entries hide for non-admins; cadence-disabled deliverables follow the same logic). Show-disabled creates a "why can't I click this?" UX hole.

**Cost of hiding:** A CPA who wants to send a kickoff memo to a client whose cadence excludes it has to first override-toggle it on. That friction is intentional — cadence is a menu, and overriding it should be a deliberate act.

**Confirm before P5 build.**

### 2. Header placement contingency: spot-check before P5 dispatch

P5's CC prompt opens with a `view` on `frontend/app/dashboard/clients/[id]/page.tsx` to confirm the actions area shape, then proceeds to the canonical placement OR the redirect target (Tax Strategies tab). The orchestrator approves the placement at show-body gate 1 of P5 before component code is written.

Not a ratification — a discipline note. Listed so the P5 prompt remembers to embed the spot-check as gate 1.

### 3. Manual override / one-off invocation for cadence-disabled clients

**Recommendation: defer to Gap 1.** Three reasons:

1. The use case brief's "manual invocation" language is in the context of the chat-command vocabulary (Gap 1), which the v1 gate sequences after this work. The header-menu UI is "the cadence-respecting one-off draft surface."
2. Adding a force flag in v1 means designing the override audit trail before the simpler path has shipped.
3. The CPA workflow for "I want to send a kickoff memo to a client who shouldn't get one" is: open the cadence tab, override-enable kickoff_memo, send, override-disable. Three clicks. The cadence override mechanism G4 shipped specifically supports this.

**Confirm before P3 build** (locks the service signature).

### 4. Open-items extraction: real or stubbed in v1

**Recommendation: run the existing extractor.** It's generic enough ("identify questions in this email body that await client response") that kickoff memo content should produce reasonable output. If the v1 smoke surfaces bad extractions, that's exactly the fan-out / fix / pivot data the v1 gate is set up to capture. Stubbing pre-empts that learning.

**Confirm before P3 build.**

### 5. `engagement_year` thread row creation: NULL `thread_quarter` handling

The plan has `record_deliverable_sent` calling `get_or_create_thread`. For kickoff memo, the natural thread key is `(client_id, thread_type='engagement_year', thread_year=tax_year)` with `thread_quarter=NULL`.

**Action item:** Confirm during P3 build by reading `get_or_create_thread`'s signature. If it handles NULL `thread_quarter` cleanly, no change needed. If it doesn't, extend it to handle NULL — one source of truth for thread creation.

Not a ratification; a P3 spot-check.

### 6. Tax year resolution for the "current engagement year"

**Recommendation: default to current calendar year.** Simple. CPA can edit. The modal has a tax_year input; the default is a convenience, not a constraint. Heuristic logic adds branching code that could be wrong in fiscal-year-aware scenarios anyway. Punt to a follow-up if smoke surfaces it as a real friction point.

**Confirm before P5 build.**

### 7. Naming: `engagement_deliverable_service`

The April 29 brief uses `engagement_deliverable_service` verbatim. Kept as-is. Listed only because once P3 ships, the file path is locked.

### 8. Carry-forward: when does deliverable #2 get planned

The v1 gate's binding sequence is: Gap 2 ✅ → Gap 4 ✅ → Gap 3 (kickoff-memo only) → Gap 1 (kickoff-memo-command only) → run one real Day-14 kickoff → decide.

This plan deliberately ends at the kickoff memo's send. The next planning effort is **Gap 1** (the chat command), not deliverable #2 (progress note). Deliverable #2 is gated on the post-smoke decision.

Logging here as the analog of G4-P4's §6 carry-forwards section.

### Items NOT listed in §5 (resolved by prior settling)

For audit clarity, decisions already settled in earlier sections:

- **Q1–Q6 scoping decisions** — settled before §1 drafted.
- **Thread type = `engagement_year`** — §2 settled.
- **Context purpose = `engagement_kickoff`** — §2 settled.
- **Handler registration = dataclass + dict** — §2 settled.
- **`draft_token` dropped** — §2 settled.
- **Edge case 4 = 200-with-warnings** — §2 settled.
- **5-phase split + P1 first** — §3 settled.
- **No Playwright in v1** — §3 settled.
- **P5 manual smoke = the v1 gate's evaluation event** — §3 settled.
- **No coverage % threshold** — §4 settled.
- **`test_send_idempotent_under_retry` retained** — §4 settled.

---

## §6 — Discipline reminders for the build sessions

Carrying forward from the hygiene track close, applicable to every G5 build prompt:

- Show-body gates between sub-phases (CC has skipped this on report-style outputs in the past; embed the rule both at top of prompt AND immediately before each output step). Use `sed -n` for narrow slices when a file is too long for the Read tool to display verbatim.
- `--force-with-lease` only if any force is needed; never plain `--force`
- Single canonical trunk: push to `origin/main` only; the GitHub Action handles `code/main` mirror
- Verify branch HEAD via `/commits/<branch>` URL, not `/tree/<branch>/<path>`
- After each G5 sub-phase deploy: verify Railway deploy ID + Vercel deploy ID + `lang/main HEAD == code/main HEAD` before claiming "synchronized"
- Mirror SHA-compare verification: `git fetch code-mirror && git log <branch> -1 --format="%H"` then string-match. Never rely on "Everything up-to-date" from manual pushes.
- No `git add .` / `-A`. Explicit paths only.
- No co-authored-by trailers.
- Two logical commits when surfaces are independent (the Track 2c voucher fixtures vs. client-isolation skip principle). For G5: each sub-phase is its own commit; the Q5 retrofit's backend service change and frontend SendEmailModal change can be one commit OR two depending on whether they're pushed together — orchestrator's call at P1 dispatch.
- Targeted test runs after each surface as cheap confidence checks.
- Embed the expected pytest-line in each phase's CC prompt as the gate.

---

*End of G5 planning artifact. Save to project knowledge as `AdvisoryBoard_G5_KickoffMemo_Plan.md` for reference during P1–P5 build sessions. Doc commits to `docs/AdvisoryBoard_G5_KickoffMemo_Plan.md` on `origin/main` in a separate CC dispatch following review.*

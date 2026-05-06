# G5-P3 Prep Decisions

**Status:** Planning prep. Not a build prompt. Output of the May 5, 2026 planning prep session.
**Purpose:** Resolve §5 items 3, 4, 5 of `AdvisoryBoard_G5_KickoffMemo_Plan.md`; settle the OpenAI mock pattern for P3's test surface; pre-empt plan-doc location bugs for P3 paths; carry an embedded G5-P3 audit prompt the next build session can dispatch as its first CC pass without reopening planning.
**Reference state at session open:** `origin/main` HEAD `ec88102` (G5-P2 close). Working tree clean. Backend tests 440 passed, 1 skipped, 0 failed. Mirror in sync. Both deploys green.
**Required reading at next session open:** §1 (this doc) → plan `AdvisoryBoard_G5_KickoffMemo_Plan.md` §2.1–§2.3, §3 G5-P3 → `session-summary-may-5-2026-g5-p2-ship.md`.

---

## §1 — Settled decisions (5)

Each decision: short rationale, integration spec, and (where the live-repo investigation has to defer to the audit pass) the audit hook that resolves it deterministically.

### Decision 1 — §5.3: Manual override / one-off invocation for cadence-disabled clients

**Outcome: RATIFY defer-to-Gap-1.** No `force` flag in `draft_deliverable`'s v1 signature.

**Rationale (consolidating the plan's three reasons + one fourth observation):**

1. The "manual invocation for a cadence-disabled client" use case is the chat-command path (Gap 1), which v1 sequences strictly after this work. The header-menu surface is the cadence-respecting one-off draft surface; it has no business handling overrides.
2. A `force` flag in v1 forces the override audit trail (who-approved, journal-entry shape, cadence-history UI surfacing) to be designed *before* the simpler path has shipped — exactly the kind of pre-emptive design the v1 milestone gate was committed to avoid.
3. The CPA workflow for "I want to send a kickoff memo to a client whose cadence excludes it" already exists: open the cadence tab → override-enable `kickoff_memo` → send → override-disable. Three clicks. The cadence override mechanism G4 shipped specifically supports this. Building a second override path bypasses the explicit one G4 just shipped.
4. (Carry-forward observation.) G4-P4d shipped configurable cadence per client *with* override semantics that already write journal entries. A v1 `force` flag would either duplicate that journal trail or skip it; either way it forks the audit-trail story. Deferring keeps one source of truth.

**Signature lock for `draft_deliverable`:**

```python
def draft_deliverable(
    db: Session,
    client_id: UUID,
    deliverable_key: str,
    tax_year: int,
    requested_by: UUID,
) -> DeliverableDraft:
    ...
```

No `force: bool = False`. No `override_reason: str | None = None`. The cadence gate at step 2 of the docstring is strict: `is_deliverable_enabled` returns false → `PermissionError`. Period.

**What this closes for P3:** the audit prompt does NOT need to reason about a force path; the action prompt does NOT need to design override audit-trail metadata; the test surface does NOT need a `test_draft_with_force_bypasses_gate` test. The taxonomy for cadence-disabled stays `PermissionError` cleanly.

**What this leaves open (deliberate, scoped to Gap 1):** when Gap 1 ships the chat-command surface, "draft kickoff memo for client X" through chat may need an override path. That's Gap 1's design problem; Gap 1 will either thread a `force` flag through `draft_deliverable` then (with audit trail), or model the chat command as the override-toggle UX itself (probably cleaner). Not P3's call.

---

### Decision 2 — §5.4: Open-items extraction in v1 (real, not stubbed)

**Outcome: RATIFY running the existing GPT-4o-mini extractor.** Stubbing in v1 would pre-empt exactly the smoke signal the v1 gate is structured to capture.

**Rationale (concise):**

The existing extractor was shipped in the April 7 communication threading work alongside `get_or_create_thread`, `get_thread_history`, `get_thread_open_items`, and `resolve_open_items` (per `session-summary-april-7-2026.md` line 83). It's generic over email-body content — the prompt is "identify questions in this email body that await client response." A kickoff memo's body shape (greeting + strategies block + client-facing tasks block + open questions + signoff) is well-suited to this extractor; the open-questions section is, by construction, what the extractor is built to find.

If smoke surfaces bad extractions on real kickoff memo content, that data is exactly what the v1 gate's fan-out / fix / pivot decision needs. Stubbing kills the signal.

**Integration spec for `_extract_open_items_from_kickoff` in `kickoff_memo.py`:**

The handler's `extract_open_items` callable receives the sent email body string and returns `list[OpenItem]` (per `_base.py` typed contract). It calls the existing extractor over the body and shapes the return. The kickoff memo handler does NOT reimplement extraction — it delegates.

```python
# backend/app/services/deliverables/kickoff_memo.py

async def _extract_open_items_from_kickoff(body: str) -> list[OpenItem]:
    """
    Delegates to the existing GPT-4o-mini open-items extractor (April 7 ship).
    Identical pattern to quarterly estimate's open-items extraction.
    """
    raw = await extract_open_items_from_email(body)  # exact import path resolved in audit
    return [OpenItem.model_validate(item) for item in raw]
```

**Audit-pass spot-checks (deterministic mapping to action prompt):**

The audit must establish three things about the existing extractor before the action prompt can write the integration:

1. **Exact import path.** Plan §2.3 says "April 7 precedent." Likely candidates:
   - `from app.services.communication_service import extract_open_items_from_email`
   - `from app.services.quarterly_estimate_service import extract_open_items_from_email`
   - `from app.services.thread_service import extract_open_items_from_email` (if a dedicated module exists)
2. **Sync vs. async.** The April 7 ship used GPT-4o-mini, which through the OpenAI SDK is async. Almost certainly `async def`. Audit confirms.
3. **DB session requirement.** Likely no — the extractor takes a body string and calls the LLM directly. Audit confirms.
4. **Return shape.** Plan says JSONB-shaped. Confirm the dict shape matches the `OpenItem` dataclass / Pydantic model the handler will use.

**Action-prompt mapping based on audit findings:**

| Audit finding | Action prompt embeds |
|---|---|
| Function exists, async, no DB, dict return | Use the integration spec above verbatim. |
| Function exists, sync | Wrap in `asyncio.to_thread` or just call sync from the post-processing path. |
| Function exists but takes more args than `body` (e.g., `client_id` for context) | Action prompt extends the handler call signature; rest of contract unchanged. |
| Function doesn't exist where plan claims | Defer extraction to a follow-up sub-phase; ship `extract_open_items=None` on the kickoff memo handler for v1, populate `client_communications.open_items` JSONB as `[]`. Surface as carry-forward. |

The fourth row is the safety net; v1 still ships if the precedent isn't where we expect. But the v1 gate's smoke value is highest with extraction running, so the audit should aggressively try the first three resolutions before falling back.

---

### Decision 3 — §5.5: `get_or_create_thread` NULL `thread_quarter` handling

**Outcome: framework settled here; investigation deferred to the audit pass as a load-bearing opening spot-check.**

**Why I can't resolve this fully in this session.** The decision needs the function's actual signature and one caller. `/mnt/project/` has the plan, summaries, and architectural docs but not the live `backend/app/services/communication_service.py` (or wherever `get_or_create_thread` lives — see Decision 2 audit hooks). The April 7 summary confirms the function exists; it does not record its signature.

**Three contingent specs (audit picks one, action prompt embeds verbatim):**

**Finding A — Already handles NULL cleanly.**

Signature looks something like:

```python
def get_or_create_thread(
    db: Session,
    client_id: UUID,
    thread_type: str,
    thread_year: int,
    thread_quarter: int | None = None,  # ← already nullable in signature AND used as nullable in lookup
) -> ClientCommunicationThread:
    ...
```

Action prompt: `record_deliverable_sent` calls `get_or_create_thread(db, client_id, thread_type=handler.thread_type, thread_year=tax_year, thread_quarter=None)` directly. Zero changes to `get_or_create_thread`. P3 ships only the new files.

**Finding B — Doesn't handle NULL, but the change is trivial.**

Signature has `thread_quarter` typed `int` (not optional), or the lookup query uses `==` against the param without distinguishing NULL. Trivial change spec:

```python
# in get_or_create_thread, change the lookup clause from:
.filter(ClientCommunicationThread.thread_quarter == thread_quarter)
# to:
.filter(
    ClientCommunicationThread.thread_quarter.is_(None)
    if thread_quarter is None
    else ClientCommunicationThread.thread_quarter == thread_quarter
)
```

And widen the param type to `int | None`. Add one new test in `test_quarterly_estimate_service.py` or wherever `get_or_create_thread` is currently tested: `test_get_or_create_thread_handles_null_quarter`. Same commit as P3.

**Finding C — Doesn't handle NULL and the change is non-trivial.**

(E.g., the function has multiple call sites that depend on quarter-required semantics, or there's a unique constraint on `(client_id, thread_type, thread_year, thread_quarter)` that PostgreSQL treats NULL inconsistently with, requiring a partial index or a sentinel-value approach.)

Spec: split into a sub-phase G5-P3a (extend `get_or_create_thread` to handle NULL with appropriate test coverage and any DB migration the unique constraint needs) before G5-P3b (the deliverable service shell). The audit surfaces this; the orchestrator decides whether to widen P3 or split. Default position: split, because compounding a thread-system change with a brand-new service ships faster as two reviewable commits than as one fat one.

**Audit-pass instructions for resolving:**

```
view backend/app/services/communication_service.py  # or wherever get_or_create_thread lives
grep -rn "get_or_create_thread" backend/app/  # confirm callers
view tests/services/test_*.py | grep -A 5 "get_or_create_thread"  # confirm existing test coverage
```

Audit's deliverable: file path + signature + caller list + decision A/B/C with short rationale.

---

### Decision 4 — OpenAI mock pattern for P3's test surface

**Outcome: hybrid pattern — most tests don't mock at all (handler tests assert against the pure prompt-builder), the few that do use decorator-based `@patch` at the deliverable service's import boundary. No session-scoped fixture in `conftest.py`.**

**Rationale.**

The P2 close summary (line 142) confirmed zero `AsyncOpenAI` / embedding mocks anywhere in the test suite. The G5-P1 observation (line 154–156) noted that `draft_quarterly_estimate_email` ran to completion without exception when the cadence gate let the call through, which is consistent with either a fallback path in the function OR an env-driven LLM-disable in test mode OR a global autouse mock that's been overlooked. The audit must distinguish between these — but the *recommendation* doesn't change with the answer:

- If there's a global mock, decorator-based per-test patches still work and are clearer at the test site.
- If there's an env-driven disable, decorator-based patches still work and are clearer.
- If there's neither, decorator-based patches are required.

In all three branches, decorator-based wins. Session-scoped fixture in `conftest.py` is overkill for the first ever AsyncOpenAI patch in the codebase — it solves a coordination problem that doesn't exist yet. Establishing the pattern as decorator-based now lets a future fixture refactor happen if/when it becomes worth it (probably never for the MVP).

**Test-surface decomposition — what each P3 test actually needs:**

Walking the 12 tests from plan §4.1:

*`TestEngagementDeliverableServiceShell` (7 tests):*

| Test | LLM mock needed? |
|---|---|
| `test_draft_refuses_when_cadence_disabled` | No — `PermissionError` raises before LLM call. |
| `test_draft_refuses_unknown_deliverable_key` | No — `ValueError` raises before LLM call. |
| `test_draft_writes_journal_entry` | **Yes** — needs draft to complete to verify journal entry. |
| `test_send_creates_client_communications_row_with_correct_thread_params` | **Yes** — open-items extractor mock if extractor runs in `record_deliverable_sent`. |
| `test_send_creates_thread_via_get_or_create_thread` | Same as above. |
| `test_send_writes_journal_entry` | Same as above. |
| `test_send_idempotent_under_retry` | Same as above. |

*`TestKickoffMemoHandler` (5 tests):*

| Test | LLM mock needed? |
|---|---|
| `test_handler_prompt_includes_recommended_strategies` | No — call `_build_kickoff_prompt` directly, assert the returned string. Pure prompt-builder. |
| `test_handler_prompt_excludes_non_recommended_strategies` | No — same. |
| `test_handler_prompt_excludes_cpa_owned_tasks` | No — same. |
| `test_handler_references_payload_shape` | No — call `_extract_strategies_and_tasks` directly. |
| `test_handler_no_recommended_strategies_returns_warning` | Depends on whether the warning is inserted pre-LLM (in the shell, before `build_prompt` even runs) or post-LLM (in the handler's draft post-processing). Plan §1 edge case 2 implies pre-LLM — handler returns `references: { strategies: [] }`, the shell wraps the LLM call with a warning. **Likely no.** Audit confirms. |

**5 tests definitely need a mock (the four send-path tests + `test_draft_writes_journal_entry`); 7 don't (5 handler tests + 2 refusal tests).**

This shape lets P3 establish the mock pattern with low-blast-radius application: only 5 tests touch it. If the pattern is wrong, only those 5 break.

**Mock decoration target:**

`@patch("app.services.engagement_deliverable_service.AsyncOpenAI")` — patches at the consumer's import boundary, not at `openai.AsyncOpenAI`'s definition. This is the standard pattern and matches how `unittest.mock.patch` is meant to work. If `engagement_deliverable_service.py` does `from openai import AsyncOpenAI`, then `app.services.engagement_deliverable_service.AsyncOpenAI` is the right target.

For the open-items extractor mock (called in `record_deliverable_sent` post-processing, not at the LLM client level), the natural patch target is the extractor function itself, not the underlying OpenAI client:

`@patch("app.services.engagement_deliverable_service._call_extract_open_items")` — or whatever the import line in `engagement_deliverable_service.py` resolves to once the audit confirms the existing extractor's location (Decision 2).

**Skeleton — a representative shell test:**

```python
# backend/tests/services/test_engagement_deliverable_service.py

from unittest.mock import patch, AsyncMock, MagicMock
import pytest
from app.services import engagement_deliverable_service as eds


class TestEngagementDeliverableServiceShell:

    @patch("app.services.engagement_deliverable_service.AsyncOpenAI")
    @pytest.mark.asyncio
    async def test_draft_writes_journal_entry(self, mock_openai_cls, db, make_org, make_user, make_client):
        # Configure mock AsyncOpenAI client to return a canned chat completion.
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=MagicMock(choices=[MagicMock(message=MagicMock(content="Subject\n\nBody"))])
        )
        mock_openai_cls.return_value = mock_client

        org = make_org(); user = make_user(org_id=org.id)
        client = make_client(org_id=org.id)
        # ... seed cadence enabling kickoff_memo, seed at least one recommended strategy ...

        draft = await eds.draft_deliverable(
            db, client_id=client.id, deliverable_key="kickoff_memo",
            tax_year=2026, requested_by=user.id,
        )

        assert draft.subject and draft.body
        # Journal entry assertion:
        entries = db.query(ClientJournalEntry).filter_by(
            client_id=client.id, category="deliverable",
        ).all()
        assert len(entries) == 1
```

**A representative pure-prompt handler test (no mock):**

```python
class TestKickoffMemoHandler:

    def test_handler_prompt_includes_recommended_strategies(self, db, make_org, make_client):
        from app.services.deliverables.kickoff_memo import _build_kickoff_prompt
        from app.services.deliverables._base import ContextBundle, ClientFacts

        # Construct a minimal ContextBundle + ClientFacts directly — no DB, no LLM.
        bundle = ContextBundle(
            strategies=[{"id": "...", "name": "Augusta Rule", "status": "recommended", ...}],
            action_items=[...],
            journal=[], financials={}, comms=[],
        )
        facts = ClientFacts(name="Tracy Chen DO, Inc", entity_type="C-Corp", tax_year=2026)

        prompt = _build_kickoff_prompt(bundle, facts)

        assert "Augusta Rule" in prompt
        assert "Tracy Chen DO, Inc" in prompt
        assert "2026" in prompt
```

**Audit-pass spot-checks (confirmation, not investigation):**

1. `grep -n "AsyncOpenAI\|patch.*openai\|monkeypatch.*openai" backend/tests/conftest.py` — confirm zero hits. If there ARE hits (P2 noted there were none, but a one-line confirmation is cheap), the action prompt either uses the existing fixture or layers decorator-based patches over it.
2. `grep -rn "AsyncOpenAI" backend/app/services/` — once `engagement_deliverable_service.py` exists, this grep will surface its import line. Pre-creation, it shows where AsyncOpenAI is currently constructed (likely `quarterly_estimate_service.py` and `communication_service.py`). The action prompt mirrors that import shape.
3. `grep -rn "OPENAI_API_KEY\|OPENAI_MODEL" backend/tests/conftest.py backend/.env*` — confirms whether there's an env-driven test-mode disable. Doesn't change the recommendation but informs whether a `test_draft_writes_journal_entry`-style test even needs the mock to *succeed* (vs. just to return a deterministic body).

The hybrid pattern (most tests no-mock, 5 tests with decorator) ships regardless of what the audit surfaces.

---

### Decision 5 — `engagement_deliverable_service` file path and handler module path spot-check

**Outcome: paths planned in §2.2/§2.3 are the right paths; pre-empt any leftover/stub collisions via an opening `ls` block in the audit prompt.**

**Why I can't resolve this fully in this session.** Same constraint as Decision 3: I have project knowledge but not the live repo filesystem. The G5 track has surfaced two plan-doc location bugs already (G5-P1: `communication_service` → `quarterly_estimate_service`; G5-P2: `context_assembler_service` → `context_assembler.py`). Pattern recommendation from the P2 carry-forwards: spot-check P3's planned paths before dispatch.

**Planned paths (from plan §2.2, §2.3, §2.5, §3 G5-P3 acceptance):**

| Path | Status | Spot-check |
|---|---|---|
| `backend/app/services/engagement_deliverable_service.py` | Will be created. | `ls backend/app/services/engagement_deliverable_service.py` |
| `backend/app/services/deliverables/__init__.py` | Will be created. | `ls backend/app/services/deliverables/` |
| `backend/app/services/deliverables/_base.py` | Will be created. | (covered above) |
| `backend/app/services/deliverables/kickoff_memo.py` | Will be created. | (covered above) |
| `backend/app/schemas/deliverables.py` | Will be created. | `ls backend/app/schemas/deliverables.py` |
| `backend/tests/services/test_engagement_deliverable_service.py` | Will be created. | `ls backend/tests/services/test_engagement_deliverable_service.py` |

**Likely outcome:** all six `ls` calls return "No such file or directory." Action prompt creates all six from scratch. P3 dispatch is "create" not "extend or replace."

**Action-prompt mapping based on audit findings:**

| Finding | Action prompt embeds |
|---|---|
| All six paths absent (expected) | Create all six. P3 unchanged from plan §3. |
| `engagement_deliverable_service.py` exists as a stub (e.g., empty file or `# TODO` placeholder) | Surface; orchestrator decides between `git rm` + create-fresh (clean) or extend-in-place (preserves the stub's commit history if it has any). Default: clean replace if the file is empty or trivial. |
| `deliverables/` directory exists with unexpected contents | Surface and stop. This would be a real surprise — investigate before action. |
| `schemas/deliverables.py` exists | Likely a leftover; surface, decide replace-vs-extend at show-body gate 1. |

The audit spends ~30 seconds running these `ls` calls and reports a single line per path. Cheap, deterministic.

**Plan-doc location-bug pre-emption note.** P3 differs from P1/P2 in that P3's primary deliverables are *new files* — there's no existing-file location to be wrong about. The location-bug risk is concentrated in the files P3 *imports from*: `cadence_service.is_deliverable_enabled` (confirmed at P1, file `backend/app/services/cadence_service.py` line 55), the open-items extractor (Decision 2 audit), `get_or_create_thread` (Decision 3 audit), and the context assembler (`backend/app/services/context_assembler.py`, confirmed P2). The audit covers all four. No additional location-bug surface for P3 beyond what Decisions 2 and 3 already track.

---

## §2 — G5-P3 audit prompt (read-only investigation pass)

The next build session opens with this prompt as the first CC dispatch. It's explicitly read-only — no edits, no commits, no test runs. Output is a markdown report the orchestrator reviews before dispatching the action prompt.

```
You are running the G5-P3 audit pass for the engagement_deliverable_service shell + kickoff memo handler. This is a READ-ONLY investigation. Do not edit files, do not run tests, do not commit. Output a markdown report with the findings below.

## Context
- HEAD: ec88102 (G5-P2 close, engagement_kickoff context purpose registered)
- Plan: docs/AdvisoryBoard_G5_KickoffMemo_Plan.md §2.2, §2.3, §3 G5-P3, §4.1 G5-P3
- Prep decisions: docs/AdvisoryBoard_G5_P3_Prep_Decisions.md (read this first; the decisions below assume you've absorbed it)

## Decisions already settled (do NOT re-litigate)
- §5.3 manual override: defer to Gap 1; no force flag in draft_deliverable. Signature locked per prep doc.
- §5.4 open-items extraction: real, not stubbed. Delegates to existing GPT-4o-mini extractor.
- OpenAI mock pattern: hybrid — handler tests no-mock (pure prompt builder), 5 shell tests use decorator @patch at the service's AsyncOpenAI import boundary. No conftest fixture.

## Investigations (in order)

### A — Path-existence audit (Decision 5)

Run each ls and report the exact stdout/stderr verbatim:
1. ls backend/app/services/engagement_deliverable_service.py
2. ls backend/app/services/deliverables/
3. ls backend/app/schemas/deliverables.py
4. ls backend/tests/services/test_engagement_deliverable_service.py

Expected: all four "No such file or directory." Surface anything else.

### B — get_or_create_thread signature audit (Decision 3)

1. Find the file containing get_or_create_thread:
   grep -rn "def get_or_create_thread" backend/app/

2. Show the full function signature + first 30 lines of the body. Use `view` with view_range.

3. Find all current callers:
   grep -rn "get_or_create_thread(" backend/app/ backend/tests/

4. Inspect existing tests for it:
   grep -rn "get_or_create_thread" backend/tests/

5. Categorize the finding as A/B/C per Decision 3 of the prep doc:
   - A: Already handles NULL cleanly. Quote the relevant code as evidence.
   - B: Trivial change needed. Show the current line that fails on NULL and the trivial change.
   - C: Non-trivial change needed. Explain why and recommend whether to split into G5-P3a (thread fix) + G5-P3b (deliverable service) or to widen P3.

### C — Open-items extractor audit (Decision 2)

1. Find the function:
   grep -rn "def extract_open_items_from_email\|async def extract_open_items_from_email" backend/app/

2. Show its signature + first 20 lines.

3. Confirm:
   - import path
   - sync vs async
   - DB session arg present? yes/no
   - return shape (dict, list of dicts, OpenItem dataclass, etc.)

4. Map to Decision 2's contingency table; report which row applies.

### D — OpenAI mock posture audit (Decision 4)

1. grep -n "AsyncOpenAI\|monkeypatch.*openai\|patch.*openai\|patch.*AsyncOpenAI" backend/tests/conftest.py
   Report verbatim. Expected: zero hits per P2 close summary.

2. grep -rn "from openai import\|import openai" backend/app/services/
   Report which services currently import the OpenAI client and from which import path.

3. grep -rn "OPENAI_API_KEY\|OPENAI_MODEL" backend/tests/conftest.py backend/.env* 2>/dev/null
   Report verbatim. Establishes whether there's an env-driven test-mode disable.

4. Look at how quarterly_estimate_service.py constructs its AsyncOpenAI client (or wherever it calls). Show the import + construction pattern. The new engagement_deliverable_service.py should mirror this.

### E — Existing test fixture conventions audit

1. view backend/tests/conftest.py (full file if reasonable, or show signature of every fixture and the make_* helpers)
2. view backend/tests/services/test_quarterly_estimate_service.py (referenced by P1/P2 as the idiom)
3. view backend/tests/services/test_context_assembler.py (created by P2, freshest example of "new test file from scratch")

Identify:
- The db fixture name + scope
- make_org / make_user / make_client signatures
- The convention for seeding TaxStrategy (P2 carry-forward: required_flags=[] must be passed explicitly to avoid SQLite JSON deserialization failure)
- Whether async tests use @pytest.mark.asyncio or some auto-mode
- Any existing patterns for seeding ClientStrategyStatus and ActionItem with the Gap 2 columns (strategy_implementation_task_id, client_strategy_status_id, owner_role)

### F — _base.py type contract audit

The handler dataclass needs ContextBundle, ClientFacts, OpenItem types. Plan §2.2 lists them but doesn't specify whether they're new types or imported from somewhere existing.

1. grep -rn "ContextBundle\|ClientFacts\|class OpenItem" backend/app/
2. If any exist, report the file + signature. The action prompt either reuses or shadows.
3. If none exist, the action prompt creates them in _base.py.

### G — Naming and registration spot-checks

1. Confirm the cadence ENUM value. The plan uses "kickoff_memo" verbatim:
   grep -rn "kickoff_memo" backend/app/models/ backend/app/schemas/

2. Confirm context_purpose value matches plan:
   grep -rn "engagement_kickoff" backend/app/

   Expected: hits in context_assembler.py (P2 ship) and schemas/context.py.

## Output shape

Single markdown report with one section per investigation (A–G). Each section:
- Verbatim grep/ls/view output where the decision depends on it.
- One-line "Finding:" summary.
- Mapping to the prep doc's contingency table where applicable.

End the report with a "Open questions for orchestrator" section listing any surprises (file existed where expected to be absent, signature didn't match, etc.). If there are no surprises, say so explicitly.

DO NOT proceed to action. The orchestrator reviews the audit, then dispatches the action prompt separately.
```

---

## §3 — What the next session inherits

This artifact is the required-reading preamble for the next build session. With it absorbed:

- **§5 items 3, 4, 5 are all settled or framework-settled.** No mid-build re-litigation.
- **OpenAI mock pattern is locked.** Decorator-based per-test, applied to 5 of 12 P3 tests. Skeleton above.
- **Path-existence and signature audits are pre-specified as the audit pass's first task.** Findings deterministically map to action-prompt branches.
- **Plan-doc location bugs for the P3 import surfaces are pre-empted.** Audit covers `is_deliverable_enabled` (already confirmed P1), open-items extractor, `get_or_create_thread`, and the context assembler.

**Action-prompt drafting is deferred to the next session, after the audit returns.** The audit's findings inform whether the action prompt's branch table picks A/B/C for `get_or_create_thread` (Decision 3) and whether the open-items extractor integration uses the canonical or fallback shape (Decision 2). Drafting the action prompt now would mean drafting four versions of the same prompt; deferring saves three of them.

**Out of scope for this session (deliberate, listed for completeness):**
- §5 items 1, 2, 6 — apply to P5 (frontend); not P3's concern.
- §5 items 7, 8 — already settled / are carry-forwards.
- Plan-doc edits for the two G5 location bugs (G5-P1: `communication_service` → `quarterly_estimate_service`; G5-P2: `context_assembler_service` → `context_assembler.py`) — captured here as a hygiene-task carry-forward; defer to a separate pass.

---

## §4 — Carry-forwards from this session

1. **Plan doc still has two unfixed location bugs from G5-P1 and G5-P2.** Tracked in the P2 close summary line 123–130 and not addressed here. Hygiene task: edit `docs/AdvisoryBoard_G5_KickoffMemo_Plan.md` §3 G5-P1 and §3 G5-P2 to reflect actual file paths. Single dispatch when convenient. Not blocking P3.
2. **Decisions 2, 3, 5 carry residual investigation into the audit pass by design.** This is the right shape for planning prep when the live repo isn't directly accessible from the planning surface; the framework + contingency table makes the audit's findings deterministic without reopening planning.
3. **Hybrid mock pattern establishes a precedent.** Once P3 ships with decorator-based per-test patches, that's the codebase convention for AsyncOpenAI mocking going forward. Future deliverables (#2 progress note, etc.) inherit it. If the post-smoke decision triggers fan-out, the pattern is already in place.

---

*End of G5-P3 prep decisions artifact. Save as `docs/AdvisoryBoard_G5_P3_Prep_Decisions.md` on `origin/main` in the next planning prep dispatch (or hold for review).*

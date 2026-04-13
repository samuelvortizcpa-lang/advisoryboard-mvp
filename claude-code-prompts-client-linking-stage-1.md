# Claude Code Prompts — Client Linking, Stage 1

**Purpose:** Session prompts for implementing Stage 1 of the client linking architecture. Stage 1 ships schema, retrieval scope change, and manual linking UI as a single PR. No auto-detection, no classifier expansion, no gap surfacing — those are Stages 2–4.

**Prerequisites before starting this session:**
- `client-linking-architecture.md` exists in the project root and has been read
- Michael Tjahjadi's baseline eval is holding at 9/10 real correctness, 10/10 header-clean (reference: `a8552383-f908-476b-b51f-286f7131abb6`)
- The voucher classifier fix (Priority 3 from April 12) has shipped — otherwise Michael's classifier row contamination will confuse cross-entity testing later
- Clean branch: `git checkout -b feat/client-linking-stage-1` off main

**How to use this file:** Do not paste the whole thing at once. Paste the Opening Context first, then paste each Part when you reach its checkpoint. This keeps Claude Code's working memory focused.

---

## Opening Context (paste first)

I'm implementing Stage 1 of the client linking architecture for Callwen. The full design is in `client-linking-architecture.md` in the project root — read it first before doing anything else. This session ships Stage 1 as a single PR: schema, retrieval scope change, and manual linking UI. No auto-detection, no classifier expansion, no gap surfacing — those are later stages.

**The problem this solves:** CPAs' CRMs model "Michael Smith" (1040) and "Smith Consulting LLC" (1120S) as two separate client records. When Callwen imports a client list, the chat on Michael cannot see Smith Consulting's 1120S because it's filed under a different `client_id`. Stage 1 makes it possible to manually link two client records so the chat retrieves across both.

**Non-negotiables:**
- Links are always human → entity. Never human → human, never entity → entity.
- Use explicit `client_kind` column (option A from the architecture discussion), not implicit classification.
- `client_kind` is enforced at link creation: `human_client_id` must resolve to `client_kind = 'individual'`, `entity_client_id` must resolve to a business/trust kind.
- Default chat scope is the full linked group. Narrowing is one click away via a header dropdown.
- No data moves between client records. Linking is metadata only.
- Billing, 7216 consent, audit logs remain per-client and completely unchanged.
- Shared entities are allowed (Michael and Bob can both link to Acme) but humans never traverse through a shared entity to reach each other.

**Commit discipline:**
- One commit per Part, conventional commit messages (shown in each Part below)
- Every commit must leave the system in a working state
- Branch: `feat/client-linking-stage-1` off main
- Open PR as draft after Checkpoint 3
- Use Superpowers PR workflow for pushes

**Security reminders:**
- Never echo `$ADMIN_KEY` or any secret. Use `[ ${#ADMIN_KEY} -eq 64 ] && echo "length ok"` for length checks only.
- Always `read -rs` for loading secrets. Clear clipboard with `pbcopy < /dev/null` after any paste.
- If a credential is flagged as exposed at any point, rotate it before continuing.

Ready for Part 1 when you confirm you've read `client-linking-architecture.md` and understand the human→entity invariant and the shared-entity privacy case.

---

## Part 1 — Schema Migration

Create an Alembic migration that:

1. Adds `client_kind` column to `clients`: enum of `individual`, `s_corp`, `partnership`, `c_corp`, `trust`, `disregarded_llc`, `sole_prop`, `unknown`. Default `unknown`. NOT NULL.
2. Backfills existing clients: if a client has any document classified as `Form 1040`, set `client_kind = 'individual'`. Leave everything else as `unknown` for now — we'll resolve those manually or with the Stage 2 classifier expansion.
3. Creates the `client_links` table exactly as specified in `client-linking-architecture.md` under "New table: client_links". Use the column definitions verbatim.
4. Adds the two partial indexes on `client_links` for `confirmed_by_user = TRUE`.
5. Adds a CHECK constraint or trigger enforcing that `human_client_id` refers to a client with `client_kind = 'individual'` and `entity_client_id` refers to a client with `client_kind IN ('s_corp', 'partnership', 'c_corp', 'trust', 'disregarded_llc', 'sole_prop')`. Use a trigger if CHECK can't reference other tables in Postgres.
6. Before writing the migration, check the latest Alembic head with `alembic heads` and confirm the new migration descends from it cleanly. No duplicate heads, no orphan branches.

Run the migration against local, confirm it applies cleanly and is reversible (`alembic downgrade -1` then `alembic upgrade head`).

**STOP — CHECKPOINT 1:** Show me the migration file, the `alembic heads` output before and after, and the backfilled `client_kind` distribution from `SELECT client_kind, COUNT(*) FROM clients GROUP BY client_kind`.

Commit: `feat(schema): add client_links table and client_kind column`

---

## Part 2 — Group Resolution Helper

In `backend/app/services/client_groups.py` (new file), implement `resolve_client_group(client_id: UUID, db: Session) -> list[UUID]` that returns all client IDs in the linked group starting from the given client. Use the recursive CTE from `client-linking-architecture.md` under "Group Resolution". Only follow links where `confirmed_by_user = TRUE`. Cache the result per-request using whatever request-scoped cache pattern already exists in the codebase — grep for existing cache decorators before inventing one.

Write unit tests in `backend/tests/test_client_groups.py` covering:

- Solo client (no links) returns `[client_id]`
- Human linked to one entity returns both IDs
- Human linked to three entities returns all four IDs
- **Two humans both linked to the same entity: each human's group contains themselves + the entity, but NOT the other human** (the shared-entity privacy case — this is the critical test)
- Dismissed/unconfirmed links are excluded
- Starting from an entity resolves to the same group as starting from its linked human

Run the tests.

**STOP — CHECKPOINT 2:** Show me test results and the shared-entity test in particular, because that's the privacy-critical case.

Commit: `feat(retrieval): add client group resolution helper`

---

## Part 3 — Retriever Scope Change

Find the retrieval entry point(s) that currently filter documents by `client_id`. Grep for `client_id = ` and `client_id==` in `backend/app/services/` to locate them. There should be one primary path through the hybrid search; flag any others you find.

Change the filter from `client_id = :client_id` to `client_id = ANY(:group_client_ids)` where `group_client_ids` comes from `resolve_client_group`. This should be a minimal diff — if you're rewriting more than ~20 lines of retrieval code, stop and show me what you're touching.

**Do not change the chat endpoint's public API.** The endpoint still takes a single `client_id`. The group expansion happens inside the retrieval layer, invisibly to the API caller. This keeps the frontend chat code untouched for now.

Run the existing RAG eval against Michael Tjahjadi (client `92574da3-13ca-4017-a233-54c99d2ae2ae`) via the Run Eval button or endpoint. Michael has no links yet so his group is `[michael]` — **the eval must return the same 9/10 real correctness, 10/10 header-clean baseline as `a8552383-f908-476b-b51f-286f7131abb6`**. If it regresses, stop and diagnose before proceeding. This is the non-negotiable regression gate.

**STOP — CHECKPOINT 3:** Show me the eval result ID, the retrieval hit rate, and the real correctness score. No moving forward until Michael's baseline holds. **Open draft PR at this checkpoint.**

Commit: `feat(retrieval): expand document scope to full client group`

---

## Part 4 — Link Management API

Add endpoints:

- `POST /api/clients/{client_id}/links` — creates a link. Body: `{entity_client_id, link_type, ownership_pct, filing_responsibility}`. Validates `client_kind` on both sides. Sets `confirmed_by_user = true`, `detection_source = 'manual'`, `detection_confidence = 1.00`, `confirmed_at = now()`. Returns the created link.
- `GET /api/clients/{client_id}/links` — returns all confirmed links for the client (both as human side and entity side).
- `DELETE /api/clients/{client_id}/links/{link_id}` — removes the link. Hard delete is fine for Stage 1; audit logging for link history is a later concern.
- `GET /api/clients/{client_id}/group` — returns the full resolved group with each member's basic info (id, name, client_kind).

Use the existing auth/authorization patterns — grep for how other client-scoped endpoints verify the requesting user has access to the client. Any link operation must verify the user has access to **both** sides of the link. A user who can see Michael but not Smith Consulting cannot link them.

Write API tests covering the happy path, the human→human rejection, the entity→entity rejection, the unauthorized-side rejection, and the duplicate-link rejection (the `UNIQUE` constraint).

**STOP — CHECKPOINT 4:** Show me the endpoint code, the auth check, and the test results.

Commit: `feat(api): add client link management endpoints`

---

## Part 5 — Frontend: Link Management UI

On the client detail page in `frontend/app/admin/`, add a "Linked Clients" section showing the current group members and a "+ Link Client" button.

The link picker is a searchable dropdown of other clients in the firm, filtered by `client_kind` (if you're on a human client, only entity-kind clients appear; if you're on an entity, only individual clients appear). Form fields: link type, ownership percentage, filing responsibility. Submit hits the POST endpoint.

The chat header gets a new scope selector: `Searching across: <current scope> ▼`. Dropdown options: "All linked clients (N)", "Just <current client name>", and individual members of the group as checkboxes. Scope selection passes through to the chat endpoint as an optional `scope_override` query parameter. If omitted, default to full group.

**If `scope_override` is sent, the backend respects it but still validates that every ID in the override is actually in the resolved group** — you cannot use scope_override to reach outside your group. That would be an authorization bypass.

**STOP — CHECKPOINT 5:** Show me the UI in a screenshot, the scope selector behavior, and the scope_override validation code.

Commit: `feat(ui): add linked clients section and chat scope selector`

---

## Part 6 — Source Card Attribution

When the resolved group contains more than one client, source cards in chat responses must show the originating client name. Format: `Form 1120S, page 3 — Smith Consulting LLC`. When the group is a single client, keep the current format (no client name needed).

**STOP — CHECKPOINT 6:** Show me a before/after screenshot of a source card.

Commit: `feat(ui): show originating client on source cards in grouped chats`

---

## Part 7 — End-to-End Validation on a Real Test Client

Pick one of the existing real test clients where a 1040 and a 1120S exist as separate client records. If none exist yet, seed them: create a new "individual" client with a real 1040, create a new entity client with the corresponding 1120S, upload docs to each. Make sure the classifier completes on both.

Manually create a link via the new API or UI: human → entity, `owner_of`, 100%, `firm_files`.

Run the RAG eval with a fixture that includes at least three cross-entity questions — questions that can only be answered by joining data from both returns. Write the fixture questions in `rag_eval_fixtures.py` following the existing pattern. Example questions:

- "What was the distribution from [entity name] to [human name] in 2024?"
- "What is [human name]'s ownership stake in [entity name] and how much W-2 wages did the entity pay?"
- "What flowed from [entity name]'s K-1 box 1 to [human name]'s Schedule E?"

**Acceptance criteria for Stage 1 ship:**

- All three cross-entity questions return correct, cited answers with source cards from both client records visible in the response
- Michael's original eval still holds at 9/10 real correctness, 10/10 header-clean
- No existing tests regress

**FINAL CHECKPOINT:** Show me the cross-entity eval result, the new fixture, all commits, and the PR description. Do not merge until I approve.

Commit: `test(rag): add cross-entity evaluation fixture`

---

## Expected Failure Modes (so you recognize them)

**Part 3 — retriever regression.** If Michael's eval drops below 9/10, the most likely causes in order: (1) the CTE is returning duplicates and the ANY clause is pulling noise from other clients; (2) there's a second retrieval path you didn't update; (3) request-scoped caching is returning stale groups across test runs. Diagnose in that order.

**Part 7 — classifier gaps.** Cross-entity questions about specific line items on the 1120S may fail because the classifier doesn't yet extract structured fields from business returns (that's Stage 2). This is expected and is **not a Stage 1 blocker** as long as the *retrieval* works — i.e., the 1120S chunks are reaching the LLM and the LLM can read them. If chunks aren't reaching the LLM at all, that's a Stage 1 bug. If they are and the LLM is just missing a specific number, that's a Stage 2 classifier issue. Document the gap and ship.

## What This PR Does NOT Include

Reminder of what's explicitly out of scope, so you don't get pulled into it:

- Auto-detection of link candidates (Stage 3)
- Classifier expansion for 1120S / 1065 / 1041 / K-1 field extraction (Stage 2)
- Gap surfacing / "what am I missing" query (Stage 4)
- Spouse / MFJ household grouping
- Entity-level 7216 consent nuance
- Bulk link suggestions
- Link history / audit trail for created-and-deleted links

If Claude Code starts drifting into any of these, stop it and redirect.

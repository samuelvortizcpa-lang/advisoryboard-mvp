# Client Linking — Implementation Package

This directory contains the design and execution artifacts for **client linking**, the feature that lets Callwen consolidate a CPA's personal and business tax clients into a single unified chat scope while preserving CRM-aligned per-client billing.

## The Problem in One Paragraph

CPAs' existing CRMs (Drake, UltraTax, Lacerte, CCH) model "Michael Smith" (1040) and "Smith Consulting LLC" (1120S) as two separate client records — two engagement letters, two invoices, two rows in the client list. But advisory reality is unified: when Michael asks *"how did my business do this year and what does it mean for my personal taxes?"*, that's one conversation about one human's financial life. If Callwen imports the CRM's client list as-is, the chat on Michael will be structurally unable to see the 1120S documents filed under Smith Consulting LLC. Client linking is the layer that reconciles these two worlds without forcing the CPA to restructure their CRM.

## Files in This Package

### `client-linking-architecture.md`
The design document. Covers the data model (`client_links` table, `client_kind` column), the human→entity invariant, group resolution via recursive CTE, retrieval scope changes, detection signals, gap surfacing, classifier expansion requirements, staged rollout plan (Stages 1–4), and open questions. **Read this first.** Every Claude Code session that touches client linking should start by reading this file.

### `claude-code-prompts-client-linking-stage-1.md`
The execution prompts for Stage 1 — schema, retrieval scope change, and manual linking UI, all shipped as a single PR. Structured in seven Parts with explicit CHECKPOINT gates between each. Paste one Part at a time into Claude Code; do not front-load the whole file. The prompts reference `client-linking-architecture.md` for design details, so both files need to live in the repo together.

## Stage Map

The full feature ships across four stages. Only Stage 1 has execution prompts so far — Stages 2–4 get their own prompt files drafted after Stage 1 ships and the classifier expansion scope is better understood.

| Stage | Scope | Status | Sessions |
|---|---|---|---|
| 1 | Schema + retrieval scope + manual linking UI | Prompts ready | 1 |
| 2 | Classifier expansion (1120S, 1065, 1041, K-1 field extraction) | Not started | 1–2 |
| 3 | Auto-detection pipeline + suggestion UI | Not started | 1 |
| 4 | Gap surfacing + "what am I missing" query | Not started | 1 |

**Total estimated scope:** 4–5 focused sessions. Compare to the cost of deferring, which is data model debt that compounds as every new client adds more unsurfaced linking opportunities.

## Before Starting Stage 1

Three preconditions must be true:

1. **`admin-dashboard/` deploy path is resolved.** The April 12 session flagged this as unknown. Part 5 of the Stage 1 prompts cannot be verified without it.
2. **Voucher classifier fix has shipped.** Priority 3 from April 12. Michael's document row must read `tax_return / Form 1040 / 2024 / high confidence`, not `Form 1040-ES / 2025 / 90`. Otherwise cross-entity testing in Part 7 will be confounded by classifier noise.
3. **Michael's baseline is holding at 9/10 real correctness, 10/10 header-clean.** Reference eval: `a8552383-f908-476b-b51f-286f7131abb6`. This is the regression gate for Part 3.

If any precondition is false, resolve it in a separate session before starting Stage 1.

## Non-Negotiables That Span All Stages

These are the invariants that must hold from Stage 1 forward. If any of them get violated in a later stage, stop and redesign.

- **Links are always human → entity.** Never human → human, never entity → entity. Enforced at the schema level via trigger on `client_kind`.
- **No data moves between client records.** Linking is metadata only. Documents stay filed under their original `client_id`.
- **Billing, 7216 consent, and audit logs remain per-client.** Linking does not consolidate these.
- **Default chat scope is the full linked group.** Narrowing is one click away via a header dropdown.
- **Shared entities are allowed; shared humans are not.** Michael and Bob can both link to Acme Partners, but Michael's retrieval group never contains Bob — privacy isolation is preserved via the star-topology constraint.
- **Detection is passive; linking is always user-confirmed.** No auto-linking without a click.

## Design Decisions Already Locked In

During the scoping conversation that produced these files, several design questions were resolved. Recording them here so they don't get relitigated mid-implementation:

- **Explicit `client_kind` column, not implicit classification.** Chosen because the column is cheap and the enforcement is cleaner than inferring kind from document types at link time.
- **Group resolution via recursive CTE, not denormalized group_id.** Chosen because links are sparse and mutations are rare — the CTE cost is negligible and avoids the consistency burden of a denormalized column.
- **Chat endpoint public API unchanged.** The endpoint still takes a single `client_id`. Group expansion happens inside the retrieval layer. This keeps the frontend simple and lets Stage 1 ship without a frontend chat refactor.
- **`scope_override` parameter for narrowing, validated against the resolved group.** Users can narrow but cannot reach outside their group via scope_override — that would be an authorization bypass. The backend always re-validates.

## Open Questions (Deferred, Not Forgotten)

Recorded in `client-linking-architecture.md` under "Open Questions" — not blocking Stage 1 but worth revisiting before Stage 3 or 4:

- Multi-firm entity deduplication
- Historical/temporal alignment within a linked group
- Entity succession (LLC → C-corp conversions)
- Spouse / MFJ household grouping (needs its own design note)
- Dismissed-link re-suggestion policy

## Where These Files Live in the Repo

Suggested placement:

```
<repo-root>/
├── client-linking-architecture.md              # Design doc
├── claude-code-prompts-client-linking-stage-1.md  # Execution prompts
└── docs/client-linking/README.md                # This file (optional)
```

The architecture note needs to be at the repo root (or wherever Claude Code's working directory resolves) because the Stage 1 prompt tells Claude Code to "read `client-linking-architecture.md` in the project root" as the first action. If you move it, update the prompt reference accordingly.

# Callwen — Client Linking Architecture

**Status:** Draft — scoping document for future implementation session
**Author:** Architecture planning session, April 12, 2026
**Purpose:** Define how Callwen models the reality that a CPA's personal and business tax clients are often the same underlying engagement, while preserving the CRM-aligned "one row per billable client" model.

---

## Problem Statement

CPAs' existing CRMs (Drake, UltraTax, Lacerte, CCH) model **Michael Smith** (1040) and **Smith Consulting LLC** (1120S) as two separate client records — two engagement letters, two invoices, two rows in the client list. This is correct for billing and will not change.

But advisory reality is unified: when Michael asks *"how did my business do this year and what does it mean for my personal taxes?"*, that is one conversation about one human's financial life. If Callwen imports the CRM's client list as-is, the chat on Michael will be unable to see the 1120S documents filed under Smith Consulting LLC — **the data exists in the system, but is invisible to the chat because it lives in another client record.**

This is the single highest-impact correctness gap for the multi-entity CPA use case. It is not a RAG tuning problem. It is a data model problem.

## Design Principle

**Callwen sits above the CRM and reconciles what the CRM structurally cannot.** Users import their client list exactly as it exists in their CRM (frictionless onboarding, preserved mental model). Callwen's intelligence layer detects when two client records represent the same underlying engagement and offers to link them. Once linked, the chat transparently retrieves across the full group while billing, consent, and audit remain per-client.

**Non-negotiables:**
- No data moves between client records. Linking is metadata only.
- Billing, 7216 consent, CRM exports, and audit logs remain per-client.
- Detection is passive; linking is always user-confirmed.
- Default chat scope is the full linked group; narrowing is one click away.
- Links are always **human → entity**, never entity → entity or human → human.

## Data Model

### New table: `client_links`

```sql
CREATE TABLE client_links (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    human_client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    entity_client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    link_type TEXT NOT NULL,  -- 'owner_of' | 'partner_in' | 'beneficiary_of' | 'officer_of'
    ownership_pct NUMERIC(5,2),  -- nullable; 100.00 for wholly-owned, NULL if unknown
    filing_responsibility TEXT NOT NULL,  -- 'firm_files' | 'k1_only' | 'external_cpa' | 'advised_only' | 'unknown'
    confirmed_by_user BOOLEAN NOT NULL DEFAULT FALSE,
    detection_source TEXT,  -- 'address_match' | 'name_match' | 'ein_match' | 'k1_issuer_match' | 'manual'
    detection_confidence NUMERIC(3,2),  -- 0.00–1.00
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    confirmed_at TIMESTAMPTZ,
    dismissed_at TIMESTAMPTZ,  -- user said "not the same engagement"
    UNIQUE (human_client_id, entity_client_id)
);

CREATE INDEX idx_client_links_human ON client_links(human_client_id) WHERE confirmed_by_user = TRUE;
CREATE INDEX idx_client_links_entity ON client_links(entity_client_id) WHERE confirmed_by_user = TRUE;
```

### Invariant: always human → entity

The `human_client_id` side must resolve to a client whose primary document is an individual return (1040). The `entity_client_id` side must resolve to a client whose primary document is a business/trust return (1120S, 1065, 1120, 1041). This is enforced at insert time by checking the target client's classified document types.

**Spouses:** if Jane has her own Schedule C LLC, she exists as her own `client` row. Jane is linked to her LLC (`human → entity`). Michael is linked to his own entities. Michael and Jane are **not** linked directly — they are each the human end of their own links. When retrieval resolves Michael's group, it does not traverse to Jane. If the firm wants Michael's chat to see Jane's docs, that's a separate product decision (explicit MFJ household grouping) and is **out of scope** for this note.

### `clients` table — `client_kind` column (Stage 1)

A `client_kind` column (TEXT, NOT NULL, default `'unknown'`) is added to `clients` with a CHECK constraint restricting values to: `individual`, `s_corp`, `partnership`, `c_corp`, `trust`, `disregarded_llc`, `sole_prop`, `unknown`. This column is enforced at link creation by a `BEFORE INSERT OR UPDATE` trigger on `client_links` that validates `human_client_id` resolves to `client_kind = 'individual'` and `entity_client_id` resolves to a business/trust kind.

Backfill: clients with any document chunk mentioning "Form 1040" are set to `individual`. All others remain `unknown` pending manual update or Stage 2 classifier expansion.

### `documents` table — no changes required

Documents stay filed under their original `client_id`. A 1120S uploaded under Smith Consulting LLC remains under Smith Consulting LLC. The link layer is purely a retrieval-scope construct.

## Group Resolution

Given a starting `client_id`, the full linked group is computed as:

```sql
SELECT :start_id AS client_id
UNION
SELECT cl.entity_client_id FROM client_links cl
  WHERE cl.human_client_id = :start_id
    AND cl.confirmed_by_user = TRUE
    AND cl.dismissed_at IS NULL
UNION
SELECT cl.human_client_id FROM client_links cl
  WHERE cl.entity_client_id = :start_id
    AND cl.confirmed_by_user = TRUE
    AND cl.dismissed_at IS NULL
```

Non-recursive by design. Because links are structurally human→entity (enforced by the `client_kind` trigger), the topology is always a star with at most one hop. A recursive CTE would traverse Michael → Acme → Bob when Michael and Bob share a linked entity, violating the privacy invariant stated below. If the human→entity invariant is ever relaxed in a future stage, this query must be re-examined.

A link is considered **active** only when `confirmed_by_user = TRUE` AND `dismissed_at IS NULL`. Dismissed links (even if still marked confirmed) are excluded from group resolution — this is the safer default for Stage 1.

Because links are human→entity only and a human cannot be linked to another human, the resulting group is always a **star** with one human at the center and N entities as leaves. No cycles are possible.

**Edge case — shared entity:** if two humans (Michael and his business partner Bob) are both linked as `owner_of` to Acme Partners LP, and both are Callwen clients, then Michael's group contains {Michael, Acme} and Bob's group contains {Bob, Acme}. **Michael's group does not contain Bob.** Acme is shared, but the humans stay isolated. This is the correct privacy posture.

## Retrieval Integration

The retriever's `where` clause for client scope changes from:

```python
WHERE d.client_id = :client_id
```

to:

```python
WHERE d.client_id = ANY(:group_client_ids)
```

where `group_client_ids` is resolved from the starting client via the group resolution query above.

**Default scope:** full group. When the CPA opens the chat on Michael, retrieval pulls from Michael + all confirmed-linked entities.

**Narrowing:** the chat header shows `Searching across: Michael Smith + 2 linked clients ▼`. The dropdown lets the user:
- Select "Just Michael Smith" (narrow to starting client only)
- Select individual entities to include/exclude
- Return to "All linked clients"

Scope selection persists for the chat session but resets to full-group on new chats.

**Source attribution in responses:** each source card must show which client record it came from when the group contains more than one. A citation like *"Form 1120S, page 3 (Smith Consulting LLC)"* is clearer than *"Form 1120S, page 3"* when the user is chatting on Michael.

## Detection Pipeline

Detection runs **after** document classification completes (so the classifier has already extracted entity names, EINs, addresses, and K-1 issuer data). It is a separate pass, not part of the classifier itself.

### Signals, in increasing order of confidence

| Signal | Confidence | Description |
|---|---|---|
| Address match | 0.4 | Principal business address on 1120S matches home address on 1040 |
| Name match | 0.6 | "Michael Smith" appears as officer/shareholder on 1120S; a client named "Michael Smith" exists |
| EIN cross-reference | 0.85 | Schedule K-1 on Michael's 1040 reports an EIN matching another client's filed EIN |
| K-1 issuer match | 0.95 | K-1 received by Michael says "Issued by Acme Partners, EIN X"; Acme Partners exists as a client with EIN X |
| Manual | 1.00 | User explicitly links two clients |

### Suggestion thresholds

- **Confidence ≥ 0.85:** surface as a high-confidence suggestion banner on the client detail page
- **Confidence 0.6–0.85:** surface in a "Possible links" section in a less prominent location
- **Confidence < 0.6:** store but do not surface; available via a "Show all possible links" power-user view
- **Dismissed links:** never re-suggest the same pair unless a new signal of strictly higher confidence arrives. A dismissed link (`dismissed_at IS NOT NULL`) is excluded from group resolution even if `confirmed_by_user` remains `TRUE`.

### UI moment

Non-intrusive banner on the client detail page:

> *We noticed **Smith Consulting LLC** (S-corp) appears on Michael's Schedule E with 100% ownership. These may be part of the same engagement.*
> [ Link as owner/entity ] [ Not the same engagement ] [ Remind me later ]

On confirmation, a toast: *"Linked. Michael's chat now includes Smith Consulting LLC documents."*

## Gap Surfacing — the Anti-Hallucination Posture

Linking solves the problem when the related entity **is** a Callwen client. Gap surfacing handles the case when it isn't — or when documents are missing within a linked group.

### Ingestion-time gap detection

When a 1040 is processed and its Schedule E / K-1s reference an entity that does **not** match any existing Callwen client, the system creates a "missing entity" flag on the human client:

> *Michael's 1040 references a K-1 from **Acme Partners LP** (EIN 12-3456789). We don't have this entity on file.*
> [ Add as linked client ] [ Mark as K-1 only — we don't file it ] [ Dismiss ]

If marked as `k1_only`, the system records this explicitly so the chat's answers about Acme Partners can be prefaced: *"Based on the K-1 received — the full 1065 is not on file with us."*

### "What am I missing?" query

A first-class prompt on the client chat page — either a button or a canned suggestion:

> **Show me what's missing for this client.**

Returns a structured list:
- K-1s referenced on the 1040 but not uploaded
- Linked entities whose most recent return is older than the human's most recent return
- Expected schedules/forms absent from the corpus (e.g., Schedule D referenced but missing)
- Prior year returns not on file
- Pass-through entities detected but not linked

This is both a trust-building feature (the system admits gaps) and a demo moment (prospects see the anti-hallucination posture made visible).

## Classifier Expansion Required

Linking and gap detection both depend on structured data the current classifier doesn't extract. Required additions:

| Form | Fields to extract |
|---|---|
| 1120S | Entity name, EIN, tax year, principal address, shareholders (name + ownership %) |
| 1065 | Entity name, EIN, tax year, principal address, partners (name + ownership %), tax matters partner |
| 1041 | Trust name, EIN, tax year, trustee, beneficiaries |
| 1120 | Entity name, EIN, tax year, officers |
| Schedule K-1 (all variants) | Issuing entity name, issuing EIN, recipient name, recipient SSN/EIN, tax year, K-1 type (1120S / 1065 / 1041), box values |
| 1040 Schedule E | All pass-through entities listed (name, EIN if present, ownership %) |

The K-1 classifier is the highest-priority addition because K-1s are the **bridge documents** that power both detection (EIN matching) and gap surfacing (referenced-but-missing entities). A K-1 classifier that extracts `{issuing_entity_name, issuing_ein, recipient_name, tax_year}` unlocks most of the value in this note.

## What Does and Does Not Change

### Unchanged

- Chat retrieval defaults, smart chunking, hybrid search, reranking, Document AI pipeline
- Source cards, confidence scoring, PDF viewer
- 7216 consent (per client, as-is — entity-level consent nuance is deferred)
- Usage metering, Stripe, quotas, Run Eval button, RAG Analytics dashboard
- Voucher classifier fix (Priority 3 from April 12 session) — independent, still needed
- CRM import flows (import as-is, let linking happen after)
- Audit logging (per-client, unchanged)
- Billing (per-client, unchanged)

### New work

- `client_links` table + migration
- Recursive CTE helper for group resolution (cached per-request)
- Retriever scope change from `client_id = :x` to `client_id = ANY(:group)`
- Classifier expansion for 1120S, 1065, 1041, 1120, K-1 (all variants), Schedule E pass-through extraction
- Detection pipeline (post-classification pass, signal scoring, suggestion storage)
- Client detail page: "Linked clients" section, suggestion banner, link/dismiss actions
- Chat header: scope selector dropdown with group members
- Source cards: show originating client when group > 1
- "What am I missing?" query handler + UI entry point
- Ingestion-time missing-entity flag surfacing

### Out of scope (explicitly deferred)

- Spouse linking / MFJ household grouping (humans do not link to humans)
- Entity-level 7216 consent (per-entity disclosure nuance — a partner consenting to their K-1 being shared but not the full 1065)
- Cross-firm entity deduplication (two firms' clients sharing the same underlying entity)
- Automatic linking without user confirmation (always require a click)
- Bulk link suggestions across an entire client list at once (one-by-one is fine for MVP)

## Migration Path — Staged Rollout

**Stage 1 — Schema + manual linking (1 session)**
Ship `client_links` table, group resolution CTE, retriever scope change, chat header scope selector, a simple "+ Link client" button on the client detail page with a searchable picker. No auto-detection yet. This alone unlocks the use case for power users who will link clients manually.

**Stage 2 — Classifier expansion (1–2 sessions)**
Add 1120S, 1065, 1041, K-1 recognition and structured field extraction. This is where the voucher-fix pattern (`detect_voucher_chunk` reuse) generalizes into a library of form-specific detectors. Re-eval on existing clients to confirm no regression.

**Stage 3 — Detection pipeline (1 session)**
Ship the post-classification detection pass with the five signals, confidence scoring, and the suggestion banner UI. Dogfood on existing real test clients.

**Stage 4 — Gap surfacing (1 session)**
Ingestion-time missing-entity flags + the "what am I missing" query. Ship this last because it depends on everything above — especially classifier K-1 extraction.

Total estimated scope: **4–5 focused sessions.** Compared to the cost of deferring (data model debt that compounds as every new client adds more unsurfaced linking opportunities), this is cheap.

## Open Questions for Future Discussion

1. **Multi-firm entities.** If two separate firms both use Callwen and both have the same underlying entity as a client (via their respective client lists), should those be deduplicated at the platform level? Probably no — each firm sees only their own tenant. But if entity-level intelligence (e.g., "this 1065 has changed between years") ever becomes cross-tenant, this needs revisiting.

2. **Historical entity data.** If a CPA imports 5 years of returns for Michael and 3 years for Smith Consulting LLC, how does the link present temporal alignment? The chat should probably default to "most recent year on both sides, unless the question specifies otherwise," but this is a prompt-engineering question more than an architecture one.

3. **Entity succession.** Smith Consulting LLC converts to Smith Consulting Inc. (C-corp). Is that one linked entity with a type change, or two linked entities with a succession relationship? Defer until a real client hits this.

4. **Spouse MFJ handling.** Out of scope here but needs its own note soon. The "always human → entity" rule means Jane's Schedule C LLC is linked to Jane, not Michael. Whether Michael's chat should see Jane's docs via an MFJ household concept is a separate product decision.

5. **Dismissed-link re-suggestion.** If a user dismisses a link and then uploads a new document that strongly confirms the link (e.g., an engagement letter naming both parties), should the system re-suggest? Lean yes, but only on strictly higher-confidence signals.

## Acceptance Criteria for Stage 1

The architecture is working when these statements are all true on a real test client:

- Michael Smith and Smith Consulting LLC exist as two separate client rows, imported as they would be from a CRM
- A manual link is created: Michael `owner_of` Smith Consulting LLC, 100%, firm_files
- Opening the chat on Michael shows "Searching across: Michael Smith + 1 linked client" in the header
- Asking *"what was the S-corp distribution to Michael in 2024?"* returns a correct answer citing pages from the 1120S (filed under Smith Consulting LLC) and the 1040 Schedule E (filed under Michael)
- The chat header dropdown allows narrowing to "Just Michael Smith" in one click
- Opening the chat on Smith Consulting LLC shows the same group with the entity as the focus
- Source cards clearly indicate which client each retrieved document came from
- Unlinking in the UI immediately removes Smith Consulting documents from Michael's retrieval scope
- Billing, audit logs, and 7216 consent records for each client remain completely independent

Once these pass on a real test client, Stage 1 ships and the team has a working foundation to layer classifier expansion, detection, and gap surfacing on top of.

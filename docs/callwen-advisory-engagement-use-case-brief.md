# Callwen — Advisory Engagement Use Case Brief

**Date:** April 28, 2026 (updated)
**Purpose:** Reference document defining the advisory-engagement-in-a-box use case Callwen is being built to serve, mapping current capabilities to that operating model, and identifying the remaining functionality gaps. Intended as carry-forward context for future build sessions.

---

## 1. The Use Case We're Targeting

Callwen is being built to serve as the operational backbone of a CPA advisory engagement, end to end — not just an AI search tool over uploaded client documents.

The target experience: a CPA opens Callwen, invokes a stage of the engagement (e.g., "draft the 60-day progress note for the Johnson family"), and the platform automatically retrieves all relevant client context, runs the stage-appropriate workflow, and produces a structured deliverable for the CPA to review and send.

Every stage of the engagement should be a recognized, stage-aware workflow with its own context-assembly logic, prompt template, and output format. The AI does not freelance — it executes templated workflows against the client's full data picture.

**The cadence is a menu, not a prescription.** The CPA selects per client which touchpoints apply to that engagement. One client may follow the full cadence; another may receive only quarterly memos and an annual review; another may sit on a custom path the firm defines. The platform's job is to support whatever methodology the firm runs, not impose its own. Configurability is a first-class concept, not an afterthought.

Beyond advisory itself, the platform should serve as the source of truth across departments. Tax prep and accounting team members opening the same client should see the same data filtered for their role, with structured handoff workflows between departments.

**Scope note:** This brief is internal-facing only. Building client-facing surfaces (client portals, client-side implementation trackers, real-time client dashboards) is explicitly out of scope for the current phase. The existing public check-in form remains the only client-facing surface and is not extended.

---

## 2. The Engagement Cadence Framework

The advisory engagement is structured as three layers of touchpoints across a 12-month cycle. Firms select which touchpoints apply per client.

**Heavy (1–2 per year):** Hour-long live meetings — the strategy kickoff and the annual review. Relationship anchors. Almost always required.

**Medium (4–6 per year, fully configurable):** Async written deliverables — Day-14 implementation kickoff memo, Day-60 progress note, quarterly estimate memos, mid-year review, year-end strategy recap. Each is templated and takes ~30–45 minutes of advisor time. This is the layer where configurability matters most — firms vary widely in how many of these they run.

**Light (10–20 per year, mostly automated):** Onboarding intake, 30-day pulse check-in, quarterly check-in forms, smart alerts triggered by income thresholds, deadline reminders, document-received acknowledgments. Configurable per client at the deliverable level (this client gets 30-day pulse, that one doesn't).

**Cross-department handoffs (twice per year, configurable):** Pre-prep brief (advisory → tax prep, December), post-prep flag (tax prep → advisory, April). Apply only if the firm has multiple departments and the client touches both.

The engagement gap most CPA firms experience is the silence after the strategy roadmap is delivered. The medium and light layers fill that silence in a scalable, templated way — for the touchpoints the firm has chosen to run.

---

## 3. What's Built — Mapping Callwen to the Framework

### Phase 1 — Onboarding (well-covered)
- Client CRUD with org-based multi-tenancy
- §7216 tiered consent flow (preparer vs. advisory acknowledgment)
- Tax Season Intake check-in template
- Document upload with auto-classification (12 types)
- 9-flag client profile system with AI auto-population
- Custom AI instructions per client

### Phase 2 — Discovery (well-covered)
- Document intelligence layer (form-aware chunking, classification, superseding)
- Structured financial extraction (63 metrics across years)
- Tax Strategy Matrix with AI auto-population from documents
- Cross-document analysis and contradiction detection

### Phase 3 — Strategy Meeting (well-covered)
- One-click Client Brief Generator
- Strategy Impact Report PDF (client-facing deliverable)
- Recording ingestion (Zoom, Fathom)
- Tax strategies populated with "recommended" statuses post-meeting

### Phase 4 — Implementation (the gap area, partially covered)
- Action items with assignment, calendar, deadline reminders, email notifications
- Recurring deadline automation via engagement engine (5 templates, 38 tasks)
- Client journal with auto-generated entries on financial changes, strategy status changes, communications, document uploads
- Communication threading with open-item tracking
- Quarterly estimate email workflow with thread awareness, financial context, and AI drafting
- Smart alerts (overdue, stale clients, deadline-approaching, threshold-crossed)
- Custom email templates with AI drafting
- Browser extension for inline document capture

### Phase 5 — Maintenance / Practice Layer (well-covered)
- Practice Book Export (per-client and full practice)
- Engagement health score (0–100) from communication frequency, action item completion, strategy coverage, document currency, journal depth
- Firm-level Strategy Dashboard

### Cross-Department Layer (partially covered)
- Client assignment to team members (basic ownership)
- Member dashboard scoped to assigned clients
- Org-based multi-tenancy with audit logging

---

## 4. Identified Functionality Gaps

The platform has the data and most of the workflow features. What's missing is the stage-aware orchestration layer that turns the AI into an engagement co-pilot rather than a generic Q&A interface — and the configurability layer that lets each firm run the cadence their own way.

### Gap 1 — Stage-aware engagement assistant (CRITICAL)

The AI chat is currently freeform retrieval. The product needs a recognized command set for engagement stages — examples: "draft Day-14 kickoff memo for [client]," "generate 60-day progress note," "draft pre-prep brief," "what's the implementation status for [client]?" Each command invokes a workflow that combines the unified context assembler with a stage-specific prompt template and produces a structured deliverable.

This is the core unlock for the use case. Without it, the CPA still has to manually orchestrate every touchpoint and the LLM is just a search box.

The assistant must respect per-client cadence configuration (Gap 4) — it auto-suggests only deliverables on the client's active cadence, but the CPA can manually invoke any deliverable as a one-off override.

**Build implication:** Define an engagement stage taxonomy. For each stage, build (a) a context-assembler purpose key, (b) a stage-specific prompt template, (c) an output schema. Add a router layer that detects stage commands in chat or surfaces them as one-click actions on the client detail page. The existing QUARTERLY_ESTIMATE purpose key in the context assembler is the precedent pattern.

**Status (May 10, 2026):** Un-deferred at the v1 milestone gate clear (May 10 evening re-smoke PASS), then re-deferred pending Layer 2 deliverable #2 (Day-60 progress note) ship. Two rationales recorded:

1. **Architectural reuse argument.** Gap 1 builds the chat-command router on top of the stage-specific deliverable framework. The framework currently has one deliverable (kickoff memo, Layer 2 #1). Building the router against a one-deliverable inventory means re-engineering the router as soon as #2 lands; building it against a two-deliverable inventory locks the polymorphic-dispatch-vs-per-deliverable-handler decision more cleanly. Defer Gap 1 until Layer 2 #2 (Day-60) ships to gain that second data point.
2. **Send-path truthfulness inheritance.** Gap 1's chat-command surface drives the same send path Layer 2 deliverables use. The send-path remediation arc (R-P0 through R-P3, plus 2B for async observability) closes the truthfulness contract end-to-end. Gap 1 inherits truthful semantics for free if it lands post-2B; shipping it pre-2B would re-expose the lying-toast failure mode at a new surface.

Resumes planning post-Layer-2-#2 ship per `Post_V1_Sequencing_Plan.md` §5 item 1.

### Gap 2 — Strategy implementation decomposition (CRITICAL)

The Tax Strategy Matrix tracks status (not_reviewed, recommended, implemented, etc.) but does not decompose a strategy into its implementation tasks. When a strategy is set to "recommended," the system should auto-generate the typical implementation steps with owners (CPA, client, third party), due dates, and required documents.

Today, a strategy can move to "recommended" with zero operational consequence — no tasks created, no client follow-up scheduled, no signal to the rest of the firm. This is the single biggest reason advisory firms struggle to convert recommendations into implementations.

**Build implication:** Add a `strategy_implementation_tasks` reference table seeded with template tasks per strategy (e.g., "S-Corp Election" → file 2553, set up payroll, establish reasonable salary, update QBO chart of accounts). On status change to "recommended," generate client-specific action items linked to that strategy. Add a strategy-level progress meter (X of Y implementation steps complete) on the strategy matrix UI.

### Gap 3 — Stage-specific deliverable templates beyond quarterly estimate (CRITICAL)

The quarterly estimate email workflow is the only deliverable today with thread awareness, financial context, and stage-specific drafting. The same pattern needs to extend to all the medium-layer touchpoints in the framework:

- Day-14 Implementation Kickoff Memo
- Day-60 Progress Note
- Mid-Year Tune-Up Memo
- Year-End Strategy Recap
- Pre-Prep Brief (advisory → tax prep)
- Post-Prep Flag (tax prep → advisory)

Each is a (context_purpose, prompt_template, output_format) tuple that uses the unified context assembler. Once the abstraction exists, adding new deliverables is incremental.

Every deliverable must check the client's cadence configuration (Gap 4) before auto-suggesting itself. Manual invocation is always permitted.

**Build implication:** Refactor the quarterly estimate workflow into a generic `engagement_deliverable_service` parameterized by stage. Wire each deliverable to the engagement engine so it auto-suggests at the right point in the cycle (e.g., kickoff memo task auto-creates 14 days after strategy meeting; year-end recap task auto-creates Nov 1) — but only if the deliverable is enabled in the client's cadence.

**Status (May 10, 2026):** Day-14 Implementation Kickoff Memo (Layer 2 deliverable #1) production-resolved at v1 milestone gate clear (May 10 evening re-smoke PASS). The send-path truthfulness contract holds end-to-end at the synchronous layer (R-P2 + R-P3); the async layer closes when **2B — Resend webhook for `delivered` / `bounced` / `complaint`** ships as the immediate-next post-v1 dispatch per `Post_V1_Sequencing_Plan.md` §3 Step 2. **Day-60 Progress Note is locked as Layer 2 deliverable #2**, sequenced after 2B ships and 2B's smoke event PASSes per `Post_V1_Sequencing_Plan.md` §8. Remaining deliverables (Mid-Year Tune-Up, Year-End Strategy Recap, Pre-Prep Brief, Post-Prep Flag) sequenced via the Master Roadmap and enter scope after Layer 2 #2 ships.

### Gap 4 — Configurable cadence per client (CRITICAL)

The framework defined in Section 2 is a *menu* the firm chooses from per client, not a fixed cadence applied to everyone. Today, no such configuration concept exists in the data model. Without it, every deliverable would fire for every client and the product would impose methodology on its users — the fastest way to lose opinionated CPAs.

Configurability is foundational. It must ship before any deliverables (Gap 3) are built so deliverables respect configuration from day one and we never retrofit.

**Build implication:**

- New table `cadence_templates` seeded with presets: "Full Cadence" (all medium touchpoints), "Quarterly Only" (quarterly memos + annual review), "Light Touch" (annual review only), "Custom."
- New table `cadence_template_deliverables` linking a template to the deliverables it includes (kickoff_memo, progress_note, quarterly_memo, mid_year_tune_up, year_end_recap, pre_prep_brief, post_prep_flag).
- New table `client_cadence` linking each client to a cadence template plus per-client overrides (JSONB column for enabled/disabled deliverable flags).
- Firm-level default in organization settings: "Default cadence template for new clients."
- UI: cadence selector on client creation/edit; per-client cadence detail page with toggles per deliverable; firm settings page for managing custom templates.
- Engagement engine: when generating tasks, check `client_cadence` and skip deliverables that aren't enabled.

This is structurally similar to the existing `engagement_templates` pattern (which handles tax-deadline scaffolding by entity type). Cadence templates are a separate axis: tax cadence vs. advisory cadence. The two coexist.

### Gap 5 — Strategy stuck/stale alerts (IMPORTANT)

A strategy can sit at "recommended" for six-plus months with zero progress and zero alert. Smart alerts cover overdue action items and stale clients but not stalled strategies. This is a structural blind spot — the firm-level Strategy Dashboard shows adoption rates but not stagnation.

**Build implication:** Add a `stalled_strategy` alert type triggered when a strategy stays in "recommended" for >60 days without progress on any linked implementation task (depends on Gap 2). Surface in the priority feed and on the firm-level Strategy Dashboard.

### Gap 6 — Department-aware role views (IMPORTANT)

`client_assignments` exists and member dashboards exist, but the client detail page is the same view for everyone. A tax preparer should see a tax-prep-focused tab arrangement (prior returns, strategies impacting this year's return, open prep items, deadlines). An accountant should see accounting-focused tabs (entity setup, QBO sync, monthly close items). An advisor should see the full advisory view.

This eliminates context-switching friction and reinforces departmental roles. It also sets up Gap 8 cleanly.

**Build implication:** Add a `department` field to `user_organization_membership` (values: advisory, tax_prep, accounting, admin). Filter and reorder client detail tabs and dashboard widgets based on department. Add department-specific home dashboards.

### Gap 7 — Engagement state view per client (IMPORTANT)

Information about where a client is in their engagement cycle is scattered across the action items, calendar, journal, and strategies tabs. There's no single view that says: "Client is at Day 47 of implementation phase. Cadence: Full. Last touchpoint: Day 30 pulse (responded). Next deliverable: Day 60 progress note (auto-creates May 12). Strategy implementation: 3 of 7 complete. Engagement health: 84."

This is the diagnostic dashboard for "what does this client need from me right now?"

**Build implication:** Build a `client_engagement_state` computed view from existing data (engagement engine + journal + strategies + comms + health score + cadence config). Surface as the default landing tab on the client detail page or as a horizontal strip at the top of every client tab.

### Gap 8 — Department-to-department handoff workflows (IMPORTANT)

Pre-prep brief (advisory → tax prep, December) and post-prep flag (tax prep → advisory, April) are not currently structured deliverables. Today these handoffs are "low communication between departments" — i.e., they don't happen reliably.

**Build implication:** These are specific instances of Gap 3 with cross-departmental routing. Build them as part of Gap 3's framework once Gap 6 (department roles) exists. The deliverable should be auto-routed to the receiving department's home dashboard with a "Reviewed" acknowledgment requirement. Both are configurable in the cadence (Gap 4) — firms without multiple departments simply don't enable them.

---

## 5. Suggested Build Order

The gaps are interdependent. Recommended sequence:

1. **Gap 2 — Strategy implementation decomposition.** Foundational — produces the data signal for Gap 5 and feeds Gap 3 (kickoff memo can reference "X strategies recommended, Y implementation tasks created"). Smallest scope and immediate visible value, so it's the right warm-up.

2. **Gap 4 — Configurable cadence per client.** Must ship before any deliverable is built so the deliverable framework respects configuration from day one. No retrofits.

3. **Gap 3 — Deliverable template framework.** Build the abstraction once, then add deliverables incrementally. Order: Day-14 Kickoff Memo → Day-60 Progress Note → Mid-Year Tune-Up → Year-End Strategy Recap → cross-department handoffs.

4. **Gap 1 — Stage-aware engagement assistant.** Wire the deliverables into a chat command vocabulary and engagement engine triggers. This is when the platform starts feeling like a co-pilot rather than a search tool.

5. **Gap 7 — Engagement state view.** Mostly UI work over already-existing data once Gaps 2 and 4 ship.

6. **Gap 6 — Department-aware role views.** Quality-of-life improvement; ships value to multi-employee firms.

7. **Gap 5 — Strategy stuck alerts** — can be slotted in alongside Gap 2 since the data signal exists then.

8. **Gap 8 — Cross-department handoffs** — these are deliverables in Gap 3's framework; build once Gaps 3 and 6 exist.

---

## 6. Success Criteria

The use case is fulfilled when a CPA can:

- Open Callwen on Day 14 of a new client engagement and run a single command that produces a draft kickoff memo with the right tone, references the strategies discussed, and lists each strategy's implementation tasks with owners and dates.
- Open Callwen on Day 60 and run a command that produces a progress note showing what the client has completed, what they still owe, and any new questions raised.
- Configure cadence per client — assign one client to "Full Cadence," another to "Quarterly Only," and a third to a firm-defined custom template — without writing code or asking support to do it.
- See at a glance, for each client, where they are in the engagement cycle, what cadence they're on, and what's next.
- See a tax preparer open a client and immediately get the correct departmental view, with the December pre-prep brief deliverable surfaced as a one-click action (if the client's cadence enables it).
- Run the year-end strategy recap workflow in November and have it pull from the strategy matrix, journal, communication threads, and financial extractions to produce a polished client-ready document.

---

## 7. Architectural Notes for Future Sessions

- **The unified AI context assembler is the leverage point.** Every new deliverable, every stage-aware command, every department view should call into it. New data sources improve every existing feature automatically. Don't bypass it.
- **The engagement engine is the scheduling layer.** Every new deliverable should auto-create a task with `lead_days` so it surfaces at the right time — gated by cadence configuration. Don't build new schedulers.
- **The client journal is the audit layer.** Every new auto-generated artifact (memo sent, deliverable produced, strategy task completed, cadence changed) should write a journal entry. The journal becomes the practice book input and the post-prep flag input automatically.
- **The communication threading model is the conversation layer.** Implementation kickoff memo + progress note + year-end recap should all live on a single `engagement_year` thread, with open-item tracking carrying across. Don't create siloed conversation models.
- **Configurability is first-class, not retrofit.** Every feature that triggers automatically must check the client's cadence configuration before firing. The CPA can always manually invoke any deliverable as a one-off override.
- **Internal-facing only for now.** No client portals, no `/portal` routes, no client-side dashboards. The check-in form remains the only client-facing surface and is not extended.

The tools to build this exist. The work is mostly composition, not invention.

---

## 8. Deferred / Future Considerations

The following were considered but explicitly deferred from the current phase:

### Client-facing implementation tracker
A tokenized, no-login client view showing open action items the client owes, document upload requests, strategy implementation status, and recently completed items. Would dramatically reduce email-chasing for documents and create ambient client awareness of the engagement.

**Reason for deferral:** The CPA market is conservative about giving clients direct portal access. The value of the framework lives in the advisor's workflow, not in real-time client visibility. Internal-side validation (own firm + 5–10 outreach firms) should come first. The existing public check-in form pattern remains as the foundation if/when this comes back into scope.

### Other future ideas
- Rich client onboarding intake form generator (richer than the current Tax Season Intake template)
- Automated post-meeting action item extraction from Fathom transcripts that flows into the engagement deliverable framework
- AI-suggested cadence template for new clients based on entity complexity, profile flags, and projected advisory time
- Multi-firm benchmarking: anonymized cross-firm comparison of strategy adoption rates, engagement health, and cadence patterns

These are noted for awareness but are not on the current roadmap.

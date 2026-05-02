# AdvisoryBoard — North Star

**Status:** Living reference doc. Updated when product framing changes; otherwise stable.
**Last updated:** April 28, 2026 (Session 23 — Layer 1/Layer 2 scope note)
**Owner:** Sam Ortiz
**Purpose:** Single source of truth for what AdvisoryBoard is *for*, what success looks like per query mode, and how feature priorities map to those modes. Every Claude Code prompt and every chat session anchors to this doc.

**Scope (April 28, 2026, Session 23):** This doc anchors **Layer 1 — the retrieval substrate** (hybrid search, form-aware chunking, answer LLM, citation extraction). It governs retrieval-quality decisions and the Mode 1/2/3/4 query taxonomy. **Layer 2 — engagement orchestration** (stage-aware deliverables, configurable cadence, strategy decomposition, department-aware views) composes on top of Layer 1 and is anchored by `callwen-advisory-engagement-use-case-brief.md`. **The accuracy north star applies to both layers** — a wrong figure in a Day-14 kickoff memo is a Layer 1 failure surfaced through a Layer 2 surface; both layers fail simultaneously. Layer 1 priority is rebalanced based on what Layer 2 deliverables actually retrieve, not deprioritized in absolute terms.

---

## The North Star (one paragraph)

AdvisoryBoard exists so a CPA can hold a client's entire document corpus in conversation — asking what's *true*, what's *there*, what's *happening*, and what to *do next* — and get answers that are correct, source-cited to the exact form and line, complete (no silent truncation), aware of which information is currently active vs superseded, and structured to either answer the question or elicit what's missing to answer it well. Fast enough to use mid-client-call.

---

## The Four Query Modes

A single chat surface handles four distinct query shapes. Each mode adds one capability over the previous; each has its own success criteria and its own architectural requirements. The current pipeline is built for Mode 1; Modes 2-4 require new architecture.

### Mode 1 — Factual lookup

**Example:** *"What was Michael's taxable income in 2024?"*

**Success criteria:** One specific value, cited to one specific location (form + line + page), retrieved from one specific document. Latency under ~3 seconds.

**Current state:** Working. retrieval=1.00 (hard floor), response=[0.80, 1.00], citation=[0.90, 1.00] across 10 ground-truth questions × 2 clients. Q4 (interest $7) and Q6 (cap gains $7,584) are the only fixtures that flip — both are ground-truth fixture quirks, not retrieval failures.

**Architecture:** Hybrid search (vector + BM25 with RRF) → Cohere cross-encoder rerank top-20 → top-5 → GPT-4o-mini answer with citation extraction. Form-aware chunker v2 with section attribution.

**Known gaps:** Q4/Q6 fixture variance (P1). Schedule A column-interleaving oscillation in OCR (Phase 1 detector live, logging-only). citation_hit and extracted_citations fields stripped from /evaluations/{id} response (P1, sub-10-minute fix).

### Mode 2 — Inventory / enumeration

**Example:** *"What K-1s are currently flowing through this client's 1040?"* / *"What properties are in this client's partnership?"* / *"What entities does this client have ownership in?"*

**Success criteria:** A **complete** list of items in the requested category. Each item grounded in a specific source document with a per-item citation. The CPA must be able to trust nothing is silently missing. If the system is uncertain about completeness, it says so explicitly.

**Current state:** Untested and architecturally weak. Top-5 reranked retrieval is biased against enumeration — if a client has 8 K-1s, the top-5 surfaces the 3-5 most semantically similar to the query and silently truncates the rest. The LLM answers "the client has 4 K-1s" with no signal that 4 more exist in the corpus. Mode 1 architecture answering a Mode 2 question = confidently wrong.

**Architecture needed:**
- **Intent detection.** "list", "what are all", "which X", "all properties", "every", etc. → switch retrieval strategy. Rule-based first pass + LLM classifier fallback.
- **Document-type filtered retrieval.** Leverage existing `document_type` / `document_subtype` / `document_period` metadata (populated by document classifier shipped March 12-13) to retrieve ALL chunks of the relevant type for the client, not just top-K.
- **Per-document aggregation.** Roll up retrieved chunks to one item per source document; deduplicate.
- **Structured output shape.** List or table response, not prose.
- **Per-item citation.** Each enumerated item references its source document, page, and where applicable form + line.
- **Completeness signal.** When retrieval thinks the list may be incomplete (e.g., document_type filter returned 0 results, or some chunks couldn't be classified), the answer says so rather than presenting a partial list as final.

**Leverage we already have:** Document classification metadata is populated. We're not starting from zero — we're wiring existing infrastructure into the chat path.

**Known gaps:** No intent detection layer. No enumeration retrieval path. No structured-list output shape. No completeness scoring in eval framework.

### Mode 3 — Synthesis / currency

**Example:** *"What strategies is this client currently implementing?"* / *"Compare 2024 vs 2023 — what changed?"* / *"What's the client's current entity structure?"*

**Success criteria:** Multi-document synthesis grounded in citations across multiple sources, filtered to what is **currently active** — not superseded by amendments, not from prior years that no longer apply. Differences and continuities both surfaced. No fabricated changes. No missed obvious changes.

**Current state:** Architecturally exists (Sonnet 4.6 routing for synthesis tier, multi-chunk retrieval), but two real gaps:
- **No temporal currency model.** Chunks aren't tagged active vs superseded. A 2024 amendment uploaded over a 2024 original leaves both in the corpus with equal retrieval weight. "Currently implementing" silently degrades when the corpus has multiple years.
- **Untested.** None of the 10 ground-truth questions per client measure synthesis or currency. We don't know how the system performs on Mode 3 today.

**Architecture needed:**
- **Temporal supersedence model** on documents and chunks (P2 backlog item, promoted to load-bearing for Mode 3).
- **Effective-date metadata** at ingest.
- **Tier 2 ground-truth fixtures** (synthesis + currency) per the Insight-Quality Eval Spec.
- **"Currency" as a scoring dimension** in the Insight-Quality rubric — currently absent from the spec, needs §8.5 addition.

### Mode 4 — Advisory / forward-looking

**Example:** *"What should Q1 estimates be for this client?"* / *"What tax-loss harvesting opportunities for 2025?"* / *"Is the client on track for retirement contributions?"*

**Success criteria:** The system either (a) answers with sufficient grounding plus stated confidence, or (b) recognizes it cannot answer responsibly and produces structured elicitation — a list of clarifying questions, or a draft client email asking projected income, current strategies, planned investments, etc. The CPA reviews and sends. **Hallucinated forward-looking advice is the worst possible failure mode here.**

**Current state:** Doesn't exist as a feature. The pipeline is `query → retrieve → answer`. There's no `query → retrieve → (answer | elicit)` branch.

**Architecture needed:**
- **Sufficiency assessment.** Does retrieved context plus the client's known state actually support a forward-looking answer?
- **Elicitation output shape.** Chat message with bulleted questions? Draft email artifact? Structured form the CPA reviews?
- **Trigger condition.** Confidence threshold? Explicit "I need more info" tool call from the LLM? Heuristic on query type (any forward-looking query → always elicit unless explicit context provided)?
- **Tier 3 ground-truth fixtures** and rubric.

**Open product questions:**
- Does the system elicit autonomously, or always answer with available data plus a labeled "to refine, I need: X, Y, Z" appendix?
- Is elicitation a chat reply or a draft artifact (email, form)?
- Does the CPA always review every elicitation before sending? (Probably yes, but worth being explicit.)

---

## Priority Sequence

**P0 — This document.** Load-bearing reference. Future Claude sessions and Sam both anchor to it. Update only when product framing changes.

**P1 — Mode 1 floor stability (defensive).** A wobbly Mode 1 baseline poisons every downstream eval comparison.
- Q4/Q6 fixture tightening (Item 5 from Session 12 menu)
- Restore citation_hit / extracted_citations / expected_citations in /evaluations/{id} (Item 3 — sub-10-min fix)
- Phase 1 detector telemetry observation as uploads accumulate

**P2 — Mode 2 enablement (highest leverage open).** Document classifier substrate is already in place; the work is wiring it into the chat path.
- Intent detection layer spec (rule-based + LLM classifier hybrid)
- Enumeration retrieval path: document-type filtered, complete recall, per-document aggregation
- Structured-list output shape with per-item citations
- Completeness eval dimension — does the answer enumerate all items in ground truth? Distinct from synthesis scoring.
- Mode 2 ground-truth fixtures (e.g., "list all K-1s for Michael" with known correct count)

**P3 — Mode 3 enablement.**
- Temporal supersedence design doc (documents + chunks; soft-delete vs flag; effective-date metadata)
- Insight-Quality Eval Spec §8.5 update — add "currency" as a Tier 2 scoring dimension
- Tier 2 ground-truth fixtures (synthesis questions for Michael and Tracy)

**P4 — Mode 4 architecture spec.** Resolve the open product questions above. Build only after Modes 2 and 3 are stable — Mode 4 reasoning collapses if the underlying retrieval modes don't already work.

**P5 — Mode 4 implementation.** Tier 3 fixtures, sufficiency scorer, elicitation output paths.

**P6 — Background quality work.** Phase 2 column reconstruction, Form Parser upgrade for financial doc types, multimodal embeddings, etc. Evidence-driven; not blocking the higher modes.

---

## Anti-patterns

- **Don't ship Mode 2/3/4 features without per-mode evals.** Mode 1 has eval discipline; the higher modes will silently regress without it. Spec the eval before the feature.
- **Don't treat top-K retrieval as universal.** It's right for Modes 1 and 4; wrong for Mode 2; partial for Mode 3.
- **Don't conflate synthesis with enumeration.** "What's the client doing" (synthesis, judgment) ≠ "What does the client own" (enumeration, completeness). Different retrieval strategy, different success criteria, different scoring.
- **Don't build Mode 4 elicitation as prompt-only.** It's an architectural decision (output shape, sufficiency assessment, trigger condition) — not just "tell the LLM to ask follow-ups."
- **Don't let documentation drift.** When the architecture changes, update this doc and the relevant spec same-session. Stale north stars are worse than no north star.
- **Don't skip ahead.** Mode 4 looks most exciting; Mode 2 has the highest leverage open. The discipline is to build the modes in order so each has working substrate underneath it.

---

## Cross-references

- `AdvisoryBoard_Insight_Quality_Eval_Spec.md` — Tier 1/2/3 eval framework. Needs §8.5 update for currency dimension (Mode 3) and a completeness dimension (Mode 2) per this doc.
- `AdvisoryBoard_ScheduleA_Oscillation_Spec.md` — Mode 1 chunker quality, Phase 1 detector.
- `AdvisoryBoard_Master_Roadmap.docx` — three-tier model routing (4o-mini / Sonnet 4.6 / Opus 4.6) maps to Modes 1 / 2-3 / 4.
- `AdvisoryBoard_OpenSource_FineTuning_Strategy.docx` — per-tier training data quality bars.
- Session March 12-13 summary — document classifier shipped (`document_type`, `document_subtype`, `document_period` populated). Mode 2 substrate.
- Session 9 summary (April 23) — first articulation of "CPA insight quality" as the actual north star.
- Session 12 chat (April 24) — four-mode framing originated; this doc is the artifact.

---

## Living document protocol

Update when:
- The product's intended functionality changes
- A new query mode is identified (current count: 4)
- A mode's architecture or eval framework materially shifts
- Priority sequence changes based on real-world evidence

Sam owns updates. Claude proposes them in chat or via Claude Code prompts; Sam ratifies before paste-in.

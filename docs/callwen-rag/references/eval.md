# Callwen RAG — Eval Framework Reference

Load this when running, interpreting, or extending the ground-truth eval. For the log patterns and SQL to inspect eval behavior, see `diagnostics.md`.

## What the eval is

A per-client, per-question ground-truth test set. Each question has:

```python
{
  "question": "What was the adjusted gross income on the 2024 return?",
  "expected_pages": [5],              # page(s) where the correct answer lives
  "expected_answer_contains": ["$293,600"],  # tokens the response must include
  "notes": "Form 1040 Line 11"        # human note — not scored as of April 16, but carries intent
}
```

Currently one client has fixtures: Michael Tjahjadi (`92574da3-13ca-4017-a233-54c99d2ae2ae`), 10 questions against his 2024 Form 1040. Generalizing to a second client is an open item — doing this would confirm the framework generalizes and would reduce confirmation bias on the current fixture.

File: `backend/app/services/rag_eval_fixtures.py`.

## The two headline scores

| Score | What it measures |
|---|---|
| **retrieval_hit_rate** | Fraction of questions where at least one `expected_pages` entry is in the retrieved-chunks page set. Tells you whether retrieval found the right page. |
| **response_keyword_rate** | Fraction where all `expected_answer_contains` tokens appear in the response text. Tells you whether the LLM used the retrieved context to actually answer. |

These are distinct axes. Retrieval can be 100% while keyword is lower (retrieval brought the right page but the LLM declined to answer or answered wrong). Keyword can be high with retrieval miss if the expected token shows up in multiple chunks across pages — this is one of the ways the rubric can be noisy; see below.

## What the eval does *not* measure

- **Real correctness.** The keyword match is substring-level. An answer of "$293,600" passes even if the LLM surrounds it with wrong line number, wrong year, or wrong context. Real correctness is human-graded ("5/10", "7/10", "9/10") and has been the north star across sessions — but the two headline numbers are what the endpoint returns.
- **Response quality / tone / presentation.** A terse, correctly-cited answer passes the same as a verbose, confused one with the right number in it.
- **Latency variance.** The `avg_latency` is reported but not scored against a threshold. 3.8s is the current reference; anything > 5s consistently is worth investigating.

## How to read an eval result

**Single run, interpretation flow:**

1. Look at the two headline numbers.
2. Drill into per-question payload. For each failed question:
   - Is `retrieval_hit` false? → retrieval problem. Check `retrieved_pages`, compare to `expected_pages`, then hybrid-search log line for that query.
   - Is `retrieval_hit` true but `keyword_hit` false? → generation problem. Read the response. Is it a bailout ("I couldn't find…")? Is it hallucinating? Is it answering but with different exact phrasing the keyword scorer doesn't catch?
3. If more than one question fails with a similar shape, treat it as a single symptom class, not N separate problems.

**Comparing runs (delta):**

Before changing code, capture a baseline eval ID. After deploy, re-run and compare. The eval is real signal as of April 16 — believe the delta. Movement of +10 points or more on either score is meaningful; <5 points is noise.

## The rubric trap — April 16 lesson

Prior to April 16, two fixtures had the wrong `expected_answer_contains`. The eval reported 100/80, the real correctness was 100/100, and the gap was invisible. This hid the fact that the retrieval layer was already at ceiling and misdirected time toward prompt refinements that were not the problem.

When a fixture stays at the "wrong" bucket across multiple runs after retrieval-side fixes that should have helped, **inspect the fixture itself** before debugging more retrieval code. Read the source document page, confirm what the correct answer actually is, and grade the LLM's response against that truth — not the written fixture.

The rubric is not scripture. It is a hypothesis about the correct answer, and it can be wrong.

## Known fixture caveats (Michael's set as of April 16)

- **Q4 (taxable interest).** Originally fixture-noisy; corrected April 16 (`7b876f0`).
- **Q8 (total tax).** Originally fixture-noisy; corrected April 16.
- **Q9 (HSA contribution).** Ground-truth is nuanced — Michael's contribution was $0 personal + $4,150 via employer cafeteria plan. `expected_answer_contains: ["$4,150"]` is too loose and accepts several different "correct" readings. Corrected April 16 but still worth revisiting if a broader question set lands.
- **Q6 and Q9 explanation noise.** Numbers correct; LLM explanation pulls adjacent instructional text (standard deduction line confusion, age-55 HSA conditional). Rubric-clean today; would fail a stricter "answer well-explained" rubric. Defer to a dedicated prompt session.

## Running the eval

```bash
curl -X POST "$CALLWEN_BACKEND_URL/api/admin/evaluate-rag-ground-truth/<client_id>" \
  -H "X-Admin-Key: $ADMIN_API_KEY"
```

The synthetic `eval_ground_truth` user used to execute the internal chat calls has a known quota-gate false positive that has been worked around via a one-time `token_usage` DELETE. The proper fix (admin-eval quota bypass flag) is a carryover. If a run returns "You've reached your monthly query limit" on every question, this is the signal — check the carryover for the fix pattern before re-running.

## Adding a new client fixture

To add a second client (recommended):

1. Pick a client with a meaningful document set — ideally a tax return with 2-3 years of data and at least one complex line-item.
2. Draft 8-12 questions that a CPA would actually ask in a client call. Start simple (AGI, total tax) then add harder ones (interest income across accounts, specific schedule line items, year-over-year comparisons).
3. For each question, open the source PDF, find the correct answer, write the `expected_answer_contains` tight. If the expected value appears in multiple places, make the expected tokens specific enough to disambiguate (include line number or year context).
4. Add the fixture to `rag_eval_fixtures.py` following the existing structure.
5. Run the eval. The first run will surface rubric bugs — fix them before trusting the number.

Target: a second fixture that generalizes what "retrieval working" means beyond one specific 1040. Open question for when this lands: whether to maintain separate per-client scores or roll them into an aggregate.

"""
Per-client ground-truth test sets for RAG evaluation.

Each test item specifies:
- question: the query to send through the RAG pipeline
- expected_page: the 1-indexed PDF page where the answer lives
- expected_answer_contains: list of strings; at least one must appear (case-insensitive)
  in the LLM response for the response to count as a hit. For numerical values,
  include multiple plausible formats (e.g., ["$293,600", "293,600", "293600"]).
- expected_citations: list of (form, line, page) tuples representing acceptable
  citation references. OR-match — any one tuple matching the LLM's emitted
  citation counts as a hit. Ground-truthed against the source document.
- category: factual_lookup | exact_term_match | multi_doc_synthesis | cross_source
- difficulty: easy | medium | hard
- notes: optional free-text explanation for maintainers
"""

from typing import Literal, NotRequired, TypedDict


class ExpectedCitation(TypedDict):
    form: str   # e.g., "Form 1040", "Schedule A", "Form 8889"
    line: str   # string, not int — "2b", "1a", "25a" exist
    page: int   # 1-indexed PDF page


class GroundTruthItem(TypedDict):
    question: str
    expected_page: int                              # primary page
    expected_pages: NotRequired[list[int]]           # all acceptable pages (overrides expected_page for scoring)
    expected_answer_contains: list[str]
    expected_citations: list[ExpectedCitation]
    category: str
    difficulty: str
    notes: str
    phrasing_category: NotRequired[Literal["A", "B", "C"]]
    original_q: NotRequired[str]


# Michael Tjahjadi — 2024 Form 1040 (single document)
MICHAEL_TJAHJADI_2024: list[GroundTruthItem] = [
    {
        "question": "What is Michael's AGI for 2024?",
        "expected_page": 5,
        "expected_answer_contains": ["$293,600", "293,600", "293600"],
        "expected_citations": [
            {"form": "Form 1040", "line": "11", "page": 5},
        ],
        "category": "factual_lookup",
        "difficulty": "easy",
        "notes": "Form 1040 line 11",
    },
    {
        "question": "What is the total income for 2024?",
        "expected_page": 5,
        "expected_answer_contains": ["$293,600", "293,600", "293600"],
        "expected_citations": [
            {"form": "Form 1040", "line": "9", "page": 5},
        ],
        "category": "factual_lookup",
        "difficulty": "easy",
        "notes": "Form 1040 line 9",
    },
    {
        "question": "How much did Michael earn in W-2 wages in 2024?",
        "expected_page": 5,
        "expected_answer_contains": ["$271,792", "271,792", "271792"],
        "expected_citations": [
            {"form": "Form 1040", "line": "1a", "page": 5},
        ],
        "category": "factual_lookup",
        "difficulty": "easy",
        "notes": "Form 1040 line 1a",
    },
    {
        "question": "How much taxable interest did Michael report in 2024?",
        "expected_page": 5,
        "expected_answer_contains": ["$7.00", "$7."],
        "expected_citations": [
            {"form": "Form 1040", "line": "2b", "page": 5},
            {"form": "Schedule B", "line": "4", "page": 11},
        ],
        "category": "factual_lookup",
        "difficulty": "medium",
        "notes": "Form 1040 line 2b ($7 taxable interest) — adjacent to tax-exempt interest ($136 on line 2a). Previous rubric had these swapped. expected_answer_contains tightened from ['$7', '7'] to avoid bare-7 false positives.",
    },
    {
        "question": "What were Michael's ordinary dividends in 2024?",
        "expected_page": 5,
        "expected_answer_contains": ["$13,267", "13,267", "13267"],
        "expected_citations": [
            {"form": "Form 1040", "line": "3b", "page": 5},
            {"form": "Schedule B", "line": "6", "page": 11},
        ],
        "category": "factual_lookup",
        "difficulty": "medium",
        "notes": "Form 1040 line 3b",
    },
    {
        "question": "What were Michael's capital gains in 2024?",
        "expected_page": 5,
        "expected_answer_contains": ["$7,584", "7,584", "7584"],
        "expected_citations": [
            {"form": "Form 1040", "line": "7", "page": 5},
            {"form": "Schedule D", "line": "16", "page": 13},
        ],
        "category": "factual_lookup",
        "difficulty": "medium",
        "notes": "Form 1040 line 7",
    },
    {
        "question": "How much did Michael contribute to charity in 2024?",
        "expected_page": 10,
        "expected_answer_contains": ["$9,630", "9,630", "9630"],
        "expected_citations": [
            {"form": "Schedule A", "line": "11", "page": 10},
            {"form": "Schedule A", "line": "14", "page": 10},
        ],
        "category": "factual_lookup",
        "difficulty": "medium",
        "notes": "Schedule A line 14",
    },
    {
        "question": "What was Michael's total tax for 2024?",
        "expected_page": 6,
        "expected_answer_contains": ["$42,645", "42,645", "42645"],
        "expected_citations": [
            {"form": "Form 1040", "line": "24", "page": 6},
        ],
        "category": "factual_lookup",
        "difficulty": "easy",
        "notes": "Form 1040 line 24 (total tax) — adjacent to line 25a withholding ($43,141). Previous rubric confused withholding with total tax.",
    },
    {
        "question": "What was Michael's HSA contribution limit for 2024?",
        "expected_page": 24,
        "expected_answer_contains": ["$4,150", "4,150", "4150"],
        "expected_citations": [
            {"form": "Form 8889", "line": "3", "page": 24},
            {"form": "Form 8889", "line": "8", "page": 24},
        ],
        "category": "factual_lookup",
        "difficulty": "hard",
        "notes": "Form 8889 line 3/8 — contribution limit for self-only HDHP coverage. Michael's personal contribution was $0 (line 2); employer contributed $420 (line 9).",
    },
    {
        "question": "Did Michael have an excess Roth IRA contribution in 2024? If so, how much?",
        "expected_page": 21,
        "expected_answer_contains": ["$7,000", "7,000", "7000"],
        "expected_citations": [
            {"form": "Form 5329", "line": "18", "page": 21},
            {"form": "Form 5329", "line": "24", "page": 21},
            {"form": "Schedule 2", "line": "24", "page": 7},
        ],
        "category": "exact_term_match",
        "difficulty": "hard",
        "notes": "Form 5329 — excess contribution. LLM may also cite Schedule 2 Line 24 (the flow-through to 1040); accepted as alternative.",
    },
]


# Tracy Chen DO, Inc — 2024 Form 1120-S (S-corp, single document)
TRACY_CHEN_DO_INC_2024: list[GroundTruthItem] = [
    {
        "question": "What was Tracy Chen DO, Inc's ordinary business income in 2024?",
        "expected_page": 16,
        "expected_pages": [16, 18, 52],
        "expected_answer_contains": ["$556,379", "556,379"],
        "expected_citations": [
            {"form": "Form 1120-S", "line": "22", "page": 16},
            {"form": "Schedule K", "line": "1", "page": 18},
        ],
        "category": "factual_lookup",
        "difficulty": "easy",
        "notes": "Ordinary business income. S-corp equivalent of total-income baseline. Also on Schedule K (p18) and reconciliation (p52).",
    },
    {
        "question": "What were the gross receipts for Tracy Chen DO, Inc in 2024?",
        "expected_page": 16,
        "expected_answer_contains": ["$920,900", "920,900"],
        "expected_citations": [
            {"form": "Form 1120-S", "line": "1a", "page": 16},
            {"form": "Form 1120-S", "line": "1c", "page": 16},
        ],
        "category": "factual_lookup",
        "difficulty": "easy",
        "notes": "Gross receipts top line. Line 1a and 1c both $920,900 (no returns/allowances).",
    },
    {
        "question": "What was the total compensation of officers reported on the 2024 1120-S for Tracy Chen DO, Inc?",
        "expected_page": 16,
        "expected_answer_contains": ["$96,000", "96,000"],
        "expected_citations": [
            {"form": "Form 1120-S", "line": "7", "page": 16},
            {"form": "Form 1125-E", "line": "2", "page": 21},
        ],
        "category": "factual_lookup",
        "difficulty": "easy",
        "notes": "Officer comp. Same $ as Q5 (sole officer). Citation metric differentiates.",
    },
    {
        "question": "What were the total deductions on Tracy Chen DO, Inc's 2024 1120-S?",
        "expected_page": 16,
        "expected_pages": [16, 17],
        "expected_answer_contains": ["$364,521", "364,521"],
        "expected_citations": [
            {"form": "Form 1120-S", "line": "21", "page": 16},
        ],
        "category": "factual_lookup",
        "difficulty": "medium",
        "notes": "Aggregation retrieval. Sum of Lines 7-20. Also on 1120-S continuation (p17).",
    },
    {
        "question": "How much was Tracy Chen paid as an officer of Tracy Chen DO, Inc in 2024?",
        "expected_page": 21,
        "expected_pages": [16, 21, 49],
        "expected_answer_contains": ["$96,000", "96,000"],
        "expected_citations": [
            {"form": "Form 1125-E", "line": "2", "page": 21},
        ],
        "category": "factual_lookup",
        "difficulty": "medium",
        "notes": "Individual officer comp. Sole officer so $ = Q3. Also on 1120-S Line 7 (p16) and CA statement (p49). Citation weak spot: 1125-E table row unnumbered, Line 2 (total) used as acceptable cite.",
    },
    {
        "question": "What were Tracy Chen DO, Inc's retained earnings at the end of 2024?",
        "expected_page": 19,
        "expected_answer_contains": ["$333,706", "333,706"],
        "expected_citations": [
            {"form": "Schedule L", "line": "24", "page": 19},
            {"form": "Schedule M-2", "line": "8", "page": 20},
        ],
        "category": "factual_lookup",
        "difficulty": "medium",
        "notes": "Balance sheet test. Schedule L Line 24 end-of-year or Schedule M-2 Line 8 AAA.",
    },
    {
        "question": "What were the total shareholder distributions from Tracy Chen DO, Inc in 2024?",
        "expected_page": 20,
        "expected_answer_contains": ["$294,484", "294,484"],
        "expected_citations": [
            {"form": "Schedule M-2", "line": "7", "page": 20},
            {"form": "Schedule K", "line": "16d", "page": 18},
        ],
        "category": "factual_lookup",
        "difficulty": "medium",
        "notes": "S-corp AAA distributions. High-signal for CPAs (affects basis).",
    },
    {
        "question": "How much California state tax does Tracy Chen DO, Inc owe for 2024?",
        "expected_page": 41,
        "expected_pages": [39, 41],
        "expected_answer_contains": ["$8,354", "8,354"],
        "expected_citations": [
            {"form": "Form 100S", "line": "30", "page": 41},
            {"form": "Form 100S", "line": "21", "page": 41},
        ],
        "category": "factual_lookup",
        "difficulty": "hard",
        "notes": "Federal/state disambiguation. Also on Form 5806 (p39). Watch for confusion with $8,780 (total due) or $556,904 (CA taxable income).",
    },
    {
        "question": "What was the California estimated tax underpayment penalty on Tracy Chen DO, Inc's 2024 return?",
        "expected_page": 39,
        "expected_answer_contains": ["$426", "$426."],
        "expected_citations": [
            {"form": "Form 5806", "line": "22b", "page": 39},
            {"form": "Form 100S", "line": "44a", "page": 41},
        ],
        "category": "factual_lookup",
        "difficulty": "hard",
        "notes": "State supporting form retrieval. Tightened keywords per Q4 lesson (bare '426' would false-match).",
    },
    {
        "question": "What was Tracy Chen's stock basis in Tracy Chen DO, Inc at the end of 2024?",
        "expected_page": 30,
        "expected_answer_contains": ["$420,490", "420,490"],
        "expected_citations": [
            {"form": "Form 7203", "line": "15", "page": 30},
        ],
        "category": "factual_lookup",
        "difficulty": "hard",
        "notes": "Shareholder basis. Form 7203 Line 15 end-of-year stock basis. Advanced S-corp topic. Avoids K-1 Box blind spot.",
    },
]


# Registry keyed by client_id (UUID as string)
CLIENT_GROUND_TRUTH: dict[str, list[GroundTruthItem]] = {
    "92574da3-13ca-4017-a233-54c99d2ae2ae": MICHAEL_TJAHJADI_2024,
    "b9708054-0b27-4041-9e69-93b20f75b1ac": TRACY_CHEN_DO_INC_2024,
}


def get_ground_truth(client_id: str) -> list[GroundTruthItem] | None:
    """Return the ground-truth test set for a client, or None if not defined."""
    return CLIENT_GROUND_TRUTH.get(str(client_id))


# ── Phrasing-variance fixtures (Session 22 Phase 3b) ─────────────────────
#
# 60 rewordings: 10 Tracy + 10 Michael base questions × 3 categories each.
# Categories: A (synonym), B (lay/colloquial), C (structural reframe).
# Each rewording inherits ground-truth fields from the corresponding original.
# Designed to defeat TERM_EXPANSIONS substring match; see §5.4 for methodology.


TRACY_CHEN_DO_INC_2024_PHRASING: list[GroundTruthItem] = [
    # ── T1 — ordinary business income ────────────────────────────────────
    {
        "question": "What was the S-corp's net income from operations for 2024?",
        "phrasing_category": "A",
        "original_q": "T1",
        "expected_page": 16,
        "expected_pages": [16, 18, 52],
        "expected_answer_contains": ["$556,379", "556,379"],
        "expected_citations": [
            {"form": "Form 1120-S", "line": "22", "page": 16},
            {"form": "Schedule K", "line": "1", "page": 18},
        ],
        "category": "factual_lookup",
        "difficulty": "easy",
        "notes": "Phrasing variant A (synonym) of T1",
    },
    {
        "question": "How much profit did Tracy's company make in 2024?",
        "phrasing_category": "B",
        "original_q": "T1",
        "expected_page": 16,
        "expected_pages": [16, 18, 52],
        "expected_answer_contains": ["$556,379", "556,379"],
        "expected_citations": [
            {"form": "Form 1120-S", "line": "22", "page": 16},
            {"form": "Schedule K", "line": "1", "page": 18},
        ],
        "category": "factual_lookup",
        "difficulty": "easy",
        "notes": "Phrasing variant B (lay/colloquial) of T1",
    },
    {
        "question": "After subtracting all operating expenses from revenue, what was the remaining income for Tracy Chen DO, Inc in 2024?",
        "phrasing_category": "C",
        "original_q": "T1",
        "expected_page": 16,
        "expected_pages": [16, 18, 52],
        "expected_answer_contains": ["$556,379", "556,379"],
        "expected_citations": [
            {"form": "Form 1120-S", "line": "22", "page": 16},
            {"form": "Schedule K", "line": "1", "page": 18},
        ],
        "category": "factual_lookup",
        "difficulty": "easy",
        "notes": "Phrasing variant C (structural reframe) of T1",
    },
    # ── T2 — gross receipts ──────────────────────────────────────────────
    {
        "question": "What was the total revenue reported by Tracy Chen DO, Inc for 2024?",
        "phrasing_category": "A",
        "original_q": "T2",
        "expected_page": 16,
        "expected_answer_contains": ["$920,900", "920,900"],
        "expected_citations": [
            {"form": "Form 1120-S", "line": "1a", "page": 16},
            {"form": "Form 1120-S", "line": "1c", "page": 16},
        ],
        "category": "factual_lookup",
        "difficulty": "easy",
        "notes": "Phrasing variant A (synonym) of T2",
    },
    {
        "question": "How much money came in to Tracy's company in 2024?",
        "phrasing_category": "B",
        "original_q": "T2",
        "expected_page": 16,
        "expected_answer_contains": ["$920,900", "920,900"],
        "expected_citations": [
            {"form": "Form 1120-S", "line": "1a", "page": 16},
            {"form": "Form 1120-S", "line": "1c", "page": 16},
        ],
        "category": "factual_lookup",
        "difficulty": "easy",
        "notes": "Phrasing variant B (lay/colloquial) of T2",
    },
    {
        "question": "Looking at the top line of Tracy Chen DO, Inc's return, what was the total before any expenses for 2024?",
        "phrasing_category": "C",
        "original_q": "T2",
        "expected_page": 16,
        "expected_answer_contains": ["$920,900", "920,900"],
        "expected_citations": [
            {"form": "Form 1120-S", "line": "1a", "page": 16},
            {"form": "Form 1120-S", "line": "1c", "page": 16},
        ],
        "category": "factual_lookup",
        "difficulty": "easy",
        "notes": "Phrasing variant C (structural reframe) of T2",
    },
    # ── T3 — officer compensation (total) ────────────────────────────────
    {
        "question": "What was the aggregate officer salary expense on Tracy Chen DO, Inc's S-corp return for 2024?",
        "phrasing_category": "A",
        "original_q": "T3",
        "expected_page": 16,
        "expected_answer_contains": ["$96,000", "96,000"],
        "expected_citations": [
            {"form": "Form 1120-S", "line": "7", "page": 16},
            {"form": "Form 1125-E", "line": "2", "page": 21},
        ],
        "category": "factual_lookup",
        "difficulty": "easy",
        "notes": "Phrasing variant A (synonym) of T3",
    },
    {
        "question": "How much did Tracy's company pay its officers in 2024?",
        "phrasing_category": "B",
        "original_q": "T3",
        "expected_page": 16,
        "expected_answer_contains": ["$96,000", "96,000"],
        "expected_citations": [
            {"form": "Form 1120-S", "line": "7", "page": 16},
            {"form": "Form 1125-E", "line": "2", "page": 21},
        ],
        "category": "factual_lookup",
        "difficulty": "easy",
        "notes": "Phrasing variant B (lay/colloquial) of T3",
    },
    {
        "question": "On the line for officer compensation on Tracy Chen DO, Inc's corporate return, what amount was reported for 2024?",
        "phrasing_category": "C",
        "original_q": "T3",
        "expected_page": 16,
        "expected_answer_contains": ["$96,000", "96,000"],
        "expected_citations": [
            {"form": "Form 1120-S", "line": "7", "page": 16},
            {"form": "Form 1125-E", "line": "2", "page": 21},
        ],
        "category": "factual_lookup",
        "difficulty": "easy",
        "notes": "Phrasing variant C (structural reframe) of T3",
    },
    # ── T4 — total deductions ────────────────────────────────────────────
    {
        "question": "What was the sum of all business expenses claimed by Tracy Chen DO, Inc on its 2024 S-corporation return?",
        "phrasing_category": "A",
        "original_q": "T4",
        "expected_page": 16,
        "expected_pages": [16, 17],
        "expected_answer_contains": ["$364,521", "364,521"],
        "expected_citations": [
            {"form": "Form 1120-S", "line": "21", "page": 16},
        ],
        "category": "factual_lookup",
        "difficulty": "medium",
        "notes": "Phrasing variant A (synonym) of T4",
    },
    {
        "question": "How much did Tracy's company write off in total for 2024?",
        "phrasing_category": "B",
        "original_q": "T4",
        "expected_page": 16,
        "expected_pages": [16, 17],
        "expected_answer_contains": ["$364,521", "364,521"],
        "expected_citations": [
            {"form": "Form 1120-S", "line": "21", "page": 16},
        ],
        "category": "factual_lookup",
        "difficulty": "medium",
        "notes": "Phrasing variant B (lay/colloquial) of T4",
    },
    {
        "question": "Adding up every expense category on Tracy Chen DO, Inc's corporate filing for 2024, what was the combined total?",
        "phrasing_category": "C",
        "original_q": "T4",
        "expected_page": 16,
        "expected_pages": [16, 17],
        "expected_answer_contains": ["$364,521", "364,521"],
        "expected_citations": [
            {"form": "Form 1120-S", "line": "21", "page": 16},
        ],
        "category": "factual_lookup",
        "difficulty": "medium",
        "notes": "Phrasing variant C (structural reframe) of T4",
    },
    # ── T5 — Tracy Chen officer pay ──────────────────────────────────────
    {
        "question": "What was Tracy Chen's officer compensation from Tracy Chen DO, Inc for 2024?",
        "phrasing_category": "A",
        "original_q": "T5",
        "expected_page": 21,
        "expected_pages": [16, 21, 49],
        "expected_answer_contains": ["$96,000", "96,000"],
        "expected_citations": [
            {"form": "Form 1125-E", "line": "2", "page": 21},
        ],
        "category": "factual_lookup",
        "difficulty": "medium",
        "notes": "Phrasing variant A (synonym) of T5",
    },
    {
        "question": "How much was Tracy paid in salary by her company in 2024?",
        "phrasing_category": "B",
        "original_q": "T5",
        "expected_page": 21,
        "expected_pages": [16, 21, 49],
        "expected_answer_contains": ["$96,000", "96,000"],
        "expected_citations": [
            {"form": "Form 1125-E", "line": "2", "page": 21},
        ],
        "category": "factual_lookup",
        "difficulty": "medium",
        "notes": "Phrasing variant B (lay/colloquial) of T5",
    },
    {
        "question": "Looking at the officer pay schedule for Tracy Chen DO, Inc, what amount was reported for Tracy Chen in 2024?",
        "phrasing_category": "C",
        "original_q": "T5",
        "expected_page": 21,
        "expected_pages": [16, 21, 49],
        "expected_answer_contains": ["$96,000", "96,000"],
        "expected_citations": [
            {"form": "Form 1125-E", "line": "2", "page": 21},
        ],
        "category": "factual_lookup",
        "difficulty": "medium",
        "notes": "Phrasing variant C (structural reframe) of T5",
    },
    # ── T6 — retained earnings ───────────────────────────────────────────
    {
        "question": "What was the accumulated equity balance for Tracy Chen DO, Inc as of year-end 2024?",
        "phrasing_category": "A",
        "original_q": "T6",
        "expected_page": 19,
        "expected_answer_contains": ["$333,706", "333,706"],
        "expected_citations": [
            {"form": "Schedule L", "line": "24", "page": 19},
            {"form": "Schedule M-2", "line": "8", "page": 20},
        ],
        "category": "factual_lookup",
        "difficulty": "medium",
        "notes": "Phrasing variant A (synonym) of T6",
    },
    {
        "question": "How much profit has Tracy's company kept in the business through the end of 2024?",
        "phrasing_category": "B",
        "original_q": "T6",
        "expected_page": 19,
        "expected_answer_contains": ["$333,706", "333,706"],
        "expected_citations": [
            {"form": "Schedule L", "line": "24", "page": 19},
            {"form": "Schedule M-2", "line": "8", "page": 20},
        ],
        "category": "factual_lookup",
        "difficulty": "medium",
        "notes": "Phrasing variant B (lay/colloquial) of T6",
    },
    {
        "question": "On the balance sheet for Tracy Chen DO, Inc, what was the ending equity balance for 2024?",
        "phrasing_category": "C",
        "original_q": "T6",
        "expected_page": 19,
        "expected_answer_contains": ["$333,706", "333,706"],
        "expected_citations": [
            {"form": "Schedule L", "line": "24", "page": 19},
            {"form": "Schedule M-2", "line": "8", "page": 20},
        ],
        "category": "factual_lookup",
        "difficulty": "medium",
        "notes": "Phrasing variant C (structural reframe) of T6",
    },
    # ── T7 — shareholder distributions ───────────────────────────────────
    {
        "question": "What was the aggregate amount distributed to shareholders by Tracy Chen DO, Inc during 2024?",
        "phrasing_category": "A",
        "original_q": "T7",
        "expected_page": 20,
        "expected_answer_contains": ["$294,484", "294,484"],
        "expected_citations": [
            {"form": "Schedule M-2", "line": "7", "page": 20},
            {"form": "Schedule K", "line": "16d", "page": 18},
        ],
        "category": "factual_lookup",
        "difficulty": "medium",
        "notes": "Phrasing variant A (synonym) of T7",
    },
    {
        "question": "How much cash did Tracy pull out of the company in 2024?",
        "phrasing_category": "B",
        "original_q": "T7",
        "expected_page": 20,
        "expected_answer_contains": ["$294,484", "294,484"],
        "expected_citations": [
            {"form": "Schedule M-2", "line": "7", "page": 20},
            {"form": "Schedule K", "line": "16d", "page": 18},
        ],
        "category": "factual_lookup",
        "difficulty": "medium",
        "notes": "Phrasing variant B (lay/colloquial) of T7",
    },
    {
        "question": "Looking at the analysis of accumulated adjustments for Tracy Chen DO, Inc, what was the total withdrawn by the owner in 2024?",
        "phrasing_category": "C",
        "original_q": "T7",
        "expected_page": 20,
        "expected_answer_contains": ["$294,484", "294,484"],
        "expected_citations": [
            {"form": "Schedule M-2", "line": "7", "page": 20},
            {"form": "Schedule K", "line": "16d", "page": 18},
        ],
        "category": "factual_lookup",
        "difficulty": "medium",
        "notes": "Phrasing variant C (structural reframe) of T7",
    },
    # ── T8 — California state tax ────────────────────────────────────────
    {
        "question": "What was the California corporate tax liability for Tracy Chen DO, Inc in 2024?",
        "phrasing_category": "A",
        "original_q": "T8",
        "expected_page": 41,
        "expected_pages": [39, 41],
        "expected_answer_contains": ["$8,354", "8,354"],
        "expected_citations": [
            {"form": "Form 100S", "line": "30", "page": 41},
            {"form": "Form 100S", "line": "21", "page": 41},
        ],
        "category": "factual_lookup",
        "difficulty": "hard",
        "notes": "Phrasing variant A (synonym) of T8",
    },
    {
        "question": "What does California charge Tracy's company in tax for 2024?",
        "phrasing_category": "B",
        "original_q": "T8",
        "expected_page": 41,
        "expected_pages": [39, 41],
        "expected_answer_contains": ["$8,354", "8,354"],
        "expected_citations": [
            {"form": "Form 100S", "line": "30", "page": 41},
            {"form": "Form 100S", "line": "21", "page": 41},
        ],
        "category": "factual_lookup",
        "difficulty": "hard",
        "notes": "Phrasing variant B (lay/colloquial) of T8",
    },
    {
        "question": "On the California corporate return for Tracy Chen DO, Inc, what was the net tax computed for 2024?",
        "phrasing_category": "C",
        "original_q": "T8",
        "expected_page": 41,
        "expected_pages": [39, 41],
        "expected_answer_contains": ["$8,354", "8,354"],
        "expected_citations": [
            {"form": "Form 100S", "line": "30", "page": 41},
            {"form": "Form 100S", "line": "21", "page": 41},
        ],
        "category": "factual_lookup",
        "difficulty": "hard",
        "notes": "Phrasing variant C (structural reframe) of T8",
    },
    # ── T9 — CA estimated tax underpayment penalty ───────────────────────
    {
        "question": "What was the underpayment penalty assessed by California on Tracy Chen DO, Inc's 2024 return?",
        "phrasing_category": "A",
        "original_q": "T9",
        "expected_page": 39,
        "expected_answer_contains": ["$426", "$426."],
        "expected_citations": [
            {"form": "Form 5806", "line": "22b", "page": 39},
            {"form": "Form 100S", "line": "44a", "page": 41},
        ],
        "category": "factual_lookup",
        "difficulty": "hard",
        "notes": "Phrasing variant A (synonym) of T9",
    },
    {
        "question": "Did California hit Tracy's company with a penalty for not paying enough during the year in 2024, and if so, how much?",
        "phrasing_category": "B",
        "original_q": "T9",
        "expected_page": 39,
        "expected_answer_contains": ["$426", "$426."],
        "expected_citations": [
            {"form": "Form 5806", "line": "22b", "page": 39},
            {"form": "Form 100S", "line": "44a", "page": 41},
        ],
        "category": "factual_lookup",
        "difficulty": "hard",
        "notes": "Phrasing variant B (lay/colloquial) of T9",
    },
    {
        "question": "On the California penalty computation form for Tracy Chen DO, Inc's 2024 return, what amount was assessed for insufficient quarterly payments?",
        "phrasing_category": "C",
        "original_q": "T9",
        "expected_page": 39,
        "expected_answer_contains": ["$426", "$426."],
        "expected_citations": [
            {"form": "Form 5806", "line": "22b", "page": 39},
            {"form": "Form 100S", "line": "44a", "page": 41},
        ],
        "category": "factual_lookup",
        "difficulty": "hard",
        "notes": "Phrasing variant C (structural reframe) of T9",
    },
    # ── T10 — stock basis ────────────────────────────────────────────────
    {
        "question": "What was Tracy Chen's adjusted shareholder basis in Tracy Chen DO, Inc as of December 31, 2024?",
        "phrasing_category": "A",
        "original_q": "T10",
        "expected_page": 30,
        "expected_answer_contains": ["$420,490", "420,490"],
        "expected_citations": [
            {"form": "Form 7203", "line": "15", "page": 30},
        ],
        "category": "factual_lookup",
        "difficulty": "hard",
        "notes": "Phrasing variant A (synonym) of T10",
    },
    {
        "question": "What's Tracy's tax cost in her company at year-end 2024?",
        "phrasing_category": "B",
        "original_q": "T10",
        "expected_page": 30,
        "expected_answer_contains": ["$420,490", "420,490"],
        "expected_citations": [
            {"form": "Form 7203", "line": "15", "page": 30},
        ],
        "category": "factual_lookup",
        "difficulty": "hard",
        "notes": "Phrasing variant B (lay/colloquial) of T10",
    },
    {
        "question": "On the shareholder basis computation for Tracy Chen DO, Inc, what was the ending balance for Tracy Chen in 2024?",
        "phrasing_category": "C",
        "original_q": "T10",
        "expected_page": 30,
        "expected_answer_contains": ["$420,490", "420,490"],
        "expected_citations": [
            {"form": "Form 7203", "line": "15", "page": 30},
        ],
        "category": "factual_lookup",
        "difficulty": "hard",
        "notes": "Phrasing variant C (structural reframe) of T10",
    },
]


MICHAEL_TJAHJADI_2024_PHRASING: list[GroundTruthItem] = [
    # ── M1 — AGI ─────────────────────────────────────────────────────────
    {
        "question": "What was Michael's income after above-the-line adjustments for 2024?",
        "phrasing_category": "A",
        "original_q": "M1",
        "expected_page": 5,
        "expected_answer_contains": ["$293,600", "293,600", "293600"],
        "expected_citations": [
            {"form": "Form 1040", "line": "11", "page": 5},
        ],
        "category": "factual_lookup",
        "difficulty": "easy",
        "notes": "Phrasing variant A (synonym) of M1",
    },
    {
        "question": "How much did Michael make overall in 2024 after adjustments?",
        "phrasing_category": "B",
        "original_q": "M1",
        "expected_page": 5,
        "expected_answer_contains": ["$293,600", "293,600", "293600"],
        "expected_citations": [
            {"form": "Form 1040", "line": "11", "page": 5},
        ],
        "category": "factual_lookup",
        "difficulty": "easy",
        "notes": "Phrasing variant B (lay/colloquial) of M1",
    },
    {
        "question": "Starting from all of Michael's income sources and subtracting the above-the-line adjustments, what was the resulting figure for 2024?",
        "phrasing_category": "C",
        "original_q": "M1",
        "expected_page": 5,
        "expected_answer_contains": ["$293,600", "293,600", "293600"],
        "expected_citations": [
            {"form": "Form 1040", "line": "11", "page": 5},
        ],
        "category": "factual_lookup",
        "difficulty": "easy",
        "notes": "Phrasing variant C (structural reframe) of M1",
    },
    # ── M2 — total income ────────────────────────────────────────────────
    {
        "question": "What was the combined income from all sources on Michael's 2024 return?",
        "phrasing_category": "A",
        "original_q": "M2",
        "expected_page": 5,
        "expected_answer_contains": ["$293,600", "293,600", "293600"],
        "expected_citations": [
            {"form": "Form 1040", "line": "9", "page": 5},
        ],
        "category": "factual_lookup",
        "difficulty": "easy",
        "notes": "Phrasing variant A (synonym) of M2",
    },
    {
        "question": "How much did Michael bring in altogether in 2024?",
        "phrasing_category": "B",
        "original_q": "M2",
        "expected_page": 5,
        "expected_answer_contains": ["$293,600", "293,600", "293600"],
        "expected_citations": [
            {"form": "Form 1040", "line": "9", "page": 5},
        ],
        "category": "factual_lookup",
        "difficulty": "easy",
        "notes": "Phrasing variant B (lay/colloquial) of M2",
    },
    {
        "question": "Adding up every income line item reported on Michael's 2024 return, what was the sum?",
        "phrasing_category": "C",
        "original_q": "M2",
        "expected_page": 5,
        "expected_answer_contains": ["$293,600", "293,600", "293600"],
        "expected_citations": [
            {"form": "Form 1040", "line": "9", "page": 5},
        ],
        "category": "factual_lookup",
        "difficulty": "easy",
        "notes": "Phrasing variant C (structural reframe) of M2",
    },
    # ── M3 — W-2 wages ───────────────────────────────────────────────────
    {
        "question": "What was Michael's employment compensation for 2024?",
        "phrasing_category": "A",
        "original_q": "M3",
        "expected_page": 5,
        "expected_answer_contains": ["$271,792", "271,792", "271792"],
        "expected_citations": [
            {"form": "Form 1040", "line": "1a", "page": 5},
        ],
        "category": "factual_lookup",
        "difficulty": "easy",
        "notes": "Phrasing variant A (synonym) of M3",
    },
    {
        "question": "How much did Michael's job pay him in 2024?",
        "phrasing_category": "B",
        "original_q": "M3",
        "expected_page": 5,
        "expected_answer_contains": ["$271,792", "271,792", "271792"],
        "expected_citations": [
            {"form": "Form 1040", "line": "1a", "page": 5},
        ],
        "category": "factual_lookup",
        "difficulty": "easy",
        "notes": "Phrasing variant B (lay/colloquial) of M3",
    },
    {
        "question": "Looking at the salary and compensation line on Michael's 2024 return, what amount was reported?",
        "phrasing_category": "C",
        "original_q": "M3",
        "expected_page": 5,
        "expected_answer_contains": ["$271,792", "271,792", "271792"],
        "expected_citations": [
            {"form": "Form 1040", "line": "1a", "page": 5},
        ],
        "category": "factual_lookup",
        "difficulty": "easy",
        "notes": "Phrasing variant C (structural reframe) of M3",
    },
    # ── M4 — taxable interest ────────────────────────────────────────────
    {
        "question": "What was Michael's interest income subject to tax for 2024?",
        "phrasing_category": "A",
        "original_q": "M4",
        "expected_page": 5,
        "expected_answer_contains": ["$7.00", "$7."],
        "expected_citations": [
            {"form": "Form 1040", "line": "2b", "page": 5},
            {"form": "Schedule B", "line": "4", "page": 11},
        ],
        "category": "factual_lookup",
        "difficulty": "medium",
        "notes": "Phrasing variant A (synonym) of M4",
    },
    {
        "question": "How much did Michael earn in bank interest in 2024?",
        "phrasing_category": "B",
        "original_q": "M4",
        "expected_page": 5,
        "expected_answer_contains": ["$7.00", "$7."],
        "expected_citations": [
            {"form": "Form 1040", "line": "2b", "page": 5},
            {"form": "Schedule B", "line": "4", "page": 11},
        ],
        "category": "factual_lookup",
        "difficulty": "medium",
        "notes": "Phrasing variant B (lay/colloquial) of M4",
    },
    {
        "question": "On the interest income line of Michael's 2024 return, what taxable amount was reported?",
        "phrasing_category": "C",
        "original_q": "M4",
        "expected_page": 5,
        "expected_answer_contains": ["$7.00", "$7."],
        "expected_citations": [
            {"form": "Form 1040", "line": "2b", "page": 5},
            {"form": "Schedule B", "line": "4", "page": 11},
        ],
        "category": "factual_lookup",
        "difficulty": "medium",
        "notes": "Phrasing variant C (structural reframe) of M4",
    },
    # ── M5 — ordinary dividends ──────────────────────────────────────────
    {
        "question": "What was the total dividend income reported on Michael's 2024 return?",
        "phrasing_category": "A",
        "original_q": "M5",
        "expected_page": 5,
        "expected_answer_contains": ["$13,267", "13,267", "13267"],
        "expected_citations": [
            {"form": "Form 1040", "line": "3b", "page": 5},
            {"form": "Schedule B", "line": "6", "page": 11},
        ],
        "category": "factual_lookup",
        "difficulty": "medium",
        "notes": "Phrasing variant A (synonym) of M5",
    },
    {
        "question": "How much did Michael get in dividends from his investments in 2024?",
        "phrasing_category": "B",
        "original_q": "M5",
        "expected_page": 5,
        "expected_answer_contains": ["$13,267", "13,267", "13267"],
        "expected_citations": [
            {"form": "Form 1040", "line": "3b", "page": 5},
            {"form": "Schedule B", "line": "6", "page": 11},
        ],
        "category": "factual_lookup",
        "difficulty": "medium",
        "notes": "Phrasing variant B (lay/colloquial) of M5",
    },
    {
        "question": "On the dividends line of Michael's 2024 return, what was the ordinary amount reported?",
        "phrasing_category": "C",
        "original_q": "M5",
        "expected_page": 5,
        "expected_answer_contains": ["$13,267", "13,267", "13267"],
        "expected_citations": [
            {"form": "Form 1040", "line": "3b", "page": 5},
            {"form": "Schedule B", "line": "6", "page": 11},
        ],
        "category": "factual_lookup",
        "difficulty": "medium",
        "notes": "Phrasing variant C (structural reframe) of M5",
    },
    # ── M6 — capital gains ───────────────────────────────────────────────
    {
        "question": "What was the net gain from investment sales reported on Michael's 2024 return?",
        "phrasing_category": "A",
        "original_q": "M6",
        "expected_page": 5,
        "expected_answer_contains": ["$7,584", "7,584", "7584"],
        "expected_citations": [
            {"form": "Form 1040", "line": "7", "page": 5},
            {"form": "Schedule D", "line": "16", "page": 13},
        ],
        "category": "factual_lookup",
        "difficulty": "medium",
        "notes": "Phrasing variant A (synonym) of M6",
    },
    {
        "question": "How much did Michael make selling stocks and investments in 2024?",
        "phrasing_category": "B",
        "original_q": "M6",
        "expected_page": 5,
        "expected_answer_contains": ["$7,584", "7,584", "7584"],
        "expected_citations": [
            {"form": "Form 1040", "line": "7", "page": 5},
            {"form": "Schedule D", "line": "16", "page": 13},
        ],
        "category": "factual_lookup",
        "difficulty": "medium",
        "notes": "Phrasing variant B (lay/colloquial) of M6",
    },
    {
        "question": "After netting all investment sale proceeds against their cost basis, what was Michael's result for 2024?",
        "phrasing_category": "C",
        "original_q": "M6",
        "expected_page": 5,
        "expected_answer_contains": ["$7,584", "7,584", "7584"],
        "expected_citations": [
            {"form": "Form 1040", "line": "7", "page": 5},
            {"form": "Schedule D", "line": "16", "page": 13},
        ],
        "category": "factual_lookup",
        "difficulty": "medium",
        "notes": "Phrasing variant C (structural reframe) of M6",
    },
    # ── M7 — charitable contributions ────────────────────────────────────
    {
        "question": "What were Michael's charitable donations for 2024?",
        "phrasing_category": "A",
        "original_q": "M7",
        "expected_page": 10,
        "expected_answer_contains": ["$9,630", "9,630", "9630"],
        "expected_citations": [
            {"form": "Schedule A", "line": "11", "page": 10},
            {"form": "Schedule A", "line": "14", "page": 10},
        ],
        "category": "factual_lookup",
        "difficulty": "medium",
        "notes": "Phrasing variant A (synonym) of M7",
    },
    {
        "question": "How much did Michael give away to nonprofits in 2024?",
        "phrasing_category": "B",
        "original_q": "M7",
        "expected_page": 10,
        "expected_answer_contains": ["$9,630", "9,630", "9630"],
        "expected_citations": [
            {"form": "Schedule A", "line": "11", "page": 10},
            {"form": "Schedule A", "line": "14", "page": 10},
        ],
        "category": "factual_lookup",
        "difficulty": "medium",
        "notes": "Phrasing variant B (lay/colloquial) of M7",
    },
    {
        "question": "On the charitable giving section of Michael's 2024 return, what total was claimed?",
        "phrasing_category": "C",
        "original_q": "M7",
        "expected_page": 10,
        "expected_answer_contains": ["$9,630", "9,630", "9630"],
        "expected_citations": [
            {"form": "Schedule A", "line": "11", "page": 10},
            {"form": "Schedule A", "line": "14", "page": 10},
        ],
        "category": "factual_lookup",
        "difficulty": "medium",
        "notes": "Phrasing variant C (structural reframe) of M7",
    },
    # ── M8 — total tax ───────────────────────────────────────────────────
    {
        "question": "What was the combined federal tax computed on Michael's 2024 return?",
        "phrasing_category": "A",
        "original_q": "M8",
        "expected_page": 6,
        "expected_answer_contains": ["$42,645", "42,645", "42645"],
        "expected_citations": [
            {"form": "Form 1040", "line": "24", "page": 6},
        ],
        "category": "factual_lookup",
        "difficulty": "easy",
        "notes": "Phrasing variant A (synonym) of M8",
    },
    {
        "question": "How much tax did Michael's return calculate for 2024?",
        "phrasing_category": "B",
        "original_q": "M8",
        "expected_page": 6,
        "expected_answer_contains": ["$42,645", "42,645", "42645"],
        "expected_citations": [
            {"form": "Form 1040", "line": "24", "page": 6},
        ],
        "category": "factual_lookup",
        "difficulty": "easy",
        "notes": "Phrasing variant B (lay/colloquial) of M8",
    },
    {
        "question": "After applying all credits on Michael's 2024 return, what was the resulting tax figure on the summary page?",
        "phrasing_category": "C",
        "original_q": "M8",
        "expected_page": 6,
        "expected_answer_contains": ["$42,645", "42,645", "42645"],
        "expected_citations": [
            {"form": "Form 1040", "line": "24", "page": 6},
        ],
        "category": "factual_lookup",
        "difficulty": "easy",
        "notes": "Phrasing variant C (structural reframe) of M8",
    },
    # ── M9 — HSA contribution limit ──────────────────────────────────────
    {
        "question": "What was the maximum allowable health savings contribution for Michael in 2024?",
        "phrasing_category": "A",
        "original_q": "M9",
        "expected_page": 24,
        "expected_answer_contains": ["$4,150", "4,150", "4150"],
        "expected_citations": [
            {"form": "Form 8889", "line": "3", "page": 24},
            {"form": "Form 8889", "line": "8", "page": 24},
        ],
        "category": "factual_lookup",
        "difficulty": "hard",
        "notes": "Phrasing variant A (synonym) of M9",
    },
    {
        "question": "How much was Michael allowed to put into his medical savings plan for 2024?",
        "phrasing_category": "B",
        "original_q": "M9",
        "expected_page": 24,
        "expected_answer_contains": ["$4,150", "4,150", "4150"],
        "expected_citations": [
            {"form": "Form 8889", "line": "3", "page": 24},
            {"form": "Form 8889", "line": "8", "page": 24},
        ],
        "category": "factual_lookup",
        "difficulty": "hard",
        "notes": "Phrasing variant B (lay/colloquial) of M9",
    },
    {
        "question": "Based on Michael's high-deductible health plan coverage in 2024, what was the contribution ceiling?",
        "phrasing_category": "C",
        "original_q": "M9",
        "expected_page": 24,
        "expected_answer_contains": ["$4,150", "4,150", "4150"],
        "expected_citations": [
            {"form": "Form 8889", "line": "3", "page": 24},
            {"form": "Form 8889", "line": "8", "page": 24},
        ],
        "category": "factual_lookup",
        "difficulty": "hard",
        "notes": "Phrasing variant C (structural reframe) of M9",
    },
    # ── M10 — excess Roth IRA contribution ───────────────────────────────
    {
        "question": "Was there a retirement account over-contribution on Michael's 2024 return, and what was the amount?",
        "phrasing_category": "A",
        "original_q": "M10",
        "expected_page": 21,
        "expected_answer_contains": ["$7,000", "7,000", "7000"],
        "expected_citations": [
            {"form": "Form 5329", "line": "18", "page": 21},
            {"form": "Form 5329", "line": "24", "page": 21},
            {"form": "Schedule 2", "line": "24", "page": 7},
        ],
        "category": "exact_term_match",
        "difficulty": "hard",
        "notes": "Phrasing variant A (synonym) of M10",
    },
    {
        "question": "Did Michael put too much into his Roth in 2024? If so, what was the extra amount?",
        "phrasing_category": "B",
        "original_q": "M10",
        "expected_page": 21,
        "expected_answer_contains": ["$7,000", "7,000", "7000"],
        "expected_citations": [
            {"form": "Form 5329", "line": "18", "page": 21},
            {"form": "Form 5329", "line": "24", "page": 21},
            {"form": "Schedule 2", "line": "24", "page": 7},
        ],
        "category": "exact_term_match",
        "difficulty": "hard",
        "notes": "Phrasing variant B (lay/colloquial) of M10",
    },
    {
        "question": "On the additional taxes form for Michael's 2024 return, was a penalty assessed for excess retirement contributions, and what was the amount?",
        "phrasing_category": "C",
        "original_q": "M10",
        "expected_page": 21,
        "expected_answer_contains": ["$7,000", "7,000", "7000"],
        "expected_citations": [
            {"form": "Form 5329", "line": "18", "page": 21},
            {"form": "Form 5329", "line": "24", "page": 21},
            {"form": "Schedule 2", "line": "24", "page": 7},
        ],
        "category": "exact_term_match",
        "difficulty": "hard",
        "notes": "Phrasing variant C (structural reframe) of M10",
    },
]


# Registry for phrasing-variance fixtures
CLIENT_PHRASING_VARIANCE: dict[str, list[GroundTruthItem]] = {
    "b9708054-0b27-4041-9e69-93b20f75b1ac": TRACY_CHEN_DO_INC_2024_PHRASING,
    "92574da3-13ca-4017-a233-54c99d2ae2ae": MICHAEL_TJAHJADI_2024_PHRASING,
}


def get_phrasing_variance(client_id: str) -> list[GroundTruthItem] | None:
    """Return phrasing-variance fixture for a client, or None."""
    return CLIENT_PHRASING_VARIANCE.get(str(client_id))

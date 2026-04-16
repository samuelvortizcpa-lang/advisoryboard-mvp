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

from typing import TypedDict


class ExpectedCitation(TypedDict):
    form: str   # e.g., "Form 1040", "Schedule A", "Form 8889"
    line: str   # string, not int — "2b", "1a", "25a" exist
    page: int   # 1-indexed PDF page


class GroundTruthItem(TypedDict):
    question: str
    expected_page: int
    expected_answer_contains: list[str]
    expected_citations: list[ExpectedCitation]
    category: str
    difficulty: str
    notes: str


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
        ],
        "category": "exact_term_match",
        "difficulty": "hard",
        "notes": "Form 5329 — excess contribution, requires understanding of penalty form",
    },
]


# Tracy Chen DO, Inc — 2024 Form 1120-S (S-corp, single document)
TRACY_CHEN_DO_INC_2024: list[GroundTruthItem] = [
    {
        "question": "What was Tracy Chen DO, Inc's ordinary business income in 2024?",
        "expected_page": 16,
        "expected_answer_contains": ["$556,379", "556,379"],
        "expected_citations": [
            {"form": "Form 1120-S", "line": "22", "page": 16},
            {"form": "Schedule K", "line": "1", "page": 18},
        ],
        "category": "factual_lookup",
        "difficulty": "easy",
        "notes": "Ordinary business income. S-corp equivalent of total-income baseline.",
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
        "expected_answer_contains": ["$364,521", "364,521"],
        "expected_citations": [
            {"form": "Form 1120-S", "line": "21", "page": 16},
        ],
        "category": "factual_lookup",
        "difficulty": "medium",
        "notes": "Aggregation retrieval. Sum of Lines 7-20.",
    },
    {
        "question": "How much was Tracy Chen paid as an officer of Tracy Chen DO, Inc in 2024?",
        "expected_page": 21,
        "expected_answer_contains": ["$96,000", "96,000"],
        "expected_citations": [
            {"form": "Form 1125-E", "line": "2", "page": 21},
        ],
        "category": "factual_lookup",
        "difficulty": "medium",
        "notes": "Individual officer comp. Sole officer so $ = Q3. Citation weak spot: 1125-E table row unnumbered, Line 2 (total) used as acceptable cite.",
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
        "expected_answer_contains": ["$8,354", "8,354"],
        "expected_citations": [
            {"form": "Form 100S", "line": "30", "page": 41},
            {"form": "Form 100S", "line": "21", "page": 41},
        ],
        "category": "factual_lookup",
        "difficulty": "hard",
        "notes": "Federal/state disambiguation. Watch for confusion with $8,780 (total due) or $556,904 (CA taxable income).",
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

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


# Registry keyed by client_id (UUID as string)
CLIENT_GROUND_TRUTH: dict[str, list[GroundTruthItem]] = {
    "92574da3-13ca-4017-a233-54c99d2ae2ae": MICHAEL_TJAHJADI_2024,
}


def get_ground_truth(client_id: str) -> list[GroundTruthItem] | None:
    """Return the ground-truth test set for a client, or None if not defined."""
    return CLIENT_GROUND_TRUTH.get(str(client_id))

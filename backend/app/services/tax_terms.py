"""
Financial term expansion for RAG retrieval.

When a user asks about "AGI", we also need to search for "Adjusted Gross
Income" and "Line 11" — otherwise the vector search may return chunks
about estimated payments or other tax forms that are semantically similar
but don't contain the actual answer.

Each key maps to:
  - expansions: alternative phrases to search for
  - forms: IRS form identifiers that contain this data (used for chunk boosting)
"""

from __future__ import annotations

# Maps lowercase trigger terms → expansion data.
# The key can be a single word or a phrase.  During query expansion,
# we check for both exact phrase matches and individual word matches.
TERM_EXPANSIONS: dict[str, dict] = {
    # ── Form 1040 core lines ────────────────────────────────────────
    "agi": {
        "expansions": [
            "adjusted gross income",
            "line 11",
            "form 1040",
        ],
        "forms": ["1040"],
    },
    "adjusted gross income": {
        "expansions": ["agi", "line 11", "form 1040"],
        "forms": ["1040"],
    },
    "total income": {
        "expansions": ["line 9", "form 1040", "total income"],
        "forms": ["1040"],
    },
    "taxable income": {
        "expansions": ["line 15", "form 1040", "taxable income"],
        "forms": ["1040"],
    },
    "filing status": {
        "expansions": [
            "single",
            "married filing jointly",
            "married filing separately",
            "head of household",
            "qualifying surviving spouse",
            "form 1040",
        ],
        "forms": ["1040"],
    },
    "standard deduction": {
        "expansions": ["line 12", "standard deduction", "itemized deductions", "form 1040"],
        "forms": ["1040"],
    },
    "itemized deductions": {
        "expansions": ["schedule a", "line 12", "form 1040"],
        "forms": ["1040", "schedule a"],
    },
    "deductions": {
        "expansions": [
            "line 12",
            "line 13",
            "standard deduction",
            "itemized deductions",
            "qualified business income deduction",
            "form 1040",
        ],
        "forms": ["1040"],
    },
    "total tax": {
        "expansions": ["line 24", "total tax", "form 1040"],
        "forms": ["1040"],
    },
    "tax owed": {
        "expansions": ["line 37", "amount you owe", "line 24", "total tax", "form 1040"],
        "forms": ["1040"],
    },
    "refund": {
        "expansions": ["line 34", "overpaid", "refund", "line 35a", "form 1040"],
        "forms": ["1040"],
    },
    "wages": {
        "expansions": ["line 1a", "wages", "salaries", "tips", "w-2", "form 1040"],
        "forms": ["1040", "w-2"],
    },
    "estimated payments": {
        "expansions": [
            "estimated tax payments",
            "1040-es",
            "line 26",
            "form 1040",
        ],
        "forms": ["1040", "1040-es"],
    },
    "estimated tax": {
        "expansions": [
            "estimated tax payments",
            "1040-es",
            "payment voucher",
            "line 26",
        ],
        "forms": ["1040", "1040-es"],
    },

    # ── Schedule C ───────────────────────────────────────────────────
    "business income": {
        "expansions": ["schedule c", "net profit", "line 31", "self-employment"],
        "forms": ["schedule c"],
    },
    "self-employment": {
        "expansions": ["schedule c", "schedule se", "self-employment tax", "net profit"],
        "forms": ["schedule c", "schedule se"],
    },

    # ── Schedule D / 8949 ────────────────────────────────────────────
    "capital gains": {
        "expansions": ["schedule d", "form 8949", "capital gain", "capital loss", "line 7"],
        "forms": ["schedule d", "8949"],
    },
    "capital loss": {
        "expansions": ["schedule d", "form 8949", "capital gain", "capital loss"],
        "forms": ["schedule d", "8949"],
    },

    # ── Schedule E ───────────────────────────────────────────────────
    "rental income": {
        "expansions": ["schedule e", "rental", "royalties", "partnerships", "s corporations"],
        "forms": ["schedule e"],
    },

    # ── QBI / 199A ───────────────────────────────────────────────────
    "qbi": {
        "expansions": [
            "qualified business income",
            "section 199a",
            "form 8995",
            "qbi deduction",
            "line 13",
        ],
        "forms": ["8995"],
    },
    "qualified business income": {
        "expansions": ["qbi", "section 199a", "form 8995", "line 13"],
        "forms": ["8995"],
    },

    # ── W-2 ──────────────────────────────────────────────────────────
    "w-2": {
        "expansions": ["wages", "box 1", "federal income tax withheld", "box 2"],
        "forms": ["w-2"],
    },
    "w2": {
        "expansions": ["wages", "box 1", "federal income tax withheld", "box 2", "w-2"],
        "forms": ["w-2"],
    },

    # ── K-1 ──────────────────────────────────────────────────────────
    "k-1": {
        "expansions": [
            "schedule k-1",
            "partnership",
            "s corporation",
            "ordinary business income",
            "box 1",
        ],
        "forms": ["k-1", "schedule k-1"],
    },
    "k1": {
        "expansions": ["schedule k-1", "k-1", "partnership", "s corporation"],
        "forms": ["k-1", "schedule k-1"],
    },
}


def expand_query(query: str) -> tuple[list[str], list[str]]:
    """
    Expand a user query with financial term synonyms.

    Returns:
        (expansion_terms, relevant_forms)

    expansion_terms: additional phrases to embed and search for.
    relevant_forms: form identifiers (e.g. "1040", "schedule c") to boost
                    in chunk ranking.
    """
    query_lower = query.lower()
    all_expansions: list[str] = []
    all_forms: list[str] = []

    for trigger, data in TERM_EXPANSIONS.items():
        if trigger in query_lower:
            all_expansions.extend(data["expansions"])
            all_forms.extend(data["forms"])

    # Deduplicate while preserving order
    seen_exp: set[str] = set()
    unique_expansions: list[str] = []
    for e in all_expansions:
        if e.lower() not in seen_exp:
            seen_exp.add(e.lower())
            unique_expansions.append(e)

    seen_forms: set[str] = set()
    unique_forms: list[str] = []
    for f in all_forms:
        if f.lower() not in seen_forms:
            seen_forms.add(f.lower())
            unique_forms.append(f)

    return unique_expansions, unique_forms

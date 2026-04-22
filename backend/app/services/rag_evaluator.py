"""
RAG Evaluation Framework.

Runs a set of test questions through the live RAG pipeline and measures
retrieval quality and response accuracy via keyword matching.

Two evaluation modes:
  - Keyword (run_evaluation): generic 8-question set, keyword hit scoring
  - Ground truth (run_ground_truth_evaluation): per-client test set with
    exact page attribution and answer-substring matching

Usage (API):
    POST /api/admin/evaluate-rag/{client_id}
    POST /api/admin/evaluate-rag-ground-truth/{client_id}

This is an internal tool — not user-facing.  Each run makes 8-10 LLM calls
(~$0.05-0.10), so don't run on every deploy.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ── Test question set ────────────────────────────────────────────────────────

EVAL_QUESTIONS: list[dict[str, Any]] = [
    {
        "question": "What was the adjusted gross income on the 2024 tax return?",
        "expected_keywords": ["adjusted gross income", "AGI", "line 11"],
        "category": "factual_lookup",
        "difficulty": "easy",
    },
    {
        "question": "What is the total amount of wages reported on the W-2?",
        "expected_keywords": ["wages", "box 1", "w-2"],
        "category": "factual_lookup",
        "difficulty": "easy",
    },
    {
        "question": "What were the Schedule C deductions?",
        "expected_keywords": ["schedule c", "deductions", "business expenses"],
        "category": "factual_lookup",
        "difficulty": "medium",
    },
    {
        "question": "Compare the client's income between 2023 and 2024",
        "expected_keywords": ["2023", "2024", "income", "change", "increase", "decrease"],
        "category": "multi_doc_synthesis",
        "difficulty": "hard",
    },
    {
        "question": "What action items are still pending from the last meeting?",
        "expected_keywords": ["action", "pending", "meeting", "follow-up"],
        "category": "cross_source",
        "difficulty": "medium",
    },
    {
        "question": "What is the K-1 Box 14 Code A amount?",
        "expected_keywords": ["k-1", "box 14", "code a"],
        "category": "exact_term_match",
        "difficulty": "hard",
    },
    {
        "question": "What charitable contributions were claimed?",
        "expected_keywords": ["charitable", "contributions", "donations", "schedule a"],
        "category": "factual_lookup",
        "difficulty": "medium",
    },
    {
        "question": "What is the depreciation schedule for the rental property?",
        "expected_keywords": ["depreciation", "rental", "property", "schedule"],
        "category": "factual_lookup",
        "difficulty": "hard",
    },
]


# ── Scoring helpers ──────────────────────────────────────────────────────────


def _keyword_hit(text: str, keywords: list[str]) -> bool:
    """Return True if ANY expected keyword appears in *text* (case-insensitive)."""
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in keywords)


def _keyword_hit_count(text: str, keywords: list[str]) -> int:
    """Count how many distinct keywords appear in *text*."""
    text_lower = text.lower()
    return sum(1 for kw in keywords if kw.lower() in text_lower)


def _normalize_for_match(text: str) -> str:
    """Normalize text for answer-substring matching: lowercase, strip $, commas, collapse whitespace."""
    t = text.lower()
    t = t.replace("$", "").replace(",", "")
    t = re.sub(r"\s+", " ", t).strip()
    return t


# Matches both smart_chunk format "[Page N]" and form-aware chunk
# prefix format "| Page N |" or "| Page N ]". Used for eval scoring only.
_PAGE_MARKER_PATTERN = re.compile(
    r"\[Page\s+(\d+)\]"            # smart_chunk: [Page 5]
    r"|"
    r"\|\s*Page\s+(\d+)\s*[\|\]]"  # form-aware: | Page 5 | or | Page 5 ]
)


def _extract_pages_from_chunks(chunk_texts: list[str]) -> list[int]:
    """Extract unique page numbers from chunk texts.

    Supports both legacy smart_chunk [Page N] markers and current
    form-aware chunk prefixes like [TAX YEAR ... | Page N | ...].
    """
    pages: set[int] = set()
    for text in chunk_texts:
        for match in _PAGE_MARKER_PATTERN.finditer(text):
            page_str = match.group(1) or match.group(2)
            if page_str:
                pages.add(int(page_str))
    return sorted(pages)


_FORM_PATTERN = re.compile(
    r"(?:Form|Schedule)\s+[A-Z0-9][\w-]*",
    re.IGNORECASE,
)
# Matches "Line 11", "Line 44a", "Box 17", "Box 1a" — captures the number+suffix.
_LINE_OR_BOX_PATTERN = re.compile(
    r"\b(?:[Ll]ine|[Bb]ox)\s+(\d{1,3}[a-z]?)\b"
)


def _normalize_form(form: str) -> str:
    """Normalize a form name: lowercase + collapse whitespace."""
    return re.sub(r"\s+", " ", form.strip().lower())


def _extract_citations(text: str) -> list[dict[str, str]]:
    """Extract (form, line) pairs via Cartesian product. Strict: both required.

    "Box N" references (K-1, W-2) are normalized to the same "line" key
    so downstream matching is uniform.
    """
    forms_raw = _FORM_PATTERN.findall(text)
    lines_raw = _LINE_OR_BOX_PATTERN.findall(text)
    if not forms_raw or not lines_raw:
        return []
    forms_norm = sorted({_normalize_form(f) for f in forms_raw})
    lines_dedup = sorted(set(lines_raw))
    return [
        {"form": f, "line": l}
        for f in forms_norm
        for l in lines_dedup
    ]


def _line_matches(extracted_line: str, expected_line: str) -> bool:
    """Tolerant line-number comparison.

    Rules:
    - Exact match (case-insensitive): "44a" == "44a" → True
    - Base-number match: extracted "44" matches expected "44a" (suffix tolerance)
    - But NOT prefix match: extracted "4" must NOT match expected "44"
    """
    ext = extracted_line.lower()
    exp = expected_line.lower()
    if ext == exp:
        return True
    # Allow extracted base number to match expected number+suffix.
    # "44" matches "44a" but "4" must not match "44".
    # Strip trailing letters from expected to get its base number.
    exp_base = re.sub(r"[a-z]+$", "", exp)
    ext_base = re.sub(r"[a-z]+$", "", ext)
    if ext_base == exp_base:
        return True
    return False


def _form_matches(extracted_form: str, expected_form: str) -> bool:
    """Tolerant form-name comparison.

    Rules:
    - Exact match (already normalized to lowercase): always wins
    - Suffix tolerance: extracted "form 100" matches expected "form 100s"
      (the LLM sometimes drops the S-corp suffix)
    - But "schedule k" must NOT match "schedule k-1" (different forms)
    """
    if extracted_form == expected_form:
        return True
    # Allow extracted to match if expected = extracted + single letter suffix.
    # "form 100" → "form 100s" OK.  "form 1120" → "form 1120-s" needs dash handling.
    # Check: expected starts with extracted AND the remainder is just a letter or -letter.
    if expected_form.startswith(extracted_form):
        remainder = expected_form[len(extracted_form):]
        # Allow: "s", "-s", "-e" (single letter or dash+letter)
        if re.fullmatch(r"-?[a-z]", remainder):
            return True
    return False


def _citation_match(
    extracted: list[dict[str, str]],
    expected: list[dict],
) -> bool:
    """Return True if any extracted (form, line) pair matches any expected citation.

    Uses tolerant matching for both form names and line numbers.
    """
    for exp in expected:
        exp_form = _normalize_form(exp["form"])
        exp_line = exp["line"].lower()
        for ext in extracted:
            if (_form_matches(ext["form"], exp_form)
                    and _line_matches(ext["line"], exp_line)):
                return True
    return False


# ── Main evaluation runner (keyword) ─────────────────────────────────────────


async def run_evaluation(
    client_id: str | UUID,
    user_id: str,
    db: Session,
) -> dict[str, Any]:
    """
    Run all EVAL_QUESTIONS through the live RAG pipeline and score results.

    Returns a summary dict suitable for JSON serialization and storage.
    """
    from app.services import rag_service

    client_id = UUID(str(client_id))
    details: list[dict[str, Any]] = []
    total_latency_ms = 0.0

    for q in EVAL_QUESTIONS:
        question = q["question"]
        expected = q["expected_keywords"]

        start = time.monotonic()
        try:
            result = await rag_service.answer_question(
                db,
                client_id=client_id,
                question=question,
                user_id=user_id,
                is_admin_eval=True,
            )
            latency_ms = (time.monotonic() - start) * 1000
            answer = result.get("answer", "")
            sources = result.get("sources", [])
            confidence_score = result.get("confidence_score", 0.0)
            model_used = result.get("model_used", "unknown")

            # Combine all source chunk text for retrieval scoring
            chunks_text = " ".join(
                s.get("chunk_text", "") or s.get("preview", "")
                for s in sources
            )

            retrieval_hit = _keyword_hit(chunks_text, expected)
            response_hit = _keyword_hit(answer, expected)
            retrieval_keyword_count = _keyword_hit_count(chunks_text, expected)
            response_keyword_count = _keyword_hit_count(answer, expected)

            detail = {
                "question": question,
                "category": q["category"],
                "difficulty": q["difficulty"],
                "expected_keywords": expected,
                "retrieval_hit": retrieval_hit,
                "response_hit": response_hit,
                "retrieval_keywords_found": retrieval_keyword_count,
                "response_keywords_found": response_keyword_count,
                "confidence_score": confidence_score,
                "model_used": model_used,
                "latency_ms": round(latency_ms, 1),
                "source_count": len(sources),
                "answer_preview": answer[:300],
                "error": None,
            }

        except Exception as exc:
            latency_ms = (time.monotonic() - start) * 1000
            logger.warning("Eval question failed: %s — %s", question[:50], exc)
            detail = {
                "question": question,
                "category": q["category"],
                "difficulty": q["difficulty"],
                "expected_keywords": expected,
                "retrieval_hit": False,
                "response_hit": False,
                "retrieval_keywords_found": 0,
                "response_keywords_found": 0,
                "confidence_score": 0.0,
                "model_used": "none",
                "latency_ms": round(latency_ms, 1),
                "source_count": 0,
                "answer_preview": "",
                "error": str(exc),
            }

        details.append(detail)
        total_latency_ms += latency_ms

    # ── Aggregate scores ─────────────────────────────────────────────────

    total = len(details)
    retrieval_hits = sum(1 for d in details if d["retrieval_hit"])
    response_hits = sum(1 for d in details if d["response_hit"])
    errors = sum(1 for d in details if d["error"])

    # By category
    by_category: dict[str, dict[str, Any]] = {}
    for d in details:
        cat = d["category"]
        if cat not in by_category:
            by_category[cat] = {"questions": 0, "retrieval_hits": 0, "response_hits": 0}
        by_category[cat]["questions"] += 1
        if d["retrieval_hit"]:
            by_category[cat]["retrieval_hits"] += 1
        if d["response_hit"]:
            by_category[cat]["response_hits"] += 1

    # By difficulty
    by_difficulty: dict[str, dict[str, Any]] = {}
    for d in details:
        diff = d["difficulty"]
        if diff not in by_difficulty:
            by_difficulty[diff] = {"questions": 0, "retrieval_hits": 0, "response_hits": 0}
        by_difficulty[diff]["questions"] += 1
        if d["retrieval_hit"]:
            by_difficulty[diff]["retrieval_hits"] += 1
        if d["response_hit"]:
            by_difficulty[diff]["response_hits"] += 1

    return {
        "test_set": "keyword_v1",
        "total_questions": total,
        "retrieval_hit_rate": round(retrieval_hits / total, 3) if total else 0,
        "response_keyword_rate": round(response_hits / total, 3) if total else 0,
        "avg_latency_ms": round(total_latency_ms / total, 1) if total else 0,
        "total_latency_ms": round(total_latency_ms, 1),
        "errors": errors,
        "by_category": by_category,
        "by_difficulty": by_difficulty,
        "details": details,
    }


# ── Ground-truth evaluation runner ───────────────────────────────────────────


async def run_ground_truth_evaluation(
    client_id: str | UUID,
    db: Session,
) -> dict[str, Any]:
    """
    Run per-client ground-truth questions through the live RAG pipeline.

    Scoring:
    - Retrieval hit: expected_page appears in [Page N] markers extracted
      from the top-K post-rerank chunks.
    - Response hit: at least one expected_answer_contains variant appears
      (after normalization) in the LLM response.

    Returns a summary dict compatible with run_evaluation() shape
    (same top-level keys) plus a per_question debugging array.
    """
    from app.services import rag_service
    from app.services.rag_eval_fixtures import get_ground_truth

    client_id_str = str(client_id)
    client_id_uuid = UUID(client_id_str)

    ground_truth = get_ground_truth(client_id_str)
    if ground_truth is None:
        raise ValueError(
            f"No ground-truth test set defined for client {client_id_str}"
        )

    per_question: list[dict[str, Any]] = []
    total_latency_ms = 0.0

    for item in ground_truth:
        question = item["question"]
        expected_page = item["expected_page"]
        expected_pages: list[int] = item.get("expected_pages") or [expected_page]
        expected_answers = item["expected_answer_contains"]

        start = time.monotonic()
        try:
            result = await rag_service.answer_question(
                db,
                client_id=client_id_uuid,
                question=question,
                user_id="eval_ground_truth",
                include_debug_chunks=True,
                is_admin_eval=True,
            )
            latency_ms = (time.monotonic() - start) * 1000

            answer = result.get("answer", "")
            debug_chunks = result.get("retrieved_chunks_debug", [])

            # Extract [Page N] markers from all raw retrieved chunk texts
            chunk_texts = [
                c.get("chunk_text", "") for c in debug_chunks
            ]
            retrieved_pages = _extract_pages_from_chunks(chunk_texts)

            # Retrieval scoring: any acceptable page found in retrieved chunks
            retrieval_hit = any(p in retrieved_pages for p in expected_pages)

            # Response scoring: normalized substring match
            norm_answer = _normalize_for_match(answer)
            response_hit = any(
                _normalize_for_match(variant) in norm_answer
                for variant in expected_answers
            )

            # Citation scoring: regex extraction + strict form+line match
            expected_citations = item.get("expected_citations", [])
            extracted_citations = _extract_citations(answer)
            citation_hit = (
                _citation_match(extracted_citations, expected_citations)
                if expected_citations
                else False
            )

            # Build top-5 chunk rank/page debug info
            top_chunk_ranks_and_pages = []
            for c in debug_chunks[:5]:
                pages_in_chunk = [
                    int(m) for m in re.findall(r"\[Page\s+(\d+)\]", c.get("chunk_text", ""))
                ]
                top_chunk_ranks_and_pages.append({
                    "rank": c.get("rank", 0),
                    "pages_in_chunk": pages_in_chunk,
                })

            per_question.append({
                "question": question,
                "category": item["category"],
                "difficulty": item["difficulty"],
                "notes": item.get("notes", ""),
                "expected_page": expected_page,
                "retrieved_pages": retrieved_pages,
                "retrieval_hit": retrieval_hit,
                "expected_answer_contains": expected_answers,
                "response_snippet": answer[:300],
                "response_hit": response_hit,
                "expected_citations": expected_citations,
                "extracted_citations": extracted_citations,
                "citation_hit": citation_hit,
                "latency_ms": round(latency_ms, 1),
                "retrieved_chunk_count": len(debug_chunks),
                "top_chunk_ranks_and_pages": top_chunk_ranks_and_pages,
                "error": None,
            })

        except Exception as exc:
            latency_ms = (time.monotonic() - start) * 1000
            logger.warning(
                "Ground-truth eval failed: %s — %s", question[:50], exc
            )
            per_question.append({
                "question": question,
                "category": item["category"],
                "difficulty": item["difficulty"],
                "notes": item.get("notes", ""),
                "expected_page": expected_page,
                "retrieved_pages": [],
                "retrieval_hit": False,
                "expected_answer_contains": expected_answers,
                "response_snippet": "",
                "response_hit": False,
                "expected_citations": item.get("expected_citations", []),
                "extracted_citations": [],
                "citation_hit": False,
                "latency_ms": round(latency_ms, 1),
                "retrieved_chunk_count": 0,
                "top_chunk_ranks_and_pages": [],
                "error": str(exc)[:500],
            })

        total_latency_ms += latency_ms

    # ── Aggregate scores (same shape as keyword eval) ─────────────────────

    total = len(per_question)
    retrieval_hits = sum(1 for q in per_question if q["retrieval_hit"])
    response_hits = sum(1 for q in per_question if q["response_hit"])
    citation_hits = sum(1 for q in per_question if q.get("citation_hit"))
    errors = sum(1 for q in per_question if q["error"])

    by_category: dict[str, dict[str, Any]] = {}
    for q in per_question:
        cat = q["category"]
        if cat not in by_category:
            by_category[cat] = {"questions": 0, "retrieval_hits": 0, "response_hits": 0}
        by_category[cat]["questions"] += 1
        if q["retrieval_hit"]:
            by_category[cat]["retrieval_hits"] += 1
        if q["response_hit"]:
            by_category[cat]["response_hits"] += 1

    by_difficulty: dict[str, dict[str, Any]] = {}
    for q in per_question:
        diff = q["difficulty"]
        if diff not in by_difficulty:
            by_difficulty[diff] = {"questions": 0, "retrieval_hits": 0, "response_hits": 0}
        by_difficulty[diff]["questions"] += 1
        if q["retrieval_hit"]:
            by_difficulty[diff]["retrieval_hits"] += 1
        if q["response_hit"]:
            by_difficulty[diff]["response_hits"] += 1

    return {
        "test_set": "ground_truth_v1",
        "total_questions": total,
        "retrieval_hit_rate": round(retrieval_hits / total, 3) if total else 0,
        "response_keyword_rate": round(response_hits / total, 3) if total else 0,
        "citation_hit_rate": round(citation_hits / total, 3) if total else 0,
        "avg_latency_ms": round(total_latency_ms / total, 1) if total else 0,
        "total_latency_ms": round(total_latency_ms, 1),
        "errors": errors,
        "by_category": by_category,
        "by_difficulty": by_difficulty,
        "per_question": per_question,
    }


# ── Comparison ───────────────────────────────────────────────────────────────


def compare_evaluations(eval_a: dict, eval_b: dict) -> dict[str, Any]:
    """
    Compare two evaluation results (A = before, B = after).

    Positive values mean improvement in B; negative means regression.
    """
    retrieval_delta = eval_b.get("retrieval_hit_rate", 0) - eval_a.get("retrieval_hit_rate", 0)
    response_delta = eval_b.get("response_keyword_rate", 0) - eval_a.get("response_keyword_rate", 0)
    citation_delta = eval_b.get("citation_hit_rate", 0) - eval_a.get("citation_hit_rate", 0)
    latency_delta = eval_b.get("avg_latency_ms", 0) - eval_a.get("avg_latency_ms", 0)

    # Per-category comparison
    all_cats = set(list(eval_a.get("by_category", {}).keys()) + list(eval_b.get("by_category", {}).keys()))
    by_category: dict[str, dict[str, Any]] = {}
    for cat in all_cats:
        a_cat = eval_a.get("by_category", {}).get(cat, {})
        b_cat = eval_b.get("by_category", {}).get(cat, {})
        a_q = a_cat.get("questions", 0)
        b_q = b_cat.get("questions", 0)
        a_rr = a_cat.get("retrieval_hits", 0) / a_q if a_q else 0
        b_rr = b_cat.get("retrieval_hits", 0) / b_q if b_q else 0
        by_category[cat] = {
            "retrieval_rate_before": round(a_rr, 3),
            "retrieval_rate_after": round(b_rr, 3),
            "retrieval_delta": round(b_rr - a_rr, 3),
        }

    result: dict[str, Any] = {
        "retrieval_improvement": round(retrieval_delta, 3),
        "response_improvement": round(response_delta, 3),
        "citation_improvement": round(citation_delta, 3),
        "latency_change_ms": round(latency_delta, 1),
        "by_category": by_category,
    }

    # Warn if comparing across different test sets
    a_set = eval_a.get("test_set")
    b_set = eval_b.get("test_set")
    if a_set and b_set and a_set != b_set:
        result["warning"] = (
            f"Comparing evaluations from different test sets "
            f"({a_set} vs {b_set}). Metrics are not directly comparable."
        )

    return result

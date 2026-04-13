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


def _extract_pages_from_chunks(chunk_texts: list[str]) -> list[int]:
    """Extract all unique [Page N] markers from a list of chunk texts."""
    pages: set[int] = set()
    for text in chunk_texts:
        for m in re.findall(r"\[Page\s+(\d+)\]", text):
            pages.add(int(m))
    return sorted(pages)


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

            # Retrieval scoring: exact page match
            retrieval_hit = expected_page in retrieved_pages

            # Response scoring: normalized substring match
            norm_answer = _normalize_for_match(answer)
            response_hit = any(
                _normalize_for_match(variant) in norm_answer
                for variant in expected_answers
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

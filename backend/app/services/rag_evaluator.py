"""
RAG Evaluation Framework.

Runs a set of test questions through the live RAG pipeline and measures
retrieval quality and response accuracy via keyword matching.

Usage (API):
    POST /api/admin/evaluate-rag/{client_id}

This is an internal tool — not user-facing.  Each run makes 8+ LLM calls
(~$0.05-0.10), so don't run on every deploy.
"""

from __future__ import annotations

import logging
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


# ── Main evaluation runner ───────────────────────────────────────────────────


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

    return {
        "retrieval_improvement": round(retrieval_delta, 3),
        "response_improvement": round(response_delta, 3),
        "latency_change_ms": round(latency_delta, 1),
        "by_category": by_category,
    }

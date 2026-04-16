"""
RAG Analytics endpoints for the admin dashboard.

Provides eval history, per-run detail, summary KPIs, and on-demand eval runs.

Routes:
  GET   /api/admin/rag-analytics/evaluations
  GET   /api/admin/rag-analytics/evaluations/{evaluation_id}
  GET   /api/admin/rag-analytics/summary
  POST  /api/admin/rag-analytics/run-eval
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.admin import verify_admin_access
from app.core.database import get_db
from app.models.client import Client
from app.models.rag_evaluation import RagEvaluation

router = APIRouter()


# ---------------------------------------------------------------------------
# 1. GET /evaluations — paginated list of recent eval runs
# ---------------------------------------------------------------------------


@router.get(
    "/evaluations",
    summary="List recent RAG evaluation runs",
)
async def list_eval_runs(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    client_id: Optional[UUID] = Query(default=None),
    _admin: None = Depends(verify_admin_access),
    db: Session = Depends(get_db),
) -> list[dict]:
    query = (
        db.query(RagEvaluation, Client.name)
        .outerjoin(Client, RagEvaluation.client_id == Client.id)
        .order_by(RagEvaluation.created_at.desc())
    )
    if client_id:
        query = query.filter(RagEvaluation.client_id == client_id)

    rows = query.offset(offset).limit(limit).all()

    return [
        {
            "evaluation_id": str(e.id),
            "client_id": str(e.client_id),
            "client_name": client_name,
            "created_at": e.created_at.isoformat(),
            "retrieval_hit_rate": e.results.get("retrieval_hit_rate"),
            "response_keyword_rate": e.results.get("response_keyword_rate"),
            "citation_hit_rate": e.results.get("citation_hit_rate"),
            "avg_latency_ms": e.results.get("avg_latency_ms"),
            "total_questions": e.results.get("total_questions"),
            "commit_sha": e.results.get("commit_sha"),
        }
        for e, client_name in rows
    ]


# ---------------------------------------------------------------------------
# 2. GET /evaluations/{evaluation_id} — full per-question detail
# ---------------------------------------------------------------------------


@router.get(
    "/evaluations/{evaluation_id}",
    summary="Get full detail for a single evaluation run",
)
async def get_eval_detail(
    evaluation_id: UUID,
    _admin: None = Depends(verify_admin_access),
    db: Session = Depends(get_db),
) -> dict:
    evaluation = (
        db.query(RagEvaluation)
        .filter(RagEvaluation.id == evaluation_id)
        .first()
    )
    if not evaluation:
        raise HTTPException(status_code=404, detail="Evaluation not found")

    results = evaluation.results or {}

    # Normalize: ground-truth evals use "per_question", keyword evals use "details"
    per_question_raw = results.get("per_question") or results.get("details") or []

    per_question = [
        {
            "question": q.get("question"),
            "expected": (
                q.get("expected_answer_contains")
                or q.get("expected_keywords")
            ),
            "response_snippet": (
                q.get("response_snippet")
                or q.get("answer_preview", "")
            ),
            "retrieval_hit": q.get("retrieval_hit", False),
            "response_hit": q.get("response_hit", False),
            "latency_ms": q.get("latency_ms"),
        }
        for q in per_question_raw
    ]

    return {
        "evaluation_id": str(evaluation.id),
        "client_id": str(evaluation.client_id),
        "created_at": evaluation.created_at.isoformat(),
        "summary": {
            "retrieval_hit_rate": results.get("retrieval_hit_rate"),
            "response_keyword_rate": results.get("response_keyword_rate"),
            "citation_hit_rate": results.get("citation_hit_rate"),
            "avg_latency_ms": results.get("avg_latency_ms"),
            "total_questions": results.get("total_questions"),
            "errors": results.get("errors", 0),
            "test_set": results.get("test_set"),
        },
        "per_question": per_question,
    }


# ---------------------------------------------------------------------------
# 3. GET /summary — aggregate KPIs and trend data
# ---------------------------------------------------------------------------


@router.get(
    "/summary",
    summary="Aggregate eval KPIs and trend data for charts",
)
async def eval_summary(
    days: int = Query(default=30, ge=1, le=365),
    _admin: None = Depends(verify_admin_access),
    db: Session = Depends(get_db),
) -> dict:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    evals = (
        db.query(RagEvaluation)
        .filter(RagEvaluation.created_at >= cutoff)
        .order_by(RagEvaluation.created_at.asc())
        .all()
    )

    if not evals:
        return {
            "total_runs": 0,
            "latest_run": None,
            "avg_retrieval_hit_rate": None,
            "avg_response_keyword_rate": None,
            "avg_latency_ms": None,
            "trend": [],
        }

    retrieval_rates = [
        e.results.get("retrieval_hit_rate", 0) for e in evals
    ]
    response_rates = [
        e.results.get("response_keyword_rate", 0) for e in evals
    ]
    citation_rates = [
        e.results.get("citation_hit_rate")
        for e in evals
        if e.results.get("citation_hit_rate") is not None
    ]
    latencies = [
        e.results.get("avg_latency_ms", 0) for e in evals
    ]

    latest = evals[-1]

    trend = [
        {
            "date": e.created_at.isoformat(),
            "evaluation_id": str(e.id),
            "retrieval_hit_rate": e.results.get("retrieval_hit_rate"),
            "response_keyword_rate": e.results.get("response_keyword_rate"),
            "avg_latency_ms": e.results.get("avg_latency_ms"),
        }
        for e in evals
    ]

    return {
        "total_runs": len(evals),
        "latest_run": {
            "evaluation_id": str(latest.id),
            "client_id": str(latest.client_id),
            "created_at": latest.created_at.isoformat(),
            "retrieval_hit_rate": latest.results.get("retrieval_hit_rate"),
            "response_keyword_rate": latest.results.get("response_keyword_rate"),
            "citation_hit_rate": latest.results.get("citation_hit_rate"),
            "avg_latency_ms": latest.results.get("avg_latency_ms"),
        },
        "avg_retrieval_hit_rate": round(
            sum(retrieval_rates) / len(retrieval_rates), 3
        ),
        "avg_response_keyword_rate": round(
            sum(response_rates) / len(response_rates), 3
        ),
        "avg_citation_hit_rate": (
            round(sum(citation_rates) / len(citation_rates), 3)
            if citation_rates
            else None
        ),
        "avg_latency_ms": round(sum(latencies) / len(latencies), 1),
        "trend": trend,
    }


# ---------------------------------------------------------------------------
# 4. POST /run-eval — trigger a ground-truth eval run
# ---------------------------------------------------------------------------


class RunEvalRequest(BaseModel):
    client_id: str


@router.post(
    "/run-eval",
    summary="Trigger a ground-truth evaluation run",
)
async def run_eval(
    body: RunEvalRequest,
    _admin: None = Depends(verify_admin_access),
    db: Session = Depends(get_db),
) -> dict:
    from app.services.rag_eval_fixtures import get_ground_truth
    from app.services.rag_evaluator import run_ground_truth_evaluation

    client_id = UUID(body.client_id)

    if get_ground_truth(body.client_id) is None:
        raise HTTPException(
            status_code=404,
            detail=f"No ground-truth test set defined for client {body.client_id}",
        )

    results = await run_ground_truth_evaluation(
        client_id=body.client_id,
        db=db,
    )

    # Persist
    evaluation = RagEvaluation(
        client_id=client_id,
        user_id="eval_ground_truth",
        results=results,
    )
    db.add(evaluation)
    db.commit()
    db.refresh(evaluation)

    # Return same shape as GET /evaluations/{id}
    per_question_raw = results.get("per_question", [])
    per_question = [
        {
            "question": q.get("question"),
            "expected": q.get("expected_answer_contains"),
            "response_snippet": q.get("response_snippet", ""),
            "retrieval_hit": q.get("retrieval_hit", False),
            "response_hit": q.get("response_hit", False),
            "latency_ms": q.get("latency_ms"),
        }
        for q in per_question_raw
    ]

    return {
        "evaluation_id": str(evaluation.id),
        "client_id": str(evaluation.client_id),
        "created_at": evaluation.created_at.isoformat(),
        "summary": {
            "retrieval_hit_rate": results.get("retrieval_hit_rate"),
            "response_keyword_rate": results.get("response_keyword_rate"),
            "citation_hit_rate": results.get("citation_hit_rate"),
            "avg_latency_ms": results.get("avg_latency_ms"),
            "total_questions": results.get("total_questions"),
            "errors": results.get("errors", 0),
            "test_set": results.get("test_set"),
        },
        "per_question": per_question,
    }

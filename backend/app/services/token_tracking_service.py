"""
Token usage tracking service.

Logs every AI API call with model, token counts, and estimated cost.
Provides aggregated usage summaries for cost monitoring and billing.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.token_usage import TokenUsage

logger = logging.getLogger(__name__)

# Cost per token in USD (as of March 2026)
COST_PER_TOKEN: dict[str, dict[str, float]] = {
    "gpt-4o-mini": {"input": 0.00000015, "output": 0.0000006},
    "gpt-4o": {"input": 0.0000025, "output": 0.00001},
    "claude-sonnet-4-20250514": {"input": 0.000003, "output": 0.000015},
    "claude-opus-4-20250514": {"input": 0.000015, "output": 0.000075},
}

# Fallback rate for unknown models
_FALLBACK_MODEL = "gpt-4o-mini"


def log_token_usage(
    db: Session,
    *,
    user_id: str,
    client_id: Optional[UUID] = None,
    org_id: Optional[UUID] = None,
    query_type: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    endpoint: Optional[str] = None,
    is_eval: bool = False,
) -> None:
    """
    Calculate cost and insert a token_usage row.

    Never raises — all errors are logged and swallowed.
    """
    try:
        rates = COST_PER_TOKEN.get(model)
        if rates is None:
            logger.warning(
                "Unknown model %r for token pricing — using %s rates",
                model, _FALLBACK_MODEL,
            )
            rates = COST_PER_TOKEN[_FALLBACK_MODEL]

        total_tokens = prompt_tokens + completion_tokens
        cost = (prompt_tokens * rates["input"]) + (completion_tokens * rates["output"])

        row = TokenUsage(
            user_id=user_id,
            client_id=client_id,
            org_id=org_id,
            query_type=query_type,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            estimated_cost_usd=round(cost, 6),
            endpoint=endpoint,
            is_eval=is_eval,
        )
        db.add(row)
        db.commit()
    except Exception:
        logger.error("Failed to log token usage", exc_info=True)
        try:
            db.rollback()
        except Exception:
            pass


def get_usage_summary(
    db: Session,
    user_id: str,
    days: int = 30,
) -> dict[str, Any]:
    """
    Return aggregated usage stats for a user over the last N days.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)

    base = db.query(TokenUsage).filter(
        TokenUsage.user_id == user_id,
        TokenUsage.created_at >= since,
    )

    # Totals
    totals = base.with_entities(
        func.count(TokenUsage.id).label("total_queries"),
        func.coalesce(func.sum(TokenUsage.total_tokens), 0).label("total_tokens"),
        func.coalesce(func.sum(TokenUsage.estimated_cost_usd), 0).label("total_cost"),
    ).first()

    # By model
    by_model = (
        base.with_entities(
            TokenUsage.model,
            func.count(TokenUsage.id).label("queries"),
            func.coalesce(func.sum(TokenUsage.total_tokens), 0).label("tokens"),
            func.coalesce(func.sum(TokenUsage.estimated_cost_usd), 0).label("cost"),
        )
        .group_by(TokenUsage.model)
        .all()
    )

    # By query type
    by_type = (
        base.with_entities(
            TokenUsage.query_type,
            func.count(TokenUsage.id).label("queries"),
            func.coalesce(func.sum(TokenUsage.total_tokens), 0).label("tokens"),
            func.coalesce(func.sum(TokenUsage.estimated_cost_usd), 0).label("cost"),
        )
        .group_by(TokenUsage.query_type)
        .all()
    )

    return {
        "days": days,
        "total_queries": totals.total_queries if totals else 0,
        "total_tokens": int(totals.total_tokens) if totals else 0,
        "total_cost": float(totals.total_cost) if totals else 0.0,
        "breakdown_by_model": [
            {"model": r.model, "queries": r.queries, "tokens": int(r.tokens), "cost": float(r.cost)}
            for r in by_model
        ],
        "breakdown_by_query_type": [
            {"query_type": r.query_type, "queries": r.queries, "tokens": int(r.tokens), "cost": float(r.cost)}
            for r in by_type
        ],
    }


def get_usage_by_client(
    db: Session,
    user_id: str,
    client_id: UUID,
    days: int = 30,
) -> dict[str, Any]:
    """
    Return aggregated usage stats for a specific client over the last N days.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)

    base = db.query(TokenUsage).filter(
        TokenUsage.user_id == user_id,
        TokenUsage.client_id == client_id,
        TokenUsage.created_at >= since,
    )

    totals = base.with_entities(
        func.count(TokenUsage.id).label("total_queries"),
        func.coalesce(func.sum(TokenUsage.total_tokens), 0).label("total_tokens"),
        func.coalesce(func.sum(TokenUsage.estimated_cost_usd), 0).label("total_cost"),
    ).first()

    by_model = (
        base.with_entities(
            TokenUsage.model,
            func.count(TokenUsage.id).label("queries"),
            func.coalesce(func.sum(TokenUsage.total_tokens), 0).label("tokens"),
            func.coalesce(func.sum(TokenUsage.estimated_cost_usd), 0).label("cost"),
        )
        .group_by(TokenUsage.model)
        .all()
    )

    by_type = (
        base.with_entities(
            TokenUsage.query_type,
            func.count(TokenUsage.id).label("queries"),
            func.coalesce(func.sum(TokenUsage.total_tokens), 0).label("tokens"),
            func.coalesce(func.sum(TokenUsage.estimated_cost_usd), 0).label("cost"),
        )
        .group_by(TokenUsage.query_type)
        .all()
    )

    return {
        "days": days,
        "client_id": str(client_id),
        "total_queries": totals.total_queries if totals else 0,
        "total_tokens": int(totals.total_tokens) if totals else 0,
        "total_cost": float(totals.total_cost) if totals else 0.0,
        "breakdown_by_model": [
            {"model": r.model, "queries": r.queries, "tokens": int(r.tokens), "cost": float(r.cost)}
            for r in by_model
        ],
        "breakdown_by_query_type": [
            {"query_type": r.query_type, "queries": r.queries, "tokens": int(r.tokens), "cost": float(r.cost)}
            for r in by_type
        ],
    }

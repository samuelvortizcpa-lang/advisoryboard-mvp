"""
Subscription tier management and strategic query quota enforcement.

Tiers:
  - free:          50 queries/month, 3 clients, 10 documents, no Opus
  - starter:       factual only, no Claude access
  - professional:  100 strategic queries/month, 10 opus queries/month
  - firm:          500 strategic queries/month, 50 opus queries/month
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, update
from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.document import Document
from app.models.token_usage import TokenUsage
from app.models.user_subscription import UserSubscription

logger = logging.getLogger(__name__)

TIER_DEFAULTS: dict[str, dict] = {
    "free": {
        "strategic_queries_limit": 50,
        "opus_queries_limit": 0,
        "models_allowed": ["gpt-4o-mini"],
        "max_clients": 3,
        "max_documents": 10,
    },
    "starter": {
        "strategic_queries_limit": 0,
        "opus_queries_limit": 0,
        "models_allowed": ["gpt-4o-mini"],
        "max_clients": 25,
        "max_documents": 500,
    },
    "professional": {
        "strategic_queries_limit": 100,
        "opus_queries_limit": 10,
        "models_allowed": ["gpt-4o-mini", "claude-sonnet-4-20250514", "claude-opus-4-20250514"],
        "max_clients": 100,
        "max_documents": 5000,
    },
    "firm": {
        "strategic_queries_limit": 500,
        "opus_queries_limit": 50,
        "models_allowed": ["gpt-4o-mini", "claude-sonnet-4-20250514", "claude-opus-4-20250514"],
        "max_clients": None,
        "max_documents": None,
    },
}

# Default tier for new users
_DEFAULT_TIER = "free"


def get_or_create_subscription(db: Session, user_id: str) -> UserSubscription:
    """
    Return the user's subscription, creating one if it doesn't exist.

    Resets the billing period if it has expired.
    """
    sub = (
        db.query(UserSubscription)
        .filter(UserSubscription.user_id == user_id)
        .first()
    )

    now = datetime.now(timezone.utc)

    if sub is None:
        defaults = TIER_DEFAULTS[_DEFAULT_TIER]
        sub = UserSubscription(
            user_id=user_id,
            tier=_DEFAULT_TIER,
            strategic_queries_limit=defaults["strategic_queries_limit"],
            strategic_queries_used=0,
            billing_period_start=now,
            billing_period_end=now + timedelta(days=30),
        )
        db.add(sub)
        db.commit()
        db.refresh(sub)
        logger.info("Created %s subscription for user %s", _DEFAULT_TIER, user_id)
        return sub

    # Reset billing period if expired
    if sub.billing_period_end and now >= sub.billing_period_end:
        sub.strategic_queries_used = 0
        sub.billing_period_start = now
        sub.billing_period_end = now + timedelta(days=30)
        sub.updated_at = now
        db.commit()
        db.refresh(sub)
        logger.info("Reset billing period for user %s", user_id)

    return sub


def check_quota(db: Session, user_id: str) -> dict:
    """
    Check whether the user can make a strategic query.

    Returns {allowed, tier, used, limit, remaining}.
    """
    sub = get_or_create_subscription(db, user_id)
    remaining = max(0, sub.strategic_queries_limit - sub.strategic_queries_used)
    allowed = sub.strategic_queries_limit > 0 and sub.strategic_queries_used < sub.strategic_queries_limit

    return {
        "allowed": allowed,
        "tier": sub.tier,
        "used": sub.strategic_queries_used,
        "limit": sub.strategic_queries_limit,
        "remaining": remaining,
    }


def check_opus_quota(db: Session, user_id: str) -> dict:
    """
    Check whether the user can make an Opus query.

    Counts Opus usage from the token_usage table (no new DB columns needed).
    Returns {allowed, tier, used, limit, remaining}.
    """
    sub = get_or_create_subscription(db, user_id)
    tier_config = TIER_DEFAULTS.get(sub.tier, TIER_DEFAULTS["free"])
    opus_limit = tier_config["opus_queries_limit"]

    if opus_limit == 0:
        return {
            "allowed": False,
            "tier": sub.tier,
            "used": 0,
            "limit": 0,
            "remaining": 0,
        }

    # Count Opus queries in the current billing period from token_usage
    opus_used = (
        db.query(func.count(TokenUsage.id))
        .filter(
            TokenUsage.user_id == user_id,
            TokenUsage.model == "claude-opus-4-20250514",
            TokenUsage.created_at >= sub.billing_period_start,
        )
        .scalar()
    ) or 0

    remaining = max(0, opus_limit - opus_used)
    return {
        "allowed": opus_used < opus_limit,
        "tier": sub.tier,
        "used": opus_used,
        "limit": opus_limit,
        "remaining": remaining,
    }


def check_client_limit(db: Session, user_id: str, owner_id) -> dict:
    """
    Check whether the user can add another client.

    Args:
        user_id: Clerk ID (for subscription lookup)
        owner_id: User UUID (for client ownership count)

    Returns {allowed, current, limit}.
    """
    sub = get_or_create_subscription(db, user_id)
    tier_config = TIER_DEFAULTS.get(sub.tier, TIER_DEFAULTS["free"])
    limit = tier_config["max_clients"]

    if limit is None:
        return {"allowed": True, "current": 0, "limit": None}

    current = (
        db.query(func.count(Client.id))
        .filter(Client.owner_id == owner_id)
        .scalar()
    ) or 0

    return {"allowed": current < limit, "current": current, "limit": limit}


def check_document_limit(db: Session, user_id: str, owner_id) -> dict:
    """
    Check whether the user can upload another document.

    Args:
        user_id: Clerk ID (for subscription lookup)
        owner_id: User UUID (for document ownership count via clients)

    Returns {allowed, current, limit}.
    """
    sub = get_or_create_subscription(db, user_id)
    tier_config = TIER_DEFAULTS.get(sub.tier, TIER_DEFAULTS["free"])
    limit = tier_config["max_documents"]

    if limit is None:
        return {"allowed": True, "current": 0, "limit": None}

    # Count documents across all of the user's clients
    current = (
        db.query(func.count(Document.id))
        .join(Client, Document.client_id == Client.id)
        .filter(Client.owner_id == owner_id)
        .scalar()
    ) or 0

    return {"allowed": current < limit, "current": current, "limit": limit}


def increment_usage(db: Session, user_id: str, query_type: str) -> None:
    """Increment strategic_queries_used if this was a strategic query."""
    if query_type != "strategic":
        return

    try:
        get_or_create_subscription(db, user_id)
        db.execute(
            update(UserSubscription)
            .where(UserSubscription.user_id == user_id)
            .values(
                strategic_queries_used=UserSubscription.strategic_queries_used + 1,
                updated_at=datetime.now(timezone.utc),
            )
        )
        db.commit()
        db.expire_all()
    except Exception:
        logger.error("Failed to increment usage for user %s", user_id, exc_info=True)
        try:
            db.rollback()
        except Exception:
            pass

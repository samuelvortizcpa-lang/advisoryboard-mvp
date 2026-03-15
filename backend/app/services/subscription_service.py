"""
Subscription tier management and strategic query quota enforcement.

Tiers:
  - starter:      factual only, no Claude access
  - professional:  100 strategic queries/month
  - firm:          500 strategic queries/month
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.user_subscription import UserSubscription

logger = logging.getLogger(__name__)

TIER_DEFAULTS: dict[str, dict] = {
    "starter": {
        "strategic_queries_limit": 0,
        "models_allowed": ["gpt-4o-mini"],
    },
    "professional": {
        "strategic_queries_limit": 100,
        "models_allowed": ["gpt-4o-mini", "claude-sonnet-4-20250514"],
    },
    "firm": {
        "strategic_queries_limit": 500,
        "models_allowed": ["gpt-4o-mini", "claude-sonnet-4-20250514", "claude-opus-4-20250514"],
    },
}

# Default tier for new users (professional during testing, switch to starter at launch)
_DEFAULT_TIER = "professional"


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


def increment_usage(db: Session, user_id: str, query_type: str) -> None:
    """Increment strategic_queries_used if this was a strategic query."""
    if query_type != "strategic":
        return

    try:
        sub = get_or_create_subscription(db, user_id)
        sub.strategic_queries_used += 1
        sub.updated_at = datetime.now(timezone.utc)
        db.commit()
    except Exception:
        logger.error("Failed to increment usage for user %s", user_id, exc_info=True)
        try:
            db.rollback()
        except Exception:
            pass

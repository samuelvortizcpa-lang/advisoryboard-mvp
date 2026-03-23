"""
Subscription tier management and strategic query quota enforcement.

Tiers:
  - free:          50 queries/month, 5 clients, unlimited documents, no Opus
  - starter:       factual only, no Claude access
  - professional:  100 strategic queries/month, 10 opus queries/month
  - firm:          500 strategic queries/month, 50 opus queries/month
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

import sentry_sdk

from sqlalchemy import func, or_, update
from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.document import Document
from app.models.organization import Organization
from app.models.organization_member import OrganizationMember
from app.models.token_usage import TokenUsage
from app.models.user_subscription import UserSubscription

from app.services.notification_service import notify

logger = logging.getLogger(__name__)

TIER_DEFAULTS: dict[str, dict] = {
    "free": {
        "strategic_queries_limit": 50,
        "opus_queries_limit": 0,
        "models_allowed": ["gpt-4o-mini"],
        "max_clients": 5,
        "max_documents": None,
        "max_members": 1,
        "base_seats": 1,
    },
    "starter": {
        "strategic_queries_limit": 0,
        "opus_queries_limit": 0,
        "models_allowed": ["gpt-4o-mini"],
        "max_clients": 25,
        "max_documents": None,
        "max_members": 1,
        "base_seats": 1,
    },
    "professional": {
        "strategic_queries_limit": 100,
        "opus_queries_limit": 10,
        "models_allowed": ["gpt-4o-mini", "claude-sonnet-4-20250514", "claude-opus-4-20250514"],
        "max_clients": 100,
        "max_documents": None,
        "max_members": 3,
        "base_seats": 1,
    },
    "firm": {
        "strategic_queries_limit": 500,
        "opus_queries_limit": 50,
        "models_allowed": ["gpt-4o-mini", "claude-sonnet-4-20250514", "claude-opus-4-20250514"],
        "max_clients": None,
        "max_documents": None,
        "max_members": 15,
        "base_seats": 3,
        "addon_seat_price_monthly": 79,
        "addon_seat_price_annual": 63,
    },
}

# Default tier for new users
_DEFAULT_TIER = "free"


def get_or_create_subscription(
    db: Session, user_id: str, *, org_id: UUID | None = None,
) -> UserSubscription:
    """
    Return the subscription, creating one if it doesn't exist.

    When *org_id* is provided the lookup is by org_id first (shared org
    subscription).  Falls back to user_id-based lookup for backward compat.
    The user_id is always stored as the billing contact.

    Resets the billing period if it has expired.
    """
    sub: UserSubscription | None = None

    if org_id is not None:
        sub = (
            db.query(UserSubscription)
            .filter(UserSubscription.org_id == org_id)
            .first()
        )

    if sub is None:
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
            org_id=org_id,
            tier=_DEFAULT_TIER,
            strategic_queries_limit=defaults["strategic_queries_limit"],
            strategic_queries_used=0,
            billing_period_start=now,
            billing_period_end=now + timedelta(days=30),
        )
        db.add(sub)
        db.commit()
        db.refresh(sub)
        logger.info("Created %s subscription for user %s (org=%s)", _DEFAULT_TIER, user_id, org_id)
        notify("new_signup", "New user signed up", {"email": user_id, "tier": "free"})
        return sub

    # Backfill org_id on existing subscription if not yet set
    if org_id is not None and sub.org_id is None:
        sub.org_id = org_id
        sub.updated_at = now
        db.commit()
        db.refresh(sub)

    # Reset billing period if expired
    if sub.billing_period_end and now >= sub.billing_period_end:
        sub.strategic_queries_used = 0
        sub.billing_period_start = now
        sub.billing_period_end = now + timedelta(days=30)
        sub.updated_at = now
        db.commit()
        db.refresh(sub)
        logger.info("Reset billing period for user %s (org=%s)", user_id, sub.org_id)

    return sub


def update_org_seat_limit(org_id: UUID, new_tier: str, db: Session) -> None:
    """
    Sync an organization's max_members with the tier's seat limit.

    Called after subscription tier changes.  If the org currently has more
    members than the new limit, existing members are kept — the limit only
    prevents *adding* new members (enforced by organization_service.add_member).
    """
    tier_config = TIER_DEFAULTS.get(new_tier, TIER_DEFAULTS["free"])
    new_max = tier_config["max_members"]

    org = db.query(Organization).filter(Organization.id == org_id).first()
    if org is None:
        logger.warning("update_org_seat_limit: org %s not found", org_id)
        return

    org.max_members = new_max
    db.commit()
    logger.info("Updated org %s max_members to %d (tier=%s)", org_id, new_max, new_tier)


def check_quota(db: Session, user_id: str, *, org_id: UUID | None = None) -> dict:
    """
    Check whether the user/org can make a strategic query.

    When org_id is provided, all org members share the same quota pool.
    Returns {allowed, tier, used, limit, remaining}.
    """
    sub = get_or_create_subscription(db, user_id, org_id=org_id)
    remaining = max(0, sub.strategic_queries_limit - sub.strategic_queries_used)
    allowed = sub.strategic_queries_limit > 0 and sub.strategic_queries_used < sub.strategic_queries_limit

    return {
        "allowed": allowed,
        "tier": sub.tier,
        "used": sub.strategic_queries_used,
        "limit": sub.strategic_queries_limit,
        "remaining": remaining,
    }


def check_opus_quota(db: Session, user_id: str, *, org_id: UUID | None = None) -> dict:
    """
    Check whether the user/org can make an Opus query.

    Counts Opus usage from the token_usage table (no new DB columns needed).
    When org_id is provided, counts across the whole org.
    Returns {allowed, tier, used, limit, remaining}.
    """
    sub = get_or_create_subscription(db, user_id, org_id=org_id)
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
    opus_query = db.query(func.count(TokenUsage.id)).filter(
        TokenUsage.model == "claude-opus-4-20250514",
        TokenUsage.created_at >= sub.billing_period_start,
    )
    if org_id is not None:
        opus_query = opus_query.filter(
            or_(TokenUsage.org_id == org_id, TokenUsage.user_id == user_id)
        )
    else:
        opus_query = opus_query.filter(TokenUsage.user_id == user_id)

    opus_used = opus_query.scalar() or 0

    remaining = max(0, opus_limit - opus_used)
    return {
        "allowed": opus_used < opus_limit,
        "tier": sub.tier,
        "used": opus_used,
        "limit": opus_limit,
        "remaining": remaining,
    }


def check_client_limit(db: Session, user_id: str, owner_id=None, org_id=None) -> dict:
    """
    Check whether the user/org can add another client.

    Args:
        user_id: Clerk ID (for subscription lookup)
        owner_id: User UUID — legacy path, counts by owner_id
        org_id: Organization UUID — new path, counts by org_id

    Returns {allowed, current, limit}.
    """
    sub = get_or_create_subscription(db, user_id, org_id=org_id)
    tier_config = TIER_DEFAULTS.get(sub.tier, TIER_DEFAULTS["free"])
    limit = tier_config["max_clients"]

    if limit is None:
        return {"allowed": True, "current": 0, "limit": None}

    if org_id is not None:
        current = (
            db.query(func.count(Client.id))
            .filter(Client.org_id == org_id)
            .scalar()
        ) or 0
    else:
        # Legacy fallback
        current = (
            db.query(func.count(Client.id))
            .filter(Client.owner_id == owner_id)
            .scalar()
        ) or 0

    result = {"allowed": current < limit, "current": current, "limit": limit}
    if not result["allowed"]:
        notify("limit_hit", "User hit client limit", {"email": user_id, "current": current, "limit": limit})
    return result


def check_document_limit(db: Session, user_id: str, owner_id=None, org_id=None) -> dict:
    """
    Check whether the user/org can upload another document.

    Args:
        user_id: Clerk ID (for subscription lookup)
        owner_id: User UUID — legacy path, counts via clients.owner_id
        org_id: Organization UUID — new path, counts via clients.org_id

    Returns {allowed, current, limit}.
    """
    sub = get_or_create_subscription(db, user_id, org_id=org_id)
    tier_config = TIER_DEFAULTS.get(sub.tier, TIER_DEFAULTS["free"])
    limit = tier_config["max_documents"]

    if limit is None:
        return {"allowed": True, "current": 0, "limit": None}

    if org_id is not None:
        current = (
            db.query(func.count(Document.id))
            .join(Client, Document.client_id == Client.id)
            .filter(Client.org_id == org_id)
            .scalar()
        ) or 0
    else:
        # Legacy fallback
        current = (
            db.query(func.count(Document.id))
            .join(Client, Document.client_id == Client.id)
            .filter(Client.owner_id == owner_id)
            .scalar()
        ) or 0

    return {"allowed": current < limit, "current": current, "limit": limit}


def increment_usage(db: Session, user_id: str, query_type: str, *, org_id: UUID | None = None) -> None:
    """Increment strategic_queries_used if this was a strategic query."""
    if query_type != "strategic":
        return

    try:
        sub = get_or_create_subscription(db, user_id, org_id=org_id)

        # Update by the subscription's primary key to be precise
        db.execute(
            update(UserSubscription)
            .where(UserSubscription.id == sub.id)
            .values(
                strategic_queries_used=UserSubscription.strategic_queries_used + 1,
                updated_at=datetime.now(timezone.utc),
            )
        )
        db.commit()
        db.expire_all()
    except Exception as exc:
        logger.error("Failed to increment usage for user %s", user_id, exc_info=True)
        sentry_sdk.capture_exception(exc)
        try:
            db.rollback()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Seat management (hybrid Firm pricing)
# ---------------------------------------------------------------------------


def get_seat_info(org_id: UUID, db: Session) -> dict:
    """
    Return seat allocation details for an organization.

    For the Firm tier, base_seats=3 are included in the $349/mo base price.
    Additional seats are tracked in user_subscriptions.addon_seats and billed
    at $79/mo each.  Starter/Professional have base_seats=1 with no add-on
    seat mechanism.

    Returns::

        {
            "included": int,        # seats included in tier base price
            "addon_purchased": int,  # extra seats purchased (addon_seats column)
            "total_allowed": int,    # included + addon_purchased
            "current_used": int,     # active organization_members count
            "can_add": bool,         # whether another member can be invited
        }
    """
    # Find the org's subscription (via any member — the sub is per-org)
    sub = (
        db.query(UserSubscription)
        .filter(UserSubscription.org_id == org_id)
        .first()
    )

    if sub is None:
        # No subscription → fall back to free tier defaults
        tier_config = TIER_DEFAULTS["free"]
        addon_purchased = 0
    else:
        tier_config = TIER_DEFAULTS.get(sub.tier, TIER_DEFAULTS["free"])
        addon_purchased = getattr(sub, "addon_seats", 0) or 0

    included = tier_config.get("base_seats", 1)
    total_allowed = included + addon_purchased

    current_used = (
        db.query(func.count(OrganizationMember.id))
        .filter(
            OrganizationMember.org_id == org_id,
            OrganizationMember.is_active == True,  # noqa: E712
        )
        .scalar()
    ) or 0

    return {
        "included": included,
        "addon_purchased": addon_purchased,
        "total_allowed": total_allowed,
        "current_used": current_used,
        "can_add": current_used < total_allowed,
    }


def check_seat_limit(org_id: UUID, db: Session) -> dict:
    """
    Check whether another member can be added to the organization.

    Used by the org member invite endpoint to block invites when at capacity.

    Returns::

        {
            "allowed": bool,
            "current": int,
            "limit": int,
            "message": str,
        }
    """
    info = get_seat_info(org_id, db)

    if info["can_add"]:
        return {
            "allowed": True,
            "current": info["current_used"],
            "limit": info["total_allowed"],
            "message": "Seat available.",
        }

    # At capacity — build a helpful message
    if info["addon_purchased"] > 0 or info["included"] > 1:
        msg = (
            f"All {info['total_allowed']} seats are in use "
            f"({info['included']} included + {info['addon_purchased']} add-on). "
            f"Purchase additional seats to invite more members."
        )
    else:
        msg = (
            f"Your plan includes {info['included']} seat. "
            f"Upgrade your plan to invite team members."
        )

    return {
        "allowed": False,
        "current": info["current_used"],
        "limit": info["total_allowed"],
        "message": msg,
    }

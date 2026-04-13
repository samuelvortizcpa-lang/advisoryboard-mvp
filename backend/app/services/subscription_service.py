"""
Subscription tier management and query quota enforcement.

Tiers:
  - free:          50 total queries/month, 10 Sonnet, 0 Opus, 5 clients
  - starter:       500 total queries/month, 50 Sonnet, 25 Opus, 25 clients
  - professional:  500 total queries/month, 100 Sonnet, 50 Opus, 100 clients
  - firm:          1000 total queries/month, 500 Sonnet, 100 Opus, unlimited clients
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
        "max_clients": 5,
        "max_documents": None,
        "total_queries_limit": 50,
        "sonnet_queries_limit": 10,
        "opus_queries_limit": 0,
        "strategic_queries_limit": 50,  # Legacy — kept for backward compat
        "models_allowed": ["gpt-4o-mini"],
        "max_members": 1,
        "base_seats": 1,
        "extension_captures_per_day": 10,
        "extension_auto_match": False,
        "extension_quick_query": False,
        "extension_parsers": False,
        "extension_monitoring": False,
    },
    "starter": {
        "max_clients": 25,
        "max_documents": None,
        "total_queries_limit": 500,
        "sonnet_queries_limit": 50,
        "opus_queries_limit": 25,
        "strategic_queries_limit": 500,
        "models_allowed": ["gpt-4o-mini", "claude-sonnet-4-20250514", "claude-opus-4-20250514"],
        "max_members": 1,
        "base_seats": 1,
        "extension_captures_per_day": 50,
        "extension_auto_match": True,
        "extension_quick_query": True,
        "extension_parsers": True,
        "extension_monitoring": True,
    },
    "professional": {
        "max_clients": 100,
        "max_documents": None,
        "total_queries_limit": 500,
        "sonnet_queries_limit": 100,
        "opus_queries_limit": 50,
        "strategic_queries_limit": 500,
        "models_allowed": ["gpt-4o-mini", "claude-sonnet-4-20250514", "claude-opus-4-20250514"],
        "max_members": 3,
        "base_seats": 1,
        "extension_captures_per_day": 200,
        "extension_auto_match": True,
        "extension_quick_query": True,
        "extension_parsers": True,
        "extension_monitoring": True,
    },
    "firm": {
        "max_clients": None,
        "max_documents": None,
        "total_queries_limit": 1000,
        "sonnet_queries_limit": 500,
        "opus_queries_limit": 100,
        "strategic_queries_limit": 1000,
        "models_allowed": ["gpt-4o-mini", "claude-sonnet-4-20250514", "claude-opus-4-20250514"],
        "max_members": 15,
        "base_seats": 3,
        "addon_seat_price_monthly": 79,
        "addon_seat_price_annual": 63,
        "extension_captures_per_day": None,
        "extension_auto_match": True,
        "extension_quick_query": True,
        "extension_parsers": True,
        "extension_monitoring": True,
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
            sonnet_queries_limit=defaults["sonnet_queries_limit"],
            sonnet_queries_used=0,
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
        sub.sonnet_queries_used = 0
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


# ---------------------------------------------------------------------------
# Query quota checks — token_usage-based counting
# ---------------------------------------------------------------------------


_EVAL_BYPASS = {"allowed": True, "used": 0, "limit": 999999, "remaining": 999999}


def _count_chat_usage(
    db: Session,
    sub: UserSubscription,
    user_id: str,
    org_id: UUID | None,
    *,
    model_filter: str | None = None,
) -> int:
    """
    Count chat query rows in token_usage for the current billing period.

    Excludes eval-framework traffic (is_eval=True) so that admin eval runs
    don't consume the user's quota.

    Args:
        model_filter: If provided, only count rows where model ILIKE this pattern
                      (e.g. '%sonnet%', '%opus%'). If None, count all chat rows.
    """
    q = db.query(func.count(TokenUsage.id)).filter(
        TokenUsage.endpoint == "chat",
        TokenUsage.created_at >= sub.billing_period_start,
        TokenUsage.is_eval == False,  # noqa: E712
    )
    if sub.billing_period_end:
        q = q.filter(TokenUsage.created_at < sub.billing_period_end)

    if model_filter:
        q = q.filter(TokenUsage.model.ilike(model_filter))

    if org_id is not None:
        q = q.filter(
            or_(TokenUsage.org_id == org_id, TokenUsage.user_id == user_id)
        )
    else:
        q = q.filter(TokenUsage.user_id == user_id)

    return q.scalar() or 0


def check_total_query_quota(
    db: Session, user_id: str, *, org_id: UUID | None = None, is_admin_eval: bool = False,
) -> dict:
    """
    Check whether the user/org can make any AI chat query this period.

    Returns {allowed, used, limit, remaining}.
    """
    if is_admin_eval:
        return _EVAL_BYPASS
    sub = get_or_create_subscription(db, user_id, org_id=org_id)
    tier_config = TIER_DEFAULTS.get(sub.tier, TIER_DEFAULTS["free"])
    limit = tier_config["total_queries_limit"]

    used = _count_chat_usage(db, sub, user_id, org_id)
    remaining = max(0, limit - used)

    return {
        "allowed": used < limit,
        "used": used,
        "limit": limit,
        "remaining": remaining,
    }


def check_sonnet_quota(
    db: Session, user_id: str, *, org_id: UUID | None = None, is_admin_eval: bool = False,
) -> dict:
    """
    Check whether the user/org can make a Sonnet (advanced analysis) query.

    Counts Sonnet usage from the token_usage table.
    Returns {allowed, tier, used, limit, remaining}.
    """
    if is_admin_eval:
        return _EVAL_BYPASS
    sub = get_or_create_subscription(db, user_id, org_id=org_id)
    tier_config = TIER_DEFAULTS.get(sub.tier, TIER_DEFAULTS["free"])
    limit = tier_config["sonnet_queries_limit"]

    if limit == 0:
        return {
            "allowed": False,
            "tier": sub.tier,
            "used": 0,
            "limit": 0,
            "remaining": 0,
        }

    used = _count_chat_usage(db, sub, user_id, org_id, model_filter="%sonnet%")
    remaining = max(0, limit - used)

    return {
        "allowed": used < limit,
        "tier": sub.tier,
        "used": used,
        "limit": limit,
        "remaining": remaining,
    }


# Legacy alias — callers that still import check_quota get Sonnet quota check
check_quota = check_sonnet_quota


def check_opus_quota(
    db: Session, user_id: str, *, org_id: UUID | None = None, is_admin_eval: bool = False,
) -> dict:
    """
    Check whether the user/org can make an Opus (premium analysis) query.

    Counts Opus usage from the token_usage table.
    Returns {allowed, tier, used, limit, remaining}.
    """
    if is_admin_eval:
        return _EVAL_BYPASS
    sub = get_or_create_subscription(db, user_id, org_id=org_id)
    tier_config = TIER_DEFAULTS.get(sub.tier, TIER_DEFAULTS["free"])
    limit = tier_config["opus_queries_limit"]

    if limit == 0:
        return {
            "allowed": False,
            "tier": sub.tier,
            "used": 0,
            "limit": 0,
            "remaining": 0,
        }

    used = _count_chat_usage(db, sub, user_id, org_id, model_filter="%opus%")
    remaining = max(0, limit - used)

    return {
        "allowed": used < limit,
        "tier": sub.tier,
        "used": used,
        "limit": limit,
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
    """Increment strategic_queries_used if this was a strategic/synthesis query."""
    if query_type not in ("strategic", "synthesis"):
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


# ---------------------------------------------------------------------------
# Browser extension helpers
# ---------------------------------------------------------------------------


def check_extension_capture_limit(
    db: Session, user_id: str, *, org_id: UUID | None = None,
) -> dict:
    """
    Check whether the user can make another extension capture today.

    Returns {allowed, current, limit, tier}.
    """
    sub = get_or_create_subscription(db, user_id, org_id=org_id)
    tier_config = TIER_DEFAULTS.get(sub.tier, TIER_DEFAULTS["free"])
    limit = tier_config["extension_captures_per_day"]

    if limit is None:
        return {"allowed": True, "current": 0, "limit": None, "tier": sub.tier}

    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    current = (
        db.query(func.count(Document.id))
        .join(Client, Document.client_id == Client.id)
        .filter(
            Document.source == "extension",
            Document.upload_date >= today_start,
        )
    )
    if org_id is not None:
        current = current.filter(Client.org_id == org_id)
    else:
        current = current.filter(Client.owner_id == user_id)

    count = current.scalar() or 0

    return {
        "allowed": count < limit,
        "current": count,
        "limit": limit,
        "tier": sub.tier,
    }


def get_extension_config(
    db: Session, user_id: str, *, org_id: UUID | None = None,
) -> dict:
    """
    Return the extension feature flags for the user's tier.
    """
    sub = get_or_create_subscription(db, user_id, org_id=org_id)
    tier_config = TIER_DEFAULTS.get(sub.tier, TIER_DEFAULTS["free"])

    limit = tier_config["extension_captures_per_day"]
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_q = (
        db.query(func.count(Document.id))
        .join(Client, Document.client_id == Client.id)
        .filter(
            Document.source == "extension",
            Document.upload_date >= today_start,
        )
    )
    if org_id is not None:
        today_q = today_q.filter(Client.org_id == org_id)
    else:
        today_q = today_q.filter(Client.owner_id == user_id)
    captures_today = today_q.scalar() or 0

    return {
        "tier": sub.tier,
        "auto_match": tier_config["extension_auto_match"],
        "quick_query": tier_config["extension_quick_query"],
        "parsers": tier_config["extension_parsers"],
        "monitoring": tier_config["extension_monitoring"],
        "captures_per_day": limit,
        "captures_today": captures_today,
    }

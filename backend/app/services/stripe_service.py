"""
Stripe payment integration service.

Handles checkout session creation, customer portal, and webhook event processing.
Gracefully degrades when STRIPE_SECRET_KEY is not configured.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import sentry_sdk

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.user import User
from app.models.user_subscription import UserSubscription
from app.services.notification_service import notify
from app.services.subscription_service import TIER_DEFAULTS

logger = logging.getLogger(__name__)


def is_configured() -> bool:
    """Return True when Stripe keys are set."""
    return bool(get_settings().stripe_secret_key)


def _stripe():
    """Return configured stripe module."""
    import stripe

    stripe.api_key = get_settings().stripe_secret_key
    return stripe


def _price_for_tier(tier: str, billing_interval: str = "monthly") -> str:
    """Map tier name + billing interval to Stripe price ID."""
    settings = get_settings()
    if billing_interval == "annual":
        mapping = {
            "starter": settings.stripe_price_starter_annual,
            "professional": settings.stripe_price_professional_annual,
            "firm": settings.stripe_price_firm_annual,
        }
    else:
        mapping = {
            "starter": settings.stripe_price_starter,
            "professional": settings.stripe_price_professional,
            "firm": settings.stripe_price_firm,
        }
    price_id = mapping.get(tier)
    if not price_id:
        raise ValueError(f"No Stripe price configured for tier: {tier} ({billing_interval})")
    return price_id


def _tier_for_price(price_id: str) -> str:
    """Map Stripe price ID back to tier name (monthly or annual)."""
    settings = get_settings()
    mapping = {
        settings.stripe_price_starter: "starter",
        settings.stripe_price_professional: "professional",
        settings.stripe_price_firm: "firm",
        settings.stripe_price_starter_annual: "starter",
        settings.stripe_price_professional_annual: "professional",
        settings.stripe_price_firm_annual: "firm",
    }
    return mapping.get(price_id, "free")


# ---------------------------------------------------------------------------
# Checkout & Portal
# ---------------------------------------------------------------------------


def create_checkout_session(
    user_id: str,
    user_email: str | None,
    tier: str,
    billing_interval: str = "monthly",
) -> str:
    """Create a Stripe Checkout session and return the URL."""
    stripe = _stripe()
    price_id = _price_for_tier(tier, billing_interval)
    settings = get_settings()
    base_url = settings.frontend_url.rstrip("/")

    params: dict = {
        "mode": "subscription",
        "line_items": [{"price": price_id, "quantity": 1}],
        "success_url": f"{base_url}/dashboard/settings/subscriptions?success=true",
        "cancel_url": f"{base_url}/dashboard/settings/subscriptions?canceled=true",
        "metadata": {
            "user_id": user_id,
            "tier": tier,
            "billing_interval": billing_interval,
        },
    }
    if user_email:
        params["customer_email"] = user_email

    session = stripe.checkout.Session.create(**params)
    return session.url


def create_customer_portal_session(stripe_customer_id: str) -> str:
    """Create a Stripe Billing Portal session and return the URL."""
    stripe = _stripe()
    settings = get_settings()
    base_url = settings.frontend_url.rstrip("/")
    session = stripe.billing_portal.Session.create(
        customer=stripe_customer_id,
        return_url=f"{base_url}/dashboard/settings/subscriptions",
    )
    return session.url


# ---------------------------------------------------------------------------
# Sync / Reconciliation
# ---------------------------------------------------------------------------


def sync_subscription_from_stripe(db: Session, stripe_subscription_id: str) -> UserSubscription | None:
    """
    Fetch a subscription from the Stripe API and reconcile the local record.

    Returns the updated UserSubscription or None if not found locally.
    """
    sub = (
        db.query(UserSubscription)
        .filter(UserSubscription.stripe_subscription_id == stripe_subscription_id)
        .first()
    )
    if not sub:
        logger.warning("sync_subscription_from_stripe: no local record for %s", stripe_subscription_id)
        return None

    try:
        stripe = _stripe()
        stripe_sub = stripe.Subscription.retrieve(stripe_subscription_id)
    except Exception as exc:
        logger.error("Failed to fetch Stripe subscription %s", stripe_subscription_id, exc_info=True)
        sentry_sdk.capture_exception(exc)
        return sub

    # Map price to tier
    items = stripe_sub.get("items", {}).get("data", [])
    if items:
        price_id = items[0].get("price", {}).get("id", "")
        new_tier = _tier_for_price(price_id)
        tier_config = TIER_DEFAULTS.get(new_tier, TIER_DEFAULTS["free"])
        sub.tier = new_tier
        sub.strategic_queries_limit = tier_config["strategic_queries_limit"]

    sub.stripe_status = stripe_sub.get("status", sub.stripe_status)

    # Sync billing period
    period_start = stripe_sub.get("current_period_start")
    period_end = stripe_sub.get("current_period_end")
    if period_start:
        sub.billing_period_start = datetime.fromtimestamp(period_start, tz=timezone.utc)
    if period_end:
        sub.billing_period_end = datetime.fromtimestamp(period_end, tz=timezone.utc)

    sub.payment_status = "active" if stripe_sub.get("status") == "active" else stripe_sub.get("status")
    sub.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(sub)

    logger.info(
        "Synced subscription from Stripe: user=%s tier=%s status=%s",
        sub.user_id, sub.tier, sub.stripe_status,
    )
    return sub


# ---------------------------------------------------------------------------
# Webhook event handlers
# ---------------------------------------------------------------------------


def handle_checkout_completed(db: Session, session: dict) -> None:
    """Process a successful checkout.session.completed event."""
    metadata = session.get("metadata", {})
    user_id = metadata.get("user_id")
    tier = metadata.get("tier")

    if not user_id or not tier:
        logger.warning("Checkout completed without user_id/tier metadata: %s", session.get("id"))
        return

    tier_config = TIER_DEFAULTS.get(tier)
    if not tier_config:
        logger.warning("Unknown tier in checkout metadata: %s", tier)
        return

    now = datetime.now(timezone.utc)
    sub = db.query(UserSubscription).filter(UserSubscription.user_id == user_id).first()

    if sub is None:
        sub = UserSubscription(
            user_id=user_id,
            tier=tier,
            strategic_queries_limit=tier_config["strategic_queries_limit"],
            strategic_queries_used=0,
            billing_period_start=now,
            billing_period_end=now + timedelta(days=30),
        )
        db.add(sub)

    sub.tier = tier
    sub.strategic_queries_limit = tier_config["strategic_queries_limit"]
    sub.stripe_customer_id = session.get("customer")
    sub.stripe_subscription_id = session.get("subscription")
    sub.stripe_status = "active"
    sub.payment_status = "active"
    sub.updated_at = now

    # Use Stripe's billing period if available via the subscription object
    stripe_sub_id = session.get("subscription")
    if stripe_sub_id:
        try:
            stripe = _stripe()
            stripe_sub = stripe.Subscription.retrieve(stripe_sub_id)
            sub.billing_period_start = datetime.fromtimestamp(
                stripe_sub.current_period_start, tz=timezone.utc
            )
            sub.billing_period_end = datetime.fromtimestamp(
                stripe_sub.current_period_end, tz=timezone.utc
            )
        except Exception:
            logger.warning("Could not fetch Stripe subscription periods, using 30-day default")
            sub.billing_period_start = now
            sub.billing_period_end = now + timedelta(days=30)
    else:
        sub.billing_period_start = now
        sub.billing_period_end = now + timedelta(days=30)

    # Reset usage counter on upgrade
    sub.strategic_queries_used = 0

    db.commit()

    user_email = session.get("customer_email") or session.get("customer_details", {}).get("email") or user_id
    notify("upgrade", "User upgraded subscription", {"email": user_email, "tier": tier, "mrr_impact": "+$99"})

    logger.info(
        "Checkout completed: user=%s tier=%s stripe_sub=%s",
        user_id, tier, session.get("subscription"),
    )


def handle_subscription_updated(db: Session, subscription: dict) -> None:
    """Sync tier and billing period when subscription changes in Stripe."""
    stripe_sub_id = subscription.get("id")
    sub = (
        db.query(UserSubscription)
        .filter(UserSubscription.stripe_subscription_id == stripe_sub_id)
        .first()
    )
    if not sub:
        logger.warning("Subscription updated for unknown stripe_subscription_id: %s", stripe_sub_id)
        return

    # Get the current price from the subscription items
    items = subscription.get("items", {}).get("data", [])
    if items:
        price_id = items[0].get("price", {}).get("id", "")
        new_tier = _tier_for_price(price_id)
        tier_config = TIER_DEFAULTS.get(new_tier, TIER_DEFAULTS["free"])
        sub.tier = new_tier
        sub.strategic_queries_limit = tier_config["strategic_queries_limit"]

    sub.stripe_status = subscription.get("status", "active")

    # Sync billing period from Stripe
    period_start = subscription.get("current_period_start")
    period_end = subscription.get("current_period_end")
    if period_start:
        sub.billing_period_start = datetime.fromtimestamp(period_start, tz=timezone.utc)
    if period_end:
        sub.billing_period_end = datetime.fromtimestamp(period_end, tz=timezone.utc)

    sub.payment_status = "active" if subscription.get("status") == "active" else subscription.get("status")
    sub.updated_at = datetime.now(timezone.utc)
    db.commit()

    logger.info(
        "Subscription updated: user=%s tier=%s status=%s",
        sub.user_id, sub.tier, sub.stripe_status,
    )


def handle_subscription_deleted(db: Session, subscription: dict) -> None:
    """Downgrade to free when subscription is canceled."""
    stripe_sub_id = subscription.get("id")
    sub = (
        db.query(UserSubscription)
        .filter(UserSubscription.stripe_subscription_id == stripe_sub_id)
        .first()
    )
    if not sub:
        logger.warning("Subscription deleted for unknown stripe_subscription_id: %s", stripe_sub_id)
        return

    old_tier = sub.tier
    free_config = TIER_DEFAULTS["free"]
    now = datetime.now(timezone.utc)
    sub.tier = "free"
    sub.strategic_queries_limit = free_config["strategic_queries_limit"]
    sub.strategic_queries_used = 0
    sub.stripe_status = "canceled"
    sub.payment_status = None
    sub.billing_period_start = now
    sub.billing_period_end = now + timedelta(days=30)
    sub.updated_at = now
    db.commit()

    user_obj = db.query(User).filter(User.clerk_id == sub.user_id).first()
    user_email = user_obj.email if user_obj else sub.user_id
    notify("churn", "User canceled subscription", {"email": user_email, "previous_tier": old_tier})

    logger.info("Subscription canceled — downgraded to free: user=%s", sub.user_id)


def handle_payment_failed(db: Session, invoice: dict) -> None:
    """Mark subscription as past_due on payment failure."""
    stripe_sub_id = invoice.get("subscription")
    if not stripe_sub_id:
        return

    sub = (
        db.query(UserSubscription)
        .filter(UserSubscription.stripe_subscription_id == stripe_sub_id)
        .first()
    )
    if not sub:
        return

    sub.stripe_status = "past_due"
    sub.payment_status = "failed"
    sub.updated_at = datetime.now(timezone.utc)
    db.commit()

    user_obj = db.query(User).filter(User.clerk_id == sub.user_id).first()
    user_email = user_obj.email if user_obj else sub.user_id
    notify("payment_failed", "Payment failed", {"email": user_email, "tier": sub.tier})

    logger.warning("Payment failed for user=%s subscription=%s", sub.user_id, stripe_sub_id)

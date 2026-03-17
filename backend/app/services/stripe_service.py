"""
Stripe payment integration service.

Handles checkout session creation, customer portal, and webhook event processing.
Gracefully degrades when STRIPE_SECRET_KEY is not configured.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.user_subscription import UserSubscription
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


def _price_for_tier(tier: str) -> str:
    """Map tier name to Stripe price ID."""
    settings = get_settings()
    mapping = {
        "starter": settings.stripe_price_starter,
        "professional": settings.stripe_price_professional,
        "firm": settings.stripe_price_firm,
    }
    price_id = mapping.get(tier)
    if not price_id:
        raise ValueError(f"No Stripe price configured for tier: {tier}")
    return price_id


def _tier_for_price(price_id: str) -> str:
    """Map Stripe price ID back to tier name."""
    settings = get_settings()
    mapping = {
        settings.stripe_price_starter: "starter",
        settings.stripe_price_professional: "professional",
        settings.stripe_price_firm: "firm",
    }
    return mapping.get(price_id, "starter")


# ---------------------------------------------------------------------------
# Checkout & Portal
# ---------------------------------------------------------------------------


def create_checkout_session(
    user_id: str, user_email: str | None, tier: str
) -> str:
    """Create a Stripe Checkout session and return the URL."""
    stripe = _stripe()
    price_id = _price_for_tier(tier)

    params: dict = {
        "mode": "subscription",
        "line_items": [{"price": price_id, "quantity": 1}],
        "success_url": "https://myadvisoryboard.space/dashboard/settings/subscriptions?success=true",
        "cancel_url": "https://myadvisoryboard.space/dashboard/settings/subscriptions?canceled=true",
        "metadata": {"user_id": user_id, "tier": tier},
    }
    if user_email:
        params["customer_email"] = user_email

    session = stripe.checkout.Session.create(**params)
    return session.url


def create_customer_portal_session(stripe_customer_id: str) -> str:
    """Create a Stripe Billing Portal session and return the URL."""
    stripe = _stripe()
    session = stripe.billing_portal.Session.create(
        customer=stripe_customer_id,
        return_url="https://myadvisoryboard.space/dashboard/settings/subscriptions",
    )
    return session.url


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
    sub.billing_period_start = now
    sub.billing_period_end = now + timedelta(days=30)
    sub.stripe_customer_id = session.get("customer")
    sub.stripe_subscription_id = session.get("subscription")
    sub.stripe_status = "active"
    sub.updated_at = now

    db.commit()
    logger.info(
        "Checkout completed: user=%s tier=%s stripe_sub=%s",
        user_id, tier, session.get("subscription"),
    )


def handle_subscription_updated(db: Session, subscription: dict) -> None:
    """Sync tier when subscription changes in Stripe."""
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
        tier_config = TIER_DEFAULTS.get(new_tier, TIER_DEFAULTS["starter"])
        sub.tier = new_tier
        sub.strategic_queries_limit = tier_config["strategic_queries_limit"]

    sub.stripe_status = subscription.get("status", "active")
    sub.updated_at = datetime.now(timezone.utc)
    db.commit()

    logger.info(
        "Subscription updated: user=%s tier=%s status=%s",
        sub.user_id, sub.tier, sub.stripe_status,
    )


def handle_subscription_deleted(db: Session, subscription: dict) -> None:
    """Downgrade to starter when subscription is canceled."""
    stripe_sub_id = subscription.get("id")
    sub = (
        db.query(UserSubscription)
        .filter(UserSubscription.stripe_subscription_id == stripe_sub_id)
        .first()
    )
    if not sub:
        logger.warning("Subscription deleted for unknown stripe_subscription_id: %s", stripe_sub_id)
        return

    starter_config = TIER_DEFAULTS["starter"]
    sub.tier = "starter"
    sub.strategic_queries_limit = starter_config["strategic_queries_limit"]
    sub.stripe_status = "canceled"
    sub.updated_at = datetime.now(timezone.utc)
    db.commit()

    logger.info("Subscription canceled — downgraded to starter: user=%s", sub.user_id)


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
    sub.updated_at = datetime.now(timezone.utc)
    db.commit()

    logger.warning("Payment failed for user=%s subscription=%s", sub.user_id, stripe_sub_id)

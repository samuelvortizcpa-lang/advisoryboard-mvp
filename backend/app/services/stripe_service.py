"""
Stripe payment integration service.

Handles checkout session creation, customer portal, and webhook event processing.
Gracefully degrades when STRIPE_SECRET_KEY is not configured.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

import sentry_sdk

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.user import User
from app.models.user_subscription import UserSubscription
from app.services.notification_service import notify
from app.services.subscription_service import TIER_DEFAULTS, get_seat_info, update_org_seat_limit

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
    """Map tier name + billing interval to the *base* Stripe price ID.

    For the Firm tier this returns the hybrid base price ($349/mo or
    $3,348/yr).  Add-on seat prices are handled separately in
    ``create_checkout_session`` and ``create_addon_seat_update``.
    """
    settings = get_settings()
    if billing_interval == "annual":
        mapping = {
            "starter": settings.stripe_price_starter_annual,
            "professional": settings.stripe_price_professional_annual,
            "firm": settings.stripe_price_firm_hybrid_annual,
        }
    else:
        mapping = {
            "starter": settings.stripe_price_starter,
            "professional": settings.stripe_price_professional,
            "firm": settings.stripe_price_firm_hybrid_monthly,
        }
    price_id = mapping.get(tier)
    if not price_id:
        raise ValueError(f"No Stripe price configured for tier: {tier} ({billing_interval})")
    return price_id


def _addon_seat_price(billing_interval: str = "monthly") -> str:
    """Return the add-on seat Stripe price ID for the given interval."""
    settings = get_settings()
    if billing_interval == "annual":
        return settings.stripe_price_addon_seat_annual
    return settings.stripe_price_addon_seat_monthly


def _tier_for_price(price_id: str) -> str:
    """Map Stripe price ID back to tier name (monthly or annual).

    Price ID mappings
    ─────────────────
    Starter  Monthly  price_1TCW0d22KK3wqa2qjXU8JJMV  → "starter"
    Starter  Annual   price_1TCW0c22KK3wqa2qZTTTJnFe  → "starter"
    Prof.    Monthly  price_1TCW0a22KK3wqa2qEw188KwS  → "professional"
    Prof.    Annual   price_1TCW0a22KK3wqa2qaAiHIjgw  → "professional"
    Firm OLD Monthly  price_1TCW0b22KK3wqa2qQD2Z6TEn  → "firm"  (legacy)
    Firm OLD Annual   price_1TCW0a22KK3wqa2q9KUYccUH  → "firm"  (legacy)
    Firm NEW Monthly  STRIPE_PRICE_FIRM_HYBRID_MONTHLY → "firm"  (hybrid base)
    Firm NEW Annual   STRIPE_PRICE_FIRM_HYBRID_ANNUAL  → "firm"  (hybrid base)
    Add-On   Monthly  STRIPE_PRICE_ADDON_SEAT_MONTHLY  → "firm_addon_seat"
    Add-On   Annual   STRIPE_PRICE_ADDON_SEAT_ANNUAL   → "firm_addon_seat"
    """
    settings = get_settings()
    mapping: dict[str, str] = {
        # Starter
        settings.stripe_price_starter: "starter",
        settings.stripe_price_starter_annual: "starter",
        # Professional
        settings.stripe_price_professional: "professional",
        settings.stripe_price_professional_annual: "professional",
        # Firm — legacy per-seat prices
        settings.stripe_price_firm: "firm",
        settings.stripe_price_firm_annual: "firm",
        # Firm — new hybrid base prices
        settings.stripe_price_firm_hybrid_monthly: "firm",
        settings.stripe_price_firm_hybrid_annual: "firm",
        # Add-on seat prices
        settings.stripe_price_addon_seat_monthly: "firm_addon_seat",
        settings.stripe_price_addon_seat_annual: "firm_addon_seat",
    }
    # Remove empty-string keys so unconfigured env vars don't clobber lookups
    mapping.pop("", None)
    return mapping.get(price_id, "free")


def _lookup_sub(db: Session, *, org_id: str | None, user_id: str | None) -> UserSubscription | None:
    """Look up a subscription by org_id first, then user_id fallback."""
    sub = None
    if org_id:
        try:
            sub = (
                db.query(UserSubscription)
                .filter(UserSubscription.org_id == UUID(org_id))
                .first()
            )
        except (ValueError, TypeError):
            pass
    if sub is None and user_id:
        sub = (
            db.query(UserSubscription)
            .filter(UserSubscription.user_id == user_id)
            .first()
        )
    return sub


# ---------------------------------------------------------------------------
# Checkout & Portal
# ---------------------------------------------------------------------------


def create_checkout_session(
    user_id: str,
    user_email: str | None,
    tier: str,
    billing_interval: str = "monthly",
    *,
    addon_seats: int = 0,
    org_id: UUID | None = None,
    db: Session | None = None,
) -> str:
    """Create a Stripe Checkout session and return the URL.

    For the Firm tier, the checkout includes a base price (qty=1) and,
    when *addon_seats* > 0, a second line item for add-on seats.
    """
    stripe = _stripe()
    price_id = _price_for_tier(tier, billing_interval)
    settings = get_settings()
    base_url = settings.frontend_url.rstrip("/")

    metadata: dict = {
        "user_id": user_id,
        "tier": tier,
        "billing_interval": billing_interval,
    }
    if org_id is not None:
        metadata["org_id"] = str(org_id)
    if addon_seats > 0:
        metadata["addon_seats"] = str(addon_seats)

    # Build line items — firm tier may include add-on seats
    line_items: list[dict] = [{"price": price_id, "quantity": 1}]
    if tier == "firm" and addon_seats > 0:
        addon_price_id = _addon_seat_price(billing_interval)
        line_items.append({"price": addon_price_id, "quantity": addon_seats})

    params: dict = {
        "mode": "subscription",
        "line_items": line_items,
        "success_url": f"{base_url}/dashboard/settings/subscriptions?success=true",
        "cancel_url": f"{base_url}/dashboard/settings/subscriptions?canceled=true",
        "metadata": metadata,
    }

    # Reuse existing Stripe customer if the org already has one
    if org_id is not None and db is not None:
        existing_sub = (
            db.query(UserSubscription)
            .filter(UserSubscription.org_id == org_id)
            .first()
        )
        if existing_sub and existing_sub.stripe_customer_id:
            params["customer"] = existing_sub.stripe_customer_id

    if "customer" not in params and user_email:
        params["customer_email"] = user_email

    session = stripe.checkout.Session.create(**params)
    return session.url


def create_customer_portal_session(
    stripe_customer_id: str,
) -> str:
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
    new_tier = sub.tier
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

    # Sync org seat limit if applicable
    if sub.org_id:
        update_org_seat_limit(sub.org_id, new_tier, db)

    logger.info(
        "Synced subscription from Stripe: user=%s org=%s tier=%s status=%s",
        sub.user_id, sub.org_id, sub.tier, sub.stripe_status,
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
    org_id_str = metadata.get("org_id")

    if not user_id or not tier:
        logger.warning("Checkout completed without user_id/tier metadata: %s", session.get("id"))
        return

    tier_config = TIER_DEFAULTS.get(tier)
    if not tier_config:
        logger.warning("Unknown tier in checkout metadata: %s", tier)
        return

    now = datetime.now(timezone.utc)

    # Look up subscription: org_id first, then user_id
    sub = _lookup_sub(db, org_id=org_id_str, user_id=user_id)

    if sub is None:
        sub = UserSubscription(
            user_id=user_id,
            tier=tier,
            strategic_queries_limit=tier_config["strategic_queries_limit"],
            strategic_queries_used=0,
            billing_period_start=now,
            billing_period_end=now + timedelta(days=30),
        )
        if org_id_str:
            try:
                sub.org_id = UUID(org_id_str)
            except (ValueError, TypeError):
                pass
        db.add(sub)

    sub.tier = tier
    sub.strategic_queries_limit = tier_config["strategic_queries_limit"]
    sub.stripe_customer_id = session.get("customer")
    sub.stripe_subscription_id = session.get("subscription")
    sub.stripe_status = "active"
    sub.payment_status = "active"
    sub.updated_at = now

    # Backfill org_id if present in metadata but not yet on record
    if org_id_str and sub.org_id is None:
        try:
            sub.org_id = UUID(org_id_str)
        except (ValueError, TypeError):
            pass

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

    # Persist add-on seats from checkout metadata
    addon_seats_str = metadata.get("addon_seats", "0")
    try:
        sub.addon_seats = int(addon_seats_str)
    except (ValueError, TypeError):
        sub.addon_seats = 0

    db.commit()

    # Sync org seat limit
    if sub.org_id:
        update_org_seat_limit(sub.org_id, tier, db)

    user_email = session.get("customer_email") or session.get("customer_details", {}).get("email") or user_id
    notify("upgrade", "User upgraded subscription", {"email": user_email, "tier": tier, "mrr_impact": "+$99"})

    logger.info(
        "Checkout completed: user=%s org=%s tier=%s addon_seats=%s stripe_sub=%s",
        user_id, sub.org_id, tier, sub.addon_seats, session.get("subscription"),
    )


def handle_subscription_updated(db: Session, subscription: dict) -> None:
    """Sync tier, billing period, and addon seats when subscription changes in Stripe.

    Iterates all subscription items to distinguish the base price from
    add-on seat items so both ``tier`` and ``addon_seats`` stay in sync.
    """
    stripe_sub_id = subscription.get("id")
    sub = (
        db.query(UserSubscription)
        .filter(UserSubscription.stripe_subscription_id == stripe_sub_id)
        .first()
    )
    if not sub:
        logger.warning("Subscription updated for unknown stripe_subscription_id: %s", stripe_sub_id)
        return

    # Iterate all items to identify the base tier and addon seat count
    new_tier = sub.tier
    addon_seats = 0
    items = subscription.get("items", {}).get("data", [])
    for item in items:
        price_id = item.get("price", {}).get("id", "")
        mapped = _tier_for_price(price_id)
        if mapped == "firm_addon_seat":
            addon_seats = item.get("quantity", 0)
        elif mapped != "free":
            # This is a base tier item
            new_tier = mapped

    tier_config = TIER_DEFAULTS.get(new_tier, TIER_DEFAULTS["free"])
    sub.tier = new_tier
    sub.strategic_queries_limit = tier_config["strategic_queries_limit"]
    sub.addon_seats = addon_seats
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

    # Sync org seat limit
    if sub.org_id:
        update_org_seat_limit(sub.org_id, new_tier, db)

    logger.info(
        "Subscription updated: user=%s org=%s tier=%s addon_seats=%d status=%s",
        sub.user_id, sub.org_id, sub.tier, sub.addon_seats, sub.stripe_status,
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

    # Sync org seat limit to free tier
    if sub.org_id:
        update_org_seat_limit(sub.org_id, "free", db)

    user_obj = db.query(User).filter(User.clerk_id == sub.user_id).first()
    user_email = user_obj.email if user_obj else sub.user_id
    notify("churn", "User canceled subscription", {"email": user_email, "previous_tier": old_tier})

    logger.info("Subscription canceled — downgraded to free: user=%s org=%s", sub.user_id, sub.org_id)


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

    logger.warning("Payment failed for user=%s org=%s subscription=%s", sub.user_id, sub.org_id, stripe_sub_id)


# ---------------------------------------------------------------------------
# Addon seat management
# ---------------------------------------------------------------------------


def create_addon_seat_update(org_id: UUID, new_addon_count: int, db: Session) -> dict:
    """Modify the add-on seat quantity on an existing Firm subscription.

    If the subscription already has an add-on seat line item, its quantity is
    updated (or the item is removed when *new_addon_count* is 0).  If no
    add-on seat item exists yet, one is added.

    Proration is applied so the customer is charged or credited immediately
    for the mid-cycle change.

    Returns a summary dict with the updated seat info.
    """
    sub = (
        db.query(UserSubscription)
        .filter(UserSubscription.org_id == org_id)
        .first()
    )
    if sub is None or not sub.stripe_subscription_id:
        raise ValueError("No active Stripe subscription found for this organization")

    stripe = _stripe()

    # Determine billing interval from the current subscription
    stripe_sub = stripe.Subscription.retrieve(sub.stripe_subscription_id)
    billing_interval = "annual"
    for item in stripe_sub["items"]["data"]:
        price = item.get("price", {})
        if price.get("recurring", {}).get("interval") == "month":
            billing_interval = "monthly"
            break

    addon_price_id = _addon_seat_price(billing_interval)

    # Find existing add-on seat item
    addon_item = None
    for item in stripe_sub["items"]["data"]:
        if item.get("price", {}).get("id") == addon_price_id:
            addon_item = item
            break

    if addon_item:
        if new_addon_count <= 0:
            # Remove the add-on seat line item entirely
            stripe.SubscriptionItem.delete(addon_item["id"], proration_behavior="create_prorations")
        else:
            # Update quantity on the existing item
            stripe.SubscriptionItem.modify(
                addon_item["id"],
                quantity=new_addon_count,
                proration_behavior="create_prorations",
            )
    elif new_addon_count > 0:
        # Add a new add-on seat line item to the subscription
        stripe.SubscriptionItem.create(
            subscription=sub.stripe_subscription_id,
            price=addon_price_id,
            quantity=new_addon_count,
            proration_behavior="create_prorations",
        )

    # Update local record
    sub.addon_seats = max(new_addon_count, 0)
    sub.updated_at = datetime.now(timezone.utc)
    db.commit()

    # Sync org seat limit
    update_org_seat_limit(org_id, sub.tier, db)

    seat_info = get_seat_info(org_id, db)
    logger.info(
        "Addon seats updated: org=%s addon_seats=%d total_allowed=%d",
        org_id, sub.addon_seats, seat_info["total_allowed"],
    )
    return seat_info

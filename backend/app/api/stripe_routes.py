"""
Stripe payment API endpoints.

Routes:
  POST /api/stripe/create-checkout   — Create Stripe Checkout session (auth required)
  POST /api/stripe/create-portal     — Create Billing Portal session (auth required)
  POST /api/stripe/webhook           — Stripe webhook handler (NO auth — signature verified)
  GET  /api/stripe/status            — Current user's Stripe subscription status (auth required)
  GET  /api/stripe/sync              — Manual reconciliation from Stripe (auth required)
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.config import get_settings
from app.core.database import get_db
from app.models.processed_webhook_event import ProcessedWebhookEvent
from app.models.user_subscription import UserSubscription
from app.services import stripe_service, user_service

logger = logging.getLogger(__name__)

router = APIRouter()


def _require_stripe():
    """Raise 503 if Stripe is not configured."""
    if not stripe_service.is_configured():
        raise HTTPException(status_code=503, detail="Payment processing not configured")


# ─── Schemas ─────────────────────────────────────────────────────────────────


class CheckoutRequest(BaseModel):
    tier: str


class CheckoutResponse(BaseModel):
    url: str


class PortalResponse(BaseModel):
    url: str


class StripeStatusResponse(BaseModel):
    stripe_status: str
    stripe_customer_id: str | None = None
    tier: str
    payment_status: str | None = None


# ─── Endpoints ───────────────────────────────────────────────────────────────


@router.post(
    "/create-checkout",
    response_model=CheckoutResponse,
    summary="Create a Stripe Checkout session",
)
async def create_checkout(
    body: CheckoutRequest,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> CheckoutResponse:
    _require_stripe()

    if body.tier not in ("starter", "professional", "firm"):
        raise HTTPException(status_code=400, detail="Invalid tier")

    user = user_service.get_or_create_user(db, current_user)
    try:
        url = stripe_service.create_checkout_session(
            user_id=user.clerk_id,
            user_email=user.email,
            tier=body.tier,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return CheckoutResponse(url=url)


@router.post(
    "/create-portal",
    response_model=PortalResponse,
    summary="Create a Stripe Billing Portal session",
)
async def create_portal(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> PortalResponse:
    _require_stripe()

    user = user_service.get_or_create_user(db, current_user)
    sub = (
        db.query(UserSubscription)
        .filter(UserSubscription.user_id == user.clerk_id)
        .first()
    )

    if not sub or not sub.stripe_customer_id:
        raise HTTPException(status_code=400, detail="No Stripe subscription found")

    url = stripe_service.create_customer_portal_session(sub.stripe_customer_id)
    return PortalResponse(url=url)


@router.post("/webhook", summary="Stripe webhook handler")
async def stripe_webhook(request: Request):
    """Handle Stripe webhook events. No auth — verified by signature."""
    settings = get_settings()
    if not settings.stripe_webhook_secret:
        raise HTTPException(status_code=503, detail="Webhook not configured")

    import stripe

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.stripe_webhook_secret
        )
    except stripe.error.SignatureVerificationError:
        logger.warning("Stripe webhook signature verification failed")
        raise HTTPException(status_code=400, detail="Invalid signature")
    except Exception as e:
        logger.error("Stripe webhook error: %s", e)
        raise HTTPException(status_code=400, detail="Invalid payload")

    # Process event with a fresh DB session
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        event_id = event["id"]

        # Idempotency check — skip already-processed events
        existing = db.query(ProcessedWebhookEvent).filter(ProcessedWebhookEvent.id == event_id).first()
        if existing:
            logger.info("Skipping already-processed webhook event: %s", event_id)
            return {"received": True}

        event_type = event["type"]
        data = event["data"]["object"]

        if event_type == "checkout.session.completed":
            stripe_service.handle_checkout_completed(db, data)
        elif event_type == "customer.subscription.updated":
            stripe_service.handle_subscription_updated(db, data)
        elif event_type == "customer.subscription.deleted":
            stripe_service.handle_subscription_deleted(db, data)
        elif event_type == "invoice.payment_failed":
            stripe_service.handle_payment_failed(db, data)
        elif event_type == "invoice.payment_succeeded":
            logger.info("Payment succeeded for subscription %s", data.get("subscription"))
        else:
            logger.info("Unhandled Stripe event type: %s", event_type)

        # Record event as processed
        db.add(ProcessedWebhookEvent(id=event_id))
        db.commit()
    except Exception:
        logger.error("Error processing Stripe webhook", exc_info=True)
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        db.close()

    return {"received": True}


@router.get(
    "/status",
    response_model=StripeStatusResponse,
    summary="Get current user's Stripe subscription status",
)
async def stripe_status(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> StripeStatusResponse:
    user = user_service.get_or_create_user(db, current_user)
    sub = (
        db.query(UserSubscription)
        .filter(UserSubscription.user_id == user.clerk_id)
        .first()
    )

    if not sub:
        return StripeStatusResponse(stripe_status="none", tier="free")

    return StripeStatusResponse(
        stripe_status=sub.stripe_status or "none",
        stripe_customer_id=sub.stripe_customer_id,
        tier=sub.tier,
        payment_status=sub.payment_status,
    )


@router.get(
    "/sync",
    response_model=StripeStatusResponse,
    summary="Sync subscription status from Stripe (manual reconciliation)",
)
async def stripe_sync(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> StripeStatusResponse:
    _require_stripe()

    user = user_service.get_or_create_user(db, current_user)
    sub = (
        db.query(UserSubscription)
        .filter(UserSubscription.user_id == user.clerk_id)
        .first()
    )

    if not sub or not sub.stripe_subscription_id:
        raise HTTPException(status_code=400, detail="No Stripe subscription to sync")

    updated = stripe_service.sync_subscription_from_stripe(db, sub.stripe_subscription_id)
    if not updated:
        raise HTTPException(status_code=500, detail="Failed to sync subscription")

    return StripeStatusResponse(
        stripe_status=updated.stripe_status or "none",
        stripe_customer_id=updated.stripe_customer_id,
        tier=updated.tier,
        payment_status=updated.payment_status,
    )

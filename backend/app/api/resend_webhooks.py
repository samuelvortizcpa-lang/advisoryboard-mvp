"""Resend delivery webhook handler (Svix-standard signatures)."""

import logging

from fastapi import APIRouter, HTTPException, Request

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.services.resend_webhook_service import handle_event

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/resend", summary="Resend delivery webhook")
async def resend_webhook(request: Request):
    """Handle Resend delivery/bounce/complaint webhooks. Verified by Svix signature."""
    settings = get_settings()
    if not settings.resend_webhook_secret:
        raise HTTPException(status_code=503, detail="Webhook not configured")

    payload = await request.body()
    svix_id = request.headers.get("svix-id", "")
    svix_timestamp = request.headers.get("svix-timestamp", "")
    svix_signature = request.headers.get("svix-signature", "")

    if not (svix_id and svix_timestamp and svix_signature):
        raise HTTPException(status_code=401, detail="Missing signature headers")

    # Verify Svix signature
    from resend import Webhooks

    try:
        event = Webhooks.verify({
            "payload": payload.decode("utf-8"),
            "headers": {
                "id": svix_id,
                "timestamp": svix_timestamp,
                "signature": svix_signature,
            },
            "webhook_secret": settings.resend_webhook_secret,
        })
    except (ValueError, TypeError, KeyError, AttributeError):
        logger.warning("Resend webhook signature verification failed")
        raise HTTPException(status_code=400, detail="Invalid signature")

    event_type = event.get("type", "")
    event_data = event.get("data", {})
    event_id = svix_id

    db = SessionLocal()
    try:
        handle_event(db, event_type, event_data, event_id)
        db.commit()
    except Exception as exc:
        logger.error("Error processing Resend webhook", exc_info=True)
        try:
            db.rollback()
        except Exception:
            pass
        raise HTTPException(status_code=500, detail="Webhook processing failed")
    finally:
        db.close()

    return {"received": True}

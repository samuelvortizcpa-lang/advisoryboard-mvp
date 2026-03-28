"""
Tests for Stripe webhook handlers — Priority 1 (billing).

Covers checkout.session.completed, customer.subscription.updated/deleted,
invoice.payment_failed, idempotency via ProcessedWebhookEvent, and
legacy firm price detection.
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.models.processed_webhook_event import ProcessedWebhookEvent
from app.models.user_subscription import UserSubscription
from app.services import stripe_service
from app.services.subscription_service import TIER_DEFAULTS
from tests.conftest import (
    make_org,
    make_stripe_event,
    make_checkout_session_data,
    make_subscription_data,
    make_invoice_data,
    make_subscription,
    make_user,
)


# ---------------------------------------------------------------------------
# handle_checkout_completed
# ---------------------------------------------------------------------------


class TestHandleCheckoutCompleted:
    @patch("app.services.stripe_service._stripe")
    @patch("app.services.stripe_service.notify")
    @patch("app.services.stripe_service.update_org_seat_limit")
    def test_creates_new_subscription(self, mock_org_seats, mock_notify, mock_stripe, db: Session):
        """Checkout session with new user creates a subscription record."""
        user = make_user(db)
        org = make_org(db, owner_user_id=user.clerk_id)

        # Mock Stripe subscription retrieval for billing period
        mock_sub = {
            "current_period_start": int(datetime.now(timezone.utc).timestamp()),
            "current_period_end": int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp()),
        }
        mock_stripe.return_value.Subscription.retrieve.return_value = mock_sub

        session_data = make_checkout_session_data(
            metadata={"user_id": user.clerk_id, "tier": "starter", "org_id": str(org.id)},
        )

        stripe_service.handle_checkout_completed(db, session_data)

        sub = db.query(UserSubscription).filter(UserSubscription.user_id == user.clerk_id).first()
        assert sub is not None
        assert sub.tier == "starter"
        assert sub.stripe_customer_id == "cus_test123"
        assert sub.stripe_subscription_id == "sub_test123"

    @patch("app.services.stripe_service._stripe")
    @patch("app.services.stripe_service.notify")
    @patch("app.services.stripe_service.update_org_seat_limit")
    def test_updates_existing_subscription(self, mock_org_seats, mock_notify, mock_stripe, db: Session):
        """Checkout for existing user updates their subscription tier."""
        user = make_user(db)
        org = make_org(db, owner_user_id=user.clerk_id)
        make_subscription(db, user.clerk_id, org_id=org.id, tier="free")

        mock_sub = {
            "current_period_start": int(datetime.now(timezone.utc).timestamp()),
            "current_period_end": int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp()),
        }
        mock_stripe.return_value.Subscription.retrieve.return_value = mock_sub

        session_data = make_checkout_session_data(
            metadata={"user_id": user.clerk_id, "tier": "professional", "org_id": str(org.id)},
        )

        stripe_service.handle_checkout_completed(db, session_data)

        sub = db.query(UserSubscription).filter(UserSubscription.user_id == user.clerk_id).first()
        assert sub.tier == "professional"
        assert sub.strategic_queries_used == 0  # reset on upgrade

    @patch("app.services.stripe_service._stripe")
    @patch("app.services.stripe_service.notify")
    @patch("app.services.stripe_service.update_org_seat_limit")
    def test_handles_addon_seats_from_metadata(self, mock_org_seats, mock_notify, mock_stripe, db: Session):
        """Addon seats from checkout metadata are persisted."""
        user = make_user(db)
        org = make_org(db, owner_user_id=user.clerk_id)

        mock_sub = {
            "current_period_start": int(datetime.now(timezone.utc).timestamp()),
            "current_period_end": int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp()),
            "items": {"data": []},
        }
        mock_stripe.return_value.Subscription.retrieve.return_value = mock_sub

        session_data = make_checkout_session_data(
            metadata={
                "user_id": user.clerk_id,
                "tier": "firm",
                "org_id": str(org.id),
                "addon_seats": "5",
            },
        )

        stripe_service.handle_checkout_completed(db, session_data)

        sub = db.query(UserSubscription).filter(UserSubscription.user_id == user.clerk_id).first()
        assert sub.addon_seats == 5


# ---------------------------------------------------------------------------
# handle_subscription_updated
# ---------------------------------------------------------------------------


class TestHandleSubscriptionUpdated:
    @patch("app.services.stripe_service.update_org_seat_limit")
    def test_syncs_tier_and_status(self, mock_org_seats, db: Session):
        """Subscription update syncs tier, status, and billing period."""
        user = make_user(db)
        org = make_org(db, owner_user_id=user.clerk_id)
        sub = make_subscription(
            db,
            user.clerk_id,
            org_id=org.id,
            tier="starter",
            stripe_subscription_id="sub_update_test",
        )

        now_ts = int(datetime.now(timezone.utc).timestamp())
        end_ts = int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp())

        subscription_data = {
            "id": "sub_update_test",
            "customer": "cus_test",
            "status": "active",
            "current_period_start": now_ts,
            "current_period_end": end_ts,
            "items": {"data": [
                {
                    "price": {"id": "price_professional_monthly", "recurring": {"interval": "month"}},
                    "quantity": 1,
                },
            ]},
            "metadata": {"user_id": user.clerk_id},
        }

        with patch("app.services.stripe_service._tier_for_price", return_value="professional"):
            stripe_service.handle_subscription_updated(db, subscription_data)

        db.refresh(sub)
        assert sub.tier == "professional"
        assert sub.stripe_status == "active"
        assert sub.strategic_queries_limit == TIER_DEFAULTS["professional"]["strategic_queries_limit"]

    @patch("app.services.stripe_service.update_org_seat_limit")
    def test_handles_addon_seat_items(self, mock_org_seats, db: Session):
        """Subscription with addon seat line item updates addon_seats."""
        user = make_user(db)
        org = make_org(db, owner_user_id=user.clerk_id)
        sub = make_subscription(
            db,
            user.clerk_id,
            org_id=org.id,
            tier="firm",
            stripe_subscription_id="sub_addon_test",
        )

        subscription_data = {
            "id": "sub_addon_test",
            "customer": "cus_test",
            "status": "active",
            "items": {"data": [
                {
                    "price": {"id": "price_firm_base", "recurring": {"interval": "month"}},
                    "quantity": 1,
                },
                {
                    "price": {"id": "price_addon_seat", "recurring": {"interval": "month"}},
                    "quantity": 3,
                },
            ]},
            "metadata": {"user_id": user.clerk_id},
        }

        def mock_tier(price_id):
            if price_id == "price_addon_seat":
                return "firm_addon_seat"
            return "firm"

        with patch("app.services.stripe_service._tier_for_price", side_effect=mock_tier):
            with patch("app.services.stripe_service.is_legacy_firm_price", return_value=False):
                stripe_service.handle_subscription_updated(db, subscription_data)

        db.refresh(sub)
        assert sub.addon_seats == 3

    def test_unknown_subscription_id_does_not_error(self, db: Session):
        """Unknown stripe_subscription_id logs warning but does not raise."""
        subscription_data = {
            "id": "sub_does_not_exist",
            "status": "active",
            "items": {"data": []},
        }

        # Should not raise
        stripe_service.handle_subscription_updated(db, subscription_data)

    @patch("app.services.stripe_service.update_org_seat_limit")
    def test_legacy_firm_price_zeroes_addon_seats(self, mock_org_seats, db: Session):
        """Legacy firm price detection should zero out addon seats."""
        user = make_user(db)
        org = make_org(db, owner_user_id=user.clerk_id)
        sub = make_subscription(
            db,
            user.clerk_id,
            org_id=org.id,
            tier="firm",
            stripe_subscription_id="sub_legacy_test",
            addon_seats=5,
        )

        subscription_data = {
            "id": "sub_legacy_test",
            "customer": "cus_test",
            "status": "active",
            "items": {"data": [
                {
                    "price": {"id": "price_legacy_firm", "recurring": {"interval": "month"}},
                    "quantity": 1,
                },
                {
                    "price": {"id": "price_addon_seat", "recurring": {"interval": "month"}},
                    "quantity": 3,
                },
            ]},
            "metadata": {"user_id": user.clerk_id},
        }

        def mock_tier(price_id):
            if price_id == "price_addon_seat":
                return "firm_addon_seat"
            return "firm"

        with patch("app.services.stripe_service._tier_for_price", side_effect=mock_tier):
            with patch("app.services.stripe_service.is_legacy_firm_price", return_value=True):
                stripe_service.handle_subscription_updated(db, subscription_data)

        db.refresh(sub)
        assert sub.addon_seats == 0


# ---------------------------------------------------------------------------
# handle_subscription_deleted
# ---------------------------------------------------------------------------


class TestHandleSubscriptionDeleted:
    @patch("app.services.stripe_service.notify")
    @patch("app.services.stripe_service.update_org_seat_limit")
    def test_downgrades_to_free(self, mock_org_seats, mock_notify, db: Session):
        """Cancellation should downgrade to free tier and reset usage."""
        user = make_user(db)
        org = make_org(db, owner_user_id=user.clerk_id)
        sub = make_subscription(
            db,
            user.clerk_id,
            org_id=org.id,
            tier="professional",
            stripe_subscription_id="sub_cancel_test",
            stripe_status="active",
        )
        sub.strategic_queries_used = 50
        db.flush()

        subscription_data = {"id": "sub_cancel_test", "customer": "cus_test"}

        stripe_service.handle_subscription_deleted(db, subscription_data)

        db.refresh(sub)
        assert sub.tier == "free"
        assert sub.stripe_status == "canceled"
        assert sub.strategic_queries_used == 0
        assert sub.strategic_queries_limit == TIER_DEFAULTS["free"]["strategic_queries_limit"]
        assert sub.payment_status is None

    @patch("app.services.stripe_service.notify")
    def test_unknown_subscription_id_does_not_error(self, mock_notify, db: Session):
        """Deleting unknown subscription ID logs but does not raise."""
        subscription_data = {"id": "sub_ghost", "customer": "cus_test"}

        # Should not raise
        stripe_service.handle_subscription_deleted(db, subscription_data)


# ---------------------------------------------------------------------------
# handle_payment_failed
# ---------------------------------------------------------------------------


class TestHandlePaymentFailed:
    @patch("app.services.stripe_service.notify")
    def test_marks_subscription_past_due(self, mock_notify, db: Session):
        """Payment failure marks subscription as past_due/failed."""
        user = make_user(db)
        org = make_org(db, owner_user_id=user.clerk_id)
        sub = make_subscription(
            db,
            user.clerk_id,
            org_id=org.id,
            tier="starter",
            stripe_subscription_id="sub_payment_test",
            stripe_status="active",
        )

        invoice_data = make_invoice_data(subscription_id="sub_payment_test")

        stripe_service.handle_payment_failed(db, invoice_data)

        db.refresh(sub)
        assert sub.stripe_status == "past_due"
        assert sub.payment_status == "failed"

    def test_missing_subscription_id_does_nothing(self, db: Session):
        """Invoice with no subscription ID should return early."""
        invoice_data = {"subscription": None, "customer": "cus_test"}

        # Should not raise
        stripe_service.handle_payment_failed(db, invoice_data)

    @patch("app.services.stripe_service.notify")
    def test_unknown_subscription_does_nothing(self, mock_notify, db: Session):
        """Unknown subscription ID on invoice should not raise."""
        invoice_data = make_invoice_data(subscription_id="sub_nonexistent")

        # Should not raise
        stripe_service.handle_payment_failed(db, invoice_data)


# ---------------------------------------------------------------------------
# Idempotency — ProcessedWebhookEvent
# ---------------------------------------------------------------------------


class TestWebhookIdempotency:
    def test_duplicate_event_id_detected(self, db: Session):
        """Same Stripe event ID should be detectable for idempotency."""
        event_id = f"evt_{uuid.uuid4().hex[:24]}"

        # First time: no record exists
        existing = db.query(ProcessedWebhookEvent).filter(
            ProcessedWebhookEvent.id == event_id
        ).first()
        assert existing is None

        # Record the event
        record = ProcessedWebhookEvent(
            id=event_id,
            processed_at=datetime.now(timezone.utc),
        )
        db.add(record)
        db.flush()

        # Second time: record exists — webhook should be skipped
        existing = db.query(ProcessedWebhookEvent).filter(
            ProcessedWebhookEvent.id == event_id
        ).first()
        assert existing is not None
        assert existing.id == event_id

    def test_different_events_not_confused(self, db: Session):
        """Different event IDs should not interfere with each other."""
        id_a = f"evt_{uuid.uuid4().hex[:24]}"
        id_b = f"evt_{uuid.uuid4().hex[:24]}"

        db.add(ProcessedWebhookEvent(id=id_a, processed_at=datetime.now(timezone.utc)))
        db.flush()

        # id_b should not be found
        existing = db.query(ProcessedWebhookEvent).filter(
            ProcessedWebhookEvent.id == id_b
        ).first()
        assert existing is None


# ---------------------------------------------------------------------------
# _tier_for_price — price ID to tier mapping
# ---------------------------------------------------------------------------


class TestTierForPrice:
    @patch("app.services.stripe_service.get_settings")
    def test_maps_known_price_ids(self, mock_settings):
        """Known price IDs map to correct tiers."""
        settings = MagicMock()
        settings.stripe_price_starter = "price_starter_m"
        settings.stripe_price_starter_annual = "price_starter_a"
        settings.stripe_price_professional = "price_pro_m"
        settings.stripe_price_professional_annual = "price_pro_a"
        settings.stripe_price_firm = "price_firm_legacy_m"
        settings.stripe_price_firm_annual = "price_firm_legacy_a"
        settings.stripe_price_firm_hybrid_monthly = "price_firm_hybrid_m"
        settings.stripe_price_firm_hybrid_annual = "price_firm_hybrid_a"
        settings.stripe_price_addon_seat_monthly = "price_addon_m"
        settings.stripe_price_addon_seat_annual = "price_addon_a"
        mock_settings.return_value = settings

        assert stripe_service._tier_for_price("price_starter_m") == "starter"
        assert stripe_service._tier_for_price("price_pro_m") == "professional"
        assert stripe_service._tier_for_price("price_firm_hybrid_m") == "firm"
        assert stripe_service._tier_for_price("price_addon_m") == "firm_addon_seat"

    @patch("app.services.stripe_service.get_settings")
    def test_unknown_price_returns_free(self, mock_settings):
        """Unknown price ID defaults to free tier."""
        settings = MagicMock()
        settings.stripe_price_starter = ""
        settings.stripe_price_starter_annual = ""
        settings.stripe_price_professional = ""
        settings.stripe_price_professional_annual = ""
        settings.stripe_price_firm = ""
        settings.stripe_price_firm_annual = ""
        settings.stripe_price_firm_hybrid_monthly = ""
        settings.stripe_price_firm_hybrid_annual = ""
        settings.stripe_price_addon_seat_monthly = ""
        settings.stripe_price_addon_seat_annual = ""
        mock_settings.return_value = settings

        assert stripe_service._tier_for_price("price_totally_unknown") == "free"


# ---------------------------------------------------------------------------
# _lookup_sub — org_id first, user_id fallback
# ---------------------------------------------------------------------------


class TestLookupSub:
    def test_finds_by_org_id(self, db: Session):
        """Should find subscription by org_id."""
        user = make_user(db)
        org = make_org(db, owner_user_id=user.clerk_id)
        sub = make_subscription(db, user.clerk_id, org_id=org.id, tier="starter")

        result = stripe_service._lookup_sub(db, org_id=str(org.id), user_id=user.clerk_id)
        assert result is not None
        assert result.id == sub.id

    def test_falls_back_to_user_id(self, db: Session):
        """When org_id is None, should find by user_id."""
        user = make_user(db)
        sub = make_subscription(db, user.clerk_id, tier="starter")

        result = stripe_service._lookup_sub(db, org_id=None, user_id=user.clerk_id)
        assert result is not None
        assert result.id == sub.id

    def test_returns_none_when_not_found(self, db: Session):
        """No matching subscription returns None."""
        result = stripe_service._lookup_sub(db, org_id=None, user_id="user_nonexistent")
        assert result is None

"""
Tests for Resend webhook handling (route + service).

17 tests total:
- 5 route-level (signature verification)
- 10 service-level (event handlers)
- 2 idempotency
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy.orm import Session

from app.models import *  # noqa: F401, F403
from app.models.client_communication import ClientCommunication
from app.models.journal_entry import JournalEntry
from app.services import resend_webhook_service as rws
from tests.conftest import make_user, make_org, make_client


def _make_comm(
    db: Session,
    user,
    client,
    *,
    resend_message_id: str = "msg_abc123",
    status: str = "sent",
    metadata_: dict | None = None,
) -> ClientCommunication:
    """Create a ClientCommunication row."""
    comm = ClientCommunication(
        id=uuid.uuid4(),
        client_id=client.id,
        user_id=user.clerk_id,
        communication_type="email",
        subject="Test email",
        body_html="<p>Hello</p>",
        body_text="Hello",
        recipient_email=client.email,
        status=status,
        resend_message_id=resend_message_id,
        metadata_=metadata_,
    )
    db.add(comm)
    db.flush()
    return comm


# ── Route-level tests ──────────────────────────────────────────────────────


class TestResendWebhookRoute:
    """Route-level tests — signature verification and error handling."""

    @patch("app.api.resend_webhooks.get_settings")
    def test_returns_503_when_webhook_secret_not_configured(self, mock_settings):
        """Missing webhook secret → 503."""
        from fastapi.testclient import TestClient
        from app.api.resend_webhooks import router
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(router)

        settings = MagicMock()
        settings.resend_webhook_secret = None
        mock_settings.return_value = settings

        client = TestClient(app)
        resp = client.post("/resend", json={"type": "email.delivered"})
        assert resp.status_code == 503

    @patch("app.api.resend_webhooks.get_settings")
    @patch("resend.Webhooks.verify", side_effect=ValueError("bad sig"))
    def test_returns_400_on_invalid_signature(self, mock_verify, mock_settings):
        """Invalid Svix signature → 400."""
        from fastapi.testclient import TestClient
        from app.api.resend_webhooks import router
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(router)

        settings = MagicMock()
        settings.resend_webhook_secret = "whsec_test123"
        mock_settings.return_value = settings

        client = TestClient(app)
        resp = client.post(
            "/resend",
            json={"type": "email.delivered"},
            headers={
                "svix-id": "evt_1",
                "svix-timestamp": "1234567890",
                "svix-signature": "v1,bad",
            },
        )
        assert resp.status_code == 400

    @patch("app.api.resend_webhooks.get_settings")
    @patch("resend.Webhooks.verify")
    @patch("app.api.resend_webhooks.handle_event")
    def test_returns_200_on_valid_event(self, mock_handle, mock_verify, mock_settings):
        """Valid signature + successful processing → 200."""
        from fastapi.testclient import TestClient
        from app.api.resend_webhooks import router
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(router)

        settings = MagicMock()
        settings.resend_webhook_secret = "whsec_test123"
        mock_settings.return_value = settings
        mock_verify.return_value = {
            "type": "email.delivered",
            "data": {"email_id": "msg_abc"},
        }

        client = TestClient(app)
        resp = client.post(
            "/resend",
            json={"type": "email.delivered"},
            headers={
                "svix-id": "evt_1",
                "svix-timestamp": "1234567890",
                "svix-signature": "v1,good",
            },
        )
        assert resp.status_code == 200
        assert resp.json() == {"received": True}

    @patch("app.api.resend_webhooks.get_settings")
    @patch("resend.Webhooks.verify")
    @patch("app.api.resend_webhooks.handle_event", side_effect=Exception("boom"))
    def test_returns_500_on_processing_error(self, mock_handle, mock_verify, mock_settings):
        """Processing error → 500 so Resend retries."""
        from fastapi.testclient import TestClient
        from app.api.resend_webhooks import router
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(router)

        settings = MagicMock()
        settings.resend_webhook_secret = "whsec_test123"
        mock_settings.return_value = settings
        mock_verify.return_value = {
            "type": "email.delivered",
            "data": {"email_id": "msg_abc"},
        }

        client = TestClient(app)
        resp = client.post(
            "/resend",
            json={"type": "email.delivered"},
            headers={
                "svix-id": "evt_1",
                "svix-timestamp": "1234567890",
                "svix-signature": "v1,good",
            },
        )
        assert resp.status_code == 500

    @patch("app.api.resend_webhooks.get_settings")
    @patch("resend.Webhooks.verify")
    @patch("app.api.resend_webhooks.handle_event")
    def test_passes_svix_id_as_event_id(self, mock_handle, mock_verify, mock_settings):
        """event_id passed to handle_event matches svix-id header."""
        from fastapi.testclient import TestClient
        from app.api.resend_webhooks import router
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(router)

        settings = MagicMock()
        settings.resend_webhook_secret = "whsec_test123"
        mock_settings.return_value = settings
        mock_verify.return_value = {
            "type": "email.delivered",
            "data": {"email_id": "msg_abc"},
        }

        client = TestClient(app)
        client.post(
            "/resend",
            json={},
            headers={
                "svix-id": "evt_unique_42",
                "svix-timestamp": "1234567890",
                "svix-signature": "v1,good",
            },
        )
        assert mock_handle.called
        call_args = mock_handle.call_args
        # event_id is the 4th positional arg (db, event_type, event_data, event_id)
        assert call_args[0][3] == "evt_unique_42"


# ── Service-level tests ────────────────────────────────────────────────────


class TestResendWebhookServiceDelivered:
    """Tests for email.delivered event handling."""

    def test_delivered_sets_delivered_at_and_status(self, db: Session):
        user = make_user(db)
        org = make_org(db, owner_user_id=user.clerk_id)
        client = make_client(db, user, org=org)
        comm = _make_comm(db, user, client)

        rws.handle_event(db, "email.delivered", {"email_id": "msg_abc123"}, "evt_1")

        db.flush()
        assert comm.delivered_at is not None
        assert comm.status == "delivered"

    def test_delivered_does_not_overwrite_failed_status(self, db: Session):
        """A delivered event for a previously-failed comm stays failed? No — delivered wins for 'sent' only."""
        user = make_user(db)
        org = make_org(db, owner_user_id=user.clerk_id)
        client = make_client(db, user, org=org)
        comm = _make_comm(db, user, client, status="failed")

        rws.handle_event(db, "email.delivered", {"email_id": "msg_abc123"}, "evt_1")

        db.flush()
        assert comm.delivered_at is not None
        # Status only upgrades from 'sent' → 'delivered'
        assert comm.status == "failed"

    def test_delivered_appends_webhook_event_to_metadata(self, db: Session):
        user = make_user(db)
        org = make_org(db, owner_user_id=user.clerk_id)
        client = make_client(db, user, org=org)
        comm = _make_comm(db, user, client)

        rws.handle_event(db, "email.delivered", {"email_id": "msg_abc123"}, "evt_1")

        db.flush()
        events = comm.metadata_["webhook_events"]
        assert len(events) == 1
        assert events[0]["event_id"] == "evt_1"
        assert events[0]["event_type"] == "email.delivered"

    def test_delivered_no_journal_entry(self, db: Session):
        """Delivered events don't create journal entries."""
        user = make_user(db)
        org = make_org(db, owner_user_id=user.clerk_id)
        client = make_client(db, user, org=org)
        _make_comm(db, user, client)

        rws.handle_event(db, "email.delivered", {"email_id": "msg_abc123"}, "evt_1")
        db.flush()

        entries = db.query(JournalEntry).filter(JournalEntry.client_id == client.id).all()
        assert len(entries) == 0


class TestResendWebhookServiceBounced:
    """Tests for email.bounced event handling."""

    def test_bounced_sets_bounced_at_and_status(self, db: Session):
        user = make_user(db)
        org = make_org(db, owner_user_id=user.clerk_id)
        client = make_client(db, user, org=org)
        comm = _make_comm(db, user, client)

        rws.handle_event(db, "email.bounced", {"email_id": "msg_abc123"}, "evt_2")

        db.flush()
        assert comm.bounced_at is not None
        assert comm.status == "bounced"

    def test_bounced_creates_journal_entry(self, db: Session):
        user = make_user(db)
        org = make_org(db, owner_user_id=user.clerk_id)
        client = make_client(db, user, org=org)
        _make_comm(db, user, client)

        rws.handle_event(db, "email.bounced", {"email_id": "msg_abc123"}, "evt_2")
        db.flush()

        entries = db.query(JournalEntry).filter(JournalEntry.client_id == client.id).all()
        assert len(entries) == 1
        assert "bounced" in entries[0].title.lower()


class TestResendWebhookServiceComplained:
    """Tests for email.complained event handling."""

    def test_complained_sets_status(self, db: Session):
        user = make_user(db)
        org = make_org(db, owner_user_id=user.clerk_id)
        client = make_client(db, user, org=org)
        comm = _make_comm(db, user, client)

        rws.handle_event(db, "email.complained", {"email_id": "msg_abc123"}, "evt_3")

        db.flush()
        assert comm.status == "complained"

    def test_complained_creates_journal_entry(self, db: Session):
        user = make_user(db)
        org = make_org(db, owner_user_id=user.clerk_id)
        client = make_client(db, user, org=org)
        _make_comm(db, user, client)

        rws.handle_event(db, "email.complained", {"email_id": "msg_abc123"}, "evt_3")
        db.flush()

        entries = db.query(JournalEntry).filter(JournalEntry.client_id == client.id).all()
        assert len(entries) == 1
        assert "spam" in entries[0].title.lower() or "complaint" in entries[0].title.lower()


class TestResendWebhookServiceEdgeCases:
    """Edge case tests."""

    def test_unknown_resend_message_id_is_noop(self, db: Session):
        """Event for unknown message_id does nothing."""
        # No comm in DB
        rws.handle_event(db, "email.delivered", {"email_id": "msg_unknown"}, "evt_x")
        # No exception raised

    def test_missing_email_id_is_noop(self, db: Session):
        """Event with no email_id is ignored."""
        rws.handle_event(db, "email.delivered", {}, "evt_y")

    def test_unhandled_event_type_is_noop(self, db: Session):
        """Unrecognized event type is ignored (no metadata update)."""
        user = make_user(db)
        org = make_org(db, owner_user_id=user.clerk_id)
        client = make_client(db, user, org=org)
        comm = _make_comm(db, user, client)

        rws.handle_event(db, "email.clicked", {"email_id": "msg_abc123"}, "evt_z")

        db.flush()
        # No webhook_events added for unhandled type
        assert comm.metadata_ is None or "webhook_events" not in (comm.metadata_ or {})


# ── Idempotency tests ──────────────────────────────────────────────────────


class TestResendWebhookIdempotency:
    """Idempotency via svix-id dedup in metadata.webhook_events."""

    def test_duplicate_event_id_is_skipped(self, db: Session):
        """Same event_id processed twice → second call is a no-op."""
        user = make_user(db)
        org = make_org(db, owner_user_id=user.clerk_id)
        client = make_client(db, user, org=org)
        comm = _make_comm(db, user, client, metadata_={
            "webhook_events": [
                {"event_id": "evt_dup", "event_type": "email.delivered", "processed_at": "2026-05-12T00:00:00+00:00"}
            ]
        })

        rws.handle_event(db, "email.bounced", {"email_id": "msg_abc123"}, "evt_dup")

        db.flush()
        # Status should NOT change to bounced — event was skipped
        assert comm.status == "sent"
        assert len(comm.metadata_["webhook_events"]) == 1

    def test_different_event_ids_both_processed(self, db: Session):
        """Two different event_ids for the same comm are both processed."""
        user = make_user(db)
        org = make_org(db, owner_user_id=user.clerk_id)
        client = make_client(db, user, org=org)
        comm = _make_comm(db, user, client)

        rws.handle_event(db, "email.delivered", {"email_id": "msg_abc123"}, "evt_a")
        rws.handle_event(db, "email.bounced", {"email_id": "msg_abc123"}, "evt_b")

        db.flush()
        assert comm.status == "bounced"
        assert len(comm.metadata_["webhook_events"]) == 2

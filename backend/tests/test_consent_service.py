"""
Tests for IRC §7216 consent service — Priority 1 (compliance).

Covers all three consent tiers, consent recording, tax document upload triggers,
preparer status changes, advisory acknowledgment, consent expiration, and
e-signature token validation/completion.
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.client_consent import ClientConsent
from app.services import consent_service
from tests.conftest import make_client, make_consent, make_org, make_user


# ---------------------------------------------------------------------------
# get_consent_status
# ---------------------------------------------------------------------------


class TestGetConsentStatus:
    def test_no_consent_records_returns_defaults(self, db: Session):
        user = make_user(db)
        org = make_org(db, owner_user_id=user.clerk_id)
        client = make_client(db, user, org=org, consent_status="not_required")

        result = consent_service.get_consent_status(client.id, user.clerk_id, db)

        assert result["status"] is None  # no consent record yet
        assert result["is_expired"] is False

    def test_obtained_consent_not_expired(self, db: Session):
        user = make_user(db)
        org = make_org(db, owner_user_id=user.clerk_id)
        client = make_client(db, user, org=org, consent_status="obtained")
        make_consent(
            db,
            client,
            user.clerk_id,
            status="obtained",
            consent_tier="full_7216",
            expiration_date=datetime.now(timezone.utc) + timedelta(days=200),
        )

        result = consent_service.get_consent_status(client.id, user.clerk_id, db)

        assert result["status"] == "obtained"
        assert result["is_expired"] is False
        assert result["days_until_expiry"] is not None
        assert result["days_until_expiry"] > 0

    def test_expired_consent_detected(self, db: Session):
        user = make_user(db)
        org = make_org(db, owner_user_id=user.clerk_id)
        client = make_client(db, user, org=org, consent_status="obtained")
        make_consent(
            db,
            client,
            user.clerk_id,
            status="obtained",
            consent_tier="full_7216",
            expiration_date=datetime.now(timezone.utc) - timedelta(days=10),
        )

        result = consent_service.get_consent_status(client.id, user.clerk_id, db)

        assert result["is_expired"] is True


# ---------------------------------------------------------------------------
# check_tax_document_upload — consent trigger on tax doc upload
# ---------------------------------------------------------------------------


class TestCheckTaxDocumentUpload:
    def test_non_tax_document_does_not_require_consent(self, db: Session):
        user = make_user(db)
        org = make_org(db, owner_user_id=user.clerk_id)
        client = make_client(db, user, org=org, consent_status="not_required")

        result = consent_service.check_tax_document_upload(
            client.id, "engagement_letter", db
        )

        assert result["needs_consent"] is False

    def test_tax_return_triggers_consent_for_preparer(self, db: Session):
        """Tax doc upload by a tax preparer must require full §7216 consent."""
        user = make_user(db)
        org = make_org(db, owner_user_id=user.clerk_id)
        client = make_client(
            db, user, org=org,
            consent_status="not_required",
            is_tax_preparer=True,
            has_tax_documents=False,
        )

        result = consent_service.check_tax_document_upload(
            client.id, "tax_return", db
        )

        assert result["needs_consent"] is True
        # Client should now be marked as having tax documents
        db.refresh(client)
        assert client.has_tax_documents is True
        assert client.consent_status in ("pending", "determination_needed")

    def test_tax_return_triggers_advisory_acknowledgment_for_non_preparer(self, db: Session):
        """Non-preparer uploading tax docs should get advisory acknowledgment flow."""
        user = make_user(db)
        org = make_org(db, owner_user_id=user.clerk_id)
        client = make_client(
            db, user, org=org,
            consent_status="not_required",
            is_tax_preparer=False,
            has_tax_documents=False,
        )

        result = consent_service.check_tax_document_upload(
            client.id, "tax_return", db
        )

        assert result["needs_consent"] is True
        db.refresh(client)
        assert client.has_tax_documents is True
        assert client.consent_status == "advisory_acknowledgment_needed"

    def test_all_tax_doc_types_trigger_consent(self, db: Session):
        """Every document type in TAX_DOCUMENT_TYPES must trigger consent."""
        user = make_user(db)
        org = make_org(db, owner_user_id=user.clerk_id)

        for doc_type in ("tax_return", "w2", "k1", "1099", "1040"):
            client = make_client(
                db, user, org=org,
                name=f"Client-{doc_type}",
                consent_status="not_required",
                is_tax_preparer=True,
                has_tax_documents=False,
            )
            result = consent_service.check_tax_document_upload(
                client.id, doc_type, db
            )
            assert result["needs_consent"] is True, f"{doc_type} should trigger consent"

    def test_already_obtained_consent_does_not_block(self, db: Session):
        """If consent is already obtained, uploading more tax docs is fine."""
        user = make_user(db)
        org = make_org(db, owner_user_id=user.clerk_id)
        client = make_client(
            db, user, org=org,
            consent_status="obtained",
            is_tax_preparer=True,
            has_tax_documents=True,
        )

        result = consent_service.check_tax_document_upload(
            client.id, "tax_return", db
        )

        # Should not need new consent — already obtained
        assert result["needs_consent"] is False

    def test_null_document_type_does_not_require_consent(self, db: Session):
        user = make_user(db)
        org = make_org(db, owner_user_id=user.clerk_id)
        client = make_client(db, user, org=org, consent_status="not_required")

        result = consent_service.check_tax_document_upload(client.id, None, db)

        assert result["needs_consent"] is False


# ---------------------------------------------------------------------------
# set_preparer_status — toggling tax preparer flag
# ---------------------------------------------------------------------------


class TestSetPreparerStatus:
    def test_set_as_preparer_with_tax_docs_triggers_consent(self, db: Session):
        """When a client with tax docs is marked as a preparer, consent must be required."""
        user = make_user(db)
        org = make_org(db, owner_user_id=user.clerk_id)
        client = make_client(
            db, user, org=org,
            consent_status="not_required",
            is_tax_preparer=False,
            has_tax_documents=True,
        )

        consent_service.set_preparer_status(client.id, True, user.clerk_id, db)

        db.refresh(client)
        assert client.is_tax_preparer is True
        assert client.consent_status == "pending"

    def test_set_as_non_preparer_with_tax_docs_needs_advisory(self, db: Session):
        """Non-preparer with tax docs should need advisory acknowledgment."""
        user = make_user(db)
        org = make_org(db, owner_user_id=user.clerk_id)
        client = make_client(
            db, user, org=org,
            consent_status="pending",
            is_tax_preparer=True,
            has_tax_documents=True,
        )

        consent_service.set_preparer_status(client.id, False, user.clerk_id, db)

        db.refresh(client)
        assert client.is_tax_preparer is False
        assert client.consent_status == "advisory_acknowledgment_needed"


# ---------------------------------------------------------------------------
# record_advisory_acknowledgment — AICPA tier
# ---------------------------------------------------------------------------


class TestRecordAdvisoryAcknowledgment:
    def test_records_acknowledgment(self, db: Session):
        user = make_user(db)
        org = make_org(db, owner_user_id=user.clerk_id)
        client = make_client(
            db, user, org=org,
            consent_status="advisory_acknowledgment_needed",
            is_tax_preparer=False,
            has_tax_documents=True,
        )

        consent_service.record_advisory_acknowledgment(
            client.id, user.clerk_id, db
        )

        db.refresh(client)
        assert client.consent_status == "acknowledged"
        assert client.data_handling_acknowledged is True
        assert client.data_handling_acknowledged_at is not None

        # A consent record should be created with aicpa tier
        record = (
            db.query(ClientConsent)
            .filter(
                ClientConsent.client_id == client.id,
                ClientConsent.user_id == user.clerk_id,
            )
            .first()
        )
        assert record is not None
        assert record.consent_tier == "aicpa_acknowledgment"
        assert record.status == "obtained"


# ---------------------------------------------------------------------------
# create_or_update_consent — consent recording
# ---------------------------------------------------------------------------


class TestCreateOrUpdateConsent:
    def test_creates_new_consent_record(self, db: Session):
        user = make_user(db)
        org = make_org(db, owner_user_id=user.clerk_id)
        client = make_client(db, user, org=org)

        result = consent_service.create_or_update_consent(
            client.id,
            user.clerk_id,
            db,
            consent_type="full_7216",
            status="obtained",
        )

        assert result is not None
        assert result.consent_type == "full_7216"
        assert result.status == "obtained"

    def test_obtained_consent_auto_sets_expiration(self, db: Session):
        """When consent is obtained with a consent_date, expiration should be set to 1 year."""
        user = make_user(db)
        org = make_org(db, owner_user_id=user.clerk_id)
        client = make_client(db, user, org=org)
        now = datetime.now(timezone.utc)

        result = consent_service.create_or_update_consent(
            client.id,
            user.clerk_id,
            db,
            consent_type="full_7216",
            status="obtained",
            consent_date=now,
        )

        assert result.expiration_date is not None
        # Should be approximately 1 year from now
        # SQLite may strip timezone info, so handle both naive and aware
        exp = result.expiration_date
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        delta = exp - now
        assert 364 <= delta.days <= 366


# ---------------------------------------------------------------------------
# get_expiring_consents
# ---------------------------------------------------------------------------


class TestGetExpiringConsents:
    def test_finds_consent_expiring_within_window(self, db: Session):
        user = make_user(db)
        org = make_org(db, owner_user_id=user.clerk_id)
        client = make_client(db, user, org=org, consent_status="obtained")
        make_consent(
            db,
            client,
            user.clerk_id,
            status="obtained",
            consent_tier="full_7216",
            expiration_date=datetime.now(timezone.utc) + timedelta(days=15),
        )

        results = consent_service.get_expiring_consents(user.clerk_id, db, days_ahead=30)

        assert len(results) >= 1

    def test_does_not_find_consent_expiring_outside_window(self, db: Session):
        user = make_user(db)
        org = make_org(db, owner_user_id=user.clerk_id)
        client = make_client(db, user, org=org, consent_status="obtained")
        make_consent(
            db,
            client,
            user.clerk_id,
            status="obtained",
            consent_tier="full_7216",
            expiration_date=datetime.now(timezone.utc) + timedelta(days=200),
        )

        results = consent_service.get_expiring_consents(user.clerk_id, db, days_ahead=30)

        # Should not include consents expiring far in the future
        client_ids = [r.client_id for r in results]
        assert client.id not in client_ids


# ---------------------------------------------------------------------------
# validate_signing_token — e-signature token validation
# ---------------------------------------------------------------------------


class TestValidateSigningToken:
    def test_valid_token_returns_record(self, db: Session):
        user = make_user(db)
        org = make_org(db, owner_user_id=user.clerk_id)
        client = make_client(db, user, org=org)
        consent = make_consent(
            db,
            client,
            user.clerk_id,
            signing_token="valid-token-123",
            signing_token_expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )

        result = consent_service.validate_signing_token("valid-token-123", db)

        assert result is not None
        assert result.id == consent.id

    def test_expired_token_returns_none(self, db: Session):
        user = make_user(db)
        org = make_org(db, owner_user_id=user.clerk_id)
        client = make_client(db, user, org=org)
        make_consent(
            db,
            client,
            user.clerk_id,
            signing_token="expired-token",
            signing_token_expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        )

        result = consent_service.validate_signing_token("expired-token", db)

        assert result is None

    def test_already_signed_token_returns_none(self, db: Session):
        user = make_user(db)
        org = make_org(db, owner_user_id=user.clerk_id)
        client = make_client(db, user, org=org)
        consent = make_consent(
            db,
            client,
            user.clerk_id,
            signing_token="signed-token",
            signing_token_expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        # Mark as already signed
        consent.signed_at = datetime.now(timezone.utc)
        db.flush()

        result = consent_service.validate_signing_token("signed-token", db)

        assert result is None

    def test_nonexistent_token_returns_none(self, db: Session):
        result = consent_service.validate_signing_token("does-not-exist", db)
        assert result is None


# ---------------------------------------------------------------------------
# complete_signing — e-signature completion
# ---------------------------------------------------------------------------


class TestCompleteSigning:
    @patch("app.services.consent_service.generate_signed_consent_pdf")
    @patch("app.services.notification_service.send_notification", side_effect=Exception("skip"))
    def test_complete_signing_updates_status(self, mock_notify, mock_pdf, db: Session):
        mock_pdf.return_value = (b"fake-pdf", "https://storage/signed.pdf")

        user = make_user(db)
        org = make_org(db, owner_user_id=user.clerk_id)
        client = make_client(db, user, org=org, consent_status="pending")
        make_consent(
            db,
            client,
            user.clerk_id,
            status="sent",
            signing_token="sign-me-token",
            signing_token_expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )

        result = consent_service.complete_signing(
            token="sign-me-token",
            typed_name="John Doe",
            ip_address="192.168.1.1",
            user_agent="TestAgent/1.0",
            db=db,
        )

        assert result.status == "obtained"
        assert result.signer_typed_name == "John Doe"
        assert result.signer_ip_address == "192.168.1.1"
        assert result.signed_at is not None
        assert result.expiration_date is not None

        # Client-level status should be updated
        db.refresh(client)
        assert client.consent_status == "obtained"

    def test_complete_signing_rejects_invalid_token(self, db: Session):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            consent_service.complete_signing(
                token="bogus-token",
                typed_name="Hacker",
                ip_address="10.0.0.1",
                user_agent="BadBot",
                db=db,
            )

        assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# Consent cannot be bypassed — uploading tax docs ALWAYS requires consent
# ---------------------------------------------------------------------------


class TestConsentCannotBeBypassed:
    def test_tax_doc_upload_with_undetermined_preparer_triggers_determination(self, db: Session):
        """When is_tax_preparer is None (undetermined), uploading tax docs must still trigger consent."""
        user = make_user(db)
        org = make_org(db, owner_user_id=user.clerk_id)
        client = make_client(
            db, user, org=org,
            consent_status="not_required",
            is_tax_preparer=None,
            has_tax_documents=False,
        )

        result = consent_service.check_tax_document_upload(
            client.id, "1040", db
        )

        assert result["needs_consent"] is True
        db.refresh(client)
        assert client.consent_status == "determination_needed"

    def test_consent_not_required_for_non_tax_docs_even_with_preparer(self, db: Session):
        """Non-tax documents should never require consent regardless of preparer status."""
        user = make_user(db)
        org = make_org(db, owner_user_id=user.clerk_id)
        client = make_client(
            db, user, org=org,
            consent_status="not_required",
            is_tax_preparer=True,
        )

        for doc_type in ("meeting_notes", "engagement_letter", "financial_statement", "other"):
            result = consent_service.check_tax_document_upload(
                client.id, doc_type, db
            )
            assert result["needs_consent"] is False, f"{doc_type} should NOT require consent"

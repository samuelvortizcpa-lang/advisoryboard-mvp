"""
Security regression tests — IRC §7216 consent enforcement (M3).

Verifies that AI processing is blocked when consent is missing, pending,
or expired on clients with tax documents, and allowed when consent is valid.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from unittest.mock import patch

from app.api.rag import _require_consent_for_ai
from app.services.auth_context import AuthContext
from tests.conftest import make_client, make_consent, make_org, make_user


def _auth(user_id: str, org_id: uuid.UUID) -> AuthContext:
    return AuthContext(user_id=user_id, org_id=org_id, org_role="admin", is_personal_org=False)


# ---------------------------------------------------------------------------
# 1. AI blocked when tax docs exist but consent is pending
# ---------------------------------------------------------------------------


def test_ai_blocked_pending_consent(db):
    user = make_user(db)
    org = make_org(db, owner_user_id=user.clerk_id)
    client = make_client(
        db, user, org=org,
        has_tax_documents=True,
        consent_status="pending",
    )
    auth = _auth(user.clerk_id, org.id)

    with pytest.raises(HTTPException) as exc_info:
        _require_consent_for_ai(client, auth, db)
    assert exc_info.value.status_code == 403
    assert "§7216" in exc_info.value.detail


# ---------------------------------------------------------------------------
# 2. AI blocked when consent status is "determination_needed"
# ---------------------------------------------------------------------------


def test_ai_blocked_determination_needed(db):
    user = make_user(db)
    org = make_org(db, owner_user_id=user.clerk_id)
    client = make_client(
        db, user, org=org,
        has_tax_documents=True,
        consent_status="determination_needed",
    )
    auth = _auth(user.clerk_id, org.id)

    with pytest.raises(HTTPException) as exc_info:
        _require_consent_for_ai(client, auth, db)
    assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# 3. AI allowed when consent is "obtained" and not expired
# ---------------------------------------------------------------------------


def test_ai_allowed_with_valid_consent(db):
    user = make_user(db)
    org = make_org(db, owner_user_id=user.clerk_id)
    client = make_client(
        db, user, org=org,
        has_tax_documents=True,
        consent_status="obtained",
    )
    make_consent(
        db, client, user.clerk_id,
        status="obtained",
        expiration_date=datetime.now(timezone.utc) + timedelta(days=365),
    )
    auth = _auth(user.clerk_id, org.id)

    # Should not raise
    _require_consent_for_ai(client, auth, db)


# ---------------------------------------------------------------------------
# 4. AI blocked when consent is expired
# ---------------------------------------------------------------------------


def test_ai_blocked_expired_consent(db):
    user = make_user(db)
    org = make_org(db, owner_user_id=user.clerk_id)
    client = make_client(
        db, user, org=org,
        has_tax_documents=True,
        consent_status="obtained",
    )
    make_consent(
        db, client, user.clerk_id,
        status="obtained",
        expiration_date=datetime.now(timezone.utc) - timedelta(days=1),
    )
    auth = _auth(user.clerk_id, org.id)

    with pytest.raises(HTTPException) as exc_info:
        _require_consent_for_ai(client, auth, db)
    assert exc_info.value.status_code == 403
    assert "expired" in exc_info.value.detail.lower()


# ---------------------------------------------------------------------------
# 5. AI allowed for non-tax clients (no consent needed)
# ---------------------------------------------------------------------------


def test_ai_allowed_no_tax_documents(db):
    user = make_user(db)
    org = make_org(db, owner_user_id=user.clerk_id)
    client = make_client(
        db, user, org=org,
        has_tax_documents=False,
        consent_status="not_required",
    )
    auth = _auth(user.clerk_id, org.id)

    # Should not raise — no tax docs means no consent needed
    _require_consent_for_ai(client, auth, db)


# ---------------------------------------------------------------------------
# 6. AI allowed when consent status is "acknowledged" (advisory tier)
# ---------------------------------------------------------------------------


def test_ai_allowed_acknowledged_consent(db):
    user = make_user(db)
    org = make_org(db, owner_user_id=user.clerk_id)
    client = make_client(
        db, user, org=org,
        has_tax_documents=True,
        consent_status="acknowledged",
    )
    auth = _auth(user.clerk_id, org.id)

    # Should not raise — AICPA acknowledgment is sufficient
    _require_consent_for_ai(client, auth, db)


# ---------------------------------------------------------------------------
# 7. AI blocked when consent status is "sent" (not yet signed)
# ---------------------------------------------------------------------------


def test_ai_blocked_sent_consent(db):
    user = make_user(db)
    org = make_org(db, owner_user_id=user.clerk_id)
    client = make_client(
        db, user, org=org,
        has_tax_documents=True,
        consent_status="sent",
    )
    auth = _auth(user.clerk_id, org.id)

    with pytest.raises(HTTPException) as exc_info:
        _require_consent_for_ai(client, auth, db)
    assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# 8. AI blocked when consent status is "declined"
# ---------------------------------------------------------------------------


def test_ai_blocked_declined_consent(db):
    user = make_user(db)
    org = make_org(db, owner_user_id=user.clerk_id)
    client = make_client(
        db, user, org=org,
        has_tax_documents=True,
        consent_status="declined",
    )
    auth = _auth(user.clerk_id, org.id)

    with pytest.raises(HTTPException) as exc_info:
        _require_consent_for_ai(client, auth, db)
    assert exc_info.value.status_code == 403

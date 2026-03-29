"""
Security regression tests — admin endpoint access control (M1).

Verifies that admin endpoints reject invalid API keys and require
proper authentication via X-Admin-Key header or Clerk JWT.
"""

from unittest.mock import patch

from fastapi.testclient import TestClient

from main import app


client = TestClient(app)


# ---------------------------------------------------------------------------
# 1. Admin endpoint rejects missing auth
# ---------------------------------------------------------------------------


def test_admin_no_auth_returns_403():
    """Admin endpoint with no auth headers returns 403."""
    r = client.get("/api/admin/overview")
    assert r.status_code == 403
    assert "admin" in r.json()["detail"].lower()


# ---------------------------------------------------------------------------
# 2. Admin endpoint rejects wrong API key
# ---------------------------------------------------------------------------


@patch("app.api.admin.get_settings")
def test_admin_wrong_key_returns_403(mock_settings):
    mock_settings.return_value.admin_api_key = "correct-secret-key"
    mock_settings.return_value.admin_user_id = None

    r = client.get(
        "/api/admin/overview",
        headers={"X-Admin-Key": "wrong-key"},
    )
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# 3. Admin endpoint accepts correct API key
# ---------------------------------------------------------------------------


@patch("app.api.admin.get_settings")
def test_admin_correct_key_passes_auth(mock_settings):
    """Correct API key should pass the auth check (endpoint may fail on DB)."""
    mock_settings.return_value.admin_api_key = "correct-secret-key"
    mock_settings.return_value.admin_user_id = None

    # The overview endpoint queries the DB — without a real DB connection,
    # it will fail with 500. But if auth fails, we get 403.
    # We verify auth passes by confirming we don't get 403.
    r = client.get(
        "/api/admin/overview",
        headers={"X-Admin-Key": "correct-secret-key"},
    )
    assert r.status_code != 403


# ---------------------------------------------------------------------------
# 4. Admin key uses constant-time comparison (hmac.compare_digest)
# ---------------------------------------------------------------------------


def test_admin_key_uses_hmac_compare_digest():
    """
    Verify that verify_admin_access uses hmac.compare_digest, not ==.
    This is a static analysis check — we import and inspect the source.
    """
    import inspect
    from app.api.admin import verify_admin_access
    source = inspect.getsource(verify_admin_access)
    assert "hmac.compare_digest" in source
    assert 'api_key ==' not in source

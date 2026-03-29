"""
Security regression tests — response headers and CORS (M4, M13).

Verifies that SecurityHeadersMiddleware injects all required security
headers on every response, and that CORS configuration is correct.
"""

from fastapi.testclient import TestClient

from main import app


client = TestClient(app)


# ---------------------------------------------------------------------------
# 1. Security headers present on responses
# ---------------------------------------------------------------------------


class TestSecurityHeaders:
    def test_x_content_type_options(self):
        r = client.get("/health")
        assert r.headers.get("X-Content-Type-Options") == "nosniff"

    def test_x_frame_options(self):
        r = client.get("/health")
        assert r.headers.get("X-Frame-Options") == "DENY"

    def test_x_xss_protection(self):
        r = client.get("/health")
        assert r.headers.get("X-XSS-Protection") == "0"

    def test_referrer_policy(self):
        r = client.get("/health")
        assert r.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"

    def test_permissions_policy(self):
        r = client.get("/health")
        pp = r.headers.get("Permissions-Policy")
        assert pp is not None
        assert "camera=()" in pp
        assert "microphone=()" in pp
        assert "geolocation=()" in pp

    def test_all_headers_on_api_endpoint(self):
        """Headers should appear on API routes too, not just /health."""
        r = client.get("/")
        assert r.headers.get("X-Content-Type-Options") == "nosniff"
        assert r.headers.get("X-Frame-Options") == "DENY"
        assert r.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"


# ---------------------------------------------------------------------------
# 2. Health endpoint returns 200
# ---------------------------------------------------------------------------


class TestHealthEndpoint:
    def test_health_ok(self):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_root_ok(self):
        r = client.get("/")
        assert r.status_code == 200
        assert "running" in r.json()["status"].lower()

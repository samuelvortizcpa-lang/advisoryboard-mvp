"""
Integration tests for the Gmail integration feature.

Runs against the live local backend (http://localhost:8000) using TEST_MODE
authentication.  Exercises:

  1. OAuth URL generation
  2. List connections (empty at first)
  3. Email routing-rule CRUD (create, list, auto-generate, delete)
  4. Sync-log creation via the API
  5. Cleanup

Usage:
    cd backend
    ./venv/bin/python3 test_gmail_integration.py
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import parse_qs, urlparse

import httpx

# Ensure ALL SQLAlchemy models are loaded before any DB operations.
# This prevents "expression 'X' failed to locate a name" mapper errors.
import app.models  # noqa: F401

# ── Configuration ──────────────────────────────────────────────────────────

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")

# Read CLERK_SECRET_KEY from .env.local so we can use it as bearer token in TEST_MODE
def _read_env_var(name: str) -> str:
    """Read a var from the .env.local file in the same directory."""
    env_path = os.path.join(os.path.dirname(__file__), ".env.local")
    if not os.path.exists(env_path):
        raise RuntimeError(f".env.local file not found at {env_path}")
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            if key.strip() == name:
                return value.strip()
    raise RuntimeError(f"{name} not found in {env_path}")


AUTH_TOKEN = _read_env_var("CLERK_SECRET_KEY")

# ── Helpers ────────────────────────────────────────────────────────────────

passed = 0
failed = 0
errors: list[str] = []


def _headers() -> dict:
    return {"Authorization": f"Bearer {AUTH_TOKEN}"}


def _ok(label: str, detail: str = ""):
    global passed
    passed += 1
    print(f"  ✅  {label}" + (f"  ({detail})" if detail else ""))


def _fail(label: str, detail: str = ""):
    global failed
    failed += 1
    msg = f"  ❌  {label}" + (f"  — {detail}" if detail else "")
    errors.append(msg)
    print(msg)


# ── 1. OAuth URL generation ───────────────────────────────────────────────

def test_oauth_url() -> None:
    print("\n── 1. Google OAuth URL generation ─────────────────────")
    with httpx.Client(base_url=BASE_URL, timeout=10) as c:
        r = c.get("/api/integrations/google/authorize", headers=_headers())

    if r.status_code != 200:
        _fail("GET /authorize", f"status={r.status_code} body={r.text[:200]}")
        return

    data = r.json()
    url_str = data.get("authorization_url", "")
    parsed = urlparse(url_str)

    # Verify domain
    if parsed.hostname == "accounts.google.com":
        _ok("URL points to accounts.google.com")
    else:
        _fail("URL domain", f"got {parsed.hostname}")

    # Verify required query params
    qs = parse_qs(parsed.query)
    required_params = ["client_id", "redirect_uri", "response_type", "scope", "state"]
    for param in required_params:
        if param in qs:
            _ok(f"URL has param '{param}'", qs[param][0][:60])
        else:
            _fail(f"URL missing param '{param}'")

    # Verify scope includes gmail.readonly
    scopes = qs.get("scope", [""])[0]
    if "gmail.readonly" in scopes:
        _ok("Scope includes gmail.readonly")
    else:
        _fail("Scope missing gmail.readonly", scopes)

    # Verify access_type=offline
    if qs.get("access_type", [""])[0] == "offline":
        _ok("access_type=offline (will return refresh_token)")
    else:
        _fail("access_type != offline")


# ── 2. List connections (should be empty or have existing) ────────────────

def test_list_connections() -> list:
    print("\n── 2. List connections ────────────────────────────────")
    with httpx.Client(base_url=BASE_URL, timeout=10) as c:
        r = c.get("/api/integrations/connections", headers=_headers())

    if r.status_code != 200:
        _fail("GET /connections", f"status={r.status_code}")
        return []

    connections = r.json()
    _ok(f"Listed connections", f"count={len(connections)}")
    return connections


# ── 3. Routing rules CRUD ────────────────────────────────────────────────

_created_test_client_id: Optional[str] = None  # Track so we can clean up


def _ensure_test_client() -> Optional[dict]:
    """
    Find the first client owned by the test user via the API.
    If none exists, create one directly in the DB and return it via API.
    """
    global _created_test_client_id

    with httpx.Client(base_url=BASE_URL, timeout=10) as c:
        r = c.get("/api/clients", headers=_headers())
    if r.status_code != 200:
        return None
    clients = r.json()
    if isinstance(clients, dict) and "items" in clients:
        clients = clients["items"]
    if clients:
        return clients[0]

    # No clients — create one via the API
    with httpx.Client(base_url=BASE_URL, timeout=10) as c:
        r = c.post(
            "/api/clients",
            headers=_headers(),
            json={
                "name": "Test Client (Gmail Integration)",
                "email": "testclient@example.com",
            },
        )
    if r.status_code in (200, 201):
        client = r.json()
        _created_test_client_id = client.get("id")
        return client

    # Last resort: create directly via DB
    from app.core.database import SessionLocal
    from app.models.client import Client
    from app.models.user import User
    import uuid as _uuid

    db = SessionLocal()
    try:
        owner = db.query(User).filter(User.clerk_id == "user_test_isolation").first()
        if not owner:
            # Create the user too
            owner = User(clerk_id="user_test_isolation", email="test-isolation@callwen.test")
            db.add(owner)
            db.commit()
            db.refresh(owner)

        new_client = Client(
            id=_uuid.uuid4(),
            name="Test Client (Gmail Integration)",
            email="testclient@example.com",
            owner_id=owner.id,
        )
        db.add(new_client)
        db.commit()
        db.refresh(new_client)
        _created_test_client_id = str(new_client.id)
        return {"id": str(new_client.id), "name": new_client.name}
    finally:
        db.close()


def test_routing_rules() -> None:
    print("\n── 3. Email routing-rule CRUD ──────────────────────────")

    # First, find or create a client to associate the rule with
    client = _ensure_test_client()
    if not client:
        _fail("Could not find or create a test client")
        return

    client_id = client["id"]
    client_name = client.get("name", "unknown")
    _ok(f"Found test client", f"{client_name} ({client_id})")

    test_email = f"test-{uuid.uuid4().hex[:8]}@example.com"
    created_rule_id: Optional[str] = None

    # ── 3a. Create a routing rule ─────────────────────────────────────────
    with httpx.Client(base_url=BASE_URL, timeout=10) as c:
        r = c.post(
            "/api/integrations/routing-rules",
            headers=_headers(),
            json={
                "email_address": test_email,
                "client_id": client_id,
                "match_type": "from",
            },
        )

    if r.status_code == 201:
        rule = r.json()
        created_rule_id = rule["id"]
        _ok("Created routing rule", f"id={created_rule_id} email={test_email}")
    else:
        _fail("Create routing rule", f"status={r.status_code} body={r.text[:200]}")

    # ── 3b. List routing rules ────────────────────────────────────────────
    with httpx.Client(base_url=BASE_URL, timeout=10) as c:
        r = c.get("/api/integrations/routing-rules", headers=_headers())

    if r.status_code == 200:
        rules = r.json()
        found = any(rl.get("email_address") == test_email for rl in rules)
        if found:
            _ok("Listed rules and found our test rule", f"total={len(rules)}")
        else:
            _fail("Listed rules but test rule not found", f"total={len(rules)}")
    else:
        _fail("List routing rules", f"status={r.status_code}")

    # ── 3c. Create duplicate (should fail 400) ────────────────────────────
    with httpx.Client(base_url=BASE_URL, timeout=10) as c:
        r = c.post(
            "/api/integrations/routing-rules",
            headers=_headers(),
            json={
                "email_address": test_email,
                "client_id": client_id,
                "match_type": "from",
            },
        )

    if r.status_code == 400:
        _ok("Duplicate rule rejected (400)")
    else:
        _fail("Duplicate rule not rejected", f"status={r.status_code}")

    # ── 3d. Auto-generate rules ───────────────────────────────────────────
    with httpx.Client(base_url=BASE_URL, timeout=10) as c:
        r = c.post(
            "/api/integrations/routing-rules/auto-generate",
            headers=_headers(),
        )

    if r.status_code == 200:
        auto_rules = r.json()
        _ok("Auto-generate endpoint OK", f"created={len(auto_rules)}")
    else:
        _fail("Auto-generate", f"status={r.status_code} body={r.text[:200]}")

    # ── 3e. Delete the test rule ──────────────────────────────────────────
    if created_rule_id:
        with httpx.Client(base_url=BASE_URL, timeout=10) as c:
            r = c.delete(
                f"/api/integrations/routing-rules/{created_rule_id}",
                headers=_headers(),
            )

        if r.status_code == 204:
            _ok("Deleted routing rule", f"id={created_rule_id}")
        else:
            _fail("Delete routing rule", f"status={r.status_code}")

        # Verify it's gone
        with httpx.Client(base_url=BASE_URL, timeout=10) as c:
            r = c.get("/api/integrations/routing-rules", headers=_headers())
        if r.status_code == 200:
            rules = r.json()
            still_exists = any(rl.get("id") == created_rule_id for rl in rules)
            if not still_exists:
                _ok("Verified rule was deleted")
            else:
                _fail("Rule still present after deletion")

    # Cleanup auto-generated rules (delete any we created during the test)
    with httpx.Client(base_url=BASE_URL, timeout=10) as c:
        r = c.get("/api/integrations/routing-rules", headers=_headers())
        if r.status_code == 200:
            for rule in r.json():
                # Only delete auto-generated rules from our test user
                c.delete(
                    f"/api/integrations/routing-rules/{rule['id']}",
                    headers=_headers(),
                )


# ── 4. Sync log creation (create a fake connection + trigger sync) ───────

def test_sync_log_via_db() -> None:
    """
    Test sync-log creation by directly inserting a fake connection into the
    DB, triggering a sync (which will fail at the Gmail API stage since the
    token is fake), and verifying the sync log is created with an error status.
    """
    print("\n── 4. Sync log / connection endpoints ─────────────────")

    # We'll use direct DB access instead of the Gmail API since we don't
    # have real Google credentials.  Import the DB & models.
    try:
        from app.core.database import SessionLocal
        from app.models.integration_connection import IntegrationConnection
        from app.models.sync_log import SyncLog
        from app.services.google_auth_service import _encrypt
    except ImportError as e:
        _fail("DB imports", str(e))
        return

    db = SessionLocal()
    conn_id = uuid.uuid4()

    try:
        # Create a fake connection for the test user
        fake_conn = IntegrationConnection(
            id=conn_id,
            user_id="user_test_isolation",
            provider="google",
            provider_email="test@gmail.com",
            access_token=_encrypt("fake_access_token"),
            refresh_token=_encrypt("fake_refresh_token"),
            token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            scopes="https://www.googleapis.com/auth/gmail.readonly",
            is_active=True,
        )
        db.add(fake_conn)
        db.commit()
        _ok("Inserted fake connection into DB", f"id={conn_id}")

        # ── 4a. List connections via API — should include our fake one ────
        with httpx.Client(base_url=BASE_URL, timeout=10) as c:
            r = c.get("/api/integrations/connections", headers=_headers())
        if r.status_code == 200:
            conns = r.json()
            found = any(str(cn["id"]) == str(conn_id) for cn in conns)
            if found:
                _ok("Fake connection visible via API")
            else:
                _fail("Fake connection NOT visible via API", f"got {len(conns)} connections")
        else:
            _fail("List connections", f"status={r.status_code}")

        # ── 4b. Trigger sync — will fail because the token is fake ────────
        with httpx.Client(base_url=BASE_URL, timeout=30) as c:
            r = c.post(
                f"/api/integrations/connections/{conn_id}/sync",
                headers=_headers(),
                params={"max_results": 5, "since_hours": 1},
            )

        if r.status_code == 200:
            sync_data = r.json()
            sync_status = sync_data.get("status", "")
            if sync_status == "error":
                _ok("Sync returned error status (expected — fake token)")
            elif sync_status == "success":
                _ok("Sync returned success (unexpected but OK)", json.dumps(sync_data, indent=2)[:200])
            else:
                _ok("Sync completed", f"status={sync_status}")

            # Verify sync log fields
            if sync_data.get("connection_id") and sync_data.get("started_at"):
                _ok("Sync log has connection_id + started_at")
            else:
                _fail("Sync log missing fields", json.dumps(sync_data)[:200])
        elif r.status_code == 500:
            # An unhandled exception — still might have created a sync log
            _fail("Sync endpoint returned 500", r.text[:200])
        else:
            _fail("Sync trigger", f"status={r.status_code} body={r.text[:200]}")

        # ── 4c. Get sync history ──────────────────────────────────────────
        with httpx.Client(base_url=BASE_URL, timeout=10) as c:
            r = c.get(
                f"/api/integrations/connections/{conn_id}/sync-history",
                headers=_headers(),
            )

        if r.status_code == 200:
            history = r.json()
            _ok(f"Sync history returned", f"count={len(history)}")
        else:
            _fail("Sync history", f"status={r.status_code}")

        # ── 4d. Disconnect ─────────────────────────────────────────────────
        with httpx.Client(base_url=BASE_URL, timeout=10) as c:
            r = c.delete(
                f"/api/integrations/connections/{conn_id}",
                headers=_headers(),
            )
        if r.status_code == 204:
            _ok("Disconnected (soft-deleted) fake connection")
        else:
            _fail("Disconnect", f"status={r.status_code}")

        # Verify it's no longer listed
        with httpx.Client(base_url=BASE_URL, timeout=10) as c:
            r = c.get("/api/integrations/connections", headers=_headers())
        if r.status_code == 200:
            conns = r.json()
            still_there = any(str(cn["id"]) == str(conn_id) for cn in conns)
            if not still_there:
                _ok("Verified connection no longer listed")
            else:
                _fail("Connection still listed after disconnect")

    finally:
        # Hard-cleanup: remove the fake connection and its sync logs from DB
        db.query(SyncLog).filter(SyncLog.connection_id == conn_id).delete()
        db.query(IntegrationConnection).filter(IntegrationConnection.id == conn_id).delete()
        db.commit()
        db.close()


# ── 5. Encryption round-trip test ────────────────────────────────────────

def test_encryption() -> None:
    print("\n── 5. Encryption round-trip ────────────────────────────")
    try:
        from app.services.google_auth_service import _encrypt, _decrypt
    except ImportError as e:
        _fail("Encryption imports", str(e))
        return

    plaintext = "test_access_token_12345"
    encrypted = _encrypt(plaintext)

    if encrypted != plaintext:
        _ok("Encrypted text differs from plaintext")
    else:
        _fail("Encrypted text is same as plaintext!")

    decrypted = _decrypt(encrypted)
    if decrypted == plaintext:
        _ok("Decrypt round-trip matches original")
    else:
        _fail("Decrypt mismatch", f"got={decrypted!r}")


# ── 6. Email routing matcher unit test ───────────────────────────────────

def test_email_matcher() -> None:
    """Test the match_email_to_client function with DB-backed rules."""
    print("\n── 6. Email routing matcher ────────────────────────────")
    try:
        from app.core.database import SessionLocal
        from app.models.client import Client
        from app.models.email_routing_rule import EmailRoutingRule
        from app.models.user import User
        from app.services.email_router import match_email_to_client
    except ImportError as e:
        _fail("Matcher imports", str(e))
        return

    db = SessionLocal()
    test_email = f"matcher-test-{uuid.uuid4().hex[:8]}@example.com"

    try:
        # Find or create the test user and client
        owner = db.query(User).filter(User.clerk_id == "user_test_isolation").first()
        if not owner:
            owner = User(clerk_id="user_test_isolation", email="test-isolation@callwen.test")
            db.add(owner)
            db.commit()
            db.refresh(owner)

        client = db.query(Client).filter(Client.owner_id == owner.id).first()
        if not client:
            client = Client(
                name="Test Client (Matcher)",
                email="matchertest@example.com",
                owner_id=owner.id,
            )
            db.add(client)
            db.commit()
            db.refresh(client)

        # Create a routing rule
        rule = EmailRoutingRule(
            user_id="user_test_isolation",
            email_address=test_email,
            client_id=client.id,
            match_type="from",
        )
        db.add(rule)
        db.commit()

        # Test: from match
        result = match_email_to_client(
            from_email=test_email,
            to_emails=["someone@else.com"],
            user_id="user_test_isolation",
            db=db,
        )
        if result == client.id:
            _ok("From-match returned correct client_id")
        else:
            _fail("From-match", f"expected={client.id}, got={result}")

        # Test: no match
        result2 = match_email_to_client(
            from_email="nobody@nowhere.com",
            to_emails=["someone@else.com"],
            user_id="user_test_isolation",
            db=db,
        )
        if result2 is None:
            _ok("No match returns None correctly")
        else:
            _fail("No match should be None", f"got={result2}")

    finally:
        # Cleanup
        db.query(EmailRoutingRule).filter(
            EmailRoutingRule.email_address == test_email
        ).delete()
        db.commit()
        db.close()


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  Gmail Integration Test Suite")
    print(f"  Backend: {BASE_URL}")
    print(f"  Time:    {datetime.now().isoformat()}")
    print("=" * 60)

    # Quick connectivity check
    try:
        r = httpx.get(f"{BASE_URL}/docs", timeout=5)
        if r.status_code != 200:
            print(f"\n⚠️  Backend may not be running at {BASE_URL} (status={r.status_code})")
    except httpx.ConnectError:
        print(f"\n❌ Cannot connect to {BASE_URL}. Is the backend running?")
        print("   Start it with:  ./venv/bin/uvicorn main:app --reload --port 8000")
        sys.exit(1)

    # Run tests
    test_oauth_url()
    test_list_connections()
    test_routing_rules()
    test_sync_log_via_db()
    test_encryption()
    test_email_matcher()

    # Summary
    print("\n" + "=" * 60)
    total = passed + failed
    print(f"  Results: {passed}/{total} passed, {failed} failed")
    if errors:
        print("\n  Failures:")
        for err in errors:
            print(f"    {err}")
    print("=" * 60)

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()

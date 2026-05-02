#!/usr/bin/env python3
"""
End-to-end tests for the Callwen organization system.

Tests the full flow: personal orgs, firm creation, shared clients, access
restriction, subscription enforcement, and edge cases.

Authentication uses TEST_MODE (same as test_client_isolation.py):
  - Reads CLERK_SECRET_KEY from backend/.env.local
  - Sends it as the Bearer token
  - Backend returns a fixed test user (user_test_isolation)

Multi-user scenarios (member B) are tested via direct service/DB calls
since TEST_MODE only supports a single identity.

Usage:
    cd backend
    python scripts/test_org_system.py                # full suite (local)
    python scripts/test_org_system.py --production   # skip destructive tests
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from pathlib import Path
from typing import Any

import httpx

# Allow imports from the backend package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

# ─── Configuration ────────────────────────────────────────────────────────────

BASE_URL = os.environ.get("TEST_BASE_URL", "http://localhost:8000")
TEST_USER_ID = "user_test_isolation"
TEST_USER_EMAIL = "test-isolation@callwen.test"
MEMBER_B_CLERK_ID = f"user_test_member_b_{uuid.uuid4().hex[:8]}"
MEMBER_B_EMAIL = f"testmember-{uuid.uuid4().hex[:6]}@callwen.test"

# ─── Result tracker ──────────────────────────────────────────────────────────

_results: list[tuple[str, bool, str]] = []


def check(label: str, condition: bool, detail: str = "") -> bool:
    status = "PASS" if condition else "FAIL"
    line = f"  [{status}] {label}"
    if detail and not condition:
        line += f"\n         → {detail}"
    print(line)
    _results.append((label, condition, detail))
    return condition


# ─── Auth helper (reused from test_client_isolation.py) ──────────────────────

def _parse_dotenv(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    if not path.exists():
        return result
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        result[key.strip()] = val.strip().strip('"').strip("'")
    return result


def get_headers() -> dict[str, str]:
    explicit = os.environ.get("CLERK_TEST_TOKEN", "").strip()
    if explicit:
        return {"Authorization": f"Bearer {explicit}"}

    env_file = Path(__file__).parent.parent / ".env.local"
    env_vars = _parse_dotenv(env_file)

    test_mode = env_vars.get("TEST_MODE", "").lower() in ("1", "true", "yes")
    secret_key = env_vars.get("CLERK_SECRET_KEY", "").strip()

    if not test_mode:
        print("ERROR: TEST_MODE is not enabled.")
        print(f"       Add TEST_MODE=true to {env_file}")
        sys.exit(1)

    if not secret_key:
        print(f"ERROR: CLERK_SECRET_KEY not found in {env_file}")
        sys.exit(1)

    return {"Authorization": f"Bearer {secret_key}"}


def get_db_session() -> Session:
    """Create a DB session from DATABASE_URL env or backend/.env.local."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        env_file = Path(__file__).parent.parent / ".env.local"
        env_vars = _parse_dotenv(env_file)
        url = env_vars.get("DATABASE_URL")
    if not url:
        print("ERROR: DATABASE_URL not found in environment or backend/.env.local")
        sys.exit(1)
    engine = create_engine(url, pool_pre_ping=True)
    return sessionmaker(bind=engine)()


# ─── DB helpers ──────────────────────────────────────────────────────────────

def ensure_subscription_tier(db: Session, user_id: str, tier: str) -> None:
    """Set the test user's subscription to a specific tier."""
    existing = db.execute(
        text("SELECT id, org_id FROM user_subscriptions WHERE user_id = :uid"),
        {"uid": user_id},
    ).fetchone()
    if existing:
        db.execute(
            text("UPDATE user_subscriptions SET tier = :tier WHERE user_id = :uid"),
            {"tier": tier, "uid": user_id},
        )
        # Also update any org-scoped subscription
        if existing[1]:
            db.execute(
                text("UPDATE user_subscriptions SET tier = :tier WHERE org_id = :oid"),
                {"tier": tier, "oid": existing[1]},
            )
    db.commit()


def create_test_user_b(db: Session) -> None:
    """Insert a second user row for multi-user tests."""
    existing = db.execute(
        text("SELECT id FROM users WHERE clerk_id = :cid"),
        {"cid": MEMBER_B_CLERK_ID},
    ).fetchone()
    if existing:
        return
    db.execute(
        text("""
            INSERT INTO users (id, clerk_id, email, first_name, last_name)
            VALUES (:id, :cid, :email, 'Test', 'MemberB')
        """),
        {
            "id": str(uuid.uuid4()),
            "cid": MEMBER_B_CLERK_ID,
            "email": MEMBER_B_EMAIL,
        },
    )
    db.commit()


def cleanup_test_user_b(db: Session) -> None:
    """Remove the second test user and all related data."""
    # Remove org memberships
    db.execute(
        text("DELETE FROM organization_members WHERE user_id = :uid"),
        {"uid": MEMBER_B_CLERK_ID},
    )
    # Remove client access
    db.execute(
        text("DELETE FROM client_access WHERE user_id = :uid"),
        {"uid": MEMBER_B_CLERK_ID},
    )
    # Remove personal org if created
    db.execute(
        text("DELETE FROM organizations WHERE owner_user_id = :uid AND org_type = 'personal'"),
        {"uid": MEMBER_B_CLERK_ID},
    )
    # Remove user row
    db.execute(
        text("DELETE FROM users WHERE clerk_id = :uid"),
        {"uid": MEMBER_B_CLERK_ID},
    )
    db.commit()


def cleanup_firm_orgs(db: Session, org_ids: list[str]) -> None:
    """Remove firm orgs created during tests."""
    for oid in org_ids:
        # Remove members
        db.execute(
            text("DELETE FROM organization_members WHERE org_id = :oid"),
            {"oid": oid},
        )
        # Remove client access for clients in this org
        db.execute(
            text("""
                DELETE FROM client_access WHERE client_id IN (
                    SELECT id FROM clients WHERE org_id = :oid
                )
            """),
            {"oid": oid},
        )
        # Remove subscriptions pointing to this org
        db.execute(
            text("DELETE FROM user_subscriptions WHERE org_id = :oid"),
            {"oid": oid},
        )
        # Org itself (cascade handles clients if FK is set)
        db.execute(
            text("DELETE FROM organizations WHERE id = :oid"),
            {"oid": oid},
        )
    db.commit()


# ═══════════════════════════════════════════════════════════════════════════════
# Test scenarios
# ═══════════════════════════════════════════════════════════════════════════════


def test_1_solo_user_flow(http: httpx.Client) -> dict[str, Any]:
    """Solo user flow — backward compatibility."""
    print("\n══ Test 1: Solo user flow (backward compatibility) ══")

    # 1a. First API call auto-creates personal org
    r = http.get("/api/organizations")
    check("GET /organizations → 200", r.status_code == 200, r.text[:200])
    orgs = r.json()
    check("At least one org returned", len(orgs) >= 1, f"got {len(orgs)}")

    personal = [o for o in orgs if o["org_type"] == "personal"]
    check("Personal org exists", len(personal) >= 1)

    personal_org = personal[0] if personal else None
    if personal_org:
        check("Personal org role is admin", personal_org["role"] == "admin")
        check("Personal org max_members = 1", personal_org["max_members"] == 1)

    # 1b. Create a client → belongs to personal org
    r = http.post("/api/clients", json={
        "name": "E2E Test Client — Solo",
        "notes": "Automated org e2e test — safe to delete",
    })
    check("Create client → 200/201", r.status_code in (200, 201), r.text[:200])
    client = r.json()
    solo_client_id = client["id"]
    check("Client has org_id", client.get("org_id") is not None)
    if personal_org:
        check(
            "Client org_id matches personal org",
            client.get("org_id") == str(personal_org["id"]),
            f"client.org_id={client.get('org_id')}  personal_org.id={personal_org['id']}",
        )
    check("Client has created_by", client.get("created_by") is not None)

    # 1c. List clients — should include the new client
    r = http.get("/api/clients")
    check("GET /clients → 200", r.status_code == 200, r.text[:200])
    client_ids = [c["id"] for c in r.json().get("items", [])]
    check("New client in list", solo_client_id in client_ids)

    # 1d. Subscription shows org tier
    if personal_org:
        r = http.get(f"/api/organizations/{personal_org['id']}")
        check("GET org detail → 200", r.status_code == 200, r.text[:200])
        detail = r.json()
        check(
            "Org detail shows subscription_tier",
            detail.get("subscription_tier") is not None,
            f"tier={detail.get('subscription_tier')}",
        )

    return {"solo_client_id": solo_client_id, "personal_org": personal_org}


def test_2_firm_creation(
    http: httpx.Client,
    db: Session,
    production: bool,
) -> dict[str, Any]:
    """Firm creation flow."""
    print("\n══ Test 2: Firm creation flow ══")

    if production:
        print("  SKIPPED (--production flag: skipping firm creation)")
        return {}

    # Upgrade subscription to professional so we can create a firm
    ensure_subscription_tier(db, TEST_USER_ID, "professional")

    # 2a. Create firm org
    firm_name = f"E2E Test Firm {uuid.uuid4().hex[:6]}"
    r = http.post("/api/organizations", json={"name": firm_name})
    check("Create firm org → 201", r.status_code == 201, r.text[:300])
    firm = r.json()
    firm_id = firm["id"]
    check("Firm org_type is 'firm'", firm.get("org_type") == "firm")
    check("Admin is owner", firm.get("owner_user_id") == TEST_USER_ID)

    # 2b. Create second test user for member tests
    create_test_user_b(db)

    # 2c. Add member B
    r = http.post(
        f"/api/organizations/{firm_id}/members",
        json={"user_email": MEMBER_B_EMAIL, "role": "member"},
    )
    check("Add member B → 201", r.status_code == 201, r.text[:300])
    if r.status_code == 201:
        member_resp = r.json()
        check("Member B role is 'member'", member_resp.get("role") == "member")
        check("Member B is active", member_resp.get("is_active") is True)

    # 2d. Member B appears in member list
    r = http.get(f"/api/organizations/{firm_id}/members")
    check("GET members → 200", r.status_code == 200, r.text[:300])
    members = r.json()
    member_ids = [m["user_id"] for m in members]
    check("Admin in member list", TEST_USER_ID in member_ids)
    check("Member B in member list", MEMBER_B_CLERK_ID in member_ids)

    # 2e. User can see both orgs
    r = http.get("/api/organizations")
    orgs = r.json()
    org_types = {o["org_type"] for o in orgs}
    check("User sees both personal and firm orgs", "personal" in org_types and "firm" in org_types)

    return {"firm_id": firm_id, "firm_name": firm_name}


def test_3_shared_client(
    http: httpx.Client,
    db: Session,
    firm_id: str,
    production: bool,
) -> dict[str, Any]:
    """Shared client flow — admin creates client, member can access."""
    print("\n══ Test 3: Shared client flow ══")

    if production or not firm_id:
        print("  SKIPPED (no firm org available)")
        return {}

    # 3a. Create client in firm org (use X-Org-Id header)
    r = http.post(
        "/api/clients",
        json={
            "name": "E2E Shared Client",
            "notes": "Automated org e2e test — safe to delete",
        },
        headers={"X-Org-Id": firm_id},
    )
    check("Create shared client → 200/201", r.status_code in (200, 201), r.text[:300])
    client = r.json()
    shared_client_id = client["id"]
    check("Shared client belongs to firm org", client.get("org_id") == firm_id)

    # 3b. Client is open by default (no access records)
    r = http.get(f"/api/organizations/{firm_id}/clients/{shared_client_id}/access")
    check("GET client access → 200", r.status_code == 200, r.text[:300])
    access = r.json()
    check("Client access mode is 'open'", access.get("mode") == "open")
    check("No access records yet", len(access.get("records", [])) == 0)

    # 3c. Verify member B can see the client (via service-level check)
    from app.services.auth_context import AuthContext, check_client_access
    member_b_auth = AuthContext(
        user_id=MEMBER_B_CLERK_ID,
        org_id=uuid.UUID(firm_id),
        org_role="member",
        is_personal_org=False,
    )
    try:
        result = check_client_access(member_b_auth, uuid.UUID(shared_client_id), db)
        check("Member B has access to open client", result is True)
    except Exception as exc:
        check("Member B has access to open client", False, str(exc))

    # 3d. Verify admin can see the client detail with members
    r = http.get(
        f"/api/clients/{shared_client_id}",
        headers={"X-Org-Id": firm_id},
    )
    check("GET client detail → 200", r.status_code == 200, r.text[:300])

    return {"shared_client_id": shared_client_id}


def test_4_access_restriction(
    http: httpx.Client,
    db: Session,
    firm_id: str,
    shared_client_id: str,
    production: bool,
) -> None:
    """Access restriction flow — restrict, revoke, re-grant."""
    print("\n══ Test 4: Access restriction flow ══")

    if production or not firm_id or not shared_client_id:
        print("  SKIPPED (no firm/client available)")
        return

    from app.services.auth_context import AuthContext, check_client_access
    from fastapi import HTTPException

    # 4a. Restrict the client
    r = http.post(
        f"/api/organizations/{firm_id}/clients/{shared_client_id}/access/restrict",
    )
    check("Restrict client → 200", r.status_code == 200, r.text[:300])
    access = r.json()
    check("Access mode is 'restricted'", access.get("mode") == "restricted")
    records = access.get("records", [])
    check("Access records created for all members", len(records) >= 2)

    # Both admin and member B should have 'full' access
    levels = {r["user_id"]: r["access_level"] for r in records}
    check(
        "Admin has 'full' access",
        levels.get(TEST_USER_ID) == "full",
        f"levels={levels}",
    )
    check(
        "Member B has 'full' access after restrict",
        levels.get(MEMBER_B_CLERK_ID) == "full",
        f"levels={levels}",
    )

    # 4b. Revoke member B's access (set to 'none')
    r = http.post(
        f"/api/organizations/{firm_id}/clients/{shared_client_id}/access",
        json={"user_id": MEMBER_B_CLERK_ID, "access_level": "none"},
    )
    check("Set member B access to 'none' → 201", r.status_code == 201, r.text[:300])

    # 4c. Verify member B is denied (service-level check)
    member_b_auth = AuthContext(
        user_id=MEMBER_B_CLERK_ID,
        org_id=uuid.UUID(firm_id),
        org_role="member",
        is_personal_org=False,
    )
    try:
        check_client_access(member_b_auth, uuid.UUID(shared_client_id), db)
        check("Member B blocked after revocation", False, "Expected 403 but access was allowed")
    except HTTPException as exc:
        check("Member B blocked after revocation", exc.status_code == 403)

    # 4d. Re-grant access
    r = http.post(
        f"/api/organizations/{firm_id}/clients/{shared_client_id}/access",
        json={"user_id": MEMBER_B_CLERK_ID, "access_level": "full"},
    )
    check("Re-grant member B access → 201", r.status_code == 201, r.text[:300])

    # 4e. Verify member B can access again
    try:
        result = check_client_access(member_b_auth, uuid.UUID(shared_client_id), db)
        check("Member B can access after re-grant", result is True)
    except Exception as exc:
        check("Member B can access after re-grant", False, str(exc))


def test_5_subscription_enforcement(
    http: httpx.Client,
    db: Session,
    firm_id: str,
    production: bool,
) -> None:
    """Subscription enforcement — seat limits and shared quota."""
    print("\n══ Test 5: Subscription enforcement ══")

    if production or not firm_id:
        print("  SKIPPED (no firm org available)")
        return

    # 5a. Check current member count
    r = http.get(f"/api/organizations/{firm_id}/members")
    members = r.json()
    member_count = len(members)
    check(f"Firm has {member_count} members", member_count >= 2)

    # 5b. Set max_members to current count to test the limit
    db.execute(
        text("UPDATE organizations SET max_members = :max WHERE id = :oid"),
        {"max": member_count, "oid": firm_id},
    )
    db.commit()

    # 5c. Try adding a third member — should fail with seat limit
    dummy_email = f"dummy-seat-{uuid.uuid4().hex[:6]}@callwen.test"
    dummy_clerk = f"user_test_dummy_{uuid.uuid4().hex[:8]}"
    db.execute(
        text("""
            INSERT INTO users (id, clerk_id, email, first_name, last_name)
            VALUES (:id, :cid, :email, 'Dummy', 'SeatTest')
        """),
        {"id": str(uuid.uuid4()), "cid": dummy_clerk, "email": dummy_email},
    )
    db.commit()

    r = http.post(
        f"/api/organizations/{firm_id}/members",
        json={"user_email": dummy_email, "role": "member"},
    )
    check(
        "Adding member beyond seat limit → 403",
        r.status_code == 403,
        f"status={r.status_code} body={r.text[:200]}",
    )

    # 5d. Increase seat limit — adding should succeed
    db.execute(
        text("UPDATE organizations SET max_members = :max WHERE id = :oid"),
        {"max": member_count + 5, "oid": firm_id},
    )
    db.commit()

    r = http.post(
        f"/api/organizations/{firm_id}/members",
        json={"user_email": dummy_email, "role": "member"},
    )
    check(
        "Adding member after seat increase → 201",
        r.status_code == 201,
        f"status={r.status_code} body={r.text[:200]}",
    )

    # 5e. Token usage is tracked at org level
    # Check that token_usage table has org_id column
    row = db.execute(
        text("SELECT column_name FROM information_schema.columns WHERE table_name = 'token_usage' AND column_name = 'org_id'")
    ).fetchone()
    check("token_usage table has org_id column", row is not None)

    # Cleanup: remove dummy user
    db.execute(
        text("DELETE FROM organization_members WHERE user_id = :uid"),
        {"uid": dummy_clerk},
    )
    db.execute(
        text("DELETE FROM users WHERE clerk_id = :uid"),
        {"uid": dummy_clerk},
    )
    db.commit()


def test_6_edge_cases(
    http: httpx.Client,
    db: Session,
    firm_id: str,
    production: bool,
) -> None:
    """Edge cases — owner protection, multi-org switching, doc preservation."""
    print("\n══ Test 6: Edge cases ══")

    # 6a. Owner cannot be removed
    if firm_id and not production:
        r = http.delete(f"/api/organizations/{firm_id}/members/{TEST_USER_ID}")
        check(
            "Cannot remove org owner → 400",
            r.status_code == 400,
            f"status={r.status_code} body={r.text[:200]}",
        )

    # 6b. Owner role cannot be demoted
    if firm_id and not production:
        r = http.patch(
            f"/api/organizations/{firm_id}/members/{TEST_USER_ID}",
            json={"role": "member"},
        )
        check(
            "Cannot demote org owner → 400",
            r.status_code == 400,
            f"status={r.status_code} body={r.text[:200]}",
        )

    # 6c. User belongs to multiple orgs
    r = http.get("/api/organizations")
    orgs = r.json()
    if not production:
        check("User sees multiple orgs", len(orgs) >= 2, f"count={len(orgs)}")

    # 6d. Removing member preserves their uploaded documents
    if firm_id and not production:
        # Get member B's docs count before removal
        pre_docs = db.execute(text("""
            SELECT count(*) FROM documents d
            JOIN clients c ON d.client_id = c.id
            JOIN users u ON d.uploaded_by = u.id
            WHERE c.org_id = :oid AND u.clerk_id = :uid
        """), {"oid": firm_id, "uid": MEMBER_B_CLERK_ID}).scalar() or 0

        # Remove member B
        r = http.delete(f"/api/organizations/{firm_id}/members/{MEMBER_B_CLERK_ID}")
        check(
            "Remove member B → 204",
            r.status_code == 204,
            f"status={r.status_code} body={r.text[:200] if r.text else ''}",
        )

        # Verify docs are preserved
        post_docs = db.execute(text("""
            SELECT count(*) FROM documents d
            JOIN clients c ON d.client_id = c.id
            JOIN users u ON d.uploaded_by = u.id
            WHERE c.org_id = :oid AND u.clerk_id = :uid
        """), {"oid": firm_id, "uid": MEMBER_B_CLERK_ID}).scalar() or 0

        check(
            "Member B's documents preserved after removal",
            post_docs == pre_docs,
            f"before={pre_docs} after={post_docs}",
        )

        # 6e. Member B's access records revoked on removal
        access_count = db.execute(text("""
            SELECT count(*) FROM client_access
            WHERE user_id = :uid AND access_level != 'none'
            AND client_id IN (SELECT id FROM clients WHERE org_id = :oid)
        """), {"uid": MEMBER_B_CLERK_ID, "oid": firm_id}).scalar()
        check(
            "Member B's access revoked on removal",
            access_count == 0,
            f"active_access_records={access_count}",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════

def run_tests(production: bool = False) -> bool:
    headers = get_headers()
    http = httpx.Client(base_url=BASE_URL, headers=headers, timeout=60)
    db = get_db_session()

    solo_client_id: str | None = None
    firm_id: str | None = None
    shared_client_id: str | None = None
    created_firm_ids: list[str] = []

    try:
        # ── Test 1: Solo user ─────────────────────────────────────────────
        result1 = test_1_solo_user_flow(http)
        solo_client_id = result1.get("solo_client_id")

        # ── Test 2: Firm creation ─────────────────────────────────────────
        result2 = test_2_firm_creation(http, db, production)
        firm_id = result2.get("firm_id")
        if firm_id:
            created_firm_ids.append(firm_id)

        # ── Test 3: Shared client ─────────────────────────────────────────
        result3 = test_3_shared_client(http, db, firm_id or "", production)
        shared_client_id = result3.get("shared_client_id")

        # ── Test 4: Access restriction ────────────────────────────────────
        test_4_access_restriction(
            http, db, firm_id or "", shared_client_id or "", production,
        )

        # ── Test 5: Subscription enforcement ──────────────────────────────
        test_5_subscription_enforcement(http, db, firm_id or "", production)

        # ── Test 6: Edge cases ────────────────────────────────────────────
        test_6_edge_cases(http, db, firm_id or "", production)

    finally:
        # ── Cleanup ───────────────────────────────────────────────────────
        print("\n── Cleanup ──")

        # Delete test clients via API
        for cid, name in [
            (solo_client_id, "Solo client"),
            (shared_client_id, "Shared client"),
        ]:
            if cid:
                # Try with firm org header first, then without
                deleted = False
                if firm_id:
                    r = http.delete(
                        f"/api/clients/{cid}",
                        headers={"X-Org-Id": firm_id},
                    )
                    if r.status_code in (200, 204):
                        print(f"  Deleted {name} ({cid})")
                        deleted = True

                if not deleted:
                    r = http.delete(f"/api/clients/{cid}")
                    if r.status_code in (200, 204):
                        print(f"  Deleted {name} ({cid})")
                    else:
                        print(f"  WARNING: Could not delete {name}: {r.status_code}")

        # Clean up test user B
        cleanup_test_user_b(db)
        print("  Cleaned up test user B")

        # Clean up firm orgs
        if created_firm_ids:
            cleanup_firm_orgs(db, created_firm_ids)
            print(f"  Cleaned up {len(created_firm_ids)} firm org(s)")

        # Restore subscription tier
        ensure_subscription_tier(db, TEST_USER_ID, "starter")
        print("  Restored subscription tier to starter")

        db.close()
        http.close()

    # ── Summary ───────────────────────────────────────────────────────────
    passed = sum(1 for _, ok, _ in _results if ok)
    failed = sum(1 for _, ok, _ in _results if not ok)
    total = passed + failed

    print("\n" + "═" * 60)
    print(f"  {passed}/{total} checks passed", end="")
    if failed:
        print(f"  ({failed} FAILED)")
    else:
        print("  — all good!")
    print("═" * 60)

    if failed:
        print("\nFailed checks:")
        for label, ok, detail in _results:
            if not ok:
                print(f"  ✗  {label}")
                if detail:
                    print(f"       {detail}")
        return False
    return True


# ─── Entry points ────────────────────────────────────────────────────────────

def test_org_system():
    """pytest-compatible wrapper."""
    assert run_tests(), "One or more org system checks failed — see output above."


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="E2E tests for org system")
    parser.add_argument(
        "--production",
        action="store_true",
        help="Skip destructive tests (firm creation, member management)",
    )
    args = parser.parse_args()

    ok = run_tests(production=args.production)
    sys.exit(0 if ok else 1)

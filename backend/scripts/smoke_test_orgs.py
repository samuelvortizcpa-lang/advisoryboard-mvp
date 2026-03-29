#!/usr/bin/env python3
"""
Quick smoke test for the Callwen organization system.

Verifies core endpoints respond correctly without creating firm orgs or
modifying shared state.  Safe to run against any environment.

Authentication uses TEST_MODE (same as other test scripts).

Usage:
    cd backend
    python scripts/smoke_test_orgs.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx

# ─── Configuration ────────────────────────────────────────────────────────────

BASE_URL = os.environ.get("TEST_BASE_URL", "http://localhost:8000")

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


# ─── Auth helper ─────────────────────────────────────────────────────────────

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

    env_file = Path(__file__).parent.parent / ".env"
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


# ─── Smoke tests ─────────────────────────────────────────────────────────────

def run_smoke_tests() -> bool:
    headers = get_headers()
    http = httpx.Client(base_url=BASE_URL, headers=headers, timeout=30)
    client_id: str | None = None

    try:
        print("\n══ Smoke Test: Organization System ══\n")

        # 1. Personal org exists
        print("── 1. Personal org ──")
        r = http.get("/api/organizations")
        check("GET /organizations → 200", r.status_code == 200, r.text[:200])
        orgs = r.json()
        personal = [o for o in orgs if o["org_type"] == "personal"]
        check("Personal org exists", len(personal) >= 1)

        org_id = personal[0]["id"] if personal else None
        if org_id:
            check("Personal org has 'id' field", org_id is not None)
            check("Personal org has role", personal[0].get("role") is not None)

        # 2. Client CRUD works with org_id
        print("\n── 2. Client CRUD with org_id ──")
        r = http.post("/api/clients", json={
            "name": "Smoke Test Client",
            "notes": "Automated smoke test — safe to delete",
        })
        check("POST /clients → 200/201", r.status_code in (200, 201), r.text[:200])
        if r.status_code in (200, 201):
            client_data = r.json()
            client_id = client_data["id"]
            check("Client has org_id", client_data.get("org_id") is not None)
            check("Client has created_by", client_data.get("created_by") is not None)

            # Read back
            r = http.get(f"/api/clients/{client_id}")
            check("GET /clients/{id} → 200", r.status_code == 200, r.text[:200])

            # Update
            r = http.put(f"/api/clients/{client_id}", json={
                "name": "Smoke Test Client (updated)",
            })
            check("PUT /clients/{id} → 200", r.status_code == 200, r.text[:200])

        # 3. Member list endpoint responds
        print("\n── 3. Member list endpoint ──")
        if org_id:
            r = http.get(f"/api/organizations/{org_id}/members")
            check("GET /organizations/{id}/members → 200", r.status_code == 200, r.text[:200])
            members = r.json()
            check("At least 1 member", len(members) >= 1)

        # 4. Client access endpoint responds
        print("\n── 4. Client access endpoint ──")
        if org_id and client_id:
            r = http.get(f"/api/organizations/{org_id}/clients/{client_id}/access")
            check(
                "GET /organizations/{id}/clients/{id}/access → 200",
                r.status_code == 200,
                r.text[:200],
            )
            access = r.json()
            check("Access response has 'mode' field", "mode" in access)
            check("Access response has 'records' field", "records" in access)

        # 5. Org detail endpoint
        print("\n── 5. Org detail endpoint ──")
        if org_id:
            r = http.get(f"/api/organizations/{org_id}")
            check("GET /organizations/{id} → 200", r.status_code == 200, r.text[:200])
            detail = r.json()
            check("Org detail has 'name'", "name" in detail)
            check("Org detail has 'org_type'", "org_type" in detail)
            check("Org detail has 'subscription_tier'", "subscription_tier" in detail)

    finally:
        # Cleanup
        print("\n── Cleanup ──")
        if client_id:
            r = http.delete(f"/api/clients/{client_id}")
            if r.status_code in (200, 204):
                print(f"  Deleted smoke test client ({client_id})")
            else:
                print(f"  WARNING: Could not delete client: {r.status_code}")
        http.close()

    # Summary
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

def test_smoke_orgs():
    """pytest-compatible wrapper."""
    assert run_smoke_tests(), "One or more smoke checks failed — see output above."


if __name__ == "__main__":
    ok = run_smoke_tests()
    sys.exit(0 if ok else 1)

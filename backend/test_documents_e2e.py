#!/usr/bin/env python3
"""
End-to-end test for the document upload API.

Uses FastAPI's dependency_overrides to replace get_current_user with a mock,
so no real Clerk JWT is needed.  The test runs against the actual dev database
and cleans up after itself.

Usage:
    cd backend && source venv/bin/activate && python test_documents_e2e.py
"""

import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from fastapi.testclient import TestClient

from main import app
from app.core.auth import get_current_user
from app.core.database import SessionLocal
from app.models.client import Client
from app.models.user import User

# ---------------------------------------------------------------------------
# Mock identity — a stable test clerk_id so re-runs reuse the same DB user.
# ---------------------------------------------------------------------------

TEST_CLERK_ID = "user_e2e_test_document_upload"

MOCK_USER = {
    "user_id": TEST_CLERK_ID,
    "email": "e2e-test@callwen.local",
    "email_verified": True,
    "first_name": "E2E",
    "last_name": "Tester",
    "image_url": None,
    "session_id": "sess_test",
    "raw": {},
}

# Replace the Clerk auth dependency for the duration of this script.
app.dependency_overrides[get_current_user] = lambda: MOCK_USER

http = TestClient(app, raise_server_exceptions=False)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PASS = "✅"
FAIL = "❌"
SEP  = "─" * 62


def banner(title: str) -> None:
    print(f"\n{'═'*62}")
    print(f"  {title}")
    print(f"{'═'*62}")


def show(label: str, r) -> None:
    ok = 200 <= r.status_code < 300
    icon = PASS if ok else FAIL
    print(f"\n{icon}  {label}")
    print(f"   Status : {r.status_code}")
    try:
        body = r.json()
        print(f"   Body   : {json.dumps(body, indent=4, default=str)}")
    except Exception:
        ct = r.headers.get("content-type", "")
        if "text" in ct or len(r.content) < 300:
            print(f"   Body   : {r.text[:300]}")
        else:
            print(f"   Body   : <binary {len(r.content)} bytes>")
    print(SEP)


def get_or_create_test_client(user_db_id: uuid.UUID) -> uuid.UUID:
    db = SessionLocal()
    try:
        existing = (
            db.query(Client)
            .filter(
                Client.owner_id == user_db_id,
                Client.name == "E2E Test Client LLC",
            )
            .first()
        )
        if existing:
            return existing.id

        c = Client(
            owner_id=user_db_id,
            name="E2E Test Client LLC",
            email="client@example.com",
            business_name="E2E Test Client LLC",
            entity_type="LLC",
            industry="Technology",
            notes="Created by test_documents_e2e.py — safe to delete.",
        )
        db.add(c)
        db.commit()
        db.refresh(c)
        return c.id
    finally:
        db.close()


def get_test_user_db_id() -> uuid.UUID:
    """The test client creates the user on first auth call; fetch it here."""
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.clerk_id == TEST_CLERK_ID).first()
        if u:
            return u.id
        raise RuntimeError("Test user not found — did the first API call fail?")
    finally:
        db.close()


def cleanup(client_id: uuid.UUID) -> None:
    """Remove only the test client (cascades to documents)."""
    db = SessionLocal()
    try:
        c = db.query(Client).filter(Client.id == client_id).first()
        if c:
            db.delete(c)
            db.commit()
            print(f"\n🧹  Cleaned up test client {client_id} (and its documents).")
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def assert_status(r, expected: int, step: str) -> bool:
    if r.status_code != expected:
        print(f"\n{FAIL}  {step} — expected {expected}, got {r.status_code}")
        try:
            print(f"   Detail: {r.json()}")
        except Exception:
            print(f"   Body  : {r.text[:200]}")
        return False
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    banner("Callwen — Document Upload End-to-End Test")

    # ── Warm-up: list clients to auto-create the test user in DB ──────────
    print("\n📋  Step 0 · Warm-up (auto-creates test user via get_or_create_user)")
    r0 = http.get("/api/clients")
    show("GET /api/clients", r0)
    if not assert_status(r0, 200, "Step 0"):
        return 1

    user_db_id = get_test_user_db_id()
    print(f"   DB user id : {user_db_id}")

    client_id = get_or_create_test_client(user_db_id)
    print(f"   Test client: {client_id}")

    # ── Create test file ──────────────────────────────────────────────────
    test_content = (
        "Callwen E2E Test Document\n"
        "================================\n"
        "Client: E2E Test Client LLC\n"
        "Date: 2026-03-02\n"
        "This file was uploaded by test_documents_e2e.py.\n"
    )
    test_file = Path("/tmp/e2e_test_report.txt")
    test_file.write_text(test_content)
    print(f"\n📄  Test file created: {test_file}  ({len(test_content)} bytes)")

    # ── Step 1: Upload ────────────────────────────────────────────────────
    banner("Step 1 · Upload document")
    with open(test_file, "rb") as fh:
        r1 = http.post(
            f"/api/clients/{client_id}/documents",
            files={"file": ("e2e_test_report.txt", fh, "text/plain")},
        )
    show(f"POST /api/clients/{client_id}/documents", r1)
    if not assert_status(r1, 201, "Step 1: Upload"):
        cleanup(client_id)
        return 1

    doc = r1.json()
    document_id = doc["id"]
    print(f"   Document ID : {document_id}")
    print(f"   Filename    : {doc['filename']}")
    print(f"   File type   : {doc['file_type']}")
    print(f"   File size   : {doc['file_size']} bytes")
    print(f"   Processed   : {doc['processed']}")

    # ── Step 2: List documents ────────────────────────────────────────────
    banner("Step 2 · List documents for client")
    r2 = http.get(f"/api/clients/{client_id}/documents")
    show(f"GET /api/clients/{client_id}/documents", r2)
    if not assert_status(r2, 200, "Step 2: List"):
        cleanup(client_id)
        return 1

    listed = r2.json()
    print(f"   Total in list : {listed['total']}")
    assert listed["total"] >= 1, "Expected at least 1 document after upload"
    ids_in_list = [d["id"] for d in listed["items"]]
    assert document_id in ids_in_list, "Uploaded document not in list"
    print(f"   Uploaded doc in list: {PASS}")

    # ── Step 3: Download ──────────────────────────────────────────────────
    banner("Step 3 · Download document")
    r3 = http.get(f"/api/documents/{document_id}/download")
    print(f"\n{PASS if r3.status_code == 200 else FAIL}  GET /api/documents/{document_id}/download")
    print(f"   Status            : {r3.status_code}")
    print(f"   Content-Type      : {r3.headers.get('content-type', 'N/A')}")
    print(f"   Content-Disposition: {r3.headers.get('content-disposition', 'N/A')}")
    if r3.status_code == 200:
        downloaded = r3.content.decode()
        match = downloaded == test_content
        print(f"   Content matches   : {PASS if match else FAIL}")
        print(f"   Downloaded bytes  : {len(r3.content)}")
        if not match:
            print(f"   Expected : {test_content!r}")
            print(f"   Got      : {downloaded!r}")
    print(SEP)
    if not assert_status(r3, 200, "Step 3: Download"):
        cleanup(client_id)
        return 1

    # ── Step 4: Delete ────────────────────────────────────────────────────
    banner("Step 4 · Delete document")
    r4 = http.delete(f"/api/documents/{document_id}")
    show(f"DELETE /api/documents/{document_id}", r4)
    if not assert_status(r4, 204, "Step 4: Delete"):
        cleanup(client_id)
        return 1
    print(f"   204 No Content — deleted {PASS}")

    # ── Step 5: Verify gone ───────────────────────────────────────────────
    banner("Step 5 · Verify document is gone")

    # 5a — list should be empty
    r5a = http.get(f"/api/clients/{client_id}/documents")
    show(f"GET /api/clients/{client_id}/documents (after delete)", r5a)
    assert_status(r5a, 200, "Step 5a: List after delete")
    total_after = r5a.json()["total"]
    print(f"   Documents remaining: {total_after}  {'✅ (zero)' if total_after == 0 else FAIL}")

    # 5b — download should 404
    r5b = http.get(f"/api/documents/{document_id}/download")
    show(f"GET /api/documents/{document_id}/download (after delete)", r5b)
    if r5b.status_code == 404:
        print(f"   404 as expected {PASS}")
    else:
        print(f"   {FAIL} Expected 404, got {r5b.status_code}")

    # 5c — delete again should 404
    r5c = http.delete(f"/api/documents/{document_id}")
    show(f"DELETE /api/documents/{document_id} (again)", r5c)
    if r5c.status_code == 404:
        print(f"   404 idempotent delete {PASS}")
    else:
        print(f"   {FAIL} Expected 404, got {r5c.status_code}")

    # ── Error cases ───────────────────────────────────────────────────────
    banner("Bonus · Error handling checks")

    # Bad extension
    bad_file = Path("/tmp/bad.exe")
    bad_file.write_bytes(b"MZ\x90\x00")
    with open(bad_file, "rb") as fh:
        r_bad_ext = http.post(
            f"/api/clients/{client_id}/documents",
            files={"file": ("malware.exe", fh, "application/octet-stream")},
        )
    show("POST with .exe extension (expect 400)", r_bad_ext)
    if r_bad_ext.status_code == 400:
        print(f"   Rejected bad extension {PASS}")

    # Wrong client ID (not owned by this user)
    fake_id = uuid.uuid4()
    with open(test_file, "rb") as fh:
        r_wrong_client = http.post(
            f"/api/clients/{fake_id}/documents",
            files={"file": ("report.txt", fh, "text/plain")},
        )
    show(f"POST to non-existent client {fake_id} (expect 404)", r_wrong_client)
    if r_wrong_client.status_code == 404:
        print(f"   Rejected wrong client {PASS}")

    # ── Cleanup ───────────────────────────────────────────────────────────
    cleanup(client_id)

    banner("All tests passed 🎉")
    return 0


if __name__ == "__main__":
    sys.exit(main())

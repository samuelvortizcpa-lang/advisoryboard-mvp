#!/usr/bin/env python3
"""
One-time migration: backfill org_id for all existing data.

Creates a personal org for every user, then sets org_id on clients,
user_subscriptions, token_usage, and integration_connections.  Also
backfills documents.uploaded_by and clients.created_by.

Idempotent — safe to run multiple times.  Rows that already have a value
are skipped.

Usage:
    cd backend
    DATABASE_URL="postgresql://..." python scripts/migrate_to_orgs.py
"""

from __future__ import annotations

import os
import sys
import time

# Allow imports from the backend package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker


def get_session() -> Session:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("ERROR: DATABASE_URL environment variable is required")
        sys.exit(1)
    engine = create_engine(url, pool_pre_ping=True)
    return sessionmaker(bind=engine)()


# ---------------------------------------------------------------------------
# Step 1 — Create personal orgs for every existing user
# ---------------------------------------------------------------------------

def step1_create_personal_orgs(db: Session) -> dict[str, str]:
    """
    Returns a mapping of clerk_id → org_id (as strings) for every user
    who now has a personal org.
    """
    print("\n=== Step 1: Create personal orgs ===")

    # Gather all distinct clerk_ids that need a personal org.
    # Source 1: users table (covers client owners)
    # Source 2: user_subscriptions.user_id (Clerk IDs)
    # Source 3: token_usage.user_id
    # Source 4: integration_connections.user_id
    rows = db.execute(text("""
        SELECT DISTINCT clerk_id FROM (
            SELECT u.clerk_id
            FROM clients c
            JOIN users u ON u.id = c.owner_id
            UNION
            SELECT user_id AS clerk_id FROM user_subscriptions
            UNION
            SELECT user_id AS clerk_id FROM token_usage
            UNION
            SELECT user_id AS clerk_id FROM integration_connections
        ) all_users
        WHERE clerk_id IS NOT NULL
    """)).fetchall()

    clerk_ids = [r[0] for r in rows]
    print(f"  Found {len(clerk_ids)} distinct users")

    # We need email + name for get_or_create_personal_org.
    # Import the service (now that sys.path is set).
    from app.services.organization_service import get_or_create_personal_org

    created = 0
    existed = 0
    clerk_to_org: dict[str, str] = {}

    for clerk_id in clerk_ids:
        # Look up user details from the users table
        user_row = db.execute(text(
            "SELECT email, first_name, last_name FROM users WHERE clerk_id = :cid"
        ), {"cid": clerk_id}).fetchone()

        email = (user_row[0] if user_row and user_row[0] else None) or f"user-{clerk_id[:8]}"
        name = None
        if user_row and (user_row[1] or user_row[2]):
            name = " ".join(filter(None, [user_row[1], user_row[2]]))
        if not name:
            name = "Unknown User"

        # Check if personal org already exists
        existing = db.execute(text(
            "SELECT id FROM organizations WHERE owner_user_id = :uid AND org_type = 'personal'"
        ), {"uid": clerk_id}).fetchone()

        if existing:
            clerk_to_org[clerk_id] = str(existing[0])
            existed += 1
        else:
            org = get_or_create_personal_org(clerk_id, email, name, db)
            clerk_to_org[clerk_id] = str(org.id)
            created += 1

    db.commit()
    print(f"  Created {created} personal orgs, {existed} already existed")
    return clerk_to_org


# ---------------------------------------------------------------------------
# Step 2 — Backfill clients.org_id and clients.created_by
# ---------------------------------------------------------------------------

def step2_backfill_clients(db: Session, clerk_to_org: dict[str, str]) -> None:
    print("\n=== Step 2: Backfill clients.org_id + created_by ===")

    # Batch update: join clients → users to get clerk_id → org_id
    result = db.execute(text("""
        UPDATE clients
        SET org_id = orgs.id
        FROM users u
        JOIN organizations orgs
            ON orgs.owner_user_id = u.clerk_id
            AND orgs.org_type = 'personal'
        WHERE clients.owner_id = u.id
          AND clients.org_id IS NULL
    """))
    print(f"  Set org_id on {result.rowcount} clients")

    # Backfill created_by (Clerk user ID) from the owner
    result = db.execute(text("""
        UPDATE clients
        SET created_by = u.clerk_id
        FROM users u
        WHERE clients.owner_id = u.id
          AND clients.created_by IS NULL
    """))
    print(f"  Set created_by on {result.rowcount} clients")

    db.commit()


# ---------------------------------------------------------------------------
# Step 3 — Backfill documents.uploaded_by
# ---------------------------------------------------------------------------

def step3_backfill_documents(db: Session) -> None:
    print("\n=== Step 3: Backfill documents.uploaded_by ===")

    result = db.execute(text("""
        UPDATE documents
        SET uploaded_by = c.owner_id
        FROM clients c
        WHERE documents.client_id = c.id
          AND documents.uploaded_by IS NULL
    """))
    print(f"  Set uploaded_by on {result.rowcount} documents")
    db.commit()


# ---------------------------------------------------------------------------
# Step 4 — Backfill user_subscriptions.org_id
# ---------------------------------------------------------------------------

def step4_backfill_subscriptions(db: Session) -> None:
    print("\n=== Step 4: Backfill user_subscriptions.org_id ===")

    result = db.execute(text("""
        UPDATE user_subscriptions us
        SET org_id = orgs.id
        FROM organizations orgs
        WHERE orgs.owner_user_id = us.user_id
          AND orgs.org_type = 'personal'
          AND us.org_id IS NULL
    """))
    print(f"  Set org_id on {result.rowcount} subscriptions")
    db.commit()


# ---------------------------------------------------------------------------
# Step 5 — Backfill token_usage.org_id
# ---------------------------------------------------------------------------

def step5_backfill_token_usage(db: Session) -> None:
    print("\n=== Step 5: Backfill token_usage.org_id ===")

    result = db.execute(text("""
        UPDATE token_usage tu
        SET org_id = orgs.id
        FROM organizations orgs
        WHERE orgs.owner_user_id = tu.user_id
          AND orgs.org_type = 'personal'
          AND tu.org_id IS NULL
    """))
    print(f"  Set org_id on {result.rowcount} token_usage rows")
    db.commit()


# ---------------------------------------------------------------------------
# Step 6 — Backfill integration_connections.org_id
# ---------------------------------------------------------------------------

def step6_backfill_integrations(db: Session) -> None:
    print("\n=== Step 6: Backfill integration_connections.org_id ===")

    result = db.execute(text("""
        UPDATE integration_connections ic
        SET org_id = orgs.id
        FROM organizations orgs
        WHERE orgs.owner_user_id = ic.user_id
          AND orgs.org_type = 'personal'
          AND ic.org_id IS NULL
    """))
    print(f"  Set org_id on {result.rowcount} integration connections")
    db.commit()


# ---------------------------------------------------------------------------
# Step 7 — Storage path migration (skipped — dual-path lookup handles this)
# ---------------------------------------------------------------------------

def step7_storage_paths(db: Session) -> None:
    print("\n=== Step 7: Storage path migration ===")
    print("  SKIPPED — dual-path lookup in storage_service.py handles old paths")


# ---------------------------------------------------------------------------
# Step 8 — Verification
# ---------------------------------------------------------------------------

def step8_verify(db: Session) -> bool:
    print("\n=== Step 8: Verification ===")
    ok = True

    checks = [
        ("clients with org_id IS NULL", "SELECT count(*) FROM clients WHERE org_id IS NULL"),
        ("clients with created_by IS NULL", "SELECT count(*) FROM clients WHERE created_by IS NULL"),
        ("documents with uploaded_by IS NULL", "SELECT count(*) FROM documents WHERE uploaded_by IS NULL"),
        ("user_subscriptions with org_id IS NULL", "SELECT count(*) FROM user_subscriptions WHERE org_id IS NULL"),
        ("token_usage with org_id IS NULL", "SELECT count(*) FROM token_usage WHERE org_id IS NULL"),
        ("integration_connections with org_id IS NULL", "SELECT count(*) FROM integration_connections WHERE org_id IS NULL"),
    ]

    for label, query in checks:
        count = db.execute(text(query)).scalar()
        status = "OK" if count == 0 else "WARN"
        if count > 0:
            ok = False
        print(f"  [{status}] {label}: {count}")

    # Summary counts
    org_count = db.execute(text("SELECT count(*) FROM organizations WHERE org_type = 'personal'")).scalar()
    client_count = db.execute(text("SELECT count(*) FROM clients")).scalar()
    print(f"\n  Total personal orgs: {org_count}")
    print(f"  Total clients: {client_count}")

    return ok


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 60)
    print("  AdvisoryBoard — Org Migration Backfill")
    print("=" * 60)

    start = time.time()
    db = get_session()

    try:
        clerk_to_org = step1_create_personal_orgs(db)
        step2_backfill_clients(db, clerk_to_org)
        step3_backfill_documents(db)
        step4_backfill_subscriptions(db)
        step5_backfill_token_usage(db)
        step6_backfill_integrations(db)
        step7_storage_paths(db)
        ok = step8_verify(db)

        elapsed = time.time() - start
        print(f"\nCompleted in {elapsed:.1f}s")

        if ok:
            print("All checks passed — safe to run the NOT NULL migration.")
        else:
            print("WARNING: Some rows still have NULL org_id. Investigate before running NOT NULL migration.")

    finally:
        db.close()


if __name__ == "__main__":
    main()

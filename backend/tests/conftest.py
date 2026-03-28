"""
Shared test fixtures for Callwen backend tests.

Uses an in-memory SQLite database so tests run fast and isolated.
For PostgreSQL-specific features (pgvector, JSONB), use integration tests instead.
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Generator
from unittest.mock import MagicMock

import pytest
from sqlalchemy import JSON, create_engine, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import Base

# ---------------------------------------------------------------------------
# Import all models so Base.metadata knows about them
# ---------------------------------------------------------------------------
from app.models.user import User  # noqa: F401
from app.models.client import Client  # noqa: F401
from app.models.client_consent import ClientConsent  # noqa: F401
from app.models.user_subscription import UserSubscription  # noqa: F401
from app.models.processed_webhook_event import ProcessedWebhookEvent  # noqa: F401
from app.models.organization import Organization  # noqa: F401


# ---------------------------------------------------------------------------
# SQLite in-memory engine (fast, isolated per test)
# ---------------------------------------------------------------------------

# SQLite doesn't support UUID natively. We need to handle that.
# Also disable server_defaults that use PostgreSQL functions.
TEST_DATABASE_URL = "sqlite:///:memory:"


def _create_test_engine():
    engine = create_engine(TEST_DATABASE_URL, echo=False)

    # Enable foreign key support in SQLite
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    # Map PostgreSQL-specific types to SQLite-compatible equivalents
    # so Base.metadata.create_all works on the in-memory SQLite engine.
    try:
        from pgvector.sqlalchemy import Vector as VECTOR_TYPE
    except ImportError:
        VECTOR_TYPE = None

    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, JSONB):
                column.type = JSON()
            # pgvector columns can't be created in SQLite — swap to String
            if VECTOR_TYPE is not None and isinstance(column.type, VECTOR_TYPE):
                from sqlalchemy import String
                column.type = String()

    return engine


@pytest.fixture
def engine():
    """Create a fresh in-memory SQLite engine for each test."""
    eng = _create_test_engine()
    Base.metadata.create_all(bind=eng)
    yield eng
    Base.metadata.drop_all(bind=eng)
    eng.dispose()


@pytest.fixture
def db(engine) -> Generator[Session, None, None]:
    """Provide a transactional database session that rolls back after each test."""
    TestSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = TestSession()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


# ---------------------------------------------------------------------------
# Model factories
# ---------------------------------------------------------------------------

def make_user(
    db: Session,
    *,
    clerk_id: str | None = None,
    email: str | None = None,
) -> User:
    """Create and persist a User."""
    user = User(
        id=uuid.uuid4(),
        clerk_id=clerk_id or f"user_{uuid.uuid4().hex[:12]}",
        email=email or f"test-{uuid.uuid4().hex[:8]}@example.com",
        first_name="Test",
        last_name="User",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.flush()
    return user


def make_org(
    db: Session,
    *,
    owner_user_id: str = "user_test",
    name: str = "Test Org",
    org_type: str = "personal",
) -> Organization:
    """Create and persist an Organization."""
    org = Organization(
        id=uuid.uuid4(),
        name=name,
        slug=f"test-org-{uuid.uuid4().hex[:8]}",
        owner_user_id=owner_user_id,
        org_type=org_type,
        max_members=5,
        settings={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(org)
    db.flush()
    return org


def make_client(
    db: Session,
    owner: User,
    *,
    name: str = "Test Client",
    org: Organization | None = None,
    is_tax_preparer: bool | None = None,
    consent_status: str = "not_required",
    has_tax_documents: bool = False,
) -> Client:
    """Create and persist a Client."""
    client = Client(
        id=uuid.uuid4(),
        owner_id=owner.id,
        org_id=org.id if org else None,
        name=name,
        email=f"client-{uuid.uuid4().hex[:8]}@example.com",
        is_tax_preparer=is_tax_preparer,
        consent_status=consent_status,
        has_tax_documents=has_tax_documents,
        data_handling_acknowledged=False,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(client)
    db.flush()
    return client


def make_consent(
    db: Session,
    client: Client,
    user_id: str,
    *,
    consent_type: str = "full_7216",
    status: str = "pending",
    consent_tier: str = "full_7216",
    signing_token: str | None = None,
    signing_token_expires_at: datetime | None = None,
    expiration_date: datetime | None = None,
) -> ClientConsent:
    """Create and persist a ClientConsent record."""
    consent = ClientConsent(
        id=uuid.uuid4(),
        client_id=client.id,
        user_id=user_id,
        consent_type=consent_type,
        status=status,
        consent_tier=consent_tier,
        signing_token=signing_token,
        signing_token_expires_at=signing_token_expires_at,
        expiration_date=expiration_date,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(consent)
    db.flush()
    return consent


def make_subscription(
    db: Session,
    user_id: str,
    *,
    org_id: uuid.UUID | None = None,
    tier: str = "free",
    stripe_customer_id: str | None = None,
    stripe_subscription_id: str | None = None,
    stripe_status: str = "none",
    addon_seats: int = 0,
) -> UserSubscription:
    """Create and persist a UserSubscription."""
    sub = UserSubscription(
        id=uuid.uuid4(),
        user_id=user_id,
        org_id=org_id,
        tier=tier,
        strategic_queries_limit=0,
        strategic_queries_used=0,
        billing_period_start=datetime.now(timezone.utc),
        stripe_customer_id=stripe_customer_id,
        stripe_subscription_id=stripe_subscription_id,
        stripe_status=stripe_status,
        addon_seats=addon_seats,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(sub)
    db.flush()
    return sub


# ---------------------------------------------------------------------------
# Stripe mock helpers
# ---------------------------------------------------------------------------

def make_stripe_event(event_type: str, data: dict, event_id: str | None = None) -> dict:
    """Build a fake Stripe event dict matching the shape construct_event returns."""
    return {
        "id": event_id or f"evt_{uuid.uuid4().hex[:24]}",
        "type": event_type,
        "data": {"object": data},
    }


def make_checkout_session_data(
    *,
    customer_id: str = "cus_test123",
    subscription_id: str = "sub_test123",
    metadata: dict | None = None,
) -> dict:
    """Build fake checkout.session.completed data."""
    return {
        "customer": customer_id,
        "subscription": subscription_id,
        "metadata": metadata or {"user_id": "user_test", "tier": "starter"},
        "mode": "subscription",
    }


def make_subscription_data(
    *,
    subscription_id: str = "sub_test123",
    customer_id: str = "cus_test123",
    status: str = "active",
    price_id: str = "price_starter_monthly",
    interval: str = "month",
    addon_quantity: int = 0,
) -> dict:
    """Build fake customer.subscription.updated/deleted data."""
    items = [
        {
            "price": {
                "id": price_id,
                "recurring": {"interval": interval},
            },
            "quantity": 1,
        }
    ]
    if addon_quantity > 0:
        items.append({
            "price": {
                "id": "price_addon_seat_monthly",
                "recurring": {"interval": interval},
            },
            "quantity": addon_quantity,
        })
    return {
        "id": subscription_id,
        "customer": customer_id,
        "status": status,
        "items": {"data": items},
        "metadata": {"user_id": "user_test", "org_id": str(uuid.uuid4())},
    }


def make_invoice_data(
    *,
    subscription_id: str = "sub_test123",
    customer_id: str = "cus_test123",
) -> dict:
    """Build fake invoice.payment_failed data."""
    return {
        "subscription": subscription_id,
        "customer": customer_id,
    }

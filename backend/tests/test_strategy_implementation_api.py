"""
Tests for strategy implementation task API endpoints.

Uses TestClient with dependency overrides for auth and DB session.
"""

import uuid
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

# Import all models so Base.metadata knows about every table
from app.models import *  # noqa: F401, F403
from app.models.action_item import ActionItem
from app.models.client_strategy_status import ClientStrategyStatus
from app.models.strategy_implementation_task import StrategyImplementationTask
from app.models.tax_strategy import TaxStrategy

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.services.auth_context import AuthContext, get_auth
from main import app
from tests.conftest import _create_test_engine, make_client, make_org, make_user


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _seed_strategy_and_templates(db: Session) -> TaxStrategy:
    """Create a TaxStrategy with 7 implementation task templates."""
    strategy = TaxStrategy(
        id=uuid.uuid4(),
        name="Test Strategy (Augusta Rule)",
        category="business",
        description="Test strategy",
        required_flags=[],
        display_order=1,
        is_active=True,
    )
    db.add(strategy)
    db.flush()

    templates = [
        ("Verify eligibility", "cpa", None, 0, 1),
        ("Establish business purpose", "cpa", None, 7, 2),
        ("Get comparable quotes", "cpa", None, 14, 3),
        ("Draft rental agreement", "cpa", None, 21, 4),
        ("Document meetings", "client", None, 30, 5),
        ("Issue 1099-MISC", "cpa", None, 365, 6),
        ("Apply exclusion on 1040", "cpa", None, 365, 7),
    ]
    for task_name, role, ext_label, lead_days, order in templates:
        tmpl = StrategyImplementationTask(
            id=uuid.uuid4(),
            strategy_id=strategy.id,
            task_name=task_name,
            default_owner_role=role,
            default_owner_external_label=ext_label,
            default_lead_days=lead_days,
            required_documents=[],
            display_order=order,
            is_active=True,
        )
        db.add(tmpl)
    db.flush()
    return strategy


def _make_css(
    db: Session, client_id, strategy_id, tax_year: int, status: str = "not_reviewed"
) -> ClientStrategyStatus:
    css = ClientStrategyStatus(
        id=uuid.uuid4(),
        client_id=client_id,
        strategy_id=strategy_id,
        tax_year=tax_year,
        status=status,
    )
    db.add(css)
    db.flush()
    return css


@pytest.fixture
def setup():
    """Create user, org, client, strategy, and return a test client with dependency overrides."""
    # Use a file-based SQLite DB to allow cross-thread access from TestClient
    engine = create_engine(
        "sqlite:///test_api.db", echo=False,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    # Get SQLite-compatible metadata copy (type swaps applied on copy, not Base.metadata)
    _, metadata = _create_test_engine()

    metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    db = TestSession()

    user = make_user(db)
    org = make_org(db, owner_user_id=user.clerk_id)
    client = make_client(db, user, org=org)
    strategy = _seed_strategy_and_templates(db)
    db.commit()

    fake_auth = AuthContext(
        user_id=user.clerk_id,
        org_id=org.id,
        org_role="admin",
        is_personal_org=False,
    )

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_auth] = lambda: fake_auth

    test_client = TestClient(app)
    yield {
        "client": test_client,
        "db": db,
        "user": user,
        "org": org,
        "app_client": client,
        "strategy": strategy,
    }

    app.dependency_overrides.clear()
    db.close()
    metadata.drop_all(bind=engine)
    engine.dispose()


# ---------------------------------------------------------------------------
# Test 1: GET /implementation-tasks — returns 7 templates
# ---------------------------------------------------------------------------


def test_list_implementation_tasks(setup):
    c = setup["client"]
    strategy = setup["strategy"]

    resp = c.get(f"/api/strategies/{strategy.id}/implementation-tasks")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 7
    assert data[0]["task_name"] == "Verify eligibility"
    assert data[0]["display_order"] == 1
    assert data[6]["display_order"] == 7

    # Verify all required fields present
    for task in data:
        assert "id" in task
        assert "strategy_id" in task
        assert "default_owner_role" in task
        assert "default_lead_days" in task


def test_list_implementation_tasks_unknown_strategy(setup):
    c = setup["client"]
    resp = c.get(f"/api/strategies/{uuid.uuid4()}/implementation-tasks")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test 2: GET /implementation-progress — empty before materialization
# ---------------------------------------------------------------------------


def test_implementation_progress_empty(setup):
    c = setup["client"]
    client_obj = setup["app_client"]
    strategy = setup["strategy"]

    resp = c.get(
        f"/api/clients/{client_obj.id}/strategies/{strategy.id}/implementation-progress",
        params={"year": 2024},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["completed"] == 0
    assert data["tasks"] == []


# ---------------------------------------------------------------------------
# Test 3: GET /implementation-progress — after materialization
# ---------------------------------------------------------------------------


def test_implementation_progress_after_materialize(setup):
    c = setup["client"]
    db = setup["db"]
    client_obj = setup["app_client"]
    strategy = setup["strategy"]
    user = setup["user"]

    # Set up CSS and materialize
    _make_css(db, client_obj.id, strategy.id, 2024, "not_reviewed")
    db.commit()

    from app.services.strategy_service import update_strategy_status

    update_strategy_status(
        db, client_obj.id, strategy.id, 2024,
        new_status="recommended", user_id=user.clerk_id,
    )

    resp = c.get(
        f"/api/clients/{client_obj.id}/strategies/{strategy.id}/implementation-progress",
        params={"year": 2024},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 7
    assert data["completed"] == 0
    assert data["by_owner_role"]["cpa"]["total"] == 6
    assert data["by_owner_role"]["client"]["total"] == 1


# ---------------------------------------------------------------------------
# Test 4: POST /regenerate — no-op after auto-materialization
# ---------------------------------------------------------------------------


def test_regenerate_noop(setup):
    c = setup["client"]
    db = setup["db"]
    client_obj = setup["app_client"]
    strategy = setup["strategy"]
    user = setup["user"]

    _make_css(db, client_obj.id, strategy.id, 2024, "not_reviewed")
    db.commit()

    from app.services.strategy_service import update_strategy_status

    update_strategy_status(
        db, client_obj.id, strategy.id, 2024,
        new_status="recommended", user_id=user.clerk_id,
    )

    resp = c.post(
        f"/api/clients/{client_obj.id}/strategies/{strategy.id}/implementation-tasks/regenerate",
        params={"year": 2024},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["new_tasks_created"] == 0
    assert "already materialized" in data["message"]


# ---------------------------------------------------------------------------
# Test 5: POST /regenerate — after archive creates 7 new
# ---------------------------------------------------------------------------


def test_regenerate_after_archive(setup):
    c = setup["client"]
    db = setup["db"]
    client_obj = setup["app_client"]
    strategy = setup["strategy"]
    user = setup["user"]

    _make_css(db, client_obj.id, strategy.id, 2024, "not_reviewed")
    db.commit()

    from app.services.strategy_service import update_strategy_status

    update_strategy_status(
        db, client_obj.id, strategy.id, 2024,
        new_status="recommended", user_id=user.clerk_id,
    )

    # Archive
    resp = c.post(
        f"/api/clients/{client_obj.id}/strategies/{strategy.id}/implementation-tasks/archive",
        params={"year": 2024},
    )
    assert resp.status_code == 200
    assert resp.json()["archived_count"] == 7

    # Regenerate
    resp = c.post(
        f"/api/clients/{client_obj.id}/strategies/{strategy.id}/implementation-tasks/regenerate",
        params={"year": 2024},
    )
    assert resp.status_code == 200
    assert resp.json()["new_tasks_created"] == 7


# ---------------------------------------------------------------------------
# Test 6: POST /archive — idempotent
# ---------------------------------------------------------------------------


def test_archive_idempotent(setup):
    c = setup["client"]
    db = setup["db"]
    client_obj = setup["app_client"]
    strategy = setup["strategy"]
    user = setup["user"]

    _make_css(db, client_obj.id, strategy.id, 2024, "not_reviewed")
    db.commit()

    from app.services.strategy_service import update_strategy_status

    update_strategy_status(
        db, client_obj.id, strategy.id, 2024,
        new_status="recommended", user_id=user.clerk_id,
    )

    # First archive
    resp = c.post(
        f"/api/clients/{client_obj.id}/strategies/{strategy.id}/implementation-tasks/archive",
        params={"year": 2024},
    )
    assert resp.status_code == 200
    assert resp.json()["archived_count"] == 7

    # Second archive — idempotent
    resp = c.post(
        f"/api/clients/{client_obj.id}/strategies/{strategy.id}/implementation-tasks/archive",
        params={"year": 2024},
    )
    assert resp.status_code == 200
    assert resp.json()["archived_count"] == 0


# ---------------------------------------------------------------------------
# Test 7: 404 paths
# ---------------------------------------------------------------------------


def test_progress_unknown_client_404(setup):
    """Unknown client_id returns 404 from check_client_access."""
    c = setup["client"]
    strategy = setup["strategy"]

    resp = c.get(
        f"/api/clients/{uuid.uuid4()}/strategies/{strategy.id}/implementation-progress",
        params={"year": 2024},
    )
    # check_client_access raises 403 or 404 depending on implementation
    assert resp.status_code in (403, 404)


def test_regenerate_no_css_404(setup):
    """Regenerate without a client_strategy_status row returns 404."""
    c = setup["client"]
    client_obj = setup["app_client"]
    strategy = setup["strategy"]

    resp = c.post(
        f"/api/clients/{client_obj.id}/strategies/{strategy.id}/implementation-tasks/regenerate",
        params={"year": 2024},
    )
    assert resp.status_code == 404

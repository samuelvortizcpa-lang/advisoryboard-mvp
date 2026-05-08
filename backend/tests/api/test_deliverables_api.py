"""
Tests for deliverable API endpoints (G5-P4).

8 tests total:
- 6 draft tests (TestDraftKickoffMemo)
- 2 send tests (TestSendKickoffMemo)
"""
import os
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.models import *  # noqa: F401, F403
from app.models.cadence_template import CadenceTemplate
from app.models.cadence_template_deliverable import (
    DELIVERABLE_KEY_VALUES,
    CadenceTemplateDeliverable,
)
from app.models.client_cadence import ClientCadence
from app.models.client_communication import ClientCommunication
from app.models.client_strategy_status import ClientStrategyStatus
from app.models.tax_strategy import TaxStrategy

from app.core.database import get_db
from app.services.auth_context import AuthContext, get_auth
from main import app
from tests.conftest import _create_test_engine, make_client, make_org, make_user


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DB_PATH = "test_deliverables_api.db"


def _enable_kickoff_memo(db: Session, client_id):
    """Seed a cadence template with kickoff_memo enabled and assign to client."""
    tpl = CadenceTemplate(
        id=uuid.uuid4(),
        name="Kickoff Enabled",
        is_system=False,
        is_active=True,
        org_id=None,
    )
    db.add(tpl)
    db.flush()
    for key in DELIVERABLE_KEY_VALUES:
        db.add(CadenceTemplateDeliverable(
            id=uuid.uuid4(),
            template_id=tpl.id,
            deliverable_key=key,
            is_enabled=True,
        ))
    db.flush()
    db.add(ClientCadence(
        id=uuid.uuid4(),
        client_id=client_id,
        template_id=tpl.id,
        overrides={},
    ))
    db.flush()


def _disable_kickoff_memo(db: Session, client_id):
    """Seed a cadence template with kickoff_memo disabled and assign to client."""
    tpl = CadenceTemplate(
        id=uuid.uuid4(),
        name="Kickoff Disabled",
        is_system=False,
        is_active=True,
        org_id=None,
    )
    db.add(tpl)
    db.flush()
    for key in DELIVERABLE_KEY_VALUES:
        db.add(CadenceTemplateDeliverable(
            id=uuid.uuid4(),
            template_id=tpl.id,
            deliverable_key=key,
            is_enabled=(key != "kickoff_memo"),
        ))
    db.flush()
    db.add(ClientCadence(
        id=uuid.uuid4(),
        client_id=client_id,
        template_id=tpl.id,
        overrides={},
    ))
    db.flush()


def _seed_recommended_strategy(db: Session, client_id):
    """Seed one recommended strategy for a client."""
    from datetime import datetime
    strategy = TaxStrategy(
        id=uuid.uuid4(),
        name="Augusta Rule",
        category="income",
        required_flags=[],
    )
    db.add(strategy)
    db.flush()
    db.add(ClientStrategyStatus(
        id=uuid.uuid4(),
        client_id=client_id,
        strategy_id=strategy.id,
        tax_year=datetime.now().year,
        status="recommended",
    ))
    db.flush()


def _mock_openai_class(mock_cls):
    """Configure a mock AsyncOpenAI class to return a canned draft."""
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=MagicMock(
            choices=[MagicMock(message=MagicMock(content="Draft body text"))]
        )
    )
    mock_cls.return_value = mock_client


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def setup():
    """Provide TestClient, db, user, org, client with auth overrides."""
    engine = create_engine(
        f"sqlite:///{DB_PATH}", echo=False,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    _, metadata = _create_test_engine()
    metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    db = TestSession()

    user = make_user(db)
    org = make_org(db, owner_user_id=user.clerk_id)
    client = make_client(db, user, org=org)
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
        "http": test_client,
        "db": db,
        "user": user,
        "org": org,
        "client": client,
        "auth": fake_auth,
    }

    app.dependency_overrides.clear()
    db.close()
    metadata.drop_all(bind=engine)
    engine.dispose()
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)


@pytest.fixture
def setup_cross_org(setup):
    """Extend setup with a second org + user for cross-org tests."""
    db = setup["db"]
    user_b = make_user(db)
    org_b = make_org(db, owner_user_id=user_b.clerk_id, name="Org B")
    client_b = make_client(db, user_b, org=org_b)
    db.commit()

    auth_b = AuthContext(
        user_id=user_b.clerk_id,
        org_id=org_b.id,
        org_role="admin",
        is_personal_org=False,
    )

    return {**setup, "user_b": user_b, "org_b": org_b, "client_b": client_b, "auth_b": auth_b}


@pytest.fixture
def setup_with_member(setup):
    """Extend setup with a non-admin (member) auth context."""
    member_user = make_user(setup["db"])
    setup["db"].commit()
    member_auth = AuthContext(
        user_id=member_user.clerk_id,
        org_id=setup["org"].id,
        org_role="member",
        is_personal_org=False,
    )
    return {**setup, "member_user": member_user, "member_auth": member_auth}


def _draft_url(client_id):
    return f"/api/clients/{client_id}/deliverables/kickoff-memo/draft"


def _send_url(client_id):
    return f"/api/clients/{client_id}/deliverables/kickoff-memo/send"


def _with_auth(setup_dict, auth_override):
    """Temporarily swap the auth override, return the test client."""
    app.dependency_overrides[get_auth] = lambda: auth_override
    return setup_dict["http"]


# ---------------------------------------------------------------------------
# POST /api/clients/{client_id}/deliverables/kickoff-memo/draft
# ---------------------------------------------------------------------------


class TestDraftKickoffMemo:

    @patch("app.services.engagement_deliverable_service.AsyncOpenAI")
    def test_draft_kickoff_memo_200_admin_enabled_with_strategies(
        self, mock_openai_cls, setup
    ):
        _mock_openai_class(mock_openai_cls)
        db, client = setup["db"], setup["client"]
        _enable_kickoff_memo(db, client.id)
        _seed_recommended_strategy(db, client.id)
        db.commit()

        r = setup["http"].post(_draft_url(client.id), json={"tax_year": 2026})
        assert r.status_code == 200
        data = r.json()
        # Contract shape: response has the right keys with the right types
        assert isinstance(data["subject"], str) and data["subject"]
        assert data["body"] == "Draft body text"
        assert isinstance(data["references"], dict)
        assert isinstance(data["references"].get("strategies"), list)
        assert isinstance(data["references"].get("tasks"), list)
        assert isinstance(data["warnings"], list)

    @patch("app.services.engagement_deliverable_service.AsyncOpenAI")
    def test_draft_kickoff_memo_200_with_warnings_when_no_recommended_strategies(
        self, mock_openai_cls, setup
    ):
        _mock_openai_class(mock_openai_cls)
        db, client = setup["db"], setup["client"]
        _enable_kickoff_memo(db, client.id)
        # No strategies seeded — warnings expected
        db.commit()

        r = setup["http"].post(_draft_url(client.id), json={"tax_year": 2026})
        assert r.status_code == 200
        data = r.json()
        assert len(data["warnings"]) > 0
        assert data["references"]["strategies"] == []

    def test_draft_kickoff_memo_403_non_admin(self, setup_with_member):
        s = setup_with_member
        http = _with_auth(s, s["member_auth"])
        r = http.post(_draft_url(s["client"].id), json={"tax_year": 2026})
        assert r.status_code == 403

    def test_draft_kickoff_memo_403_cadence_disabled(self, setup):
        db, client = setup["db"], setup["client"]
        _disable_kickoff_memo(db, client.id)
        db.commit()

        r = setup["http"].post(_draft_url(client.id), json={"tax_year": 2026})
        assert r.status_code == 403

    def test_draft_kickoff_memo_403_cross_org_client_id(self, setup_cross_org):
        s = setup_cross_org
        # user_b (org_b) tries to access client in org_a
        http = _with_auth(s, s["auth_b"])
        r = http.post(_draft_url(s["client"].id), json={"tax_year": 2026})
        assert r.status_code == 403

    def test_draft_kickoff_memo_422_invalid_tax_year(self, setup):
        r = setup["http"].post(
            _draft_url(setup["client"].id), json={"tax_year": "not-an-int"}
        )
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/clients/{client_id}/deliverables/kickoff-memo/send
# ---------------------------------------------------------------------------


class TestSendKickoffMemo:

    @patch("app.services.deliverables.kickoff_memo.extract_open_items_from_email")
    def test_send_kickoff_memo_200_writes_communication_row(
        self, mock_extract, setup
    ):
        mock_extract.return_value = []
        db, client = setup["db"], setup["client"]
        _enable_kickoff_memo(db, client.id)
        db.commit()

        r = setup["http"].post(
            _send_url(client.id),
            json={
                "tax_year": 2026,
                "subject": "Kickoff",
                "body": "Body text",
                "recipient_email": "client@example.com",
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert "client_communication_id" in data

        # Verify DB row
        comm = (
            db.query(ClientCommunication)
            .filter(ClientCommunication.client_id == client.id)
            .first()
        )
        assert comm is not None
        assert comm.thread_type == "engagement_year"
        assert comm.recipient_email == "client@example.com"

    def test_send_kickoff_memo_403_cadence_disabled(self, setup):
        db, client = setup["db"], setup["client"]
        _disable_kickoff_memo(db, client.id)
        db.commit()

        r = setup["http"].post(
            _send_url(client.id),
            json={
                "tax_year": 2026,
                "subject": "Kickoff",
                "body": "Body text",
                "recipient_email": "client@example.com",
            },
        )
        assert r.status_code == 403

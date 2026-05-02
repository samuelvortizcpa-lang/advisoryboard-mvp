"""
Tests for per-client cadence API endpoints (G4-P3a).

Uses TestClient with dependency overrides for auth and DB session.
"""
import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.models import *  # noqa: F401, F403
from app.models.cadence_template import CadenceTemplate
from app.models.cadence_template_deliverable import (
    CadenceTemplateDeliverable,
    DELIVERABLE_KEY_VALUES,
)

from app.core.database import get_db
from app.services import cadence_service
from app.services.auth_context import AuthContext, get_auth
from main import app
from tests.conftest import _create_test_engine, make_client, make_org, make_user


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DB_PATH = "test_cadence_api.db"


def _seed_system_templates(db: Session):
    """Seed 3 system templates with 7 deliverable rows each."""
    full = CadenceTemplate(
        id=uuid.uuid4(), name="Full Cadence",
        is_system=True, is_active=True, org_id=None,
    )
    empty = CadenceTemplate(
        id=uuid.uuid4(), name="Empty",
        is_system=True, is_active=True, org_id=None,
    )
    quarterly = CadenceTemplate(
        id=uuid.uuid4(), name="Quarterly Only",
        is_system=True, is_active=True, org_id=None,
    )
    db.add_all([full, empty, quarterly])
    db.flush()
    for key in DELIVERABLE_KEY_VALUES:
        db.add(CadenceTemplateDeliverable(
            template_id=full.id, deliverable_key=key, is_enabled=True,
        ))
        db.add(CadenceTemplateDeliverable(
            template_id=empty.id, deliverable_key=key, is_enabled=False,
        ))
        db.add(CadenceTemplateDeliverable(
            template_id=quarterly.id, deliverable_key=key,
            is_enabled=(key in ("quarterly_memo", "year_end_recap")),
        ))
    db.flush()
    return full, empty, quarterly


@pytest.fixture
def setup():
    """Provide TestClient, db, user, org, client, templates with auth overrides."""
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
    full, empty, quarterly = _seed_system_templates(db)
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
        "full": full,
        "empty": empty,
        "quarterly": quarterly,
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


def _url(client_id, suffix=""):
    return f"/api/clients/{client_id}/cadence{suffix}"


def _with_auth(setup_dict, auth_override):
    """Temporarily swap the auth override, return the test client."""
    app.dependency_overrides[get_auth] = lambda: auth_override
    return setup_dict["http"]


def _without_auth(setup_dict):
    """Remove auth override so real get_auth fires (→ 401)."""
    app.dependency_overrides.pop(get_auth, None)
    return setup_dict["http"]


# ---------------------------------------------------------------------------
# GET /api/clients/{client_id}/cadence
# ---------------------------------------------------------------------------


class TestGetCadence:

    def test_get_cadence_returns_detail_when_assigned(self, setup):
        db, client, full = setup["db"], setup["client"], setup["full"]
        cadence_service.assign_cadence(db, client.id, full.id, setup["user"].clerk_id)
        r = setup["http"].get(_url(client.id))
        assert r.status_code == 200
        data = r.json()
        assert data["template_name"] == "Full Cadence"
        assert data["overrides"] == {}
        assert len(data["effective_flags"]) == 7
        for v in data["effective_flags"].values():
            assert v is True

    def test_get_cadence_returns_404_when_no_cadence(self, setup):
        r = setup["http"].get(_url(setup["client"].id))
        assert r.status_code == 404

    def test_get_cadence_returns_403_without_auth(self, setup):
        http = _without_auth(setup)
        r = http.get(_url(setup["client"].id))
        assert r.status_code == 403

    def test_get_cadence_returns_403_cross_org(self, setup_cross_org):
        s = setup_cross_org
        # user_b (org_b) tries to access client in org_a
        http = _with_auth(s, s["auth_b"])
        r = http.get(_url(s["client"].id))
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# PUT /api/clients/{client_id}/cadence
# ---------------------------------------------------------------------------


class TestPutCadence:

    def test_put_cadence_first_assign_returns_200(self, setup):
        r = setup["http"].put(
            _url(setup["client"].id),
            json={"template_id": str(setup["full"].id)},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["template_name"] == "Full Cadence"
        assert data["overrides"] == {}
        assert len(data["effective_flags"]) == 7

    def test_put_cadence_reassign_same_template_idempotent(self, setup):
        db, client, full = setup["db"], setup["client"], setup["full"]
        cadence_service.assign_cadence(db, client.id, full.id, setup["user"].clerk_id)
        r = setup["http"].put(
            _url(client.id), json={"template_id": str(full.id)},
        )
        assert r.status_code == 200
        assert r.json()["template_name"] == "Full Cadence"

    def test_put_cadence_reassign_resets_overrides(self, setup):
        db, client, full, quarterly = setup["db"], setup["client"], setup["full"], setup["quarterly"]
        uid = setup["user"].clerk_id
        cadence_service.assign_cadence(db, client.id, full.id, uid)
        cadence_service.update_overrides(db, client.id, {"progress_note": False}, uid)
        r = setup["http"].put(
            _url(client.id), json={"template_id": str(quarterly.id)},
        )
        assert r.status_code == 200
        assert r.json()["overrides"] == {}

    def test_put_cadence_inactive_template_returns_422(self, setup):
        db = setup["db"]
        all_true = {k: True for k in DELIVERABLE_KEY_VALUES}
        custom = cadence_service.create_custom_template(
            db, setup["org"].id, "Temp", None, all_true, setup["user"].clerk_id,
        )
        cadence_service.deactivate_template(db, custom.id, setup["user"].clerk_id, org_id=setup["org"].id)
        r = setup["http"].put(
            _url(setup["client"].id), json={"template_id": str(custom.id)},
        )
        assert r.status_code == 422

    def test_put_cadence_returns_403_without_auth(self, setup):
        http = _without_auth(setup)
        r = http.put(
            _url(setup["client"].id),
            json={"template_id": str(setup["full"].id)},
        )
        assert r.status_code == 403

    def test_put_cadence_returns_403_cross_org(self, setup_cross_org):
        s = setup_cross_org
        http = _with_auth(s, s["auth_b"])
        r = http.put(
            _url(s["client"].id), json={"template_id": str(s["full"].id)},
        )
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# PATCH /api/clients/{client_id}/cadence/overrides
# ---------------------------------------------------------------------------


class TestPatchOverrides:

    def test_patch_overrides_success_single_key(self, setup):
        db, client, full = setup["db"], setup["client"], setup["full"]
        cadence_service.assign_cadence(db, client.id, full.id, setup["user"].clerk_id)
        r = setup["http"].patch(
            _url(client.id, "/overrides"),
            json={"overrides": {"progress_note": False}},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["overrides"]["progress_note"] is False
        assert data["effective_flags"]["progress_note"] is False
        # Other 6 keys still True
        for k, v in data["effective_flags"].items():
            if k != "progress_note":
                assert v is True

    def test_patch_overrides_merge_semantics(self, setup):
        db, client, full = setup["db"], setup["client"], setup["full"]
        uid = setup["user"].clerk_id
        cadence_service.assign_cadence(db, client.id, full.id, uid)
        setup["http"].patch(
            _url(client.id, "/overrides"),
            json={"overrides": {"progress_note": False}},
        )
        r = setup["http"].patch(
            _url(client.id, "/overrides"),
            json={"overrides": {"quarterly_memo": False}},
        )
        assert r.status_code == 200
        overrides = r.json()["overrides"]
        assert overrides["progress_note"] is False
        assert overrides["quarterly_memo"] is False

    def test_patch_overrides_no_cadence_returns_409(self, setup):
        r = setup["http"].patch(
            _url(setup["client"].id, "/overrides"),
            json={"overrides": {"progress_note": False}},
        )
        assert r.status_code == 409

    def test_patch_overrides_invalid_key_returns_422(self, setup):
        db, client, full = setup["db"], setup["client"], setup["full"]
        cadence_service.assign_cadence(db, client.id, full.id, setup["user"].clerk_id)
        r = setup["http"].patch(
            _url(client.id, "/overrides"),
            json={"overrides": {"not_a_real_key": False}},
        )
        assert r.status_code == 422

    def test_patch_overrides_non_bool_value_returns_422(self, setup):
        db, client, full = setup["db"], setup["client"], setup["full"]
        cadence_service.assign_cadence(db, client.id, full.id, setup["user"].clerk_id)
        r = setup["http"].patch(
            _url(client.id, "/overrides"),
            json={"overrides": {"progress_note": 0}},
        )
        assert r.status_code == 422

    def test_patch_overrides_null_value_returns_422(self, setup):
        db, client, full = setup["db"], setup["client"], setup["full"]
        cadence_service.assign_cadence(db, client.id, full.id, setup["user"].clerk_id)
        r = setup["http"].patch(
            _url(client.id, "/overrides"),
            json={"overrides": {"progress_note": None}},
        )
        assert r.status_code == 422

    def test_patch_overrides_returns_403_without_auth(self, setup):
        http = _without_auth(setup)
        r = http.patch(
            _url(setup["client"].id, "/overrides"),
            json={"overrides": {"progress_note": False}},
        )
        assert r.status_code == 403

    def test_patch_overrides_returns_403_cross_org(self, setup_cross_org):
        s = setup_cross_org
        http = _with_auth(s, s["auth_b"])
        r = http.patch(
            _url(s["client"].id, "/overrides"),
            json={"overrides": {"progress_note": False}},
        )
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# GET /api/clients/{client_id}/cadence/enabled-deliverables
# ---------------------------------------------------------------------------


class TestEnabledDeliverables:

    def test_enabled_deliverables_full_cadence(self, setup):
        db, client, full = setup["db"], setup["client"], setup["full"]
        cadence_service.assign_cadence(db, client.id, full.id, setup["user"].clerk_id)
        r = setup["http"].get(_url(client.id, "/enabled-deliverables"))
        assert r.status_code == 200
        assert len(r.json()["enabled"]) == 7

    def test_enabled_deliverables_respects_overrides(self, setup):
        db, client, full = setup["db"], setup["client"], setup["full"]
        uid = setup["user"].clerk_id
        cadence_service.assign_cadence(db, client.id, full.id, uid)
        cadence_service.update_overrides(db, client.id, {"progress_note": False}, uid)
        r = setup["http"].get(_url(client.id, "/enabled-deliverables"))
        assert r.status_code == 200
        enabled = r.json()["enabled"]
        assert len(enabled) == 6
        assert "progress_note" not in enabled

    def test_enabled_deliverables_empty_when_no_cadence(self, setup):
        r = setup["http"].get(_url(setup["client"].id, "/enabled-deliverables"))
        assert r.status_code == 200
        assert r.json()["enabled"] == []

    def test_enabled_deliverables_returns_403_without_auth(self, setup):
        http = _without_auth(setup)
        r = http.get(_url(setup["client"].id, "/enabled-deliverables"))
        assert r.status_code == 403

    def test_enabled_deliverables_returns_403_cross_org(self, setup_cross_org):
        s = setup_cross_org
        http = _with_auth(s, s["auth_b"])
        r = http.get(_url(s["client"].id, "/enabled-deliverables"))
        assert r.status_code == 403

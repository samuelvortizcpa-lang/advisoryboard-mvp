"""
Tests for organization API endpoints — default_cadence_template_id exposure.

Uses TestClient with dependency overrides for auth and DB session.
"""
import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.models import *  # noqa: F401, F403
from app.models.cadence_template import CadenceTemplate
from app.models.cadence_template_deliverable import (
    CadenceTemplateDeliverable,
    DELIVERABLE_KEY_VALUES,
)
from app.models.organization_member import OrganizationMember

from app.core.database import get_db
from app.services import cadence_service
from app.services.auth_context import AuthContext, get_auth
from main import app
from tests.conftest import _create_test_engine, make_org, make_user


DB_PATH = "test_organization_api.db"


def _seed_template(db):
    """Seed a single system template with all 7 deliverables enabled."""
    tpl = CadenceTemplate(
        id=uuid.uuid4(), name="Full Cadence",
        is_system=True, is_active=True, org_id=None,
    )
    db.add(tpl)
    db.flush()
    for key in DELIVERABLE_KEY_VALUES:
        db.add(CadenceTemplateDeliverable(
            template_id=tpl.id, deliverable_key=key, is_enabled=True,
        ))
    db.flush()
    return tpl


def _add_membership(db, org, user, role="admin"):
    """Create an active OrganizationMember row."""
    member = OrganizationMember(
        id=uuid.uuid4(),
        org_id=org.id,
        user_id=user.clerk_id,
        role=role,
        is_active=True,
    )
    db.add(member)
    db.flush()
    return member


@pytest.fixture
def setup():
    """Provide TestClient, db, user, org, template with auth overrides."""
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
    org = make_org(db, owner_user_id=user.clerk_id, org_type="firm")
    _add_membership(db, org, user, role="admin")
    tpl = _seed_template(db)
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
        "tpl": tpl,
        "auth": fake_auth,
    }

    app.dependency_overrides.clear()
    db.close()
    metadata.drop_all(bind=engine)
    engine.dispose()
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)


class TestDefaultCadenceTemplateId:
    """Verify default_cadence_template_id is exposed on org endpoints."""

    def test_list_orgs_returns_default_cadence_template_id(self, setup):
        http, db, user, org, tpl = setup["http"], setup["db"], setup["user"], setup["org"], setup["tpl"]

        # Before setting firm default — field should be null
        resp = http.get("/api/organizations")
        assert resp.status_code == 200
        orgs = resp.json()
        match = [o for o in orgs if o["id"] == str(org.id)]
        assert len(match) == 1
        assert match[0]["default_cadence_template_id"] is None

        # Set firm default
        cadence_service.set_firm_default(db, org.id, tpl.id, user.clerk_id)
        db.commit()

        # After setting firm default — field should have template id
        resp = http.get("/api/organizations")
        assert resp.status_code == 200
        orgs = resp.json()
        match = [o for o in orgs if o["id"] == str(org.id)]
        assert match[0]["default_cadence_template_id"] == str(tpl.id)

    def test_get_org_detail_returns_default_cadence_template_id(self, setup):
        http, db, user, org, tpl = setup["http"], setup["db"], setup["user"], setup["org"], setup["tpl"]

        # Set firm default
        cadence_service.set_firm_default(db, org.id, tpl.id, user.clerk_id)
        db.commit()

        resp = http.get(f"/api/organizations/{org.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["default_cadence_template_id"] == str(tpl.id)

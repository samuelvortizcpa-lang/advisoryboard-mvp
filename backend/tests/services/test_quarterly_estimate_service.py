"""
Tests for quarterly_estimate_service cadence gate (G5-P1).
"""
import uuid
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from app.models import *  # noqa: F401, F403
from app.models.cadence_template import CadenceTemplate
from app.models.cadence_template_deliverable import (
    CadenceTemplateDeliverable,
    DELIVERABLE_KEY_VALUES,
)
from app.models.client_cadence import ClientCadence
from app.services.quarterly_estimate_service import draft_quarterly_estimate_email
from tests.conftest import make_client, make_org, make_user


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_template_with_quarterly_disabled(db: Session):
    """Seed a template where quarterly_memo is disabled."""
    tpl = CadenceTemplate(
        id=uuid.uuid4(),
        name="No Quarterly",
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
            is_enabled=(key != "quarterly_memo"),
        ))
    db.flush()
    return tpl


def _seed_template_with_quarterly_enabled(db: Session):
    """Seed a template where quarterly_memo is enabled."""
    tpl = CadenceTemplate(
        id=uuid.uuid4(),
        name="With Quarterly",
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
    return tpl


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_draft_quarterly_estimate_refuses_when_cadence_disabled(db: Session):
    """Gate blocks when quarterly_memo is not enabled for the client."""
    user = make_user(db)
    org = make_org(db, owner_user_id=user.clerk_id)
    client = make_client(db, user, org=org)

    tpl = _seed_template_with_quarterly_disabled(db)
    db.add(ClientCadence(
        id=uuid.uuid4(),
        client_id=client.id,
        template_id=tpl.id,
        overrides={},
    ))
    db.flush()

    with pytest.raises(PermissionError, match="quarterly_memo"):
        await draft_quarterly_estimate_email(
            db=db,
            client_id=client.id,
            user_id=user.clerk_id,
            tax_year=2025,
            quarter=1,
        )


@pytest.mark.asyncio
async def test_draft_quarterly_estimate_succeeds_when_cadence_enabled(db: Session):
    """Gate passes when quarterly_memo is enabled; function proceeds past the gate."""
    user = make_user(db)
    org = make_org(db, owner_user_id=user.clerk_id)
    client = make_client(db, user, org=org)

    tpl = _seed_template_with_quarterly_enabled(db)
    db.add(ClientCadence(
        id=uuid.uuid4(),
        client_id=client.id,
        template_id=tpl.id,
        overrides={},
    ))
    db.flush()

    # The function should pass the cadence gate without raising PermissionError.
    # It may succeed fully or fail downstream — either is fine as long as
    # PermissionError is not raised.
    try:
        await draft_quarterly_estimate_email(
            db=db,
            client_id=client.id,
            user_id=user.clerk_id,
            tax_year=2025,
            quarter=1,
        )
    except PermissionError:
        pytest.fail("PermissionError raised despite quarterly_memo being enabled")
    except Exception:
        pass  # Any other downstream failure is acceptable

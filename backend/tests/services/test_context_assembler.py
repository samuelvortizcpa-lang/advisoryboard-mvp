"""
Tests for context_assembler ENGAGEMENT_KICKOFF purpose (G5-P2).
"""
import uuid
from datetime import datetime

import pytest
from sqlalchemy.orm import Session

from app.models import *  # noqa: F401, F403
from app.models.action_item import ActionItem
from app.models.client_strategy_status import ClientStrategyStatus
from app.models.tax_strategy import TaxStrategy
from app.services.context_assembler import (
    TOKEN_BUDGETS,
    ContextPurpose,
    assemble_context,
)
from tests.conftest import make_client, make_org, make_user


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_strategies(db: Session, client_id, current_year: int):
    """Seed 3 TaxStrategy + 3 ClientStrategyStatus with different statuses."""
    statuses = ["recommended", "not_recommended", "implemented"]
    for i, status in enumerate(statuses):
        strategy = TaxStrategy(
            id=uuid.uuid4(),
            name=f"Strategy {i}",
            category="income",
            required_flags=[],
        )
        db.add(strategy)
        db.flush()
        db.add(ClientStrategyStatus(
            id=uuid.uuid4(),
            client_id=client_id,
            strategy_id=strategy.id,
            tax_year=current_year,
            status=status,
        ))
    db.flush()


def _seed_action_items(db: Session, client_id):
    """Seed 4 ActionItems with different owner_roles."""
    items = [
        ("Confirm rental records", "client"),
        ("Provide W-2", "client"),
        ("Engineer cost seg study", "third_party"),
        ("Draft engagement letter", "cpa"),
    ]
    for text, role in items:
        db.add(ActionItem(
            id=uuid.uuid4(),
            client_id=client_id,
            text=text,
            status="pending",
            owner_role=role,
        ))
    db.flush()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assembler_engagement_kickoff_returns_recommended_strategies(db: Session):
    """Only strategies with status='recommended' appear in the context."""
    user = make_user(db)
    org = make_org(db, owner_user_id=user.clerk_id)
    client = make_client(db, user, org=org)
    current_year = datetime.now().year

    _seed_strategies(db, client.id, current_year)

    ctx = await assemble_context(
        db,
        client_id=client.id,
        user_id=user.clerk_id,
        purpose=ContextPurpose.ENGAGEMENT_KICKOFF,
    )

    year_key = str(current_year)
    assert year_key in ctx.strategy_status["years"]
    strategies = ctx.strategy_status["years"][year_key]
    assert len(strategies) == 1
    assert strategies[0]["status"] == "recommended"


@pytest.mark.asyncio
async def test_assembler_engagement_kickoff_filters_client_facing_tasks(db: Session):
    """Only action items with owner_role in (client, third_party) appear."""
    user = make_user(db)
    org = make_org(db, owner_user_id=user.clerk_id)
    client = make_client(db, user, org=org)

    _seed_action_items(db, client.id)

    ctx = await assemble_context(
        db,
        client_id=client.id,
        user_id=user.clerk_id,
        purpose=ContextPurpose.ENGAGEMENT_KICKOFF,
    )

    assert len(ctx.action_items) == 3
    roles = {ai["owner_role"] for ai in ctx.action_items}
    assert roles == {"client", "third_party"}
    assert not any(ai["owner_role"] == "cpa" for ai in ctx.action_items)


def test_assembler_engagement_kickoff_respects_token_budget():
    """TOKEN_BUDGETS registers the correct budget for ENGAGEMENT_KICKOFF."""
    assert TOKEN_BUDGETS[ContextPurpose.ENGAGEMENT_KICKOFF] == 6000

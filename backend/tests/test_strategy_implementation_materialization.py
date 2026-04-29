"""
Tests for strategy implementation task materialization.

Covers: materialize on recommended transition, idempotency,
re-recommendation, archive + re-materialize, progress meter,
and notification filter.
"""

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy.orm import Session

# Ensure all required models are registered with Base.metadata
from app.models.action_item import ActionItem  # noqa: F401
from app.models.client_assignment import ClientAssignment  # noqa: F401
from app.models.client_strategy_status import ClientStrategyStatus  # noqa: F401
from app.models.journal_entry import JournalEntry  # noqa: F401
from app.models.strategy_implementation_task import StrategyImplementationTask  # noqa: F401
from app.models.tax_strategy import TaxStrategy  # noqa: F401

from app.services.strategy_service import (
    archive_implementation_tasks,
    get_implementation_progress,
    materialize_implementation_tasks,
    update_strategy_status,
)
from tests.conftest import make_client, make_org, make_user


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _seed_strategy_and_templates(db: Session) -> TaxStrategy:
    """Create a TaxStrategy with 7 implementation task templates (matches Augusta Rule shape)."""
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
    db: Session, client_id: uuid.UUID, strategy_id: uuid.UUID, tax_year: int, status: str = "not_reviewed"
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


# ---------------------------------------------------------------------------
# Test 1: Happy path — recommended transition creates 7 tasks
# ---------------------------------------------------------------------------


def test_materialize_on_recommended_transition(db: Session):
    user = make_user(db)
    org = make_org(db, owner_user_id=user.clerk_id)
    client = make_client(db, user, org=org)
    strategy = _seed_strategy_and_templates(db)
    db.commit()

    # Set initial status to not_reviewed
    _make_css(db, client.id, strategy.id, 2024, "not_reviewed")
    db.commit()

    # Transition to recommended — should trigger materialization
    update_strategy_status(
        db, client.id, strategy.id, 2024,
        new_status="recommended", user_id=user.clerk_id,
    )

    # Verify 7 action_items created
    items = db.query(ActionItem).filter(
        ActionItem.client_id == client.id,
        ActionItem.source == "strategy_implementation",
    ).all()
    assert len(items) == 7

    # Verify linkage
    css = db.query(ClientStrategyStatus).filter(
        ClientStrategyStatus.client_id == client.id,
        ClientStrategyStatus.strategy_id == strategy.id,
    ).first()
    for item in items:
        assert item.strategy_implementation_task_id is not None
        assert item.client_strategy_status_id == css.id

    # Verify owner_role distribution: cpa=6, client=1
    roles = [item.owner_role for item in items]
    assert roles.count("cpa") == 6
    assert roles.count("client") == 1

    # Verify due dates are computed from lead days
    today = date.today()
    lead_0_items = [i for i in items if i.due_date == today]
    assert len(lead_0_items) == 1  # "Verify eligibility" with 0 lead days

    lead_7_items = [i for i in items if i.due_date == today + timedelta(days=7)]
    assert len(lead_7_items) == 1

    # Verify journal entry written
    journals = db.query(JournalEntry).filter(
        JournalEntry.client_id == client.id,
        JournalEntry.title.contains("Generated 7 implementation tasks"),
    ).all()
    assert len(journals) == 1


# ---------------------------------------------------------------------------
# Test 2: Idempotency — re-recommending creates no new tasks
# ---------------------------------------------------------------------------


def test_idempotency_no_duplicate_tasks(db: Session):
    user = make_user(db)
    org = make_org(db, owner_user_id=user.clerk_id)
    client = make_client(db, user, org=org)
    strategy = _seed_strategy_and_templates(db)
    _make_css(db, client.id, strategy.id, 2024, "not_reviewed")
    db.commit()

    # First transition → recommended
    update_strategy_status(
        db, client.id, strategy.id, 2024,
        new_status="recommended", user_id=user.clerk_id,
    )
    count_after_first = db.query(ActionItem).filter(
        ActionItem.client_id == client.id,
        ActionItem.source == "strategy_implementation",
    ).count()
    assert count_after_first == 7

    # Second call to recommended (no-op — already recommended)
    update_strategy_status(
        db, client.id, strategy.id, 2024,
        new_status="recommended", user_id=user.clerk_id,
    )
    count_after_second = db.query(ActionItem).filter(
        ActionItem.client_id == client.id,
        ActionItem.source == "strategy_implementation",
    ).count()
    assert count_after_second == 7  # No duplicates


# ---------------------------------------------------------------------------
# Test 3: Re-recommendation after demote — no new tasks
# ---------------------------------------------------------------------------


def test_re_recommendation_after_demote_no_new_tasks(db: Session):
    user = make_user(db)
    org = make_org(db, owner_user_id=user.clerk_id)
    client = make_client(db, user, org=org)
    strategy = _seed_strategy_and_templates(db)
    _make_css(db, client.id, strategy.id, 2024, "not_reviewed")
    db.commit()

    # recommended
    update_strategy_status(
        db, client.id, strategy.id, 2024,
        new_status="recommended", user_id=user.clerk_id,
    )
    assert db.query(ActionItem).filter(
        ActionItem.client_id == client.id,
        ActionItem.source == "strategy_implementation",
    ).count() == 7

    # demote to not_reviewed
    update_strategy_status(
        db, client.id, strategy.id, 2024,
        new_status="not_reviewed", user_id=user.clerk_id,
    )

    # re-recommend — tasks still exist (not archived), so idempotency holds
    update_strategy_status(
        db, client.id, strategy.id, 2024,
        new_status="recommended", user_id=user.clerk_id,
    )
    assert db.query(ActionItem).filter(
        ActionItem.client_id == client.id,
        ActionItem.source == "strategy_implementation",
    ).count() == 7  # Same 7, no new ones


# ---------------------------------------------------------------------------
# Test 4: Re-recommendation after archive — 7 NEW tasks
# ---------------------------------------------------------------------------


def test_re_recommendation_after_archive_creates_new_tasks(db: Session):
    user = make_user(db)
    org = make_org(db, owner_user_id=user.clerk_id)
    client = make_client(db, user, org=org)
    strategy = _seed_strategy_and_templates(db)
    _make_css(db, client.id, strategy.id, 2024, "not_reviewed")
    db.commit()

    # recommended → materialize
    update_strategy_status(
        db, client.id, strategy.id, 2024,
        new_status="recommended", user_id=user.clerk_id,
    )
    assert db.query(ActionItem).filter(
        ActionItem.client_id == client.id,
        ActionItem.source == "strategy_implementation",
    ).count() == 7

    # archive
    archived_count = archive_implementation_tasks(
        db, client_id=client.id, strategy_id=strategy.id,
        tax_year=2024, user_id=user.clerk_id,
    )
    assert archived_count == 7

    # Verify old tasks are cancelled
    cancelled = db.query(ActionItem).filter(
        ActionItem.client_id == client.id,
        ActionItem.status == "cancelled",
    ).count()
    assert cancelled == 7

    # demote then re-recommend
    update_strategy_status(
        db, client.id, strategy.id, 2024,
        new_status="not_reviewed", user_id=user.clerk_id,
    )
    update_strategy_status(
        db, client.id, strategy.id, 2024,
        new_status="recommended", user_id=user.clerk_id,
    )

    # 7 cancelled + 7 new pending = 14 total
    total = db.query(ActionItem).filter(
        ActionItem.client_id == client.id,
        ActionItem.source == "strategy_implementation",
    ).count()
    assert total == 14

    pending = db.query(ActionItem).filter(
        ActionItem.client_id == client.id,
        ActionItem.source == "strategy_implementation",
        ActionItem.status == "pending",
    ).count()
    assert pending == 7


# ---------------------------------------------------------------------------
# Test 5: Progress meter
# ---------------------------------------------------------------------------


def test_progress_meter(db: Session):
    user = make_user(db)
    org = make_org(db, owner_user_id=user.clerk_id)
    client = make_client(db, user, org=org)
    strategy = _seed_strategy_and_templates(db)
    _make_css(db, client.id, strategy.id, 2024, "not_reviewed")
    db.commit()

    # Empty case (before materialization)
    progress = get_implementation_progress(
        db, client_id=client.id, strategy_id=strategy.id, tax_year=2024,
    )
    assert progress["total"] == 0
    assert progress["completed"] == 0

    # Materialize
    update_strategy_status(
        db, client.id, strategy.id, 2024,
        new_status="recommended", user_id=user.clerk_id,
    )

    progress = get_implementation_progress(
        db, client_id=client.id, strategy_id=strategy.id, tax_year=2024,
    )
    assert progress["total"] == 7
    assert progress["completed"] == 0
    assert progress["by_owner_role"]["cpa"]["total"] == 6
    assert progress["by_owner_role"]["client"]["total"] == 1
    assert progress["by_owner_role"]["third_party"]["total"] == 0

    # Complete 3 CPA tasks
    cpa_items = db.query(ActionItem).filter(
        ActionItem.client_id == client.id,
        ActionItem.source == "strategy_implementation",
        ActionItem.owner_role == "cpa",
    ).limit(3).all()
    for item in cpa_items:
        item.status = "completed"
    db.commit()

    progress = get_implementation_progress(
        db, client_id=client.id, strategy_id=strategy.id, tax_year=2024,
    )
    assert progress["total"] == 7
    assert progress["completed"] == 3
    assert progress["by_owner_role"]["cpa"]["completed"] == 3
    assert progress["by_owner_role"]["client"]["completed"] == 0

    # Verify tasks are ordered by display_order
    orders = [t["display_order"] for t in progress["tasks"]]
    assert orders == sorted(orders)


# ---------------------------------------------------------------------------
# Test 6: Notification filter — only cpa owner_role returned
# ---------------------------------------------------------------------------


def test_notification_filter_cpa_only(db: Session):
    """Verify alerts service query pattern filters on owner_role='cpa'."""
    user = make_user(db)
    org = make_org(db, owner_user_id=user.clerk_id)
    client = make_client(db, user, org=org)
    db.commit()

    today = date.today()
    yesterday = today - timedelta(days=1)

    # Create a CPA-owned overdue action item
    cpa_item = ActionItem(
        id=uuid.uuid4(),
        client_id=client.id,
        text="CPA task overdue",
        status="pending",
        owner_role="cpa",
        due_date=yesterday,
        source="strategy_implementation",
    )
    # Create a client-owned overdue action item
    client_item = ActionItem(
        id=uuid.uuid4(),
        client_id=client.id,
        text="Client task overdue",
        status="pending",
        owner_role="client",
        due_date=yesterday,
        source="strategy_implementation",
    )
    db.add_all([cpa_item, client_item])
    db.commit()

    # Simulate the alerts query pattern (mirrors Q3 in alerts_service.py)
    seven_days = today + timedelta(days=7)
    results = (
        db.query(ActionItem)
        .filter(
            ActionItem.client_id == client.id,
            ActionItem.status == "pending",
            ActionItem.owner_role == "cpa",
            ActionItem.due_date.isnot(None),
            ActionItem.due_date <= seven_days,
        )
        .all()
    )

    assert len(results) == 1
    assert results[0].id == cpa_item.id

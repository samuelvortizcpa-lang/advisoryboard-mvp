"""
Tests for engagement_deliverable_service shell + kickoff_memo handler (G5-P3).

12 tests total:
- 7 shell tests (TestEngagementDeliverableServiceShell)
- 5 handler tests (TestKickoffMemoHandler)
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.models import *  # noqa: F401, F403
from app.models.action_item import ActionItem
from app.models.cadence_template import CadenceTemplate
from app.models.cadence_template_deliverable import (
    DELIVERABLE_KEY_VALUES,
    CadenceTemplateDeliverable,
)
from app.models.client_cadence import ClientCadence
from app.models.client_communication import ClientCommunication
from app.models.client_strategy_status import ClientStrategyStatus
from app.models.journal_entry import JournalEntry
from app.models.tax_strategy import TaxStrategy
from app.services import engagement_deliverable_service as eds
from app.services.deliverables._base import ClientFacts, ContextBundle
from app.services.deliverables.kickoff_memo import (
    _build_kickoff_prompt,
    _extract_strategies_and_tasks,
)
from tests.conftest import make_client, make_org, make_user


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Shell tests
# ---------------------------------------------------------------------------


class TestEngagementDeliverableServiceShell:

    @pytest.mark.asyncio
    async def test_draft_refuses_when_cadence_disabled(self, db: Session):
        """PermissionError raised when kickoff_memo is cadence-disabled."""
        user = make_user(db)
        org = make_org(db, owner_user_id=user.clerk_id)
        client = make_client(db, user, org=org)
        _disable_kickoff_memo(db, client.id)

        with pytest.raises(PermissionError, match="kickoff_memo"):
            await eds.draft_deliverable(
                db,
                client_id=client.id,
                deliverable_key="kickoff_memo",
                tax_year=2026,
                requested_by=user.clerk_id,
            )

    @pytest.mark.asyncio
    async def test_draft_refuses_unknown_deliverable_key(self, db: Session):
        """ValueError raised for unregistered deliverable_key."""
        user = make_user(db)
        org = make_org(db, owner_user_id=user.clerk_id)
        client = make_client(db, user, org=org)

        with pytest.raises(ValueError, match="No handler registered"):
            await eds.draft_deliverable(
                db,
                client_id=client.id,
                deliverable_key="bogus_unknown",
                tax_year=2026,
                requested_by=user.clerk_id,
            )

    @patch("app.services.engagement_deliverable_service.AsyncOpenAI")
    @pytest.mark.asyncio
    async def test_draft_writes_journal_entry(self, mock_openai_cls, db: Session):
        """Successful draft writes a journal entry with category=deliverable."""
        # Configure mock
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=MagicMock(
                choices=[MagicMock(message=MagicMock(content="Draft body text"))]
            )
        )
        mock_openai_cls.return_value = mock_client

        user = make_user(db)
        org = make_org(db, owner_user_id=user.clerk_id)
        client = make_client(db, user, org=org)
        _enable_kickoff_memo(db, client.id)
        _seed_recommended_strategy(db, client.id)

        result = await eds.draft_deliverable(
            db,
            client_id=client.id,
            deliverable_key="kickoff_memo",
            tax_year=2026,
            requested_by=user.clerk_id,
        )

        assert result.subject
        assert result.body == "Draft body text"

        entries = (
            db.query(JournalEntry)
            .filter(
                JournalEntry.client_id == client.id,
                JournalEntry.category == "deliverable",
            )
            .all()
        )
        assert len(entries) == 1
        assert "Drafted" in entries[0].title

    @patch("app.services.deliverables.kickoff_memo.extract_open_items_from_email")
    def test_send_creates_client_communications_row_with_correct_thread_params(
        self, mock_extract, db: Session
    ):
        """record_deliverable_sent creates a row with correct threading."""
        mock_extract.return_value = []

        user = make_user(db)
        org = make_org(db, owner_user_id=user.clerk_id)
        client = make_client(db, user, org=org)
        _enable_kickoff_memo(db, client.id)

        comm = eds.record_deliverable_sent(
            db,
            client_id=client.id,
            deliverable_key="kickoff_memo",
            tax_year=2026,
            subject="Test subject",
            body="Test body",
            sent_by=user.clerk_id,
            recipient_email="client@example.com",
        )

        assert comm.thread_type == "engagement_year"
        assert comm.thread_year == 2026
        assert comm.thread_quarter is None
        assert comm.thread_id is not None

    @patch("app.services.deliverables.kickoff_memo.extract_open_items_from_email")
    def test_send_creates_thread_via_get_or_create_thread(
        self, mock_extract, db: Session
    ):
        """Second send for same client+year reuses the first thread_id."""
        mock_extract.return_value = []

        user = make_user(db)
        org = make_org(db, owner_user_id=user.clerk_id)
        client = make_client(db, user, org=org)
        _enable_kickoff_memo(db, client.id)

        comm1 = eds.record_deliverable_sent(
            db,
            client_id=client.id,
            deliverable_key="kickoff_memo",
            tax_year=2026,
            subject="First",
            body="Body 1",
            sent_by=user.clerk_id,
            recipient_email="client@example.com",
        )
        comm2 = eds.record_deliverable_sent(
            db,
            client_id=client.id,
            deliverable_key="kickoff_memo",
            tax_year=2026,
            subject="Second",
            body="Body 2",
            sent_by=user.clerk_id,
            recipient_email="client@example.com",
        )

        assert comm1.thread_id == comm2.thread_id

    @patch("app.services.deliverables.kickoff_memo.extract_open_items_from_email")
    def test_send_writes_journal_entry(self, mock_extract, db: Session):
        """record_deliverable_sent writes a journal entry."""
        mock_extract.return_value = []

        user = make_user(db)
        org = make_org(db, owner_user_id=user.clerk_id)
        client = make_client(db, user, org=org)
        _enable_kickoff_memo(db, client.id)

        eds.record_deliverable_sent(
            db,
            client_id=client.id,
            deliverable_key="kickoff_memo",
            tax_year=2026,
            subject="Sent",
            body="Body",
            sent_by=user.clerk_id,
            recipient_email="client@example.com",
        )

        entries = (
            db.query(JournalEntry)
            .filter(
                JournalEntry.client_id == client.id,
                JournalEntry.category == "deliverable",
            )
            .all()
        )
        assert len(entries) == 1
        assert "Sent" in entries[0].title

    @patch("app.services.deliverables.kickoff_memo.extract_open_items_from_email")
    def test_send_idempotent_under_retry(self, mock_extract, db: Session):
        """Duplicate gmail_message_id returns existing row, no new side effects."""
        mock_extract.return_value = [
            {"question": "Confirm records?", "category": "awaiting_response"}
        ]

        user = make_user(db)
        org = make_org(db, owner_user_id=user.clerk_id)
        client = make_client(db, user, org=org)
        _enable_kickoff_memo(db, client.id)

        gmail_id = "msg_abc123"
        comm1 = eds.record_deliverable_sent(
            db,
            client_id=client.id,
            deliverable_key="kickoff_memo",
            tax_year=2026,
            subject="Kickoff",
            body="Body with questions",
            sent_by=user.clerk_id,
            recipient_email="client@example.com",
            gmail_message_id=gmail_id,
        )
        comm2 = eds.record_deliverable_sent(
            db,
            client_id=client.id,
            deliverable_key="kickoff_memo",
            tax_year=2026,
            subject="Kickoff",
            body="Body with questions",
            sent_by=user.clerk_id,
            recipient_email="client@example.com",
            gmail_message_id=gmail_id,
        )

        assert comm1.id == comm2.id

        # Only one communication row
        comms = (
            db.query(ClientCommunication)
            .filter(ClientCommunication.client_id == client.id)
            .all()
        )
        assert len(comms) == 1

        # Only one journal entry
        entries = (
            db.query(JournalEntry)
            .filter(
                JournalEntry.client_id == client.id,
                JournalEntry.category == "deliverable",
            )
            .all()
        )
        assert len(entries) == 1

        # Extractor called only once
        assert mock_extract.call_count == 1


# ---------------------------------------------------------------------------
# Handler tests (pure prompt builders, no mocks needed)
# ---------------------------------------------------------------------------


class TestKickoffMemoHandler:

    def test_handler_prompt_includes_recommended_strategies(self):
        """Recommended strategy name appears in the prompt."""
        bundle = ContextBundle(
            strategies=[
                {
                    "id": str(uuid.uuid4()),
                    "name": "Augusta Rule",
                    "status": "recommended",
                    "category": "income",
                    "estimated_impact": 15000,
                    "notes": None,
                }
            ],
            action_items=[],
            journal=[],
            financials={},
            comms=[],
        )
        facts = ClientFacts(name="Tracy Chen DO, Inc", entity_type="C-Corp", tax_year=2026)

        prompt = _build_kickoff_prompt(bundle, facts)

        assert "Augusta Rule" in prompt
        assert "Tracy Chen DO, Inc" in prompt
        assert "2026" in prompt

    def test_handler_prompt_excludes_non_recommended_strategies(self):
        """Only recommended strategies appear; not_recommended are excluded."""
        bundle = ContextBundle(
            strategies=[
                {"id": str(uuid.uuid4()), "name": "Keep This", "status": "recommended",
                 "category": "income", "estimated_impact": None, "notes": None},
                {"id": str(uuid.uuid4()), "name": "Drop This", "status": "not_recommended",
                 "category": "income", "estimated_impact": None, "notes": None},
            ],
            action_items=[],
            journal=[],
            financials={},
            comms=[],
        )
        facts = ClientFacts(name="Client", entity_type="LLC", tax_year=2026)

        prompt = _build_kickoff_prompt(bundle, facts)

        assert "Keep This" in prompt
        assert "Drop This" not in prompt

    def test_handler_prompt_excludes_cpa_owned_tasks(self):
        """CPA-owned tasks do not appear; client and third_party tasks do."""
        bundle = ContextBundle(
            strategies=[],
            action_items=[
                {"id": str(uuid.uuid4()), "text": "Client task", "owner_role": "client",
                 "due_date": None},
                {"id": str(uuid.uuid4()), "text": "Third party task", "owner_role": "third_party",
                 "due_date": None},
                {"id": str(uuid.uuid4()), "text": "CPA task", "owner_role": "cpa",
                 "due_date": None},
            ],
            journal=[],
            financials={},
            comms=[],
        )
        facts = ClientFacts(name="Client", entity_type=None, tax_year=2026)

        prompt = _build_kickoff_prompt(bundle, facts)

        assert "Client task" in prompt
        assert "Third party task" in prompt
        assert "CPA task" not in prompt

    def test_handler_references_payload_shape(self):
        """_extract_strategies_and_tasks returns correct dict shape."""
        sid = str(uuid.uuid4())
        tid = str(uuid.uuid4())
        bundle = ContextBundle(
            strategies=[
                {"id": sid, "name": "Cost Seg", "status": "recommended",
                 "category": "deductions", "estimated_impact": None, "notes": None},
                {"id": str(uuid.uuid4()), "name": "Excluded", "status": "implemented",
                 "category": "income", "estimated_impact": None, "notes": None},
            ],
            action_items=[
                {"id": tid, "text": "Get appraisal", "owner_role": "client",
                 "due_date": "2026-03-15", "strategy_name": "Cost Seg"},
                {"id": str(uuid.uuid4()), "text": "File extension", "owner_role": "cpa",
                 "due_date": None, "strategy_name": ""},
            ],
            journal=[],
            financials={},
            comms=[],
        )
        facts = ClientFacts(name="Client", entity_type="S-Corp", tax_year=2026)

        result = _extract_strategies_and_tasks(bundle, facts)

        assert "strategies" in result
        assert "tasks" in result
        assert len(result["strategies"]) == 1
        assert result["strategies"][0]["id"] == sid
        assert result["strategies"][0]["name"] == "Cost Seg"
        assert len(result["tasks"]) == 1
        assert result["tasks"][0]["id"] == tid
        assert result["tasks"][0]["owner_role"] == "client"
        assert result["tasks"][0]["due_date"] == "2026-03-15"

    def test_handler_no_recommended_strategies_returns_warning(self):
        """When no strategies are recommended, prompt includes warning copy."""
        bundle = ContextBundle(
            strategies=[
                {"id": str(uuid.uuid4()), "name": "Not Rec", "status": "not_recommended",
                 "category": "income", "estimated_impact": None, "notes": None},
            ],
            action_items=[],
            journal=[],
            financials={},
            comms=[],
        )
        facts = ClientFacts(name="Client", entity_type=None, tax_year=2026)

        prompt = _build_kickoff_prompt(bundle, facts)

        assert "still finalizing" in prompt

    def test_handler_dedup_tasks_by_text(self):
        """Duplicate action items with same text are deduplicated."""
        tid1 = str(uuid.uuid4())
        tid2 = str(uuid.uuid4())
        bundle = ContextBundle(
            strategies=[],
            action_items=[
                {"id": tid1, "text": "Get appraisal", "owner_role": "client",
                 "due_date": "2026-06-15", "strategy_name": "Cost Seg"},
                {"id": tid2, "text": "Get appraisal", "owner_role": "client",
                 "due_date": "2026-06-15", "strategy_name": "Cost Seg"},
            ],
            journal=[],
            financials={},
            comms=[],
        )
        facts = ClientFacts(name="Client", entity_type="S-Corp", tax_year=2026)

        result = _extract_strategies_and_tasks(bundle, facts)

        assert len(result["tasks"]) == 1
        assert result["tasks"][0]["name"] == "Get appraisal"


# ---------------------------------------------------------------------------
# Regression tests (FT-2, FT-3 from May 9 v1 smoke)
# ---------------------------------------------------------------------------


class TestKickoffMemoRegressions:

    @patch("app.services.engagement_deliverable_service.AsyncOpenAI")
    @pytest.mark.asyncio
    async def test_draft_kickoff_memo_strategy_references_populated(
        self, mock_openai_cls, db: Session
    ):
        """FT-2 regression: recommended strategies produce non-empty references."""
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=MagicMock(
                choices=[MagicMock(message=MagicMock(content="Draft body"))]
            )
        )
        mock_openai_cls.return_value = mock_client

        user = make_user(db)
        org = make_org(db, owner_user_id=user.clerk_id)
        client = make_client(db, user, org=org)
        _enable_kickoff_memo(db, client.id)
        _seed_recommended_strategy(db, client.id)

        result = await eds.draft_deliverable(
            db,
            client_id=client.id,
            deliverable_key="kickoff_memo",
            tax_year=2026,
            requested_by=user.clerk_id,
        )

        assert len(result.references.strategies) >= 1
        assert result.references.strategies[0].id != ""
        assert result.references.strategies[0].name == "Augusta Rule"
        assert result.warnings == []

    @patch("app.services.engagement_deliverable_service.AsyncOpenAI")
    @pytest.mark.asyncio
    async def test_draft_kickoff_memo_warnings_fire_when_no_strategies_post_filter(
        self, mock_openai_cls, db: Session
    ):
        """FT-2 defense-in-depth: warnings fire when post-filter strategies is empty."""
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=MagicMock(
                choices=[MagicMock(message=MagicMock(content="Draft body"))]
            )
        )
        mock_openai_cls.return_value = mock_client

        user = make_user(db)
        org = make_org(db, owner_user_id=user.clerk_id)
        client = make_client(db, user, org=org)
        _enable_kickoff_memo(db, client.id)
        # No strategies seeded — references_dict will have empty strategies list

        result = await eds.draft_deliverable(
            db,
            client_id=client.id,
            deliverable_key="kickoff_memo",
            tax_year=2026,
            requested_by=user.clerk_id,
        )

        assert result.references.strategies == []
        assert "No recommended strategies found" in result.warnings

    @patch("app.services.engagement_deliverable_service.AsyncOpenAI")
    @pytest.mark.asyncio
    async def test_draft_kickoff_memo_no_duplicate_tasks(
        self, mock_openai_cls, db: Session
    ):
        """FT-3 regression: duplicate ActionItems with same text appear once."""
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=MagicMock(
                choices=[MagicMock(message=MagicMock(content="Draft body"))]
            )
        )
        mock_openai_cls.return_value = mock_client

        user = make_user(db)
        org = make_org(db, owner_user_id=user.clerk_id)
        client = make_client(db, user, org=org)
        _enable_kickoff_memo(db, client.id)

        # Seed two ActionItems with identical text
        from app.models.action_item import ActionItem
        for _ in range(2):
            db.add(ActionItem(
                id=uuid.uuid4(),
                client_id=client.id,
                created_by=user.clerk_id,
                text="Get appraisal",
                priority="medium",
                status="pending",
                owner_role="client",
                source="manual",
            ))
        db.flush()

        result = await eds.draft_deliverable(
            db,
            client_id=client.id,
            deliverable_key="kickoff_memo",
            tax_year=2026,
            requested_by=user.clerk_id,
        )

        task_names = [t.name for t in result.references.tasks]
        assert task_names.count("Get appraisal") == 1

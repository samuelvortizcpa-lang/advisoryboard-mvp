"""
Tests for cadence_service (Layer 2 Gap 4 — G4-P2).
"""
import uuid

import pytest
from sqlalchemy.orm import Session

from app.models import *  # noqa: F401, F403
from app.models.cadence_template import CadenceTemplate
from app.models.cadence_template_deliverable import (
    CadenceTemplateDeliverable,
    DELIVERABLE_KEY_VALUES,
)
from app.models.client_cadence import ClientCadence
from app.models.journal_entry import JournalEntry
from app.services import cadence_service
from tests.conftest import make_client, make_org, make_user


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_system_templates(db: Session):
    """Seed Full Cadence and Empty system templates with all 7 deliverable rows each."""
    full = CadenceTemplate(
        id=uuid.uuid4(),
        name="Full Cadence",
        is_system=True,
        is_active=True,
        org_id=None,
    )
    empty = CadenceTemplate(
        id=uuid.uuid4(),
        name="Empty",
        is_system=True,
        is_active=True,
        org_id=None,
    )
    quarterly = CadenceTemplate(
        id=uuid.uuid4(),
        name="Quarterly Only",
        is_system=True,
        is_active=True,
        org_id=None,
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
        # Quarterly: only quarterly_memo and year_end_recap enabled
        db.add(CadenceTemplateDeliverable(
            template_id=quarterly.id,
            deliverable_key=key,
            is_enabled=(key in ("quarterly_memo", "year_end_recap")),
        ))
    db.flush()
    return full, empty, quarterly


def _setup(db: Session):
    """Create user, org, client, and seed system templates."""
    user = make_user(db)
    org = make_org(db, owner_user_id=user.clerk_id)
    client = make_client(db, user, org=org)
    full, empty, quarterly = _seed_system_templates(db)
    db.commit()
    return user, org, client, full, empty, quarterly


# ---------------------------------------------------------------------------
# is_deliverable_enabled
# ---------------------------------------------------------------------------


class TestIsDeliverableEnabled:
    def test_template_default_returned(self, db):
        user, org, client, full, empty, quarterly = _setup(db)
        # Assign Full Cadence
        cadence_service.assign_cadence(db, client.id, full.id, user.clerk_id)
        assert cadence_service.is_deliverable_enabled(db, client.id, "kickoff_memo") is True

    def test_override_true_wins_over_template_false(self, db):
        user, org, client, full, empty, quarterly = _setup(db)
        cadence_service.assign_cadence(db, client.id, empty.id, user.clerk_id)
        # Empty has all disabled; override one to True
        cadence_service.update_overrides(db, client.id, {"kickoff_memo": True}, user.clerk_id)
        assert cadence_service.is_deliverable_enabled(db, client.id, "kickoff_memo") is True

    def test_override_false_wins_over_template_true(self, db):
        user, org, client, full, empty, quarterly = _setup(db)
        cadence_service.assign_cadence(db, client.id, full.id, user.clerk_id)
        cadence_service.update_overrides(db, client.id, {"kickoff_memo": False}, user.clerk_id)
        assert cadence_service.is_deliverable_enabled(db, client.id, "kickoff_memo") is False

    def test_returns_false_when_no_cadence(self, db):
        user, org, client, full, empty, quarterly = _setup(db)
        assert cadence_service.is_deliverable_enabled(db, client.id, "kickoff_memo") is False

    def test_raises_on_invalid_key(self, db):
        user, org, client, full, empty, quarterly = _setup(db)
        with pytest.raises(ValueError, match="Invalid deliverable_key"):
            cadence_service.is_deliverable_enabled(db, client.id, "bogus_key")


# ---------------------------------------------------------------------------
# list_enabled_deliverables
# ---------------------------------------------------------------------------


class TestListEnabledDeliverables:
    def test_full_cadence_returns_all_7(self, db):
        user, org, client, full, empty, quarterly = _setup(db)
        cadence_service.assign_cadence(db, client.id, full.id, user.clerk_id)
        result = cadence_service.list_enabled_deliverables(db, client.id)
        assert set(result) == set(DELIVERABLE_KEY_VALUES)

    def test_quarterly_only_returns_2(self, db):
        user, org, client, full, empty, quarterly = _setup(db)
        cadence_service.assign_cadence(db, client.id, quarterly.id, user.clerk_id)
        result = cadence_service.list_enabled_deliverables(db, client.id)
        assert set(result) == {"quarterly_memo", "year_end_recap"}

    def test_empty_list_when_no_cadence(self, db):
        user, org, client, full, empty, quarterly = _setup(db)
        assert cadence_service.list_enabled_deliverables(db, client.id) == []

    def test_reflects_override(self, db):
        user, org, client, full, empty, quarterly = _setup(db)
        cadence_service.assign_cadence(db, client.id, quarterly.id, user.clerk_id)
        cadence_service.update_overrides(db, client.id, {"kickoff_memo": True}, user.clerk_id)
        result = cadence_service.list_enabled_deliverables(db, client.id)
        assert "kickoff_memo" in result
        assert "quarterly_memo" in result


# ---------------------------------------------------------------------------
# assign_cadence
# ---------------------------------------------------------------------------


class TestAssignCadence:
    def test_first_call_inserts(self, db):
        user, org, client, full, empty, quarterly = _setup(db)
        cc = cadence_service.assign_cadence(db, client.id, full.id, user.clerk_id)
        assert cc.client_id == client.id
        assert cc.template_id == full.id
        assert cc.overrides == {}

    def test_second_call_upserts_and_resets_overrides(self, db):
        user, org, client, full, empty, quarterly = _setup(db)
        cadence_service.assign_cadence(db, client.id, full.id, user.clerk_id)
        cadence_service.update_overrides(db, client.id, {"kickoff_memo": False}, user.clerk_id)
        # Reassign to different template
        cc = cadence_service.assign_cadence(db, client.id, quarterly.id, user.clerk_id)
        assert cc.template_id == quarterly.id
        assert cc.overrides == {}  # reset

    def test_journal_entry_written(self, db):
        user, org, client, full, empty, quarterly = _setup(db)
        cadence_service.assign_cadence(db, client.id, full.id, user.clerk_id)
        entries = (
            db.query(JournalEntry)
            .filter(
                JournalEntry.client_id == client.id,
                JournalEntry.category == "cadence",
            )
            .all()
        )
        assert len(entries) == 1
        assert "Full Cadence" in entries[0].title

    def test_same_template_reassign_writes_no_journal(self, db):
        user, org, client, full, empty, quarterly = _setup(db)
        cadence_service.assign_cadence(db, client.id, full.id, user.clerk_id)
        count_before = (
            db.query(JournalEntry)
            .filter(JournalEntry.client_id == client.id, JournalEntry.category == "cadence")
            .count()
        )
        # Re-assign same template
        cadence_service.assign_cadence(db, client.id, full.id, user.clerk_id)
        count_after = (
            db.query(JournalEntry)
            .filter(JournalEntry.client_id == client.id, JournalEntry.category == "cadence")
            .count()
        )
        assert count_after == count_before

    def test_different_template_reassign_writes_journal(self, db):
        user, org, client, full, empty, quarterly = _setup(db)
        cadence_service.assign_cadence(db, client.id, full.id, user.clerk_id)
        count_before = (
            db.query(JournalEntry)
            .filter(JournalEntry.client_id == client.id, JournalEntry.category == "cadence")
            .count()
        )
        cadence_service.assign_cadence(db, client.id, quarterly.id, user.clerk_id)
        count_after = (
            db.query(JournalEntry)
            .filter(JournalEntry.client_id == client.id, JournalEntry.category == "cadence")
            .count()
        )
        assert count_after == count_before + 1

    def test_refuses_nonexistent_template(self, db):
        user, org, client, full, empty, quarterly = _setup(db)
        with pytest.raises(ValueError, match="does not exist"):
            cadence_service.assign_cadence(db, client.id, uuid.uuid4(), user.clerk_id)

    def test_refuses_inactive_template(self, db):
        user, org, client, full, empty, quarterly = _setup(db)
        # Create an inactive template
        inactive = CadenceTemplate(
            id=uuid.uuid4(), org_id=org.id, name="Inactive",
            is_system=False, is_active=False,
        )
        db.add(inactive)
        db.flush()
        with pytest.raises(ValueError, match="not active"):
            cadence_service.assign_cadence(db, client.id, inactive.id, user.clerk_id)


# ---------------------------------------------------------------------------
# update_overrides
# ---------------------------------------------------------------------------


class TestUpdateOverrides:
    def test_single_key_set_and_read(self, db):
        user, org, client, full, empty, quarterly = _setup(db)
        cadence_service.assign_cadence(db, client.id, full.id, user.clerk_id)
        cc = cadence_service.update_overrides(db, client.id, {"kickoff_memo": False}, user.clerk_id)
        assert cc.overrides["kickoff_memo"] is False
        assert cadence_service.is_deliverable_enabled(db, client.id, "kickoff_memo") is False

    def test_multi_key_writes_one_journal_per_changed_key(self, db):
        user, org, client, full, empty, quarterly = _setup(db)
        cadence_service.assign_cadence(db, client.id, full.id, user.clerk_id)
        # Clear assignment journal entries count
        initial_count = (
            db.query(JournalEntry)
            .filter(JournalEntry.client_id == client.id, JournalEntry.category == "cadence")
            .count()
        )
        cadence_service.update_overrides(
            db, client.id,
            {"kickoff_memo": False, "progress_note": False},
            user.clerk_id,
        )
        new_count = (
            db.query(JournalEntry)
            .filter(JournalEntry.client_id == client.id, JournalEntry.category == "cadence")
            .count()
        )
        assert new_count - initial_count == 2  # one per changed key

    def test_noop_key_writes_no_journal(self, db):
        user, org, client, full, empty, quarterly = _setup(db)
        cadence_service.assign_cadence(db, client.id, full.id, user.clerk_id)
        cadence_service.update_overrides(db, client.id, {"kickoff_memo": False}, user.clerk_id)
        count_before = (
            db.query(JournalEntry)
            .filter(JournalEntry.client_id == client.id, JournalEntry.category == "cadence")
            .count()
        )
        # Same value again — no-op
        cadence_service.update_overrides(db, client.id, {"kickoff_memo": False}, user.clerk_id)
        count_after = (
            db.query(JournalEntry)
            .filter(JournalEntry.client_id == client.id, JournalEntry.category == "cadence")
            .count()
        )
        assert count_after == count_before

    def test_raises_on_invalid_key(self, db):
        user, org, client, full, empty, quarterly = _setup(db)
        cadence_service.assign_cadence(db, client.id, full.id, user.clerk_id)
        with pytest.raises(ValueError, match="Invalid deliverable_key"):
            cadence_service.update_overrides(db, client.id, {"bogus": True}, user.clerk_id)

    def test_raises_on_non_bool_value_none(self, db):
        user, org, client, full, empty, quarterly = _setup(db)
        cadence_service.assign_cadence(db, client.id, full.id, user.clerk_id)
        with pytest.raises(ValueError, match="must be bool"):
            cadence_service.update_overrides(db, client.id, {"kickoff_memo": None}, user.clerk_id)

    def test_raises_on_non_bool_value_int(self, db):
        user, org, client, full, empty, quarterly = _setup(db)
        cadence_service.assign_cadence(db, client.id, full.id, user.clerk_id)
        with pytest.raises(ValueError, match="must be bool"):
            cadence_service.update_overrides(db, client.id, {"kickoff_memo": 1}, user.clerk_id)

    def test_raises_on_non_bool_value_string(self, db):
        user, org, client, full, empty, quarterly = _setup(db)
        cadence_service.assign_cadence(db, client.id, full.id, user.clerk_id)
        with pytest.raises(ValueError, match="must be bool"):
            cadence_service.update_overrides(db, client.id, {"kickoff_memo": ""}, user.clerk_id)

    def test_raises_if_no_cadence_row(self, db):
        user, org, client, full, empty, quarterly = _setup(db)
        with pytest.raises(ValueError, match="No cadence assignment"):
            cadence_service.update_overrides(db, client.id, {"kickoff_memo": True}, user.clerk_id)

    def test_existing_keys_preserved(self, db):
        user, org, client, full, empty, quarterly = _setup(db)
        cadence_service.assign_cadence(db, client.id, full.id, user.clerk_id)
        cadence_service.update_overrides(db, client.id, {"kickoff_memo": False}, user.clerk_id)
        cadence_service.update_overrides(db, client.id, {"progress_note": False}, user.clerk_id)
        cc = db.query(ClientCadence).filter(ClientCadence.client_id == client.id).first()
        assert cc.overrides["kickoff_memo"] is False  # preserved
        assert cc.overrides["progress_note"] is False  # newly set


# ---------------------------------------------------------------------------
# create_custom_template
# ---------------------------------------------------------------------------


class TestCreateCustomTemplate:
    def test_happy_path(self, db):
        user, org, client, full, empty, quarterly = _setup(db)
        flags = {k: (k == "year_end_recap") for k in DELIVERABLE_KEY_VALUES}
        template = cadence_service.create_custom_template(
            db, org.id, "My Custom", "desc", flags, user.clerk_id,
        )
        assert template.is_system is False
        assert template.org_id == org.id
        deliverables = (
            db.query(CadenceTemplateDeliverable)
            .filter(CadenceTemplateDeliverable.template_id == template.id)
            .all()
        )
        assert len(deliverables) == 7
        enabled = [d for d in deliverables if d.is_enabled]
        assert len(enabled) == 1

    def test_refuses_org_id_none(self, db):
        _setup(db)
        flags = {k: True for k in DELIVERABLE_KEY_VALUES}
        with pytest.raises(ValueError, match="org_id is required"):
            cadence_service.create_custom_template(db, None, "Bad", None, flags, "user")

    def test_refuses_missing_key(self, db):
        user, org, client, full, empty, quarterly = _setup(db)
        flags = {k: True for k in list(DELIVERABLE_KEY_VALUES)[:6]}  # only 6
        with pytest.raises(ValueError, match="missing"):
            cadence_service.create_custom_template(
                db, org.id, "Bad", None, flags, user.clerk_id,
            )

    def test_refuses_extra_key(self, db):
        user, org, client, full, empty, quarterly = _setup(db)
        flags = {k: True for k in DELIVERABLE_KEY_VALUES}
        flags["bogus"] = True
        with pytest.raises(ValueError, match="extra"):
            cadence_service.create_custom_template(
                db, org.id, "Bad", None, flags, user.clerk_id,
            )


# ---------------------------------------------------------------------------
# update_template
# ---------------------------------------------------------------------------


class TestUpdateTemplate:
    def test_updates_name_and_description(self, db):
        user, org, client, full, empty, quarterly = _setup(db)
        flags = {k: True for k in DELIVERABLE_KEY_VALUES}
        template = cadence_service.create_custom_template(
            db, org.id, "Original", "Original desc", flags, user.clerk_id,
        )
        updated = cadence_service.update_template(
            db, template.id, "New Name", "New desc", None, user.clerk_id,
        )
        assert updated.name == "New Name"
        assert updated.description == "New desc"

    def test_partial_deliverable_flags(self, db):
        user, org, client, full, empty, quarterly = _setup(db)
        flags = {k: True for k in DELIVERABLE_KEY_VALUES}
        template = cadence_service.create_custom_template(
            db, org.id, "Test", None, flags, user.clerk_id,
        )
        cadence_service.update_template(
            db, template.id, None, None, {"kickoff_memo": False}, user.clerk_id,
        )
        row = (
            db.query(CadenceTemplateDeliverable)
            .filter(
                CadenceTemplateDeliverable.template_id == template.id,
                CadenceTemplateDeliverable.deliverable_key == "kickoff_memo",
            )
            .first()
        )
        assert row.is_enabled is False

    def test_refuses_system_template(self, db):
        user, org, client, full, empty, quarterly = _setup(db)
        with pytest.raises(ValueError, match="system"):
            cadence_service.update_template(
                db, full.id, "Hacked", None, None, user.clerk_id,
            )


# ---------------------------------------------------------------------------
# deactivate_template
# ---------------------------------------------------------------------------


class TestDeactivateTemplate:
    def test_deactivates_when_no_refs(self, db):
        user, org, client, full, empty, quarterly = _setup(db)
        flags = {k: True for k in DELIVERABLE_KEY_VALUES}
        template = cadence_service.create_custom_template(
            db, org.id, "Temp", None, flags, user.clerk_id,
        )
        cadence_service.deactivate_template(db, template.id, user.clerk_id)
        refreshed = db.query(CadenceTemplate).filter(CadenceTemplate.id == template.id).first()
        assert refreshed.is_active is False

    def test_refuses_when_client_refs_exist(self, db):
        user, org, client, full, empty, quarterly = _setup(db)
        flags = {k: True for k in DELIVERABLE_KEY_VALUES}
        template = cadence_service.create_custom_template(
            db, org.id, "InUse", None, flags, user.clerk_id,
        )
        cadence_service.assign_cadence(db, client.id, template.id, user.clerk_id)
        with pytest.raises(ValueError, match="referenced"):
            cadence_service.deactivate_template(db, template.id, user.clerk_id)

    def test_refuses_system_template(self, db):
        user, org, client, full, empty, quarterly = _setup(db)
        with pytest.raises(ValueError, match="system"):
            cadence_service.deactivate_template(db, full.id, user.clerk_id)


# ---------------------------------------------------------------------------
# set_firm_default
# ---------------------------------------------------------------------------


class TestSetFirmDefault:
    def test_sets_system_template(self, db):
        user, org, client, full, empty, quarterly = _setup(db)
        cadence_service.set_firm_default(db, org.id, full.id, user.clerk_id)
        refreshed = db.query(Organization).filter(Organization.id == org.id).first()
        assert refreshed.default_cadence_template_id == full.id

    def test_sets_org_owned_template(self, db):
        user, org, client, full, empty, quarterly = _setup(db)
        flags = {k: True for k in DELIVERABLE_KEY_VALUES}
        custom = cadence_service.create_custom_template(
            db, org.id, "Firm Custom", None, flags, user.clerk_id,
        )
        cadence_service.set_firm_default(db, org.id, custom.id, user.clerk_id)
        refreshed = db.query(Organization).filter(Organization.id == org.id).first()
        assert refreshed.default_cadence_template_id == custom.id

    def test_refuses_cross_org(self, db):
        user, org, client, full, empty, quarterly = _setup(db)
        other_org = make_org(db, owner_user_id=user.clerk_id, name="Other Org")
        db.commit()
        flags = {k: True for k in DELIVERABLE_KEY_VALUES}
        other_custom = cadence_service.create_custom_template(
            db, other_org.id, "Other Custom", None, flags, user.clerk_id,
        )
        with pytest.raises(ValueError, match="cross-org"):
            cadence_service.set_firm_default(db, org.id, other_custom.id, user.clerk_id)

    def test_none_clears_default(self, db):
        user, org, client, full, empty, quarterly = _setup(db)
        cadence_service.set_firm_default(db, org.id, full.id, user.clerk_id)
        cadence_service.set_firm_default(db, org.id, None, user.clerk_id)
        refreshed = db.query(Organization).filter(Organization.id == org.id).first()
        assert refreshed.default_cadence_template_id is None

    def test_refuses_nonexistent_template(self, db):
        user, org, client, full, empty, quarterly = _setup(db)
        with pytest.raises(ValueError, match="does not exist"):
            cadence_service.set_firm_default(db, org.id, uuid.uuid4(), user.clerk_id)

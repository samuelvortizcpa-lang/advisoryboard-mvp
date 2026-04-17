"""
Tests for client group resolution (client-linking feature).

Covers the recursive CTE that resolves a linked group from a starting
client_id.  The critical invariant: humans never traverse through a
shared entity to reach each other.

NOTE: These tests use SQLite in-memory (via conftest), so there is no
PostgreSQL trigger enforcement.  The trigger (trg_check_client_link_kinds)
is tested implicitly by the migration's own up/down cycle against real
Postgres.  Here, we set client_kind explicitly on each test client to
simulate what the trigger enforces.
"""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from tests.conftest import make_client, make_user
from app.models.client_link import ClientLink
from app.services.client_groups import resolve_client_group


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_link(
    db,
    human,
    entity,
    *,
    confirmed: bool = True,
    dismissed: bool = False,
    link_type: str = "owner_of",
    filing_responsibility: str = "firm_files",
):
    """Insert a ClientLink row with sensible defaults for testing."""
    link = ClientLink(
        id=uuid.uuid4(),
        human_client_id=human.id,
        entity_client_id=entity.id,
        link_type=link_type,
        filing_responsibility=filing_responsibility,
        confirmed_by_user=confirmed,
        detection_source="manual",
        detection_confidence=1.0,
        created_at=datetime.now(timezone.utc),
        confirmed_at=datetime.now(timezone.utc) if confirmed else None,
        dismissed_at=datetime.now(timezone.utc) if dismissed else None,
    )
    db.add(link)
    db.flush()
    return link


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestResolveClientGroup:
    """Tests for resolve_client_group()."""

    def test_solo_client_returns_self(self, db):
        """1. A client with no links returns exactly [client_id]."""
        user = make_user(db)
        client = make_client(db, user, name="Solo Michael", client_kind="individual")

        group = resolve_client_group(client.id, db)

        assert set(group) == {client.id}

    def test_human_linked_to_one_entity(self, db):
        """2. Human linked to one entity returns both IDs."""
        user = make_user(db)
        michael = make_client(db, user, name="Michael Smith", client_kind="individual")
        smith_llc = make_client(db, user, name="Smith Consulting LLC", client_kind="s_corp")

        _make_link(db, michael, smith_llc)

        group = resolve_client_group(michael.id, db)
        assert set(group) == {michael.id, smith_llc.id}

    def test_human_linked_to_three_entities(self, db):
        """3. Human linked to three entities returns all four IDs."""
        user = make_user(db)
        michael = make_client(db, user, name="Michael", client_kind="individual")

        entities = []
        for name, kind in [
            ("Smith Consulting LLC", "s_corp"),
            ("Smith Trust", "trust"),
            ("Smith Holdings LP", "partnership"),
        ]:
            e = make_client(db, user, name=name, client_kind=kind)
            entities.append(e)

        for e in entities:
            _make_link(db, michael, e)

        group = resolve_client_group(michael.id, db)
        expected = {michael.id} | {e.id for e in entities}
        assert set(group) == expected

    def test_shared_entity_privacy(self, db):
        """4. CRITICAL: Shared entity — humans do not traverse to each other.

        Michael and Bob both link to Acme (shared entity).
        Michael's group = {Michael, Acme}.
        Bob's group = {Bob, Acme}.
        Michael's group must NOT contain Bob, and vice versa.
        """
        user = make_user(db)
        michael = make_client(db, user, name="Michael", client_kind="individual")
        bob = make_client(db, user, name="Bob", client_kind="individual")
        acme = make_client(db, user, name="Acme Partners LP", client_kind="partnership")

        _make_link(db, michael, acme)
        _make_link(db, bob, acme)

        michael_group = set(resolve_client_group(michael.id, db))
        bob_group = set(resolve_client_group(bob.id, db))

        # Core privacy assertions
        assert michael_group == {michael.id, acme.id}
        assert bob_group == {bob.id, acme.id}

        # Explicit: humans do NOT see each other
        assert bob.id not in michael_group
        assert michael.id not in bob_group

    def test_unconfirmed_link_excluded(self, db):
        """5. Unconfirmed link (confirmed_by_user=FALSE) is excluded."""
        user = make_user(db)
        michael = make_client(db, user, name="Michael", client_kind="individual")
        entity = make_client(db, user, name="Pending LLC", client_kind="s_corp")

        _make_link(db, michael, entity, confirmed=False)

        group = resolve_client_group(michael.id, db)
        assert set(group) == {michael.id}

    def test_dismissed_link_excluded(self, db):
        """6. Dismissed link (dismissed_at IS NOT NULL) is excluded.

        The schema allows dismissed_at to be set while confirmed_by_user
        remains TRUE.  For Stage 1, resolve_client_group treats dismissed
        links as inactive by filtering on BOTH confirmed_by_user=TRUE AND
        dismissed_at IS NULL.  This is the safer default — a user who
        dismissed a link expects it to stop affecting retrieval immediately.
        """
        user = make_user(db)
        michael = make_client(db, user, name="Michael", client_kind="individual")
        entity = make_client(db, user, name="Dismissed LLC", client_kind="s_corp")

        # confirmed=True but also dismissed
        _make_link(db, michael, entity, confirmed=True, dismissed=True)

        group = resolve_client_group(michael.id, db)
        assert set(group) == {michael.id}

    def test_starting_from_entity_resolves_group(self, db):
        """7. Starting from an entity resolves the entity plus its linked humans."""
        user = make_user(db)
        michael = make_client(db, user, name="Michael", client_kind="individual")
        entity = make_client(db, user, name="Smith LLC", client_kind="s_corp")

        _make_link(db, michael, entity)

        group = resolve_client_group(entity.id, db)
        assert set(group) == {entity.id, michael.id}

    def test_shared_entity_from_entity_side(self, db):
        """Starting from a shared entity includes all linked humans.

        When starting from a shared entity (Acme), the group includes
        Acme plus ALL humans linked to it.  This is correct because
        the CTE traverses bidirectionally within the star.  However,
        from each human's perspective, the other human is still excluded
        (tested in test_shared_entity_privacy).
        """
        user = make_user(db)
        michael = make_client(db, user, name="Michael", client_kind="individual")
        bob = make_client(db, user, name="Bob", client_kind="individual")
        acme = make_client(db, user, name="Acme Partners LP", client_kind="partnership")

        _make_link(db, michael, acme)
        _make_link(db, bob, acme)

        acme_group = set(resolve_client_group(acme.id, db))

        # From the entity side, both humans are visible
        assert acme.id in acme_group
        assert michael.id in acme_group
        assert bob.id in acme_group

    def test_sql_output(self, db, capsys):
        """Emit the SQL for eyeballing (not a real assertion test).

        NOTE: The architecture doc specifies a recursive CTE, but the
        recursive version has a shared-entity traversal bug (Michael →
        Acme → Bob).  Since the topology is always a star (max 1 hop),
        we use a simple UNION instead.  This query is equivalent for
        the star topology and correctly enforces the privacy invariant.
        """
        user = make_user(db)
        client = make_client(db, user, name="SQL Inspection Client", client_kind="individual")

        # The actual SQL used by resolve_client_group:
        actual_sql = """
        SELECT :start_id AS client_id
        UNION
        SELECT cl.entity_client_id
        FROM client_links cl
        WHERE cl.human_client_id = :start_id
          AND cl.confirmed_by_user = TRUE
          AND cl.dismissed_at IS NULL
        UNION
        SELECT cl.human_client_id
        FROM client_links cl
        WHERE cl.entity_client_id = :start_id
          AND cl.confirmed_by_user = TRUE
          AND cl.dismissed_at IS NULL
        """
        print(f"\n--- SQL emitted by resolve_client_group ---\n{actual_sql}")
        print(f"--- Parameter: start_id = {client.id} ---\n")

        # Run it to confirm it works
        group = resolve_client_group(client.id, db)
        print(f"Result: {group}")
        assert len(group) == 1

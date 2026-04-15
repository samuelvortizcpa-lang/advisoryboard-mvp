"""
Regression test: chunk_metadata=None must persist as SQL NULL, not JSONB null.

Requires PostgreSQL — SQLite's JSON1 cannot distinguish JSONB null from SQL NULL.
The test connects to the local dev database and runs inside a transaction that
is always rolled back, so no test data leaks.

Bug: SQLAlchemy JSONB(none_as_null=False) (the default) serialises Python None
as the JSONB literal ``null`` instead of SQL NULL.  This broke every caller that
used ``WHERE chunk_metadata IS NULL``.

Fix: JSONB(none_as_null=True) on the column definition.
"""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import Base
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.user import User  # noqa: F401 — register model
from app.models.client import Client  # noqa: F401
from app.models.organization import Organization  # noqa: F401

# ---------------------------------------------------------------------------
# PostgreSQL fixtures (transaction-scoped, always rolled back)
# ---------------------------------------------------------------------------

PG_URL = "postgresql://localhost:5432/advisoryboard_dev"


@pytest.fixture
def pg_session():
    """
    Provide a PostgreSQL session inside a transaction that is rolled back
    after the test.  Uses a SAVEPOINT so the test can call session.flush()
    without committing to the real database.
    """
    engine = create_engine(PG_URL)
    conn = engine.connect()
    txn = conn.begin()
    session = Session(bind=conn)

    yield session

    session.close()
    txn.rollback()
    conn.close()
    engine.dispose()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_doc_and_client(session: Session):
    """Insert minimal parent rows so the FK constraints on DocumentChunk pass."""
    from tests.conftest import make_user, make_org, make_client

    user = make_user(session)
    org = make_org(session, owner_user_id=user.clerk_id)
    client = make_client(session, user, org=org)

    doc = Document(
        id=uuid.uuid4(),
        client_id=client.id,
        uploaded_by=user.id,
        filename="test_null_semantics.pdf",
        file_path="uploads/test_null_semantics.pdf",
        file_type="pdf",
        file_size=1024,
        processed=True,
        source="upload",
        upload_date=datetime.now(timezone.utc),
    )
    session.add(doc)
    session.flush()

    return doc, client


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestChunkMetadataNullSemantics:
    """chunk_metadata=None must be SQL NULL, not JSONB literal null."""

    def test_none_persists_as_sql_null_via_bulk_save(self, pg_session: Session):
        """
        Production path: rag_service.py uses bulk_save_objects.
        Python None must become SQL NULL so WHERE chunk_metadata IS NULL matches.
        """
        doc, client = _make_doc_and_client(pg_session)
        chunk_id = uuid.uuid4()

        chunk = DocumentChunk(
            id=chunk_id,
            document_id=doc.id,
            client_id=client.id,
            chunk_text="Test chunk for null semantics regression.",
            chunk_index=0,
            embedding=None,
            chunk_metadata=None,
        )
        pg_session.bulk_save_objects([chunk])
        pg_session.flush()

        # Raw SQL: the row should match chunk_metadata IS NULL
        row = pg_session.execute(
            text("SELECT id FROM document_chunks WHERE id = :id AND chunk_metadata IS NULL"),
            {"id": str(chunk_id)},
        ).fetchone()
        assert row is not None, (
            "chunk_metadata=None was persisted as JSONB null literal, not SQL NULL. "
            "Expected WHERE chunk_metadata IS NULL to match."
        )

        # Double-check: jsonb_typeof should return NULL (not the string 'null')
        jt_row = pg_session.execute(
            text("SELECT jsonb_typeof(chunk_metadata) AS jt FROM document_chunks WHERE id = :id"),
            {"id": str(chunk_id)},
        ).fetchone()
        assert jt_row.jt is None, (
            f"jsonb_typeof(chunk_metadata) returned {jt_row.jt!r}, expected Python None "
            "(meaning SQL NULL).  JSONB null literal would return the string 'null'."
        )

    def test_none_persists_as_sql_null_via_session_add(self, pg_session: Session):
        """
        Alternative path: session.add (used in admin.py continuation flagger).
        Same assertion — Python None → SQL NULL.
        """
        doc, client = _make_doc_and_client(pg_session)
        chunk_id = uuid.uuid4()

        chunk = DocumentChunk(
            id=chunk_id,
            document_id=doc.id,
            client_id=client.id,
            chunk_text="Test chunk for null semantics via session.add.",
            chunk_index=0,
            embedding=None,
            chunk_metadata=None,
        )
        pg_session.add(chunk)
        pg_session.flush()

        row = pg_session.execute(
            text("SELECT id FROM document_chunks WHERE id = :id AND chunk_metadata IS NULL"),
            {"id": str(chunk_id)},
        ).fetchone()
        assert row is not None, (
            "chunk_metadata=None via session.add was persisted as JSONB null, not SQL NULL."
        )

    def test_dict_persists_as_jsonb_object(self, pg_session: Session):
        """Sanity check: a real dict should persist as a JSONB object, not NULL."""
        doc, client = _make_doc_and_client(pg_session)
        chunk_id = uuid.uuid4()

        chunk = DocumentChunk(
            id=chunk_id,
            document_id=doc.id,
            client_id=client.id,
            chunk_text="Voucher chunk with metadata.",
            chunk_index=0,
            embedding=None,
            chunk_metadata={"is_voucher": True, "voucher_type": "1040-ES"},
        )
        pg_session.bulk_save_objects([chunk])
        pg_session.flush()

        jt_row = pg_session.execute(
            text("SELECT jsonb_typeof(chunk_metadata) AS jt FROM document_chunks WHERE id = :id"),
            {"id": str(chunk_id)},
        ).fetchone()
        assert jt_row.jt == "object", (
            f"Expected jsonb_typeof='object' for a dict, got {jt_row.jt!r}"
        )

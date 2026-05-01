# Regression tests for the conftest type-swap fix shipped 2026-04-30.
#
# These tests guard against future regressions of the destructive
# `Base.metadata` mutation in `tests/conftest.py::_create_test_engine`.
#
# Calibrated for fix Shape A:
#   - Under Shape A, both tests give true isolation guarantees.
#   - Under Shape B, Test 2 passes by accident during the session and
#     only verifies cleanup at teardown — it gives weaker mid-session
#     guarantees.
#   - Under Shape C, both tests pass trivially (no shared metadata).

from sqlalchemy.dialects.postgresql import JSONB

from app.core.database import Base

# Register the model that owns the target table
from app.models.document_chunk import DocumentChunk  # noqa: F401


TARGET_TABLE = "document_chunks"
TARGET_COLUMN = "chunk_metadata"


class TestCanonicalMetadataIsolation:
    """Base.metadata column types must not be mutated by the SQLite engine fixture."""

    def test_canonical_metadata_type_at_import(self):
        """The canonical column type for chunk_metadata must be JSONB at import time."""
        col = Base.metadata.tables[TARGET_TABLE].c[TARGET_COLUMN]
        assert isinstance(col.type, JSONB), (
            f"Expected canonical {TARGET_TABLE}.{TARGET_COLUMN} type to be JSONB, "
            f"got {type(col.type).__name__}. "
            "The conftest type-swap is leaking into Base.metadata."
        )

    def test_canonical_metadata_type_after_sqlite_engine(self, engine):
        """After the SQLite engine fixture runs, Base.metadata must still have JSONB."""
        col = Base.metadata.tables[TARGET_TABLE].c[TARGET_COLUMN]
        assert isinstance(col.type, JSONB), (
            f"Expected canonical {TARGET_TABLE}.{TARGET_COLUMN} type to be JSONB "
            f"after engine fixture, got {type(col.type).__name__}. "
            "The conftest type-swap is leaking into Base.metadata."
        )

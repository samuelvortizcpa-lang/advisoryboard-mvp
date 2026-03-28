"""
Tests for document upload and RAG pipeline.

Covers text chunking (basic, empty, overlap), Document model creation,
and DocumentChunk model creation (embedding skipped for SQLite).
"""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.services.chunking import chunk_text, MIN_CHUNK_LEN
from tests.conftest import make_client, make_org, make_user


# ---------------------------------------------------------------------------
# chunk_text
# ---------------------------------------------------------------------------


class TestChunkTextBasic:
    def test_chunk_text_basic(self):
        """Chunking service splits text into expected chunks."""
        # Build text with several paragraphs that together exceed chunk_size
        paragraphs = [f"Paragraph {i}. " + ("Lorem ipsum dolor sit amet. " * 10) for i in range(10)]
        text = "\n\n".join(paragraphs)

        chunks = chunk_text(text, chunk_size=500, overlap=50)

        assert len(chunks) > 1, "Text should be split into multiple chunks"
        for chunk in chunks:
            # Each chunk should not exceed chunk_size (plus some tolerance
            # for paragraph boundaries)
            assert len(chunk) <= 600, f"Chunk too large: {len(chunk)} chars"
            assert len(chunk) >= MIN_CHUNK_LEN, "Chunk should meet minimum length"

    def test_short_text_single_chunk(self):
        """Text shorter than chunk_size stays in a single chunk."""
        text = "This is a short document with enough text to pass the minimum length threshold for chunking."
        chunks = chunk_text(text, chunk_size=1500, overlap=200)

        assert len(chunks) == 1
        assert chunks[0] == text


class TestChunkTextEmpty:
    def test_empty_string(self):
        """Empty text returns empty list."""
        assert chunk_text("") == []

    def test_whitespace_only(self):
        """Whitespace-only text returns empty list."""
        assert chunk_text("   \n\n\t  ") == []

    def test_none_text(self):
        """None input returns empty list."""
        assert chunk_text(None) == []

    def test_tiny_text_below_minimum(self):
        """Text below MIN_CHUNK_LEN is discarded."""
        assert chunk_text("Hi") == []


class TestChunkTextOverlap:
    def test_chunks_have_proper_overlap(self):
        """Adjacent chunks share overlapping content."""
        # Create enough text to produce multiple chunks
        sentences = [f"Sentence number {i} contains some important information about tax returns." for i in range(30)]
        text = " ".join(sentences)

        chunks = chunk_text(text, chunk_size=300, overlap=100)

        assert len(chunks) >= 2, "Need at least 2 chunks to test overlap"

        # Check that consecutive chunks share some content
        for i in range(len(chunks) - 1):
            current_chunk = chunks[i]
            next_chunk = chunks[i + 1]

            # The end of the current chunk should overlap with the start
            # of the next chunk. Extract words to compare.
            current_words = current_chunk.split()
            next_words = next_chunk.split()

            # Find shared words between end of current and start of next
            shared = set(current_words[-15:]) & set(next_words[:15])
            assert len(shared) > 0, (
                f"Chunks {i} and {i + 1} should share overlapping content, "
                f"but no common words found in boundary region"
            )

    def test_zero_overlap(self):
        """Chunks with zero overlap do not repeat content (no crash)."""
        text = "\n\n".join([f"Paragraph {i} with enough content to be meaningful." for i in range(10)])
        chunks = chunk_text(text, chunk_size=200, overlap=0)
        assert len(chunks) >= 1


# ---------------------------------------------------------------------------
# Document model
# ---------------------------------------------------------------------------


class TestDocumentModelCreation:
    def test_document_model_creation(self, db: Session):
        """Document model can be created and persisted in test DB."""
        user = make_user(db)
        org = make_org(db, owner_user_id=user.clerk_id)
        client = make_client(db, user, org=org)

        doc_id = uuid.uuid4()
        doc = Document(
            id=doc_id,
            client_id=client.id,
            uploaded_by=user.id,
            filename="2024_1040.pdf",
            file_path="uploads/2024_1040.pdf",
            file_type="pdf",
            file_size=102400,
            processed=False,
            source="upload",
            upload_date=datetime.now(timezone.utc),
        )
        db.add(doc)
        db.flush()

        fetched = db.get(Document, doc_id)
        assert fetched is not None
        assert fetched.filename == "2024_1040.pdf"
        assert fetched.file_type == "pdf"
        assert fetched.file_size == 102400
        assert fetched.processed is False
        assert fetched.client_id == client.id
        assert fetched.uploaded_by == user.id

    def test_document_classification_fields(self, db: Session):
        """Document classification metadata can be set."""
        user = make_user(db)
        org = make_org(db, owner_user_id=user.clerk_id)
        client = make_client(db, user, org=org)

        doc = Document(
            id=uuid.uuid4(),
            client_id=client.id,
            uploaded_by=user.id,
            filename="K1_2024.pdf",
            file_path="uploads/K1_2024.pdf",
            file_type="pdf",
            file_size=51200,
            processed=True,
            source="upload",
            document_type="k1",
            document_subtype="partnership",
            document_period="2024",
            classification_confidence=0.95,
            upload_date=datetime.now(timezone.utc),
        )
        db.add(doc)
        db.flush()

        fetched = db.get(Document, doc.id)
        assert fetched.document_type == "k1"
        assert fetched.document_subtype == "partnership"
        assert fetched.document_period == "2024"
        assert fetched.classification_confidence == pytest.approx(0.95)


# ---------------------------------------------------------------------------
# DocumentChunk model
# ---------------------------------------------------------------------------


class TestDocumentChunkModelCreation:
    def test_document_chunk_model_creation(self, db: Session):
        """DocumentChunk model can be created in test DB (embedding skipped for SQLite)."""
        user = make_user(db)
        org = make_org(db, owner_user_id=user.clerk_id)
        client = make_client(db, user, org=org)

        doc = Document(
            id=uuid.uuid4(),
            client_id=client.id,
            uploaded_by=user.id,
            filename="meeting_notes.pdf",
            file_path="uploads/meeting_notes.pdf",
            file_type="pdf",
            file_size=8192,
            processed=True,
            source="upload",
            upload_date=datetime.now(timezone.utc),
        )
        db.add(doc)
        db.flush()

        chunk_id = uuid.uuid4()
        chunk = DocumentChunk(
            id=chunk_id,
            document_id=doc.id,
            client_id=client.id,
            chunk_text="The client discussed tax planning strategies for Q4 2024.",
            chunk_index=0,
            embedding=None,  # SQLite cannot store pgvector; leave null
        )
        db.add(chunk)
        db.flush()

        fetched = db.get(DocumentChunk, chunk_id)
        assert fetched is not None
        assert fetched.chunk_text == "The client discussed tax planning strategies for Q4 2024."
        assert fetched.chunk_index == 0
        assert fetched.document_id == doc.id
        assert fetched.client_id == client.id

    def test_multiple_chunks_for_document(self, db: Session):
        """Multiple chunks can be created for a single document."""
        user = make_user(db)
        org = make_org(db, owner_user_id=user.clerk_id)
        client = make_client(db, user, org=org)

        doc = Document(
            id=uuid.uuid4(),
            client_id=client.id,
            uploaded_by=user.id,
            filename="annual_report.pdf",
            file_path="uploads/annual_report.pdf",
            file_type="pdf",
            file_size=204800,
            processed=True,
            source="upload",
            upload_date=datetime.now(timezone.utc),
        )
        db.add(doc)
        db.flush()

        chunk_texts = [
            "Revenue increased by 15% year-over-year to $2.3M.",
            "Operating expenses were reduced through strategic cost optimization.",
            "The board approved a dividend distribution of $0.50 per share.",
        ]

        for i, text in enumerate(chunk_texts):
            chunk = DocumentChunk(
                id=uuid.uuid4(),
                document_id=doc.id,
                client_id=client.id,
                chunk_text=text,
                chunk_index=i,
                embedding=None,
            )
            db.add(chunk)

        db.flush()

        # Query all chunks for this document
        chunks = (
            db.query(DocumentChunk)
            .filter(DocumentChunk.document_id == doc.id)
            .order_by(DocumentChunk.chunk_index)
            .all()
        )

        assert len(chunks) == 3
        assert chunks[0].chunk_index == 0
        assert chunks[1].chunk_index == 1
        assert chunks[2].chunk_index == 2
        assert "Revenue" in chunks[0].chunk_text
        assert "dividend" in chunks[2].chunk_text

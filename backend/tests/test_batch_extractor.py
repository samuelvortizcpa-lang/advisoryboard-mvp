"""
Unit tests for BatchExtractor.

These tests use unittest.mock to stub out google-cloud-storage
and google-cloud-documentai. No real network calls. No real
credentials required.

Covers the orchestration logic end-to-end: upload → submit →
poll → list shards → download → merge. Each failure mode in
the three-branch error taxonomy (DocAIStagingFailed,
DocAIBatchTimeout, DocAIBatchFailed) is exercised separately.

Run:
    pytest tests/test_batch_extractor.py -v
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from app.services.batch_extractor import (
    BatchExtractor,
    DocAIBatchError,
    DocAIStagingFailed,
    DocAIBatchTimeout,
    DocAIBatchFailed,
    _download_shard,
    _extract_page_text,
    _list_output_shards,
    _upload_to_gcs,
)


# ── Mock builders ──────────────────────────────────────────────────────────


def _make_shard_blob(name: str, shard_json: dict) -> MagicMock:
    """Mock a storage.Blob whose download_as_bytes returns shard JSON."""
    blob = MagicMock()
    blob.name = name
    blob.download_as_bytes.return_value = json.dumps(shard_json).encode("utf-8")
    return blob


def _make_storage_client(shard_blobs: list[MagicMock]) -> MagicMock:
    """
    Build a mock storage.Client where:
    - client.bucket(name) returns a bucket mock whose blob(path) returns
      a fresh blob mock (for uploads + downloads)
    - client.list_blobs(bucket, prefix) iterates the given shard_blobs
    """
    client = MagicMock()

    # bucket(name).blob(path) chain — used by _upload_to_gcs and _download_shard
    def bucket_factory(name):
        bucket = MagicMock()
        # list_blobs path uses the bucket as an argument, so blob(path)
        # is only hit for uploads and single downloads.
        # For downloads, we route by object_path to the right shard_blob.
        def blob_factory(path):
            # If the path matches a known shard blob, return that blob.
            for sb in shard_blobs:
                if sb.name == path:
                    return sb
            # Otherwise return a fresh blob (upload path).
            return MagicMock()
        bucket.blob.side_effect = blob_factory
        return bucket

    client.bucket.side_effect = bucket_factory
    client.list_blobs.return_value = iter(shard_blobs)
    return client


def _make_docai_client(operation_result_fn=None, submit_raises=None) -> MagicMock:
    """
    Build a mock DocAI client where batch_process_documents either
    returns an operation mock or raises submit_raises. The operation's
    .result() calls operation_result_fn (which may raise for timeout).
    """
    client = MagicMock()

    if submit_raises is not None:
        client.batch_process_documents.side_effect = submit_raises
        return client

    operation = MagicMock()
    if operation_result_fn is None:
        operation.result.return_value = None
    else:
        operation.result.side_effect = operation_result_fn
    client.batch_process_documents.return_value = operation
    return client


def _make_shard(
    pages_spec: list[tuple[int, int, int]],
    text: str = "Page one text. Page two text. Page three text.",
) -> dict:
    """
    Build a shard-JSON dict with the given pages.

    pages_spec: list of (page_number, start_offset, end_offset) tuples
    indicating the slice of `text` that each page covers.
    """
    return {
        "text": text,
        "pages": [
            {
                "pageNumber": pn,
                "layout": {
                    "textAnchor": {
                        "textSegments": [
                            {"startIndex": start, "endIndex": end},
                        ]
                    }
                },
            }
            for pn, start, end in pages_spec
        ],
    }


# ── Tests ───────────────────────────────────────────────────────────────────


def test_constructor_requires_bucket(monkeypatch):
    """BatchExtractor raises ValueError if bucket is unavailable."""
    monkeypatch.delenv("DOCAI_GCS_BUCKET", raising=False)
    with pytest.raises(ValueError, match="DOCAI_GCS_BUCKET"):
        BatchExtractor()


def test_constructor_uses_env_var(monkeypatch):
    """BatchExtractor pulls bucket from DOCAI_GCS_BUCKET env var."""
    monkeypatch.setenv("DOCAI_GCS_BUCKET", "env-bucket")
    ex = BatchExtractor()
    assert ex.bucket_name == "env-bucket"


def test_extract_happy_path():
    """
    End-to-end: upload → submit → poll → list → download → merge.
    Returns a dict with pages sorted by page_number.
    """
    # Shard covers pages 1-3 with 'A', 'B', 'C' slices
    shard_json = _make_shard(
        pages_spec=[(1, 0, 1), (2, 1, 2), (3, 2, 3)],
        text="ABC",
    )
    shard_blob = _make_shard_blob(
        "output/docid/opid/0-0.json", shard_json,
    )
    storage_client = _make_storage_client([shard_blob])
    docai_client = _make_docai_client()

    ex = BatchExtractor(
        bucket_name="test-bucket",
        storage_client_factory=lambda: storage_client,
        docai_client_factory=lambda: docai_client,
    )

    result = ex.extract(
        file_bytes=b"pdf-bytes",
        document_id="docid",
        processor_name="projects/p/locations/us/processors/proc",
    )

    assert result is not None
    assert "text" in result
    assert "pages" in result
    assert result["text"] == "ABC"
    assert [p["page_number"] for p in result["pages"]] == [1, 2, 3]
    assert [p["text"] for p in result["pages"]] == ["A", "B", "C"]


def test_extract_multi_shard_sorts_by_page_number():
    """
    Two shards: first contains pages 3-4, second contains pages 1-2.
    Final output must be sorted [1,2,3,4] regardless of shard order.
    """
    shard_2 = _make_shard(
        pages_spec=[(3, 0, 1), (4, 1, 2)],
        text="CD",
    )
    shard_1 = _make_shard(
        pages_spec=[(1, 0, 1), (2, 1, 2)],
        text="AB",
    )
    blob_2 = _make_shard_blob("output/docid/opid/0-0.json", shard_2)
    blob_1 = _make_shard_blob("output/docid/opid/0-1.json", shard_1)
    storage_client = _make_storage_client([blob_2, blob_1])
    docai_client = _make_docai_client()

    ex = BatchExtractor(
        bucket_name="test-bucket",
        storage_client_factory=lambda: storage_client,
        docai_client_factory=lambda: docai_client,
    )

    result = ex.extract(
        file_bytes=b"pdf", document_id="docid",
        processor_name="projects/p/locations/us/processors/proc",
    )

    assert [p["page_number"] for p in result["pages"]] == [1, 2, 3, 4]
    assert [p["text"] for p in result["pages"]] == ["A", "B", "C", "D"]
    # Combined text: shard_1 first (starts at page 1), shard_2 second
    assert result["text"] == "AB" + "CD"


def test_extract_empty_shards_raises_batch_failed():
    """Batch succeeded but produced no output → DocAIBatchFailed."""
    storage_client = _make_storage_client([])
    docai_client = _make_docai_client()

    ex = BatchExtractor(
        bucket_name="test-bucket",
        storage_client_factory=lambda: storage_client,
        docai_client_factory=lambda: docai_client,
    )

    with pytest.raises(DocAIBatchFailed, match="no output shards"):
        ex.extract(
            file_bytes=b"pdf", document_id="docid",
            processor_name="projects/p/locations/us/processors/proc",
        )


def test_extract_gcs_upload_failure_raises_staging_failed():
    """GCS upload raises → DocAIStagingFailed propagates."""
    bad_bucket = MagicMock()
    bad_blob = MagicMock()
    bad_blob.upload_from_string.side_effect = RuntimeError("GCS down")
    bad_bucket.blob.return_value = bad_blob
    storage_client = MagicMock()
    storage_client.bucket.return_value = bad_bucket

    docai_client = _make_docai_client()

    ex = BatchExtractor(
        bucket_name="test-bucket",
        storage_client_factory=lambda: storage_client,
        docai_client_factory=lambda: docai_client,
    )

    with pytest.raises(DocAIStagingFailed, match="GCS upload failed"):
        ex.extract(
            file_bytes=b"pdf", document_id="docid",
            processor_name="projects/p/locations/us/processors/proc",
        )


def test_extract_submit_failure_raises_batch_failed():
    """batch_process_documents raises → DocAIBatchFailed."""
    storage_client = _make_storage_client([])
    docai_client = _make_docai_client(
        submit_raises=RuntimeError("DocAI 500"),
    )

    ex = BatchExtractor(
        bucket_name="test-bucket",
        storage_client_factory=lambda: storage_client,
        docai_client_factory=lambda: docai_client,
    )

    with pytest.raises(DocAIBatchFailed, match="submit failed"):
        ex.extract(
            file_bytes=b"pdf", document_id="docid",
            processor_name="projects/p/locations/us/processors/proc",
        )


def test_extract_poll_timeout_raises_batch_timeout():
    """
    operation.result() raises and elapsed >= poll_timeout - 1
    → DocAIBatchTimeout classification fires.

    We set poll_timeout=0 so any elapsed time exceeds (0 - 1 = -1).
    """
    storage_client = _make_storage_client([])
    docai_client = _make_docai_client(
        operation_result_fn=lambda *a, **kw: (_ for _ in ()).throw(
            TimeoutError("deadline exceeded")
        ),
    )

    ex = BatchExtractor(
        bucket_name="test-bucket",
        storage_client_factory=lambda: storage_client,
        docai_client_factory=lambda: docai_client,
        poll_timeout=0,
    )

    with pytest.raises(DocAIBatchTimeout, match="exceeded"):
        ex.extract(
            file_bytes=b"pdf", document_id="docid",
            processor_name="projects/p/locations/us/processors/proc",
        )


def test_extract_poll_non_timeout_failure_raises_batch_failed():
    """
    operation.result() raises and elapsed < poll_timeout - 1
    → DocAIBatchFailed (not timeout).

    With poll_timeout=3600, any quick failure is NOT classified
    as timeout.
    """
    storage_client = _make_storage_client([])
    docai_client = _make_docai_client(
        operation_result_fn=lambda *a, **kw: (_ for _ in ()).throw(
            RuntimeError("internal server error")
        ),
    )

    ex = BatchExtractor(
        bucket_name="test-bucket",
        storage_client_factory=lambda: storage_client,
        docai_client_factory=lambda: docai_client,
        poll_timeout=3600,
    )

    with pytest.raises(DocAIBatchFailed, match="Batch operation failed"):
        ex.extract(
            file_bytes=b"pdf", document_id="docid",
            processor_name="projects/p/locations/us/processors/proc",
        )


def test_extract_shard_parse_failure_raises_batch_failed():
    """A shard with invalid JSON → DocAIBatchFailed."""
    bad_blob = MagicMock()
    bad_blob.name = "output/docid/opid/0-0.json"
    bad_blob.download_as_bytes.return_value = b"{not valid json"
    storage_client = _make_storage_client([bad_blob])
    docai_client = _make_docai_client()

    ex = BatchExtractor(
        bucket_name="test-bucket",
        storage_client_factory=lambda: storage_client,
        docai_client_factory=lambda: docai_client,
    )

    with pytest.raises(DocAIBatchFailed, match="parse failed"):
        ex.extract(
            file_bytes=b"pdf", document_id="docid",
            processor_name="projects/p/locations/us/processors/proc",
        )


def test_extract_page_text_offset_extraction():
    """_extract_page_text slices correctly using textSegments offsets."""
    page = {
        "layout": {
            "textAnchor": {
                "textSegments": [
                    {"startIndex": 5, "endIndex": 10},
                ]
            }
        }
    }
    result = _extract_page_text("01234hello56789", page)
    assert result == "hello"


def test_extract_page_text_multiple_segments():
    """Multiple textSegments are concatenated in order."""
    page = {
        "layout": {
            "textAnchor": {
                "textSegments": [
                    {"startIndex": 0, "endIndex": 3},
                    {"startIndex": 10, "endIndex": 13},
                ]
            }
        }
    }
    result = _extract_page_text("ABC-------XYZ---", page)
    assert result == "ABCXYZ"


def test_extract_page_text_missing_layout_returns_empty():
    """Missing layout returns empty string, doesn't raise."""
    assert _extract_page_text("text", {}) == ""
    assert _extract_page_text("text", {"layout": {}}) == ""
    assert _extract_page_text(
        "text", {"layout": {"textAnchor": {}}}
    ) == ""
    assert _extract_page_text(
        "text", {"layout": {"textAnchor": {"textSegments": []}}}
    ) == ""

"""
Document AI batch processing extractor.

Handles documents too large for online sync (>30 pages with
imageless_mode, >15 without). Uses Google Cloud Storage for
input staging and output collection per design doc
AdvisoryBoard_DocAI_Batch_Architecture.md §3.4.

This module is infrastructure for future dispatcher work. It
does NOT plug into extract_text_with_docai yet — that wiring
lands in a subsequent session.

Flow:
  1. Upload file_bytes to gs://{bucket}/input/{document_id}/file.pdf
  2. Submit BatchProcessRequest with GCS input + output locations
  3. Poll long-running operation (up to 10 min)
  4. List output JSON shards, download each, deserialize, merge
     into a single pages list sorted by pageNumber
  5. Return dict in same shape as OnlineExtractor:
       {"text": str, "pages": list[{"page_number": int, "text": str}]}

Cleanup:
  GCS lifecycle policy auto-deletes all objects after 7 days.
  No explicit delete here — per design §3.4 rationale.
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any

logger = logging.getLogger(__name__)


# ── Custom exceptions ──────────────────────────────────────────────────────


class DocAIBatchError(Exception):
    """Base class for all batch-processing failures. Callers can catch
    this single type to fall through to text_extraction gracefully."""


class DocAIStagingFailed(DocAIBatchError):
    """GCS upload of the input PDF failed."""


class DocAIBatchTimeout(DocAIBatchError):
    """Batch long-running operation exceeded the poll timeout."""


class DocAIBatchFailed(DocAIBatchError):
    """Batch LRO reported FAILED state. Message preserves state_message
    from the DocAI operation for debugging."""


# ── GCS helpers (module-level; each opens its own client if needed) ────────


def _upload_to_gcs(
    storage_client: Any, bucket_name: str, object_path: str, file_bytes: bytes
) -> str:
    """
    Upload bytes to gs://{bucket_name}/{object_path}. Returns the full
    gs:// URI on success. Raises DocAIStagingFailed on any GCS error.

    storage_client is injected (not instantiated here) so tests can
    pass a mock.
    """
    try:
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(object_path)
        blob.upload_from_string(file_bytes, content_type="application/pdf")
    except Exception as exc:
        raise DocAIStagingFailed(
            f"GCS upload failed: gs://{bucket_name}/{object_path}: {exc}"
        ) from exc

    return f"gs://{bucket_name}/{object_path}"


def _list_output_shards(
    storage_client: Any, bucket_name: str, prefix: str
) -> list[str]:
    """
    List JSON shard URIs under gs://{bucket_name}/{prefix}. Returns a
    list of gs:// URIs (may be empty if batch produced no output).

    DocAI batch output file names look like <operation_id>-N.json, where
    N is the shard index. Only .json blobs are returned; any other
    objects under the prefix are ignored defensively.
    """
    bucket = storage_client.bucket(bucket_name)
    uris: list[str] = []
    for blob in storage_client.list_blobs(bucket, prefix=prefix):
        if blob.name.endswith(".json"):
            uris.append(f"gs://{bucket_name}/{blob.name}")
    return uris


def _download_shard(storage_client: Any, uri: str) -> dict:
    """
    Download one JSON shard from a gs:// URI and deserialize as dict.
    Returns the parsed dict (DocAI's Document proto serialized to JSON).

    Raises DocAIBatchFailed if the URI is malformed, the blob does not
    exist, or the content is not valid JSON.
    """
    import json as _json

    if not uri.startswith("gs://"):
        raise DocAIBatchFailed(f"Invalid GCS URI (no gs:// prefix): {uri}")

    path = uri[len("gs://"):]
    if "/" not in path:
        raise DocAIBatchFailed(f"Invalid GCS URI (no object path): {uri}")

    bucket_name, object_path = path.split("/", 1)

    try:
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(object_path)
        raw = blob.download_as_bytes()
    except Exception as exc:
        raise DocAIBatchFailed(
            f"GCS download failed: {uri}: {exc}"
        ) from exc

    try:
        return _json.loads(raw)
    except Exception as exc:
        raise DocAIBatchFailed(
            f"Shard JSON parse failed: {uri}: {exc}"
        ) from exc


def _extract_page_text(full_text: str, page_dict: dict) -> str:
    """
    Extract a page's text slice from the shard's flat text using
    page.layout.textAnchor.textSegments offsets. Matches the pattern
    document_ai_service._get_text_from_layout uses for online responses.

    DocAI returns page boundaries as (startIndex, endIndex) offsets
    into the Document's flat text field, not as pre-sliced strings.
    Returns empty string on missing/malformed layout rather than
    raising — a single bad page should not fail the whole extract.
    """
    layout = page_dict.get("layout") or {}
    text_anchor = layout.get("textAnchor") or {}
    segments = text_anchor.get("textSegments") or []
    if not segments:
        return ""

    parts: list[str] = []
    for seg in segments:
        start = int(seg.get("startIndex", 0) or 0)
        end = int(seg.get("endIndex", 0) or 0)
        if end <= start:
            continue
        parts.append(full_text[start:end])
    return "".join(parts)


# ── BatchExtractor ─────────────────────────────────────────────────────────


class BatchExtractor:
    """
    Document AI batch processing with GCS staging.

    Usage:
        extractor = BatchExtractor()
        result = extractor.extract(file_bytes, document_id="...")
        # result is dict | None matching OnlineExtractor shape

    For testing, pass storage_client_factory and docai_client_factory
    to inject mocks:
        extractor = BatchExtractor(
            storage_client_factory=lambda: mock_storage_client,
            docai_client_factory=lambda: mock_docai_client,
        )
    """

    # Default poll timeout in seconds (10 min per design §3.6)
    DEFAULT_POLL_TIMEOUT = 600

    def __init__(
        self,
        bucket_name: str | None = None,
        storage_client_factory: Any = None,
        docai_client_factory: Any = None,
        poll_timeout: int = DEFAULT_POLL_TIMEOUT,
    ):
        """
        bucket_name defaults to DOCAI_GCS_BUCKET env var. Raises
        ValueError if neither is set.

        storage_client_factory and docai_client_factory are callables
        that return fresh clients. Default factories instantiate real
        Google SDK clients. Tests override to inject mocks.
        """
        resolved_bucket = bucket_name or os.getenv("DOCAI_GCS_BUCKET")
        if not resolved_bucket:
            raise ValueError(
                "BatchExtractor requires bucket_name arg or "
                "DOCAI_GCS_BUCKET env var"
            )
        self.bucket_name = resolved_bucket
        self._storage_client_factory = (
            storage_client_factory or self._default_storage_client
        )
        self._docai_client_factory = (
            docai_client_factory or self._default_docai_client
        )
        self.poll_timeout = poll_timeout

    @staticmethod
    def _default_storage_client() -> Any:
        """
        Lazily import + instantiate google-cloud-storage client.

        Uses service-account credentials from GOOGLE_APPLICATION_CREDENTIALS_JSON
        env var — same pattern as document_ai_service._get_client.
        """
        import json as _json

        from google.cloud import storage
        from google.oauth2 import service_account

        creds_json = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")
        if not creds_json:
            raise DocAIBatchError(
                "BatchExtractor: GOOGLE_APPLICATION_CREDENTIALS_JSON not set; "
                "cannot create GCS client"
            )

        project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        if not project_id:
            raise DocAIBatchError(
                "BatchExtractor: GOOGLE_CLOUD_PROJECT not set; "
                "cannot create GCS client"
            )

        creds_info = _json.loads(creds_json)
        credentials = service_account.Credentials.from_service_account_info(creds_info)
        return storage.Client(credentials=credentials, project=project_id)

    @staticmethod
    def _default_docai_client() -> Any:
        """
        Lazily import + instantiate DocumentProcessorServiceClient for batch.

        Uses service-account credentials from GOOGLE_APPLICATION_CREDENTIALS_JSON
        env var — same pattern as document_ai_service._get_client.
        """
        import json as _json

        from google.cloud import documentai
        from google.oauth2 import service_account

        creds_json = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")
        if not creds_json:
            raise DocAIBatchError(
                "BatchExtractor: GOOGLE_APPLICATION_CREDENTIALS_JSON not set; "
                "cannot create DocAI client"
            )

        creds_info = _json.loads(creds_json)
        credentials = service_account.Credentials.from_service_account_info(creds_info)
        return documentai.DocumentProcessorServiceClient(credentials=credentials)

    def extract(
        self,
        file_bytes: bytes,
        document_id: str,
        processor_name: str,
    ) -> dict | None:
        """
        Run a document through DocAI batch processing.

        processor_name is the full resource path:
          projects/{project}/locations/{loc}/processors/{processor_id}
        Caller chooses which processor (form_parser vs ocr) since
        BatchExtractor is processor-agnostic.

        Returns dict matching OnlineExtractor shape:
          {"text": str, "pages": [{"page_number": int, "text": str}, ...]}

        Raises DocAIBatchError subclasses on unrecoverable errors.
        Caller chooses whether to fall through to text_extraction.
        """
        import time

        from google.cloud import documentai

        operation_id = str(uuid.uuid4())
        logger.info(
            "BatchExtractor.extract start: document_id=%s operation_id=%s "
            "bucket=%s",
            document_id, operation_id, self.bucket_name,
        )

        # Per design §3.2, input and output paths are keyed on document_id
        # (and operation_id on output so repeat reprocesses don't collide).
        input_path = f"input/{document_id}/{operation_id}.pdf"
        output_prefix = f"output/{document_id}/{operation_id}/"

        storage_client = self._storage_client_factory()
        docai_client = self._docai_client_factory()

        # Step 1: stage PDF to GCS input path
        input_uri = _upload_to_gcs(
            storage_client, self.bucket_name, input_path, file_bytes,
        )
        logger.info(
            "BatchExtractor: staged input: %s (operation_id=%s)",
            input_uri, operation_id,
        )

        # Step 2: build + submit batch request
        output_uri = f"gs://{self.bucket_name}/{output_prefix}"
        request = documentai.BatchProcessRequest(
            name=processor_name,
            input_documents=documentai.BatchDocumentsInputConfig(
                gcs_documents=documentai.GcsDocuments(
                    documents=[
                        documentai.GcsDocument(
                            gcs_uri=input_uri,
                            mime_type="application/pdf",
                        )
                    ]
                )
            ),
            document_output_config=documentai.DocumentOutputConfig(
                gcs_output_config=documentai.DocumentOutputConfig.GcsOutputConfig(
                    gcs_uri=output_uri,
                )
            ),
        )

        submit_start = time.monotonic()
        try:
            operation = docai_client.batch_process_documents(request=request)
        except Exception as exc:
            raise DocAIBatchFailed(
                f"batch_process_documents submit failed: {exc}"
            ) from exc

        logger.info(
            "BatchExtractor: batch submitted, polling (timeout=%ds, "
            "operation_id=%s)",
            self.poll_timeout, operation_id,
        )

        # Step 3: poll LRO; result() blocks until done or timeout.
        # Classify by elapsed-vs-timeout rather than exception type
        # because Google's SDK has surfaced timeouts as several
        # different exception types across versions.
        try:
            operation.result(timeout=self.poll_timeout)
        except Exception as exc:
            elapsed = time.monotonic() - submit_start
            if elapsed >= self.poll_timeout - 1:
                raise DocAIBatchTimeout(
                    f"Batch operation exceeded {self.poll_timeout}s timeout "
                    f"(operation_id={operation_id}): {exc}"
                ) from exc
            raise DocAIBatchFailed(
                f"Batch operation failed "
                f"(operation_id={operation_id}, elapsed={elapsed:.1f}s): {exc}"
            ) from exc

        elapsed = time.monotonic() - submit_start
        logger.info(
            "BatchExtractor: batch complete in %.1fs (operation_id=%s)",
            elapsed, operation_id,
        )

        # Step 4: list shards under output prefix
        shard_uris = _list_output_shards(
            storage_client, self.bucket_name, output_prefix,
        )
        if not shard_uris:
            raise DocAIBatchFailed(
                f"Batch succeeded but produced no output shards under "
                f"gs://{self.bucket_name}/{output_prefix}"
            )
        logger.info(
            "BatchExtractor: downloading %d shard(s)", len(shard_uris),
        )

        # Step 5: download shards, extract page text slices.
        #
        # Each shard is a Document proto serialized as JSON. Shards may
        # split a document at page boundaries — we collect all pages
        # from all shards, sorted by pageNumber for a contiguous result.
        all_pages: list[tuple[int, str]] = []  # (page_number, text)
        shard_texts: list[tuple[int, str]] = []  # (first_page_num, shard_text)

        for uri in shard_uris:
            shard = _download_shard(storage_client, uri)
            shard_text = shard.get("text", "")
            shard_pages = shard.get("pages", [])

            first_page_num_in_shard: int | None = None
            for page in shard_pages:
                page_num = int(page.get("pageNumber", 0)) or 0
                page_text = _extract_page_text(shard_text, page)
                all_pages.append((page_num, page_text))
                if first_page_num_in_shard is None:
                    first_page_num_in_shard = page_num

            if first_page_num_in_shard is not None:
                shard_texts.append((first_page_num_in_shard, shard_text))

        # Step 6: sort by page_number, build return dict matching OnlineExtractor
        all_pages.sort(key=lambda pt: pt[0])
        shard_texts.sort(key=lambda st: st[0])

        pages_out = [
            {"page_number": pn, "text": pt}
            for pn, pt in all_pages
        ]
        text_out = "".join(st for _, st in shard_texts)

        logger.info(
            "BatchExtractor.extract complete: document_id=%s "
            "operation_id=%s pages=%d text_chars=%d elapsed=%.1fs",
            document_id, operation_id, len(pages_out), len(text_out), elapsed,
        )

        return {
            "text": text_out,
            "pages": pages_out,
        }

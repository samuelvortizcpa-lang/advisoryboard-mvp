"""
Storage service: Supabase Storage backend for file uploads/downloads.

All files are stored in the "documents" bucket with the key pattern:
    {user_id}/{client_id}/{file_id}_{filename}

The value stored in Document.file_path is the storage path string
(e.g. "abc/def/1234_report.pdf").

Requires SUPABASE_URL and SUPABASE_SERVICE_KEY environment variables.
"""

from __future__ import annotations

import logging
import os
import tempfile

from supabase import create_client, Client

logger = logging.getLogger(__name__)

BUCKET = "documents"


def _get_client() -> Client:
    """Create and return a Supabase client using env vars."""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_KEY must be set"
        )
    return create_client(url, key)


def upload_file(
    user_id: str,
    client_id: str,
    file_id: str,
    filename: str,
    file_bytes: bytes,
    content_type: str,
) -> str:
    """
    Upload file bytes to Supabase Storage.

    Returns the storage path string.
    """
    storage_path = f"{user_id}/{client_id}/{file_id}_{filename}"
    try:
        client = _get_client()
        client.storage.from_(BUCKET).upload(
            path=storage_path,
            file=file_bytes,
            file_options={"content-type": content_type},
        )
        logger.info("Uploaded %d bytes to %s/%s", len(file_bytes), BUCKET, storage_path)
        return storage_path
    except Exception:
        logger.exception("Failed to upload file to %s/%s", BUCKET, storage_path)
        raise


def download_file(storage_path: str) -> bytes:
    """
    Download file bytes from Supabase Storage.

    Returns the raw file bytes.
    """
    try:
        client = _get_client()
        data = client.storage.from_(BUCKET).download(storage_path)
        logger.info("Downloaded %d bytes from %s/%s", len(data), BUCKET, storage_path)
        return data
    except Exception:
        logger.exception("Failed to download file from %s/%s", BUCKET, storage_path)
        raise


def delete_file(storage_path: str) -> None:
    """Delete a file from Supabase Storage."""
    try:
        client = _get_client()
        client.storage.from_(BUCKET).remove([storage_path])
        logger.info("Deleted %s/%s", BUCKET, storage_path)
    except Exception:
        logger.exception("Failed to delete file %s/%s", BUCKET, storage_path)


def get_temp_local_path(storage_path: str) -> str:
    """
    Download a file to a temporary local path and return that path.

    The caller is responsible for deleting the temp file when done.
    """
    try:
        file_bytes = download_file(storage_path)
        suffix = ""
        if "." in storage_path:
            suffix = "." + storage_path.rsplit(".", 1)[-1]
        tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        tmp.write(file_bytes)
        tmp.close()
        logger.info("Wrote temp file %s for %s", tmp.name, storage_path)
        return tmp.name
    except Exception:
        logger.exception("Failed to create temp file for %s/%s", BUCKET, storage_path)
        raise

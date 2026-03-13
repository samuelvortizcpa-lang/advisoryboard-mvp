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


def upload_file_to_path(
    storage_path: str,
    file_bytes: bytes,
    content_type: str,
) -> str:
    """
    Upload file bytes to an explicit Supabase Storage path.

    Unlike `upload_file()`, which builds the path from user/client/file IDs,
    this function takes the full storage path directly.  Used for page images.

    Returns the storage path string.
    """
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


def get_signed_url(storage_path: str, expires_in: int = 3600) -> str:
    """
    Generate a time-limited signed URL for a file in Supabase Storage.

    Args:
        storage_path: The storage path of the file.
        expires_in: Seconds until the URL expires (default 1 hour).

    Returns:
        A signed URL string for direct browser access.
    """
    try:
        client = _get_client()
        result = client.storage.from_(BUCKET).create_signed_url(
            storage_path, expires_in
        )
        signed_url = result.get("signedURL") or result.get("signedUrl") or ""
        if not signed_url:
            raise ValueError(f"No signed URL returned for {storage_path}")
        logger.debug("Generated signed URL for %s/%s (expires in %ds)", BUCKET, storage_path, expires_in)
        return signed_url
    except Exception:
        logger.exception("Failed to generate signed URL for %s/%s", BUCKET, storage_path)
        raise


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

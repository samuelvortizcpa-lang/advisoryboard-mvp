"""
Storage service: abstraction over Railway Object Storage, AWS S3, and local
filesystem.

Backend priority (first match wins):
  1. Railway Object Storage — set RAILWAY_STORAGE_ACCESS_KEY_ID,
     RAILWAY_STORAGE_SECRET_ACCESS_KEY, RAILWAY_STORAGE_ENDPOINT_URL,
     and RAILWAY_STORAGE_BUCKET_NAME (Railway auto-injects these when you
     attach an Object Storage service to your project).
  2. AWS S3 — set AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, and
     S3_BUCKET_NAME (plus optionally AWS_REGION, default us-east-1).
  3. Local filesystem — ``uploads/`` directory relative to the backend root.
     No configuration needed; used automatically when neither cloud backend
     is configured, so local development works without any credentials.

Both Railway Object Storage and AWS S3 expose an S3-compatible API, so the
same boto3 operations work for both — the only difference is the endpoint URL
(Railway uses a custom endpoint; AWS uses the default regional endpoint).

File key pattern (S3 key or relative path under uploads/):
    {user_id}/{client_id}/{uuid}_{filename}

The value stored in Document.file_path is:
  • Cloud mode → the S3 object key  (e.g. "abc/def/1234_report.pdf")
  • Local mode → the absolute filesystem path  (e.g. "/app/uploads/abc/…")

All public functions accept whichever value is present in Document.file_path
and dispatch to the right backend automatically.
"""

from __future__ import annotations

import contextlib
import io
import logging
import mimetypes
import os
import tempfile
from enum import Enum
from pathlib import Path
from typing import Generator

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Local fallback root — same resolution as the original document_service
UPLOAD_ROOT = Path(__file__).resolve().parent.parent.parent / "uploads"


# ─── Storage mode ─────────────────────────────────────────────────────────────


class _Mode(str, Enum):
    RAILWAY = "railway"   # Railway Object Storage (S3-compatible)
    AWS     = "aws"       # AWS S3
    LOCAL   = "local"     # local filesystem fallback


def _storage_mode() -> _Mode:
    """
    Determine the active storage backend.

    Priority: Railway Object Storage → AWS S3 → local filesystem.
    """
    s = get_settings()
    if s.railway_storage_enabled:
        return _Mode.RAILWAY
    if s.aws_storage_enabled:
        return _Mode.AWS
    return _Mode.LOCAL


# ─── MIME type helper ─────────────────────────────────────────────────────────

_CONTENT_TYPES: dict[str, str] = {
    "pdf":  "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "doc":  "application/msword",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xls":  "application/vnd.ms-excel",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "txt":  "text/plain",
    "csv":  "text/csv",
    "json": "application/json",
    "mp4":  "video/mp4",
    "mp3":  "audio/mpeg",
    "m4a":  "audio/mp4",
    "wav":  "audio/wav",
    "eml":  "message/rfc822",
    "msg":  "application/vnd.ms-outlook",
}


def content_type_for(filename: str) -> str:
    """Return the best MIME type for *filename*, falling back to octet-stream."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in _CONTENT_TYPES:
        return _CONTENT_TYPES[ext]
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or "application/octet-stream"


# ─── Public mode check ────────────────────────────────────────────────────────


def is_s3_enabled() -> bool:
    """
    Return True when any cloud storage backend is active (Railway or AWS).

    When False, the local filesystem fallback is used.
    """
    return _storage_mode() != _Mode.LOCAL


# ─── boto3 client + bucket factory ───────────────────────────────────────────


def _get_cloud_config():
    """
    Return ``(boto3_client, bucket_name)`` for the active cloud backend.

    Railway Object Storage uses a custom ``endpoint_url``; AWS uses the default
    regional endpoint.  Both are otherwise identical from boto3's perspective.
    """
    import boto3  # noqa: PLC0415 — lazy import so boto3 is optional

    s = get_settings()
    mode = _storage_mode()

    if mode == _Mode.RAILWAY:
        client = boto3.client(
            "s3",
            aws_access_key_id=s.railway_storage_access_key_id,
            aws_secret_access_key=s.railway_storage_secret_access_key,
            endpoint_url=s.railway_storage_endpoint_url,
        )
        return client, s.railway_storage_bucket_name

    # AWS S3
    client = boto3.client(
        "s3",
        aws_access_key_id=s.aws_access_key_id,
        aws_secret_access_key=s.aws_secret_access_key,
        region_name=s.aws_region or "us-east-1",
    )
    return client, s.s3_bucket_name


# ─── Upload ───────────────────────────────────────────────────────────────────


def upload_file(
    file_bytes: bytes,
    key: str,
    content_type: str = "application/octet-stream",
) -> str:
    """
    Upload *file_bytes* to cloud storage at *key*, or write to local disk.

    Returns:
      • Cloud mode → the object key (store this in Document.file_path)
      • Local mode → the absolute filesystem path
    """
    mode = _storage_mode()
    if mode != _Mode.LOCAL:
        return _cloud_upload(file_bytes, key, content_type, mode)
    return _local_upload(file_bytes, key)


def _cloud_upload(file_bytes: bytes, key: str, content_type: str, mode: _Mode) -> str:
    client, bucket = _get_cloud_config()
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=file_bytes,
        ContentType=content_type,
    )
    logger.debug(
        "%s: uploaded %d bytes — bucket=%s key=%s",
        mode.value, len(file_bytes), bucket, key,
    )
    return key


def _local_upload(file_bytes: bytes, key: str) -> str:
    path = UPLOAD_ROOT / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(file_bytes)
    logger.debug("Local: wrote %d bytes to %s", len(file_bytes), path)
    return str(path)


# ─── Download ─────────────────────────────────────────────────────────────────


def download_file(key_or_path: str) -> bytes:
    """
    Return the raw bytes for the object identified by *key_or_path*.

    *key_or_path* is the value stored in Document.file_path — a cloud object
    key in cloud mode, or an absolute local path in local mode.
    """
    if is_s3_enabled():
        return _cloud_download(key_or_path)
    return Path(key_or_path).read_bytes()


def _cloud_download(key: str) -> bytes:
    client, bucket = _get_cloud_config()
    buf = io.BytesIO()
    client.download_fileobj(bucket, key, buf)
    return buf.getvalue()


# ─── Delete ───────────────────────────────────────────────────────────────────


def delete_file(key_or_path: str) -> None:
    """Delete the file. Non-fatal if the file does not exist."""
    if is_s3_enabled():
        _cloud_delete(key_or_path)
    else:
        _local_delete(key_or_path)


def _cloud_delete(key: str) -> None:
    client, bucket = _get_cloud_config()
    try:
        client.delete_object(Bucket=bucket, Key=key)
        logger.debug("Cloud: deleted bucket=%s key=%s", bucket, key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Cloud: delete failed for %s: %s", key, exc)


def _local_delete(path_str: str) -> None:
    try:
        Path(path_str).unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("Local: delete failed for %s: %s", path_str, exc)


# ─── Presigned URL ────────────────────────────────────────────────────────────


def get_presigned_url(
    key_or_path: str,
    expires: int = 3600,
    filename: str | None = None,
) -> str:
    """
    Return a time-limited URL for the object.

    Cloud mode → generates a presigned GET URL.  The optional *filename*
                 argument sets ``Content-Disposition: attachment; filename="…"``
                 so browsers prompt a download with the original filename.
    Local mode → returns a ``file://`` URI (usable in dev only).
    """
    if is_s3_enabled():
        return _cloud_presigned_url(key_or_path, expires, filename)
    return f"file://{key_or_path}"


def _cloud_presigned_url(key: str, expires: int, filename: str | None) -> str:
    client, bucket = _get_cloud_config()
    params: dict = {"Bucket": bucket, "Key": key}
    if filename:
        params["ResponseContentDisposition"] = f'attachment; filename="{filename}"'
    return client.generate_presigned_url(
        "get_object",
        Params=params,
        ExpiresIn=expires,
    )


# ─── Local-path context manager ───────────────────────────────────────────────


@contextlib.contextmanager
def local_path(key_or_path: str, suffix: str = "") -> Generator[str, None, None]:
    """
    Context manager that yields a guaranteed local filesystem path.

    Local mode: yields *key_or_path* directly — no copy, no temp file.
    Cloud mode: downloads the object to a ``NamedTemporaryFile``, yields that
                path, then deletes the temp file on exit.

    Usage::

        with storage_service.local_path(document.file_path, suffix=".pdf") as p:
            text = extract_text(p, document.file_type)
    """
    if not is_s3_enabled():
        yield key_or_path
        return

    # Cloud mode: download to a temp file so local tools (pdfplumber, ffmpeg…)
    # can open it via a regular filesystem path.
    file_bytes = _cloud_download(key_or_path)
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        yield tmp_path
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

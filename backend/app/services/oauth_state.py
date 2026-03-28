"""
Cryptographic OAuth state parameter generation and verification.

Prevents OAuth CSRF attacks by embedding a signed, timestamped nonce in the
state parameter instead of a bare user_id.  The state is self-contained
(no DB table needed) — it's an HMAC-signed JSON payload encoded as
URL-safe base64.

Format: base64url({ "uid": "<user_id>", "nonce": "<random>", "ts": <epoch> }).<hmac_signature>
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import time

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# State tokens expire after 10 minutes (generous for slow OAuth flows)
STATE_TTL_SECONDS = 600


def _get_signing_key() -> bytes:
    """Derive a signing key from the app's ENCRYPTION_KEY."""
    settings = get_settings()
    key = settings.encryption_key
    if not key:
        raise RuntimeError("ENCRYPTION_KEY must be set for OAuth state signing")
    return hashlib.sha256(f"oauth-state:{key}".encode()).digest()


def _sign(payload_b64: bytes) -> str:
    """Compute HMAC-SHA256 of the base64 payload, return hex digest."""
    return hmac.new(_get_signing_key(), payload_b64, hashlib.sha256).hexdigest()


def generate(user_id: str) -> str:
    """
    Generate a signed OAuth state token for the given user.

    Returns a string safe for use as a URL query parameter.
    """
    payload = {
        "uid": user_id,
        "nonce": os.urandom(16).hex(),
        "ts": int(time.time()),
    }
    payload_json = json.dumps(payload, separators=(",", ":"))
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode())
    signature = _sign(payload_b64)
    return f"{payload_b64.decode()}.{signature}"


def verify(state: str) -> str:
    """
    Verify a signed OAuth state token and return the user_id.

    Raises ValueError if the token is invalid, tampered with, or expired.
    """
    if not state or "." not in state:
        raise ValueError("Invalid OAuth state format")

    payload_b64_str, received_sig = state.rsplit(".", 1)
    payload_b64 = payload_b64_str.encode()

    # Verify HMAC signature (constant-time comparison)
    expected_sig = _sign(payload_b64)
    if not hmac.compare_digest(received_sig, expected_sig):
        raise ValueError("Invalid OAuth state signature")

    # Decode and parse payload
    try:
        payload_json = base64.urlsafe_b64decode(payload_b64)
        payload = json.loads(payload_json)
    except Exception:
        raise ValueError("Corrupted OAuth state payload")

    # Check required fields
    uid = payload.get("uid")
    ts = payload.get("ts")
    if not uid or not ts:
        raise ValueError("Incomplete OAuth state payload")

    # Check expiration
    age = int(time.time()) - ts
    if age > STATE_TTL_SECONDS:
        raise ValueError(f"OAuth state expired ({age}s old, max {STATE_TTL_SECONDS}s)")
    if age < -60:
        raise ValueError("OAuth state timestamp is in the future")

    return uid

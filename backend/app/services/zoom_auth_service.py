"""
Zoom OAuth2 service for connecting Zoom accounts.

Handles the full OAuth2 flow: authorization URL generation, token exchange,
token refresh, and connection management.  Tokens are encrypted at rest
using Fernet symmetric encryption (same pattern as google_auth_service).
"""

import base64
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.integration_connection import IntegrationConnection

logger = logging.getLogger(__name__)

# Zoom OAuth2 endpoints
ZOOM_AUTH_URL = "https://zoom.us/oauth/authorize"
ZOOM_TOKEN_URL = "https://zoom.us/oauth/token"
ZOOM_USERINFO_URL = "https://api.zoom.us/v2/users/me"


# ---------------------------------------------------------------------------
# Encryption helpers (same as google_auth_service)
# ---------------------------------------------------------------------------

def _get_fernet() -> Fernet:
    """Return a Fernet instance using the configured ENCRYPTION_KEY."""
    settings = get_settings()
    key = settings.encryption_key
    if not key:
        raise RuntimeError("ENCRYPTION_KEY must be set in environment variables")
    return Fernet(key.encode())


def _encrypt(plaintext: str) -> str:
    """Encrypt a string and return the base64-encoded ciphertext."""
    return _get_fernet().encrypt(plaintext.encode()).decode()


def _decrypt(ciphertext: str) -> str:
    """Decrypt a base64-encoded ciphertext and return the plaintext."""
    return _get_fernet().decrypt(ciphertext.encode()).decode()


# ---------------------------------------------------------------------------
# Zoom Basic Auth helper
# ---------------------------------------------------------------------------

def _basic_auth_header() -> str:
    """Build the Base64-encoded Basic Auth header for Zoom token requests."""
    settings = get_settings()
    credentials = f"{settings.zoom_client_id}:{settings.zoom_client_secret}"
    encoded = base64.b64encode(credentials.encode()).decode()
    return f"Basic {encoded}"


# ---------------------------------------------------------------------------
# 1. Authorization URL
# ---------------------------------------------------------------------------

def get_authorization_url(user_id: str, redirect_uri: Optional[str] = None) -> str:
    """
    Generate the Zoom OAuth2 authorization URL.

    The `state` parameter carries the user_id so the callback can associate
    the granted tokens with the correct user.  Scopes are configured in the
    Zoom Marketplace app settings, not in the URL.
    """
    settings = get_settings()
    redirect = redirect_uri or settings.zoom_redirect_uri

    params = {
        "response_type": "code",
        "client_id": settings.zoom_client_id,
        "redirect_uri": redirect,
        "state": user_id,
    }

    return f"{ZOOM_AUTH_URL}?{urlencode(params)}"


# ---------------------------------------------------------------------------
# 2. Callback — exchange code for tokens
# ---------------------------------------------------------------------------

async def handle_callback(
    code: str,
    state: str,
    db: Session,
    redirect_uri: Optional[str] = None,
) -> IntegrationConnection:
    """
    Exchange the authorisation code for tokens, fetch the user's Zoom
    email, encrypt the tokens, and upsert an IntegrationConnection row.

    Returns the created / updated IntegrationConnection.
    """
    settings = get_settings()
    redirect = redirect_uri or settings.zoom_redirect_uri
    user_id = state  # state carries the Clerk user_id

    # ── Exchange code for tokens ──────────────────────────────────────────
    async with httpx.AsyncClient(timeout=15) as client:
        token_response = await client.post(
            ZOOM_TOKEN_URL,
            headers={
                "Authorization": _basic_auth_header(),
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect,
            },
        )
        token_response.raise_for_status()
        token_data = token_response.json()

    access_token: str = token_data["access_token"]
    refresh_token: Optional[str] = token_data.get("refresh_token")
    expires_in: int = token_data.get("expires_in", 3600)
    token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    scopes_granted = token_data.get("scope", "")

    # ── Fetch user info to get the Zoom email ─────────────────────────────
    async with httpx.AsyncClient(timeout=10) as client:
        userinfo_response = await client.get(
            ZOOM_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        userinfo_response.raise_for_status()
        userinfo = userinfo_response.json()

    zoom_email: str = userinfo.get("email", "")

    # ── Upsert IntegrationConnection ──────────────────────────────────────
    existing = (
        db.query(IntegrationConnection)
        .filter(
            IntegrationConnection.user_id == user_id,
            IntegrationConnection.provider == "zoom",
            IntegrationConnection.provider_email == zoom_email,
        )
        .first()
    )

    encrypted_access = _encrypt(access_token)
    encrypted_refresh = _encrypt(refresh_token) if refresh_token else None

    if existing:
        existing.access_token = encrypted_access
        existing.refresh_token = encrypted_refresh or existing.refresh_token
        existing.token_expires_at = token_expires_at
        existing.scopes = scopes_granted
        existing.is_active = True
        db.commit()
        db.refresh(existing)
        logger.info("Updated Zoom connection for user=%s email=%s", user_id, zoom_email)
        return existing

    connection = IntegrationConnection(
        id=uuid.uuid4(),
        user_id=user_id,
        provider="zoom",
        provider_email=zoom_email,
        access_token=encrypted_access,
        refresh_token=encrypted_refresh,
        token_expires_at=token_expires_at,
        scopes=scopes_granted,
        is_active=True,
    )
    db.add(connection)
    db.commit()
    db.refresh(connection)
    logger.info("Created Zoom connection for user=%s email=%s", user_id, zoom_email)
    return connection


# ---------------------------------------------------------------------------
# 3. Refresh access token
# ---------------------------------------------------------------------------

async def refresh_access_token(
    connection_id: uuid.UUID,
    db: Session,
) -> IntegrationConnection:
    """
    Use the stored refresh_token to obtain a new access_token from Zoom.

    Updates the database record and returns the updated connection.
    """
    connection = (
        db.query(IntegrationConnection)
        .filter(IntegrationConnection.id == connection_id)
        .first()
    )
    if not connection:
        raise ValueError(f"Connection {connection_id} not found")

    if not connection.refresh_token:
        raise ValueError(f"Connection {connection_id} has no refresh token")

    decrypted_refresh = _decrypt(connection.refresh_token)

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            ZOOM_TOKEN_URL,
            headers={
                "Authorization": _basic_auth_header(),
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "refresh_token",
                "refresh_token": decrypted_refresh,
            },
        )
        response.raise_for_status()
        token_data = response.json()

    new_access = token_data["access_token"]
    expires_in = token_data.get("expires_in", 3600)

    connection.access_token = _encrypt(new_access)
    connection.token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

    # Zoom issues a new refresh_token on every refresh
    if "refresh_token" in token_data:
        connection.refresh_token = _encrypt(token_data["refresh_token"])

    db.commit()
    db.refresh(connection)
    logger.info("Refreshed access token for connection=%s", connection_id)
    return connection


# ---------------------------------------------------------------------------
# 4. Get a valid (non-expired) token
# ---------------------------------------------------------------------------

async def get_valid_token(
    connection_id: uuid.UUID,
    db: Session,
) -> str:
    """
    Return a decrypted, valid access token.  Automatically refreshes if
    the current token has expired (or will expire within 5 minutes).
    """
    connection = (
        db.query(IntegrationConnection)
        .filter(IntegrationConnection.id == connection_id)
        .first()
    )
    if not connection:
        raise ValueError(f"Connection {connection_id} not found")
    if not connection.is_active:
        raise ValueError(f"Connection {connection_id} is inactive")

    # Refresh if expired or about to expire (5-minute buffer)
    now = datetime.now(timezone.utc)
    if connection.token_expires_at and connection.token_expires_at < now + timedelta(minutes=5):
        connection = await refresh_access_token(connection_id, db)

    return _decrypt(connection.access_token)


# ---------------------------------------------------------------------------
# 5. Disconnect (soft delete)
# ---------------------------------------------------------------------------

def disconnect(
    connection_id: uuid.UUID,
    user_id: str,
    db: Session,
) -> bool:
    """
    Deactivate a connection (soft delete).

    Returns True if the connection was found and deactivated, False otherwise.
    Only the owning user can disconnect.
    """
    connection = (
        db.query(IntegrationConnection)
        .filter(
            IntegrationConnection.id == connection_id,
            IntegrationConnection.user_id == user_id,
        )
        .first()
    )
    if not connection:
        return False

    connection.is_active = False
    db.commit()
    logger.info("Disconnected connection=%s for user=%s", connection_id, user_id)
    return True

"""
Front (shared inbox) OAuth2 + API token service.

Supports two authentication methods:
  1. OAuth2 — for team accounts (standard authorization code flow)
  2. API token — for personal accounts (user pastes a token from Front settings)

Tokens are encrypted at rest using Fernet symmetric encryption
(same pattern as google_auth_service / zoom_auth_service).
"""

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
from app.services import oauth_state

logger = logging.getLogger(__name__)

# Front API endpoints
FRONT_AUTH_URL = "https://app.frontapp.com/oauth/authorize"
FRONT_TOKEN_URL = "https://app.frontapp.com/oauth/token"
FRONT_USERINFO_URL = "https://api2.frontapp.com/me"


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
# 1. Authorization URL (OAuth2)
# ---------------------------------------------------------------------------

def get_authorization_url(user_id: str, redirect_uri: Optional[str] = None) -> str:
    """
    Generate the Front OAuth2 authorization URL.

    The `state` parameter carries the user_id so the callback can associate
    the granted tokens with the correct user.
    """
    settings = get_settings()
    redirect = redirect_uri or settings.front_redirect_uri

    params = {
        "response_type": "code",
        "client_id": settings.front_client_id,
        "redirect_uri": redirect,
        "state": oauth_state.generate(user_id),
    }

    return f"{FRONT_AUTH_URL}?{urlencode(params)}"


# ---------------------------------------------------------------------------
# 2. Callback — exchange code for tokens (OAuth2)
# ---------------------------------------------------------------------------

async def handle_callback(
    code: str,
    state: str,
    db: Session,
    redirect_uri: Optional[str] = None,
) -> IntegrationConnection:
    """
    Exchange the authorisation code for tokens, fetch the user's Front
    identity, encrypt the tokens, and upsert an IntegrationConnection row.

    Returns the created / updated IntegrationConnection.
    """
    settings = get_settings()
    redirect = redirect_uri or settings.front_redirect_uri
    user_id = oauth_state.verify(state)  # verify signed nonce, extract user_id

    # ── Exchange code for tokens ──────────────────────────────────────────
    async with httpx.AsyncClient(timeout=15) as client:
        token_response = await client.post(
            FRONT_TOKEN_URL,
            json={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect,
                "client_id": settings.front_client_id,
                "client_secret": settings.front_client_secret,
            },
        )
        token_response.raise_for_status()
        token_data = token_response.json()

    access_token: str = token_data["access_token"]
    refresh_token: Optional[str] = token_data.get("refresh_token")
    expires_in: int = token_data.get("expires_in", 3600)
    token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

    # ── Fetch user info to get the Front identity ─────────────────────────
    async with httpx.AsyncClient(timeout=10) as client:
        userinfo_response = await client.get(
            FRONT_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        userinfo_response.raise_for_status()
        userinfo = userinfo_response.json()

    front_email: str = userinfo.get("email", "") or userinfo.get("username", "")

    # ── Upsert IntegrationConnection ──────────────────────────────────────
    existing = (
        db.query(IntegrationConnection)
        .filter(
            IntegrationConnection.user_id == user_id,
            IntegrationConnection.provider == "front",
            IntegrationConnection.provider_email == front_email,
        )
        .first()
    )

    encrypted_access = _encrypt(access_token)
    encrypted_refresh = _encrypt(refresh_token) if refresh_token else None

    if existing:
        existing.access_token = encrypted_access
        existing.refresh_token = encrypted_refresh or existing.refresh_token
        existing.token_expires_at = token_expires_at
        existing.is_active = True
        db.commit()
        db.refresh(existing)
        logger.info("Updated Front connection for user=%s email=%s", user_id, front_email)
        return existing

    connection = IntegrationConnection(
        id=uuid.uuid4(),
        user_id=user_id,
        provider="front",
        provider_email=front_email,
        access_token=encrypted_access,
        refresh_token=encrypted_refresh,
        token_expires_at=token_expires_at,
        is_active=True,
    )
    db.add(connection)
    db.commit()
    db.refresh(connection)
    logger.info("Created Front OAuth connection for user=%s email=%s", user_id, front_email)
    return connection


# ---------------------------------------------------------------------------
# 3. API token connection (non-OAuth)
# ---------------------------------------------------------------------------

async def handle_api_token_connection(
    user_id: str,
    api_token: str,
    db: Session,
) -> IntegrationConnection:
    """
    Validate a Front API token by calling /me, then store the connection.

    API tokens don't expire (unless revoked in Front), so we set
    refresh_token=NULL and token_expires_at=NULL.

    Raises httpx.HTTPStatusError if the token is invalid.
    """
    # ── Validate the token ────────────────────────────────────────────────
    async with httpx.AsyncClient(timeout=10) as client:
        userinfo_response = await client.get(
            FRONT_USERINFO_URL,
            headers={"Authorization": f"Bearer {api_token}"},
        )
        userinfo_response.raise_for_status()
        userinfo = userinfo_response.json()

    front_email: str = userinfo.get("email", "") or userinfo.get("username", "")

    # ── Upsert IntegrationConnection ──────────────────────────────────────
    existing = (
        db.query(IntegrationConnection)
        .filter(
            IntegrationConnection.user_id == user_id,
            IntegrationConnection.provider == "front",
            IntegrationConnection.provider_email == front_email,
        )
        .first()
    )

    encrypted_token = _encrypt(api_token)

    if existing:
        existing.access_token = encrypted_token
        existing.refresh_token = None  # API tokens don't use refresh
        existing.token_expires_at = None  # API tokens don't expire
        existing.is_active = True
        db.commit()
        db.refresh(existing)
        logger.info("Updated Front API-token connection for user=%s email=%s", user_id, front_email)
        return existing

    connection = IntegrationConnection(
        id=uuid.uuid4(),
        user_id=user_id,
        provider="front",
        provider_email=front_email,
        access_token=encrypted_token,
        refresh_token=None,
        token_expires_at=None,
        is_active=True,
    )
    db.add(connection)
    db.commit()
    db.refresh(connection)
    logger.info("Created Front API-token connection for user=%s email=%s", user_id, front_email)
    return connection


# ---------------------------------------------------------------------------
# 4. Get a valid (non-expired) token
# ---------------------------------------------------------------------------

async def get_valid_token(
    connection_id: uuid.UUID,
    db: Session,
) -> str:
    """
    Return a decrypted, valid access token.

    For OAuth connections: automatically refreshes if the current token has
    expired (or will expire within 5 minutes).
    For API token connections (no refresh_token, no token_expires_at):
    returns the token directly — they don't expire unless revoked.
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

    # API token connections: no expiry, return directly
    if not connection.refresh_token and not connection.token_expires_at:
        return _decrypt(connection.access_token)

    # OAuth connections: refresh if expired or about to expire (5-minute buffer)
    now = datetime.now(timezone.utc)
    if connection.token_expires_at and connection.token_expires_at < now + timedelta(minutes=5):
        connection = await refresh_access_token(connection_id, db)

    return _decrypt(connection.access_token)


# ---------------------------------------------------------------------------
# 5. Refresh access token (OAuth only)
# ---------------------------------------------------------------------------

async def refresh_access_token(
    connection_id: uuid.UUID,
    db: Session,
) -> IntegrationConnection:
    """
    Use the stored refresh_token to obtain a new access_token from Front.

    Only applicable for OAuth connections.  API token connections should
    never call this (they have no refresh_token).
    """
    settings = get_settings()

    connection = (
        db.query(IntegrationConnection)
        .filter(IntegrationConnection.id == connection_id)
        .first()
    )
    if not connection:
        raise ValueError(f"Connection {connection_id} not found")

    if not connection.refresh_token:
        raise ValueError(
            f"Connection {connection_id} has no refresh token "
            "(API token connections don't support refresh)"
        )

    decrypted_refresh = _decrypt(connection.refresh_token)

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            FRONT_TOKEN_URL,
            json={
                "grant_type": "refresh_token",
                "refresh_token": decrypted_refresh,
                "client_id": settings.front_client_id,
                "client_secret": settings.front_client_secret,
            },
        )
        response.raise_for_status()
        token_data = response.json()

    new_access = token_data["access_token"]
    expires_in = token_data.get("expires_in", 3600)

    connection.access_token = _encrypt(new_access)
    connection.token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

    if "refresh_token" in token_data:
        connection.refresh_token = _encrypt(token_data["refresh_token"])

    db.commit()
    db.refresh(connection)
    logger.info("Refreshed Front access token for connection=%s", connection_id)
    return connection


# ---------------------------------------------------------------------------
# 6. Disconnect (soft delete)
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
    logger.info("Disconnected Front connection=%s for user=%s", connection_id, user_id)
    return True

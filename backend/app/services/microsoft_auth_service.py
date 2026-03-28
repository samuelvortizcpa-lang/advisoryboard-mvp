"""
Microsoft OAuth2 service for connecting Outlook/Microsoft 365 accounts.

Handles the full OAuth2 flow: authorization URL generation, token exchange,
token refresh, and connection management.  Tokens are encrypted at rest
using Fernet symmetric encryption (same pattern as google_auth_service).
"""

import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
import msal
from cryptography.fernet import Fernet
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.integration_connection import IntegrationConnection
from app.services import oauth_state

logger = logging.getLogger(__name__)

# Microsoft OAuth2 constants
MICROSOFT_AUTHORITY = "https://login.microsoftonline.com/common"
MICROSOFT_SCOPES = ["Mail.Read", "User.Read", "offline_access"]
MICROSOFT_GRAPH_ME_URL = "https://graph.microsoft.com/v1.0/me"


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
# MSAL app helper
# ---------------------------------------------------------------------------

def _get_msal_app() -> msal.ConfidentialClientApplication:
    """Create an MSAL ConfidentialClientApplication."""
    settings = get_settings()
    return msal.ConfidentialClientApplication(
        client_id=settings.microsoft_client_id,
        client_credential=settings.microsoft_client_secret,
        authority=MICROSOFT_AUTHORITY,
    )


# ---------------------------------------------------------------------------
# 1. Authorization URL
# ---------------------------------------------------------------------------

def get_authorization_url(user_id: str, redirect_uri: Optional[str] = None) -> str:
    """
    Generate the Microsoft OAuth2 authorization URL.

    The `state` parameter carries the user_id so the callback can associate
    the granted tokens with the correct user.
    """
    settings = get_settings()
    redirect = redirect_uri or settings.microsoft_redirect_uri
    app = _get_msal_app()

    auth_url = app.get_authorization_request_url(
        scopes=MICROSOFT_SCOPES,
        redirect_uri=redirect,
        state=oauth_state.generate(user_id),
    )

    return auth_url


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
    Exchange the authorisation code for tokens, fetch the user's Microsoft
    email, encrypt the tokens, and upsert an IntegrationConnection row.

    Returns the created / updated IntegrationConnection.
    """
    settings = get_settings()
    redirect = redirect_uri or settings.microsoft_redirect_uri
    user_id = oauth_state.verify(state)  # verify signed nonce, extract user_id

    # ── Exchange code for tokens via MSAL ─────────────────────────────────
    app = _get_msal_app()
    token_data = app.acquire_token_by_authorization_code(
        code=code,
        scopes=MICROSOFT_SCOPES,
        redirect_uri=redirect,
    )

    if "error" in token_data:
        raise ValueError(
            f"Microsoft token exchange failed: {token_data.get('error_description', token_data['error'])}"
        )

    access_token: str = token_data["access_token"]
    refresh_token: Optional[str] = token_data.get("refresh_token")
    expires_in: int = token_data.get("expires_in", 3600)
    token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    scopes_granted = " ".join(token_data.get("scope", MICROSOFT_SCOPES))

    # ── Fetch user info to get the Microsoft email ────────────────────────
    async with httpx.AsyncClient(timeout=10) as client:
        userinfo_response = await client.get(
            MICROSOFT_GRAPH_ME_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        userinfo_response.raise_for_status()
        userinfo = userinfo_response.json()

    microsoft_email: str = userinfo.get("mail") or userinfo.get("userPrincipalName", "")

    # ── Upsert IntegrationConnection ──────────────────────────────────────
    existing = (
        db.query(IntegrationConnection)
        .filter(
            IntegrationConnection.user_id == user_id,
            IntegrationConnection.provider == "microsoft",
            IntegrationConnection.provider_email == microsoft_email,
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
        logger.info("Updated Microsoft connection for user=%s email=%s", user_id, microsoft_email)
        return existing

    connection = IntegrationConnection(
        id=uuid.uuid4(),
        user_id=user_id,
        provider="microsoft",
        provider_email=microsoft_email,
        access_token=encrypted_access,
        refresh_token=encrypted_refresh,
        token_expires_at=token_expires_at,
        scopes=scopes_granted,
        is_active=True,
    )
    db.add(connection)
    db.commit()
    db.refresh(connection)
    logger.info("Created Microsoft connection for user=%s email=%s", user_id, microsoft_email)
    return connection


# ---------------------------------------------------------------------------
# 3. Refresh access token
# ---------------------------------------------------------------------------

async def refresh_access_token(
    connection_id: uuid.UUID,
    db: Session,
) -> IntegrationConnection:
    """
    Use the stored refresh_token to obtain a new access_token from Microsoft.

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
    app = _get_msal_app()

    token_data = app.acquire_token_by_refresh_token(
        refresh_token=decrypted_refresh,
        scopes=MICROSOFT_SCOPES,
    )

    if "error" in token_data:
        raise ValueError(
            f"Microsoft token refresh failed: {token_data.get('error_description', token_data['error'])}"
        )

    new_access = token_data["access_token"]
    expires_in = token_data.get("expires_in", 3600)

    connection.access_token = _encrypt(new_access)
    connection.token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

    # Microsoft may issue a new refresh_token during refresh
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

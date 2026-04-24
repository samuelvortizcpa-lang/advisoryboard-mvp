"""
Clerk JWT authentication middleware for FastAPI.

Clerk signs tokens with RS256 using keys published at:
  <CLERK_FRONTEND_API_URL>/.well-known/jwks.json

Two usage patterns are supported:

  1. FastAPI dependency (recommended):
       @router.get("/me")
       async def get_me(current_user: dict = Depends(get_current_user)):
           ...

  2. Decorator (convenience wrapper around the same dependency):
       @router.get("/me")
       @require_auth
       async def get_me(current_user: dict):
           ...
"""

import hmac
import inspect
import json
import logging
import functools
from typing import Any, Dict, Optional

import httpx
from jwt import PyJWT, ExpiredSignatureError, InvalidTokenError, get_unverified_header
from jwt.algorithms import RSAAlgorithm
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# JWKS cache (process-level; refreshed if an unknown key id appears)
# ---------------------------------------------------------------------------

_jwks_cache: Optional[Dict[str, Any]] = None   # raw JWKS document
_key_cache: Dict[str, Any] = {}                 # kid -> RSA public key object


async def _fetch_jwks() -> Dict[str, Any]:
    """Download Clerk's JWKS document and return it."""
    settings = get_settings()
    url = f"{settings.clerk_frontend_api_url.rstrip('/')}/.well-known/jwks.json"
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.json()


async def _get_public_key(kid: str) -> Any:
    """
    Return the RSA public key for a given key id.
    Fetches/refreshes the JWKS document when the key is not cached.
    """
    global _jwks_cache, _key_cache

    if kid not in _key_cache:
        _jwks_cache = await _fetch_jwks()
        for jwk in _jwks_cache.get("keys", []):
            jwk_kid = jwk.get("kid")
            if jwk_kid:
                _key_cache[jwk_kid] = RSAAlgorithm.from_jwk(json.dumps(jwk))

    if kid not in _key_cache:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token signing key not recognised",
        )

    return _key_cache[kid]


# ---------------------------------------------------------------------------
# Token verification
# ---------------------------------------------------------------------------

_jwt = PyJWT()


async def verify_clerk_token(token: str) -> Dict[str, Any]:
    """
    Verify a Clerk JWT and return its decoded payload.

    Raises HTTPException 401 on any failure.

    TEST_MODE bypass: when TEST_MODE=true in .env.local, sending the CLERK_SECRET_KEY
    value as the Bearer token skips Clerk verification and returns a fixed test user.
    This makes automated tests runnable without short-lived JWTs.

    NOTE: get_settings() is @lru_cache'd.  If you add/change TEST_MODE or
    CLERK_SECRET_KEY in .env.local while the server is running, you must restart
    the server for the new values to take effect.
    """
    settings = get_settings()

    # ── TEST_MODE bypass ────────────────────────────────────────────────────
    # This block must stay ABOVE all JWT parsing so that the Clerk-secret-key
    # bearer token never reaches get_unverified_header().
    if settings.test_mode:
        if settings.clerk_secret_key and hmac.compare_digest(
            token.strip().encode("utf-8"),
            settings.clerk_secret_key.strip().encode("utf-8"),
        ):
            logger.warning(
                "TEST_MODE: secret-key bearer accepted — returning fixed test user "
                "(user_test_isolation).  This bypass must never reach production."
            )
            return {
                "sub": "user_test_isolation",
                "email": "test-isolation@callwen.test",
                "email_verified": True,
                "first_name": "Test",
                "last_name": "Isolation",
                "sid": "sess_test_isolation",
            }
        # test_mode is ON but the token didn't match — log details to help diagnose
        logger.warning(
            "TEST_MODE is enabled but the bearer token did NOT match CLERK_SECRET_KEY. "
            "token_len=%d  key_len=%d  key_set=%s",
            len(token.strip()),
            len(settings.clerk_secret_key.strip()),
            bool(settings.clerk_secret_key),
        )
    # ── End TEST_MODE bypass ────────────────────────────────────────────────

    try:
        header = get_unverified_header(token)
    except InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed authorization token",
        )

    kid = header.get("kid")
    if not kid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token header missing key id (kid)",
        )

    public_key = await _get_public_key(kid)

    try:
        payload = _jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            # Clerk populates 'azp' (authorized party) instead of 'aud'.
            # We verify azp below after decoding.
            options={"verify_aud": False},
        )
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        )
    except InvalidTokenError as exc:
        logger.debug("JWT validation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    # ── Verify azp (authorized party) ────────────────────────────────────
    # Clerk JWTs include 'azp' with the requesting origin.  Validate it
    # against the frontend URL to prevent token confusion attacks (a JWT
    # issued for a different Clerk app being accepted here).
    azp = payload.get("azp")
    if azp:
        allowed_origins = set(settings.cors_origins)
        if settings.clerk_frontend_api_url:
            allowed_origins.add(settings.clerk_frontend_api_url.rstrip("/"))
        if azp not in allowed_origins:
            logger.warning("JWT azp claim '%s' not in allowed origins", azp)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token issued for unauthorized origin",
            )

    return payload


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------

_bearer = HTTPBearer(auto_error=True)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
) -> Dict[str, Any]:
    """
    FastAPI dependency.  Resolves to a dict with normalized user fields.

    Usage:
        @router.get("/protected")
        async def route(current_user: dict = Depends(get_current_user)):
            return {"user_id": current_user["user_id"]}
    """
    payload = await verify_clerk_token(credentials.credentials)

    return {
        "user_id": payload.get("sub"),                  # Clerk user ID (user_xxx)
        "email": payload.get("email"),
        "email_verified": payload.get("email_verified", False),
        "first_name": payload.get("first_name"),
        "last_name": payload.get("last_name"),
        "image_url": payload.get("image_url"),
        "session_id": payload.get("sid"),
        "raw": payload,                                  # full payload if needed
    }


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(
        HTTPBearer(auto_error=False)
    ),
) -> Optional[Dict[str, Any]]:
    """
    Like get_current_user, but returns None instead of 401 when no token
    is present.  Useful for routes that behave differently when logged in.
    """
    if credentials is None:
        return None
    payload = await verify_clerk_token(credentials.credentials)
    return {
        "user_id": payload.get("sub"),
        "email": payload.get("email"),
        "email_verified": payload.get("email_verified", False),
        "first_name": payload.get("first_name"),
        "last_name": payload.get("last_name"),
        "image_url": payload.get("image_url"),
        "session_id": payload.get("sid"),
        "raw": payload,
    }


# ---------------------------------------------------------------------------
# @require_auth decorator
# ---------------------------------------------------------------------------

def require_auth(func):
    """
    Decorator that protects a FastAPI route handler with Clerk authentication.

    The wrapped function must accept a `current_user` keyword argument; the
    decorator injects it automatically via FastAPI's dependency system.

    Usage:
        @router.get("/protected")
        @require_auth
        async def protected_route(current_user: dict):
            return {"user_id": current_user["user_id"]}

    The decorator works by appending a `current_user` parameter (with a
    Depends default) to the function's __signature__ so FastAPI's
    introspection picks it up correctly.
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        return await func(*args, **kwargs)

    # Build the new parameter list from the original signature, then append
    # `current_user` with Depends(get_current_user) as its default.
    original_params = list(inspect.signature(func).parameters.values())

    if any(p.name == "current_user" for p in original_params):
        # Already has the param; nothing to inject.
        return wrapper

    injected_param = inspect.Parameter(
        "current_user",
        kind=inspect.Parameter.KEYWORD_ONLY,
        default=Depends(get_current_user),
        annotation=Dict[str, Any],
    )

    wrapper.__signature__ = inspect.signature(func).replace(
        parameters=original_params + [injected_param]
    )

    return wrapper

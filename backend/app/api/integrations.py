"""
API endpoints for third-party integrations (Google OAuth, etc.).
"""

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.config import get_settings
from app.core.database import get_db
from app.models.integration_connection import IntegrationConnection
from app.services import email_router, gmail_sync_service, google_auth_service, microsoft_auth_service, outlook_sync_service

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class ConnectionResponse(BaseModel):
    id: UUID
    provider: str
    provider_email: Optional[str]
    is_active: bool
    scopes: Optional[str]
    last_sync_at: Optional[str]
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class AuthorizeResponse(BaseModel):
    authorization_url: str


class RoutingRuleResponse(BaseModel):
    id: UUID
    user_id: str
    email_address: str
    client_id: UUID
    client_name: str
    match_type: str
    is_active: bool
    created_at: str


class RoutingRuleCreateRequest(BaseModel):
    email_address: str
    client_id: UUID
    match_type: str = "from"


class SyncLogResponse(BaseModel):
    id: UUID
    connection_id: UUID
    sync_type: Optional[str]
    status: Optional[str]
    emails_found: int
    emails_ingested: int
    emails_skipped: int
    error_message: Optional[str]
    started_at: str
    completed_at: Optional[str]

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Google OAuth endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/integrations/google/authorize",
    response_model=AuthorizeResponse,
    summary="Get Google OAuth authorization URL",
)
async def google_authorize(
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> AuthorizeResponse:
    """
    Return the Google OAuth2 authorization URL.  The frontend should
    redirect the user to this URL to begin the consent flow.
    """
    user_id = current_user["user_id"]
    url = google_auth_service.get_authorization_url(user_id)
    return AuthorizeResponse(authorization_url=url)


@router.get(
    "/integrations/google/callback",
    summary="Handle Google OAuth callback",
)
async def google_callback(
    code: str = Query(..., description="Authorization code from Google"),
    state: str = Query(..., description="State parameter (user_id)"),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """
    Google redirects here after the user grants consent.  We exchange the
    authorization code for tokens, store them, and redirect to the
    frontend settings page.
    """
    settings = get_settings()

    try:
        connection = await google_auth_service.handle_callback(
            code=code,
            state=state,
            db=db,
        )
    except Exception as exc:
        logger.exception("Google OAuth callback failed: %s", exc)
        # Redirect to frontend with error parameter
        return RedirectResponse(
            url=f"{settings.frontend_url}/dashboard/settings/integrations?integration_error=google_auth_failed",
            status_code=status.HTTP_302_FOUND,
        )

    # Redirect to frontend integrations page with success indicator
    return RedirectResponse(
        url=f"{settings.frontend_url}/dashboard/settings/integrations?integration_connected=google",
        status_code=status.HTTP_302_FOUND,
    )


# ---------------------------------------------------------------------------
# Microsoft OAuth endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/integrations/microsoft/authorize",
    response_model=AuthorizeResponse,
    summary="Get Microsoft OAuth authorization URL",
)
async def microsoft_authorize(
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> AuthorizeResponse:
    """
    Return the Microsoft OAuth2 authorization URL.  The frontend should
    redirect the user to this URL to begin the consent flow.
    """
    user_id = current_user["user_id"]
    url = microsoft_auth_service.get_authorization_url(user_id)
    return AuthorizeResponse(authorization_url=url)


@router.get(
    "/integrations/microsoft/callback",
    summary="Handle Microsoft OAuth callback",
)
async def microsoft_callback(
    code: str = Query(..., description="Authorization code from Microsoft"),
    state: str = Query(..., description="State parameter (user_id)"),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """
    Microsoft redirects here after the user grants consent.  We exchange the
    authorization code for tokens, store them, and redirect to the
    frontend settings page.
    """
    settings = get_settings()

    try:
        connection = await microsoft_auth_service.handle_callback(
            code=code,
            state=state,
            db=db,
        )
    except Exception as exc:
        logger.exception("Microsoft OAuth callback failed: %s", exc)
        return RedirectResponse(
            url=f"{settings.frontend_url}/dashboard/settings/integrations?integration_error=microsoft_auth_failed",
            status_code=status.HTTP_302_FOUND,
        )

    return RedirectResponse(
        url=f"{settings.frontend_url}/dashboard/settings/integrations?connected=microsoft",
        status_code=status.HTTP_302_FOUND,
    )


# ---------------------------------------------------------------------------
# Connection management endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/integrations/connections",
    response_model=List[ConnectionResponse],
    summary="List active integration connections",
)
async def list_connections(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> List[ConnectionResponse]:
    """
    Return all active integration connections for the current user.
    """
    user_id = current_user["user_id"]
    connections = (
        db.query(IntegrationConnection)
        .filter(
            IntegrationConnection.user_id == user_id,
            IntegrationConnection.is_active == True,
        )
        .order_by(IntegrationConnection.created_at.desc())
        .all()
    )

    return [
        ConnectionResponse(
            id=c.id,
            provider=c.provider,
            provider_email=c.provider_email,
            is_active=c.is_active,
            scopes=c.scopes,
            last_sync_at=c.last_sync_at.isoformat() if c.last_sync_at else None,
            created_at=c.created_at.isoformat(),
            updated_at=c.updated_at.isoformat(),
        )
        for c in connections
    ]


@router.delete(
    "/integrations/connections/{connection_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Disconnect an integration",
)
async def disconnect_integration(
    connection_id: UUID,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> None:
    """
    Soft-delete an integration connection (sets is_active=False).
    """
    user_id = current_user["user_id"]
    deleted = google_auth_service.disconnect(connection_id, user_id, db)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection not found",
        )


# ---------------------------------------------------------------------------
# Sync endpoints
# ---------------------------------------------------------------------------

def _sync_log_response(sync_log: Any) -> SyncLogResponse:
    """Convert a SyncLog to a SyncLogResponse."""
    return SyncLogResponse(
        id=sync_log.id,
        connection_id=sync_log.connection_id,
        sync_type=sync_log.sync_type,
        status=sync_log.status,
        emails_found=sync_log.emails_found,
        emails_ingested=sync_log.emails_ingested,
        emails_skipped=sync_log.emails_skipped,
        error_message=sync_log.error_message,
        started_at=sync_log.started_at.isoformat(),
        completed_at=sync_log.completed_at.isoformat() if sync_log.completed_at else None,
    )


def _get_connection_provider(connection_id: UUID, user_id: str, db: Session) -> str:
    """Look up the provider for a connection, raising 404 if not found."""
    connection = (
        db.query(IntegrationConnection)
        .filter(
            IntegrationConnection.id == connection_id,
            IntegrationConnection.user_id == user_id,
            IntegrationConnection.is_active == True,
        )
        .first()
    )
    if not connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection not found",
        )
    return connection.provider


@router.post(
    "/integrations/connections/{connection_id}/sync",
    response_model=SyncLogResponse,
    summary="Trigger a manual email sync",
)
async def trigger_sync(
    connection_id: UUID,
    max_results: int = Query(50, ge=1, le=500, description="Max emails to fetch"),
    since_hours: int = Query(24, ge=1, le=720, description="Fetch emails from last N hours"),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> SyncLogResponse:
    """
    Trigger a manual sync for a connected email account.  Automatically
    detects the provider (Google or Microsoft) and calls the right service.
    """
    user_id = current_user["user_id"]
    provider = _get_connection_provider(connection_id, user_id, db)

    if provider == "microsoft":
        sync_log = await outlook_sync_service.sync_emails(
            connection_id=connection_id,
            user_id=user_id,
            db=db,
            sync_type="manual",
            max_results=max_results,
            since_hours=since_hours,
        )
    else:
        sync_log = await gmail_sync_service.sync_emails(
            connection_id=connection_id,
            user_id=user_id,
            db=db,
            sync_type="manual",
            max_results=max_results,
            since_hours=since_hours,
        )

    return _sync_log_response(sync_log)


@router.get(
    "/integrations/connections/{connection_id}/sync-history",
    response_model=List[SyncLogResponse],
    summary="Get sync history for a connection",
)
async def get_sync_history(
    connection_id: UUID,
    limit: int = Query(20, ge=1, le=100, description="Max logs to return"),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> List[SyncLogResponse]:
    """
    Return recent sync logs for a connection, most recent first.
    Works for both Google and Microsoft connections.
    """
    user_id = current_user["user_id"]
    provider = _get_connection_provider(connection_id, user_id, db)

    if provider == "microsoft":
        logs = outlook_sync_service.get_sync_history(
            user_id=user_id, connection_id=connection_id, db=db, limit=limit,
        )
    else:
        logs = gmail_sync_service.get_sync_history(
            user_id=user_id, connection_id=connection_id, db=db, limit=limit,
        )

    return [_sync_log_response(log) for log in logs]


@router.post(
    "/integrations/connections/{connection_id}/sync-all",
    response_model=SyncLogResponse,
    summary="Deep sync — last 7 days, up to 200 emails",
)
async def trigger_deep_sync(
    connection_id: UUID,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> SyncLogResponse:
    """
    Perform a deep sync: fetches up to 200 emails from the last 7 days.
    Automatically detects the provider and calls the right service.
    """
    user_id = current_user["user_id"]
    provider = _get_connection_provider(connection_id, user_id, db)

    if provider == "microsoft":
        sync_log = await outlook_sync_service.sync_emails(
            connection_id=connection_id,
            user_id=user_id,
            db=db,
            sync_type="manual",
            max_results=200,
            since_hours=168,  # 7 days
        )
    else:
        sync_log = await gmail_sync_service.sync_emails(
            connection_id=connection_id,
            user_id=user_id,
            db=db,
            sync_type="manual",
            max_results=200,
            since_hours=168,  # 7 days
        )

    return _sync_log_response(sync_log)


# ---------------------------------------------------------------------------
# Email routing rules endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/integrations/routing-rules",
    response_model=List[RoutingRuleResponse],
    summary="List all email routing rules",
)
async def list_routing_rules(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> List[RoutingRuleResponse]:
    """
    Return all email routing rules for the current user, with client names.
    """
    user_id = current_user["user_id"]
    rules = email_router.get_routing_rules(user_id, db)
    return [RoutingRuleResponse(**r) for r in rules]


@router.post(
    "/integrations/routing-rules",
    response_model=RoutingRuleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an email routing rule",
)
async def create_routing_rule(
    body: RoutingRuleCreateRequest,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> RoutingRuleResponse:
    """
    Create a new email routing rule that maps an email address to a client.
    """
    user_id = current_user["user_id"]
    try:
        rule = email_router.create_routing_rule(
            user_id=user_id,
            email_address=body.email_address,
            client_id=body.client_id,
            match_type=body.match_type,
            db=db,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    # Re-query to get client name
    from app.models.client import Client
    client = db.query(Client).filter(Client.id == rule.client_id).first()
    client_name = client.name if client else "Unknown"

    return RoutingRuleResponse(
        id=rule.id,
        user_id=rule.user_id,
        email_address=rule.email_address,
        client_id=rule.client_id,
        client_name=client_name,
        match_type=rule.match_type,
        is_active=rule.is_active,
        created_at=rule.created_at.isoformat(),
    )


@router.delete(
    "/integrations/routing-rules/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an email routing rule",
)
async def delete_routing_rule(
    rule_id: UUID,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> None:
    """
    Delete an email routing rule (ownership-scoped).
    """
    user_id = current_user["user_id"]
    deleted = email_router.delete_routing_rule(rule_id, user_id, db)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Routing rule not found",
        )


@router.post(
    "/integrations/routing-rules/auto-generate",
    response_model=List[RoutingRuleResponse],
    summary="Auto-generate routing rules from client emails",
)
async def auto_generate_routing_rules(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> List[RoutingRuleResponse]:
    """
    Scan all clients that have an email address and create 'from' routing
    rules for any that don't already have one.  Returns the newly created
    rules.
    """
    user_id = current_user["user_id"]
    created_rules = email_router.auto_create_routing_rules(user_id, db)

    # Re-query with client names for the response
    from app.models.client import Client
    results: list[RoutingRuleResponse] = []
    for rule in created_rules:
        client = db.query(Client).filter(Client.id == rule.client_id).first()
        client_name = client.name if client else "Unknown"
        results.append(
            RoutingRuleResponse(
                id=rule.id,
                user_id=rule.user_id,
                email_address=rule.email_address,
                client_id=rule.client_id,
                client_name=client_name,
                match_type=rule.match_type,
                is_active=rule.is_active,
                created_at=rule.created_at.isoformat(),
            )
        )
    return results

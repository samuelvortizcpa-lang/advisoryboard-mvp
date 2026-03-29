"""
API endpoints for third-party integrations (Google OAuth, etc.).
"""

import hmac
import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.models.integration_connection import IntegrationConnection
from app.services import email_router, fathom_sync_service, front_auth_service, front_sync_service, gmail_sync_service, google_auth_service, microsoft_auth_service, outlook_sync_service, zoom_auth_service, zoom_sync_service
from app.services.auth_context import AuthContext, check_client_access, get_auth

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


class ZoomRuleResponse(BaseModel):
    id: UUID
    user_id: str
    match_field: str
    match_value: str
    client_id: UUID
    client_name: str
    is_active: bool
    created_at: str


class ZoomRuleCreateRequest(BaseModel):
    match_field: str   # 'topic_contains', 'participant_email', 'meeting_id_prefix'
    match_value: str
    client_id: UUID


class UnmatchedRecordingResponse(BaseModel):
    document_id: UUID
    filename: str
    file_size: int
    source: str
    external_id: Optional[str]
    upload_date: str


class AssignRecordingRequest(BaseModel):
    document_id: UUID
    client_id: UUID
    create_rule: bool = True
    rule_match_field: str = "topic_contains"


class FrontTokenRequest(BaseModel):
    api_token: str


class FathomConnectRequest(BaseModel):
    api_key: str


class FathomConnectResponse(BaseModel):
    connected: bool
    api_available: bool
    message: str
    connection: Optional[ConnectionResponse] = None


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
# Helpers
# ---------------------------------------------------------------------------

def _connection_filter(query, auth: AuthContext):
    """
    Scope integration connections to the org.  Includes backward-compat
    fallback for records where org_id is NULL (pre-migration data).
    """
    return query.filter(
        or_(
            IntegrationConnection.org_id == auth.org_id,
            IntegrationConnection.user_id == auth.user_id,
        )
    )


# ---------------------------------------------------------------------------
# Google OAuth endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/integrations/google/authorize",
    response_model=AuthorizeResponse,
    summary="Get Google OAuth authorization URL",
)
async def google_authorize(
    auth: AuthContext = Depends(get_auth),
) -> AuthorizeResponse:
    """
    Return the Google OAuth2 authorization URL.  The frontend should
    redirect the user to this URL to begin the consent flow.
    """
    url = google_auth_service.get_authorization_url(auth.user_id)
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
    auth: AuthContext = Depends(get_auth),
) -> AuthorizeResponse:
    """
    Return the Microsoft OAuth2 authorization URL.  The frontend should
    redirect the user to this URL to begin the consent flow.
    """
    url = microsoft_auth_service.get_authorization_url(auth.user_id)
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
# Zoom OAuth endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/integrations/zoom/authorize",
    response_model=AuthorizeResponse,
    summary="Get Zoom OAuth authorization URL",
)
async def zoom_authorize(
    auth: AuthContext = Depends(get_auth),
) -> AuthorizeResponse:
    """
    Return the Zoom OAuth2 authorization URL.  The frontend should
    redirect the user to this URL to begin the consent flow.
    """
    url = zoom_auth_service.get_authorization_url(auth.user_id)
    return AuthorizeResponse(authorization_url=url)


@router.get(
    "/integrations/zoom/callback",
    summary="Handle Zoom OAuth callback",
)
async def zoom_callback(
    code: str = Query(..., description="Authorization code from Zoom"),
    state: str = Query(..., description="State parameter (user_id)"),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """
    Zoom redirects here after the user grants consent.  We exchange the
    authorization code for tokens, store them, and redirect to the
    frontend settings page.
    """
    settings = get_settings()

    try:
        connection = await zoom_auth_service.handle_callback(
            code=code,
            state=state,
            db=db,
        )
    except Exception as exc:
        logger.exception("Zoom OAuth callback failed: %s", exc)
        return RedirectResponse(
            url=f"{settings.frontend_url}/dashboard/settings/integrations?integration_error=zoom_auth_failed",
            status_code=status.HTTP_302_FOUND,
        )

    return RedirectResponse(
        url=f"{settings.frontend_url}/dashboard/settings/integrations?connected=zoom",
        status_code=status.HTTP_302_FOUND,
    )


# ---------------------------------------------------------------------------
# Front OAuth + API token endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/integrations/front/authorize",
    response_model=AuthorizeResponse,
    summary="Get Front OAuth authorization URL",
)
async def front_authorize(
    auth: AuthContext = Depends(get_auth),
) -> AuthorizeResponse:
    """
    Return the Front OAuth2 authorization URL.  The frontend should
    redirect the user to this URL to begin the consent flow.
    """
    url = front_auth_service.get_authorization_url(auth.user_id)
    return AuthorizeResponse(authorization_url=url)


@router.get(
    "/integrations/front/callback",
    summary="Handle Front OAuth callback",
)
async def front_callback(
    code: str = Query(..., description="Authorization code from Front"),
    state: str = Query(..., description="State parameter (user_id)"),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """
    Front redirects here after the user grants consent.  We exchange the
    authorization code for tokens, store them, and redirect to the
    frontend settings page.
    """
    settings = get_settings()

    try:
        connection = await front_auth_service.handle_callback(
            code=code,
            state=state,
            db=db,
        )
    except Exception as exc:
        logger.exception("Front OAuth callback failed: %s", exc)
        return RedirectResponse(
            url=f"{settings.frontend_url}/dashboard/settings/integrations?integration_error=front_auth_failed",
            status_code=status.HTTP_302_FOUND,
        )

    return RedirectResponse(
        url=f"{settings.frontend_url}/dashboard/settings/integrations?connected=front",
        status_code=status.HTTP_302_FOUND,
    )


@router.post(
    "/integrations/front/connect-token",
    response_model=ConnectionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Connect Front via API token",
)
async def front_connect_token(
    body: FrontTokenRequest,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> ConnectionResponse:
    """
    Validate a Front API token and store the connection.  This lets users
    paste their Front API token instead of going through OAuth.
    """
    if not body.api_token.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="api_token must not be empty",
        )

    try:
        connection = await front_auth_service.handle_api_token_connection(
            user_id=auth.user_id,
            api_token=body.api_token.strip(),
            db=db,
        )
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 401:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Front API token",
            )
        logger.error("Front API error: %s", exc.response.status_code)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Front API returned an error",
        )
    except httpx.RequestError as exc:
        logger.error("Could not reach Front API: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not reach Front API",
        )

    # Store org_id on the connection
    if connection.org_id is None:
        connection.org_id = auth.org_id
        db.commit()

    return ConnectionResponse(
        id=connection.id,
        provider=connection.provider,
        provider_email=connection.provider_email,
        is_active=connection.is_active,
        scopes=connection.scopes,
        last_sync_at=connection.last_sync_at.isoformat() if connection.last_sync_at else None,
        created_at=connection.created_at.isoformat(),
        updated_at=connection.updated_at.isoformat(),
    )


# ---------------------------------------------------------------------------
# Fathom endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/integrations/fathom/connect",
    response_model=FathomConnectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Connect Fathom via API key",
)
async def fathom_connect(
    body: FathomConnectRequest,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> FathomConnectResponse:
    """
    Validate a Fathom API key and store the connection.

    If the Fathom API is reachable, auto-sync will be available.
    If not, the connection is still stored for manual import tracking.
    """
    if not body.api_key.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="api_key must not be empty",
        )

    try:
        connection, api_available = await fathom_sync_service.handle_api_key_connection(
            user_id=auth.user_id,
            api_key=body.api_key.strip(),
            db=db,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    # Store org_id on the connection
    if connection.org_id is None:
        connection.org_id = auth.org_id
        db.commit()

    message = (
        "Fathom connected — auto-sync is available."
        if api_available
        else "Fathom connected — API not reachable, but you can import transcripts manually."
    )

    return FathomConnectResponse(
        connected=True,
        api_available=api_available,
        message=message,
        connection=ConnectionResponse(
            id=connection.id,
            provider=connection.provider,
            provider_email=connection.provider_email,
            is_active=connection.is_active,
            scopes=connection.scopes,
            last_sync_at=connection.last_sync_at.isoformat() if connection.last_sync_at else None,
            created_at=connection.created_at.isoformat(),
            updated_at=connection.updated_at.isoformat(),
        ),
    )


@router.post(
    "/integrations/fathom/import",
    summary="Import a Fathom JSON transcript",
)
async def fathom_import(
    file: UploadFile = File(...),
    client_id: UUID = Query(..., description="Client to assign this transcript to"),
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> Dict[str, Any]:
    """
    Import a manually uploaded Fathom JSON transcript file.

    Parses the JSON, builds a document, and ingests it through the RAG pipeline.
    This is a streamlined version of regular document upload, specifically for
    Fathom transcript files.
    """
    import uuid as _uuid

    from app.models.client import Client
    from app.models.document import Document
    from app.models.user import User

    check_client_access(auth, client_id, db)

    # Resolve user for uploaded_by FK
    owner = db.query(User).filter(User.clerk_id == auth.user_id).first()
    if not owner:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Read the uploaded file
    file_content = await file.read()
    if not file_content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty",
        )

    # Parse the Fathom JSON
    try:
        parsed = fathom_sync_service.parse_fathom_json_upload(file_content)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    # Build document content using the sync service's formatter
    call_data = parsed["raw_data"]
    call_data["title"] = parsed["title"]  # ensure title is set
    transcript_text = parsed["transcript_text"]

    if not transcript_text and not parsed["summary"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No transcript or summary found in the Fathom JSON file",
        )

    content_text = fathom_sync_service.build_fathom_document_content(
        call_data, transcript_text,
    )
    # Replace auto-synced label with manual import
    content_text = content_text.replace(
        "Source: Fathom (auto-synced)",
        "Source: Fathom (manual import)",
    )
    content_bytes = content_text.encode("utf-8")

    # Build filename
    import re
    clean_title = re.sub(r"[^\w\s-]", "", parsed["title"] or "meeting")
    clean_title = re.sub(r"\s+", "_", clean_title.strip())[:80]
    date_part = re.sub(r"[^\w-]", "", str(parsed["date"])[:10]) if parsed["date"] else "unknown"
    filename = f"fathom_meeting_{clean_title}_{date_part}.txt"

    # Upload to storage
    file_id = str(_uuid.uuid4())
    from app.services import storage_service

    storage_path = storage_service.upload_file(
        user_id=str(owner.id),
        client_id=str(client_id),
        file_id=file_id,
        filename=filename,
        file_bytes=content_bytes,
        content_type="text/plain",
    )

    # Create document
    try:
        document = Document(
            client_id=client_id,
            uploaded_by=owner.id,
            filename=filename,
            file_path=storage_path,
            file_type="txt",
            file_size=len(content_bytes),
            source="fathom",
            external_id=None,  # manual imports don't have an external ID
        )
        db.add(document)
        db.commit()
        db.refresh(document)
    except Exception:
        storage_service.delete_file(storage_path)
        db.rollback()
        raise

    # Run RAG pipeline
    try:
        from app.services.rag_service import process_document
        await process_document(db, document)
    except Exception as rag_exc:
        logger.warning(
            "Fathom import: RAG processing failed for document %s: %s",
            document.id, rag_exc,
        )

    return {
        "status": "imported",
        "document_id": str(document.id),
        "filename": filename,
        "title": parsed["title"],
        "client_id": str(client_id),
    }


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
    auth: AuthContext = Depends(get_auth),
) -> List[ConnectionResponse]:
    """
    Return all active integration connections for the current user's org.
    """
    query = (
        db.query(IntegrationConnection)
        .filter(IntegrationConnection.is_active == True)
    )
    connections = (
        _connection_filter(query, auth)
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
    auth: AuthContext = Depends(get_auth),
) -> None:
    """
    Soft-delete an integration connection (sets is_active=False).
    """
    deleted = google_auth_service.disconnect(connection_id, auth.user_id, db)
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
    summary="Trigger a manual sync",
)
async def trigger_sync(
    connection_id: UUID,
    max_results: int = Query(50, ge=1, le=500, description="Max items to fetch"),
    since_hours: int = Query(24, ge=1, le=720, description="Fetch items from last N hours"),
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> SyncLogResponse:
    """
    Trigger a manual sync for a connected account.  Automatically detects
    the provider (Google, Microsoft, Zoom, Front, or Fathom) and calls the right service.
    """
    provider = _get_connection_provider(connection_id, auth.user_id, db)

    if provider == "fathom":
        sync_log = await fathom_sync_service.sync_calls(
            connection_id=connection_id,
            user_id=auth.user_id,
            db=db,
            sync_type="manual",
            max_results=max_results,
            since_hours=since_hours,
        )
    elif provider == "front":
        sync_log = await front_sync_service.sync_conversations(
            connection_id=connection_id,
            user_id=auth.user_id,
            db=db,
            sync_type="manual",
            max_results=max_results,
            since_hours=since_hours,
        )
    elif provider == "zoom":
        days_back = max(since_hours // 24, 1)
        sync_log = await zoom_sync_service.sync_recordings(
            connection_id=connection_id,
            user_id=auth.user_id,
            db=db,
            sync_type="manual",
            days_back=days_back,
            max_results=max_results,
        )
    elif provider == "microsoft":
        sync_log = await outlook_sync_service.sync_emails(
            connection_id=connection_id,
            user_id=auth.user_id,
            db=db,
            sync_type="manual",
            max_results=max_results,
            since_hours=since_hours,
        )
    else:
        sync_log = await gmail_sync_service.sync_emails(
            connection_id=connection_id,
            user_id=auth.user_id,
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
    auth: AuthContext = Depends(get_auth),
) -> List[SyncLogResponse]:
    """
    Return recent sync logs for a connection, most recent first.
    Works for all providers (Google, Microsoft, Zoom, Front, Fathom).
    """
    provider = _get_connection_provider(connection_id, auth.user_id, db)

    if provider == "fathom":
        logs = fathom_sync_service.get_sync_history(
            user_id=auth.user_id, connection_id=connection_id, db=db, limit=limit,
        )
    elif provider == "front":
        logs = front_sync_service.get_sync_history(
            user_id=auth.user_id, connection_id=connection_id, db=db, limit=limit,
        )
    elif provider == "zoom":
        logs = zoom_sync_service.get_sync_history(
            user_id=auth.user_id, connection_id=connection_id, db=db, limit=limit,
        )
    elif provider == "microsoft":
        logs = outlook_sync_service.get_sync_history(
            user_id=auth.user_id, connection_id=connection_id, db=db, limit=limit,
        )
    else:
        logs = gmail_sync_service.get_sync_history(
            user_id=auth.user_id, connection_id=connection_id, db=db, limit=limit,
        )

    return [_sync_log_response(log) for log in logs]


@router.post(
    "/integrations/connections/{connection_id}/sync-all",
    response_model=SyncLogResponse,
    summary="Deep sync — last 7 days, up to 200 items",
)
async def trigger_deep_sync(
    connection_id: UUID,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> SyncLogResponse:
    """
    Perform a deep sync: fetches up to 200 items from the last 7 days.
    Automatically detects the provider and calls the right service.
    """
    provider = _get_connection_provider(connection_id, auth.user_id, db)

    if provider == "fathom":
        sync_log = await fathom_sync_service.sync_calls(
            connection_id=connection_id,
            user_id=auth.user_id,
            db=db,
            sync_type="manual",
            max_results=100,
            since_hours=720,  # 30 days
        )
    elif provider == "front":
        sync_log = await front_sync_service.sync_conversations(
            connection_id=connection_id,
            user_id=auth.user_id,
            db=db,
            sync_type="manual",
            max_results=200,
            since_hours=168,  # 7 days
        )
    elif provider == "zoom":
        sync_log = await zoom_sync_service.sync_recordings(
            connection_id=connection_id,
            user_id=auth.user_id,
            db=db,
            sync_type="manual",
            days_back=30,
            max_results=100,
        )
    elif provider == "microsoft":
        sync_log = await outlook_sync_service.sync_emails(
            connection_id=connection_id,
            user_id=auth.user_id,
            db=db,
            sync_type="manual",
            max_results=200,
            since_hours=168,  # 7 days
        )
    else:
        sync_log = await gmail_sync_service.sync_emails(
            connection_id=connection_id,
            user_id=auth.user_id,
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
    auth: AuthContext = Depends(get_auth),
) -> List[RoutingRuleResponse]:
    """
    Return all email routing rules for the current user, with client names.
    """
    rules = email_router.get_routing_rules(auth.user_id, db)
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
    auth: AuthContext = Depends(get_auth),
) -> RoutingRuleResponse:
    """
    Create a new email routing rule that maps an email address to a client.
    """
    # Verify user has access to the target client
    check_client_access(auth, body.client_id, db)

    try:
        rule = email_router.create_routing_rule(
            user_id=auth.user_id,
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
    auth: AuthContext = Depends(get_auth),
) -> None:
    """
    Delete an email routing rule (ownership-scoped).
    """
    deleted = email_router.delete_routing_rule(rule_id, auth.user_id, db)
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
    auth: AuthContext = Depends(get_auth),
) -> List[RoutingRuleResponse]:
    """
    Scan all clients that have an email address and create 'from' routing
    rules for any that don't already have one.  Returns the newly created
    rules.
    """
    created_rules = email_router.auto_create_routing_rules(auth.user_id, db)

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


# ---------------------------------------------------------------------------
# Zoom meeting rules endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/integrations/zoom-rules",
    response_model=List[ZoomRuleResponse],
    summary="List all Zoom meeting matching rules",
)
async def list_zoom_rules(
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> List[ZoomRuleResponse]:
    """
    Return all Zoom meeting routing rules for the current user, with client names.
    """
    from app.models.client import Client
    from app.models.zoom_meeting_rule import ZoomMeetingRule

    rules = (
        db.query(ZoomMeetingRule, Client.name)
        .join(Client, ZoomMeetingRule.client_id == Client.id)
        .filter(ZoomMeetingRule.user_id == auth.user_id)
        .order_by(ZoomMeetingRule.created_at.desc())
        .all()
    )

    return [
        ZoomRuleResponse(
            id=rule.id,
            user_id=rule.user_id,
            match_field=rule.match_field,
            match_value=rule.match_value,
            client_id=rule.client_id,
            client_name=client_name,
            is_active=rule.is_active,
            created_at=rule.created_at.isoformat(),
        )
        for rule, client_name in rules
    ]


@router.post(
    "/integrations/zoom-rules",
    response_model=ZoomRuleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a Zoom meeting matching rule",
)
async def create_zoom_rule(
    body: ZoomRuleCreateRequest,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> ZoomRuleResponse:
    """
    Create a new Zoom meeting routing rule that maps a meeting attribute to a client.
    """
    from app.models.client import Client
    from app.models.zoom_meeting_rule import ZoomMeetingRule

    # Validate match_field
    valid_fields = ("topic_contains", "participant_email", "meeting_id_prefix")
    if body.match_field not in valid_fields:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid match_field: {body.match_field!r}. Must be one of {valid_fields}",
        )

    if not body.match_value.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="match_value must not be empty",
        )

    # Verify client access
    check_client_access(auth, body.client_id, db)
    client = db.query(Client).filter(Client.id == body.client_id).first()

    # Check for duplicate
    existing = (
        db.query(ZoomMeetingRule)
        .filter(
            ZoomMeetingRule.user_id == auth.user_id,
            ZoomMeetingRule.match_value == body.match_value.strip(),
            ZoomMeetingRule.match_field == body.match_field,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"A rule for {body.match_value!r} with match_field={body.match_field!r} already exists",
        )

    rule = ZoomMeetingRule(
        user_id=auth.user_id,
        match_field=body.match_field,
        match_value=body.match_value.strip(),
        client_id=body.client_id,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)

    return ZoomRuleResponse(
        id=rule.id,
        user_id=rule.user_id,
        match_field=rule.match_field,
        match_value=rule.match_value,
        client_id=rule.client_id,
        client_name=client.name,
        is_active=rule.is_active,
        created_at=rule.created_at.isoformat(),
    )


@router.delete(
    "/integrations/zoom-rules/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a Zoom meeting matching rule",
)
async def delete_zoom_rule(
    rule_id: UUID,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> None:
    """
    Delete a Zoom meeting routing rule (ownership-scoped).
    """
    from app.models.zoom_meeting_rule import ZoomMeetingRule

    rule = (
        db.query(ZoomMeetingRule)
        .filter(
            ZoomMeetingRule.id == rule_id,
            ZoomMeetingRule.user_id == auth.user_id,
        )
        .first()
    )
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Zoom rule not found",
        )

    db.delete(rule)
    db.commit()


@router.post(
    "/integrations/zoom-rules/auto-generate",
    response_model=List[ZoomRuleResponse],
    summary="Auto-generate Zoom rules from client names",
)
async def auto_generate_zoom_rules(
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> List[ZoomRuleResponse]:
    """
    For each client in the org, create a topic_contains rule using the client's name
    (if one doesn't already exist).  Returns the newly created rules.
    """
    from app.models.client import Client
    from app.models.zoom_meeting_rule import ZoomMeetingRule

    clients = (
        db.query(Client)
        .filter(Client.org_id == auth.org_id)
        .all()
    )

    # Get existing topic_contains rules to avoid duplicates
    existing_rules = (
        db.query(ZoomMeetingRule)
        .filter(
            ZoomMeetingRule.user_id == auth.user_id,
            ZoomMeetingRule.match_field == "topic_contains",
        )
        .all()
    )
    existing_values = {r.match_value.strip().lower() for r in existing_rules}

    created: list[ZoomMeetingRule] = []
    for client in clients:
        if not client.name or not client.name.strip():
            continue
        name_lower = client.name.strip().lower()
        if name_lower in existing_values:
            continue

        rule = ZoomMeetingRule(
            user_id=auth.user_id,
            match_field="topic_contains",
            match_value=client.name.strip(),
            client_id=client.id,
        )
        db.add(rule)
        created.append(rule)
        existing_values.add(name_lower)

    if created:
        db.commit()
        for rule in created:
            db.refresh(rule)

    return [
        ZoomRuleResponse(
            id=rule.id,
            user_id=rule.user_id,
            match_field=rule.match_field,
            match_value=rule.match_value,
            client_id=rule.client_id,
            client_name=next(
                (c.name for c in clients if c.id == rule.client_id), "Unknown"
            ),
            is_active=rule.is_active,
            created_at=rule.created_at.isoformat(),
        )
        for rule in created
    ]


# ---------------------------------------------------------------------------
# Zoom unmatched recordings endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/integrations/zoom/unmatched",
    response_model=List[UnmatchedRecordingResponse],
    summary="List Zoom recordings without a client match",
)
async def list_unmatched_recordings(
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> List[UnmatchedRecordingResponse]:
    """
    Return Zoom documents that don't have a client assignment.

    Since client_id is NOT NULL on documents, unmatched recordings are
    never ingested by the sync service.  This endpoint instead returns
    Zoom meetings that were *skipped* during sync — i.e., meetings that
    exist in Zoom but have no corresponding document in Callwen.

    Implementation: returns Zoom-sourced documents that were ingested but
    may need re-assignment.  In practice this returns recently synced Zoom
    documents so the user can review and reassign if needed.
    """
    from app.models.document import Document

    # Return Zoom documents for clients in this org, most recent first
    docs = (
        db.query(Document)
        .join(Client, Document.client_id == Client.id)
        .filter(
            Document.source == "zoom",
            Client.org_id == auth.org_id,
        )
        .order_by(Document.upload_date.desc())
        .limit(50)
        .all()
    )

    return [
        UnmatchedRecordingResponse(
            document_id=doc.id,
            filename=doc.filename,
            file_size=doc.file_size,
            source=doc.source,
            external_id=doc.external_id,
            upload_date=doc.upload_date.isoformat(),
        )
        for doc in docs
    ]


@router.post(
    "/integrations/zoom/assign",
    response_model=ZoomRuleResponse,
    summary="Assign a Zoom recording to a client and create a routing rule",
)
async def assign_recording(
    body: AssignRecordingRequest,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> ZoomRuleResponse:
    """
    Reassign a Zoom document to a different client.  Optionally creates a
    Zoom meeting rule so future meetings with the same topic are auto-matched.
    """
    from app.models.client import Client
    from app.models.document import Document
    from app.models.zoom_meeting_rule import ZoomMeetingRule

    # Verify target client access
    check_client_access(auth, body.client_id, db)
    client = db.query(Client).filter(Client.id == body.client_id).first()

    # Verify document exists and belongs to the org
    doc = (
        db.query(Document)
        .join(Client, Document.client_id == Client.id)
        .filter(
            Document.id == body.document_id,
            Document.source == "zoom",
            Client.org_id == auth.org_id,
        )
        .first()
    )
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Zoom document not found",
        )

    # Reassign the document to the new client
    doc.client_id = body.client_id
    db.commit()
    db.refresh(doc)

    # Optionally create a routing rule for future matches
    rule = None
    if body.create_rule:
        # Extract the meeting topic from the filename
        # Filenames are like: zoom_meeting_{topic}_{date}.txt
        topic = doc.filename
        if topic.startswith("zoom_meeting_"):
            topic = topic[len("zoom_meeting_"):]
        # Remove date suffix and .txt
        topic = topic.rsplit("_", 1)[0] if "_" in topic else topic
        if topic.endswith(".txt"):
            topic = topic[:-4]
        # Convert underscores back to spaces
        topic = topic.replace("_", " ").strip()

        if topic:
            # Check for duplicate
            existing = (
                db.query(ZoomMeetingRule)
                .filter(
                    ZoomMeetingRule.user_id == auth.user_id,
                    ZoomMeetingRule.match_value == topic,
                    ZoomMeetingRule.match_field == body.rule_match_field,
                )
                .first()
            )
            if not existing:
                rule = ZoomMeetingRule(
                    user_id=auth.user_id,
                    match_field=body.rule_match_field,
                    match_value=topic,
                    client_id=body.client_id,
                )
                db.add(rule)
                db.commit()
                db.refresh(rule)

    if not rule:
        # Return a synthetic response when no rule was created
        # (either create_rule=False or rule already existed)
        return ZoomRuleResponse(
            id=doc.id,  # use document id as placeholder
            user_id=auth.user_id,
            match_field=body.rule_match_field,
            match_value="(document reassigned, no new rule)",
            client_id=body.client_id,
            client_name=client.name,
            is_active=True,
            created_at=doc.upload_date.isoformat(),
        )

    return ZoomRuleResponse(
        id=rule.id,
        user_id=rule.user_id,
        match_field=rule.match_field,
        match_value=rule.match_value,
        client_id=rule.client_id,
        client_name=client.name,
        is_active=rule.is_active,
        created_at=rule.created_at.isoformat(),
    )


# ---------------------------------------------------------------------------
# Admin: auto-sync endpoints
# ---------------------------------------------------------------------------

async def _require_admin_integrations(request: Any) -> None:
    """Require admin auth via X-Admin-Key header or Clerk admin JWT."""
    settings = get_settings()

    api_key = request.headers.get("X-Admin-Key")
    if api_key and settings.admin_api_key and hmac.compare_digest(
        api_key.encode("utf-8"), settings.admin_api_key.encode("utf-8")
    ):
        return

    from fastapi.security import HTTPBearer
    bearer = HTTPBearer(auto_error=False)
    credentials = await bearer(request)
    if credentials:
        try:
            from app.core.auth import verify_clerk_token
            payload = await verify_clerk_token(credentials.credentials)
            user_id = payload.get("sub")
            if settings.admin_user_id and user_id and hmac.compare_digest(
                user_id.encode("utf-8"), settings.admin_user_id.encode("utf-8")
            ):
                return
        except HTTPException:
            pass

    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")


@router.post(
    "/integrations/admin/trigger-sync",
    summary="Manually trigger auto-sync (admin only)",
)
async def admin_trigger_sync(
    request: Request,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Manually trigger the auto-sync loop for all active connections.
    Requires admin authentication.
    """
    await _require_admin_integrations(request)

    from app.services.auto_sync_service import run_auto_sync
    summary = await run_auto_sync(db)
    return summary


@router.get(
    "/integrations/admin/sync-status",
    summary="Get auto-sync scheduler status (admin only)",
)
async def admin_sync_status(
    request: Request,
) -> Dict[str, Any]:
    """
    Return the current auto-sync scheduler status.
    Requires admin authentication.
    """
    await _require_admin_integrations(request)

    from app.services.auto_sync_service import get_scheduler_status
    return get_scheduler_status()

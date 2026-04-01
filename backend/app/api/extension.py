"""Browser extension endpoints — capture content, auto-match clients, config."""

from __future__ import annotations

import asyncio
import base64
import logging
import uuid as _uuid
from datetime import datetime, timezone
from typing import List, Optional
from urllib.parse import urlparse
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.client import Client
from app.models.document import Document
from app.services import storage_service, user_service
from app.services.audit_service import log_action
from app.services.auth_context import AuthContext, check_client_access, get_auth
from app.services.email_router import match_email_to_client
from app.services.extension_rate_limiter import check_rate as check_burst_rate
from app.services.subscription_service import (
    TIER_DEFAULTS,
    check_extension_capture_limit,
    get_extension_config,
    get_or_create_subscription,
)

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_FILE_URL_SIZE = 50 * 1024 * 1024  # 50 MB
FILE_URL_TIMEOUT = 30  # seconds

CAPTURE_TYPES = {"text_selection", "full_page", "file_url", "screenshot"}
TAX_RELATED_TAGS = {"tax_document", "financial_statement"}


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class CaptureMetadata(BaseModel):
    url: str
    page_title: str = ""
    captured_at: str = ""
    site_domain: str = ""


class CaptureRequest(BaseModel):
    client_id: UUID
    capture_type: str
    content: Optional[str] = None
    file_url: Optional[str] = None
    image_data: Optional[str] = None
    metadata: CaptureMetadata
    document_tag: Optional[str] = None


class CaptureResponse(BaseModel):
    document_id: UUID
    filename: str
    status: str
    client_name: str
    warning: Optional[str] = None


class MatchClientRequest(BaseModel):
    url: str
    email_addresses: List[str] = Field(default_factory=list)
    company_names: List[str] = Field(default_factory=list)
    page_title: Optional[str] = None


class MatchClientResponse(BaseModel):
    matched: bool
    client_id: Optional[UUID] = None
    client_name: Optional[str] = None
    match_method: Optional[str] = None
    confidence: Optional[str] = None


class RecentCaptureItem(BaseModel):
    document_id: UUID
    client_id: UUID
    client_name: str
    filename: str
    capture_type: Optional[str] = None
    source_url: Optional[str] = None
    created_at: datetime
    processed: bool


class ExtensionConfigResponse(BaseModel):
    tier: str
    auto_match: bool
    quick_query: bool
    parsers: bool
    monitoring: bool
    captures_per_day: Optional[int] = None
    captures_today: int
    captures_remaining: Optional[int] = None


# ---------------------------------------------------------------------------
# POST /extension/capture
# ---------------------------------------------------------------------------


@router.post("/capture", response_model=CaptureResponse, status_code=status.HTTP_201_CREATED)
async def capture(
    body: CaptureRequest,
    request: Request,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> CaptureResponse:
    """Capture content from the browser extension and route into the document pipeline."""

    if body.capture_type not in CAPTURE_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid capture_type. Must be one of: {', '.join(sorted(CAPTURE_TYPES))}")

    # 0. Burst rate limit (in-memory, per-user)
    if not check_burst_rate(auth.user_id):
        raise HTTPException(status_code=429, detail="Too many captures. Please wait a moment.")

    # 1. Verify user owns the client
    check_client_access(auth, body.client_id, db)
    client = db.query(Client).filter(Client.id == body.client_id).first()
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found")

    # 2. Check capture limit
    limit_check = check_extension_capture_limit(db, auth.user_id, org_id=auth.org_id)
    if not limit_check["allowed"]:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "Daily capture limit reached",
                "limit": limit_check["limit"],
                "upgrade_url": "/dashboard/settings/subscriptions",
            },
        )

    # 3. Check 7216 consent for tax-related documents
    consent_warning = None
    pause_processing = False
    if (
        body.document_tag in TAX_RELATED_TAGS
        and getattr(client, "consent_status", None) == "pending"
    ):
        consent_warning = "Document saved but AI processing paused pending client consent"
        pause_processing = True

    # 4. Produce file bytes + filename based on capture type
    file_bytes: bytes
    filename: str
    content_type: str

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    if body.capture_type in ("text_selection", "full_page"):
        if not body.content:
            raise HTTPException(status_code=400, detail="content is required for text captures")
        file_bytes = body.content.encode("utf-8")
        safe_title = _safe_filename(body.metadata.page_title or "capture")
        filename = f"extension_{safe_title}_{ts}.txt"
        content_type = "text/plain"

    elif body.capture_type == "file_url":
        if not body.file_url:
            raise HTTPException(status_code=400, detail="file_url is required for file_url captures")
        file_bytes, filename, content_type = await _fetch_file_url(body.file_url, ts)

    elif body.capture_type == "screenshot":
        if not body.image_data:
            raise HTTPException(status_code=400, detail="image_data is required for screenshot captures")
        try:
            file_bytes = base64.b64decode(body.image_data)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid base64 image_data")
        filename = f"extension_screenshot_{ts}.png"
        content_type = "image/png"

    else:
        raise HTTPException(status_code=400, detail="Unsupported capture_type")

    # 5. Upload to Supabase Storage
    user = user_service.get_or_create_user(db, {"user_id": auth.user_id})
    file_id = str(_uuid.uuid4())

    storage_path = storage_service.upload_file(
        user_id=str(user.id),
        client_id=str(body.client_id),
        file_id=file_id,
        filename=filename,
        file_bytes=file_bytes,
        content_type=content_type,
        org_id=str(auth.org_id) if auth.org_id else None,
    )

    # 6. Create Document record
    ext = filename.rsplit(".", 1)[-1] if "." in filename else "txt"
    try:
        document = Document(
            client_id=body.client_id,
            uploaded_by=user.id,
            filename=filename,
            file_path=storage_path,
            file_type=ext,
            file_size=len(file_bytes),
            source="extension",
            external_id=body.metadata.url,
            processed=False if pause_processing else False,  # starts unprocessed; pipeline sets True
        )
        db.add(document)
        db.commit()
        db.refresh(document)
    except Exception:
        storage_service.delete_file(storage_path)
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to save document metadata.")

    # 7. Kick off RAG processing (unless consent-paused)
    if not pause_processing:
        from app.core.config import get_settings
        from app.services import rag_service
        from app.services.background_processor import run_in_process

        asyncio.create_task(
            run_in_process(
                rag_service.process_document_sync,
                str(document.id),
                get_settings().database_url,
            )
        )

    # 8. Audit log
    log_action(
        db, auth, "document.extension_capture", "document", document.id,
        detail={
            "capture_type": body.capture_type,
            "source_url": body.metadata.url,
            "site_domain": body.metadata.site_domain,
            "document_tag": body.document_tag,
        },
        request=request,
    )

    return CaptureResponse(
        document_id=document.id,
        filename=filename,
        status="saved_pending_consent" if pause_processing else "processing",
        client_name=client.name,
        warning=consent_warning,
    )


# ---------------------------------------------------------------------------
# GET /extension/config
# ---------------------------------------------------------------------------


@router.get("/config", response_model=ExtensionConfigResponse)
async def config(
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> ExtensionConfigResponse:
    """Return extension feature flags and usage for the current user."""
    cfg = get_extension_config(db, auth.user_id, org_id=auth.org_id)
    limit = cfg["captures_per_day"]
    remaining = None if limit is None else max(0, limit - cfg["captures_today"])
    return ExtensionConfigResponse(
        **cfg,
        captures_remaining=remaining,
    )


# ---------------------------------------------------------------------------
# POST /extension/match-client
# ---------------------------------------------------------------------------


@router.post("/match-client", response_model=MatchClientResponse)
async def match_client(
    body: MatchClientRequest,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> MatchClientResponse:
    """Auto-match a webpage to an existing client (paid tiers only)."""

    # Check feature flag
    sub = get_or_create_subscription(db, auth.user_id, org_id=auth.org_id)
    tier_config = TIER_DEFAULTS.get(sub.tier, TIER_DEFAULTS["free"])
    if not tier_config["extension_auto_match"]:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "Auto-matching requires a paid plan",
                "upgrade_url": "/dashboard/settings/subscriptions",
            },
        )

    # 1. Try email routing rules
    for email in body.email_addresses:
        client_id = match_email_to_client(
            from_email=email, to_emails=[], user_id=auth.user_id, db=db,
        )
        if client_id:
            client = db.query(Client).filter(Client.id == client_id).first()
            return MatchClientResponse(
                matched=True,
                client_id=client_id,
                client_name=client.name if client else None,
                match_method="email_rule",
                confidence="high",
            )

    # 2. Fuzzy-match company names against clients
    if body.company_names:
        base_q = db.query(Client)
        if auth.org_id:
            base_q = base_q.filter(Client.org_id == auth.org_id)

        for name in body.company_names:
            pattern = f"%{name}%"
            match = base_q.filter(
                func.lower(Client.business_name).ilike(func.lower(pattern))
                | func.lower(Client.name).ilike(func.lower(pattern))
            ).first()
            if match:
                return MatchClientResponse(
                    matched=True,
                    client_id=match.id,
                    client_name=match.name,
                    match_method="company_name",
                    confidence="medium",
                )

    # 3. Domain history — check previous extension captures from same domain
    domain = _extract_domain(body.url)
    if domain:
        domain_match = (
            db.query(Document.client_id, Client.name)
            .join(Client, Document.client_id == Client.id)
            .filter(
                Document.source == "extension",
                Document.external_id.ilike(f"%{domain}%"),
            )
        )
        if auth.org_id:
            domain_match = domain_match.filter(Client.org_id == auth.org_id)

        domain_match = domain_match.order_by(Document.upload_date.desc()).first()
        if domain_match:
            return MatchClientResponse(
                matched=True,
                client_id=domain_match[0],
                client_name=domain_match[1],
                match_method="domain_history",
                confidence="medium",
            )

    return MatchClientResponse(matched=False)


# ---------------------------------------------------------------------------
# GET /extension/recent-captures
# ---------------------------------------------------------------------------


@router.get("/recent-captures", response_model=List[RecentCaptureItem])
async def recent_captures(
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> List[RecentCaptureItem]:
    """Return the last 10 extension captures for the current user."""
    user = user_service.get_or_create_user(db, {"user_id": auth.user_id})

    rows = (
        db.query(Document, Client.name)
        .join(Client, Document.client_id == Client.id)
        .filter(
            Document.source == "extension",
            Document.uploaded_by == user.id,
        )
        .order_by(Document.upload_date.desc())
        .limit(10)
        .all()
    )

    return [
        RecentCaptureItem(
            document_id=doc.id,
            client_id=doc.client_id,
            client_name=client_name,
            filename=doc.filename,
            capture_type=doc.file_type,
            source_url=doc.external_id,
            created_at=doc.upload_date,
            processed=doc.processed,
        )
        for doc, client_name in rows
    ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_filename(title: str) -> str:
    """Sanitize a page title for use in a filename."""
    safe = "".join(c if c.isalnum() or c in (" ", "-", "_") else "" for c in title)
    return safe.strip().replace(" ", "_")[:60] or "capture"


def _extract_domain(url: str) -> str | None:
    """Extract the domain from a URL."""
    try:
        parsed = urlparse(url)
        return parsed.netloc or None
    except Exception:
        return None


async def _fetch_file_url(url: str, ts: str) -> tuple[bytes, str, str]:
    """Fetch a file from a URL with size and timeout limits."""
    async with httpx.AsyncClient(timeout=FILE_URL_TIMEOUT, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()

    if len(resp.content) > MAX_FILE_URL_SIZE:
        raise HTTPException(status_code=413, detail="Remote file exceeds 50 MB limit.")

    # Derive filename from URL path or Content-Disposition
    parsed = urlparse(url)
    path_name = parsed.path.rsplit("/", 1)[-1] if "/" in parsed.path else ""
    if not path_name or "." not in path_name:
        ct = resp.headers.get("content-type", "application/octet-stream").split(";")[0]
        ext = _mime_to_ext(ct)
        path_name = f"extension_file_{ts}.{ext}"

    content_type = resp.headers.get("content-type", "application/octet-stream").split(";")[0]
    return resp.content, path_name, content_type


def _mime_to_ext(mime: str) -> str:
    """Map common MIME types to file extensions."""
    mapping = {
        "application/pdf": "pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
        "text/plain": "txt",
        "text/csv": "csv",
        "text/html": "html",
        "image/png": "png",
        "image/jpeg": "jpg",
    }
    return mapping.get(mime, "bin")

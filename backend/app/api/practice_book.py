"""Practice Book Export — PDF, JSON, and CSV endpoints."""

import csv
import io
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.auth_context import AuthContext, check_client_access, get_auth, require_admin
from app.services.practice_book_service import (
    generate_client_practice_page,
    generate_practice_book_pdf,
    generate_practice_summary,
    generate_single_client_pdf,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Request schemas ──────────────────────────────────────────────────────────


class PracticeBookExportRequest(BaseModel):
    format: str = "pdf"  # pdf | json | csv
    client_ids: list[UUID] | None = None


# ── Helpers ──────────────────────────────────────────────────────────────────


def _serialize(obj):
    """Make practice book dicts JSON-safe (dates, UUIDs, etc.)."""
    import datetime

    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize(v) for v in obj]
    if isinstance(obj, (datetime.date, datetime.datetime)):
        return obj.isoformat()
    if isinstance(obj, UUID):
        return str(obj)
    return obj


# ── 1. Full practice book export ─────────────────────────────────────────────


@router.post("/practice-book/export")
async def export_practice_book(
    body: PracticeBookExportRequest,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
):
    """Export practice book as PDF, JSON, or CSV.

    Requires admin role for org-wide exports.
    If client_ids is provided, verifies access to each client.
    """
    # Org-wide export (no client_ids filter) requires admin
    if not body.client_ids and auth.org_id and not auth.is_personal_org:
        require_admin(auth)

    # Verify access to specific clients if provided
    if body.client_ids:
        for cid in body.client_ids:
            check_client_access(auth, str(cid), db)

    fmt = body.format.lower()

    if fmt == "pdf":
        pdf_bytes = generate_practice_book_pdf(
            db,
            user_id=auth.user_id,
            org_id=UUID(str(auth.org_id)) if auth.org_id else None,
            client_ids=body.client_ids,
        )
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=practice-book.pdf"},
        )

    if fmt == "json":
        summary = generate_practice_summary(
            db,
            user_id=auth.user_id,
            org_id=UUID(str(auth.org_id)) if auth.org_id else None,
        )
        # Include per-client pages
        client_pages = []
        client_list = body.client_ids or [
            c["client_id"] for c in summary.get("clients", [])
        ]
        for cid in client_list:
            try:
                page = generate_client_practice_page(db, cid, auth.user_id)
                page["client_id"] = str(cid)
                client_pages.append(page)
            except ValueError:
                continue
        data = _serialize({
            "practice_summary": summary,
            "clients": client_pages,
        })
        return JSONResponse(content=data)

    if fmt == "csv":
        summary = generate_practice_summary(
            db,
            user_id=auth.user_id,
            org_id=UUID(str(auth.org_id)) if auth.org_id else None,
        )
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Client Name",
            "Entity Type",
            "Health Score",
            "Estimated Impact",
            "Document Count",
            "Last Contact",
            "Open Actions",
            "Data Quality",
        ])
        for c in summary.get("clients", []):
            if body.client_ids and UUID(c["client_id"]) not in body.client_ids:
                continue
            writer.writerow([
                c.get("name", ""),
                c.get("entity_type", ""),
                c.get("health_score", ""),
                c.get("estimated_impact", ""),
                c.get("document_count", ""),
                c.get("last_contact", ""),
                c.get("open_action_count", ""),
                c.get("data_quality", "Clean"),
            ])
        return StreamingResponse(
            io.BytesIO(output.getvalue().encode("utf-8")),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=practice-book.csv"},
        )

    raise HTTPException(status_code=400, detail=f"Unsupported format: {body.format}")


# ── 2. Single-client practice book ──────────────────────────────────────────


@router.post("/clients/{client_id}/practice-book")
async def export_single_client(
    client_id: UUID,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
):
    """Generate a single-client practice book PDF."""
    check_client_access(auth, str(client_id), db)
    pdf_bytes = generate_single_client_pdf(db, client_id, auth.user_id)
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=practice-book-{client_id}.pdf",
        },
    )


# ── 3. Practice summary (JSON) ──────────────────────────────────────────────


@router.get("/practice-book/summary")
async def get_practice_summary(
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
):
    """Return practice-level summary data (aggregate stats, per-client scores)."""
    summary = generate_practice_summary(
        db,
        user_id=auth.user_id,
        org_id=UUID(str(auth.org_id)) if auth.org_id else None,
    )
    return JSONResponse(content=_serialize(summary))

"""Per-client cadence API endpoints (G4-P3a)."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.cadence import (
    AssignCadenceRequest,
    ClientCadenceResponse,
    EnabledDeliverablesResponse,
    UpdateOverridesRequest,
)
from app.services import cadence_service
from app.services.auth_context import AuthContext, check_client_access, get_auth

router = APIRouter(
    prefix="/clients/{client_id}/cadence",
    tags=["cadence"],
)


def _detail_to_response(client_id: UUID, detail) -> ClientCadenceResponse:
    return ClientCadenceResponse(
        client_id=client_id,
        template_id=detail.template_id,
        template_name=detail.template_name,
        template_is_system=detail.template_is_system,
        overrides=detail.overrides,
        effective_flags=detail.effective_flags,
    )


@router.get("", response_model=ClientCadenceResponse)
async def get_cadence(
    client_id: UUID,
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
) -> ClientCadenceResponse:
    check_client_access(auth, client_id, db)
    detail = cadence_service.get_client_cadence_detail(db, client_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="No cadence assigned for this client")
    return _detail_to_response(client_id, detail)


@router.put("", response_model=ClientCadenceResponse)
async def assign_cadence(
    client_id: UUID,
    body: AssignCadenceRequest,
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
) -> ClientCadenceResponse:
    check_client_access(auth, client_id, db)
    try:
        cadence_service.assign_cadence(db, client_id, body.template_id, auth.user_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    detail = cadence_service.get_client_cadence_detail(db, client_id)
    return _detail_to_response(client_id, detail)


@router.patch("/overrides", response_model=ClientCadenceResponse)
async def update_overrides(
    client_id: UUID,
    body: UpdateOverridesRequest,
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
) -> ClientCadenceResponse:
    check_client_access(auth, client_id, db)
    overrides_str_keyed = {
        (k.value if hasattr(k, "value") else k): v for k, v in body.overrides.items()
    }
    try:
        cadence_service.update_overrides(db, client_id, overrides_str_keyed, auth.user_id)
    except ValueError as e:
        msg = str(e).lower()
        if "no cadence" in msg:
            raise HTTPException(status_code=409, detail=str(e))
        raise HTTPException(status_code=422, detail=str(e))
    detail = cadence_service.get_client_cadence_detail(db, client_id)
    return _detail_to_response(client_id, detail)


@router.get("/enabled-deliverables", response_model=EnabledDeliverablesResponse)
async def get_enabled_deliverables(
    client_id: UUID,
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
) -> EnabledDeliverablesResponse:
    check_client_access(auth, client_id, db)
    enabled = cadence_service.list_enabled_deliverables(db, client_id)
    return EnabledDeliverablesResponse(enabled=enabled)

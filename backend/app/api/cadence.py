"""Cadence API endpoints (G4-P3a per-client + G4-P3b org-level template management)."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.cadence import (
    AssignCadenceRequest,
    CadenceTemplateDetailResponse,
    CadenceTemplateListResponse,
    CadenceTemplateSummary,
    ClientCadenceResponse,
    CreateCadenceTemplateRequest,
    EnabledDeliverablesResponse,
    SetFirmDefaultRequest,
    UpdateCadenceTemplateRequest,
    UpdateOverridesRequest,
)
from app.services import cadence_service
from app.services.auth_context import AuthContext, check_client_access, get_auth, require_admin

router = APIRouter(tags=["cadence"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _detail_to_response(client_id: UUID, detail) -> ClientCadenceResponse:
    return ClientCadenceResponse(
        client_id=client_id,
        template_id=detail.template_id,
        template_name=detail.template_name,
        template_is_system=detail.template_is_system,
        overrides=detail.overrides,
        effective_flags=detail.effective_flags,
    )


def _template_detail_to_response(twf) -> CadenceTemplateDetailResponse:
    """Compose CadenceTemplateDetailResponse from TemplateWithFlags dataclass."""
    return CadenceTemplateDetailResponse(
        id=twf.template.id,
        name=twf.template.name,
        description=twf.template.description,
        is_system=twf.template.is_system,
        is_active=twf.template.is_active,
        deliverable_flags=twf.deliverable_flags,
    )


def _template_to_summary(template) -> CadenceTemplateSummary:
    """Compose CadenceTemplateSummary from a CadenceTemplate row."""
    return CadenceTemplateSummary(
        id=template.id,
        name=template.name,
        description=template.description,
        is_system=template.is_system,
        is_active=template.is_active,
    )


def _scope_check_template(twf, auth, action: str) -> None:
    """Raise 403 if a non-system template doesn't belong to the caller's org.

    action is one of: 'access', 'modify', 'deactivate'. Used in the error message.
    """
    if twf.template.is_system:
        return
    if twf.template.org_id != auth.org_id:
        raise HTTPException(
            status_code=403,
            detail=f"Template {twf.template.id} not in your organization scope; {action} not allowed",
        )


# ---------------------------------------------------------------------------
# G4-P3a — Per-client cadence endpoints
# ---------------------------------------------------------------------------


@router.get("/clients/{client_id}/cadence", response_model=ClientCadenceResponse)
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


@router.put("/clients/{client_id}/cadence", response_model=ClientCadenceResponse)
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


@router.patch("/clients/{client_id}/cadence/overrides", response_model=ClientCadenceResponse)
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


@router.get("/clients/{client_id}/cadence/enabled-deliverables", response_model=EnabledDeliverablesResponse)
async def get_enabled_deliverables(
    client_id: UUID,
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
) -> EnabledDeliverablesResponse:
    check_client_access(auth, client_id, db)
    enabled = cadence_service.list_enabled_deliverables(db, client_id)
    return EnabledDeliverablesResponse(enabled=enabled)


# ---------------------------------------------------------------------------
# G4-P3b — Org-level cadence template management endpoints
# ---------------------------------------------------------------------------


@router.get("/cadence-templates", response_model=CadenceTemplateListResponse)
def list_cadence_templates(
    include_inactive: bool = Query(default=False),
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
) -> CadenceTemplateListResponse:
    templates = cadence_service.list_templates_for_org(
        db, auth.org_id, include_inactive=include_inactive
    )
    return CadenceTemplateListResponse(
        templates=[_template_to_summary(t) for t in templates]
    )


@router.get("/cadence-templates/{template_id}", response_model=CadenceTemplateDetailResponse)
def get_cadence_template(
    template_id: UUID,
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
) -> CadenceTemplateDetailResponse:
    twf = cadence_service.get_template_with_flags(db, template_id)
    if twf is None:
        raise HTTPException(status_code=404, detail=f"Template {template_id} not found")
    _scope_check_template(twf, auth, "access")
    return _template_detail_to_response(twf)


@router.post(
    "/cadence-templates",
    response_model=CadenceTemplateDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_cadence_template(
    body: CreateCadenceTemplateRequest,
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
) -> CadenceTemplateDetailResponse:
    require_admin(auth)
    flags_str_keyed = {
        (k.value if hasattr(k, "value") else k): v for k, v in body.deliverable_flags.items()
    }
    try:
        template = cadence_service.create_custom_template(
            db,
            org_id=auth.org_id,
            name=body.name,
            description=body.description,
            deliverable_flags=flags_str_keyed,
            created_by=auth.user_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    twf = cadence_service.get_template_with_flags(db, template.id)
    return _template_detail_to_response(twf)


@router.patch("/cadence-templates/{template_id}", response_model=CadenceTemplateDetailResponse)
def update_cadence_template(
    template_id: UUID,
    body: UpdateCadenceTemplateRequest,
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
) -> CadenceTemplateDetailResponse:
    require_admin(auth)
    twf = cadence_service.get_template_with_flags(db, template_id)
    if twf is None:
        raise HTTPException(status_code=404, detail=f"Template {template_id} not found")
    if twf.template.is_system:
        raise HTTPException(
            status_code=403,
            detail="System templates cannot be modified",
        )
    _scope_check_template(twf, auth, "modify")
    flags_str_keyed = None
    if body.deliverable_flags is not None:
        flags_str_keyed = {
            (k.value if hasattr(k, "value") else k): v for k, v in body.deliverable_flags.items()
        }
    try:
        cadence_service.update_template(
            db,
            template_id=template_id,
            name=body.name,
            description=body.description,
            deliverable_flags=flags_str_keyed,
            updated_by=auth.user_id,
            org_id=auth.org_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    twf_refreshed = cadence_service.get_template_with_flags(db, template_id)
    return _template_detail_to_response(twf_refreshed)


@router.post("/cadence-templates/{template_id}/deactivate", status_code=204, response_model=None)
def deactivate_cadence_template(
    template_id: UUID,
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
) -> None:
    require_admin(auth)
    twf = cadence_service.get_template_with_flags(db, template_id)
    if twf is None:
        raise HTTPException(status_code=404, detail=f"Template {template_id} not found")
    if twf.template.is_system:
        raise HTTPException(
            status_code=403,
            detail="System templates cannot be deactivated",
        )
    _scope_check_template(twf, auth, "deactivate")
    try:
        cadence_service.deactivate_template(
            db,
            template_id=template_id,
            updated_by=auth.user_id,
            org_id=auth.org_id,
        )
    except ValueError as e:
        msg = str(e).lower()
        if "referenced" in msg:
            raise HTTPException(status_code=409, detail=str(e))
        raise HTTPException(status_code=422, detail=str(e))
    return None


@router.put(
    "/organizations/{org_id}/cadence/default-template",
    status_code=204,
    response_model=None,
)
def set_firm_default_template(
    org_id: UUID,
    body: SetFirmDefaultRequest,
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
) -> None:
    require_admin(auth)
    if org_id != auth.org_id:
        raise HTTPException(
            status_code=403,
            detail="Cannot set firm default for a different organization",
        )
    try:
        cadence_service.set_firm_default(
            db,
            org_id=org_id,
            template_id=body.template_id,
            updated_by=auth.user_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return None

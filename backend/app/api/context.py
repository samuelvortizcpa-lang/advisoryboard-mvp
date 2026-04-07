"""Context assembler API — primarily for debugging and testing."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.context import ClientContextResponse, ContextRequest
from app.services.auth_context import AuthContext, check_client_access, get_auth
from app.services.context_assembler import ContextPurpose, assemble_context

router = APIRouter()

_VALID_PURPOSES = {p.value for p in ContextPurpose}


@router.post(
    "/clients/{client_id}/context",
    response_model=ClientContextResponse,
    summary="Assemble AI context for a client (debug/testing)",
)
async def get_client_context(
    client_id: UUID,
    body: ContextRequest,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> ClientContextResponse:
    check_client_access(auth, client_id, db)

    if body.purpose not in _VALID_PURPOSES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid purpose '{body.purpose}'. Must be one of: {', '.join(sorted(_VALID_PURPOSES))}",
        )

    purpose = ContextPurpose(body.purpose)
    ctx = await assemble_context(
        db,
        client_id=client_id,
        user_id=auth.user_id,
        purpose=purpose,
        options=body.options,
    )

    return ClientContextResponse(
        client_profile=ctx.client_profile,
        documents_summary=ctx.documents_summary,
        financial_metrics=ctx.financial_metrics,
        action_items=ctx.action_items,
        communication_history=ctx.communication_history,
        journal_entries=ctx.journal_entries,
        strategy_status=ctx.strategy_status,
        engagement_calendar=ctx.engagement_calendar,
        rag_chunks=ctx.rag_chunks,
    )

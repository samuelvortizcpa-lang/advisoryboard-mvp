"""Deliverable drafting + sending API endpoints (G5-P4)."""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.deliverables import (
    DeliverableDraftResponse,
    DraftKickoffMemoRequest,
    RecordDeliverableSentRequest,
)
from app.services.auth_context import AuthContext, check_client_access, get_auth, require_admin
from app.services.engagement_deliverable_service import (
    draft_deliverable,
    record_deliverable_sent,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["deliverables"])


# ---------------------------------------------------------------------------
# POST /clients/{client_id}/deliverables/kickoff-memo/draft
# ---------------------------------------------------------------------------


@router.post(
    "/clients/{client_id}/deliverables/kickoff-memo/draft",
    response_model=DeliverableDraftResponse,
)
async def draft_kickoff_memo(
    client_id: UUID,
    payload: DraftKickoffMemoRequest,
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
) -> DeliverableDraftResponse:
    require_admin(auth)
    check_client_access(auth, client_id, db)
    try:
        return await draft_deliverable(
            db=db,
            client_id=client_id,
            deliverable_key="kickoff_memo",
            tax_year=payload.tax_year,
            requested_by=auth.user_id,
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception:
        logger.exception("LLM generation failed for client %s", client_id)
        raise HTTPException(status_code=502, detail="LLM generation failed")


# ---------------------------------------------------------------------------
# POST /clients/{client_id}/deliverables/kickoff-memo/send
# ---------------------------------------------------------------------------


@router.post("/clients/{client_id}/deliverables/kickoff-memo/send")
def send_kickoff_memo(
    client_id: UUID,
    payload: RecordDeliverableSentRequest,
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
) -> dict:
    require_admin(auth)
    check_client_access(auth, client_id, db)
    try:
        comm = record_deliverable_sent(
            db=db,
            client_id=client_id,
            deliverable_key="kickoff_memo",
            tax_year=payload.tax_year,
            subject=payload.subject,
            body=payload.body,
            sent_by=auth.user_id,
            recipient_email=payload.recipient_email,
            gmail_message_id=payload.gmail_message_id,
        )
        return {"client_communication_id": str(comm.id)}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

"""Pydantic schemas for cadence (Layer 2 Gap 4)."""
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, StrictBool


class DeliverableKey(str, Enum):
    KICKOFF_MEMO = "kickoff_memo"
    PROGRESS_NOTE = "progress_note"
    QUARTERLY_MEMO = "quarterly_memo"
    MID_YEAR_TUNE_UP = "mid_year_tune_up"
    YEAR_END_RECAP = "year_end_recap"
    PRE_PREP_BRIEF = "pre_prep_brief"
    POST_PREP_FLAG = "post_prep_flag"


class ClientCadenceResponse(BaseModel):
    client_id: UUID
    template_id: UUID
    template_name: str
    template_is_system: bool
    overrides: dict[DeliverableKey, bool]
    effective_flags: dict[DeliverableKey, bool]


class AssignCadenceRequest(BaseModel):
    template_id: UUID


class UpdateOverridesRequest(BaseModel):
    overrides: dict[DeliverableKey, StrictBool]


class EnabledDeliverablesResponse(BaseModel):
    enabled: list[DeliverableKey]

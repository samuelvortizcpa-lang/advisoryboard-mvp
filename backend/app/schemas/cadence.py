"""Pydantic schemas for cadence (Layer 2 Gap 4)."""
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, StrictBool, model_validator


class DeliverableKey(str, Enum):
    KICKOFF_MEMO = "kickoff_memo"
    PROGRESS_NOTE = "progress_note"
    QUARTERLY_MEMO = "quarterly_memo"
    MID_YEAR_TUNE_UP = "mid_year_tune_up"
    YEAR_END_RECAP = "year_end_recap"
    PRE_PREP_BRIEF = "pre_prep_brief"
    POST_PREP_FLAG = "post_prep_flag"


# ---------------------------------------------------------------------------
# G4-P3a — Per-client cadence schemas
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# G4-P3b — Org-level cadence template schemas
# ---------------------------------------------------------------------------


def _validate_all_seven_keys(flags: dict) -> dict:
    provided_keys = set(flags.keys())
    expected_keys = set(DeliverableKey)
    if provided_keys != expected_keys:
        missing = expected_keys - provided_keys
        extra = provided_keys - expected_keys
        parts = []
        if missing:
            parts.append(f"missing keys: {sorted(k.value for k in missing)}")
        if extra:
            parts.append(f"unexpected keys: {sorted(str(k) for k in extra)}")
        raise ValueError(
            "deliverable_flags must contain exactly all 7 deliverable keys; " + ", ".join(parts)
        )
    return flags


class CadenceTemplateSummary(BaseModel):
    id: UUID
    name: str
    description: Optional[str] = None
    is_system: bool
    is_active: bool


class CadenceTemplateListResponse(BaseModel):
    templates: list[CadenceTemplateSummary]


class CadenceTemplateDetailResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str] = None
    is_system: bool
    is_active: bool
    deliverable_flags: dict[DeliverableKey, bool]


class CreateCadenceTemplateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)
    deliverable_flags: dict[DeliverableKey, StrictBool]

    @model_validator(mode="after")
    def _check_all_seven_keys(self):
        _validate_all_seven_keys(self.deliverable_flags)
        return self


class UpdateCadenceTemplateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)
    deliverable_flags: Optional[dict[DeliverableKey, StrictBool]] = None

    @model_validator(mode="after")
    def _check_all_seven_keys_when_present(self):
        if self.deliverable_flags is not None:
            _validate_all_seven_keys(self.deliverable_flags)
        return self


class SetFirmDefaultRequest(BaseModel):
    template_id: Optional[UUID] = None

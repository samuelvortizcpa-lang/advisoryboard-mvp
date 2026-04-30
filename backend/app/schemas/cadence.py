"""Pydantic schemas for cadence (Layer 2 Gap 4). G4-P1 ships only the
DeliverableKey enum; full request/response schemas land in G4-P3."""
from enum import Enum


class DeliverableKey(str, Enum):
    KICKOFF_MEMO = "kickoff_memo"
    PROGRESS_NOTE = "progress_note"
    QUARTERLY_MEMO = "quarterly_memo"
    MID_YEAR_TUNE_UP = "mid_year_tune_up"
    YEAR_END_RECAP = "year_end_recap"
    PRE_PREP_BRIEF = "pre_prep_brief"
    POST_PREP_FLAG = "post_prep_flag"

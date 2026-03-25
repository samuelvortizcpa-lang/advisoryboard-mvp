from __future__ import annotations

from typing import Optional
from uuid import UUID

from pydantic import BaseModel


# ─── Reference table ──────────────────────────────────────────────────────────


class TaxStrategyResponse(BaseModel):
    id: UUID
    name: str
    category: str
    description: Optional[str] = None
    required_flags: list[str] = []
    display_order: int

    class Config:
        from_attributes = True


# ─── Strategy + status (per client/year) ──────────────────────────────────────


class StrategyWithStatus(BaseModel):
    strategy: TaxStrategyResponse
    status: str = "not_reviewed"
    notes: Optional[str] = None
    estimated_impact: Optional[float] = None
    tax_year: int


class CategoryGroup(BaseModel):
    category_name: str
    strategies: list[StrategyWithStatus]


class ChecklistSummary(BaseModel):
    total_applicable: int
    total_reviewed: int
    total_implemented: int
    total_estimated_impact: float


class StrategyChecklistResponse(BaseModel):
    tax_year: int
    client_id: UUID
    categories: list[CategoryGroup]
    summary: ChecklistSummary


# ─── Mutations ────────────────────────────────────────────────────────────────


class StrategyStatusUpdate(BaseModel):
    tax_year: int
    status: str
    notes: Optional[str] = None
    estimated_impact: Optional[float] = None


class BulkStatusItem(BaseModel):
    strategy_id: UUID
    tax_year: int
    status: str
    notes: Optional[str] = None
    estimated_impact: Optional[float] = None


class BulkStatusUpdate(BaseModel):
    updates: list[BulkStatusItem]


class BulkStatusResponse(BaseModel):
    updated: int


# ─── History / comparison ─────────────────────────────────────────────────────


class YearStatus(BaseModel):
    tax_year: int
    status: str
    notes: Optional[str] = None
    estimated_impact: Optional[float] = None


class StrategyHistory(BaseModel):
    strategy_id: UUID
    name: str
    category: str
    statuses: list[YearStatus]


class YearSummary(BaseModel):
    tax_year: int
    total_applicable: int
    total_reviewed: int
    total_implemented: int
    total_estimated_impact: float


class StrategyHistoryResponse(BaseModel):
    strategies: list[StrategyHistory]
    year_summaries: list[YearSummary]
    available_years: list[int]


# ─── Profile flags ────────────────────────────────────────────────────────────


class ProfileFlagsUpdate(BaseModel):
    has_business_entity: Optional[bool] = None
    has_real_estate: Optional[bool] = None
    is_real_estate_professional: Optional[bool] = None
    has_high_income: Optional[bool] = None
    has_estate_planning: Optional[bool] = None
    is_medical_professional: Optional[bool] = None
    has_retirement_plans: Optional[bool] = None
    has_investments: Optional[bool] = None
    has_employees: Optional[bool] = None


class ProfileFlagsResponse(BaseModel):
    has_business_entity: bool
    has_real_estate: bool
    is_real_estate_professional: bool
    has_high_income: bool
    has_estate_planning: bool
    is_medical_professional: bool
    has_retirement_plans: bool
    has_investments: bool
    has_employees: bool

    class Config:
        from_attributes = True


# ─── AI suggestions ─────────────────────────────────────────────────────────


class FlagSuggestion(BaseModel):
    flag: str
    suggested_value: bool
    reason: str


class StrategySuggestion(BaseModel):
    strategy_name: str
    strategy_id: Optional[UUID] = None
    suggested_status: str
    reason: str


class AISuggestResponse(BaseModel):
    flag_suggestions: list[FlagSuggestion]
    strategy_suggestions: list[StrategySuggestion]
    documents_analyzed: int
    tax_year: int


class AcceptedFlag(BaseModel):
    flag: str
    value: bool


class AcceptedStrategy(BaseModel):
    strategy_id: UUID
    status: str
    notes: Optional[str] = None


class ApplySuggestionsRequest(BaseModel):
    accepted_flags: list[AcceptedFlag] = []
    accepted_strategies: list[AcceptedStrategy] = []
    tax_year: int


class ApplySuggestionsResponse(BaseModel):
    flags_updated: int
    strategies_updated: int

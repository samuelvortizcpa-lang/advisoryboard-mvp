from __future__ import annotations

from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


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
    status: str = Field(..., max_length=50)
    notes: Optional[str] = Field(None, max_length=5000)
    estimated_impact: Optional[float] = None


class BulkStatusItem(BaseModel):
    strategy_id: UUID
    tax_year: int
    status: str = Field(..., max_length=50)
    notes: Optional[str] = Field(None, max_length=5000)
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


# ─── Strategy dashboard ──────────────────────────────────────────────────────


class StrategyOverview(BaseModel):
    total_clients: int
    clients_reviewed: int
    clients_unreviewed: int
    total_implemented: int
    total_estimated_impact: float


class ClientStrategySummary(BaseModel):
    client_id: UUID
    client_name: str
    client_type: Optional[str] = None
    active_flags: list[str]
    total_applicable: int
    total_reviewed: int
    total_implemented: int
    total_estimated_impact: float
    coverage_pct: float
    last_reviewed_at: Optional[str] = None


class StrategyAdoption(BaseModel):
    strategy_id: UUID
    strategy_name: str
    category: str
    total_applicable: int
    total_implemented: int
    total_recommended: int
    total_declined: int
    adoption_rate: float


class UnreviewedAlert(BaseModel):
    client_id: UUID
    client_name: str
    strategy_id: UUID
    strategy_name: str
    category: str


# ─── Strategy report ─────────────────────────────────────────────────────────


class ReportRequest(BaseModel):
    year: Optional[int] = None
    include_prior_years: bool = True


# ─── Implementation tasks ───────────────────────────────────────────────────


class StrategyImplementationTaskResponse(BaseModel):
    id: UUID
    strategy_id: UUID
    task_name: str
    description: Optional[str] = None
    default_owner_role: str
    default_owner_external_label: Optional[str] = None
    default_lead_days: int
    required_documents: list[dict] = []
    display_order: int
    is_active: bool

    class Config:
        from_attributes = True


class TaskProgressItem(BaseModel):
    id: UUID
    task_name: str
    owner_role: str
    owner_external_label: Optional[str] = None
    status: str
    due_date: Optional[date] = None
    completed_at: Optional[str] = None
    display_order: int


class OwnerRoleBreakdown(BaseModel):
    total: int
    completed: int


class ImplementationProgressResponse(BaseModel):
    total: int
    completed: int
    by_owner_role: dict[str, OwnerRoleBreakdown]
    tasks: list[TaskProgressItem]


class RegenerateTasksResponse(BaseModel):
    new_tasks_created: int
    message: str


class ArchiveTasksResponse(BaseModel):
    archived_count: int
    message: str

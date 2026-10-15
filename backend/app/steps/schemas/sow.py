"""Statement of Work Gemini and stored schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.steps.schemas.estimate import PHASE_ORDER

PhaseKey = Literal["mvp", "phase_1", "phase_2", "phase_3", "future_scope"]
BasisKind = Literal["stated_in_source", "assumed_not_in_source"]


class PhaseDescriptionItem(BaseModel):
    phase: PhaseKey = Field(..., description="Phase key from the provided list.")
    description: str = Field(..., description="Client-facing scope for this phase.", max_length=2000)


class OutOfScopeItem(BaseModel):
    item: str = Field(..., max_length=400)
    rationale: str = Field(..., max_length=800)


class DeliverableItem(BaseModel):
    bundle_key: str = Field(..., description="Exact bundle key from the provided list.", max_length=120)
    title: str = Field(..., max_length=200)
    description: str = Field(..., max_length=2000)
    acceptance_criteria: list[str] = Field(..., description="Testable criteria derived from features.")


class MilestoneItem(BaseModel):
    name: str = Field(..., max_length=200)
    phase: PhaseKey = Field(..., description="Phase this milestone closes.")
    description: str = Field(..., max_length=1200)
    completion_criteria: str = Field(..., max_length=800)


class TeamRoleItem(BaseModel):
    role: str = Field(..., description="Exact role name from the provided team list.", max_length=40)
    responsibilities: list[str] = Field(..., description="Bullets describing responsibilities.")


class ClientResponsibilityItem(BaseModel):
    responsibility: str = Field(..., max_length=600)
    needed_by: str = Field(..., description="When or by which milestone this is needed.", max_length=300)
    linked_gap_ref: str | None = Field(default=None, max_length=16)


class AssumptionItem(BaseModel):
    statement: str = Field(..., max_length=800)
    basis: BasisKind = Field(..., description="Whether stated in client material or assumed.")
    linked_gap_ref: str | None = Field(default=None, max_length=16)


class RiskItem(BaseModel):
    risk: str = Field(..., max_length=500)
    impact: str = Field(..., max_length=500)
    mitigation: str = Field(..., max_length=800)


class GlossaryItem(BaseModel):
    term: str = Field(..., max_length=80)
    definition: str = Field(..., max_length=400)


class SowNarrativeOutput(BaseModel):
    document_title: str = Field(..., max_length=300)
    purpose: str = Field(..., max_length=4000)
    background: str = Field(..., max_length=4000)
    objectives: list[str] = Field(..., description="Business objectives.")
    success_criteria: list[str] = Field(..., description="Measurable success criteria.")
    scope_overview: str = Field(..., max_length=4000)
    phase_descriptions: list[PhaseDescriptionItem] = Field(default_factory=list)
    out_of_scope: list[OutOfScopeItem] = Field(default_factory=list)
    deliverables: list[DeliverableItem] = Field(default_factory=list)
    approach: str = Field(..., max_length=4000)
    quality_approach: str = Field(..., max_length=3000)
    milestones: list[MilestoneItem] = Field(default_factory=list)
    team_roles: list[TeamRoleItem] = Field(default_factory=list)
    client_responsibilities: list[ClientResponsibilityItem] = Field(default_factory=list)
    assumptions: list[AssumptionItem] = Field(default_factory=list)
    constraints_and_dependencies: list[str] = Field(default_factory=list)
    risks: list[RiskItem] = Field(default_factory=list)
    glossary: list[GlossaryItem] = Field(default_factory=list)


class SowDeliverablesRepairOutput(BaseModel):
    deliverables: list[DeliverableItem] = Field(..., description="Missing bundle deliverables only.")


class ScopeBundleItem(BaseModel):
    bundle_key: str
    kind: str
    phase: str
    component: str
    title: str
    feature_ids: list[str] = Field(default_factory=list)
    feature_titles: list[str] = Field(default_factory=list)


class TimelineRow(BaseModel):
    phase: str
    planned_weeks: float
    start_week: float
    end_week: float
    indicative_start: str | None = None
    indicative_end: str | None = None


class CommercialsBlock(BaseModel):
    pricing_model: str
    pricing_model_label: str
    total_fee: float | None = None
    currency: str | None = None
    fee_display: str
    payment_rows: list[dict[str, Any]] = Field(default_factory=list)


class PlaceholderItem(BaseModel):
    placeholder_id: str
    location: str
    label: str


class NumericClaimWarning(BaseModel):
    path: str
    label: str
    snippet: str


class SowViewerMeta(BaseModel):
    placeholder_count: int = 0
    placeholders: list[PlaceholderItem] = Field(default_factory=list)
    numeric_claim_warnings: list[NumericClaimWarning] = Field(default_factory=list)


class SowAssembled(BaseModel):
    standard_terms_version: str
    document_reference: str
    issue_date: str
    status_text: str
    bundle_keys: list[str] = Field(default_factory=list)
    scope_bundles: list[ScopeBundleItem] = Field(default_factory=list)
    timeline_table: list[TimelineRow] = Field(default_factory=list)
    total_weeks: float = 0.0
    total_months: float = 0.0
    optional_items: list[dict[str, str]] = Field(default_factory=list)
    future_scope_items: list[dict[str, str]] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)
    delivery_team: list[dict[str, Any]] = Field(default_factory=list)
    effort_by_phase_component: list[dict[str, Any]] = Field(default_factory=list)
    commercials: CommercialsBlock
    standard_terms: dict[str, Any] = Field(default_factory=dict)
    appendix_a: list[dict[str, str]] = Field(default_factory=list)
    appendix_b: list[dict[str, str]] = Field(default_factory=list)
    appendix_c: list[dict[str, str]] = Field(default_factory=list)
    allowed_numbers: list[str] = Field(default_factory=list)
    placeholders: list[PlaceholderItem] = Field(default_factory=list)
    contents_list: list[str] = Field(default_factory=list)


class StoredDeliverableItem(DeliverableItem):
    default_deliverable: bool = False


class StoredMilestoneItem(MilestoneItem):
    code_added: bool = False


class StoredTeamRoleItem(TeamRoleItem):
    code_added: bool = False


class SowNarrativeStored(BaseModel):
    document_title: str
    purpose: str
    background: str
    objectives: list[str]
    success_criteria: list[str]
    scope_overview: str
    phase_descriptions: list[PhaseDescriptionItem]
    out_of_scope: list[OutOfScopeItem]
    deliverables: list[StoredDeliverableItem]
    approach: str
    quality_approach: str
    milestones: list[StoredMilestoneItem]
    team_roles: list[StoredTeamRoleItem]
    client_responsibilities: list[ClientResponsibilityItem]
    assumptions: list[AssumptionItem]
    constraints_and_dependencies: list[str]
    risks: list[RiskItem]
    glossary: list[GlossaryItem]


class SowStored(BaseModel):
    schema_version: int = 1
    narrative: SowNarrativeStored
    assembled: SowAssembled
    viewer: SowViewerMeta = Field(default_factory=SowViewerMeta)


COMMITTED_PHASES: tuple[str, ...] = tuple(p for p in PHASE_ORDER if p != "future_scope")

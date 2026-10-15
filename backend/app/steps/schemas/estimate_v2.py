"""Estimate v2 Gemini and stored schemas.

Gemini-safe: flat shape, Literal enums, list caps in code.
Planning and batch schemas are what the model returns; ``EstimateV2Stored``
is persisted after post-processing. ``schema_version`` is set in code, not by
the model.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.steps.schemas.estimate import PHASE_ORDER, PRIORITY_DEFAULT_PHASE
from app.steps.schemas.feature_list import PrimaryRiskDomain

PhaseKey = Literal["mvp", "phase_1", "phase_2", "phase_3", "future_scope"]
Confidence = Literal["high", "medium", "low"]
AiLeverage = Literal["high", "medium", "low", "none"]
Complexity = Literal["S", "M", "L", "XL"]
EffortImpact = Literal["low", "medium", "high"]
BasisKind = Literal["source", "assumed_not_in_source"]
Discipline = Literal["development", "qa", "design", "management", "devops", "other"]
DomainExperience = Literal["built_similar_before", "some_experience", "new_to_us"]
TaskKind = Literal[
    "backend_api",
    "database",
    "web_ui",
    "mobile_ui",
    "admin_config_ui",
    "validation",
    "notifications",
    "integration",
    "tests",
    "error_edge_handling",
    "qa_testing",
    "design",
    "devops",
    "other",
]
PackageType = Literal[
    "project_setup_architecture",
    "cicd_environments",
    "data_migration",
    "third_party_integration_setup",
    "uat_support",
    "deployment",
    "documentation_training",
    "stabilization",
    "hypercare",
    "other",
]

REQUIRED_PACKAGE_TYPES: tuple[str, ...] = (
    "project_setup_architecture",
    "cicd_environments",
    "uat_support",
    "deployment",
    "documentation_training",
    "stabilization",
    "hypercare",
)

RISK_CONFIDENCE_CAP_DOMAINS: frozenset[str] = frozenset(
    {"offline_sync", "hardware", "payments"}
)

__all__ = [
    "PHASE_ORDER",
    "PRIORITY_DEFAULT_PHASE",
    "REQUIRED_PACKAGE_TYPES",
    "RISK_CONFIDENCE_CAP_DOMAINS",
    "AddedItemV2",
    "AiLeverage",
    "AssumptionItemV2",
    "BasisKind",
    "Complexity",
    "ComponentItemV2",
    "Confidence",
    "Discipline",
    "DomainExperience",
    "EffortLineV2",
    "EstimateBatchOutput",
    "EstimatePlanningOutput",
    "EstimateRepairPackagesOutput",
    "EstimateV2Merged",
    "EstimateV2Stored",
    "FeatureEstimateItemV2",
    "PackageType",
    "PhaseItemV2",
    "PhaseKey",
    "PrimaryRiskDomain",
    "StoredAddedItemV2",
    "StoredFeatureEstimateV2",
    "StoredWorkPackageV2",
    "TaskKind",
    "WorkPackageItemV2",
]


class ComponentItemV2(BaseModel):
    name: str = Field(..., description="Short component name reused on features.", max_length=80)
    description: str = Field(..., description="What this component covers.", max_length=600)
    screens: int = Field(
        default=1,
        description="Count of distinct screens or surfaces in this component.",
        ge=0,
        le=200,
    )


class PhaseItemV2(BaseModel):
    key: PhaseKey = Field(..., description="Phase key from the selected set.")
    goal: str = Field(..., description="What this phase delivers.", max_length=800)
    scope_rationale: str = Field(
        ..., description="Why these items belong in this phase.", max_length=800
    )


class AssumptionItemV2(BaseModel):
    gap_ref: str | None = Field(
        default=None,
        description='Gap ref from Gap Analysis, like "G-3", or omit if not from a gap.',
        max_length=16,
    )
    topic: str = Field(..., description="What was decided.", max_length=200)
    solution: str = Field(..., description="The practical solution being estimated.", max_length=1200)
    rationale: str = Field(..., description="Why this solution is the best practical choice.", max_length=1200)
    effort_impact: EffortImpact = Field(..., description="How much this choice affects effort.")
    alternatives: str = Field(..., description="Other options considered.", max_length=800)
    confirm_with_client: str = Field(
        ..., description="What to confirm with the client.", max_length=500
    )
    basis: BasisKind = Field(
        default="assumed_not_in_source",
        description="source if stated in client material; assumed_not_in_source otherwise.",
    )


class FeatureEstimateItemV2(BaseModel):
    feature_id: str = Field(..., description='Feature id from the Feature List, like "F-001".', max_length=16)
    phase: PhaseKey = Field(..., description="Delivery phase for this feature.")
    component: str = Field(..., description="Exact component name from components[].", max_length=80)
    confidence: Confidence = Field(..., description="Estimate confidence.")
    confidence_reason: str = Field(
        ...,
        description="Why this confidence level applies; high only if the work is fully specified.",
        max_length=600,
    )
    ai_leverage: AiLeverage = Field(
        ...,
        description="How much AI coding tools can reduce implementation time for this item.",
    )
    complexity: Complexity = Field(..., description="Relative size.")
    basis: BasisKind = Field(
        ...,
        description="source if the work is stated; assumed_not_in_source if inferred.",
    )
    primary_risk_domain: PrimaryRiskDomain = Field(
        default="none",
        description="Main risk domain, copied from the Feature List unless clearly wrong.",
    )


class AddedItemV2(BaseModel):
    id: str = Field(..., description='Added item id like "X-1".', max_length=16)
    title: str = Field(..., description="Short title.", max_length=200)
    description: str = Field(..., description="What this implied or supporting work covers.", max_length=1200)
    phase: PhaseKey = Field(..., description="Delivery phase.")
    component: str = Field(..., description="Exact component name from components[].", max_length=80)
    confidence: Confidence = Field(..., description="Estimate confidence.")
    confidence_reason: str = Field(..., description="Why this confidence level applies.", max_length=600)
    ai_leverage: AiLeverage = Field(..., description="AI leverage for this item.")
    complexity: Complexity = Field(..., description="Relative size.")
    primary_risk_domain: PrimaryRiskDomain = Field(default="none", description="Main risk domain.")
    reason: str = Field(..., description="Why this was added beyond the Feature List.", max_length=600)


class WorkPackageItemV2(BaseModel):
    id: str = Field(..., description='Work package id like "W-1".', max_length=16)
    package_type: PackageType = Field(..., description="Required or supporting package type.")
    title: str = Field(..., description="Short title.", max_length=200)
    description: str = Field(..., description="What this package covers.", max_length=1200)
    phase: PhaseKey = Field(..., description="Delivery phase.")
    component: str = Field(..., description="Exact component name from components[].", max_length=80)
    confidence: Confidence = Field(..., description="Estimate confidence.")
    ai_leverage: AiLeverage = Field(..., description="AI leverage for this package.")
    lead_time_weeks: float = Field(
        default=0,
        description="Calendar lead time in weeks that cannot be compressed by more people.",
        ge=0,
        le=52,
    )


class EffortLineV2(BaseModel):
    item_id: str = Field(
        ...,
        description="Feature id (F-001), added item id (X-1) or work package id (W-1).",
        max_length=16,
    )
    role: str = Field(..., description="Exact estimated role name from the team list.", max_length=40)
    task: TaskKind = Field(..., description="Kind of work this line covers.")
    best_hours: float = Field(..., description="Optimistic hours without AI for a mid-level engineer.")
    likely_hours: float = Field(..., description="Most likely hours without AI for a mid-level engineer.")
    worst_hours: float = Field(..., description="Pessimistic hours without AI for a mid-level engineer.")


class EstimatePlanningOutput(BaseModel):
    summary: str = Field(..., description="Brief overview of the estimate.", max_length=4000)
    approach: str = Field(
        ...,
        description="Overall solution approach and key technical assumptions.",
        max_length=4000,
    )
    components: list[ComponentItemV2] = Field(..., description="Delivery components (at most 10).")
    phases: list[PhaseItemV2] = Field(..., description="Selected phases with goals.")
    assumptions_and_solutions: list[AssumptionItemV2] = Field(
        ..., description="Solutions used where gaps remain."
    )
    exclusions: list[str] = Field(..., description="Items not included in this estimate.")
    work_packages: list[WorkPackageItemV2] = Field(
        ..., description="Cross-cutting packages including the required types."
    )


class EstimateBatchOutput(BaseModel):
    feature_estimates: list[FeatureEstimateItemV2] = Field(
        ..., description="One row per Feature List id in this batch."
    )
    added_items: list[AddedItemV2] = Field(
        default_factory=list,
        description="Implied or supporting items discovered while estimating this batch.",
    )
    effort_lines: list[EffortLineV2] = Field(
        ...,
        description="Task-level hour ranges for this batch's features, added items and listed packages.",
    )


class EstimateRepairPackagesOutput(BaseModel):
    work_packages: list[WorkPackageItemV2] = Field(
        ..., description="Packages for the missing required types only."
    )
    effort_lines: list[EffortLineV2] = Field(
        ..., description="Hour ranges for those packages only."
    )


class EstimateV2Merged(BaseModel):
    """Internal merge of planning + batches; not sent to Gemini."""

    summary: str
    approach: str
    components: list[ComponentItemV2]
    phases: list[PhaseItemV2]
    assumptions_and_solutions: list[AssumptionItemV2]
    exclusions: list[str]
    feature_estimates: list[FeatureEstimateItemV2]
    added_items: list[AddedItemV2] = Field(default_factory=list)
    work_packages: list[WorkPackageItemV2]
    effort_lines: list[EffortLineV2]


class StoredFeatureEstimateV2(FeatureEstimateItemV2):
    title: str = Field(..., description="Title joined from the Feature List.")
    not_estimated: bool = Field(default=False, description="True when hours could not be produced.")
    priority: str = Field(default="must", description="MoSCoW priority from the Feature List.")
    origin: str = Field(default="stated", description="Feature origin from the Feature List.")
    confidence_raw: Confidence = Field(default="medium", description="Model confidence before guardrails.")
    ai_leverage_raw: AiLeverage = Field(default="none", description="Model leverage before guardrails.")
    guardrail_codes: list[str] = Field(default_factory=list)


class StoredAddedItemV2(AddedItemV2):
    confidence_raw: Confidence = Field(default="medium")
    ai_leverage_raw: AiLeverage = Field(default="none")
    guardrail_codes: list[str] = Field(default_factory=list)


class StoredWorkPackageV2(WorkPackageItemV2):
    default_allowance: bool = Field(
        default=False, description="True when hours were filled as a default allowance."
    )
    confidence_raw: Confidence = Field(default="medium")
    ai_leverage_raw: AiLeverage = Field(default="none")
    guardrail_codes: list[str] = Field(default_factory=list)


class EstimateV2Stored(BaseModel):
    schema_version: int = 2
    summary: str
    approach: str
    components: list[ComponentItemV2]
    phases: list[PhaseItemV2]
    assumptions_and_solutions: list[AssumptionItemV2]
    exclusions: list[str]
    feature_estimates: list[StoredFeatureEstimateV2]
    added_items: list[StoredAddedItemV2] = Field(default_factory=list)
    work_packages: list[StoredWorkPackageV2]
    effort_lines: list[EffortLineV2]
    computed: dict[str, Any] = Field(default_factory=dict)

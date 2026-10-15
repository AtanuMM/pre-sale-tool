"""Estimate output schema (plan section 9.4).

Gemini-safe: flat shape, enums via Literal, list caps enforced in code.
``EstimateOutput`` is what the model returns; ``EstimateStored`` is persisted
after post-processing (titles, flags, computed totals).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

PhaseKey = Literal["mvp", "phase_1", "phase_2", "phase_3", "future_scope"]
Confidence = Literal["high", "medium", "low"]
AiLeverage = Literal["high", "medium", "low"]
Complexity = Literal["S", "M", "L", "XL"]
EffortImpact = Literal["low", "medium", "high"]

PHASE_ORDER: tuple[str, ...] = (
    "mvp",
    "phase_1",
    "phase_2",
    "phase_3",
    "future_scope",
)
PRIORITY_DEFAULT_PHASE: dict[str, str] = {
    "must": "mvp",
    "should": "phase_1",
    "could": "phase_2",
    "wont": "future_scope",
}


class ComponentItem(BaseModel):
    name: str = Field(..., description="Short component name reused on features.", max_length=80)
    description: str = Field(..., description="What this component covers.", max_length=600)


class PhaseItem(BaseModel):
    key: PhaseKey = Field(..., description="Phase key from the selected set.")
    goal: str = Field(..., description="What this phase delivers.", max_length=800)
    scope_rationale: str = Field(
        ..., description="Why these items belong in this phase.", max_length=800
    )


class AssumptionItem(BaseModel):
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


class FeatureEstimateItem(BaseModel):
    feature_id: str = Field(..., description='Feature id from the Feature List, like "F-001".', max_length=16)
    phase: PhaseKey = Field(..., description="Delivery phase for this feature.")
    component: str = Field(..., description="Exact component name from components[].", max_length=80)
    confidence: Confidence = Field(..., description="Estimate confidence.")
    ai_leverage: AiLeverage = Field(
        ...,
        description="How much AI coding tools can reduce implementation time for this item.",
    )
    complexity: Complexity = Field(..., description="Relative size.")
    basis: str = Field(
        ...,
        description="Short justification of the base hours.",
        max_length=600,
    )


class WorkPackageItem(BaseModel):
    id: str = Field(..., description='Work package id like "W-1".', max_length=16)
    title: str = Field(..., description="Short title.", max_length=200)
    description: str = Field(..., description="What this package covers.", max_length=1200)
    phase: PhaseKey = Field(..., description="Delivery phase.")
    component: str = Field(..., description="Exact component name from components[].", max_length=80)
    confidence: Confidence = Field(..., description="Estimate confidence.")
    ai_leverage: AiLeverage = Field(..., description="AI leverage for this package.")


class EffortLine(BaseModel):
    item_id: str = Field(
        ...,
        description="Feature id (F-001) or work package id (W-1) this line belongs to.",
        max_length=16,
    )
    role: str = Field(..., description="Exact estimated role name from the team list.", max_length=40)
    base_hours: float = Field(
        ...,
        description="Base hours without AI tools for a competent mid-level engineer.",
    )


class EstimateOutput(BaseModel):
    summary: str = Field(..., description="Brief overview of the estimate.", max_length=4000)
    approach: str = Field(
        ...,
        description="Overall solution approach and key technical assumptions.",
        max_length=4000,
    )
    components: list[ComponentItem] = Field(..., description="Delivery components (at most 10).")
    phases: list[PhaseItem] = Field(..., description="Selected phases with goals.")
    assumptions_and_solutions: list[AssumptionItem] = Field(
        ..., description="Solutions used where gaps remain."
    )
    exclusions: list[str] = Field(..., description="Items not included in this estimate.")
    feature_estimates: list[FeatureEstimateItem] = Field(
        ..., description="One row per Feature List id."
    )
    work_packages: list[WorkPackageItem] = Field(
        ..., description="Cross-cutting packages beyond individual features."
    )
    effort_lines: list[EffortLine] = Field(
        ...,
        description="Sparse base hours: one row per item and estimated role; omit zeros.",
    )


class StoredFeatureEstimate(FeatureEstimateItem):
    title: str = Field(..., description="Title joined from the Feature List.")
    not_estimated: bool = Field(
        default=False, description="True when hours could not be produced."
    )


class EstimateStored(BaseModel):
    summary: str
    approach: str
    components: list[ComponentItem]
    phases: list[PhaseItem]
    assumptions_and_solutions: list[AssumptionItem]
    exclusions: list[str]
    feature_estimates: list[StoredFeatureEstimate]
    work_packages: list[WorkPackageItem]
    effort_lines: list[EffortLine]
    computed: dict[str, Any] = Field(default_factory=dict)


class EstimateRepairOutput(BaseModel):
    feature_estimates: list[FeatureEstimateItem] = Field(
        ..., description="Estimates for the missing feature ids only."
    )
    assumptions_and_solutions: list[AssumptionItem] = Field(
        ..., description="Assumptions for the listed high/medium gaps."
    )
    work_packages: list[WorkPackageItem] = Field(
        default_factory=list, description="Optional extra packages; usually empty."
    )
    effort_lines: list[EffortLine] = Field(
        ..., description="Base hours for the new items only."
    )

"""Feature List output schema (plan section 9.3).

Gemini-safe: flat shape (root -> features[] -> scalars / arrays of scalars),
enums via Literal, list caps enforced in code rather than the JSON schema.
``FeatureListOutput`` is what the model returns; ``FeatureListStored`` is what
we persist after post-processing (adds ids, resolved dependencies and stats).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Platform = Literal["web", "mobile", "admin", "api", "background"]
Priority = Literal["must", "should", "could", "wont"]
Origin = Literal["stated", "implied", "suggested"]
PrimaryRiskDomain = Literal[
    "payments",
    "offline_sync",
    "hardware",
    "security",
    "compliance",
    "concurrency",
    "state_machine",
    "data_migration",
    "none",
]

PRIORITY_ORDER: tuple[str, ...] = ("must", "should", "could", "wont")
ORIGIN_ORDER: tuple[str, ...] = ("stated", "implied", "suggested")


class ModuleItem(BaseModel):
    name: str = Field(..., description="Short module name.", max_length=120)
    purpose: str = Field(
        ..., description="One or two sentences on what the module is for.", max_length=600
    )


class FeatureItem(BaseModel):
    ref: int = Field(
        ...,
        description="Position of this feature in the list, starting at 1 (1, 2, 3 ...).",
    )
    module: str = Field(
        ..., description="Exact name of the module this feature belongs to.", max_length=120
    )
    title: str = Field(..., description="Short feature title.", max_length=200)
    description: str = Field(
        ...,
        description=(
            "What the feature does for the user; mention the default assumption used "
            "when an unresolved gap applies."
        ),
        max_length=1500,
    )
    platforms: list[Platform] = Field(
        ..., description="Platforms or actors the feature is delivered on."
    )
    priority: Priority = Field(..., description="MoSCoW priority.")
    origin: Origin = Field(
        ...,
        description=(
            "stated: explicit in client material; implied: necessary for stated "
            "features; suggested: recommended addition."
        ),
    )
    depends_on_refs: list[int] = Field(
        ..., description="Refs of features this feature depends on (empty if none)."
    )
    linked_gap_refs: list[str] = Field(
        ..., description='Gap refs from the Gap Analysis, like "G-3" (empty if none).'
    )
    linked_assumption_refs: list[str] = Field(
        ...,
        description='Assumption refs from the Scope Analysis, like "A-2" (empty if none).',
    )
    source_requirement_ids: list[str] = Field(
        default_factory=list,
        description="Distinct source requirement ids this feature traces to.",
    )
    source_priority: str = Field(
        default="not specified",
        description='Client priority tag as written, or "not specified".',
        max_length=40,
    )
    primary_risk_domain: PrimaryRiskDomain = Field(
        default="none",
        description="Main risk domain for this feature, or none.",
    )


class FeatureListWarning(BaseModel):
    code: str
    count: int
    label: str


class FeatureListOutput(BaseModel):
    summary: str = Field(
        ..., description="Brief overview of the solution broken into modules.", max_length=4000
    )
    modules: list[ModuleItem] = Field(..., description="Modules grouping the features.")
    features: list[FeatureItem] = Field(..., description="Features, small enough to estimate.")
    coverage_notes: str = Field(
        ...,
        description=(
            "What could not be broken down because information is missing, and why."
        ),
        max_length=3000,
    )
    source_requirements_total: int = Field(
        default=0,
        description="Count of distinct source requirement rows, or 0 if unknown.",
    )


class StoredFeatureItem(FeatureItem):
    id: str = Field(..., description="Stable id assigned in code, e.g. F-001.")
    depends_on_ids: list[str] = Field(
        default_factory=list, description="Resolved dependency ids (acyclic)."
    )


class FeatureListStats(BaseModel):
    by_priority: dict[str, int] = Field(default_factory=dict)
    by_origin: dict[str, int] = Field(default_factory=dict)
    by_module: dict[str, int] = Field(default_factory=dict)


class FeatureListStored(BaseModel):
    summary: str
    modules: list[ModuleItem]
    features: list[StoredFeatureItem]
    coverage_notes: str
    stats: FeatureListStats
    source_requirements_total: int = 0
    warnings: list[FeatureListWarning] = Field(default_factory=list)

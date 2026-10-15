"""Sprint Plan pass outputs and stored content."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

SprintTypeStored = Literal["sprint_zero", "sprint", "hardening", "hypercare"]


class EpicItem(BaseModel):
    module: str = Field(..., max_length=120)
    name: str = Field(..., max_length=200)
    goal: str = Field(..., max_length=2000)


class ReleaseExitCriteriaItem(BaseModel):
    phase: str = Field(..., max_length=32)
    criteria: list[str] = Field(default_factory=list, max_length=8)


class RiskItem(BaseModel):
    risk: str = Field(..., max_length=500)
    impact: str = Field(..., max_length=500)
    mitigation: str = Field(..., max_length=500)
    gap_ref: str = Field(..., max_length=16)


class LeadTimeActionItem(BaseModel):
    action: str = Field(..., max_length=500)
    owner_role: str = Field(..., max_length=80)
    needed_by_phase: str = Field(..., max_length=32)


class GlossaryItem(BaseModel):
    term: str = Field(..., max_length=120)
    definition: str = Field(..., max_length=500)


class SprintPlanPlanningPassAOutput(BaseModel):
    """Gemini-safe planning pass (no risks — combined with pass B in one response breaks schema limits)."""

    epics: list[EpicItem] = Field(default_factory=list, max_length=40)
    definition_of_ready_additions: list[str] = Field(default_factory=list, max_length=20)
    definition_of_done_additions: list[str] = Field(default_factory=list, max_length=20)
    release_exit_criteria: list[ReleaseExitCriteriaItem] = Field(default_factory=list, max_length=8)
    dependencies: list[str] = Field(default_factory=list, max_length=40)
    assumptions: list[str] = Field(default_factory=list, max_length=30)


class SprintPlanPlanningPassBRisksLeadOutput(BaseModel):
    """Gemini-safe: risks + lead-time actions only (adding glossary in one schema fails validation)."""

    risks: list[RiskItem] = Field(default_factory=list, max_length=30)
    lead_time_actions: list[LeadTimeActionItem] = Field(default_factory=list, max_length=30)


class SprintPlanPlanningGlossaryOutput(BaseModel):
    glossary: list[GlossaryItem] = Field(default_factory=list, max_length=40)


class SprintPlanPlanningPassBOutput(BaseModel):
    """Merged planning pass B (two LLM calls)."""

    risks: list[RiskItem] = Field(default_factory=list, max_length=30)
    lead_time_actions: list[LeadTimeActionItem] = Field(default_factory=list, max_length=30)
    glossary: list[GlossaryItem] = Field(default_factory=list, max_length=40)


# Legacy name for imports/tests
SprintPlanPlanningOutput = SprintPlanPlanningPassAOutput


class StoryDraftItem(BaseModel):
    feature_id: str = Field(..., max_length=32)
    title: str = Field(..., max_length=90)
    story_statement: str = Field(..., max_length=500)
    acceptance_criteria: list[str] = Field(..., min_length=1, max_length=5)
    share_percent: int = Field(..., ge=5, le=100)
    is_spike: bool = False
    depends_on_previous: bool = False
    linked_requirement_ids: list[str] = Field(default_factory=list, max_length=20)


class SprintPlanModuleStoriesBatchOutput(BaseModel):
    """Single Gemini response (at most 10 stories per call)."""

    module: str = Field(..., max_length=120)
    stories: list[StoryDraftItem] = Field(default_factory=list, max_length=10)


class SprintPlanModuleStoriesOutput(BaseModel):
    """Merged stories for one module across batches."""

    module: str = Field(..., max_length=120)
    stories: list[StoryDraftItem] = Field(default_factory=list)


class SprintGoalItem(BaseModel):
    sprint_number: int = Field(..., ge=0)
    goal: str = Field(..., max_length=800)
    demo_focus: str = Field(..., max_length=400)


class ReleaseSummaryItem(BaseModel):
    phase: str = Field(..., max_length=32)
    summary: str = Field(..., max_length=2000)


class SprintPlanGoalsOutput(BaseModel):
    sprint_goals: list[SprintGoalItem] = Field(default_factory=list, max_length=30)
    release_summaries: list[ReleaseSummaryItem] = Field(default_factory=list, max_length=8)
    executive_summary: str = Field(default="", max_length=4000)


class SprintPlanRepairOutput(BaseModel):
    extra_stories: list[StoryDraftItem] = Field(default_factory=list, max_length=10)
    linked_requirement_ids: list[str] = Field(default_factory=list, max_length=50)


class StoredStory(BaseModel):
    id: str
    feature_id: str
    epic_id: str | None = None
    title: str
    story_statement: str
    acceptance_criteria: list[str]
    is_spike: bool = False
    linked_requirement_ids: list[str] = Field(default_factory=list)
    hours_by_role: dict[str, float] = Field(default_factory=dict)
    story_points: int | None = None
    sprint_number: int | None = None


class SprintPlanAssembled(BaseModel):
    document_reference: str = ""
    schedule_sprints: list[dict[str, Any]] = Field(default_factory=list)
    releases: list[dict[str, Any]] = Field(default_factory=list)
    ceremonies: list[dict[str, str]] = Field(default_factory=list)
    definition_of_ready: list[str] = Field(default_factory=list)
    definition_of_done: list[str] = Field(default_factory=list)
    traceability: list[dict[str, str]] = Field(default_factory=list)
    feature_traceability: list[dict[str, str]] = Field(default_factory=list)
    unscheduled_backlog: list[dict[str, str]] = Field(default_factory=list)
    lead_time_actions: list[dict[str, str]] = Field(default_factory=list)
    comparison: dict[str, float | str] = Field(default_factory=dict)
    placeholders: list[str] = Field(default_factory=list)
    diagram_specs: dict[str, dict[str, Any]] = Field(default_factory=dict)
    epics: list[dict[str, str]] = Field(default_factory=list)


class SprintPlanHealthMeta(BaseModel):
    health_rows: list[dict[str, Any]] = Field(default_factory=list)
    comparison: dict[str, Any] = Field(default_factory=dict)


class SprintPlanPasses(BaseModel):
    planning_a: SprintPlanPlanningPassAOutput | None = None
    planning_b: SprintPlanPlanningPassBOutput | None = None
    module_stories: dict[str, SprintPlanModuleStoriesOutput] = Field(default_factory=dict)
    goals: SprintPlanGoalsOutput | None = None
    repair: SprintPlanRepairOutput | None = None


class SprintPlanStored(BaseModel):
    schema_version: int = 1
    passes: SprintPlanPasses
    stories: list[StoredStory] = Field(default_factory=list)
    assembled: SprintPlanAssembled
    viewer: SprintPlanHealthMeta = Field(default_factory=SprintPlanHealthMeta)

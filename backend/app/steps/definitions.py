from __future__ import annotations

from dataclasses import dataclass
from typing import TypeVar

from pydantic import BaseModel

from app.steps.estimate_inputs import ESTIMATE_INPUT_FIELDS
from app.steps.input_fields import InputFieldSpec
from app.steps.layout_config import SectionLayoutSpec, validate_layout_against_schema
from app.steps.layouts_registry import (
    ESTIMATE_V2_LAYOUT,
    FEATURE_LIST_LAYOUT,
    GAP_ANALYSIS_LAYOUT,
    SCOPE_ANALYSIS_LAYOUT,
    SOW_LAYOUT,
    FRS_LAYOUT,
    SPRINT_PLAN_LAYOUT,
    SRS_LAYOUT,
)
from app.steps.postprocess import PostprocessFn
from app.steps.postprocess.estimate_v2 import postprocess_estimate_v2
from app.steps.postprocess.feature_list import postprocess_feature_list
from app.steps.postprocess.gap_analysis import postprocess_gap_analysis
from app.steps.postprocess.sow import postprocess_sow
from app.steps.postprocess.frs import postprocess_frs
from app.steps.postprocess.sprint_plan import postprocess_sprint_plan
from app.steps.postprocess.srs import postprocess_srs
from app.steps.schema_gemini import (
    collect_forbidden_keywords,
    gemini_processed_schema_dict,
)
from app.steps.schemas.estimate_v2 import EstimatePlanningOutput, EstimateV2Stored
from app.steps.schemas.feature_list import FeatureListOutput, FeatureListStored
from app.steps.schemas.gap_analysis import GapAnalysisOutput
from app.steps.schemas.scope_analysis import ScopeAnalysisOutput
from app.steps.schemas.sow import SowNarrativeOutput, SowStored
from app.steps.schemas.frs import FrsPlanningPassAOutput, FrsStored
from app.steps.schemas.sprint_plan import SprintPlanPlanningPassAOutput, SprintPlanStored
from app.steps.schemas.srs import SrsPlanningPassAOutput, SrsStored
from app.steps.sow_inputs import SOW_INPUT_FIELDS
from app.steps.frs_inputs import FRS_INPUT_FIELDS
from app.steps.sprint_plan_inputs import SPRINT_PLAN_INPUT_FIELDS
from app.steps.srs_inputs import SRS_INPUT_FIELDS

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class SoftListCap:
    field: str
    settings_key: str | None = None
    limit: int = 0


@dataclass(frozen=True)
class StepDefinition:
    key: str
    title: str
    order: int
    depends_on: str | None
    output_schema: type[BaseModel] | None
    extra_inputs_schema: type[BaseModel] | None
    prompt_version: str | None
    implemented: bool
    context_steps: tuple[str, ...]
    layout: tuple[SectionLayoutSpec, ...]
    soft_list_caps: tuple[SoftListCap, ...]
    reads_description: str
    writes_description: str
    uses_scope_revise_prompt: bool = False
    # Shape persisted after post-processing; defaults to output_schema.
    stored_schema: type[BaseModel] | None = None
    postprocess: PostprocessFn | None = None
    input_fields: tuple[InputFieldSpec, ...] = ()
    export_formats: tuple[str, ...] = ("docx",)
    max_output_tokens: int | None = None
    supports_reassemble: bool = False

    @property
    def persisted_schema(self) -> type[BaseModel] | None:
        return self.stored_schema or self.output_schema


FEATURE_LIST_NOTES_FIELD = InputFieldSpec(
    key="team_notes",
    label="Notes and client answers (optional)",
    help_text=(
        "Paste client answers to the gap questions or decisions made since the intake. "
        "Used only for this step."
    ),
    kind="textarea",
    max_length=8000,
)


_STEPS: tuple[StepDefinition, ...] = (
    StepDefinition(
        key="scope_analysis",
        title="Scope Analysis",
        order=1,
        depends_on=None,
        output_schema=ScopeAnalysisOutput,
        extra_inputs_schema=None,
        prompt_version="v1",
        implemented=True,
        context_steps=(),
        layout=SCOPE_ANALYSIS_LAYOUT,
        soft_list_caps=(
            SoftListCap("ambiguities_and_questions", "SOFT_CAP_AMBIGUITIES"),
            SoftListCap("dependencies", "SOFT_CAP_DEPENDENCIES"),
            SoftListCap("assumptions", "SOFT_CAP_ASSUMPTIONS"),
        ),
        reads_description=(
            "Initial client message and attachment text (when extractable). "
            "Follow-up messages are not used yet."
        ),
        writes_description="Structured scope analysis for review and approval.",
        uses_scope_revise_prompt=True,
    ),
    StepDefinition(
        key="gap_analysis",
        title="Gap Analysis",
        order=2,
        depends_on="scope_analysis",
        output_schema=GapAnalysisOutput,
        extra_inputs_schema=None,
        prompt_version="v2",
        implemented=True,
        context_steps=("scope_analysis",),
        layout=GAP_ANALYSIS_LAYOUT,
        soft_list_caps=(
            SoftListCap("gaps", "SOFT_CAP_GAPS"),
            SoftListCap("client_questions", "SOFT_CAP_GAP_CLIENT_QUESTIONS"),
        ),
        reads_description=(
            "Initial client intake (same as step 1) and the approved Scope Analysis output."
        ),
        writes_description="Evidence-based gaps, severities, and consolidated client questions.",
        uses_scope_revise_prompt=False,
        postprocess=postprocess_gap_analysis,
        max_output_tokens=65_536,
    ),
    StepDefinition(
        key="feature_list",
        title="Feature List",
        order=3,
        depends_on="gap_analysis",
        output_schema=FeatureListOutput,
        extra_inputs_schema=None,
        prompt_version="v2",
        implemented=True,
        context_steps=("scope_analysis", "gap_analysis"),
        layout=FEATURE_LIST_LAYOUT,
        soft_list_caps=(SoftListCap("modules", "SOFT_CAP_FEATURE_MODULES"),),
        reads_description=(
            "Initial client intake, the approved Scope Analysis, the approved Gap Analysis, "
            "and optional notes or client answers you paste for this step."
        ),
        writes_description=(
            "Modules and features with MoSCoW priority, origin, dependencies, "
            "and links to gaps or assumptions."
        ),
        uses_scope_revise_prompt=False,
        stored_schema=FeatureListStored,
        postprocess=postprocess_feature_list,
        input_fields=(FEATURE_LIST_NOTES_FIELD,),
        max_output_tokens=65_536,
    ),
    StepDefinition(
        key="estimate",
        title="Estimate",
        order=4,
        depends_on="feature_list",
        output_schema=EstimatePlanningOutput,
        extra_inputs_schema=None,
        prompt_version="v2",
        implemented=True,
        context_steps=("scope_analysis", "gap_analysis", "feature_list"),
        layout=ESTIMATE_V2_LAYOUT,
        soft_list_caps=(
            SoftListCap("components", limit=10),
            SoftListCap("work_packages", "ESTIMATE_MAX_WORK_PACKAGES"),
            SoftListCap("assumptions_and_solutions", "ESTIMATE_MAX_ASSUMPTIONS"),
        ),
        reads_description=(
            "Initial client intake, the approved Scope Analysis, Gap Analysis and Feature List, "
            "plus the team, phases, domain experience and optional notes you enter for this step."
        ),
        writes_description=(
            "Task-level hour ranges by role, phases, components, assumptions and computed totals "
            "(best / likely / worst, hours with AI, recommended hours, weeks, cost)."
        ),
        uses_scope_revise_prompt=False,
        stored_schema=EstimateV2Stored,
        postprocess=postprocess_estimate_v2,
        input_fields=ESTIMATE_INPUT_FIELDS,
        export_formats=("docx", "xlsx", "csv"),
        max_output_tokens=65_536,
    ),
    StepDefinition(
        key="sow",
        title="Statement of Work",
        order=5,
        depends_on="estimate",
        output_schema=SowNarrativeOutput,
        extra_inputs_schema=None,
        prompt_version="v1",
        implemented=True,
        context_steps=("scope_analysis", "gap_analysis", "feature_list", "estimate"),
        layout=SOW_LAYOUT,
        soft_list_caps=(
            SoftListCap("objectives", "SOW_MAX_OBJECTIVES"),
            SoftListCap("success_criteria", "SOW_MAX_SUCCESS_CRITERIA"),
            SoftListCap("glossary", "SOW_MAX_GLOSSARY"),
            SoftListCap("milestones", "SOW_MAX_MILESTONES"),
        ),
        reads_description=(
            "Initial client intake and approved Scope Analysis, Gap Analysis, Feature List, "
            "and Estimate (client-safe projection), plus SOW inputs you enter for this step."
        ),
        writes_description=(
            "Client-facing Statement of Work narrative plus code-assembled timeline, "
            "commercials, standard terms and appendices."
        ),
        uses_scope_revise_prompt=False,
        stored_schema=SowStored,
        postprocess=postprocess_sow,
        input_fields=SOW_INPUT_FIELDS,
        export_formats=("docx",),
        max_output_tokens=65_536,
        supports_reassemble=True,
    ),
    StepDefinition(
        key="srs",
        title="Software Requirements Specification",
        order=6,
        depends_on="sow",
        output_schema=SrsPlanningPassAOutput,
        extra_inputs_schema=None,
        prompt_version="v1",
        implemented=True,
        context_steps=("scope_analysis", "gap_analysis", "feature_list", "estimate", "sow"),
        layout=SRS_LAYOUT,
        soft_list_caps=(),
        reads_description=(
            "Initial client intake and approved Scope Analysis, Gap Analysis, Feature List, "
            "Estimate (client-safe projection), Statement of Work, plus SRS inputs you enter."
        ),
        writes_description=(
            "ISO/IEC/IEEE 29148-style Software Requirements Specification with code-owned "
            "ids, traceability, diagrams, and exports."
        ),
        uses_scope_revise_prompt=False,
        stored_schema=SrsStored,
        postprocess=postprocess_srs,
        input_fields=SRS_INPUT_FIELDS,
        export_formats=("docx", "xlsx", "csv"),
        max_output_tokens=65_536,
    ),
    StepDefinition(
        key="sprint_plan",
        title="Sprint Plan",
        order=7,
        depends_on="srs",
        output_schema=SprintPlanPlanningPassAOutput,
        extra_inputs_schema=None,
        prompt_version="v1",
        implemented=True,
        context_steps=("scope_analysis", "gap_analysis", "feature_list", "estimate", "sow", "srs"),
        layout=SPRINT_PLAN_LAYOUT,
        soft_list_caps=(),
        reads_description=(
            "Approved Scope Analysis, Gap Analysis, Feature List, Estimate (qualitative projection), "
            "Statement of Work, Software Requirements Specification, plus sprint planning inputs."
        ),
        writes_description=(
            "Release and sprint plan with code-owned schedule, capacity, traceability, charts, and exports."
        ),
        uses_scope_revise_prompt=False,
        stored_schema=SprintPlanStored,
        postprocess=postprocess_sprint_plan,
        input_fields=SPRINT_PLAN_INPUT_FIELDS,
        export_formats=("docx", "xlsx", "csv"),
        max_output_tokens=65_536,
        supports_reassemble=True,
    ),
    StepDefinition(
        key="frs",
        title="Functional Requirements Specification",
        order=8,
        depends_on="sprint_plan",
        output_schema=FrsPlanningPassAOutput,
        extra_inputs_schema=None,
        prompt_version="v1",
        implemented=True,
        context_steps=(
            "scope_analysis",
            "gap_analysis",
            "feature_list",
            "estimate",
            "sow",
            "srs",
            "sprint_plan",
        ),
        layout=FRS_LAYOUT,
        soft_list_caps=(),
        reads_description=(
            "Approved Scope Analysis, Gap Analysis, Feature List, Estimate (client-safe), "
            "Statement of Work, Software Requirements Specification, Sprint Plan, plus FRS inputs."
        ),
        writes_description=(
            "Client-facing functional specifications with code-owned ids, traceability, "
            "catalogs, matrices, and exports."
        ),
        uses_scope_revise_prompt=False,
        stored_schema=FrsStored,
        postprocess=postprocess_frs,
        input_fields=FRS_INPUT_FIELDS,
        export_formats=("docx", "xlsx", "csv"),
        max_output_tokens=65_536,
    ),
)

_BY_KEY: dict[str, StepDefinition] = {s.key: s for s in _STEPS}
_BY_ORDER: dict[int, StepDefinition] = {s.order: s for s in _STEPS}


def _validate_registry() -> None:
    if len(_BY_KEY) != len(_STEPS):
        raise RuntimeError("Duplicate step keys in registry")
    orders = sorted(_BY_ORDER)
    if orders != list(range(1, len(_STEPS) + 1)):
        raise RuntimeError("Step orders must be contiguous 1..n")
    for step in _STEPS:
        if step.order == 1:
            if step.depends_on is not None:
                raise RuntimeError("First step must not depend on another step")
        else:
            prev = _BY_ORDER[step.order - 1]
            if step.depends_on != prev.key:
                raise RuntimeError(f"Step {step.key} must depend on {prev.key}")
        for ctx in step.context_steps:
            ctx_step = _BY_KEY[ctx]
            if ctx_step.order >= step.order:
                raise RuntimeError(
                    f"Step {step.key} context_steps must reference earlier steps"
                )
        seen_input_keys: set[str] = set()
        for field in step.input_fields:
            if field.key in seen_input_keys:
                raise RuntimeError(f"Duplicate input field {field.key!r} on {step.key}")
            seen_input_keys.add(field.key)
        if step.implemented:
            if step.output_schema is None:
                raise RuntimeError(f"Implemented step {step.key} needs output_schema")
            if not step.layout:
                raise RuntimeError(f"Implemented step {step.key} needs layout")
            persisted = step.persisted_schema
            assert persisted is not None
            validate_layout_against_schema(step.layout, persisted)
            forbidden = collect_forbidden_keywords(
                gemini_processed_schema_dict(step.output_schema)
            )
            if forbidden:
                raise RuntimeError(
                    f"Schema for {step.key} uses forbidden Gemini keywords: {forbidden}"
                )


_validate_registry()


def get_step(key: str) -> StepDefinition:
    try:
        return _BY_KEY[key]
    except KeyError as exc:
        raise KeyError(f"Unknown step key: {key}") from exc


def ordered_steps() -> tuple[StepDefinition, ...]:
    return _STEPS


def previous_step(key: str) -> StepDefinition | None:
    step = get_step(key)
    if step.order == 1:
        return None
    return _BY_ORDER[step.order - 1]


def next_step(key: str) -> StepDefinition | None:
    step = get_step(key)
    if step.order == len(_STEPS):
        return None
    return _BY_ORDER[step.order + 1]

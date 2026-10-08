from __future__ import annotations

from dataclasses import dataclass
from typing import TypeVar

from pydantic import BaseModel

from app.steps.layout_config import SectionLayoutSpec, validate_layout_against_schema
from app.steps.layouts_registry import GAP_ANALYSIS_LAYOUT, SCOPE_ANALYSIS_LAYOUT
from app.steps.schema_gemini import (
    collect_forbidden_keywords,
    gemini_processed_schema_dict,
)
from app.steps.schemas.gap_analysis import GapAnalysisOutput
from app.steps.schemas.scope_analysis import ScopeAnalysisOutput

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
        prompt_version="v1",
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
    ),
    StepDefinition(
        key="feature_list",
        title="Feature List",
        order=3,
        depends_on="gap_analysis",
        output_schema=None,
        extra_inputs_schema=None,
        prompt_version=None,
        implemented=False,
        context_steps=(),
        layout=(),
        soft_list_caps=(),
        reads_description="",
        writes_description="",
    ),
    StepDefinition(
        key="estimate",
        title="Estimate",
        order=4,
        depends_on="feature_list",
        output_schema=None,
        extra_inputs_schema=None,
        prompt_version=None,
        implemented=False,
        context_steps=(),
        layout=(),
        soft_list_caps=(),
        reads_description="",
        writes_description="",
    ),
    StepDefinition(
        key="sow",
        title="Statement of Work",
        order=5,
        depends_on="estimate",
        output_schema=None,
        extra_inputs_schema=None,
        prompt_version=None,
        implemented=False,
        context_steps=(),
        layout=(),
        soft_list_caps=(),
        reads_description="",
        writes_description="",
    ),
    StepDefinition(
        key="srs",
        title="Software Requirements Specification",
        order=6,
        depends_on="sow",
        output_schema=None,
        extra_inputs_schema=None,
        prompt_version=None,
        implemented=False,
        context_steps=(),
        layout=(),
        soft_list_caps=(),
        reads_description="",
        writes_description="",
    ),
    StepDefinition(
        key="sprint_plan",
        title="Sprint Plan",
        order=7,
        depends_on="srs",
        output_schema=None,
        extra_inputs_schema=None,
        prompt_version=None,
        implemented=False,
        context_steps=(),
        layout=(),
        soft_list_caps=(),
        reads_description="",
        writes_description="",
    ),
    StepDefinition(
        key="frs",
        title="Functional Requirements Specification",
        order=8,
        depends_on="sprint_plan",
        output_schema=None,
        extra_inputs_schema=None,
        prompt_version=None,
        implemented=False,
        context_steps=(),
        layout=(),
        soft_list_caps=(),
        reads_description="",
        writes_description="",
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
        if step.implemented:
            if step.output_schema is None:
                raise RuntimeError(f"Implemented step {step.key} needs output_schema")
            if not step.layout:
                raise RuntimeError(f"Implemented step {step.key} needs layout")
            validate_layout_against_schema(step.layout, step.output_schema)
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

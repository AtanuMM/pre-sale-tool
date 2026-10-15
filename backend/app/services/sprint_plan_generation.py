"""Sprint Plan multi-pass generation."""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

logger = logging.getLogger(__name__)

from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.llm.gemini import LLMError, LLMValidationError, generate_structured_result
from app.llm.prompts.sprint_plan import v1 as sp_prompts
from app.services.estimate_generation import write_generation_progress
from app.services.step_generation import _approved_content
from app.steps.definitions import StepDefinition
from app.steps.postprocess import PostprocessContext, PostprocessError
from app.steps.postprocess.sprint_plan import postprocess_sprint_plan
from app.steps.schemas.sprint_plan import (
    SprintPlanAssembled,
    SprintPlanGoalsOutput,
    SprintPlanModuleStoriesBatchOutput,
    SprintPlanModuleStoriesOutput,
    SprintPlanPasses,
    SprintPlanPlanningGlossaryOutput,
    SprintPlanPlanningPassAOutput,
    SprintPlanPlanningPassBOutput,
    SprintPlanPlanningPassBRisksLeadOutput,
    SprintPlanStored,
)
from app.steps.sprint_plan_projection import build_sprint_plan_context


def _sum_optional(current: int | None, added: int | None) -> int | None:
    if added is None:
        return current
    if current is None:
        return added
    return current + added


def _module_batches(feature_list: dict[str, Any], batch_size: int) -> list[tuple[str, list[dict[str, Any]]]]:
    features = feature_list.get("features") if isinstance(feature_list.get("features"), list) else []
    by_module: dict[str, list[dict[str, Any]]] = {}
    order: list[str] = []
    for item in features:
        if not isinstance(item, dict):
            continue
        if str(item.get("priority") or "") == "could":
            continue
        if str(item.get("phase") or "") == "future_scope":
            continue
        mod = str(item.get("module") or "General")
        if mod not in order:
            order.append(mod)
        by_module.setdefault(mod, []).append(item)
    batches: list[tuple[str, list[dict[str, Any]]]] = []
    for mod in order:
        rows = by_module.get(mod, [])
        for i in range(0, len(rows), batch_size):
            batches.append((mod, rows[i : i + batch_size]))
    return batches or [("General", [])]


def _merge_module_stories(
    modules: dict[str, SprintPlanModuleStoriesOutput],
    mod_name: str,
    batch: SprintPlanModuleStoriesBatchOutput,
) -> None:
    existing = modules.get(mod_name)
    if existing is None:
        modules[mod_name] = SprintPlanModuleStoriesOutput(
            module=mod_name, stories=list(batch.stories)
        )
        return
    merged = [*existing.stories, *batch.stories]
    modules[mod_name] = SprintPlanModuleStoriesOutput(module=mod_name, stories=merged)


def _load_previous(session: Session, version_id: uuid.UUID) -> SprintPlanPasses | None:
    from app.models.steps import StepVersion

    row = session.get(StepVersion, version_id)
    if row is None or not isinstance(row.content, dict):
        return None
    try:
        return SprintPlanStored.model_validate(row.content).passes
    except ValueError:
        return None


def run_sprint_plan(
    *,
    factory: sessionmaker[Session],
    version_id: uuid.UUID,
    defn: StepDefinition,
    user_inputs: dict[str, Any],
    ctx: PostprocessContext,
    deadline: float,
    based_on_version_id: uuid.UUID | None,
    instructions: str | None,
    revision_parts: list[str] | None,
    reschedule_only: bool = False,
) -> tuple[SprintPlanStored, dict[str, Any], str | None, str, int | None, int | None, int]:
    settings = get_settings()
    tokens_in: int | None = 0
    tokens_out: int | None = 0
    api_attempts = 0
    inputs_meta: dict[str, Any] = {}

    with factory() as session:
        from app.models.steps import StepVersion

        version = session.get(StepVersion, version_id)
        if version is None:
            raise LLMError("version missing")
        project_id = version.project_id
        scope = ctx.scope_content or {}
        gap = ctx.gap_content or {}
        feature_list = ctx.feature_list_content or {}
        estimate = ctx.estimate_content or {}
        sow = _approved_content(session, project_id, "sow") or {}
        srs = _approved_content(session, project_id, "srs") or {}

    context = build_sprint_plan_context(
        scope=scope,
        gap=gap,
        feature_list=feature_list,
        estimate=estimate,
        estimate_user_inputs=ctx.estimate_user_inputs,
        sow=sow,
        srs=srs,
        sprint_user_inputs=user_inputs,
    )

    batches = _module_batches(feature_list, max(1, settings.SPRINT_PLAN_MODULE_BATCH_SIZE))
    planning_steps = 0 if reschedule_only else 3
    total_steps = planning_steps + (0 if reschedule_only else len(batches)) + 1
    write_generation_progress(factory, version_id, 0, max(total_steps, 1))

    previous: SprintPlanPasses | None = None
    if based_on_version_id is not None:
        with factory() as session:
            previous = _load_previous(session, based_on_version_id)

    parts_set = set(revision_parts or [])
    rerun_all = based_on_version_id is None or (not parts_set and not reschedule_only)
    rerun_planning = rerun_all or "planning" in parts_set
    passes = SprintPlanPasses(
        planning_a=previous.planning_a if previous and not (rerun_planning or reschedule_only) else None,
        planning_b=previous.planning_b if previous and not (rerun_planning or reschedule_only) else None,
        module_stories=dict(previous.module_stories) if previous else {},
        goals=previous.goals if previous and not reschedule_only else None,
        repair=previous.repair if previous else None,
    )

    step_no = 0
    if not reschedule_only and rerun_planning:
        if passes.planning_a is None:
            result = generate_structured_result(
                sp_prompts.build_planning_pass_a_prompt(context, instructions),
                SprintPlanPlanningPassAOutput,
                system=sp_prompts.PLANNING_SYSTEM,
                deadline=deadline,
                max_output_tokens=settings.SPRINT_PLAN_MAX_OUTPUT_TOKENS,
            )
            tokens_in = _sum_optional(tokens_in, result.tokens_in)
            tokens_out = _sum_optional(tokens_out, result.tokens_out)
            api_attempts += result.api_attempt_count
            passes = passes.model_copy(
                update={"planning_a": SprintPlanPlanningPassAOutput.model_validate(result.data.model_dump())}
            )
        step_no += 1
        write_generation_progress(factory, version_id, step_no, max(total_steps, 1))
        if time.monotonic() >= deadline:
            raise LLMError("generation timeout exceeded")
        if passes.planning_b is None:
            risks_lead = generate_structured_result(
                sp_prompts.build_planning_pass_b_prompt(context, instructions),
                SprintPlanPlanningPassBRisksLeadOutput,
                system=sp_prompts.PLANNING_SYSTEM,
                deadline=deadline,
                max_output_tokens=settings.SPRINT_PLAN_MAX_OUTPUT_TOKENS,
            )
            tokens_in = _sum_optional(tokens_in, risks_lead.tokens_in)
            tokens_out = _sum_optional(tokens_out, risks_lead.tokens_out)
            api_attempts += risks_lead.api_attempt_count
            step_no += 1
            write_generation_progress(factory, version_id, step_no, max(total_steps, 1))
            if time.monotonic() >= deadline:
                raise LLMError("generation timeout exceeded")
            glossary = generate_structured_result(
                sp_prompts.build_planning_pass_c_prompt(context, instructions),
                SprintPlanPlanningGlossaryOutput,
                system=sp_prompts.PLANNING_SYSTEM,
                deadline=deadline,
                max_output_tokens=settings.SPRINT_PLAN_MAX_OUTPUT_TOKENS,
            )
            tokens_in = _sum_optional(tokens_in, glossary.tokens_in)
            tokens_out = _sum_optional(tokens_out, glossary.tokens_out)
            api_attempts += glossary.api_attempt_count
            rl = SprintPlanPlanningPassBRisksLeadOutput.model_validate(risks_lead.data.model_dump())
            gl = SprintPlanPlanningGlossaryOutput.model_validate(glossary.data.model_dump())
            passes = passes.model_copy(
                update={
                    "planning_b": SprintPlanPlanningPassBOutput(
                        risks=rl.risks,
                        lead_time_actions=rl.lead_time_actions,
                        glossary=gl.glossary,
                    )
                }
            )
        step_no += 1
        write_generation_progress(factory, version_id, step_no, max(total_steps, 1))

    if not reschedule_only:
        modules = dict(passes.module_stories)
        for mod_name, feature_rows in batches:
            if time.monotonic() >= deadline:
                raise LLMError("generation timeout exceeded")
            part_key = f"stories:{mod_name}"
            if (
                not rerun_all
                and part_key not in parts_set
                and mod_name not in parts_set
                and mod_name in modules
                and modules[mod_name].stories
            ):
                step_no += 1
                write_generation_progress(factory, version_id, step_no, max(total_steps, 1))
                continue
            if not feature_rows:
                continue
            prompt = sp_prompts.build_stories_prompt(context, mod_name, feature_rows, instructions)
            result = generate_structured_result(
                prompt,
                SprintPlanModuleStoriesBatchOutput,
                system=sp_prompts.STORIES_SYSTEM,
                deadline=deadline,
                max_output_tokens=settings.SPRINT_PLAN_MAX_OUTPUT_TOKENS,
            )
            tokens_in = _sum_optional(tokens_in, result.tokens_in)
            tokens_out = _sum_optional(tokens_out, result.tokens_out)
            api_attempts += result.api_attempt_count
            batch_out = SprintPlanModuleStoriesBatchOutput.model_validate(result.data.model_dump())
            if len(batch_out.stories) > 10:
                batch_out = batch_out.model_copy(update={"stories": batch_out.stories[:10]})
            _merge_module_stories(modules, mod_name, batch_out)
            step_no += 1
            write_generation_progress(factory, version_id, step_no, max(total_steps, 1))
        passes = passes.model_copy(update={"module_stories": modules})

    draft = SprintPlanStored(
        passes=passes,
        stories=[],
        assembled=SprintPlanAssembled(document_reference="pending"),
    )
    try:
        stored, validation_notes = postprocess_sprint_plan(draft, ctx)
    except PostprocessError as exc:
        raise LLMError(str(exc)) from exc

    if time.monotonic() < deadline and (rerun_all or "goals" in parts_set or reschedule_only or passes.goals is None):
        outline = [
            {"number": s["number"], "name": s["name"], "phase": s["phase"], "items": s.get("items") or []}
            for s in stored.assembled.schedule_sprints
        ][: settings.SPRINT_PLAN_GOALS_BATCH_SIZE]
        prompt = sp_prompts.build_goals_prompt(outline, instructions)
        try:
            result = generate_structured_result(
                prompt,
                SprintPlanGoalsOutput,
                system=sp_prompts.GOALS_SYSTEM,
                deadline=deadline,
                max_output_tokens=settings.SPRINT_PLAN_MAX_OUTPUT_TOKENS,
            )
            tokens_in = _sum_optional(tokens_in, result.tokens_in)
            tokens_out = _sum_optional(tokens_out, result.tokens_out)
            api_attempts += result.api_attempt_count
            passes = passes.model_copy(
                update={"goals": SprintPlanGoalsOutput.model_validate(result.data.model_dump())}
            )
            stored = stored.model_copy(update={"passes": passes})
        except (LLMError, LLMValidationError) as exc:
            logger.warning("Sprint plan goals skipped: %s", type(exc).__name__)
            validation_notes["goals_skipped"] = 1

    write_generation_progress(factory, version_id, max(total_steps, 1), max(total_steps, 1))
    inputs_meta["validation_notes"] = validation_notes
    if revision_parts:
        inputs_meta["revision_parts_count"] = len(revision_parts)
    if reschedule_only:
        inputs_meta["reschedule"] = 1
    assembled_prompt = json.dumps({"step": "sprint_plan", "passes": len(batches)}, ensure_ascii=False)
    return stored, inputs_meta, assembled_prompt, sp_prompts.PROMPT_VERSION, tokens_in, tokens_out, api_attempts

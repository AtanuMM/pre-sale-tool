"""Estimate v2 batched generation and team-only recompute."""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.llm.gemini import LLMError
from app.llm.prompts.assembly import PromptAssemblyError
from app.models.steps import StepVersion
from app.services.step_prompts import (
    assemble_estimate_batch_prompt,
    assemble_estimate_packages_repair_prompt,
    assemble_step_prompt,
)
from app.services.step_soft_caps import apply_soft_list_caps
from app.steps.definitions import StepDefinition
from app.steps.postprocess import PostprocessContext, PostprocessError
from app.steps.postprocess.estimate_v2 import (
    merge_package_repair,
    missing_required_package_types,
    postprocess_estimate_v2,
    recompute_estimate_v2,
)
from app.steps.schemas.estimate_v2 import (
    EstimateBatchOutput,
    EstimatePlanningOutput,
    EstimateRepairPackagesOutput,
    EstimateV2Merged,
    EstimateV2Stored,
)

logger = logging.getLogger(__name__)

TEAM_RECOMPUTE_RE = re.compile(
    r"^(recalc(ulate)?(\s+with\s+(the\s+)?updated\s+team)?|"
    r"update team|apply team|new team|headcount|ai gain)\b",
    re.IGNORECASE,
)


def is_team_recompute_request(instructions: str | None) -> bool:
    if not instructions:
        return False
    return TEAM_RECOMPUTE_RE.match(instructions.strip()) is not None


def _sum_optional(current: int | None, added: int | None) -> int | None:
    if added is None:
        return current
    if current is None:
        return added
    return current + added


def write_generation_progress(
    factory: sessionmaker[Session],
    version_id: uuid.UUID,
    done: int,
    total: int,
) -> None:
    with factory() as session:
        version = session.get(StepVersion, version_id)
        if version is None or version.status != "generating":
            return
        inputs = dict(version.inputs or {})
        inputs["generation_progress"] = {"done": done, "total": total}
        version.inputs = inputs
        session.commit()


def _planning_excerpt(planning: EstimatePlanningOutput) -> str:
    payload = {
        "components": [
            {"name": c.name, "screens": c.screens} for c in planning.components
        ],
        "work_packages": [
            {
                "id": w.id,
                "package_type": w.package_type,
                "title": w.title,
                "phase": w.phase,
                "component": w.component,
            }
            for w in planning.work_packages
        ],
        "phases": [{"key": p.key, "goal": p.goal} for p in planning.phases],
        "assumption_topics": [a.topic for a in planning.assumptions_and_solutions],
    }
    text = json.dumps(payload, ensure_ascii=False)
    if len(text) > 8000:
        return text[:8000]
    return text


def _planning_to_merged(planning: EstimatePlanningOutput) -> EstimateV2Merged:
    return EstimateV2Merged(
        summary=planning.summary,
        approach=planning.approach,
        components=planning.components,
        phases=planning.phases,
        assumptions_and_solutions=planning.assumptions_and_solutions,
        exclusions=planning.exclusions,
        feature_estimates=[],
        added_items=[],
        work_packages=planning.work_packages,
        effort_lines=[],
    )


def load_previous_v2_stored(session: Session, version_id: uuid.UUID) -> EstimateV2Stored | None:
    base = session.get(StepVersion, version_id)
    if base is None or not isinstance(base.content, dict):
        return None
    if base.content.get("schema_version") != 2:
        return None
    try:
        return EstimateV2Stored.model_validate(base.content)
    except ValueError:
        return None


def run_estimate_v2(
    *,
    factory: sessionmaker[Session],
    version_id: uuid.UUID,
    defn: StepDefinition,
    user_inputs: dict[str, Any],
    block_nonce: str,
    deadline: float,
    ctx: PostprocessContext,
    based_on_version_id: uuid.UUID | None,
    instructions: str | None,
    previous_prompt: str | None,
) -> tuple[EstimateV2Stored, dict[str, Any], str, str, int | None, int | None, int]:
    """Returns stored, inputs_meta, assembled_prompt, prompt_version, tokens_in, tokens_out, attempts."""
    from app.services.step_generation import generate_structured_result

    settings = get_settings()
    tokens_in: int | None = None
    tokens_out: int | None = None
    api_attempts = 0
    inputs_meta: dict[str, Any] = {}

    if based_on_version_id and is_team_recompute_request(instructions):
        with factory() as session:
            previous = load_previous_v2_stored(session, based_on_version_id)
        if previous is not None:
            stored, notes = recompute_estimate_v2(previous, ctx)
            inputs_meta["team_recompute"] = 1
            inputs_meta["repair_attempted"] = 0
            inputs_meta["validation_notes"] = notes
            prompt = previous_prompt or "Team variables recomputed from stored estimate output."
            return stored, inputs_meta, prompt, "v2", 0, 0, 0

    try:
        with factory() as session:
            assembled = assemble_step_prompt(
                session,
                step_key="estimate",
                project_id=_project_id(session, version_id),
                block_nonce=block_nonce,
                user_inputs=user_inputs,
            )
    except PromptAssemblyError as exc:
        raise LLMError(str(exc)) from exc

    feature_ids = list(ctx.feature_ids)
    batch_size = max(1, settings.ESTIMATE_BATCH_SIZE)
    batches = [
        feature_ids[i : i + batch_size] for i in range(0, len(feature_ids), batch_size)
    ] or [[]]
    n_batches = len(batches)
    write_generation_progress(factory, version_id, 0, n_batches)

    planning_result = generate_structured_result(
        assembled.user_prompt,
        EstimatePlanningOutput,
        system=assembled.system_instruction,
        deadline=deadline,
        max_output_tokens=defn.max_output_tokens,
    )
    tokens_in = _sum_optional(tokens_in, planning_result.tokens_in)
    tokens_out = _sum_optional(tokens_out, planning_result.tokens_out)
    api_attempts += planning_result.api_attempt_count
    list_trim, planning = apply_soft_list_caps(defn, planning_result.data)
    inputs_meta.update(list_trim)
    if not isinstance(planning, EstimatePlanningOutput):
        planning = EstimatePlanningOutput.model_validate(planning.model_dump())

    merged = _planning_to_merged(planning)
    excerpt = _planning_excerpt(planning)
    wp_ids = [w.id for w in planning.work_packages]

    with factory() as session:
        project_id = _project_id(session, version_id)

    for index, batch_ids in enumerate(batches):
        if time.monotonic() >= deadline:
            raise LLMError("generation timeout exceeded")
        batch_nonce = f"{block_nonce}-b{index + 1}"
        wp_for_batch = wp_ids if index == 0 else []
        try:
            with factory() as session:
                batch_assembled = assemble_estimate_batch_prompt(
                    session,
                    project_id=project_id,
                    block_nonce=batch_nonce,
                    user_inputs=user_inputs,
                    feature_ids=batch_ids,
                    work_package_ids=wp_for_batch,
                    planning_excerpt=excerpt,
                )
        except PromptAssemblyError as exc:
            raise LLMError(str(exc)) from exc
        batch_result = generate_structured_result(
            batch_assembled.user_prompt,
            EstimateBatchOutput,
            system=batch_assembled.system_instruction,
            deadline=deadline,
            max_output_tokens=defn.max_output_tokens,
        )
        tokens_in = _sum_optional(tokens_in, batch_result.tokens_in)
        tokens_out = _sum_optional(tokens_out, batch_result.tokens_out)
        api_attempts += batch_result.api_attempt_count
        merged = _merge_batch_output(merged, batch_result.data)
        write_generation_progress(factory, version_id, index + 1, n_batches)

    missing_types = missing_required_package_types(merged)
    inputs_meta["repair_attempted"] = 0
    if missing_types:
        inputs_meta["repair_attempted"] = 1
        try:
            with factory() as session:
                repair_assembled = assemble_estimate_packages_repair_prompt(
                    session,
                    project_id=project_id,
                    block_nonce=f"{block_nonce}-repair",
                    user_inputs=user_inputs,
                    missing_types=missing_types,
                )
            repair_result = generate_structured_result(
                repair_assembled.user_prompt,
                EstimateRepairPackagesOutput,
                system=repair_assembled.system_instruction,
                deadline=deadline,
                max_output_tokens=defn.max_output_tokens,
            )
            tokens_in = _sum_optional(tokens_in, repair_result.tokens_in)
            tokens_out = _sum_optional(tokens_out, repair_result.tokens_out)
            api_attempts += repair_result.api_attempt_count
            merged = merge_package_repair(merged, repair_result.data)
        except (LLMError, PromptAssemblyError):
            logger.info("Estimate package repair failed version_id=%s", version_id)

    try:
        stored, validation_notes = postprocess_estimate_v2(merged, ctx)
    except PostprocessError as exc:
        raise LLMError(str(exc)) from exc
    except ValidationError as exc:
        raise LLMError("estimate output failed validation") from exc
    inputs_meta["validation_notes"] = validation_notes
    assert isinstance(stored, EstimateV2Stored)
    return (
        stored,
        inputs_meta,
        assembled.user_prompt,
        assembled.prompt_version,
        tokens_in,
        tokens_out,
        api_attempts,
    )


def _merge_batch_output(merged: EstimateV2Merged, batch: EstimateBatchOutput) -> EstimateV2Merged:
    existing_features = {f.feature_id.strip() for f in merged.feature_estimates}
    extra_features = [
        f for f in batch.feature_estimates if f.feature_id.strip() not in existing_features
    ]
    existing_added = {a.id.strip() for a in merged.added_items}
    extra_added = [a for a in batch.added_items if a.id.strip() not in existing_added]
    existing_lines = {(e.item_id, e.role, e.task) for e in merged.effort_lines}
    extra_lines = [
        line
        for line in batch.effort_lines
        if (line.item_id, line.role, line.task) not in existing_lines
    ]
    return merged.model_copy(
        update={
            "feature_estimates": [*merged.feature_estimates, *extra_features],
            "added_items": [*merged.added_items, *extra_added],
            "effort_lines": [*merged.effort_lines, *extra_lines],
        }
    )


def _project_id(session: Session, version_id: uuid.UUID) -> uuid.UUID:
    version = session.get(StepVersion, version_id)
    if version is None:
        raise LLMError("version missing")
    return version.project_id

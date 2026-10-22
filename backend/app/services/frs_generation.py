"""FRS multi-pass generation orchestration."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import replace
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.llm.gemini import LLMError, generate_structured_result
from app.llm.prompts.frs import v1 as frs_prompts
from app.services.estimate_generation import write_generation_progress
from app.services.step_generation import _approved_content
from app.steps.definitions import StepDefinition
from app.steps.frs_projection import (
    batch_features_payload,
    build_frs_context,
    build_frs_context_json,
    project_core_summary,
)
from app.steps.postprocess import PostprocessContext, PostprocessError
from app.steps.postprocess.frs import postprocess_frs
from app.steps.schemas.frs import (
    FrsCoverageRepairOutput,
    FrsModuleBatchOutput,
    FrsPasses,
    FrsPlanningOutput,
    FrsStored,
)


def _sum_optional(current: int | None, added: int | None) -> int | None:
    if added is None:
        return current
    if current is None:
        return added
    return current + added


def _module_batches(feature_list: dict[str, Any], batch_size: int) -> list[tuple[str, list[str]]]:
    from app.steps.frs_projection import _committed_feature

    by_module: dict[str, list[str]] = {}
    module_order: list[str] = []
    for mod in feature_list.get("modules") or []:
        if isinstance(mod, dict):
            name = str(mod.get("name") or "")
            if name and name not in module_order:
                module_order.append(name)
    for item in feature_list.get("features") or []:
        if not isinstance(item, dict) or not _committed_feature(item):
            continue
        fid = str(item.get("id") or "")
        mod = str(item.get("module") or "General")
        if mod not in module_order:
            module_order.append(mod)
        by_module.setdefault(mod, []).append(fid)
    batches: list[tuple[str, list[str]]] = []
    for mod in module_order:
        ids = by_module.get(mod, [])
        for i in range(0, len(ids), batch_size):
            batches.append((mod, ids[i : i + batch_size]))
    return batches or [("General", [])]


def _load_previous_passes(session: Session, version_id: uuid.UUID) -> FrsPasses | None:
    from app.models.steps import StepVersion

    row = session.get(StepVersion, version_id)
    if row is None or not isinstance(row.content, dict):
        return None
    try:
        stored = FrsStored.model_validate(row.content)
    except ValueError:
        return None
    return stored.passes


def _index_srs(context: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    by_feature: dict[str, list[dict[str, Any]]] = {}
    for req in context.get("srs_requirements") or []:
        if isinstance(req, dict):
            fid = str(req.get("feature_id") or "")
            by_feature.setdefault(fid, []).append(req)
    return by_feature


def _index_stories(context: dict[str, Any]) -> dict[str, list[dict[str, str]]]:
    by_feature: dict[str, list[dict[str, str]]] = {}
    for st in context.get("stories") or []:
        if isinstance(st, dict):
            fid = str(st.get("feature_id") or "")
            by_feature.setdefault(fid, []).append(
                {"id": str(st.get("id") or ""), "title": str(st.get("title") or "")}
            )
    return by_feature


def _entities_by_module(context: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for ent in context.get("entities") or []:
        if isinstance(ent, dict):
            mod = str(ent.get("module") or "General")
            out.setdefault(mod, []).append(ent)
    return out


def run_frs(
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
) -> tuple[FrsStored, dict[str, Any], str | None, str, int | None, int | None, int]:
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
        sprint = _approved_content(session, project_id, "sprint_plan") or {}

    context = build_frs_context(
        scope=scope,
        gap=gap,
        feature_list=feature_list,
        estimate=estimate,
        sow=sow,
        srs=srs,
        sprint_plan=sprint,
        frs_user_inputs=user_inputs,
    )
    batches = _module_batches(feature_list, max(1, settings.FRS_MODULE_BATCH_SIZE))
    total_steps = 1 + len(batches) + 1
    write_generation_progress(factory, version_id, 0, total_steps)

    previous_passes: FrsPasses | None = None
    if based_on_version_id is not None:
        with factory() as session:
            previous_passes = _load_previous_passes(session, based_on_version_id)

    parts_set = set(revision_parts or [])
    rerun_all = based_on_version_id is None or (not parts_set and based_on_version_id is not None)
    if based_on_version_id is None:
        rerun_all = True

    passes = FrsPasses(
        planning=previous_passes.planning
        if previous_passes and not (rerun_all or "planning" in parts_set)
        else None,
        modules=dict(previous_passes.modules) if previous_passes else {},
        coverage_repair=previous_passes.coverage_repair if previous_passes and not rerun_all else None,
    )

    instr_block = f"\nReviewer instructions:\n{instructions}\n" if instructions else ""
    core_json = json.dumps(project_core_summary(context), ensure_ascii=False)

    if rerun_all or "planning" in parts_set or passes.planning is None:
        prompt = (
            f"{frs_prompts.PLANNING_SYSTEM}\n\n"
            f"Project summary:\n{core_json}\n\n"
            f"User classes from SRS:\n{json.dumps(context.get('user_classes'), ensure_ascii=False)}\n\n"
            f"Interfaces:\n{json.dumps(context.get('interfaces'), ensure_ascii=False)}\n\n"
            f"Entities:\n{json.dumps(context.get('entities'), ensure_ascii=False)[:12000]}\n"
            f"{instr_block}"
        )
        result = generate_structured_result(
            prompt,
            FrsPlanningOutput,
            system=frs_prompts.PLANNING_SYSTEM,
            deadline=deadline,
            max_output_tokens=settings.FRS_MAX_OUTPUT_TOKENS,
        )
        tokens_in = _sum_optional(tokens_in, result.tokens_in)
        tokens_out = _sum_optional(tokens_out, result.tokens_out)
        api_attempts += result.api_attempt_count
        passes = passes.model_copy(
            update={"planning": FrsPlanningOutput.model_validate(result.data.model_dump())}
        )
    write_generation_progress(factory, version_id, 1, total_steps)

    srs_by_feature = _index_srs(context)
    stories_by_feature = _index_stories(context)
    entities_by_module = _entities_by_module(context)
    roles_json = json.dumps([r.model_dump() for r in passes.planning.roles], ensure_ascii=False) if passes.planning else "[]"
    conventions = json.dumps(user_inputs, ensure_ascii=False)

    modules = dict(passes.modules)
    for step_index, (mod_name, feature_ids) in enumerate(batches, start=1):
        if time.monotonic() >= deadline:
            raise LLMError("generation timeout exceeded")
        if (
            not rerun_all
            and mod_name not in parts_set
            and mod_name in modules
        ):
            write_generation_progress(factory, version_id, step_index, total_steps)
            continue
        if not feature_ids:
            continue
        batch_payload = batch_features_payload(
            context,
            feature_ids,
            srs_by_feature=srs_by_feature,
            stories_by_feature=stories_by_feature,
            entities_by_module=entities_by_module,
            module=mod_name,
        )
        prompt = (
            f"{frs_prompts.MODULE_BATCH_SYSTEM}\n\n"
            f"Project summary:\n{core_json}\n\n"
            f"Roles:\n{roles_json}\n\n"
            f"Global conventions (use exactly):\n{conventions}\n\n"
            f"Detail level: {user_inputs.get('detail_level', 'detailed')}\n\n"
            f"Batch payload:\n{json.dumps(batch_payload, ensure_ascii=False)[:50000]}\n"
            f"{instr_block}"
        )
        result = generate_structured_result(
            prompt,
            FrsModuleBatchOutput,
            system=frs_prompts.MODULE_BATCH_SYSTEM,
            deadline=deadline,
            max_output_tokens=settings.FRS_MAX_OUTPUT_TOKENS,
        )
        tokens_in = _sum_optional(tokens_in, result.tokens_in)
        tokens_out = _sum_optional(tokens_out, result.tokens_out)
        api_attempts += result.api_attempt_count
        modules[mod_name] = FrsModuleBatchOutput.model_validate(result.data.model_dump())
        write_generation_progress(factory, version_id, step_index, total_steps)

    passes = passes.model_copy(update={"modules": modules})

    if time.monotonic() >= deadline:
        raise LLMError("generation timeout exceeded")

    from app.steps.schemas.frs import FrsAssembled

    ctx = replace(
        ctx,
        srs_content=srs,
        sprint_plan_content=sprint,
        frs_revision_parts=tuple(revision_parts or ()),
    )

    if passes.coverage_repair is None and time.monotonic() < deadline:
        prompt = (
            f"{frs_prompts.COVERAGE_REPAIR_SYSTEM}\n\n"
            f"Modules batch summary feature ids:\n"
            f"{json.dumps([s.feature_id for b in passes.modules.values() for s in b.specifications], ensure_ascii=False)}\n\n"
            f"SRS requirements:\n{json.dumps(context.get('srs_requirements'), ensure_ascii=False)[:25000]}\n"
            f"{instr_block}"
        )
        result = generate_structured_result(
            prompt,
            FrsCoverageRepairOutput,
            system=frs_prompts.COVERAGE_REPAIR_SYSTEM,
            deadline=deadline,
            max_output_tokens=settings.FRS_MAX_OUTPUT_TOKENS,
        )
        tokens_in = _sum_optional(tokens_in, result.tokens_in)
        tokens_out = _sum_optional(tokens_out, result.tokens_out)
        api_attempts += result.api_attempt_count
        passes = passes.model_copy(
            update={
                "coverage_repair": FrsCoverageRepairOutput.model_validate(result.data.model_dump())
            }
        )

    draft = FrsStored(
        passes=passes,
        specifications=[],
        assembled=FrsAssembled(document_reference="pending"),
    )
    try:
        stored, validation_notes = postprocess_frs(draft, ctx)
    except PostprocessError as exc:
        raise LLMError(str(exc)) from exc

    write_generation_progress(factory, version_id, total_steps, total_steps)
    inputs_meta["validation_notes"] = validation_notes
    inputs_meta["frs_pass_count"] = total_steps
    if revision_parts:
        inputs_meta["revision_parts_count"] = len(revision_parts)
    assembled_prompt = build_frs_context_json(
        scope=scope,
        gap=gap,
        feature_list=feature_list,
        estimate=estimate,
        sow=sow,
        srs=srs,
        sprint_plan=sprint,
        frs_user_inputs=user_inputs,
    )
    return stored, inputs_meta, assembled_prompt, "v1", tokens_in, tokens_out, api_attempts


def _merge_specs_for_repair(passes: FrsPasses) -> list[Any]:
    specs: list[Any] = []
    for batch in passes.modules.values():
        specs.extend(batch.specifications)
    return specs

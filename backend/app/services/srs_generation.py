"""SRS multi-pass generation orchestration."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.llm.gemini import LLMError, generate_structured_result
from app.llm.prompts.srs import v1 as srs_prompts
from app.services.estimate_generation import write_generation_progress
from app.services.step_generation import _approved_content
from app.steps.definitions import StepDefinition
from app.steps.postprocess import PostprocessContext, PostprocessError
from app.steps.postprocess.srs import postprocess_srs
from app.steps.schemas.srs import (
    SrsAssembled,
    SrsCoverageRepairOutput,
    SrsHealthMeta,
    SrsModuleBatchOutput,
    SrsPasses,
    SrsPlanningPassAOutput,
    SrsPlanningPassBOutput,
    SrsStored,
)
from app.steps.srs_projection import (
    architecture_summary_from_pass_a,
    batch_features_payload,
    build_srs_context,
    build_srs_context_json,
    project_core_summary,
)


def _sum_optional(current: int | None, added: int | None) -> int | None:
    if added is None:
        return current
    if current is None:
        return added
    return current + added


def _gap_by_ref(gap: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(gap.get("gaps") or [], start=1):
        if isinstance(item, dict):
            out[f"G-{index}"] = {
                "ref": f"G-{index}",
                "title": item.get("title") or "",
                "severity": item.get("severity") or "",
                "question": item.get("clarification_question") or "",
            }
    return out


def _module_batches(feature_list: dict[str, Any], batch_size: int) -> list[tuple[str, list[str]]]:
    features = feature_list.get("features") if isinstance(feature_list.get("features"), list) else []
    by_module: dict[str, list[str]] = {}
    module_order: list[str] = []
    for mod in feature_list.get("modules") or []:
        if isinstance(mod, dict):
            name = str(mod.get("name") or "")
            if name and name not in module_order:
                module_order.append(name)
    for item in features:
        if not isinstance(item, dict):
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


def _load_previous_passes(session: Session, version_id: uuid.UUID) -> SrsPasses | None:
    from app.models.steps import StepVersion

    row = session.get(StepVersion, version_id)
    if row is None or not isinstance(row.content, dict):
        return None
    try:
        stored = SrsStored.model_validate(row.content)
    except ValueError:
        return None
    return stored.passes


def run_srs(
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
) -> tuple[SrsStored, dict[str, Any], str | None, str, int | None, int | None, int]:
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
        if estimate.get("schema_version") != 2:
            raise LLMError("estimate must be version 2")
        sow = _approved_content(session, project_id, "sow") or {}

    context = build_srs_context(
        scope=scope,
        gap=gap,
        feature_list=feature_list,
        estimate=estimate,
        estimate_user_inputs=ctx.estimate_user_inputs,
        sow=sow,
        srs_user_inputs=user_inputs,
    )
    gap_refs = _gap_by_ref(gap)
    batches = _module_batches(feature_list, max(1, settings.SRS_MODULE_BATCH_SIZE))
    total_steps = 2 + len(batches) + 1
    write_generation_progress(factory, version_id, 0, total_steps)

    previous_passes: SrsPasses | None = None
    if based_on_version_id is not None:
        with factory() as session:
            previous_passes = _load_previous_passes(session, based_on_version_id)

    parts_set = set(revision_parts or [])
    rerun_all = not parts_set and based_on_version_id is not None
    if based_on_version_id is None:
        rerun_all = True

    passes = SrsPasses(
        planning_a=previous_passes.planning_a if previous_passes and not (rerun_all or "planning_a" in parts_set) else None,
        planning_b=previous_passes.planning_b if previous_passes and not (rerun_all or "planning_b" in parts_set) else None,
        modules=dict(previous_passes.modules) if previous_passes else {},
        coverage_repair=previous_passes.coverage_repair if previous_passes and not rerun_all else None,
    )

    if rerun_all or "planning_a" in parts_set or passes.planning_a is None:
        prompt = _planning_a_prompt(context, instructions)
        result = generate_structured_result(
            prompt,
            SrsPlanningPassAOutput,
            system=srs_prompts.PLANNING_A_SYSTEM,
            deadline=deadline,
            max_output_tokens=settings.SRS_MAX_OUTPUT_TOKENS,
        )
        tokens_in = _sum_optional(tokens_in, result.tokens_in)
        tokens_out = _sum_optional(tokens_out, result.tokens_out)
        api_attempts += result.api_attempt_count
        passes = passes.model_copy(update={"planning_a": SrsPlanningPassAOutput.model_validate(result.data.model_dump())})
    write_generation_progress(factory, version_id, 1, total_steps)

    if time.monotonic() >= deadline:
        raise LLMError("generation timeout exceeded")

    if rerun_all or "planning_b" in parts_set or passes.planning_b is None:
        arch = architecture_summary_from_pass_a(passes.planning_a.model_dump(mode="json")) if passes.planning_a else {}
        prompt = _planning_b_prompt(context, arch, instructions)
        result = generate_structured_result(
            prompt,
            SrsPlanningPassBOutput,
            system=srs_prompts.PLANNING_B_SYSTEM,
            deadline=deadline,
            max_output_tokens=settings.SRS_MAX_OUTPUT_TOKENS,
        )
        tokens_in = _sum_optional(tokens_in, result.tokens_in)
        tokens_out = _sum_optional(tokens_out, result.tokens_out)
        api_attempts += result.api_attempt_count
        passes = passes.model_copy(update={"planning_b": SrsPlanningPassBOutput.model_validate(result.data.model_dump())})
    write_generation_progress(factory, version_id, 2, total_steps)

    core = project_core_summary(context)
    arch_summary = (
        architecture_summary_from_pass_a(passes.planning_a.model_dump(mode="json"))
        if passes.planning_a
        else {}
    )

    modules = dict(passes.modules)
    for step_index, (mod_name, feature_ids) in enumerate(batches, start=1):
        if time.monotonic() >= deadline:
            raise LLMError("generation timeout exceeded")
        batch_key = f"{mod_name}::{','.join(feature_ids)}"
        if (
            not rerun_all
            and mod_name not in parts_set
            and batch_key not in parts_set
            and mod_name in modules
        ):
            write_generation_progress(factory, version_id, 2 + step_index, total_steps)
            continue
        if not feature_ids:
            continue
        batch_payload = batch_features_payload(context, feature_ids, gap_refs)
        prompt = _module_prompt(core, arch_summary, user_inputs, mod_name, batch_payload, instructions)
        result = generate_structured_result(
            prompt,
            SrsModuleBatchOutput,
            system=srs_prompts.MODULE_BATCH_SYSTEM,
            deadline=deadline,
            max_output_tokens=settings.SRS_MAX_OUTPUT_TOKENS,
        )
        tokens_in = _sum_optional(tokens_in, result.tokens_in)
        tokens_out = _sum_optional(tokens_out, result.tokens_out)
        api_attempts += result.api_attempt_count
        modules[mod_name] = SrsModuleBatchOutput.model_validate(result.data.model_dump())
        write_generation_progress(factory, version_id, 2 + step_index, total_steps)

    passes = passes.model_copy(update={"modules": modules})

    if time.monotonic() >= deadline:
        raise LLMError("generation timeout exceeded")

    missing_features = _missing_feature_ids(passes, ctx.feature_ids)
    missing_nfr = _missing_nfr_categories(passes, user_inputs)
    if missing_features or missing_nfr:
        inputs_meta["coverage_repair"] = 1
        prompt = _coverage_prompt(context, missing_features, missing_nfr, instructions)
        result = generate_structured_result(
            prompt,
            SrsCoverageRepairOutput,
            system=srs_prompts.COVERAGE_REPAIR_SYSTEM,
            deadline=deadline,
            max_output_tokens=settings.SRS_MAX_OUTPUT_TOKENS,
        )
        tokens_in = _sum_optional(tokens_in, result.tokens_in)
        tokens_out = _sum_optional(tokens_out, result.tokens_out)
        api_attempts += result.api_attempt_count
        passes = passes.model_copy(
            update={"coverage_repair": SrsCoverageRepairOutput.model_validate(result.data.model_dump())}
        )
    write_generation_progress(factory, version_id, total_steps, total_steps)

    draft = SrsStored(
        passes=passes,
        functional_requirements=[],
        nfr_requirements=[],
        interfaces=[],
        entities=[],
        assembled=SrsAssembled(document_reference="pending"),
        viewer=SrsHealthMeta(),
    )
    try:
        stored, validation_notes = postprocess_srs(draft, ctx)
    except PostprocessError as exc:
        raise LLMError(str(exc)) from exc
    inputs_meta["validation_notes"] = validation_notes
    inputs_meta["srs_pass_count"] = total_steps
    if revision_parts:
        inputs_meta["revision_parts_count"] = len(revision_parts)
    assembled_prompt = build_srs_context_json(
        scope=scope,
        gap=gap,
        feature_list=feature_list,
        estimate=estimate,
        estimate_user_inputs=ctx.estimate_user_inputs,
        sow=sow,
        srs_user_inputs=user_inputs,
    )
    return stored, inputs_meta, assembled_prompt, "v1", tokens_in, tokens_out, api_attempts


def _missing_feature_ids(passes: SrsPasses, feature_ids: tuple[str, ...]) -> list[str]:
    covered: set[str] = set()
    for batch in passes.modules.values():
        for fr in batch.functional_requirements:
            covered.add(fr.feature_id)
    if passes.coverage_repair:
        for fr in passes.coverage_repair.functional_requirements:
            covered.add(fr.feature_id)
    return [fid for fid in feature_ids if fid not in covered]


def _missing_nfr_categories(passes: SrsPasses, user_inputs: dict[str, Any]) -> list[str]:
    from app.steps.schemas.srs import MANDATORY_NFR_CATEGORIES

    cats: set[str] = set()
    if passes.planning_b:
        cats.update(n.category for n in passes.planning_b.nfr_catalogue)
    if passes.coverage_repair:
        cats.update(n.category for n in passes.coverage_repair.nfr_items)
    missing = [c for c in MANDATORY_NFR_CATEGORIES if c not in cats]
    if user_inputs.get("languages") and "localisation" not in cats:
        missing.append("localisation")
    return missing


def _planning_a_prompt(context: dict[str, Any], instructions: str | None) -> str:
    payload = {"context": context, "reviewer_instructions": instructions or ""}
    return json.dumps(payload, ensure_ascii=False)


def _planning_b_prompt(context: dict[str, Any], arch: dict[str, Any], instructions: str | None) -> str:
    payload = {"context": context, "architecture_summary": arch, "reviewer_instructions": instructions or ""}
    return json.dumps(payload, ensure_ascii=False)


def _module_prompt(
    core: dict[str, Any],
    arch: dict[str, Any],
    user_inputs: dict[str, Any],
    module_name: str,
    features: list[dict[str, Any]],
    instructions: str | None,
) -> str:
    payload = {
        "project_core": core,
        "architecture_summary": arch,
        "srs_parameters": user_inputs,
        "module_name": module_name,
        "features": features,
        "reviewer_instructions": instructions or "",
    }
    return json.dumps(payload, ensure_ascii=False)


def _coverage_prompt(
    context: dict[str, Any],
    missing_features: list[str],
    missing_nfr: list[str],
    instructions: str | None,
) -> str:
    payload = {
        "context": context,
        "missing_feature_ids": missing_features,
        "missing_nfr_categories": missing_nfr,
        "reviewer_instructions": instructions or "",
    }
    return json.dumps(payload, ensure_ascii=False)

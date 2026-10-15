"""SOW generation helpers: repair and reassemble."""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from app.llm.gemini import LLMError
from app.llm.prompts.assembly import PromptAssemblyError
from app.llm.prompts.sow import repair_v1 as sow_repair
from app.models.steps import StepVersion
from app.services.step_prompts import assemble_step_prompt
from app.steps.definitions import get_step
from app.steps.postprocess import PostprocessContext
from app.steps.postprocess.sow import (
    merge_deliverable_repair,
    postprocess_sow,
    reassemble_sow,
)
from app.steps.schemas.sow import (
    SowDeliverablesRepairOutput,
    SowNarrativeOutput,
    SowStored,
)
from app.steps.sow_assemble import build_assembled
from app.steps.sow_projection import project_estimate_for_prompt


def inputs_changed(base_inputs: dict[str, Any], new_inputs: dict[str, Any]) -> bool:
    return json.dumps(base_inputs, sort_keys=True) != json.dumps(new_inputs, sort_keys=True)


def load_previous_sow(session: Session, version_id: uuid.UUID) -> SowStored | None:
    row = session.get(StepVersion, version_id)
    if row is None or not isinstance(row.content, dict):
        return None
    if row.content.get("schema_version") != 1:
        return None
    try:
        return SowStored.model_validate(row.content)
    except ValueError:
        return None


def missing_deliverable_keys(merged: SowNarrativeOutput, ctx: PostprocessContext) -> list[str]:
    estimate = ctx.estimate_content or {}
    assembled = build_assembled(
        project_id=ctx.project_id,
        version_no=ctx.version_no,
        status_text="In review",
        user_inputs=ctx.user_inputs,
        scope=ctx.scope_content or {},
        gap=ctx.gap_content or {},
        feature_list=ctx.feature_list_content or {},
        estimate=estimate,
        estimate_user_inputs=ctx.estimate_user_inputs,
    )
    seen = {d.bundle_key for d in merged.deliverables}
    return [k for k in assembled.bundle_keys if k not in seen]


def run_sow_reassemble(
    *,
    previous: SowStored,
    ctx: PostprocessContext,
) -> tuple[SowStored, dict[str, int]]:
    stored, notes = reassemble_sow(previous, ctx)
    return stored, notes


def run_sow_postprocess_with_repair(
    *,
    factory: sessionmaker[Session],
    version_id: uuid.UUID,
    narrative: SowNarrativeOutput,
    ctx: PostprocessContext,
    deadline: float,
) -> tuple[SowStored, dict[str, Any], int]:
    from app.services.step_generation import generate_structured_result

    notes_meta: dict[str, Any] = {"repair_attempted": 0}
    merged = narrative
    missing = missing_deliverable_keys(merged, ctx)
    api_attempts = 0
    if missing:
        notes_meta["repair_attempted"] = 1
        try:
            defn = get_step("sow")
            with factory() as session:
                version = session.get(StepVersion, version_id)
                if version is None:
                    raise LLMError("version missing")
                assembled_prompt = assemble_step_prompt(
                    session,
                    step_key="sow",
                    project_id=version.project_id,
                    block_nonce=f"{version_id}-repair",
                    user_inputs=ctx.user_inputs,
                )
            excerpt = project_estimate_for_prompt(
                ctx.estimate_content or {}, ctx.user_inputs
            )
            repair_prompt = sow_repair.build_repair_prompt(
                missing_keys=missing,
                context_excerpt=json.dumps(excerpt, ensure_ascii=False)[:6000],
                block_nonce=f"{version_id}-repair",
            )
            repair_result = generate_structured_result(
                repair_prompt,
                SowDeliverablesRepairOutput,
                system=sow_repair.SYSTEM_INSTRUCTION,
                deadline=deadline,
                max_output_tokens=defn.max_output_tokens,
            )
            api_attempts += repair_result.api_attempt_count
            merged = merge_deliverable_repair(merged, repair_result.data.deliverables)
        except (LLMError, PromptAssemblyError):
            pass

    stored, validation_notes = postprocess_sow(merged, ctx)
    notes_meta["validation_notes"] = validation_notes
    assert isinstance(stored, SowStored)
    return stored, notes_meta, api_attempts

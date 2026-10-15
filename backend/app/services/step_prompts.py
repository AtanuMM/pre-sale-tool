"""Assemble step prompts (scope v1 unchanged; generic path for other steps)."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.llm.prompts import generic_revise_v4 as generic_revise
from app.llm.prompts.assembly import build_untrusted_preamble, build_user_inputs_block
from app.llm.prompts.estimate import repair_v2 as estimate_repair_v2
from app.llm.prompts.estimate import v2 as estimate_v2
from app.llm.prompts.feature_list import v2 as feature_list_v2
from app.llm.prompts.gap_analysis import v2 as gap_v2
from app.llm.prompts.scope_analysis import revise_v1
from app.llm.prompts.scope_analysis.v1 import (
    PROMPT_VERSION,
    SYSTEM_INSTRUCTION,
    IntakeItemPayload,
    build_user_prompt,
)
from app.llm.prompts.sow import v1 as sow_v1
from app.models.steps import StepVersion
from app.services.prompt_intake import (
    build_intake_payloads,
    load_initial_intake,
    project_has_readable_content,
)
from app.steps.definitions import StepDefinition, get_step
from app.steps.schemas.scope_analysis import ScopeAnalysisOutput
from app.steps.sow_assemble import build_assembled
from app.steps.sow_projection import (
    build_prompt_context_json,
    estimated_roles_from_inputs,
)

# Re-export for existing imports
__all__ = [
    "AssembledPrompt",
    "apply_soft_list_caps_legacy_scope",
    "assemble_scope_analysis_prompt",
    "assemble_scope_analysis_revise_prompt",
    "assemble_step_prompt",
    "assemble_step_revise_prompt",
    "project_has_readable_content",
]


@dataclass(frozen=True)
class AssembledPrompt:
    user_prompt: str
    system_instruction: str
    prompt_version: str
    inputs_metadata: dict


def assemble_scope_analysis_prompt(
    session: Session,
    *,
    project_id: uuid.UUID,
    block_nonce: str,
) -> AssembledPrompt:
    settings = get_settings()
    project, inp = load_initial_intake(session, project_id)
    metadata: dict = {}
    body, attachment_payloads = build_intake_payloads(
        inp, max_prompt_chars=settings.MAX_PROMPT_CHARS, metadata=metadata
    )
    intake_items = [
        IntakeItemPayload(
            received_at=inp.received_at,
            kind=inp.kind,  # type: ignore[arg-type]
            subject=inp.subject,
            body=body,
        )
    ]

    user_prompt = build_user_prompt(
        project_name=project.name,
        client_name=project.client_name,
        intake_items=intake_items,
        attachment_texts=attachment_payloads,
        block_nonce=block_nonce,
    )

    return AssembledPrompt(
        user_prompt=user_prompt,
        system_instruction=SYSTEM_INSTRUCTION,
        prompt_version=PROMPT_VERSION,
        inputs_metadata=metadata,
    )


def assemble_scope_analysis_revise_prompt(
    session: Session,
    *,
    project_id: uuid.UUID,
    base_version_id: uuid.UUID,
    reviewer_instructions: str,
    block_nonce: str,
) -> AssembledPrompt:
    settings = get_settings()
    project, inp = load_initial_intake(session, project_id)
    base = session.get(StepVersion, base_version_id)
    if base is None or base.content is None:
        raise ValueError("base version content missing")
    previous_json = json.dumps(base.content, ensure_ascii=False)
    reserved = len(previous_json) + len(reviewer_instructions) + 512
    intake_budget = max(1000, settings.MAX_PROMPT_CHARS - reserved)
    metadata: dict = {"revise_base_version_id": str(base_version_id)}
    body, attachment_payloads = build_intake_payloads(
        inp, max_prompt_chars=intake_budget, metadata=metadata
    )
    if len(previous_json) + intake_budget > settings.MAX_PROMPT_CHARS:
        cut = len(previous_json) - (settings.MAX_PROMPT_CHARS - intake_budget - 256)
        if cut > 0:
            previous_json = previous_json[: max(0, len(previous_json) - cut)]
            metadata.setdefault("prompt_truncation", [])
            metadata["prompt_truncation"].append(
                {"source": "previous_analysis", "chars_removed": cut}
            )

    intake_items = [
        IntakeItemPayload(
            received_at=inp.received_at,
            kind=inp.kind,  # type: ignore[arg-type]
            subject=inp.subject,
            body=body,
        )
    ]
    user_prompt = revise_v1.build_revise_user_prompt(
        project_name=project.name,
        client_name=project.client_name,
        intake_items=intake_items,
        attachment_texts=attachment_payloads,
        client_block_nonce=f"{block_nonce}-client",
        previous_analysis_json=previous_json,
        previous_block_nonce=f"{block_nonce}-prev",
        reviewer_instructions=reviewer_instructions,
        instructions_block_nonce=f"{block_nonce}-instr",
    )

    return AssembledPrompt(
        user_prompt=user_prompt,
        system_instruction=revise_v1.SYSTEM_INSTRUCTION,
        prompt_version=revise_v1.PROMPT_VERSION,
        inputs_metadata=metadata,
    )


def _assemble_gap_generate(
    session: Session,
    *,
    project_id: uuid.UUID,
    block_nonce: str,
) -> AssembledPrompt:
    project, _ = load_initial_intake(session, project_id)
    defn = get_step("gap_analysis")
    metadata: dict = {}
    preamble = build_untrusted_preamble(
        session,
        project_id,
        context_steps=defn.context_steps,
        block_nonce=block_nonce,
        tail_reserve=768,
        metadata=metadata,
    )
    user_prompt = gap_v2.build_user_prompt(
        project_name=project.name,
        client_name=project.client_name,
        untrusted_preamble=preamble,
    )
    return AssembledPrompt(
        user_prompt=user_prompt,
        system_instruction=gap_v2.SYSTEM_INSTRUCTION,
        prompt_version=gap_v2.PROMPT_VERSION,
        inputs_metadata=metadata,
    )


def _user_inputs_from_version(version: StepVersion) -> dict[str, Any]:
    raw = (version.inputs or {}).get("user_inputs")
    if not isinstance(raw, dict):
        return {}
    return dict(raw)


def _estimated_role_names(user_inputs: dict[str, Any]) -> list[str]:
    return [name for name, _disc in _estimated_roles_with_discipline(user_inputs)]


def _estimated_roles_with_discipline(user_inputs: dict[str, Any]) -> list[tuple[str, str]]:
    team = user_inputs.get("team")
    if not isinstance(team, list):
        return []
    out: list[tuple[str, str]] = []
    for row in team:
        if not isinstance(row, dict):
            continue
        if row.get("mode") != "estimated":
            continue
        role = str(row.get("role") or "").strip()
        if not role:
            continue
        discipline = str(row.get("discipline") or "other").strip() or "other"
        out.append((role, discipline))
    return out


def _selected_phase_keys(user_inputs: dict[str, Any]) -> list[str]:
    raw = user_inputs.get("phases")
    if not isinstance(raw, list):
        return ["mvp"]
    return [str(p) for p in raw]


def _estimate_input_blocks(
    user_inputs: dict[str, Any], *, block_nonce: str
) -> tuple[str, int]:
    notes_block, notes_chars = build_user_inputs_block(
        get_step("estimate").input_fields, user_inputs, block_nonce=block_nonce
    )
    roles_block = estimate_v2.build_roles_block(
        _estimated_roles_with_discipline(user_inputs),
        block_nonce=f"{block_nonce}-roles",
    )
    phases_block = estimate_v2.build_phases_block(
        _selected_phase_keys(user_inputs), block_nonce=f"{block_nonce}-phases"
    )
    extra = "\n\n".join(p for p in (notes_block, roles_block, phases_block) if p)
    return extra, notes_chars + len(roles_block) + len(phases_block)


def _model_facing_content(content: dict) -> dict:
    if content.get("schema_version") == 1 and "narrative" in content:
        narrative = content.get("narrative")
        return narrative if isinstance(narrative, dict) else {}
    return {k: v for k, v in content.items() if k != "computed"}


def _approved_content_dict(
    session: Session, project_id: uuid.UUID, step_key: str
) -> dict:
    row = session.scalar(
        select(StepVersion).where(
            StepVersion.project_id == project_id,
            StepVersion.step_key == step_key,
            StepVersion.status == "approved",
        )
    )
    if row is None or not isinstance(row.content, dict):
        raise PromptAssemblyError(f"Missing approved output for step {step_key}")
    return row.content


def _assemble_sow_generate(
    session: Session,
    *,
    project_id: uuid.UUID,
    block_nonce: str,
    user_inputs: dict[str, Any],
) -> AssembledPrompt:
    project, _ = load_initial_intake(session, project_id)
    scope = _approved_content_dict(session, project_id, "scope_analysis")
    gap = _approved_content_dict(session, project_id, "gap_analysis")
    feature_list = _approved_content_dict(session, project_id, "feature_list")
    estimate = _approved_content_dict(session, project_id, "estimate")
    if estimate.get("schema_version") != 2:
        raise PromptAssemblyError("Approved estimate must be version 2 for SOW generation")
    estimate_inputs_row = session.scalar(
        select(StepVersion).where(
            StepVersion.project_id == project_id,
            StepVersion.step_key == "estimate",
            StepVersion.status == "approved",
        )
    )
    estimate_user_inputs: dict[str, Any] = {}
    if estimate_inputs_row and isinstance(estimate_inputs_row.inputs, dict):
        raw = estimate_inputs_row.inputs.get("user_inputs")
        if isinstance(raw, dict):
            estimate_user_inputs = raw
    assembled = build_assembled(
        project_id=str(project_id),
        version_no=1,
        status_text="In review",
        user_inputs=user_inputs,
        scope=scope,
        gap=gap,
        feature_list=feature_list,
        estimate=estimate,
        estimate_user_inputs=estimate_user_inputs,
    )
    metadata: dict = {}
    notes_block, notes_chars = build_user_inputs_block(
        get_step("sow").input_fields, user_inputs, block_nonce=block_nonce
    )
    context_json = build_prompt_context_json(
        scope=scope,
        gap=gap,
        feature_list=feature_list,
        estimate=estimate,
        estimate_user_inputs=estimate_user_inputs,
    )
    preamble = build_untrusted_preamble(
        session,
        project_id,
        context_steps=(),
        block_nonce=block_nonce,
        tail_reserve=len(context_json) + notes_chars + 4096,
        metadata=metadata,
        notes_chars=notes_chars,
    )
    user_prompt = sow_v1.build_user_prompt(
        project_name=project.name,
        client_name=project.client_name,
        untrusted_preamble=preamble,
        projected_context=context_json,
        bundle_keys=assembled.bundle_keys,
        roles=estimated_roles_from_inputs(estimate_user_inputs),
        notes_block=notes_block,
        block_nonce=block_nonce,
    )
    return AssembledPrompt(
        user_prompt=user_prompt,
        system_instruction=sow_v1.SYSTEM_INSTRUCTION,
        prompt_version=sow_v1.PROMPT_VERSION,
        inputs_metadata=metadata,
    )


def _assemble_feature_list_generate(
    session: Session,
    *,
    project_id: uuid.UUID,
    block_nonce: str,
    user_inputs: dict[str, Any],
) -> AssembledPrompt:
    project, _ = load_initial_intake(session, project_id)
    defn = get_step("feature_list")
    metadata: dict = {}
    notes_block, notes_chars = build_user_inputs_block(
        defn.input_fields, user_inputs, block_nonce=block_nonce
    )
    preamble = build_untrusted_preamble(
        session,
        project_id,
        context_steps=defn.context_steps,
        block_nonce=block_nonce,
        tail_reserve=notes_chars + 2048,
        metadata=metadata,
        notes_chars=notes_chars,
    )
    user_prompt = feature_list_v2.build_user_prompt(
        project_name=project.name,
        client_name=project.client_name,
        untrusted_preamble=preamble,
        notes_block=notes_block,
    )
    return AssembledPrompt(
        user_prompt=user_prompt,
        system_instruction=feature_list_v2.SYSTEM_INSTRUCTION,
        prompt_version=feature_list_v2.PROMPT_VERSION,
        inputs_metadata=metadata,
    )


def _assemble_estimate_generate(
    session: Session,
    *,
    project_id: uuid.UUID,
    block_nonce: str,
    user_inputs: dict[str, Any],
) -> AssembledPrompt:
    project, _ = load_initial_intake(session, project_id)
    defn = get_step("estimate")
    metadata: dict = {}
    _extra, extra_chars = _estimate_input_blocks(user_inputs, block_nonce=block_nonce)
    preamble = build_untrusted_preamble(
        session,
        project_id,
        context_steps=defn.context_steps,
        block_nonce=block_nonce,
        tail_reserve=extra_chars + 2048,
        metadata=metadata,
        notes_chars=extra_chars,
    )
    notes_block, _ = build_user_inputs_block(
        defn.input_fields, user_inputs, block_nonce=block_nonce
    )
    user_prompt = estimate_v2.build_user_prompt(
        project_name=project.name,
        client_name=project.client_name,
        untrusted_preamble=preamble,
        notes_block=notes_block,
        roles_block=estimate_v2.build_roles_block(
            _estimated_roles_with_discipline(user_inputs),
            block_nonce=f"{block_nonce}-roles",
        ),
        phases_block=estimate_v2.build_phases_block(
            _selected_phase_keys(user_inputs), block_nonce=f"{block_nonce}-phases"
        ),
    )
    return AssembledPrompt(
        user_prompt=user_prompt,
        system_instruction=estimate_v2.SYSTEM_INSTRUCTION,
        prompt_version=estimate_v2.PROMPT_VERSION,
        inputs_metadata=metadata,
    )


def assemble_estimate_batch_prompt(
    session: Session,
    *,
    project_id: uuid.UUID,
    block_nonce: str,
    user_inputs: dict[str, Any],
    feature_ids: list[str],
    work_package_ids: list[str],
    planning_excerpt: str,
) -> AssembledPrompt:
    project, _ = load_initial_intake(session, project_id)
    defn = get_step("estimate")
    metadata: dict = {"batch": True, "batch_feature_count": len(feature_ids)}
    _extra, extra_chars = _estimate_input_blocks(user_inputs, block_nonce=block_nonce)
    features_block = estimate_v2.build_id_list_block(
        "Feature ids in this batch", feature_ids, block_nonce=f"{block_nonce}-feat"
    )
    wp_block = estimate_v2.build_id_list_block(
        "Work package ids to estimate in this batch",
        work_package_ids,
        block_nonce=f"{block_nonce}-wp",
    )
    planning_block = estimate_v2.build_id_list_block(
        "Planning excerpt (components, packages, assumptions)",
        [planning_excerpt] if planning_excerpt else [],
        block_nonce=f"{block_nonce}-plan",
    )
    preamble = build_untrusted_preamble(
        session,
        project_id,
        context_steps=defn.context_steps,
        block_nonce=block_nonce,
        tail_reserve=extra_chars
        + len(features_block)
        + len(wp_block)
        + len(planning_block)
        + 2048,
        metadata=metadata,
        notes_chars=extra_chars,
    )
    notes_block, _ = build_user_inputs_block(
        defn.input_fields, user_inputs, block_nonce=block_nonce
    )
    user_prompt = estimate_v2.build_batch_prompt(
        project_name=project.name,
        client_name=project.client_name,
        untrusted_preamble=preamble,
        notes_block=notes_block,
        roles_block=estimate_v2.build_roles_block(
            _estimated_roles_with_discipline(user_inputs),
            block_nonce=f"{block_nonce}-roles",
        ),
        phases_block=estimate_v2.build_phases_block(
            _selected_phase_keys(user_inputs), block_nonce=f"{block_nonce}-phases"
        ),
        feature_ids_block=features_block,
        work_package_ids_block=wp_block,
        planning_excerpt_block=planning_block,
    )
    return AssembledPrompt(
        user_prompt=user_prompt,
        system_instruction=estimate_v2.BATCH_SYSTEM_INSTRUCTION,
        prompt_version=estimate_v2.PROMPT_VERSION,
        inputs_metadata=metadata,
    )


def assemble_estimate_packages_repair_prompt(
    session: Session,
    *,
    project_id: uuid.UUID,
    block_nonce: str,
    user_inputs: dict[str, Any],
    missing_types: list[str],
) -> AssembledPrompt:
    project, _ = load_initial_intake(session, project_id)
    defn = get_step("estimate")
    metadata: dict = {"repair": True}
    _extra, extra_chars = _estimate_input_blocks(user_inputs, block_nonce=block_nonce)
    missing_block = estimate_repair_v2.build_type_list_block(
        missing_types, block_nonce=f"{block_nonce}-mt"
    )
    preamble = build_untrusted_preamble(
        session,
        project_id,
        context_steps=defn.context_steps,
        block_nonce=block_nonce,
        tail_reserve=extra_chars + len(missing_block) + 2048,
        metadata=metadata,
        notes_chars=extra_chars,
    )
    notes_block, _ = build_user_inputs_block(
        defn.input_fields, user_inputs, block_nonce=block_nonce
    )
    user_prompt = estimate_repair_v2.build_repair_prompt(
        project_name=project.name,
        client_name=project.client_name,
        untrusted_preamble=preamble,
        notes_block=notes_block,
        roles_block=estimate_v2.build_roles_block(
            _estimated_roles_with_discipline(user_inputs),
            block_nonce=f"{block_nonce}-roles",
        ),
        phases_block=estimate_v2.build_phases_block(
            _selected_phase_keys(user_inputs), block_nonce=f"{block_nonce}-phases"
        ),
        missing_types_block=missing_block,
    )
    return AssembledPrompt(
        user_prompt=user_prompt,
        system_instruction=estimate_repair_v2.SYSTEM_INSTRUCTION,
        prompt_version=estimate_repair_v2.PROMPT_VERSION,
        inputs_metadata=metadata,
    )


def _assemble_generic_revise(
    session: Session,
    *,
    project_id: uuid.UUID,
    defn: StepDefinition,
    base_version_id: uuid.UUID,
    reviewer_instructions: str,
    block_nonce: str,
    user_inputs: dict[str, Any],
) -> AssembledPrompt:
    project, _ = load_initial_intake(session, project_id)
    base = session.get(StepVersion, base_version_id)
    if base is None or base.content is None:
        raise ValueError("base version content missing")
    facing = base.content if isinstance(base.content, dict) else {}
    previous_json = json.dumps(_model_facing_content(facing), ensure_ascii=False)
    metadata: dict = {"revise_base_version_id": str(base_version_id)}
    if defn.key == "estimate":
        notes_block, notes_chars = _estimate_input_blocks(
            user_inputs, block_nonce=block_nonce
        )
    else:
        notes_block, notes_chars = build_user_inputs_block(
            defn.input_fields, user_inputs, block_nonce=block_nonce
        )
    preamble = build_untrusted_preamble(
        session,
        project_id,
        context_steps=defn.context_steps,
        block_nonce=block_nonce,
        tail_reserve=len(previous_json)
        + len(reviewer_instructions)
        + notes_chars
        + 1024,
        metadata=metadata,
        notes_chars=notes_chars,
    )
    user_prompt = generic_revise.build_revise_user_prompt(
        project_name=project.name,
        client_name=project.client_name,
        untrusted_preamble=preamble,
        previous_output_json=previous_json,
        reviewer_instructions=reviewer_instructions,
        previous_block_nonce=f"{block_nonce}-prev",
        instructions_block_nonce=f"{block_nonce}-instr",
        user_inputs_block=notes_block,
    )
    return AssembledPrompt(
        user_prompt=user_prompt,
        system_instruction=generic_revise.SYSTEM_INSTRUCTION,
        prompt_version=generic_revise.PROMPT_VERSION,
        inputs_metadata=metadata,
    )


def assemble_step_prompt(
    session: Session,
    *,
    step_key: str,
    project_id: uuid.UUID,
    block_nonce: str,
    user_inputs: dict[str, Any] | None = None,
) -> AssembledPrompt:
    if step_key == "scope_analysis":
        return assemble_scope_analysis_prompt(
            session, project_id=project_id, block_nonce=block_nonce
        )
    if step_key == "gap_analysis":
        return _assemble_gap_generate(
            session, project_id=project_id, block_nonce=block_nonce
        )
    if step_key == "feature_list":
        return _assemble_feature_list_generate(
            session,
            project_id=project_id,
            block_nonce=block_nonce,
            user_inputs=user_inputs or {},
        )
    if step_key == "estimate":
        return _assemble_estimate_generate(
            session,
            project_id=project_id,
            block_nonce=block_nonce,
            user_inputs=user_inputs or {},
        )
    if step_key == "sow":
        return _assemble_sow_generate(
            session,
            project_id=project_id,
            block_nonce=block_nonce,
            user_inputs=user_inputs or {},
        )
    raise ValueError(f"Prompt assembly not configured for step {step_key}")


def assemble_step_revise_prompt(
    session: Session,
    *,
    step_key: str,
    project_id: uuid.UUID,
    base_version_id: uuid.UUID,
    reviewer_instructions: str,
    block_nonce: str,
    user_inputs: dict[str, Any] | None = None,
) -> AssembledPrompt:
    defn = get_step(step_key)
    if defn.uses_scope_revise_prompt:
        return assemble_scope_analysis_revise_prompt(
            session,
            project_id=project_id,
            base_version_id=base_version_id,
            reviewer_instructions=reviewer_instructions,
            block_nonce=block_nonce,
        )
    resolved = user_inputs
    if resolved is None:
        base = session.get(StepVersion, base_version_id)
        resolved = _user_inputs_from_version(base) if base is not None else {}
    if step_key == "sow":
        project, _ = load_initial_intake(session, project_id)
        base = session.get(StepVersion, base_version_id)
        if base is None or base.content is None:
            raise ValueError("base version content missing")
        facing = base.content if isinstance(base.content, dict) else {}
        previous_json = json.dumps(_model_facing_content(facing), ensure_ascii=False)
        scope = _approved_content_dict(session, project_id, "scope_analysis")
        gap = _approved_content_dict(session, project_id, "gap_analysis")
        feature_list = _approved_content_dict(session, project_id, "feature_list")
        estimate = _approved_content_dict(session, project_id, "estimate")
        estimate_user_inputs: dict[str, Any] = {}
        est_row = session.scalar(
            select(StepVersion).where(
                StepVersion.project_id == project_id,
                StepVersion.step_key == "estimate",
                StepVersion.status == "approved",
            )
        )
        if est_row and isinstance(est_row.inputs, dict):
            raw = est_row.inputs.get("user_inputs")
            if isinstance(raw, dict):
                estimate_user_inputs = raw
        context_json = build_prompt_context_json(
            scope=scope,
            gap=gap,
            feature_list=feature_list,
            estimate=estimate,
            estimate_user_inputs=estimate_user_inputs,
        )
        notes_block, notes_chars = build_user_inputs_block(
            get_step("sow").input_fields, resolved, block_nonce=block_nonce
        )
        metadata: dict = {"revise_base_version_id": str(base_version_id)}
        assembled = build_assembled(
            project_id=str(project_id),
            version_no=base.version_no,
            status_text="In review",
            user_inputs=resolved,
            scope=scope,
            gap=gap,
            feature_list=feature_list,
            estimate=estimate,
            estimate_user_inputs=estimate_user_inputs,
        )
        preamble = build_untrusted_preamble(
            session,
            project_id,
            context_steps=(),
            block_nonce=block_nonce,
            tail_reserve=len(previous_json)
            + len(reviewer_instructions)
            + len(context_json)
            + notes_chars
            + 1024,
            metadata=metadata,
            notes_chars=notes_chars,
        )
        context_block = sow_v1.build_user_prompt(
            project_name=project.name,
            client_name=project.client_name,
            untrusted_preamble=preamble,
            projected_context=context_json,
            bundle_keys=assembled.bundle_keys,
            roles=estimated_roles_from_inputs(estimate_user_inputs),
            notes_block="",
            block_nonce=block_nonce,
        )
        user_prompt = generic_revise.build_revise_user_prompt(
            project_name=project.name,
            client_name=project.client_name,
            untrusted_preamble=context_block,
            previous_output_json=previous_json,
            reviewer_instructions=reviewer_instructions,
            previous_block_nonce=f"{block_nonce}-prev",
            instructions_block_nonce=f"{block_nonce}-instr",
            user_inputs_block=notes_block,
        )
        return AssembledPrompt(
            user_prompt=user_prompt,
            system_instruction=sow_v1.SYSTEM_INSTRUCTION,
            prompt_version=sow_v1.PROMPT_VERSION,
            inputs_metadata=metadata,
        )
    return _assemble_generic_revise(
        session,
        project_id=project_id,
        defn=defn,
        base_version_id=base_version_id,
        reviewer_instructions=reviewer_instructions,
        block_nonce=block_nonce,
        user_inputs=resolved,
    )


def apply_soft_list_caps_legacy_scope(
    content: ScopeAnalysisOutput,
) -> tuple[dict, ScopeAnalysisOutput]:
    """Backward-compatible wrapper; prefer app.services.step_soft_caps."""
    from app.services.step_soft_caps import apply_soft_list_caps

    defn = get_step("scope_analysis")
    meta, trimmed = apply_soft_list_caps(defn, content)
    return meta, trimmed  # type: ignore[return-value]

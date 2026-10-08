"""Assemble step prompts (scope v1 unchanged; generic path for other steps)."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.config import get_settings
from app.llm.prompts import generic_revise
from app.llm.prompts.assembly import build_untrusted_preamble
from app.llm.prompts.gap_analysis import v1 as gap_v1
from app.llm.prompts.scope_analysis import revise_v1
from app.llm.prompts.scope_analysis.v1 import (
    PROMPT_VERSION,
    SYSTEM_INSTRUCTION,
    IntakeItemPayload,
    build_user_prompt,
)
from app.models.steps import StepVersion
from app.services.prompt_intake import (
    build_intake_payloads,
    load_initial_intake,
    project_has_readable_content,
)
from app.steps.definitions import StepDefinition, get_step
from app.steps.schemas.scope_analysis import ScopeAnalysisOutput

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
    user_prompt = gap_v1.build_user_prompt(
        project_name=project.name,
        client_name=project.client_name,
        untrusted_preamble=preamble,
    )
    return AssembledPrompt(
        user_prompt=user_prompt,
        system_instruction=gap_v1.SYSTEM_INSTRUCTION,
        prompt_version=gap_v1.PROMPT_VERSION,
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
) -> AssembledPrompt:
    project, _ = load_initial_intake(session, project_id)
    base = session.get(StepVersion, base_version_id)
    if base is None or base.content is None:
        raise ValueError("base version content missing")
    previous_json = json.dumps(base.content, ensure_ascii=False)
    metadata: dict = {"revise_base_version_id": str(base_version_id)}
    preamble = build_untrusted_preamble(
        session,
        project_id,
        context_steps=defn.context_steps,
        block_nonce=block_nonce,
        tail_reserve=len(previous_json) + len(reviewer_instructions) + 1024,
        metadata=metadata,
    )
    user_prompt = generic_revise.build_revise_user_prompt(
        project_name=project.name,
        client_name=project.client_name,
        untrusted_preamble=preamble,
        previous_output_json=previous_json,
        reviewer_instructions=reviewer_instructions,
        previous_block_nonce=f"{block_nonce}-prev",
        instructions_block_nonce=f"{block_nonce}-instr",
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
) -> AssembledPrompt:
    if step_key == "scope_analysis":
        return assemble_scope_analysis_prompt(
            session, project_id=project_id, block_nonce=block_nonce
        )
    if step_key == "gap_analysis":
        return _assemble_gap_generate(
            session, project_id=project_id, block_nonce=block_nonce
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
    return _assemble_generic_revise(
        session,
        project_id=project_id,
        defn=defn,
        base_version_id=base_version_id,
        reviewer_instructions=reviewer_instructions,
        block_nonce=block_nonce,
    )


def apply_soft_list_caps_legacy_scope(
    content: ScopeAnalysisOutput,
) -> tuple[dict, ScopeAnalysisOutput]:
    """Backward-compatible wrapper; prefer app.services.step_soft_caps."""
    from app.services.step_soft_caps import apply_soft_list_caps

    defn = get_step("scope_analysis")
    meta, trimmed = apply_soft_list_caps(defn, content)
    return meta, trimmed  # type: ignore[return-value]

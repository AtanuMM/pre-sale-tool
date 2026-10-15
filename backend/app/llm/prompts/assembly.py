"""Generic prompt block assembly (intake + context steps)."""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.llm.prompts.scope_analysis.blocks import wrap_untrusted
from app.llm.prompts.scope_analysis.v1 import IntakeItemPayload
from app.models.steps import StepVersion
from app.services.prompt_intake import build_intake_payloads, load_initial_intake
from app.steps.definitions import get_step
from app.steps.input_fields import InputFieldSpec
from app.steps.refs import annotate_content_with_refs

ERR_PROMPT_TOO_LARGE = (
    "Prompt would exceed the size limit even after truncating intake; "
    "reduce attachment size or split the project."
)
ERR_NOTES_TOO_LARGE = "Notes exceed the prompt size limit; shorten them."


class PromptAssemblyError(ValueError):
    pass


def _approved_content_json(
    session: Session,
    project_id: uuid.UUID,
    step_key: str,
) -> str:
    row = session.scalar(
        select(StepVersion).where(
            StepVersion.project_id == project_id,
            StepVersion.step_key == step_key,
            StepVersion.status == "approved",
        )
    )
    if row is None or row.content is None:
        raise PromptAssemblyError(f"Missing approved output for step {step_key}")
    annotated = annotate_content_with_refs(get_step(step_key).layout, row.content)
    return json.dumps(annotated, ensure_ascii=False)


def build_context_block_lines(
    session: Session,
    project_id: uuid.UUID,
    context_steps: tuple[str, ...],
    block_nonce: str,
) -> tuple[list[str], int]:
    parts: list[str] = []
    total_chars = 0
    for step_key in context_steps:
        defn = get_step(step_key)
        payload = _approved_content_json(session, project_id, step_key)
        total_chars += len(payload)
        parts.append("")
        parts.append(f"Approved output: {defn.title} ({step_key}) (untrusted data):")
        parts.append(
            wrap_untrusted(payload, block_nonce=f"{block_nonce}-ctx-{step_key}")
        )
    return parts, total_chars


def compute_intake_budget(
    context_char_count: int, tail_reserve: int, *, notes_chars: int = 0
) -> int:
    settings = get_settings()
    fixed = context_char_count + tail_reserve + 4096
    if fixed >= settings.MAX_PROMPT_CHARS:
        if notes_chars > 0 and (fixed - notes_chars) < settings.MAX_PROMPT_CHARS:
            raise PromptAssemblyError(ERR_NOTES_TOO_LARGE)
        raise PromptAssemblyError(ERR_PROMPT_TOO_LARGE)
    return settings.MAX_PROMPT_CHARS - fixed


def build_user_inputs_block(
    field_specs: tuple[InputFieldSpec, ...],
    user_inputs: dict[str, Any],
    *,
    block_nonce: str,
) -> tuple[str, int]:
    lines: list[str] = []
    for spec in field_specs:
        if spec.kind not in ("textarea", "text"):
            continue
        text = user_inputs.get(spec.key)
        if not isinstance(text, str) or not text:
            continue
        lines.append(f"{spec.label} (untrusted data):")
        lines.append(wrap_untrusted(text, block_nonce=f"{block_nonce}-ui-{spec.key}"))
        lines.append("")
    block = "\n".join(lines).rstrip()
    return block, len(block)


def build_intake_wrapped_lines(
    session: Session,
    project_id: uuid.UUID,
    *,
    intake_budget: int,
    metadata: dict,
    block_nonce: str,
) -> tuple[list[str], int]:
    _project, inp = load_initial_intake(session, project_id)
    body, attachment_payloads = build_intake_payloads(
        inp, max_prompt_chars=intake_budget, metadata=metadata
    )
    intake_items = [
        IntakeItemPayload(
            received_at=inp.received_at,
            kind=inp.kind,  # type: ignore[arg-type]
            subject=inp.subject,
            body=body,
        )
    ]
    lines: list[str] = [
        "Initial client communication (untrusted data follows):",
    ]
    char_count = len(lines[0])
    for index, item in enumerate(intake_items, start=1):
        header = f"Intake item {index} ({item.kind}, received {item.received_at.isoformat()})"
        body_text = item.body or ""
        if item.subject:
            body_text = f"Subject: {item.subject}\n{body_text}"
        wrapped = wrap_untrusted(body_text, block_nonce=f"{block_nonce}-intake-{index}")
        lines.extend([header, wrapped])
        char_count += len(header) + len(wrapped)

    if attachment_payloads:
        lines.append("")
        lines.append("Attachment extracted text (untrusted data):")
        char_count += len(lines[-2]) + len(lines[-1])
        for i, attachment in enumerate(attachment_payloads, start=1):
            lines.append(f"Attachment: {attachment.label}")
            wrapped = wrap_untrusted(
                attachment.text, block_nonce=f"{block_nonce}-att-{i}"
            )
            lines.extend([wrapped])
            char_count += len(lines[-2]) + len(wrapped)

    return lines, char_count


def build_untrusted_preamble(
    session: Session,
    project_id: uuid.UUID,
    *,
    context_steps: tuple[str, ...],
    block_nonce: str,
    tail_reserve: int,
    metadata: dict,
    notes_chars: int = 0,
) -> str:
    ctx_parts, ctx_chars = build_context_block_lines(
        session, project_id, context_steps, block_nonce
    )
    intake_budget = compute_intake_budget(
        ctx_chars, tail_reserve, notes_chars=notes_chars
    )
    intake_lines, _ = build_intake_wrapped_lines(
        session,
        project_id,
        intake_budget=intake_budget,
        metadata=metadata,
        block_nonce=block_nonce,
    )
    preamble_parts = [*intake_lines, *ctx_parts]
    full = "\n".join(preamble_parts)
    settings = get_settings()
    if len(full) + tail_reserve > settings.MAX_PROMPT_CHARS:
        raise PromptAssemblyError(ERR_PROMPT_TOO_LARGE)
    return full

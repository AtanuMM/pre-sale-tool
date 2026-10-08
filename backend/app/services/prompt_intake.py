"""Intake loading and truncation for prompt assembly."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.llm.prompts.scope_analysis.v1 import AttachmentTextPayload
from app.models.projects import Project, ProjectInput, ProjectInputFile


def empty_extraction_label() -> str:
    return "no text could be extracted"


def load_initial_intake(session: Session, project_id: uuid.UUID) -> tuple[Project, ProjectInput]:
    project = session.get(Project, project_id)
    if project is None:
        raise ValueError("project not found")
    inp = session.scalar(
        select(ProjectInput)
        .where(
            ProjectInput.project_id == project_id,
            ProjectInput.is_followup.is_(False),
        )
        .options(
            selectinload(ProjectInput.file_links).selectinload(ProjectInputFile.file)
        )
    )
    if inp is None:
        raise ValueError("initial intake missing")
    return project, inp


def project_has_readable_content(session: Session, project_id: uuid.UUID) -> bool:
    try:
        _, inp = load_initial_intake(session, project_id)
    except ValueError:
        return False
    if (inp.body or "").strip():
        return True
    for link in inp.file_links:
        text = link.file.extracted_text if link.file else None
        if text and text.strip():
            return True
    return False


def truncate_text(text: str, max_chars: int) -> tuple[str, int]:
    if max_chars <= 0:
        return "", len(text)
    if len(text) <= max_chars:
        return text, 0
    return text[:max_chars], len(text) - max_chars


def build_intake_payloads(
    inp: ProjectInput,
    *,
    max_prompt_chars: int,
    metadata: dict,
) -> tuple[str, list[AttachmentTextPayload]]:
    files: list[tuple[uuid.UUID, str, str]] = []
    for link in inp.file_links:
        f = link.file
        if f is None:
            continue
        label = f.original_name
        raw = (f.extracted_text or "").strip()
        files.append((f.id, label, raw))

    body = inp.body or ""

    body, body_removed = truncate_text(body, max_prompt_chars)
    if body_removed:
        metadata.setdefault("prompt_truncation", [])
        metadata["prompt_truncation"].append(
            {"source": "intake_body", "chars_removed": body_removed}
        )

    remaining = max_prompt_chars - len(body)
    attachment_payloads: list[AttachmentTextPayload] = []
    truncations: list[dict] = []

    sized = [
        (fid, label, text if text else empty_extraction_label()) for fid, label, text in files
    ]
    sized.sort(key=lambda t: len(t[2]), reverse=True)

    for fid, label, text in sized:
        if len(text) <= remaining:
            attachment_payloads.append(AttachmentTextPayload(label=label, text=text))
            remaining -= len(text) + len(label) + 32
            continue
        if remaining <= 0:
            cut = len(text)
            truncations.append({"file_id": str(fid), "chars_removed": cut})
            attachment_payloads.append(
                AttachmentTextPayload(
                    label=label,
                    text="[attachment omitted due to size cap]",
                )
            )
            continue
        allowed = max(0, remaining - 64)
        trimmed, removed = truncate_text(text, allowed)
        truncations.append({"file_id": str(fid), "chars_removed": removed})
        attachment_payloads.append(AttachmentTextPayload(label=label, text=trimmed))
        remaining -= len(trimmed)

    if truncations:
        metadata["prompt_truncation"] = metadata.get("prompt_truncation", []) + truncations

    return body, attachment_payloads

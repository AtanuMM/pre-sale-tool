"""Read models for workflow steps and versions."""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.auth import User
from app.models.steps import Approval, StepVersion
from app.schemas.steps import (
    ApprovalOut,
    ProjectStepOut,
    ProjectStepsOut,
    StepContextStepOut,
    StepVersionDetailOut,
    StepVersionSummaryOut,
)
from app.services.step_state import (
    VersionSnapshot,
    blocked_reason_for_step,
    can_generate,
    derive_step_status,
)
from app.services.step_version_context import compute_step_action_flags
from app.steps.definitions import get_step, ordered_steps
from app.steps.layout_config import layout_to_api


def _user_display_name(user: User | None) -> str | None:
    if user is None:
        return None
    return user.full_name or user.email


def _versions_by_step(session: Session, project_id: uuid.UUID) -> dict[str, list[VersionSnapshot]]:
    rows = session.scalars(
        select(StepVersion).where(StepVersion.project_id == project_id)
    ).all()
    grouped: dict[str, list[VersionSnapshot]] = {}
    for row in rows:
        grouped.setdefault(row.step_key, []).append(
            VersionSnapshot(version_no=row.version_no, status=row.status)
        )
    return grouped


def _latest_version_row(
    session: Session, project_id: uuid.UUID, step_key: str
) -> StepVersion | None:
    return session.scalar(
        select(StepVersion)
        .where(StepVersion.project_id == project_id, StepVersion.step_key == step_key)
        .order_by(StepVersion.version_no.desc())
        .limit(1)
    )


def version_to_summary(session: Session, version: StepVersion) -> StepVersionSummaryOut:
    creator = (
        session.get(User, version.created_by) if version.created_by else None
    )
    return StepVersionSummaryOut(
        id=version.id,
        version_no=version.version_no,
        status=version.status,  # type: ignore[arg-type]
        source=version.source,  # type: ignore[arg-type]
        created_at=version.created_at,
        created_by_name=_user_display_name(creator),
        tokens_in=version.tokens_in,
        tokens_out=version.tokens_out,
        error=version.error,
    )


def _permission_codes(user: User) -> set[str]:
    return {perm.code for role in user.roles for perm in role.permissions}


def get_project_steps(
    session: Session, project_id: uuid.UUID, *, actor: User
) -> ProjectStepsOut:
    from app.models.projects import Project

    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    codes = _permission_codes(actor)
    grouped = _versions_by_step(session, project_id)
    steps_out: list[ProjectStepOut] = []
    for defn in ordered_steps():
        derived = derive_step_status(defn.key, grouped, project.status)  # type: ignore[arg-type]
        can_gen = can_generate(defn.key, grouped, project.status)  # type: ignore[arg-type]
        blocked = blocked_reason_for_step(
            defn.key, grouped, project.status  # type: ignore[arg-type]
        )
        latest_row = _latest_version_row(session, project_id, defn.key)
        latest = version_to_summary(session, latest_row) if latest_row else None
        current_id, can_req, can_app, approve_blocked = compute_step_action_flags(
            session,
            project=project,
            step_key=defn.key,
            actor=actor,
            has_request_changes_perm="step.request_changes" in codes,
            has_approve_perm="step.approve" in codes,
        )
        context_out = [
            StepContextStepOut(key=ctx_key, title=get_step(ctx_key).title)
            for ctx_key in defn.context_steps
        ]
        steps_out.append(
            ProjectStepOut(
                key=defn.key,
                title=defn.title,
                order=defn.order,
                implemented=defn.implemented,
                status=derived.status.value,
                has_failed_attempt=derived.has_failed_attempt,
                can_generate=can_gen,
                blocked_reason=blocked,
                current_version_id=current_id,
                can_request_changes=can_req,
                can_approve=can_app,
                approve_blocked_reason=approve_blocked,
                latest_version=latest,
                layout=layout_to_api(defn.layout),
                reads_description=defn.reads_description,
                writes_description=defn.writes_description,
                context_steps=context_out,
            )
        )
    return ProjectStepsOut(steps=steps_out)


def list_step_versions(
    session: Session, project_id: uuid.UUID, step_key: str
) -> list[StepVersionSummaryOut]:
    try:
        get_step(step_key)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Step not found"
        ) from None

    from app.models.projects import Project

    if session.get(Project, project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    rows = session.scalars(
        select(StepVersion)
        .where(StepVersion.project_id == project_id, StepVersion.step_key == step_key)
        .order_by(StepVersion.version_no.desc())
    ).all()
    return [version_to_summary(session, row) for row in rows]


def get_step_version_detail(session: Session, version_id: uuid.UUID) -> StepVersionDetailOut:
    version = session.get(StepVersion, version_id)
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")
    creator = (
        session.get(User, version.created_by) if version.created_by else None
    )
    approval_row = session.scalar(
        select(Approval).where(Approval.step_version_id == version.id)
    )
    approval_out: ApprovalOut | None = None
    if approval_row is not None:
        approver = (
            session.get(User, approval_row.approved_by)
            if approval_row.approved_by
            else None
        )
        approval_out = ApprovalOut(
            approved_by_name=_user_display_name(approver),
            approved_at=approval_row.approved_at,
            comment=approval_row.comment,
            self_approved=approval_row.self_approved,
        )
    return StepVersionDetailOut(
        id=version.id,
        project_id=version.project_id,
        step_key=version.step_key,
        version_no=version.version_no,
        status=version.status,  # type: ignore[arg-type]
        source=version.source,  # type: ignore[arg-type]
        content=version.content,
        inputs=version.inputs or {},
        based_on_version_id=version.based_on_version_id,
        instructions=version.instructions,
        error=version.error,
        model_id=version.model_id,
        prompt_version=version.prompt_version,
        tokens_in=version.tokens_in,
        tokens_out=version.tokens_out,
        created_at=version.created_at,
        created_by_name=_user_display_name(creator),
        generation_started_at=version.generation_started_at,
        generation_finished_at=version.generation_finished_at,
        approval=approval_out,
    )


def get_step_version_for_view(session: Session, version_id: uuid.UUID) -> StepVersion:
    version = session.get(StepVersion, version_id)
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")
    return version

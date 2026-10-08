"""Request-changes and approve flows."""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.auth import User
from app.models.projects import Project
from app.models.steps import Approval, StepVersion
from app.schemas.steps import StepVersionDetailOut, StepVersionSummaryOut
from app.services.approval_policy import (
    SELF_APPROVAL_FORBIDDEN,
    resolve_origin_author_id,
    self_approval_allowed,
    self_approved_flag,
)
from app.services.audit import AuditAction, record_audit
from app.services.generation_recovery import expire_in_flight_for_project
from app.services.step_queries import get_step_version_detail, version_to_summary
from app.services.step_state import (
    ERR_IN_FLIGHT,
    ERR_NOT_IMPLEMENTED,
    ERR_PROJECT_INACTIVE,
)
from app.services.step_version_context import (
    copy_dependencies,
    is_current_review_version,
    step_has_in_flight,
    upstream_dependencies_still_approved,
)
from app.steps.definitions import get_step

ERR_NOT_IN_REVIEW = "Only an in-review version can be revised or approved"
ERR_NOT_CURRENT = "This version is not the current review version for the step"
ERR_REVISION_RACE = "Could not start revision; try again"
ERR_ALREADY_APPROVED = "This version is already approved"
ERR_UPSTREAM_CHANGED = "An upstream step has changed; regenerate this step"
ERR_SELF_APPROVAL_BLOCKED = SELF_APPROVAL_FORBIDDEN


class RequestChangesBody(BaseModel):
    instructions: str = Field(..., min_length=1, max_length=4000)

    @field_validator("instructions")
    @classmethod
    def strip_instructions(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Instructions cannot be whitespace only")
        return stripped


class ApproveBody(BaseModel):
    comment: str | None = Field(default=None, max_length=2000)

    @field_validator("comment")
    @classmethod
    def normalize_comment(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


def _load_project_for_update(session: Session, project_id: uuid.UUID) -> Project:
    project = session.scalar(
        select(Project).where(Project.id == project_id).with_for_update()
    )
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


def _ensure_active(project: Project) -> None:
    if project.status != "active":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=ERR_PROJECT_INACTIVE)


def _ensure_no_in_flight(session: Session, project_id: uuid.UUID, step_key: str) -> None:
    if step_has_in_flight(session, project_id, step_key):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=ERR_IN_FLIGHT)


def request_step_changes(
    session: Session,
    *,
    version_id: uuid.UUID,
    body: RequestChangesBody,
    actor: User,
    audit_ip: str | None,
    audit_ua: str | None,
) -> StepVersionSummaryOut:
    base = session.get(StepVersion, version_id)
    if base is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")

    try:
        defn = get_step(base.step_key)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Step not found") from None

    if not defn.implemented:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=ERR_NOT_IMPLEMENTED)

    if base.status != "in_review":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=ERR_NOT_IN_REVIEW)

    expire_in_flight_for_project(session, base.project_id)
    project = _load_project_for_update(session, base.project_id)
    _ensure_active(project)
    _ensure_no_in_flight(session, base.project_id, base.step_key)

    if not is_current_review_version(session, base):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=ERR_NOT_CURRENT)

    max_no = session.scalar(
        select(func.max(StepVersion.version_no)).where(
            StepVersion.project_id == base.project_id,
            StepVersion.step_key == base.step_key,
        )
    )
    next_no = (max_no or 0) + 1
    instructions = body.instructions

    new_version = StepVersion(
        project_id=base.project_id,
        step_key=base.step_key,
        version_no=next_no,
        status="queued",
        source="generated",
        content=None,
        inputs={},
        instructions=instructions,
        based_on_version_id=base.id,
        created_by=actor.id,
    )
    session.add(new_version)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=ERR_REVISION_RACE
            if "version_no" in str(exc).lower()
            else ERR_IN_FLIGHT,
        ) from exc

    copy_dependencies(session, from_version_id=base.id, to_version_id=new_version.id)

    record_audit(
        session,
        action=AuditAction.STEP_CHANGES_REQUESTED,
        actor=actor,
        entity_type="step_version",
        entity_id=new_version.id,
        project_id=base.project_id,
        metadata={
            "base_version_id": str(base.id),
            "new_version_id": str(new_version.id),
            "step_key": base.step_key,
            "base_version_no": base.version_no,
            "new_version_no": next_no,
            "instructions_length": len(instructions),
        },
        ip_address=audit_ip,
        user_agent=audit_ua,
    )
    session.commit()
    session.refresh(new_version)
    return version_to_summary(session, new_version)


def approve_step_version(
    session: Session,
    *,
    version_id: uuid.UUID,
    body: ApproveBody,
    actor: User,
    audit_ip: str | None,
    audit_ua: str | None,
) -> StepVersionDetailOut:
    version = session.get(StepVersion, version_id)
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")

    if version.status != "in_review":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=ERR_NOT_IN_REVIEW)

    expire_in_flight_for_project(session, version.project_id)
    project = _load_project_for_update(session, version.project_id)
    _ensure_active(project)
    _ensure_no_in_flight(session, version.project_id, version.step_key)

    if not is_current_review_version(session, version):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=ERR_NOT_CURRENT)

    existing = session.scalar(
        select(Approval.id).where(Approval.step_version_id == version.id)
    )
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=ERR_ALREADY_APPROVED)

    if not upstream_dependencies_still_approved(session, version.id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=ERR_UPSTREAM_CHANGED)

    if not self_approval_allowed(session, project, actor, version):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=ERR_SELF_APPROVAL_BLOCKED)

    origin_id = resolve_origin_author_id(session, version)
    flag = self_approved_flag(actor.id, origin_id)

    from datetime import UTC, datetime

    approval = Approval(
        step_version_id=version.id,
        approved_by=actor.id,
        approved_at=datetime.now(UTC),
        comment=body.comment,
        self_approved=flag,
    )
    session.add(approval)
    try:
        version.status = "approved"
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=ERR_ALREADY_APPROVED
        ) from exc

    record_audit(
        session,
        action=AuditAction.STEP_APPROVED,
        actor=actor,
        entity_type="step_version",
        entity_id=version.id,
        project_id=version.project_id,
        metadata={
            "version_id": str(version.id),
            "step_key": version.step_key,
            "version_no": version.version_no,
            "self_approved": flag,
            "has_comment": body.comment is not None,
        },
        ip_address=audit_ip,
        user_agent=audit_ua,
    )
    session.commit()
    return get_step_version_detail(session, version.id)



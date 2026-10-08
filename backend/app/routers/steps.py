from __future__ import annotations

import uuid
from typing import Annotated, Any, Literal

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Body,
    Depends,
    HTTPException,
    Request,
    status,
)
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.auth import User
from app.schemas.steps import (
    GenerateStepAcceptedOut,
    ProjectStepsOut,
    RequestChangesAcceptedOut,
    StepVersionDetailOut,
    StepVersionPromptOut,
    StepVersionSummaryOut,
)
from app.security.deps import require_permission
from app.services.audit import (
    AuditAction,
    client_ip_from_request,
    record_audit,
    user_agent_from_request,
)
from app.services.generation_recovery import expire_in_flight_for_project
from app.services.step_actions import (
    ApproveBody,
    RequestChangesBody,
    approve_step_version,
    request_step_changes,
)
from app.services.step_export import build_step_version_docx
from app.services.step_generation import request_step_generation, run_generation
from app.services.step_queries import (
    get_project_steps,
    get_step_version_detail,
    get_step_version_for_view,
    list_step_versions,
)

router = APIRouter(tags=["steps"])

_view = require_permission("project.view")
_generate = require_permission("step.generate")
_request_changes = require_permission("step.request_changes")
_approve = require_permission("step.approve")
_prompt_view = require_permission("prompt.view")
_download = require_permission("document.download")

DOCX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)


@router.get("/projects/{project_id}/steps", response_model=ProjectStepsOut)
def list_project_steps(
    project_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[User, Depends(_view)],
) -> ProjectStepsOut:
    expire_in_flight_for_project(db, project_id)
    db.commit()
    return get_project_steps(db, project_id, actor=actor)


@router.post(
    "/projects/{project_id}/steps/{step_key}/generate",
    response_model=GenerateStepAcceptedOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def generate_step(
    project_id: uuid.UUID,
    step_key: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[User, Depends(_generate)],
    _body: Annotated[dict[str, Any] | None, Body()] = None,
) -> GenerateStepAcceptedOut:
    summary = request_step_generation(
        db,
        project_id=project_id,
        step_key=step_key,
        actor=actor,
        audit_ip=client_ip_from_request(request),
        audit_ua=user_agent_from_request(request),
    )
    background_tasks.add_task(run_generation, summary.id)
    return GenerateStepAcceptedOut(version=summary)


@router.get(
    "/projects/{project_id}/steps/{step_key}/versions",
    response_model=list[StepVersionSummaryOut],
)
def get_step_versions(
    project_id: uuid.UUID,
    step_key: str,
    db: Annotated[Session, Depends(get_db)],
    _actor: Annotated[User, Depends(_view)],
) -> list[StepVersionSummaryOut]:
    return list_step_versions(db, project_id, step_key)


@router.get("/step-versions/{version_id}", response_model=StepVersionDetailOut)
def get_version(
    version_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    _actor: Annotated[User, Depends(_view)],
) -> StepVersionDetailOut:
    return get_step_version_detail(db, version_id)


@router.get("/step-versions/{version_id}/download")
def download_step_version(
    version_id: uuid.UUID,
    format: Literal["docx"],
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    _view: Annotated[User, Depends(_view)],
    actor: Annotated[User, Depends(_download)],
):
    version = get_step_version_for_view(db, version_id)
    docx_bytes, filename = build_step_version_docx(db, version)
    record_audit(
        db,
        action=AuditAction.DOCUMENT_DOWNLOADED,
        actor=actor,
        entity_type="step_version",
        entity_id=version.id,
        project_id=version.project_id,
        metadata={
            "version_id": str(version.id),
            "step_key": version.step_key,
            "version_no": version.version_no,
            "format": format,
            "project_id": str(version.project_id),
        },
        ip_address=client_ip_from_request(request),
        user_agent=user_agent_from_request(request),
    )
    db.commit()
    return StreamingResponse(
        iter([docx_bytes]),
        media_type=DOCX_MEDIA_TYPE,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/step-versions/{version_id}/prompt", response_model=StepVersionPromptOut)
def get_version_prompt(
    version_id: uuid.UUID,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[User, Depends(_prompt_view)],
) -> StepVersionPromptOut:
    version = get_step_version_for_view(db, version_id)
    if version.assembled_prompt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prompt not available for this version",
        )
    record_audit(
        db,
        action=AuditAction.PROMPT_VIEWED,
        actor=actor,
        entity_type="step_version",
        entity_id=version.id,
        project_id=version.project_id,
        metadata={
            "version_id": str(version.id),
            "project_id": str(version.project_id),
            "step_key": version.step_key,
            "version_no": version.version_no,
        },
        ip_address=client_ip_from_request(request),
        user_agent=user_agent_from_request(request),
    )
    db.commit()
    return StepVersionPromptOut(
        step_version_id=version.id,
        assembled_prompt=version.assembled_prompt,
    )


@router.post(
    "/step-versions/{version_id}/request-changes",
    response_model=RequestChangesAcceptedOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def request_changes(
    version_id: uuid.UUID,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[User, Depends(_request_changes)],
    body: RequestChangesBody,
) -> RequestChangesAcceptedOut:
    summary = request_step_changes(
        db,
        version_id=version_id,
        body=body,
        actor=actor,
        audit_ip=client_ip_from_request(request),
        audit_ua=user_agent_from_request(request),
    )
    background_tasks.add_task(run_generation, summary.id)
    return RequestChangesAcceptedOut(version=summary)


@router.post(
    "/step-versions/{version_id}/approve",
    response_model=StepVersionDetailOut,
)
def approve_version(
    version_id: uuid.UUID,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[User, Depends(_approve)],
    body: ApproveBody | None = None,
) -> StepVersionDetailOut:
    return approve_step_version(
        db,
        version_id=version_id,
        body=body or ApproveBody(),
        actor=actor,
        audit_ip=client_ip_from_request(request),
        audit_ua=user_agent_from_request(request),
    )

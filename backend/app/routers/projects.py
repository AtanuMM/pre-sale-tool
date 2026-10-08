from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models.auth import User
from app.schemas.projects import (
    FileTextOut,
    ProjectCreateOut,
    ProjectIntakeLimitsOut,
    ProjectListOut,
    ProjectOverviewOut,
    ProjectSettingsOut,
    ProjectSettingsPatch,
    ProjectSummaryOut,
)
from app.security.deps import get_current_user, require_permission
from app.services.audit import (
    AuditAction,
    client_ip_from_request,
    record_audit,
    user_agent_from_request,
)
from app.services.file_validation import sanitize_original_name
from app.services.project_intake import (
    IntakeValidationError,
    add_followup_input,
    archive_project,
    create_project_with_intake,
    file_text_out,
    get_file_for_project,
    get_intake_limits,
    intake_validation_to_http,
    list_projects,
    load_project_overview,
    patch_project_settings,
    restore_project,
    validate_intake_form,
)
from app.services.storage import (
    STORAGE_UNAVAILABLE_DETAIL,
    StorageError,
    get_file_stream,
)

router = APIRouter(prefix="/projects", tags=["projects"])

_create = require_permission("project.create")
_view = require_permission("project.view")
_add_input = require_permission("input.add")
_archive = require_permission("project.archive")
_settings = require_permission("settings.manage")


def _check_content_length(request: Request) -> None:
    raw = request.headers.get("content-length")
    if raw is None:
        return
    try:
        length = int(raw)
    except ValueError:
        return
    if length > get_settings().MAX_INTAKE_REQUEST_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Request body too large",
        )


def _collect_uploads(files: list[UploadFile] | None) -> list[UploadFile]:
    if not files:
        return []
    return [f for f in files if f.filename]


@router.post("", response_model=ProjectCreateOut, status_code=status.HTTP_201_CREATED)
def create_project(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[User, Depends(_create)],
    name: Annotated[str, Form()],
    client_name: Annotated[str, Form()],
    kind: Annotated[str, Form()],
    received_at: Annotated[str, Form()],
    received_from: Annotated[str | None, Form()] = None,
    subject: Annotated[str | None, Form()] = None,
    body: Annotated[str, Form()] = "",
    files: Annotated[list[UploadFile] | None, File()] = None,
) -> ProjectCreateOut:
    _check_content_length(request)
    uploads = _collect_uploads(files)
    try:
        form = validate_intake_form(
            name=name,
            client_name=client_name,
            kind=kind,
            received_at_raw=received_at,
            received_from=received_from,
            subject=subject,
            body=body,
            file_count=len(uploads),
        )
    except IntakeValidationError as exc:
        raise intake_validation_to_http(exc) from exc

    try:
        return create_project_with_intake(
            db,
            form=form,
            uploads=uploads,
            actor=actor,
            audit_ip=client_ip_from_request(request),
            audit_ua=user_agent_from_request(request),
        )
    except IntakeValidationError as exc:
        raise intake_validation_to_http(exc) from exc
    except StorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=STORAGE_UNAVAILABLE_DETAIL,
        ) from exc


@router.get("", response_model=ProjectListOut)
def get_projects(
    db: Annotated[Session, Depends(get_db)],
    _actor: Annotated[User, Depends(_view)],
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    search: str | None = Query(default=None),
    status: str | None = Query(default=None, alias="status"),
) -> ProjectListOut:
    try:
        return list_projects(db, limit=limit, offset=offset, search=search, status_filter=status)
    except IntakeValidationError as exc:
        raise intake_validation_to_http(exc) from exc


@router.get("/limits", response_model=ProjectIntakeLimitsOut)
def get_project_intake_limits(
    _actor: Annotated[User, Depends(get_current_user)],
) -> ProjectIntakeLimitsOut:
    return get_intake_limits()


@router.get("/{project_id}", response_model=ProjectOverviewOut)
def get_project(
    project_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    _actor: Annotated[User, Depends(_view)],
) -> ProjectOverviewOut:
    return load_project_overview(db, project_id)


@router.get("/{project_id}/overview", response_model=ProjectOverviewOut)
def get_project_overview(
    project_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    _actor: Annotated[User, Depends(_view)],
) -> ProjectOverviewOut:
    return load_project_overview(db, project_id)


@router.post("/{project_id}/inputs", response_model=ProjectCreateOut, status_code=status.HTTP_201_CREATED)
def create_followup_input(
    project_id: uuid.UUID,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[User, Depends(_add_input)],
    name: Annotated[str, Form()],
    client_name: Annotated[str, Form()],
    kind: Annotated[str, Form()],
    received_at: Annotated[str, Form()],
    received_from: Annotated[str | None, Form()] = None,
    subject: Annotated[str | None, Form()] = None,
    body: Annotated[str, Form()] = "",
    files: Annotated[list[UploadFile] | None, File()] = None,
) -> ProjectCreateOut:
    _check_content_length(request)
    uploads = _collect_uploads(files)
    try:
        form = validate_intake_form(
            name=name,
            client_name=client_name,
            kind=kind,
            received_at_raw=received_at,
            received_from=received_from,
            subject=subject,
            body=body,
            file_count=len(uploads),
        )
    except IntakeValidationError as exc:
        raise intake_validation_to_http(exc) from exc

    try:
        return add_followup_input(
            db,
            project_id=project_id,
            form=form,
            uploads=uploads,
            actor=actor,
            audit_ip=client_ip_from_request(request),
            audit_ua=user_agent_from_request(request),
        )
    except IntakeValidationError as exc:
        raise intake_validation_to_http(exc) from exc
    except StorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=STORAGE_UNAVAILABLE_DETAIL,
        ) from exc


@router.get("/{project_id}/files/{file_id}/download")
def download_project_file(
    project_id: uuid.UUID,
    file_id: uuid.UUID,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[User, Depends(_view)],
):
    inp, file_row = get_file_for_project(db, project_id=project_id, file_id=file_id)
    try:
        data = get_file_stream(file_row.storage_key)
    except StorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=STORAGE_UNAVAILABLE_DETAIL,
        ) from exc
    content = data.read()
    safe_name = sanitize_original_name(file_row.original_name)
    record_audit(
        db,
        action=AuditAction.DOCUMENT_DOWNLOADED,
        actor=actor,
        entity_type="file",
        entity_id=file_row.id,
        project_id=project_id,
        metadata={"file_id": str(file_row.id), "input_id": str(inp.id)},
        ip_address=client_ip_from_request(request),
        user_agent=user_agent_from_request(request),
    )
    db.commit()

    return StreamingResponse(
        iter([content]),
        media_type=file_row.mime_type,
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/{project_id}/files/{file_id}/text", response_model=FileTextOut)
def get_project_file_text(
    project_id: uuid.UUID,
    file_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    _actor: Annotated[User, Depends(_view)],
) -> FileTextOut:
    _inp, file_row = get_file_for_project(db, project_id=project_id, file_id=file_id)
    return file_text_out(file_row)


@router.patch("/{project_id}/settings", response_model=ProjectSettingsOut)
def update_project_settings(
    project_id: uuid.UUID,
    body: ProjectSettingsPatch,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[User, Depends(_settings)],
) -> ProjectSettingsOut:
    return patch_project_settings(
        db,
        project_id=project_id,
        allow_self_approval=body.allow_self_approval,
        actor=actor,
        audit_ip=client_ip_from_request(request),
        audit_ua=user_agent_from_request(request),
    )


@router.post("/{project_id}/archive", response_model=ProjectSummaryOut)
def archive_project_endpoint(
    project_id: uuid.UUID,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[User, Depends(_archive)],
) -> ProjectSummaryOut:
    return archive_project(
        db,
        project_id=project_id,
        actor=actor,
        audit_ip=client_ip_from_request(request),
        audit_ua=user_agent_from_request(request),
    )


@router.post("/{project_id}/restore", response_model=ProjectSummaryOut)
def restore_project_endpoint(
    project_id: uuid.UUID,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[User, Depends(_archive)],
) -> ProjectSummaryOut:
    return restore_project(
        db,
        project_id=project_id,
        actor=actor,
        audit_ip=client_ip_from_request(request),
        audit_ua=user_agent_from_request(request),
    )

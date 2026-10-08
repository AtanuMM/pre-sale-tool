from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.models.auth import User
from app.models.files import File
from app.models.projects import (
    INPUT_KINDS,
    PROJECT_STATUSES,
    Project,
    ProjectInput,
    ProjectInputFile,
)
from app.models.system import AuditLog
from app.schemas.projects import (
    ExtractionStatus,
    FileSummaryOut,
    FileTextOut,
    InputOut,
    ProjectCreateOut,
    ProjectIntakeLimitsOut,
    ProjectListItemOut,
    ProjectListOut,
    ProjectOverviewOut,
    ProjectSettingsOut,
    ProjectSummaryOut,
    TimelineEntryOut,
)
from app.services.audit import AuditAction, record_audit
from app.services.extraction import TRUNCATION_MARKER
from app.services.file_service import (
    PreparedFileUpload,
    prepare_file_upload,
    rollback_storage_keys,
)
from app.services.file_validation import (
    ALLOWED_UPLOAD_EXTENSIONS,
    FileTooLargeError,
    FileValidationError,
    assert_file_count_for_input,
)
from app.services.settings_admin import get_settings_out

InputKind = Literal["email", "document", "meeting_notes", "other"]


class IntakeValidationError(Exception):
    def __init__(self, message: str, *, status_code: int = status.HTTP_422_UNPROCESSABLE_ENTITY):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


@dataclass(frozen=True)
class IntakeFormData:
    name: str
    client_name: str
    kind: InputKind
    received_at: datetime
    received_from: str | None
    subject: str | None
    body: str


def parse_received_at(raw: str) -> datetime:
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise IntakeValidationError("received_at must be a valid ISO 8601 datetime") from exc
    if dt.tzinfo is None:
        raise IntakeValidationError("received_at must include a timezone offset")
    return dt.astimezone(UTC)


def validate_received_at_not_future(received_at: datetime) -> None:
    settings = get_settings()
    limit = datetime.now(UTC) + timedelta(seconds=settings.RECEIVED_AT_FUTURE_TOLERANCE_SECONDS)
    if received_at > limit:
        raise IntakeValidationError("received_at must not be in the future")


def validate_intake_form(
    *,
    name: str,
    client_name: str,
    kind: str,
    received_at_raw: str,
    received_from: str | None,
    subject: str | None,
    body: str,
    file_count: int,
) -> IntakeFormData:
    name = name.strip()
    client_name = client_name.strip()
    if not name:
        raise IntakeValidationError("name is required")
    if not client_name:
        raise IntakeValidationError("client_name is required")
    if len(name) > 255 or len(client_name) > 255:
        raise IntakeValidationError("name and client_name must be at most 255 characters")
    if kind not in INPUT_KINDS:
        raise IntakeValidationError(f"kind must be one of: {', '.join(INPUT_KINDS)}")
    received_at = parse_received_at(received_at_raw)
    validate_received_at_not_future(received_at)
    body_stripped = body if body is not None else ""
    if received_from is not None and len(received_from) > 320:
        raise IntakeValidationError("received_from must be at most 320 characters")
    if subject is not None and len(subject) > 500:
        raise IntakeValidationError("subject must be at most 500 characters")
    try:
        assert_file_count_for_input(file_count)
    except FileValidationError as exc:
        raise IntakeValidationError(str(exc)) from exc
    if not body_stripped.strip() and file_count == 0:
        raise IntakeValidationError("Provide a non-empty body or at least one attachment")
    return IntakeFormData(
        name=name,
        client_name=client_name,
        kind=kind,  # type: ignore[arg-type]
        received_at=received_at,
        received_from=received_from.strip() if received_from else None,
        subject=subject.strip() if subject else None,
        body=body_stripped,
    )


def extraction_status_and_count(extracted_text: str | None) -> tuple[ExtractionStatus, int]:
    if extracted_text is None or not extracted_text.strip():
        return "empty", 0
    if TRUNCATION_MARKER in extracted_text:
        base = extracted_text.split(TRUNCATION_MARKER, 1)[0]
        return "truncated", len(base)
    return "ok", len(extracted_text)


def _user_display_name(user: User | None) -> str | None:
    if user is None:
        return None
    return user.full_name


def file_to_summary(file: File) -> FileSummaryOut:
    status_name, count = extraction_status_and_count(file.extracted_text)
    return FileSummaryOut(
        id=file.id,
        original_name=file.original_name,
        mime_type=file.mime_type,
        size_bytes=file.size_bytes,
        sha256=file.sha256,
        extraction_status=status_name,
        extracted_char_count=count,
    )


def effective_allow_self_approval(session: Session, project: Project) -> bool:
    if project.allow_self_approval is not None:
        return project.allow_self_approval
    return get_settings_out(session).allow_self_approval


def project_to_summary(session: Session, project: Project) -> ProjectSummaryOut:
    creator = session.get(User, project.created_by) if project.created_by else None
    return ProjectSummaryOut(
        id=project.id,
        name=project.name,
        client_name=project.client_name,
        status=project.status,  # type: ignore[arg-type]
        allow_self_approval=project.allow_self_approval,
        created_by_name=_user_display_name(creator),
        created_at=project.created_at,
        completed_at=project.completed_at,
    )


def _prepare_uploads(uploads: list[UploadFile]) -> list[PreparedFileUpload]:
    prepared: list[PreparedFileUpload] = []
    storage_keys: list[str] = []
    succeeded = False
    try:
        for upload in uploads:
            if not upload.filename:
                continue
            try:
                prep = prepare_file_upload(
                    upload.file,
                    original_name=upload.filename,
                    content_type=upload.content_type,
                )
            except FileTooLargeError as exc:
                raise IntakeValidationError(
                    str(exc),
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                ) from exc
            except FileValidationError as exc:
                raise IntakeValidationError(str(exc)) from exc
            prepared.append(prep)
            storage_keys.append(prep.storage_key)
        succeeded = True
        return prepared
    finally:
        if not succeeded:
            rollback_storage_keys(storage_keys)


def _persist_input_with_files(
    session: Session,
    *,
    project: Project,
    form: IntakeFormData,
    prepared: list[PreparedFileUpload],
    actor: User,
    is_followup: bool,
    audit_ip: str | None,
    audit_ua: str | None,
) -> tuple[ProjectInput, list[File]]:
    inp = ProjectInput(
        project_id=project.id,
        kind=form.kind,
        received_at=form.received_at,
        received_from=form.received_from,
        subject=form.subject,
        body=form.body,
        is_followup=is_followup,
        created_by=actor.id,
    )
    session.add(inp)
    session.flush()
    session.refresh(inp)

    files: list[File] = []
    for prep in prepared:
        row = File(
            storage_key=prep.storage_key,
            original_name=prep.sanitized_original_name,
            mime_type=prep.mime_type,
            size_bytes=prep.size_bytes,
            sha256=prep.sha256,
            extracted_text=prep.extraction.text,
            uploaded_by=actor.id,
        )
        session.add(row)
        session.flush()
        session.add(ProjectInputFile(input_id=inp.id, file_id=row.id))
        files.append(row)

    file_ids = [str(f.id) for f in files]
    record_audit(
        session,
        action=AuditAction.INPUT_ADDED,
        actor=actor,
        entity_type="input",
        entity_id=inp.id,
        project_id=project.id,
        metadata={
            "input_id": str(inp.id),
            "kind": form.kind,
            "is_followup": is_followup,
            "received_at": form.received_at.isoformat(),
            "recorded_at": inp.created_at.isoformat(),
            "file_ids": file_ids,
        },
        ip_address=audit_ip,
        user_agent=audit_ua,
    )
    return inp, files


def create_project_with_intake(
    session: Session,
    *,
    form: IntakeFormData,
    uploads: list[UploadFile],
    actor: User,
    audit_ip: str | None,
    audit_ua: str | None,
) -> ProjectCreateOut:
    prepared = _prepare_uploads(uploads)
    storage_keys = [p.storage_key for p in prepared]
    try:
        project = Project(
            name=form.name,
            client_name=form.client_name,
            status="active",
            created_by=actor.id,
        )
        session.add(project)
        session.flush()

        record_audit(
            session,
            action=AuditAction.PROJECT_CREATED,
            actor=actor,
            entity_type="project",
            entity_id=project.id,
            project_id=project.id,
            metadata={"name": form.name, "client_name": form.client_name},
            ip_address=audit_ip,
            user_agent=audit_ua,
        )

        inp, files = _persist_input_with_files(
            session,
            project=project,
            form=form,
            prepared=prepared,
            actor=actor,
            is_followup=False,
            audit_ip=audit_ip,
            audit_ua=audit_ua,
        )
        session.commit()
        session.refresh(project)
        session.refresh(inp)
        for f in files:
            session.refresh(f)

        input_out = _input_to_out(session, inp, files)
        return ProjectCreateOut(
            project=project_to_summary(session, project),
            input=input_out,
            files=[file_to_summary(f) for f in files],
        )
    except Exception:
        session.rollback()
        rollback_storage_keys(storage_keys)
        raise


def add_followup_input(
    session: Session,
    *,
    project_id: uuid.UUID,
    form: IntakeFormData,
    uploads: list[UploadFile],
    actor: User,
    audit_ip: str | None,
    audit_ua: str | None,
) -> ProjectCreateOut:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if project.status in ("archived", "completed"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot add inputs to an archived or completed project",
        )

    prepared = _prepare_uploads(uploads)
    storage_keys = [p.storage_key for p in prepared]
    try:
        inp, files = _persist_input_with_files(
            session,
            project=project,
            form=form,
            prepared=prepared,
            actor=actor,
            is_followup=True,
            audit_ip=audit_ip,
            audit_ua=audit_ua,
        )
        session.commit()
        session.refresh(project)
        session.refresh(inp)
        for f in files:
            session.refresh(f)
        input_out = _input_to_out(session, inp, files)
        return ProjectCreateOut(
            project=project_to_summary(session, project),
            input=input_out,
            files=[file_to_summary(f) for f in files],
        )
    except Exception:
        session.rollback()
        rollback_storage_keys(storage_keys)
        raise


def _input_to_out(session: Session, inp: ProjectInput, files: list[File]) -> InputOut:
    creator = session.get(User, inp.created_by) if inp.created_by else None
    return InputOut(
        id=inp.id,
        kind=inp.kind,  # type: ignore[arg-type]
        received_at=inp.received_at,
        received_from=inp.received_from,
        subject=inp.subject,
        body=inp.body,
        is_followup=inp.is_followup,
        created_by_name=_user_display_name(creator),
        created_at=inp.created_at,
        files=[file_to_summary(f) for f in files],
    )


def get_intake_limits() -> ProjectIntakeLimitsOut:
    settings = get_settings()
    return ProjectIntakeLimitsOut(
        max_file_bytes=settings.MAX_UPLOAD_FILE_BYTES,
        max_files_per_input=settings.MAX_FILES_PER_INPUT,
        allowed_extensions=list(ALLOWED_UPLOAD_EXTENSIONS),
        max_extracted_chars=settings.MAX_EXTRACTED_TEXT_CHARS,
    )


def load_project_overview(session: Session, project_id: uuid.UUID) -> ProjectOverviewOut:
    project = session.scalar(
        select(Project)
        .where(Project.id == project_id)
        .options(
            selectinload(Project.inputs)
            .selectinload(ProjectInput.file_links)
            .selectinload(ProjectInputFile.file)
        )
    )
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    inputs_sorted = sorted(project.inputs, key=lambda i: i.created_at)
    input_outs: list[InputOut] = []
    for inp in inputs_sorted:
        files = [link.file for link in inp.file_links]
        input_outs.append(_input_to_out(session, inp, files))

    timeline_rows = session.scalars(
        select(AuditLog)
        .where(AuditLog.project_id == project_id)
        .order_by(AuditLog.occurred_at.asc())
    ).all()
    timeline = [
        TimelineEntryOut(
            action=row.action,
            actor_name=row.actor_email,
            occurred_at=row.occurred_at,
        )
        for row in timeline_rows
    ]

    return ProjectOverviewOut(
        project=project_to_summary(session, project),
        effective_allow_self_approval=effective_allow_self_approval(session, project),
        inputs=input_outs,
        timeline=timeline,
    )


def list_projects(
    session: Session,
    *,
    limit: int,
    offset: int,
    search: str | None,
    status_filter: str | None,
) -> ProjectListOut:
    stmt = select(Project)
    count_stmt = select(func.count()).select_from(Project)

    if status_filter:
        if status_filter not in PROJECT_STATUSES:
            raise IntakeValidationError(f"status must be one of: {', '.join(PROJECT_STATUSES)}")
        stmt = stmt.where(Project.status == status_filter)
        count_stmt = count_stmt.where(Project.status == status_filter)

    if search and search.strip():
        q = f"%{search.strip()}%"
        cond = or_(Project.name.ilike(q), Project.client_name.ilike(q))
        stmt = stmt.where(cond)
        count_stmt = count_stmt.where(cond)

    total = session.scalar(count_stmt) or 0
    projects = session.scalars(
        stmt.order_by(Project.created_at.desc()).limit(limit).offset(offset)
    ).all()

    items: list[ProjectListItemOut] = []
    for project in projects:
        creator = session.get(User, project.created_by) if project.created_by else None
        items.append(
            ProjectListItemOut(
                id=project.id,
                name=project.name,
                client_name=project.client_name,
                status=project.status,  # type: ignore[arg-type]
                created_by_name=_user_display_name(creator),
                created_at=project.created_at,
            )
        )
    return ProjectListOut(items=items, total=total)


def get_file_for_project(
    session: Session,
    *,
    project_id: uuid.UUID,
    file_id: uuid.UUID,
) -> tuple[ProjectInput, File]:
    link = session.scalar(
        select(ProjectInputFile)
        .join(ProjectInput, ProjectInput.id == ProjectInputFile.input_id)
        .where(
            ProjectInputFile.file_id == file_id,
            ProjectInput.project_id == project_id,
        )
    )
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    inp = session.get(ProjectInput, link.input_id)
    file_row = session.get(File, file_id)
    if inp is None or file_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    return inp, file_row


def file_text_out(file: File) -> FileTextOut:
    status_name, count = extraction_status_and_count(file.extracted_text)
    return FileTextOut(
        extraction_status=status_name,
        extracted_char_count=count,
        text=file.extracted_text or "",
    )


def patch_project_settings(
    session: Session,
    *,
    project_id: uuid.UUID,
    allow_self_approval: bool | None,
    actor: User,
    audit_ip: str | None,
    audit_ua: str | None,
) -> ProjectSettingsOut:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    old = project.allow_self_approval
    project.allow_self_approval = allow_self_approval
    record_audit(
        session,
        action=AuditAction.PROJECT_SETTINGS_CHANGED,
        actor=actor,
        entity_type="project",
        entity_id=project.id,
        project_id=project.id,
        metadata={"old": {"allow_self_approval": old}, "new": {"allow_self_approval": allow_self_approval}},
        ip_address=audit_ip,
        user_agent=audit_ua,
    )
    session.commit()
    session.refresh(project)
    return ProjectSettingsOut(
        allow_self_approval=project.allow_self_approval,
        effective_allow_self_approval=effective_allow_self_approval(session, project),
    )


def archive_project(
    session: Session,
    *,
    project_id: uuid.UUID,
    actor: User,
    audit_ip: str | None,
    audit_ua: str | None,
) -> ProjectSummaryOut:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    project.status = "archived"
    record_audit(
        session,
        action=AuditAction.PROJECT_ARCHIVED,
        actor=actor,
        entity_type="project",
        entity_id=project.id,
        project_id=project.id,
        metadata={"status": "archived"},
        ip_address=audit_ip,
        user_agent=audit_ua,
    )
    session.commit()
    session.refresh(project)
    return project_to_summary(session, project)


def restore_project(
    session: Session,
    *,
    project_id: uuid.UUID,
    actor: User,
    audit_ip: str | None,
    audit_ua: str | None,
) -> ProjectSummaryOut:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    new_status = "completed" if project.completed_at is not None else "active"
    project.status = new_status
    record_audit(
        session,
        action=AuditAction.PROJECT_RESTORED,
        actor=actor,
        entity_type="project",
        entity_id=project.id,
        project_id=project.id,
        metadata={"status": new_status},
        ip_address=audit_ip,
        user_agent=audit_ua,
    )
    session.commit()
    session.refresh(project)
    return project_to_summary(session, project)


def intake_validation_to_http(exc: IntakeValidationError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.message)

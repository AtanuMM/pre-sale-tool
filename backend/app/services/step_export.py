"""Build step version DOCX exports."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.documents.filename import build_step_export_filename
from app.documents.layouts import layout_for_step
from app.documents.meta import (
    ApprovalMarker,
    ExportMeta,
    build_marker_line,
    format_export_date,
    status_display_label,
)
from app.documents.render import render_step_docx
from app.models.auth import User
from app.models.projects import Project
from app.models.steps import Approval, StepVersion
from app.services.step_queries import _user_display_name
from app.steps.definitions import get_step

_NO_CONTENT_STATUSES = frozenset({"queued", "generating", "failed"})


def version_has_exportable_content(version: StepVersion) -> bool:
    if version.status in _NO_CONTENT_STATUSES:
        return False
    if version.content is None:
        return False
    if not isinstance(version.content, dict):
        return False
    return len(version.content) > 0


def _metadata_date(
    version: StepVersion,
    approval: Approval | None,
) -> tuple[str, str]:
    if version.status == "approved" and approval is not None:
        return "Approved", format_export_date(approval.approved_at)
    finished = version.generation_finished_at or version.created_at
    return "Generated", format_export_date(finished)


def build_step_version_docx(
    session: Session,
    version: StepVersion,
) -> tuple[bytes, str]:
    if not version_has_exportable_content(version):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No content to download for this version",
        )
    if layout_for_step(version.step_key) is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="DOCX export is not available for this step",
        )

    project = session.get(Project, version.project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    try:
        defn = get_step(version.step_key)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="DOCX export is not available for this step",
        ) from None

    creator = (
        session.get(User, version.created_by) if version.created_by else None
    )
    approval_row = session.scalar(
        select(Approval).where(Approval.step_version_id == version.id)
    )
    approval_marker: ApprovalMarker | None = None
    if approval_row is not None:
        approver = (
            session.get(User, approval_row.approved_by)
            if approval_row.approved_by
            else None
        )
        approval_marker = ApprovalMarker(
            approved_by_name=_user_display_name(approver) or "Unknown",
            approved_at=approval_row.approved_at,
            self_approved=approval_row.self_approved,
        )

    date_label, date_value = _metadata_date(version, approval_row)
    fallback_approved = (
        version.generation_finished_at or version.created_at
        if version.status == "approved"
        else None
    )
    marker = build_marker_line(
        status=version.status,
        approval=approval_marker,
        fallback_approved_at=fallback_approved,
    )
    meta = ExportMeta(
        step_key=version.step_key,
        step_title=defn.title,
        project_name=project.name,
        client_name=project.client_name,
        version_no=version.version_no,
        status=version.status,
        status_label=status_display_label(version.status),
        marker_line=marker,
        metadata_date_label=date_label,
        metadata_date_value=date_value,
        created_by_name=_user_display_name(creator) or "Unknown",
        is_draft_filename=version.status != "approved",
    )
    content: dict[str, Any] = version.content  # type: ignore[assignment]
    docx_bytes = render_step_docx(version.step_key, content, meta)
    filename = build_step_export_filename(
        project_name=project.name,
        step_key=version.step_key,
        version_no=version.version_no,
        is_draft=meta.is_draft_filename,
    )
    return docx_bytes, filename

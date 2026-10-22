"""Build downloadable zip of all approved step exports for a project."""

from __future__ import annotations

import csv
import hashlib
import io
import re
import uuid
import zipfile
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.projects import Project
from app.models.steps import Approval, StepVersion
from app.services.step_export import (
    build_step_version_export,
    version_has_exportable_content,
)
from app.steps.definitions import ordered_steps

_STEP_FOLDER = {
    "scope_analysis": "01-scope-analysis",
    "gap_analysis": "02-gap-analysis",
    "feature_list": "03-feature-list",
    "estimate": "04-estimate",
    "sow": "05-sow",
    "srs": "06-srs",
    "sprint_plan": "07-sprint-plan",
    "frs": "08-frs",
}


def _sanitize_zip_name(name: str) -> str:
    cleaned = re.sub(r"[^\w\-]+", "-", name.strip()).strip("-") or "project"
    return cleaned[:80]


def build_project_package(
    session: Session,
    project_id: uuid.UUID,
) -> tuple[bytes, str]:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    settings = get_settings()
    buf = io.BytesIO()
    manifest_rows: list[dict[str, str]] = []
    excluded: list[dict[str, str]] = []
    included = 0

    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for step in ordered_steps():
            folder = _STEP_FOLDER[step.key]
            approved = session.scalar(
                select(StepVersion)
                .where(
                    StepVersion.project_id == project_id,
                    StepVersion.step_key == step.key,
                    StepVersion.status == "approved",
                )
                .order_by(StepVersion.version_no.desc())
            )
            stale = session.scalar(
                select(StepVersion)
                .where(
                    StepVersion.project_id == project_id,
                    StepVersion.step_key == step.key,
                    StepVersion.status == "stale",
                )
                .order_by(StepVersion.version_no.desc())
            )
            if stale is not None and approved is None:
                excluded.append(
                    {"step": step.key, "reason": "stale", "version_no": str(stale.version_no)}
                )
            if approved is None or not version_has_exportable_content(approved):
                continue
            approval = session.scalar(
                select(Approval).where(Approval.step_version_id == approved.id)
            )
            approved_date = ""
            if approval is not None:
                approved_date = approval.approved_at.astimezone(UTC).date().isoformat()

            for fmt in step.export_formats:
                if fmt == "csv" and step.key not in ("estimate", "srs", "sprint_plan", "frs"):
                    continue
                try:
                    data, filename, _ = build_step_version_export(session, approved, fmt)
                except HTTPException:
                    continue
                path = f"{folder}/{filename}"
                zf.writestr(path, data)
                digest = hashlib.sha256(data).hexdigest()
                manifest_rows.append(
                    {
                        "step": step.key,
                        "version_no": str(approved.version_no),
                        "approved_date": approved_date,
                        "file_name": filename,
                        "sha256": digest,
                    }
                )
                included += 1

        readme = (
            "ScopeDesk project package\r\n"
            f"Project: {project.name}\r\n"
            f"Generated: {datetime.now(UTC).isoformat()}\r\n"
            "Includes approved documents only.\r\n"
        )
        zf.writestr("README.txt", readme)

        manifest_io = io.StringIO()
        writer = csv.DictWriter(
            manifest_io,
            fieldnames=["step", "version_no", "approved_date", "file_name", "sha256"],
        )
        writer.writeheader()
        for row in manifest_rows:
            writer.writerow(row)
        if excluded:
            writer.writerow(
                {
                    "step": "excluded",
                    "version_no": "",
                    "approved_date": "",
                    "file_name": excluded[0].get("step", ""),
                    "sha256": excluded[0].get("reason", ""),
                }
            )
        zf.writestr("manifest.csv", manifest_io.getvalue())

    payload = buf.getvalue()
    if included == 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No approved documents are available for packaging",
        )
    if len(payload) > settings.PROJECT_PACKAGE_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Project package exceeds the configured size limit",
        )
    filename = f"{_sanitize_zip_name(project.name)}-package.zip"
    return payload, filename

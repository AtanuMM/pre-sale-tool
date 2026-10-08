"""Trusted export metadata and status markers (never from raw model JSON)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class ApprovalMarker:
    approved_by_name: str
    approved_at: datetime
    self_approved: bool


@dataclass(frozen=True)
class ExportMeta:
    step_key: str
    step_title: str
    project_name: str
    client_name: str
    version_no: int
    status: str
    status_label: str
    marker_line: str
    metadata_date_label: str
    metadata_date_value: str
    created_by_name: str
    is_draft_filename: bool


def format_export_date(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    dt = dt.astimezone(UTC)
    return f"{dt.day} {dt.strftime('%B')} {dt.year}"


def build_marker_line(
    *,
    status: str,
    approval: ApprovalMarker | None,
    fallback_approved_at: datetime | None,
) -> str:
    if status == "approved":
        if approval is not None:
            line = (
                f"Approved by {approval.approved_by_name} on "
                f"{format_export_date(approval.approved_at)}"
            )
            if approval.self_approved:
                line = f"{line}. Self-approved"
            return line
        if fallback_approved_at is not None:
            return f"Approved on {format_export_date(fallback_approved_at)}"
        return "Approved"
    if status == "in_review":
        return "DRAFT, NOT APPROVED"
    if status in ("changes_requested", "superseded"):
        return "SUPERSEDED DRAFT, NOT APPROVED"
    if status == "stale":
        return "STALE: an upstream step changed, not current"
    return ""


def status_display_label(status: str) -> str:
    labels = {
        "in_review": "In review",
        "approved": "Approved",
        "changes_requested": "Changes requested",
        "superseded": "Superseded",
        "stale": "Stale",
        "queued": "Queued",
        "generating": "Generating",
        "failed": "Failed",
    }
    return labels.get(status, status.replace("_", " ").title())

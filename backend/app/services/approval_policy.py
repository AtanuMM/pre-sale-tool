"""Self-approval policy and origin-author resolution."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.models.auth import User
from app.models.projects import Project
from app.models.steps import StepVersion
from app.services.project_intake import effective_allow_self_approval

SELF_APPROVAL_FORBIDDEN = "Self-approval is not allowed for this project"


def resolve_origin_author_id(session: Session, version: StepVersion) -> uuid.UUID | None:
    """Root of based_on_version_id chain (first generation without a base)."""
    current: StepVersion | None = version
    seen: set[uuid.UUID] = set()
    while current is not None and current.based_on_version_id is not None:
        if current.id in seen:
            break
        seen.add(current.id)
        parent = session.get(StepVersion, current.based_on_version_id)
        if parent is None:
            break
        current = parent
    return current.created_by if current else None


def self_approved_flag(approver_id: uuid.UUID | None, origin_author_id: uuid.UUID | None) -> bool:
    if approver_id is None or origin_author_id is None:
        return False
    return approver_id == origin_author_id


def self_approval_allowed(
    session: Session,
    project: Project,
    approver: User,
    version: StepVersion,
) -> bool:
    if effective_allow_self_approval(session, project):
        return True
    origin = resolve_origin_author_id(session, version)
    if origin is None:
        return True
    return approver.id != origin

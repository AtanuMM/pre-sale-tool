"""Step version lookup helpers (current review version, in-flight)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.auth import User
from app.models.projects import Project
from app.models.steps import StepVersion, StepVersionDependency
from app.services.approval_policy import SELF_APPROVAL_FORBIDDEN, self_approval_allowed
from app.services.step_state import ERR_IN_FLIGHT, IN_FLIGHT_STATUSES
from app.steps.definitions import get_step


def step_has_in_flight(session: Session, project_id: uuid.UUID, step_key: str) -> bool:
    row = session.scalar(
        select(StepVersion.id).where(
            StepVersion.project_id == project_id,
            StepVersion.step_key == step_key,
            StepVersion.status.in_(tuple(IN_FLIGHT_STATUSES)),
        )
    )
    return row is not None


def find_in_review_version(
    session: Session, project_id: uuid.UUID, step_key: str
) -> StepVersion | None:
    return session.scalar(
        select(StepVersion)
        .where(
            StepVersion.project_id == project_id,
            StepVersion.step_key == step_key,
            StepVersion.status == "in_review",
        )
        .order_by(StepVersion.version_no.desc())
        .limit(1)
    )


def find_current_version_id(
    session: Session, project_id: uuid.UUID, step_key: str
) -> uuid.UUID | None:
    in_review = find_in_review_version(session, project_id, step_key)
    if in_review is not None:
        return in_review.id
    approved = session.scalar(
        select(StepVersion)
        .where(
            StepVersion.project_id == project_id,
            StepVersion.step_key == step_key,
            StepVersion.status == "approved",
        )
        .limit(1)
    )
    if approved is not None:
        return approved.id
    stale = session.scalar(
        select(StepVersion)
        .where(
            StepVersion.project_id == project_id,
            StepVersion.step_key == step_key,
            StepVersion.status == "stale",
        )
        .order_by(StepVersion.version_no.desc())
        .limit(1)
    )
    return stale.id if stale else None


def is_current_review_version(session: Session, version: StepVersion) -> bool:
    current_id = find_current_version_id(
        session, version.project_id, version.step_key
    )
    return current_id == version.id and version.status == "in_review"


def copy_dependencies(
    session: Session, *, from_version_id: uuid.UUID, to_version_id: uuid.UUID
) -> None:
    rows = session.scalars(
        select(StepVersionDependency).where(
            StepVersionDependency.step_version_id == from_version_id
        )
    ).all()
    for row in rows:
        session.add(
            StepVersionDependency(
                step_version_id=to_version_id,
                depends_on_version_id=row.depends_on_version_id,
            )
        )


def upstream_dependencies_still_approved(session: Session, version_id: uuid.UUID) -> bool:
    dep_ids = session.scalars(
        select(StepVersionDependency.depends_on_version_id).where(
            StepVersionDependency.step_version_id == version_id
        )
    ).all()
    for dep_id in dep_ids:
        dep = session.get(StepVersion, dep_id)
        if dep is None or dep.status != "approved":
            return False
    return True


def compute_step_action_flags(
    session: Session,
    *,
    project: Project,
    step_key: str,
    actor: User,
    has_request_changes_perm: bool,
    has_approve_perm: bool,
) -> tuple[uuid.UUID | None, bool, bool, str | None]:
    current_id = find_current_version_id(session, project.id, step_key)
    can_req = False
    can_app = False
    approve_blocked: str | None = None

    if project.status != "active":
        return current_id, can_req, can_app, approve_blocked

    try:
        defn = get_step(step_key)
    except KeyError:
        return current_id, can_req, can_app, approve_blocked

    if not defn.implemented:
        return current_id, can_req, can_app, approve_blocked

    if step_has_in_flight(session, project.id, step_key):
        if has_approve_perm and current_id is not None:
            in_rev = session.get(StepVersion, current_id)
            if in_rev is not None and in_rev.status == "in_review":
                approve_blocked = ERR_IN_FLIGHT
        return current_id, can_req, can_app, approve_blocked

    if current_id is None:
        return current_id, can_req, can_app, approve_blocked

    current = session.get(StepVersion, current_id)
    if current is None or current.status != "in_review":
        return current_id, can_req, can_app, approve_blocked

    if has_request_changes_perm:
        can_req = True
    if has_approve_perm:
        if self_approval_allowed(session, project, actor, current):
            can_app = True
        else:
            approve_blocked = SELF_APPROVAL_FORBIDDEN

    return current_id, can_req, can_app, approve_blocked

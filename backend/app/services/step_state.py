"""Pure workflow step status derivation (no database I/O)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal

from app.steps.definitions import get_step, previous_step

ProjectStatus = Literal["active", "completed", "archived"]

IN_FLIGHT_STATUSES = frozenset({"queued", "generating"})
REVIEW_STATUSES = frozenset({"in_review", "changes_requested"})


class DerivedStepStatus(str, Enum):
    LOCKED = "locked"
    READY = "ready"
    GENERATING = "generating"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    STALE = "stale"


@dataclass(frozen=True)
class VersionSnapshot:
    version_no: int
    status: str


@dataclass(frozen=True)
class StepStatusResult:
    status: DerivedStepStatus
    has_failed_attempt: bool


def _latest(versions: list[VersionSnapshot]) -> VersionSnapshot | None:
    if not versions:
        return None
    return max(versions, key=lambda v: v.version_no)


def _has_approved(versions: list[VersionSnapshot]) -> bool:
    return any(v.status == "approved" for v in versions)


def _previous_step_approved(
    step_key: str, versions_by_step: dict[str, list[VersionSnapshot]]
) -> bool:
    prev = previous_step(step_key)
    if prev is None:
        return True
    return _has_approved(versions_by_step.get(prev.key, []))


def _prerequisites_for_ready(
    step_key: str,
    project_status: ProjectStatus,
    versions_by_step: dict[str, list[VersionSnapshot]],
) -> bool:
    if step_key == "scope_analysis":
        return project_status == "active"
    return _previous_step_approved(step_key, versions_by_step)


def derive_step_status(
    step_key: str,
    versions_by_step: dict[str, list[VersionSnapshot]],
    project_status: ProjectStatus,
) -> StepStatusResult:
    versions = versions_by_step.get(step_key, [])
    latest = _latest(versions)

    if latest is not None:
        if latest.status in IN_FLIGHT_STATUSES:
            return StepStatusResult(DerivedStepStatus.GENERATING, False)
        if latest.status in REVIEW_STATUSES:
            return StepStatusResult(DerivedStepStatus.IN_REVIEW, False)
        if latest.status == "stale":
            return StepStatusResult(DerivedStepStatus.STALE, False)
        if latest.status == "approved":
            return StepStatusResult(DerivedStepStatus.APPROVED, False)
        if latest.status == "failed":
            if any(v.status == "in_review" for v in versions):
                return StepStatusResult(DerivedStepStatus.IN_REVIEW, True)
            return StepStatusResult(DerivedStepStatus.READY, True)
        if latest.status == "superseded":
            return StepStatusResult(DerivedStepStatus.READY, False)

    if not _prerequisites_for_ready(step_key, project_status, versions_by_step):
        return StepStatusResult(DerivedStepStatus.LOCKED, False)

    return StepStatusResult(DerivedStepStatus.READY, False)


def can_generate(
    step_key: str,
    versions_by_step: dict[str, list[VersionSnapshot]],
    project_status: ProjectStatus,
) -> bool:
    if project_status != "active":
        return False
    if not get_step(step_key).implemented:
        return False

    versions = versions_by_step.get(step_key, [])
    if any(v.status in IN_FLIGHT_STATUSES for v in versions):
        return False

    derived = derive_step_status(step_key, versions_by_step, project_status)

    if derived.status == DerivedStepStatus.STALE:
        return step_key == "scope_analysis" or _previous_step_approved(
            step_key, versions_by_step
        )

    return derived.status == DerivedStepStatus.READY


ERR_NOT_IMPLEMENTED = "Step is not implemented yet"
ERR_PROJECT_INACTIVE = "Project is archived or completed"
ERR_IN_FLIGHT = "A generation is already in progress for this step"
ERR_LOCKED = "Previous step must be approved before generating this step"
ERR_HAS_OUTPUT = "This step already has output awaiting review or approval"
ERR_STALE_PREV = "Previous step must be approved before regenerating this step"


def blocked_reason_for_step(
    step_key: str,
    versions_by_step: dict[str, list[VersionSnapshot]],
    project_status: ProjectStatus,
) -> str | None:
    if can_generate(step_key, versions_by_step, project_status):
        return None
    try:
        defn = get_step(step_key)
    except KeyError:
        return None
    if project_status != "active":
        return ERR_PROJECT_INACTIVE
    if not defn.implemented:
        return ERR_NOT_IMPLEMENTED
    versions = versions_by_step.get(step_key, [])
    if any(v.status in IN_FLIGHT_STATUSES for v in versions):
        return ERR_IN_FLIGHT
    derived = derive_step_status(step_key, versions_by_step, project_status)
    if derived.status == DerivedStepStatus.LOCKED:
        return ERR_LOCKED
    if derived.status in (DerivedStepStatus.IN_REVIEW, DerivedStepStatus.APPROVED):
        return ERR_HAS_OUTPUT
    if (
        derived.status == DerivedStepStatus.STALE
        and step_key != "scope_analysis"
        and not _previous_step_approved(step_key, versions_by_step)
    ):
        return ERR_STALE_PREV
    if derived.status == DerivedStepStatus.GENERATING:
        return ERR_IN_FLIGHT
    return ERR_HAS_OUTPUT

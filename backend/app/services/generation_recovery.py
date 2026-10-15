"""Expire stuck step generation rows (startup and lazy per project)."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.auth import User
from app.models.steps import StepVersion
from app.services.audit import AuditAction, record_audit

logger = logging.getLogger(__name__)

STARTUP_RECOVERY_ADVISORY_KEY = 0x53444B5F524543  # "SDK_REC"

GENERIC_INTERRUPTED = "Generation was interrupted"


def _timeout_seconds_for_step(step_key: str) -> float:
    settings = get_settings()
    if step_key == "estimate":
        return settings.ESTIMATE_GENERATION_TIMEOUT_SECONDS
    if step_key == "srs":
        return settings.SRS_GENERATION_TIMEOUT_SECONDS
    if step_key == "sprint_plan":
        return settings.SPRINT_PLAN_GENERATION_TIMEOUT_SECONDS
    return settings.GENERATION_TIMEOUT_SECONDS


def _expiry_cutoff(step_key: str | None = None) -> datetime:
    settings = get_settings()
    base = (
        _timeout_seconds_for_step(step_key)
        if step_key
        else settings.GENERATION_TIMEOUT_SECONDS
    )
    seconds = base + settings.GENERATION_RECOVERY_MARGIN_SECONDS
    return datetime.now(UTC) - timedelta(seconds=seconds)


def _is_expired(row: StepVersion, cutoff: datetime) -> bool:
    if row.status == "generating":
        started = row.generation_started_at or row.created_at
        return started < cutoff
    if row.status == "queued":
        return row.created_at < cutoff
    return False


def expire_in_flight_for_project(session: Session, project_id: uuid.UUID) -> int:
    """Mark expired queued/generating rows failed for one project (same transaction)."""
    rows = session.scalars(
        select(StepVersion).where(
            StepVersion.project_id == project_id,
            StepVersion.status.in_(("queued", "generating")),
        )
    ).all()
    count = 0
    now = datetime.now(UTC)
    for row in rows:
        cutoff = _expiry_cutoff(row.step_key)
        if not _is_expired(row, cutoff):
            continue
        row.status = "failed"
        row.error = GENERIC_INTERRUPTED
        row.generation_finished_at = now
        record_audit(
            session,
            action=AuditAction.STEP_GENERATION_FAILED,
            actor=None,
            entity_type="step_version",
            entity_id=row.id,
            project_id=project_id,
            metadata=_recovery_metadata(row),
        )
        count += 1
        logger.info(
            "Expired stuck generation version_id=%s step_key=%s",
            row.id,
            row.step_key,
        )
    return count


def expire_in_flight_startup(session: Session) -> int:
    """Global startup sweep; caller must hold pg_try_advisory_xact_lock."""
    rows = session.scalars(
        select(StepVersion).where(
            StepVersion.status.in_(("queued", "generating")),
        )
    ).all()
    count = 0
    now = datetime.now(UTC)
    for row in rows:
        cutoff = _expiry_cutoff(row.step_key)
        if not _is_expired(row, cutoff):
            continue
        row.status = "failed"
        row.error = GENERIC_INTERRUPTED
        row.generation_finished_at = now
        record_audit(
            session,
            action=AuditAction.STEP_GENERATION_FAILED,
            actor=None,
            entity_type="step_version",
            entity_id=row.id,
            project_id=row.project_id,
            metadata=_recovery_metadata(row),
        )
        count += 1
    if count:
        logger.info("Startup recovery marked %s stuck generation(s) failed", count)
    return count


def try_startup_recovery(session: Session) -> None:
    """Run startup recovery inside a transaction with an xact advisory lock."""
    with session.begin():
        acquired = session.execute(
            text("SELECT pg_try_advisory_xact_lock(:key)"),
            {"key": STARTUP_RECOVERY_ADVISORY_KEY},
        ).scalar()
        if not acquired:
            return
        expire_in_flight_startup(session)


def _recovery_metadata(row: StepVersion) -> dict[str, object]:
    return {
        "version_id": str(row.id),
        "step_key": row.step_key,
        "version_no": row.version_no,
        "recovery": True,
    }


def load_actor_for_version(session: Session, version: StepVersion) -> User | None:
    if version.created_by is None:
        return None
    return session.get(User, version.created_by)

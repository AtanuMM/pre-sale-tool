"""Step generation request handling and background worker."""

from __future__ import annotations

import logging
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.llm.gemini import (
    LLMError,
    LLMValidationError,
    generate_structured_result,
)
from app.llm.prompts.assembly import PromptAssemblyError
from app.models.auth import User
from app.models.projects import Project
from app.models.steps import StepVersion, StepVersionDependency
from app.schemas.steps import StepVersionSummaryOut
from app.services.audit import AuditAction, record_audit
from app.services.generation_recovery import (
    expire_in_flight_for_project,
    load_actor_for_version,
)
from app.services.prompt_intake import project_has_readable_content
from app.services.step_prompts import assemble_step_prompt, assemble_step_revise_prompt
from app.services.step_queries import version_to_summary
from app.services.step_soft_caps import apply_soft_list_caps
from app.services.step_state import (
    ERR_HAS_OUTPUT,
    ERR_IN_FLIGHT,
    ERR_NOT_IMPLEMENTED,
    VersionSnapshot,
    blocked_reason_for_step,
    can_generate,
)
from app.steps.definitions import get_step

logger = logging.getLogger(__name__)

ERR_RACE = "Could not start generation; try again"
ERR_NO_CONTENT = "No readable content to analyse"

ERR_GENERIC_FAIL = "Generation failed. Please try again."
ERR_GENERIC_TIMEOUT = "Generation timed out. Please try again."

_GEN_EXECUTOR = ThreadPoolExecutor(max_workers=8, thread_name_prefix="step-gen")
_concurrency_sem: threading.BoundedSemaphore | None = None


def shutdown_generation_executor() -> None:
    _GEN_EXECUTOR.shutdown(wait=False, cancel_futures=True)


def reset_generation_limits_for_tests() -> None:
    global _concurrency_sem
    _concurrency_sem = None


def _generate_reject_reason(
    step_key: str,
    versions_by_step: dict[str, list[VersionSnapshot]],
    project_status: str,
) -> str:
    reason = blocked_reason_for_step(
        step_key, versions_by_step, project_status  # type: ignore[arg-type]
    )
    return reason or ERR_HAS_OUTPUT


def _approved_dependency_ids(
    session: Session, project_id: uuid.UUID, step_key: str
) -> list[uuid.UUID]:
    defn = get_step(step_key)
    ids: list[uuid.UUID] = []
    for ctx_key in defn.context_steps:
        row = session.scalar(
            select(StepVersion).where(
                StepVersion.project_id == project_id,
                StepVersion.step_key == ctx_key,
                StepVersion.status == "approved",
            )
        )
        if row is None:
            continue
        ids.append(row.id)
    return ids


def request_step_generation(
    session: Session,
    *,
    project_id: uuid.UUID,
    step_key: str,
    actor: User,
    audit_ip: str | None,
    audit_ua: str | None,
) -> StepVersionSummaryOut:
    expire_in_flight_for_project(session, project_id)

    project = session.scalar(
        select(Project).where(Project.id == project_id).with_for_update()
    )
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    try:
        defn = get_step(step_key)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Step not found") from None

    if not defn.implemented:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=ERR_NOT_IMPLEMENTED)

    rows = session.scalars(
        select(StepVersion).where(StepVersion.project_id == project_id)
    ).all()
    grouped: dict[str, list[VersionSnapshot]] = {}
    for row in rows:
        grouped.setdefault(row.step_key, []).append(
            VersionSnapshot(version_no=row.version_no, status=row.status)
        )

    if not can_generate(step_key, grouped, project.status):  # type: ignore[arg-type]
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_generate_reject_reason(step_key, grouped, project.status),
        )

    if not project_has_readable_content(session, project_id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=ERR_NO_CONTENT,
        )

    max_no = session.scalar(
        select(func.max(StepVersion.version_no)).where(
            StepVersion.project_id == project_id,
            StepVersion.step_key == step_key,
        )
    )
    next_no = (max_no or 0) + 1

    version = StepVersion(
        project_id=project_id,
        step_key=step_key,
        version_no=next_no,
        status="queued",
        source="generated",
        content=None,
        inputs={},
        created_by=actor.id,
    )
    session.add(version)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=ERR_RACE if "version_no" in str(exc).lower() else ERR_IN_FLIGHT,
        ) from exc

    for dep_id in _approved_dependency_ids(session, project_id, step_key):
        session.add(
            StepVersionDependency(
                step_version_id=version.id,
                depends_on_version_id=dep_id,
            )
        )

    record_audit(
        session,
        action=AuditAction.STEP_GENERATE_REQUESTED,
        actor=actor,
        entity_type="step_version",
        entity_id=version.id,
        project_id=project_id,
        metadata={
            "version_id": str(version.id),
            "step_key": step_key,
            "version_no": next_no,
        },
        ip_address=audit_ip,
        user_agent=audit_ua,
    )
    session.commit()
    session.refresh(version)
    return version_to_summary(session, version)


def run_generation(version_id: uuid.UUID) -> None:
    settings = get_settings()
    sem = _acquire_concurrency_slot(settings.MAX_CONCURRENT_GENERATIONS)
    future = _GEN_EXECUTOR.submit(_generation_worker, version_id)
    try:
        future.result(timeout=settings.GENERATION_TIMEOUT_SECONDS)
    except FuturesTimeoutError:
        logger.warning("Generation wall-clock timeout version_id=%s", version_id)
        _mark_failed(version_id, ERR_GENERIC_TIMEOUT, duration_ms=None)
    finally:
        _release_when_done(future, sem)


def _acquire_concurrency_slot(limit: int) -> threading.BoundedSemaphore:
    global _concurrency_sem
    if _concurrency_sem is None:
        _concurrency_sem = threading.BoundedSemaphore(limit)
    _concurrency_sem.acquire()
    return _concurrency_sem


def _release_when_done(future: Future[object], sem) -> None:
    if future.done():
        sem.release()
    else:
        future.add_done_callback(lambda _f: sem.release())


def _generation_worker(version_id: uuid.UUID) -> None:
    from app.db import get_session_factory

    settings = get_settings()
    factory = get_session_factory()
    started = time.monotonic()

    with factory() as session:
        version = session.get(StepVersion, version_id)
        if version is None or version.status != "queued":
            return
        version.status = "generating"
        version.generation_started_at = datetime.now(UTC)
        session.commit()

    actor: User | None = None
    assembled_prompt: str | None = None
    prompt_version: str | None = None
    inputs_meta: dict = {}
    system_instruction: str | None = None

    try:
        with factory() as session:
            version = session.get(StepVersion, version_id)
            if version is None or version.status != "generating":
                return
            actor = load_actor_for_version(session, version)
            defn = get_step(version.step_key)
            if not defn.implemented or defn.output_schema is None:
                raise LLMError("step not implemented")
            block_nonce = str(version_id)
            try:
                if version.based_on_version_id and version.instructions:
                    assembled = assemble_step_revise_prompt(
                        session,
                        step_key=version.step_key,
                        project_id=version.project_id,
                        base_version_id=version.based_on_version_id,
                        reviewer_instructions=version.instructions,
                        block_nonce=block_nonce,
                    )
                else:
                    assembled = assemble_step_prompt(
                        session,
                        step_key=version.step_key,
                        project_id=version.project_id,
                        block_nonce=block_nonce,
                    )
            except PromptAssemblyError as exc:
                raise LLMError(str(exc)) from exc
            assembled_prompt = assembled.user_prompt
            system_instruction = assembled.system_instruction
            prompt_version = assembled.prompt_version
            inputs_meta = dict(assembled.inputs_metadata)
            version.inputs = inputs_meta
            step_key = version.step_key
            session.commit()

        output_schema = get_step(step_key).output_schema
        assert output_schema is not None

        deadline = time.monotonic() + settings.GENERATION_TIMEOUT_SECONDS
        result = generate_structured_result(
            assembled_prompt,
            output_schema,
            system=system_instruction,
            deadline=deadline,
        )
        defn = get_step(step_key)
        list_trim, trimmed = apply_soft_list_caps(defn, result.data)
        inputs_meta = {**inputs_meta, **list_trim}
        inputs_meta["generation_attempt_count"] = result.api_attempt_count
        duration_ms = int((time.monotonic() - started) * 1000)

        _finalize_generating_success(
            version_id,
            actor=actor,
            content=trimmed.model_dump(mode="json"),
            inputs_meta=inputs_meta,
            model_id=result.model_id or settings.GEMINI_MODEL,
            prompt_version=prompt_version,
            assembled_prompt=assembled_prompt,
            tokens_in=result.tokens_in,
            tokens_out=result.tokens_out,
            duration_ms=duration_ms,
        )
    except (LLMError, LLMValidationError) as exc:
        logger.info(
            "Generation failed version_id=%s error_type=%s",
            version_id,
            type(exc).__name__,
        )
        msg = ERR_GENERIC_TIMEOUT if "timeout" in str(exc).lower() else ERR_GENERIC_FAIL
        duration_ms = int((time.monotonic() - started) * 1000)
        _finalize_generating_failed(version_id, msg, duration_ms=duration_ms)
    except Exception:
        logger.exception("Unexpected generation error version_id=%s", version_id)
        duration_ms = int((time.monotonic() - started) * 1000)
        _finalize_generating_failed(version_id, ERR_GENERIC_FAIL, duration_ms=duration_ms)


def _finalize_generating_success(
    version_id: uuid.UUID,
    *,
    actor: User | None,
    content: dict,
    inputs_meta: dict,
    model_id: str,
    prompt_version: str | None,
    assembled_prompt: str | None,
    tokens_in: int | None,
    tokens_out: int | None,
    duration_ms: int,
) -> None:
    from app.db import get_session_factory

    factory = get_session_factory()
    with factory() as session:
        version = session.scalar(
            select(StepVersion)
            .where(StepVersion.id == version_id, StepVersion.status == "generating")
            .with_for_update()
        )
        if version is None:
            logger.warning(
                "Discarding stale generation success version_id=%s",
                version_id,
            )
            return
        actor = load_actor_for_version(session, version) or actor
        version.content = content
        version.inputs = inputs_meta
        version.model_id = model_id
        version.prompt_version = prompt_version
        version.assembled_prompt = assembled_prompt
        version.tokens_in = tokens_in
        version.tokens_out = tokens_out
        version.status = "in_review"
        version.generation_finished_at = datetime.now(UTC)
        if version.based_on_version_id and version.instructions:
            base = session.get(StepVersion, version.based_on_version_id)
            if base is not None and base.status == "in_review":
                base.status = "changes_requested"
        record_audit(
            session,
            action=AuditAction.STEP_GENERATED,
            actor=actor,
            entity_type="step_version",
            entity_id=version.id,
            project_id=version.project_id,
            metadata=_success_metadata(version, duration_ms),
        )
        session.commit()


def _finalize_generating_failed(
    version_id: uuid.UUID,
    message: str,
    *,
    duration_ms: int | None = None,
) -> None:
    from app.db import get_session_factory

    factory = get_session_factory()
    with factory() as session:
        version = session.scalar(
            select(StepVersion)
            .where(StepVersion.id == version_id, StepVersion.status == "generating")
            .with_for_update()
        )
        if version is None:
            logger.warning(
                "Discarding stale generation failure version_id=%s",
                version_id,
            )
            return
        actor = load_actor_for_version(session, version)
        version.status = "failed"
        version.error = message
        version.generation_finished_at = datetime.now(UTC)
        record_audit(
            session,
            action=AuditAction.STEP_GENERATION_FAILED,
            actor=actor,
            entity_type="step_version",
            entity_id=version.id,
            project_id=version.project_id,
            metadata=_failure_metadata(version, duration_ms),
        )
        session.commit()


def _mark_failed(
    version_id: uuid.UUID,
    message: str,
    *,
    duration_ms: int | None = None,
) -> None:
    from app.db import get_session_factory

    factory = get_session_factory()
    with factory() as session:
        version = session.scalar(
            select(StepVersion)
            .where(
                StepVersion.id == version_id,
                StepVersion.status.in_(("queued", "generating")),
            )
            .with_for_update()
        )
        if version is None:
            logger.warning(
                "Discarding stale generation failure version_id=%s",
                version_id,
            )
            return
        actor = load_actor_for_version(session, version)
        version.status = "failed"
        version.error = message
        version.generation_finished_at = datetime.now(UTC)
        record_audit(
            session,
            action=AuditAction.STEP_GENERATION_FAILED,
            actor=actor,
            entity_type="step_version",
            entity_id=version.id,
            project_id=version.project_id,
            metadata=_failure_metadata(version, duration_ms),
        )
        session.commit()


def _success_metadata(version: StepVersion, duration_ms: int) -> dict[str, object]:
    return {
        "version_id": str(version.id),
        "step_key": version.step_key,
        "version_no": version.version_no,
        "model_id": version.model_id,
        "prompt_version": version.prompt_version,
        "tokens_in": version.tokens_in,
        "tokens_out": version.tokens_out,
        "duration_ms": duration_ms,
    }


def _failure_metadata(
    version: StepVersion, duration_ms: int | None
) -> dict[str, object]:
    meta: dict[str, object] = {
        "version_id": str(version.id),
        "step_key": version.step_key,
        "version_no": version.version_no,
    }
    if duration_ms is not None:
        meta["duration_ms"] = duration_ms
    if version.model_id:
        meta["model_id"] = version.model_id
    if version.prompt_version:
        meta["prompt_version"] = version.prompt_version
    return meta

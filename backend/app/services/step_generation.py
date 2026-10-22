"""Step generation request handling and background worker."""

from __future__ import annotations

import logging
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from datetime import UTC, datetime
from typing import Any

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
from app.services.step_prompts import (
    assemble_step_prompt,
    assemble_step_revise_prompt,
)
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
from app.steps.definitions import StepDefinition, get_step
from app.steps.input_fields import (
    StepInputValidationError,
    user_inputs_audit_metadata,
    validate_step_inputs,
)
from app.steps.postprocess import PostprocessContext, PostprocessError
from app.steps.refs import ref_sections, section_ref_count

logger = logging.getLogger(__name__)

ERR_RACE = "Could not start generation; try again"
ERR_NO_CONTENT = "No readable content to analyse"

ERR_GENERIC_FAIL = "Generation failed. Please try again."
ERR_GENERIC_TIMEOUT = "Generation timed out. Please try again."


def _sum_optional(current: int | None, added: int | None) -> int | None:
    if added is None:
        return current
    if current is None:
        return added
    return current + added

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


def _approved_content(
    session: Session, project_id: uuid.UUID, step_key: str
) -> dict[str, Any] | None:
    row = session.scalar(
        select(StepVersion).where(
            StepVersion.project_id == project_id,
            StepVersion.step_key == step_key,
            StepVersion.status == "approved",
        )
    )
    if row is None or not isinstance(row.content, dict):
        return None
    return row.content


def _load_estimate_user_inputs(session: Session, project_id: uuid.UUID) -> dict[str, Any]:
    row = session.scalar(
        select(StepVersion).where(
            StepVersion.project_id == project_id,
            StepVersion.step_key == "estimate",
            StepVersion.status == "approved",
        )
    )
    if row is None or not isinstance(row.inputs, dict):
        return {}
    raw = row.inputs.get("user_inputs")
    return dict(raw) if isinstance(raw, dict) else {}


def _postprocess_context(
    session: Session,
    project_id: uuid.UUID,
    defn: StepDefinition,
    user_inputs: dict[str, Any] | None = None,
    *,
    version_no: int = 1,
) -> PostprocessContext:
    settings = get_settings()
    ref_counts: dict[str, int] = {}
    for ctx_key in defn.context_steps:
        ctx_defn = get_step(ctx_key)
        row_content = _approved_content(session, project_id, ctx_key)
        if row_content is None:
            continue
        for section in ref_sections(ctx_defn.layout):
            if section.ref_prefix:
                ref_counts[section.ref_prefix] = section_ref_count(row_content, section)

    feature_ids: list[str] = []
    feature_titles: dict[str, str] = {}
    feature_priorities: dict[str, str] = {}
    feature_depends: dict[str, tuple[str, ...]] = {}
    feature_risk_domains: dict[str, str] = {}
    feature_origins: dict[str, str] = {}
    feature_gap_refs: dict[str, tuple[str, ...]] = {}
    implied_count = 0
    suggested_count = 0
    source_requirements_total = 0
    features_content = _approved_content(session, project_id, "feature_list")
    if features_content is not None:
        raw_total = features_content.get("source_requirements_total")
        if isinstance(raw_total, int):
            source_requirements_total = raw_total
        raw_features = features_content.get("features")
        if isinstance(raw_features, list):
            for item in raw_features:
                if not isinstance(item, dict):
                    continue
                fid = str(item.get("id") or "").strip()
                if not fid:
                    continue
                feature_ids.append(fid)
                feature_titles[fid] = str(item.get("title") or fid)
                feature_priorities[fid] = str(item.get("priority") or "must")
                origin = str(item.get("origin") or "stated")
                feature_origins[fid] = origin
                if origin == "implied":
                    implied_count += 1
                elif origin == "suggested":
                    suggested_count += 1
                feature_risk_domains[fid] = str(item.get("primary_risk_domain") or "none")
                deps = item.get("depends_on_ids")
                if isinstance(deps, list):
                    feature_depends[fid] = tuple(str(d) for d in deps if isinstance(d, str))
                else:
                    feature_depends[fid] = ()
                gaps = item.get("linked_gap_refs")
                if isinstance(gaps, list):
                    feature_gap_refs[fid] = tuple(str(g) for g in gaps if isinstance(g, str))
                else:
                    feature_gap_refs[fid] = ()

    high_medium: list[str] = []
    gap_severities: dict[str, str] = {}
    gap_content = _approved_content(session, project_id, "gap_analysis")
    if gap_content is not None:
        gaps = gap_content.get("gaps")
        if isinstance(gaps, list):
            for index, gap in enumerate(gaps, start=1):
                if not isinstance(gap, dict):
                    continue
                ref = f"G-{index}"
                sev = str(gap.get("severity") or "")
                if sev:
                    gap_severities[ref] = sev
                if sev in ("high", "medium"):
                    high_medium.append(ref)

    inputs = user_inputs or {}
    team = inputs.get("team") if isinstance(inputs.get("team"), list) else []
    estimated_names: list[str] = []
    role_disciplines: dict[str, str] = {}
    for row in team:
        if isinstance(row, dict) and row.get("mode") == "estimated":
            role = str(row.get("role") or "").strip()
            if role:
                estimated_names.append(role)
                role_disciplines[role] = str(row.get("discipline") or "other")
    phases_raw = inputs.get("phases")
    selected_phases = (
        tuple(str(p) for p in phases_raw) if isinstance(phases_raw, list) else ()
    )

    estimate_user_inputs = _load_estimate_user_inputs(session, project_id)
    if defn.key == "sow":
        team = estimate_user_inputs.get("team")
        if isinstance(team, list):
            estimated_names = []
            for row in team:
                if isinstance(row, dict) and row.get("mode") == "estimated":
                    role = str(row.get("role") or "").strip()
                    if role:
                        estimated_names.append(role)

    return PostprocessContext(
        ref_counts=ref_counts,
        max_features=settings.FEATURE_LIST_MAX_FEATURES,
        feature_ids=tuple(feature_ids),
        feature_titles=feature_titles,
        feature_priorities=feature_priorities,
        feature_depends=feature_depends,
        high_medium_gap_refs=tuple(high_medium),
        selected_phases=selected_phases,
        estimated_role_names=tuple(estimated_names),
        user_inputs=inputs,
        max_work_packages=settings.ESTIMATE_MAX_WORK_PACKAGES,
        max_effort_lines=settings.ESTIMATE_MAX_EFFORT_LINES,
        max_assumptions=settings.ESTIMATE_MAX_ASSUMPTIONS,
        max_components=settings.ESTIMATE_MAX_COMPONENTS,
        feature_risk_domains=feature_risk_domains,
        feature_origins=feature_origins,
        feature_gap_refs=feature_gap_refs,
        gap_severities=gap_severities,
        role_disciplines=role_disciplines,
        source_requirements_total=source_requirements_total,
        implied_count=implied_count,
        suggested_count=suggested_count,
        project_id=str(project_id),
        version_no=version_no,
        scope_content=_approved_content(session, project_id, "scope_analysis"),
        gap_content=_approved_content(session, project_id, "gap_analysis"),
        feature_list_content=_approved_content(session, project_id, "feature_list"),
        estimate_content=_approved_content(session, project_id, "estimate"),
        estimate_user_inputs=estimate_user_inputs,
    )


def request_step_generation(
    session: Session,
    *,
    project_id: uuid.UUID,
    step_key: str,
    actor: User,
    audit_ip: str | None,
    audit_ua: str | None,
    raw_inputs: dict[str, Any] | None = None,
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

    try:
        cleaned_inputs = validate_step_inputs(defn.input_fields, raw_inputs)
    except StepInputValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=[{"type": "value_error", **item} for item in exc.errors],
        ) from exc

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

    initial_inputs: dict[str, Any] = {}
    if cleaned_inputs:
        initial_inputs["user_inputs"] = cleaned_inputs
    version = StepVersion(
        project_id=project_id,
        step_key=step_key,
        version_no=next_no,
        status="queued",
        source="generated",
        content=None,
        inputs=initial_inputs,
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
            **(
                {
                    "user_inputs": user_inputs_audit_metadata(
                        defn.input_fields, cleaned_inputs
                    )
                }
                if defn.input_fields
                else {}
            ),
        },
        ip_address=audit_ip,
        user_agent=audit_ua,
    )
    session.commit()
    session.refresh(version)
    return version_to_summary(session, version)


def run_generation(version_id: uuid.UUID) -> None:
    settings = get_settings()
    timeout = settings.GENERATION_TIMEOUT_SECONDS
    from app.db import get_session_factory

    factory = get_session_factory()
    with factory() as session:
        version = session.get(StepVersion, version_id)
        if version is not None and version.step_key == "estimate":
            timeout = settings.ESTIMATE_GENERATION_TIMEOUT_SECONDS
        elif version is not None and version.step_key == "srs":
            timeout = settings.SRS_GENERATION_TIMEOUT_SECONDS
        elif version is not None and version.step_key == "sprint_plan":
            timeout = settings.SPRINT_PLAN_GENERATION_TIMEOUT_SECONDS
        elif version is not None and version.step_key == "frs":
            timeout = settings.FRS_GENERATION_TIMEOUT_SECONDS
    sem = _acquire_concurrency_slot(settings.MAX_CONCURRENT_GENERATIONS)
    future = _GEN_EXECUTOR.submit(_generation_worker, version_id)
    try:
        future.result(timeout=timeout)
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
            existing_inputs = dict(version.inputs or {})
            raw_user = existing_inputs.get("user_inputs")
            user_inputs = dict(raw_user) if isinstance(raw_user, dict) else {}
            step_key = version.step_key
            based_on_version_id = version.based_on_version_id
            instructions = version.instructions
            previous_prompt = None
            if based_on_version_id is not None:
                base_row = session.get(StepVersion, based_on_version_id)
                if base_row is not None:
                    previous_prompt = base_row.assembled_prompt
            version_no = version.version_no
            if step_key in ("estimate", "srs", "sprint_plan", "frs"):
                inputs_meta = {**existing_inputs}
                if user_inputs:
                    inputs_meta["user_inputs"] = user_inputs
                version.inputs = inputs_meta
                session.commit()
            elif (
                defn.supports_reassemble
                and instructions == "Inputs updated"
                and based_on_version_id is not None
                and step_key not in ("sprint_plan",)
            ):
                inputs_meta = {**existing_inputs}
                if user_inputs:
                    inputs_meta["user_inputs"] = user_inputs
                inputs_meta["reassemble"] = 1
                version.inputs = inputs_meta
                session.commit()
            else:
                try:
                    if based_on_version_id and instructions:
                        assembled = assemble_step_revise_prompt(
                            session,
                            step_key=step_key,
                            project_id=version.project_id,
                            base_version_id=based_on_version_id,
                            reviewer_instructions=instructions,
                            block_nonce=block_nonce,
                            user_inputs=user_inputs,
                        )
                    else:
                        assembled = assemble_step_prompt(
                            session,
                            step_key=step_key,
                            project_id=version.project_id,
                            block_nonce=block_nonce,
                            user_inputs=user_inputs,
                        )
                except PromptAssemblyError as exc:
                    raise LLMError(str(exc)) from exc
                assembled_prompt = assembled.user_prompt
                system_instruction = assembled.system_instruction
                prompt_version = assembled.prompt_version
                inputs_meta = {**existing_inputs, **assembled.inputs_metadata}
                if user_inputs:
                    inputs_meta["user_inputs"] = user_inputs
                version.inputs = inputs_meta
                session.commit()

        defn = get_step(step_key)
        timeout = settings.GENERATION_TIMEOUT_SECONDS
        if step_key == "estimate":
            timeout = settings.ESTIMATE_GENERATION_TIMEOUT_SECONDS
        elif step_key == "srs":
            timeout = settings.SRS_GENERATION_TIMEOUT_SECONDS
        elif step_key == "sprint_plan":
            timeout = settings.SPRINT_PLAN_GENERATION_TIMEOUT_SECONDS
        elif step_key == "frs":
            timeout = settings.FRS_GENERATION_TIMEOUT_SECONDS
        deadline = time.monotonic() + timeout
        if step_key == "sprint_plan":
            from app.services.sprint_plan_generation import run_sprint_plan

            revision_parts = existing_inputs.get("revision_parts")
            parts_list = (
                [str(p) for p in revision_parts]
                if isinstance(revision_parts, list)
                else None
            )
            reschedule_only = (
                instructions == "Inputs updated" and based_on_version_id is not None
            )
            with factory() as session:
                version = session.get(StepVersion, version_id)
                if version is None:
                    return
                ctx = _postprocess_context(
                    session,
                    version.project_id,
                    defn,
                    user_inputs=user_inputs,
                    version_no=version.version_no,
                )
            stored, extra_meta, assembled_prompt, prompt_version, tokens_in, tokens_out, api_attempts = (
                run_sprint_plan(
                    factory=factory,
                    version_id=version_id,
                    defn=defn,
                    user_inputs=user_inputs,
                    ctx=ctx,
                    deadline=deadline,
                    based_on_version_id=based_on_version_id,
                    instructions=instructions,
                    revision_parts=parts_list,
                    reschedule_only=reschedule_only,
                )
            )
            inputs_meta = {**inputs_meta, **extra_meta}
            if user_inputs:
                inputs_meta["user_inputs"] = user_inputs
            model_id = settings.GEMINI_MODEL
        elif step_key == "srs":
            from app.services.srs_generation import run_srs

            revision_parts = existing_inputs.get("revision_parts")
            parts_list = (
                [str(p) for p in revision_parts]
                if isinstance(revision_parts, list)
                else None
            )
            with factory() as session:
                version = session.get(StepVersion, version_id)
                if version is None:
                    return
                ctx = _postprocess_context(
                    session,
                    version.project_id,
                    defn,
                    user_inputs=user_inputs,
                    version_no=version.version_no,
                )
            stored, extra_meta, assembled_prompt, prompt_version, tokens_in, tokens_out, api_attempts = (
                run_srs(
                    factory=factory,
                    version_id=version_id,
                    defn=defn,
                    user_inputs=user_inputs,
                    ctx=ctx,
                    deadline=deadline,
                    based_on_version_id=based_on_version_id,
                    instructions=instructions,
                    revision_parts=parts_list,
                )
            )
            inputs_meta = {**inputs_meta, **extra_meta}
            if user_inputs:
                inputs_meta["user_inputs"] = user_inputs
            model_id = settings.GEMINI_MODEL
        elif step_key == "frs":
            from app.services.frs_generation import run_frs

            revision_parts = existing_inputs.get("revision_parts")
            parts_list = (
                [str(p) for p in revision_parts]
                if isinstance(revision_parts, list)
                else None
            )
            with factory() as session:
                version = session.get(StepVersion, version_id)
                if version is None:
                    return
                ctx = _postprocess_context(
                    session,
                    version.project_id,
                    defn,
                    user_inputs=user_inputs,
                    version_no=version.version_no,
                )
            stored, extra_meta, assembled_prompt, prompt_version, tokens_in, tokens_out, api_attempts = (
                run_frs(
                    factory=factory,
                    version_id=version_id,
                    defn=defn,
                    user_inputs=user_inputs,
                    ctx=ctx,
                    deadline=deadline,
                    based_on_version_id=based_on_version_id,
                    instructions=instructions,
                    revision_parts=parts_list,
                )
            )
            inputs_meta = {**inputs_meta, **extra_meta}
            if user_inputs:
                inputs_meta["user_inputs"] = user_inputs
            model_id = settings.GEMINI_MODEL
        elif (
            step_key == "sow"
            and instructions == "Inputs updated"
            and based_on_version_id is not None
            and get_step(step_key).supports_reassemble
        ):
            from app.services.sow_generation import (
                load_previous_sow,
                run_sow_reassemble,
            )

            with factory() as session:
                version = session.get(StepVersion, version_id)
                if version is None:
                    return
                ctx = _postprocess_context(
                    session,
                    version.project_id,
                    defn,
                    user_inputs=user_inputs,
                    version_no=version.version_no,
                )
                previous = load_previous_sow(session, based_on_version_id)
            if previous is None:
                raise LLMError("reassemble base missing")
            stored, validation_notes = run_sow_reassemble(previous=previous, ctx=ctx)
            inputs_meta = {**inputs_meta, "validation_notes": validation_notes, "reassemble": 1}
            tokens_in = 0
            tokens_out = 0
            api_attempts = 0
            prompt_version = "reassemble"
            assembled_prompt = None
            model_id = ""
        elif step_key == "estimate":
            from app.services.estimate_generation import run_estimate_v2

            with factory() as session:
                version = session.get(StepVersion, version_id)
                if version is None:
                    return
                ctx = _postprocess_context(
                    session,
                    version.project_id,
                    defn,
                    user_inputs=user_inputs,
                    version_no=version.version_no,
                )
            stored, extra_meta, assembled_prompt, prompt_version, tokens_in, tokens_out, api_attempts = (
                run_estimate_v2(
                    factory=factory,
                    version_id=version_id,
                    defn=defn,
                    user_inputs=user_inputs,
                    block_nonce=block_nonce,
                    deadline=deadline,
                    ctx=ctx,
                    based_on_version_id=based_on_version_id,
                    instructions=instructions,
                    previous_prompt=previous_prompt,
                )
            )
            inputs_meta = {**inputs_meta, **extra_meta}
            if user_inputs:
                inputs_meta["user_inputs"] = user_inputs
            model_id = settings.GEMINI_MODEL
        elif step_key == "sow":
            from app.services.sow_generation import run_sow_postprocess_with_repair
            from app.steps.schemas.sow import SowNarrativeOutput

            output_schema = SowNarrativeOutput
            result = generate_structured_result(
                assembled_prompt,
                output_schema,
                system=system_instruction,
                deadline=deadline,
                max_output_tokens=defn.max_output_tokens,
            )
            list_trim, trimmed = apply_soft_list_caps(defn, result.data)
            inputs_meta = {**inputs_meta, **list_trim}
            tokens_in = result.tokens_in
            tokens_out = result.tokens_out
            api_attempts = result.api_attempt_count
            if not isinstance(trimmed, SowNarrativeOutput):
                trimmed = SowNarrativeOutput.model_validate(trimmed.model_dump())
            with factory() as session:
                version = session.get(StepVersion, version_id)
                if version is None:
                    return
                ctx = _postprocess_context(
                    session,
                    version.project_id,
                    defn,
                    user_inputs=user_inputs,
                    version_no=version.version_no,
                )
            stored, extra_meta, repair_attempts = run_sow_postprocess_with_repair(
                factory=factory,
                version_id=version_id,
                narrative=trimmed,
                ctx=ctx,
                deadline=deadline,
            )
            inputs_meta = {**inputs_meta, **extra_meta}
            api_attempts += repair_attempts
            model_id = result.model_id or settings.GEMINI_MODEL
        else:
            output_schema = defn.output_schema
            assert output_schema is not None
            result = generate_structured_result(
                assembled_prompt,
                output_schema,
                system=system_instruction,
                deadline=deadline,
                max_output_tokens=defn.max_output_tokens,
            )
            list_trim, trimmed = apply_soft_list_caps(defn, result.data)
            inputs_meta = {**inputs_meta, **list_trim}
            tokens_in = result.tokens_in
            tokens_out = result.tokens_out
            api_attempts = result.api_attempt_count
            stored = trimmed
            if defn.postprocess is not None:
                with factory() as session:
                    version = session.get(StepVersion, version_id)
                    if version is None:
                        return
                    ctx = _postprocess_context(
                        session,
                        version.project_id,
                        defn,
                        user_inputs=user_inputs,
                        version_no=version.version_no,
                    )
                try:
                    stored, validation_notes = defn.postprocess(trimmed, ctx)
                except PostprocessError as exc:
                    raise LLMError(str(exc)) from exc
                inputs_meta["validation_notes"] = validation_notes
            model_id = result.model_id or settings.GEMINI_MODEL
        inputs_meta["generation_attempt_count"] = api_attempts
        duration_ms = int((time.monotonic() - started) * 1000)

        _finalize_generating_success(
            version_id,
            actor=actor,
            content=stored.model_dump(mode="json"),
            inputs_meta=inputs_meta,
            model_id=model_id,
            prompt_version=prompt_version,
            assembled_prompt=assembled_prompt,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            duration_ms=duration_ms,
        )
    except (LLMError, LLMValidationError) as exc:
        detail = _safe_failure_detail(exc)
        logger.warning(
            "Generation failed version_id=%s error_type=%s detail=%s",
            version_id,
            type(exc).__name__,
            detail,
        )
        msg = ERR_GENERIC_TIMEOUT if "timeout" in str(exc).lower() else ERR_GENERIC_FAIL
        duration_ms = int((time.monotonic() - started) * 1000)
        _finalize_generating_failed(
            version_id,
            msg,
            duration_ms=duration_ms,
            failure_code=_safe_failure_code(exc),
            failure_detail=detail,
        )
    except Exception:
        logger.exception("Unexpected generation error version_id=%s", version_id)
        duration_ms = int((time.monotonic() - started) * 1000)
        _finalize_generating_failed(
            version_id,
            ERR_GENERIC_FAIL,
            duration_ms=duration_ms,
            failure_code="unexpected_error",
        )


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


_SAFE_FAILURE_CODES = {
    "no valid effort lines": "no_valid_effort_lines",
    "unexpected output type for estimate v2": "unexpected_output_type",
    "estimate output failed validation": "estimate_validation",
    "estimate compute failed": "estimate_compute_failed",
    "generation timeout exceeded": "generation_timeout",
    "version missing": "version_missing",
}


def _safe_failure_detail(exc: BaseException) -> str:
    raw = " ".join(str(exc).split())
    if len(raw) > 180:
        raw = raw[:177] + "..."
    return raw or type(exc).__name__


def _safe_failure_code(exc: BaseException) -> str | None:
    if isinstance(exc, LLMValidationError):
        return "llm_validation"
    mapped = _SAFE_FAILURE_CODES.get(str(exc))
    if mapped is not None:
        return mapped
    if isinstance(exc, LLMError):
        msg = str(exc).lower()
        if "invalid_argument" in msg or "400" in msg:
            return "llm_schema_rejected"
        if "rate" in msg and "limit" in msg:
            return "llm_rate_limit"
        return "llm_error"
    return None


def _finalize_generating_failed(
    version_id: uuid.UUID,
    message: str,
    *,
    duration_ms: int | None = None,
    failure_code: str | None = None,
    failure_detail: str | None = None,
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
        if failure_code or failure_detail:
            inputs = dict(version.inputs or {})
            if failure_code:
                inputs["failure_code"] = failure_code
            if failure_detail:
                inputs["failure_detail"] = failure_detail
            version.inputs = inputs
        record_audit(
            session,
            action=AuditAction.STEP_GENERATION_FAILED,
            actor=actor,
            entity_type="step_version",
            entity_id=version.id,
            project_id=version.project_id,
            metadata=_failure_metadata(version, duration_ms, failure_code),
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
    version: StepVersion,
    duration_ms: int | None,
    failure_code: str | None = None,
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
    if failure_code:
        meta["failure_code"] = failure_code
    return meta

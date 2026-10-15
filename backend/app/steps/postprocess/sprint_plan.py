"""Sprint Plan post-processing: ids, scheduler, assembly, health."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from typing import Any

from app.steps.postprocess import PostprocessContext, PostprocessError
from app.steps.schemas.estimate import PHASE_ORDER
from app.steps.schemas.sprint_plan import (
    SprintPlanAssembled,
    SprintPlanHealthMeta,
    SprintPlanPasses,
    SprintPlanStored,
    StoredStory,
    StoryDraftItem,
)
from app.steps.sprint_scheduler import (
    SchedulerConfig,
    SchedulerRole,
    SchedulerStory,
    SchedulerWorkPackage,
    SprintSchedulerError,
    schedule_stories_and_packages,
    story_points_from_hours,
)

_WEAK_RE = re.compile(r"\b(maybe|might|possibly|etc\.?|tbd)\b", re.IGNORECASE)
_BASE_DOR = (
    "User story has clear acceptance criteria.",
    "Dependencies and data needs are identified.",
    "Story is sized for a single sprint.",
)
_BASE_DOD = (
    "Code reviewed and merged to the main branch.",
    "Automated tests pass for the story scope.",
    "Product owner accepts the demo outcome.",
)


def _parse_date(raw: Any) -> date | None:
    if not raw or not isinstance(raw, str):
        return None
    try:
        return date.fromisoformat(raw.strip()[:10])
    except ValueError:
        return None


def _feature_hours(estimate: dict[str, Any], feature_id: str) -> dict[str, float]:
    computed = estimate.get("computed") if isinstance(estimate.get("computed"), dict) else {}
    for row in computed.get("feature_rows") or []:
        if isinstance(row, dict) and row.get("id") == feature_id:
            per = row.get("per_role") if isinstance(row.get("per_role"), dict) else {}
            out: dict[str, float] = {}
            for role, cell in per.items():
                if isinstance(cell, dict):
                    out[str(role)] = float(cell.get("recommended") or 0)
            return out
    return {}


def _wp_hours(estimate: dict[str, Any], wp_id: str) -> dict[str, float]:
    computed = estimate.get("computed") if isinstance(estimate.get("computed"), dict) else {}
    for row in computed.get("work_package_rows") or []:
        if isinstance(row, dict) and row.get("id") == wp_id:
            per = row.get("per_role") if isinstance(row.get("per_role"), dict) else {}
            out: dict[str, float] = {}
            for role, cell in per.items():
                if isinstance(cell, dict):
                    out[str(role)] = float(cell.get("recommended") or 0)
            return out
    return {}


def _team_roles(estimate_user_inputs: dict[str, Any]) -> list[SchedulerRole]:
    rows = estimate_user_inputs.get("team")
    if not isinstance(rows, list):
        return []
    out: list[SchedulerRole] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        out.append(
            SchedulerRole(
                role=str(row.get("role") or ""),
                headcount=float(row.get("headcount") or 0),
                hours_per_week=float(row.get("hours_per_week") or 0),
                utilisation_pct=float(row.get("utilisation") or row.get("utilization") or 100),
                mode=str(row.get("mode") or "estimated"),
            )
        )
    return [r for r in out if r.role and r.mode == "estimated"]


def _committed_phases(estimate: dict[str, Any], estimate_inputs: dict[str, Any]) -> list[str]:
    selected = estimate_inputs.get("phases")
    if isinstance(selected, list):
        return [p for p in PHASE_ORDER if p in selected and p != "future_scope"]
    return [p for p in PHASE_ORDER if p != "future_scope"]


def _normalized_shares(items: list[StoryDraftItem]) -> list[int]:
    """Scale story shares to 100. Gemini often returns totals other than 100."""
    count = len(items)
    if count == 0:
        return []
    raw = [max(0, int(item.share_percent)) for item in items]
    total = sum(raw)
    if total <= 0:
        base, extra = divmod(100, count)
        return [base + (1 if index < extra else 0) for index in range(count)]
    scaled = [share * 100 / total for share in raw]
    floors = [int(value) for value in scaled]
    remainder = 100 - sum(floors)
    order = sorted(range(count), key=lambda index: scaled[index] - floors[index], reverse=True)
    for index in range(remainder):
        floors[order[index % count]] += 1
    return floors


def _flatten_stories(passes: SprintPlanPasses) -> list[StoryDraftItem]:
    out: list[StoryDraftItem] = []
    for batch in passes.module_stories.values():
        out.extend(batch.stories)
    if passes.repair:
        out.extend(passes.repair.extra_stories)
    return out


def _feature_phase(estimate: dict[str, Any], feature_id: str, fallback: str) -> str:
    for row in estimate.get("feature_estimates") or []:
        if isinstance(row, dict) and row.get("feature_id") == feature_id:
            return str(row.get("phase") or fallback)
    return fallback


def _story_deps(
    draft: StoryDraftItem,
    feature_id: str,
    feature_depends: dict[str, tuple[str, ...]],
    prior_keys: list[str],
    stories_by_feature: dict[str, list[str]],
    non_spike_by_feature: dict[str, list[str]],
) -> frozenset[str]:
    deps: set[str] = set()
    for fid in feature_depends.get(feature_id, ()):
        deps.update(non_spike_by_feature.get(fid, ()))
    if draft.is_spike:
        deps.update(prior_keys)
    elif draft.depends_on_previous and prior_keys:
        deps.add(prior_keys[-1])
    return frozenset(deps)


def postprocess_sprint_plan(
    draft: SprintPlanStored,
    ctx: PostprocessContext,
) -> tuple[SprintPlanStored, dict[str, int]]:
    estimate = ctx.estimate_content or {}
    if estimate.get("schema_version") != 2:
        raise PostprocessError("Estimate v2 required")

    user = ctx.user_inputs or {}
    roles = _team_roles(ctx.estimate_user_inputs)
    if not roles:
        raise PostprocessError("Estimate team required")

    config = SchedulerConfig(
        sprint_length_weeks=int(user.get("sprint_length_weeks") or 2),
        ceremony_overhead_pct=float(user.get("ceremony_overhead_pct") or 10),
        include_sprint_zero=str(user.get("include_sprint_zero") or "yes") == "yes",
        hardening_sprint_per_release=str(user.get("hardening_sprint_per_release") or "yes") == "yes",
        start_date=_parse_date(user.get("start_date")),
        non_working_periods=(),
    )

    feature_meta: dict[str, dict[str, Any]] = {}
    for item in (ctx.feature_list_content or {}).get("features") or []:
        if isinstance(item, dict):
            fid = str(item.get("id") or "")
            if fid:
                feature_meta[fid] = item

    committed_phases = _committed_phases(estimate, ctx.estimate_user_inputs)
    scheduler_stories: list[SchedulerStory] = []
    stories_by_feature: dict[str, list[str]] = {}
    non_spike_by_feature: dict[str, list[str]] = {}
    story_counter = 1

    for mod_batch in draft.passes.module_stories.values():
        by_feature: dict[str, list[StoryDraftItem]] = {}
        for s in mod_batch.stories:
            by_feature.setdefault(s.feature_id, []).append(s)
        for fid, items in by_feature.items():
            shares = _normalized_shares(items)
            meta = feature_meta.get(fid, {})
            phase = _feature_phase(estimate, fid, str(meta.get("phase") or "mvp"))
            priority = str(meta.get("priority") or "must")
            risk = str(meta.get("primary_risk_domain") or "none") not in ("", "none")
            gap_refs = ctx.feature_gap_refs.get(fid, ())
            if any(ctx.gap_severities.get(g) in ("high", "medium") for g in gap_refs):
                risk = True
            prior_keys = stories_by_feature.setdefault(fid, [])
            for index, item in enumerate(items):
                key = f"US-{story_counter:04d}"
                story_counter += 1
                base_hours = _feature_hours(estimate, fid)
                share = shares[index]
                hours = {
                    r: round(base_hours.get(r, 0) * share / 100.0, 4)
                    for r in base_hours
                }
                deps = _story_deps(
                    item,
                    fid,
                    ctx.feature_depends,
                    prior_keys,
                    stories_by_feature,
                    non_spike_by_feature,
                )
                scheduler_stories.append(
                    SchedulerStory(
                        story_key=key,
                        feature_id=fid,
                        phase=phase,
                        priority=priority,
                        risk_first=risk,
                        story_index=index,
                        part_index=0,
                        is_spike=item.is_spike,
                        depends_on_keys=deps,
                        hours_by_role=hours,
                    )
                )
                prior_keys.append(key)
                if not item.is_spike:
                    non_spike_by_feature.setdefault(fid, []).append(key)

    work_packages: list[SchedulerWorkPackage] = []
    for wp in estimate.get("work_packages") or []:
        if not isinstance(wp, dict):
            continue
        phase = str(wp.get("phase") or "mvp")
        if phase not in committed_phases:
            continue
        wp_id = str(wp.get("id") or "")
        if not wp_id:
            continue
        hours = _wp_hours(estimate, wp_id)
        if not hours or sum(hours.values()) <= 0:
            continue
        work_packages.append(
            SchedulerWorkPackage(
                wp_id=wp_id,
                phase=phase,
                package_type=str(wp.get("package_type") or "other"),
                dep_level=0,
                hours_by_role=hours,
            )
        )

    try:
        schedule = schedule_stories_and_packages(
            roles=roles,
            stories=scheduler_stories,
            work_packages=work_packages,
            committed_phases=committed_phases,
            config=config,
        )
    except SprintSchedulerError as exc:
        raise PostprocessError(str(exc)) from exc

    show_points = str(user.get("show_story_points") or "no") == "yes"
    stored_stories: list[StoredStory] = []
    draft_by_key: dict[str, StoryDraftItem] = {}
    for batch in draft.passes.module_stories.values():
        for s in batch.stories:
            draft_by_key[s.feature_id + s.title] = s

    for sched in scheduler_stories:
        match = next(
            (
                d
                for d in _flatten_stories(draft.passes)
                if d.feature_id == sched.feature_id
            ),
            None,
        )
        total_h = sum(sched.hours_by_role.values())
        stored_stories.append(
            StoredStory(
                id=sched.story_key,
                feature_id=sched.feature_id,
                title=match.title if match else sched.story_key,
                story_statement=match.story_statement if match else "",
                acceptance_criteria=list(match.acceptance_criteria) if match else [],
                is_spike=sched.is_spike,
                linked_requirement_ids=list(match.linked_requirement_ids) if match else [],
                hours_by_role=dict(sched.hours_by_role),
                story_points=story_points_from_hours(total_h) if show_points else None,
                sprint_number=schedule.placement.get(sched.story_key),
            )
        )

    computed = estimate.get("computed") if isinstance(estimate.get("computed"), dict) else {}
    phase_rows = computed.get("phase_rows") if isinstance(computed.get("phase_rows"), list) else []
    estimate_weeks = sum(
        float(r.get("weeks_planned") or 0)
        for r in phase_rows
        if isinstance(r, dict) and r.get("phase") != "future_scope"
    )
    scheduled_weeks = len([s for s in schedule.sprints if s.sprint_type == "sprint"]) * config.sprint_length_weeks
    scheduled_weeks += sum(
        config.sprint_length_weeks
        for s in schedule.sprints
        if s.sprint_type in ("sprint_zero", "hardening", "hypercare")
    )

    sow_weeks = estimate_weeks

    planning_a = draft.passes.planning_a
    planning_b = draft.passes.planning_b
    dor = list(_BASE_DOR)
    dod = list(_BASE_DOD)
    if planning_a:
        dor.extend(planning_a.definition_of_ready_additions)
        dod.extend(planning_a.definition_of_done_additions)
    lead_time_actions = [
        {
            "action": a.action,
            "owner_role": a.owner_role,
            "needed_by_phase": a.needed_by_phase,
        }
        for a in (planning_b.lead_time_actions if planning_b else [])
    ]

    weak = 0
    for st in stored_stories:
        for ac in st.acceptance_criteria:
            if _WEAK_RE.search(ac):
                weak += 1

    health_rows = [
        {"key": "scheduled_items", "label": "Committed items scheduled", "value": len(stored_stories), "status": "ok"},
        {"key": "conservation", "label": "Hours conserved", "value": 1, "status": "ok"},
        {"key": "weak_ac", "label": "Weak acceptance criteria", "value": weak, "status": "warn" if weak else "ok"},
    ]

    assembled = SprintPlanAssembled(
        document_reference=f"SPR-{datetime.now(UTC).date():%Y%m}{ctx.project_id[:6].upper()}-v{ctx.version_no}",
        schedule_sprints=[
            {
                "number": s.number,
                "name": s.name,
                "type": s.sprint_type,
                "phase": s.phase,
                "capacity_by_role": s.capacity_by_role,
                "planned_by_role": s.planned_by_role,
                "items": list(s.item_keys),
            }
            for s in schedule.sprints
        ],
        definition_of_ready=dor,
        definition_of_done=dod,
        comparison={
            "scheduled_weeks": round(scheduled_weeks, 2),
            "estimate_weeks": round(estimate_weeks, 2),
            "sow_weeks": round(sow_weeks, 2),
        },
        epics=[
            {"id": f"E-{i+1:02d}", "module": e.module, "name": e.name, "goal": e.goal}
            for i, e in enumerate(planning_a.epics if planning_a else [])
        ],
        lead_time_actions=lead_time_actions,
        unscheduled_backlog=[
            {"id": wp_id, "reason": "Could not fit in sprint capacity"}
            for wp_id in schedule.unplaced_packages
        ]
        + [
            {"id": story_id, "reason": "Could not schedule around dependencies or capacity"}
            for story_id in schedule.unplaced_stories
        ],
    )

    viewer = SprintPlanHealthMeta(health_rows=health_rows, comparison=dict(assembled.comparison))
    stored = draft.model_copy(
        update={
            "stories": stored_stories,
            "assembled": assembled,
            "viewer": viewer,
        }
    )
    notes = {
        "stories": len(stored_stories),
        "sprints": len(schedule.sprints),
        "weak_ac": weak,
    }
    return stored, notes

"""Deterministic sprint scheduling (no database access)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Literal

from app.steps.schemas.estimate import PHASE_ORDER

SprintType = Literal["sprint_zero", "sprint", "hardening", "hypercare"]

PRIORITY_RANK = {"must": 0, "should": 1, "could": 2}


class SprintSchedulerError(Exception):
    """Planning could not place all committed work."""


@dataclass(frozen=True)
class SchedulerRole:
    role: str
    headcount: float
    hours_per_week: float
    utilisation_pct: float
    mode: str = "estimated"


@dataclass(frozen=True)
class SchedulerStory:
    story_key: str
    feature_id: str
    phase: str
    priority: str
    risk_first: bool
    story_index: int
    part_index: int
    is_spike: bool
    depends_on_keys: frozenset[str]
    hours_by_role: dict[str, float]


@dataclass(frozen=True)
class SchedulerWorkPackage:
    wp_id: str
    phase: str
    package_type: str
    dep_level: int
    hours_by_role: dict[str, float]


@dataclass
class SprintSlot:
    number: int
    name: str
    sprint_type: SprintType
    phase: str
    release: str
    capacity_by_role: dict[str, float]
    planned_by_role: dict[str, float] = field(default_factory=dict)
    item_keys: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SchedulerConfig:
    sprint_length_weeks: int
    ceremony_overhead_pct: float
    include_sprint_zero: bool
    hardening_sprint_per_release: bool
    start_date: date | None = None
    non_working_periods: tuple[tuple[date, date], ...] = ()


@dataclass(frozen=True)
class ScheduleResult:
    sprints: tuple[SprintSlot, ...]
    placement: dict[str, int]
    total_hours_by_role: dict[str, float]
    unplaced_packages: tuple[str, ...] = ()
    unplaced_stories: tuple[str, ...] = ()


def _working_day_factor(config: SchedulerConfig, sprint_index: int) -> float:
    if config.start_date is None:
        return 1.0
    length = config.sprint_length_weeks
    nominal = 5 * length
    sprint_start = config.start_date + timedelta(weeks=sprint_index * length)
    sprint_end = sprint_start + timedelta(weeks=length) - timedelta(days=1)
    working = 0
    cursor = sprint_start
    while cursor <= sprint_end:
        if cursor.weekday() < 5:
            blocked = any(a <= cursor <= b for a, b in config.non_working_periods)
            if not blocked:
                working += 1
        cursor += timedelta(days=1)
    return working / nominal if nominal else 1.0


def role_capacity_per_sprint(role: SchedulerRole, config: SchedulerConfig, sprint_index: int) -> float:
    if role.mode != "estimated":
        return 0.0
    factor = _working_day_factor(config, sprint_index)
    ceremony = 1.0 - config.ceremony_overhead_pct / 100.0
    return (
        role.headcount
        * role.hours_per_week
        * (role.utilisation_pct / 100.0)
        * ceremony
        * config.sprint_length_weeks
        * factor
    )


def _phase_order(phase: str) -> int:
    if phase in PHASE_ORDER:
        return PHASE_ORDER.index(phase)
    return 99


def _story_sort_key(story: SchedulerStory) -> tuple[Any, ...]:
    return (
        _phase_order(story.phase),
        0,
        -int(story.risk_first),
        PRIORITY_RANK.get(story.priority, 9),
        story.feature_id,
        story.story_index,
        story.part_index,
    )


def _wp_sort_key(wp: SchedulerWorkPackage) -> tuple[Any, ...]:
    return (_phase_order(wp.phase), wp.dep_level, wp.wp_id)


def _total_hours(hours: dict[str, float]) -> float:
    return sum(hours.values())


def split_oversize_story(
    story: SchedulerStory,
    capacities: dict[str, float],
) -> list[SchedulerStory]:
    needed = [r for r, h in story.hours_by_role.items() if h > 0.001]
    if not needed:
        return [story]
    min_cap = min(capacities.get(r, 0.0) for r in needed)
    size_cap = min(60.0, 0.5 * min_cap) if min_cap > 0 else 60.0
    fits_whole = all(
        story.hours_by_role.get(r, 0.0) <= capacities.get(r, 0.0) + 0.001 for r in needed
    )
    max_role_hours = max(story.hours_by_role.get(r, 0.0) for r in needed)
    if fits_whole and max_role_hours <= size_cap + 0.001:
        return [story]
    if fits_whole:
        return [story]
    total = _total_hours(story.hours_by_role)
    if total <= size_cap + 0.001:
        return [story]
    parts = max(2, math.ceil(total / size_cap))
    out: list[SchedulerStory] = []
    prev_key: str | None = None
    for part in range(parts):
        ratio = 1.0 / parts
        hours = {r: round(h * ratio, 4) for r, h in story.hours_by_role.items()}
        # Keep the original key on the last part so later stories can still depend on it.
        is_last = part == parts - 1
        key = story.story_key if is_last else f"{story.story_key}-p{part + 1}"
        deps = set(story.depends_on_keys)
        if prev_key:
            deps.add(prev_key)
        out.append(
            SchedulerStory(
                story_key=key,
                feature_id=story.feature_id,
                phase=story.phase,
                priority=story.priority,
                risk_first=story.risk_first,
                story_index=story.story_index,
                part_index=part,
                is_spike=story.is_spike,
                depends_on_keys=frozenset(deps),
                hours_by_role=hours,
            )
        )
        prev_key = key
    return out


def _new_sprint(
    number: int,
    sprint_type: SprintType,
    phase: str,
    roles: list[SchedulerRole],
    config: SchedulerConfig,
) -> SprintSlot:
    sprint_index = number - 1
    cap = {
        r.role: round(role_capacity_per_sprint(r, config, sprint_index), 4)
        for r in roles
        if r.mode == "estimated"
    }
    prefix = {
        "sprint_zero": "Sprint 0",
        "hardening": f"Hardening {number}",
        "hypercare": f"Hypercare {number}",
        "sprint": f"Sprint {number}",
    }[sprint_type]
    return SprintSlot(
        number=number,
        name=prefix,
        sprint_type=sprint_type,
        phase=phase,
        release=phase,
        capacity_by_role=cap,
    )


def _fits(sprint: SprintSlot, hours: dict[str, float]) -> bool:
    for role, h in hours.items():
        if h <= 0:
            continue
        remaining = sprint.capacity_by_role.get(role, 0.0) - sprint.planned_by_role.get(role, 0.0)
        if remaining + 0.001 < h:
            return False
    return True


def _place(sprint: SprintSlot, item_key: str, hours: dict[str, float]) -> None:
    sprint.item_keys.append(item_key)
    for role, h in hours.items():
        if h <= 0:
            continue
        sprint.planned_by_role[role] = round(sprint.planned_by_role.get(role, 0.0) + h, 4)


def _deps_done(deps: frozenset[str], placement: dict[str, int], sprint_number: int) -> bool:
    for dep in deps:
        if dep not in placement:
            return False
        if placement[dep] >= sprint_number:
            return False
    return True


def schedule_stories_and_packages(
    *,
    roles: list[SchedulerRole],
    stories: list[SchedulerStory],
    work_packages: list[SchedulerWorkPackage],
    committed_phases: list[str],
    config: SchedulerConfig,
) -> ScheduleResult:
    estimated_roles = [r for r in roles if r.mode == "estimated"]
    if not estimated_roles:
        raise SprintSchedulerError("no estimated roles")

    nominal_cap = {r.role: role_capacity_per_sprint(r, config, 0) for r in estimated_roles}
    expanded: list[SchedulerStory] = []
    for s in stories:
        expanded.extend(split_oversize_story(s, nominal_cap))

    sprints: list[SprintSlot] = []
    placement: dict[str, int] = {}
    sprint_no = 0

    def add_sprint(stype: SprintType, phase: str) -> SprintSlot:
        nonlocal sprint_no
        sprint_no += 1
        sp = _new_sprint(sprint_no, stype, phase, estimated_roles, config)
        sprints.append(sp)
        return sp

    delivery_by_phase: dict[str, list[SprintSlot]] = {}

    for phase in committed_phases:
        if phase == "future_scope":
            continue
        delivery_by_phase[phase] = []
        phase_wps = [w for w in work_packages if w.phase == phase]

        if config.include_sprint_zero and phase == committed_phases[0]:
            sz = add_sprint("sprint_zero", phase)
            for wp in sorted(phase_wps, key=_wp_sort_key):
                if wp.package_type not in ("project_setup_architecture", "cicd_environments"):
                    continue
                if _fits(sz, wp.hours_by_role):
                    _place(sz, wp.wp_id, wp.hours_by_role)
                    placement[wp.wp_id] = sz.number

        phase_stories = sorted([s for s in expanded if s.phase == phase], key=_story_sort_key)
        pending = [s for s in phase_stories if s.story_key not in placement]
        while pending and len(delivery_by_phase[phase]) <= 100:
            deferred: list[SchedulerStory] = []
            opened_for_capacity = False
            placed_any = False
            for story in pending:
                if not all(dep in placement for dep in story.depends_on_keys):
                    deferred.append(story)
                    continue
                placed = False
                for sp in delivery_by_phase[phase]:
                    if _deps_done(story.depends_on_keys, placement, sp.number) and _fits(
                        sp, story.hours_by_role
                    ):
                        _place(sp, story.story_key, story.hours_by_role)
                        placement[story.story_key] = sp.number
                        placed = True
                        placed_any = True
                        break
                if placed:
                    continue
                if not opened_for_capacity:
                    slot = add_sprint("sprint", phase)
                    delivery_by_phase[phase].append(slot)
                    opened_for_capacity = True
                    if _fits(slot, story.hours_by_role):
                        _place(slot, story.story_key, story.hours_by_role)
                        placement[story.story_key] = slot.number
                        placed_any = True
                        continue
                deferred.append(story)
            pending = [s for s in deferred if s.story_key not in placement]
            if not placed_any:
                break

        early_wps = [
            w
            for w in phase_wps
            if w.package_type in ("third_party_integration_setup", "data_migration", "design")
            or w.package_type == "other"
        ]
        for wp in sorted(early_wps, key=_wp_sort_key):
            if wp.wp_id in placement:
                continue
            slots = delivery_by_phase[phase]
            placed_wp = False
            while not placed_wp:
                for sp in slots:
                    if _fits(sp, wp.hours_by_role):
                        _place(sp, wp.wp_id, wp.hours_by_role)
                        placement[wp.wp_id] = sp.number
                        placed_wp = True
                        break
                if placed_wp:
                    break
                if len(slots) > 100:
                    break
                slots.append(add_sprint("sprint", phase))

        if config.hardening_sprint_per_release:
            hard = add_sprint("hardening", phase)
            for wp in sorted(phase_wps, key=_wp_sort_key):
                if wp.wp_id in placement:
                    continue
                if wp.package_type not in (
                    "uat_support",
                    "deployment",
                    "documentation_training",
                    "stabilization",
                    "hypercare",
                ):
                    continue
                target = hard
                if not _fits(target, wp.hours_by_role):
                    target = add_sprint("hardening", phase)
                _place(target, wp.wp_id, wp.hours_by_role)
                placement[wp.wp_id] = target.number

    unplaced_stories = tuple(s.story_key for s in expanded if s.story_key not in placement)
    unplaced_packages = tuple(w.wp_id for w in work_packages if w.wp_id and w.wp_id not in placement)

    totals: dict[str, float] = {}
    for s in expanded:
        for role, h in s.hours_by_role.items():
            totals[role] = round(totals.get(role, 0.0) + h, 4)
    for wp in work_packages:
        if wp.wp_id not in placement:
            continue
        for role, h in wp.hours_by_role.items():
            totals[role] = round(totals.get(role, 0.0) + h, 4)

    return ScheduleResult(
        sprints=tuple(sprints),
        placement=placement,
        total_hours_by_role=totals,
        unplaced_packages=unplaced_packages,
        unplaced_stories=unplaced_stories,
    )


def story_points_from_hours(
    total_hours: float,
    thresholds: tuple[tuple[float, int], ...] = (
        (4, 1),
        (8, 2),
        (16, 3),
        (24, 5),
        (40, 8),
        (10_000, 13),
    ),
) -> int:
    for limit, points in thresholds:
        if total_hours <= limit:
            return points
    return 13

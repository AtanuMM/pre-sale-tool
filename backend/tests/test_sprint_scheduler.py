from __future__ import annotations

import pytest

from app.steps.sprint_scheduler import (
    SchedulerConfig,
    SchedulerRole,
    SchedulerStory,
    schedule_stories_and_packages,
    role_capacity_per_sprint,
)


def _roles() -> list[SchedulerRole]:
    return [
        SchedulerRole("Developer", 2, 40, 100),
        SchedulerRole("QA", 1, 40, 100),
    ]


def test_capacity_formula_fixture() -> None:
    config = SchedulerConfig(2, 10, False, False)
    dev = _roles()[0]
    qa = _roles()[1]
    assert role_capacity_per_sprint(dev, config, 0) == pytest.approx(144.0)
    assert role_capacity_per_sprint(qa, config, 0) == pytest.approx(72.0)


def test_hand_checked_abc_scheduling() -> None:
    config = SchedulerConfig(
        sprint_length_weeks=2,
        ceremony_overhead_pct=10,
        include_sprint_zero=False,
        hardening_sprint_per_release=False,
    )
    stories = [
        SchedulerStory(
            "A",
            "F-A",
            "mvp",
            "must",
            False,
            0,
            0,
            False,
            frozenset(),
            {"Developer": 100, "QA": 30},
        ),
        SchedulerStory(
            "B",
            "F-B",
            "mvp",
            "must",
            False,
            1,
            0,
            False,
            frozenset(),
            {"Developer": 60, "QA": 30},
        ),
        SchedulerStory(
            "C",
            "F-C",
            "mvp",
            "must",
            False,
            2,
            0,
            False,
            frozenset({"A"}),
            {"Developer": 50, "QA": 20},
        ),
    ]
    result = schedule_stories_and_packages(
        roles=_roles(),
        stories=stories,
        work_packages=[],
        committed_phases=["mvp"],
        config=config,
    )
    delivery = [s for s in result.sprints if s.sprint_type == "sprint"]
    assert len(delivery) == 2
    assert result.placement["A"] == delivery[0].number
    assert result.placement["B"] == delivery[1].number
    assert result.placement["C"] == delivery[1].number
    assert delivery[0].planned_by_role["Developer"] == pytest.approx(100)
    assert delivery[1].planned_by_role["Developer"] == pytest.approx(110)
    assert result.total_hours_by_role["Developer"] == pytest.approx(210)
    assert result.total_hours_by_role["QA"] == pytest.approx(80)


def test_dependent_waits_for_split_story_even_if_feature_id_sorts_first() -> None:
    config = SchedulerConfig(
        sprint_length_weeks=2,
        ceremony_overhead_pct=10,
        include_sprint_zero=False,
        hardening_sprint_per_release=False,
    )
    stories = [
        SchedulerStory(
            "US-0010",
            "F-010",
            "mvp",
            "must",
            False,
            0,
            0,
            False,
            frozenset(),
            {"Developer": 20, "QA": 200},
        ),
        SchedulerStory(
            "US-0011",
            "F-001",
            "mvp",
            "must",
            False,
            0,
            0,
            False,
            frozenset({"US-0010"}),
            {"Developer": 20, "QA": 20},
        ),
    ]
    result = schedule_stories_and_packages(
        roles=_roles(),
        stories=stories,
        work_packages=[],
        committed_phases=["mvp"],
        config=config,
    )
    assert "US-0010" in result.placement
    assert "US-0011" in result.placement
    assert result.placement["US-0011"] > result.placement["US-0010"]
    assert result.unplaced_stories == ()

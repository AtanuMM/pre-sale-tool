import pytest

from app.services.step_state import (
    DerivedStepStatus,
    VersionSnapshot,
    can_generate,
    derive_step_status,
)


def v(no: int, status: str) -> VersionSnapshot:
    return VersionSnapshot(version_no=no, status=status)


@pytest.mark.parametrize(
    ("step_key", "project_status", "versions_by_step", "expected", "failed_flag"),
    [
        ("scope_analysis", "active", {"scope_analysis": [v(1, "queued")]}, DerivedStepStatus.GENERATING, False),
        (
            "scope_analysis",
            "active",
            {"scope_analysis": [v(1, "in_review")]},
            DerivedStepStatus.IN_REVIEW,
            False,
        ),
        (
            "scope_analysis",
            "active",
            {"scope_analysis": [v(1, "changes_requested")]},
            DerivedStepStatus.IN_REVIEW,
            False,
        ),
        ("scope_analysis", "active", {"scope_analysis": [v(1, "stale")]}, DerivedStepStatus.STALE, False),
        (
            "scope_analysis",
            "active",
            {"scope_analysis": [v(1, "approved")]},
            DerivedStepStatus.APPROVED,
            False,
        ),
        ("scope_analysis", "active", {"scope_analysis": [v(1, "failed")]}, DerivedStepStatus.READY, True),
        (
            "scope_analysis",
            "active",
            {"scope_analysis": [v(1, "in_review"), v(2, "failed")]},
            DerivedStepStatus.IN_REVIEW,
            True,
        ),
        ("scope_analysis", "active", {}, DerivedStepStatus.READY, False),
        ("scope_analysis", "archived", {}, DerivedStepStatus.LOCKED, False),
        (
            "scope_analysis",
            "archived",
            {"scope_analysis": [v(1, "approved")]},
            DerivedStepStatus.APPROVED,
            False,
        ),
        ("gap_analysis", "active", {}, DerivedStepStatus.LOCKED, False),
        (
            "gap_analysis",
            "active",
            {"scope_analysis": [v(1, "approved")]},
            DerivedStepStatus.READY,
            False,
        ),
        (
            "gap_analysis",
            "active",
            {"scope_analysis": [v(1, "approved")], "gap_analysis": [v(1, "generating")]},
            DerivedStepStatus.GENERATING,
            False,
        ),
    ],
)
def test_derive_step_status_table(
    step_key, project_status, versions_by_step, expected, failed_flag
) -> None:
    result = derive_step_status(step_key, versions_by_step, project_status)
    assert result.status == expected
    assert result.has_failed_attempt is failed_flag


@pytest.mark.parametrize(
    ("step_key", "project_status", "versions_by_step", "expected"),
    [
        (
            "scope_analysis",
            "active",
            {"scope_analysis": [v(1, "stale")]},
            True,
        ),
        (
            "gap_analysis",
            "active",
            {
                "scope_analysis": [v(1, "approved")],
                "gap_analysis": [v(1, "stale")],
            },
            True,
        ),
        (
            "gap_analysis",
            "active",
            {
                "scope_analysis": [v(1, "in_review")],
                "gap_analysis": [v(1, "stale")],
            },
            False,
        ),
        (
            "scope_analysis",
            "archived",
            {"scope_analysis": [v(1, "stale")]},
            False,
        ),
        (
            "scope_analysis",
            "active",
            {"scope_analysis": [v(1, "generating")]},
            False,
        ),
        ("gap_analysis", "active", {}, False),
        (
            "gap_analysis",
            "active",
            {"scope_analysis": [v(1, "approved")]},
            True,
        ),
        ("estimate", "active", {"scope_analysis": [v(1, "approved")]}, False),
    ],
)
def test_can_generate_table(step_key, project_status, versions_by_step, expected) -> None:
    assert can_generate(step_key, versions_by_step, project_status) is expected

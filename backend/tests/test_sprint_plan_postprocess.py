from __future__ import annotations

from app.steps.postprocess import PostprocessContext
from app.steps.postprocess.sprint_plan import postprocess_sprint_plan
from app.steps.schemas.sprint_plan import (
    SprintPlanAssembled,
    SprintPlanModuleStoriesOutput,
    SprintPlanPasses,
    SprintPlanStored,
    StoryDraftItem,
)


def _estimate_content() -> dict:
    return {
        "schema_version": 2,
        "feature_estimates": [{"feature_id": "F-001", "phase": "mvp", "title": "Login"}],
        "work_packages": [],
        "computed": {
            "feature_rows": [
                {
                    "id": "F-001",
                    "per_role": {
                        "Developer": {"recommended": 100},
                        "QA": {"recommended": 30},
                    },
                }
            ],
            "phase_rows": [{"phase": "mvp", "weeks_planned": 4}],
        },
    }


def test_postprocess_schedules_stories() -> None:
    draft = SprintPlanStored(
        passes=SprintPlanPasses(
            module_stories={
                "Auth": SprintPlanModuleStoriesOutput(
                    module="Auth",
                    stories=[
                        StoryDraftItem(
                            feature_id="F-001",
                            title="Login story",
                            story_statement="As a user I want login so that I can access",
                            acceptance_criteria=["Given valid credentials", "When submitting", "Then access"],
                            share_percent=60,
                        )
                    ],
                )
            }
        ),
        assembled=SprintPlanAssembled(),
    )
    ctx = PostprocessContext(
        feature_ids=("F-001",),
        feature_depends={"F-001": ()},
        feature_gap_refs={"F-001": ()},
        gap_severities={},
        feature_risk_domains={"F-001": "none"},
        estimate_content=_estimate_content(),
        estimate_user_inputs={
            "phases": ["mvp"],
            "team": [
                {
                    "role": "Developer",
                    "headcount": 2,
                    "hours_per_week": 40,
                    "utilisation": 100,
                    "mode": "estimated",
                    "discipline": "development",
                },
                {
                    "role": "QA",
                    "headcount": 1,
                    "hours_per_week": 40,
                    "utilisation": 100,
                    "mode": "estimated",
                    "discipline": "qa",
                },
            ],
        },
        user_inputs={
            "sprint_length_weeks": 2,
            "ceremony_overhead_pct": 10,
            "include_sprint_zero": "no",
            "hardening_sprint_per_release": "no",
        },
        project_id="00000000-0000-0000-0000-000000000099",
        version_no=1,
        feature_list_content={
            "features": [{"id": "F-001", "phase": "mvp", "priority": "must", "primary_risk_domain": "none"}]
        },
    )
    stored, notes = postprocess_sprint_plan(draft, ctx)
    assert len(stored.stories) == 1
    assert stored.stories[0].sprint_number is not None
    assert notes["stories"] == 1

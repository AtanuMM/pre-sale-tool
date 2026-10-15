from __future__ import annotations

from app.services.sprint_plan_generation import _merge_module_stories
from app.steps.schemas.sprint_plan import (
    SprintPlanModuleStoriesBatchOutput,
    SprintPlanModuleStoriesOutput,
    StoryDraftItem,
)


def _story(n: int) -> StoryDraftItem:
    return StoryDraftItem(
        feature_id=f"F-{n:03d}",
        title=f"Story {n}",
        story_statement="As a user I want x so that y",
        acceptance_criteria=["Given a", "When b", "Then c"],
        share_percent=100,
    )


def test_merge_module_stories_across_batches_exceeds_ten() -> None:
    modules: dict[str, SprintPlanModuleStoriesOutput] = {}
    _merge_module_stories(
        modules,
        "Mobile",
        SprintPlanModuleStoriesBatchOutput(module="Mobile", stories=[_story(i) for i in range(8)]),
    )
    _merge_module_stories(
        modules,
        "Mobile",
        SprintPlanModuleStoriesBatchOutput(module="Mobile", stories=[_story(i) for i in range(8, 14)]),
    )
    assert len(modules["Mobile"].stories) == 14

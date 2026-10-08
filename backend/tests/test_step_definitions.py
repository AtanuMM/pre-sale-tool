from app.steps.definitions import (
    get_step,
    next_step,
    ordered_steps,
    previous_step,
)


def test_eight_steps_in_order() -> None:
    steps = ordered_steps()
    assert len(steps) == 8
    assert [s.order for s in steps] == list(range(1, 9))
    assert steps[0].key == "scope_analysis"
    assert steps[-1].key == "frs"


def test_linear_chain_through_sprint_plan_before_frs() -> None:
    assert get_step("frs").depends_on == "sprint_plan"
    assert previous_step("frs").key == "sprint_plan"
    assert next_step("sprint_plan").key == "frs"
    assert get_step("scope_analysis").depends_on is None


def test_scope_and_gap_implemented() -> None:
    implemented = [s.key for s in ordered_steps() if s.implemented]
    assert implemented == ["scope_analysis", "gap_analysis"]

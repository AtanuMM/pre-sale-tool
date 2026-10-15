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


def test_scope_gap_feature_list_estimate_sow_and_srs_implemented() -> None:
    implemented = [s.key for s in ordered_steps() if s.implemented]
    assert implemented == [
        "scope_analysis",
        "gap_analysis",
        "feature_list",
        "estimate",
        "sow",
        "srs",
        "sprint_plan",
    ]
    feature = get_step("feature_list")
    assert feature.context_steps == ("scope_analysis", "gap_analysis")
    assert feature.input_fields[0].key == "team_notes"
    assert feature.prompt_version == "v2"
    assert feature.max_output_tokens == 65_536
    gap = get_step("gap_analysis")
    assert gap.prompt_version == "v2"
    assert gap.max_output_tokens == 65_536
    assert gap.postprocess is not None
    estimate = get_step("estimate")
    assert estimate.context_steps == ("scope_analysis", "gap_analysis", "feature_list")
    assert estimate.export_formats == ("docx", "xlsx", "csv")
    assert [field.key for field in estimate.input_fields][:1] == ["team"]
    assert estimate.prompt_version == "v2"
    assert "contingency_pct" not in [field.key for field in estimate.input_fields]
    assert "discipline" in [c.key for c in estimate.input_fields[0].columns]
    sow = get_step("sow")
    assert sow.implemented is True
    assert sow.supports_reassemble is True
    assert sow.export_formats == ("docx",)
    assert sow.depends_on == "estimate"
    assert "client_legal_name" in [f.key for f in sow.input_fields]
    srs = get_step("srs")
    assert srs.implemented is True
    assert srs.export_formats == ("docx", "xlsx", "csv")
    assert srs.depends_on == "sow"
    assert "detail_level" in [f.key for f in srs.input_fields]
    sprint = get_step("sprint_plan")
    assert sprint.implemented is True
    assert sprint.depends_on == "srs"
    assert sprint.export_formats == ("docx", "xlsx", "csv")
    assert sprint.supports_reassemble is True
    assert "sprint_length_weeks" in [f.key for f in sprint.input_fields]

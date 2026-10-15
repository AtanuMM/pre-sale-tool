from app.steps.postprocess import PostprocessContext, PostprocessError
from app.steps.postprocess.estimate import (
    coverage_gaps,
    merge_repair,
    postprocess_estimate,
)
from app.steps.schemas.estimate import EstimateOutput, EstimateRepairOutput


def _ctx(**overrides: object) -> PostprocessContext:
    base = {
        "feature_ids": ("F-001", "F-002"),
        "feature_titles": {"F-001": "Sign in", "F-002": "Order list"},
        "feature_priorities": {"F-001": "must", "F-002": "should"},
        "feature_depends": {"F-001": (), "F-002": ("F-001",)},
        "high_medium_gap_refs": ("G-1",),
        "selected_phases": ("mvp", "phase_1", "future_scope"),
        "estimated_role_names": ("Developer",),
        "user_inputs": {
            "team": [
                {
                    "role": "Developer",
                    "mode": "estimated",
                    "headcount": 2,
                    "hours_per_week": 40,
                    "utilisation_pct": 100,
                    "ai_gain_pct": 20,
                }
            ],
            "phases": ["mvp", "phase_1", "future_scope"],
            "contingency_pct": 10,
        },
        "max_work_packages": 40,
        "max_effort_lines": 1800,
        "max_assumptions": 40,
        "max_components": 10,
    }
    base.update(overrides)
    return PostprocessContext(**base)  # type: ignore[arg-type]


def _output(**overrides: object) -> EstimateOutput:
    data = {
        "summary": "s",
        "approach": "a",
        "components": [{"name": "Backend API", "description": "API"}],
        "phases": [
            {"key": "mvp", "goal": "core", "scope_rationale": "must"},
            {"key": "phase_1", "goal": "next", "scope_rationale": "should"},
        ],
        "assumptions_and_solutions": [
            {
                "gap_ref": "G-1",
                "topic": "IdP",
                "solution": "Azure AD",
                "rationale": "Common for the client",
                "effort_impact": "medium",
                "alternatives": "Okta",
                "confirm_with_client": "Confirm IdP",
            }
        ],
        "exclusions": ["Hosting fees"],
        "feature_estimates": [
            {
                "feature_id": "F-001",
                "phase": "mvp",
                "component": "Backend API",
                "confidence": "high",
                "ai_leverage": "medium",
                "complexity": "M",
                "basis": "auth",
            },
            {
                "feature_id": "F-002",
                "phase": "phase_1",
                "component": "Backend API",
                "confidence": "high",
                "ai_leverage": "medium",
                "complexity": "S",
                "basis": "list",
            },
        ],
        "work_packages": [],
        "effort_lines": [
            {"item_id": "F-001", "role": "Developer", "base_hours": 100},
            {"item_id": "F-002", "role": "Developer", "base_hours": 20},
        ],
    }
    data.update(overrides)
    return EstimateOutput.model_validate(data)


def test_unknown_and_duplicate_features_dropped() -> None:
    output = _output(
        feature_estimates=[
            {
                "feature_id": "F-001",
                "phase": "mvp",
                "component": "Backend API",
                "confidence": "high",
                "ai_leverage": "medium",
                "complexity": "M",
                "basis": "a",
            },
            {
                "feature_id": "F-001",
                "phase": "mvp",
                "component": "Backend API",
                "confidence": "high",
                "ai_leverage": "medium",
                "complexity": "M",
                "basis": "dup",
            },
            {
                "feature_id": "F-999",
                "phase": "mvp",
                "component": "Backend API",
                "confidence": "high",
                "ai_leverage": "medium",
                "complexity": "M",
                "basis": "unknown",
            },
        ]
    )
    stored, notes = postprocess_estimate(output, _ctx())
    assert notes["features_deduplicated"] == 1
    assert notes["features_unknown_dropped"] == 1
    assert notes["features_not_estimated"] == 1
    ids = [f.feature_id for f in stored.feature_estimates]
    assert ids.count("F-001") == 1
    missing = next(f for f in stored.feature_estimates if f.feature_id == "F-002")
    assert missing.not_estimated is True


def test_phase_remap_and_dep_pull_forward() -> None:
    output = _output(
        feature_estimates=[
            {
                "feature_id": "F-001",
                "phase": "phase_3",
                "component": "Backend API",
                "confidence": "high",
                "ai_leverage": "medium",
                "complexity": "M",
                "basis": "a",
            },
            {
                "feature_id": "F-002",
                "phase": "mvp",
                "component": "Backend API",
                "confidence": "high",
                "ai_leverage": "medium",
                "complexity": "S",
                "basis": "b",
            },
        ]
    )
    stored, notes = postprocess_estimate(output, _ctx())
    assert notes["phases_remapped"] >= 1
    by_id = {f.feature_id: f for f in stored.feature_estimates}
    # F-002 in mvp depends on F-001; F-001 remapped from phase_3 to future_scope
    # then pulled forward to mvp
    assert by_id["F-002"].phase == "mvp"
    assert by_id["F-001"].phase == "mvp"
    assert notes["deps_pulled_forward"] >= 1


def test_unknown_role_dropped_and_component_other() -> None:
    output = _output(
        effort_lines=[
            {"item_id": "F-001", "role": "Wizard", "base_hours": 10},
            {"item_id": "F-001", "role": "Developer", "base_hours": 8},
            {"item_id": "F-002", "role": "Developer", "base_hours": 4},
        ],
        feature_estimates=[
            {
                "feature_id": "F-001",
                "phase": "mvp",
                "component": "Mystery Box",
                "confidence": "high",
                "ai_leverage": "medium",
                "complexity": "M",
                "basis": "a",
            },
            {
                "feature_id": "F-002",
                "phase": "phase_1",
                "component": "backend api",
                "confidence": "high",
                "ai_leverage": "medium",
                "complexity": "S",
                "basis": "b",
            },
        ],
    )
    stored, notes = postprocess_estimate(output, _ctx())
    assert notes["roles_dropped"] >= 1
    assert notes["components_unmapped"] >= 1
    names = {c.name for c in stored.components}
    assert "Other" in names
    feat = next(f for f in stored.feature_estimates if f.feature_id == "F-002")
    assert feat.component == "Backend API"


def test_zero_effort_lines_fails() -> None:
    output = _output(effort_lines=[])
    try:
        postprocess_estimate(output, _ctx())
        raise AssertionError("expected fail")
    except PostprocessError:
        pass


def test_coverage_gaps_and_merge_repair() -> None:
    output = _output(
        feature_estimates=[
            {
                "feature_id": "F-001",
                "phase": "mvp",
                "component": "Backend API",
                "confidence": "high",
                "ai_leverage": "medium",
                "complexity": "M",
                "basis": "a",
            }
        ],
        assumptions_and_solutions=[],
        effort_lines=[{"item_id": "F-001", "role": "Developer", "base_hours": 10}],
    )
    missing_f, missing_g = coverage_gaps(output, _ctx())
    assert missing_f == ["F-002"]
    assert missing_g == ["G-1"]
    repair = EstimateRepairOutput.model_validate(
        {
            "feature_estimates": [
                {
                    "feature_id": "F-002",
                    "phase": "phase_1",
                    "component": "Backend API",
                    "confidence": "medium",
                    "ai_leverage": "low",
                    "complexity": "S",
                    "basis": "repaired",
                }
            ],
            "assumptions_and_solutions": [
                {
                    "gap_ref": "G-1",
                    "topic": "IdP",
                    "solution": "Azure AD",
                    "rationale": "Practical",
                    "effort_impact": "low",
                    "alternatives": "Okta",
                    "confirm_with_client": "Confirm",
                }
            ],
            "work_packages": [],
            "effort_lines": [{"item_id": "F-002", "role": "Developer", "base_hours": 12}],
        }
    )
    merged = merge_repair(output, repair)
    assert {f.feature_id for f in merged.feature_estimates} == {"F-001", "F-002"}
    assert merged.assumptions_and_solutions[0].gap_ref == "G-1"


def test_cycle_safe_pull_forward() -> None:
    ctx = _ctx(feature_depends={"F-001": ("F-002",), "F-002": ("F-001",)})
    output = _output()
    stored, notes = postprocess_estimate(output, ctx)
    assert "dep_cycles_skipped" in notes
    assert len(stored.feature_estimates) == 2

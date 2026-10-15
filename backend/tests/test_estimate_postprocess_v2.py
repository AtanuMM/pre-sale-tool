from app.steps.postprocess import PostprocessContext
from app.steps.postprocess.estimate_v2 import postprocess_estimate_v2
from app.steps.schemas.estimate_v2 import EstimateV2Merged, EstimateV2Stored

_TEAM = {
    "team": [
        {
            "role": "Developer",
            "discipline": "other",
            "mode": "estimated",
            "headcount": 2,
            "hours_per_week": 40,
            "utilisation_pct": 100,
            "ai_gain_pct": 0,
        },
        {
            "role": "QA Engineer",
            "discipline": "other",
            "mode": "estimated",
            "headcount": 1,
            "hours_per_week": 40,
            "utilisation_pct": 100,
            "ai_gain_pct": 0,
        },
    ],
    "phases": ["mvp", "phase_1", "phase_2", "phase_3", "future_scope"],
    "domain_experience": "some_experience",
}


def _ctx(**overrides: object) -> PostprocessContext:
    base: dict[str, object] = {
        "feature_ids": ("F-001", "F-002"),
        "feature_titles": {"F-001": "Sign in", "F-002": "Order list"},
        "feature_priorities": {"F-001": "must", "F-002": "should"},
        "feature_depends": {"F-001": (), "F-002": ("F-001",)},
        "high_medium_gap_refs": (),
        "selected_phases": ("mvp", "phase_1", "phase_2", "phase_3", "future_scope"),
        "estimated_role_names": ("Developer", "QA Engineer"),
        "user_inputs": _TEAM,
        "max_work_packages": 40,
        "max_effort_lines": 1800,
        "max_assumptions": 40,
        "max_components": 10,
        "feature_risk_domains": {"F-001": "none", "F-002": "none"},
        "feature_origins": {"F-001": "stated", "F-002": "stated"},
    }
    base.update(overrides)
    return PostprocessContext(**base)  # type: ignore[arg-type]


def _merged(**overrides: object) -> EstimateV2Merged:
    data: dict[str, object] = {
        "summary": "Dummy estimate",
        "approach": "API plus a small web app.",
        "components": [{"name": "Backend API", "description": "Services", "screens": 2}],
        "phases": [{"key": "mvp", "goal": "core", "scope_rationale": "must"}],
        "assumptions_and_solutions": [],
        "exclusions": [],
        "feature_estimates": [
            {
                "feature_id": "F-001",
                "phase": "mvp",
                "component": "Backend API",
                "confidence": "medium",
                "confidence_reason": "Typical auth work.",
                "ai_leverage": "none",
                "complexity": "M",
                "basis": "source",
                "primary_risk_domain": "none",
            }
        ],
        "added_items": [],
        "work_packages": [
            {
                "id": "W-1",
                "package_type": "hypercare",
                "title": "Hypercare",
                "description": "Support window",
                "phase": "mvp",
                "component": "Backend API",
                "confidence": "medium",
                "ai_leverage": "none",
                "lead_time_weeks": 0,
            }
        ],
        "effort_lines": [],
    }
    data.update(overrides)
    return EstimateV2Merged.model_validate(data)


def test_empty_effort_lines_recovers_default_packages() -> None:
    stored, notes = postprocess_estimate_v2(_merged(), _ctx())
    assert isinstance(stored, EstimateV2Stored)
    assert notes["effort_lines_empty"] == 1
    assert notes["default_packages_added"] >= 1
    totals = stored.computed["totals"]
    assert totals["hours_without_ai"] > 0
    assert any(pkg.default_allowance for pkg in stored.work_packages)


def test_fuzzy_role_and_padded_feature_id_keep_hours() -> None:
    stored, notes = postprocess_estimate_v2(
        _merged(
            effort_lines=[
                {
                    "item_id": "F-1",
                    "role": "QA",
                    "task": "qa_testing",
                    "best_hours": 8,
                    "likely_hours": 10,
                    "worst_hours": 16,
                }
            ]
        ),
        _ctx(),
    )
    assert notes["roles_fuzzy_matched"] == 1
    assert notes["effort_lines_empty"] == 0
    assert stored.effort_lines[0].item_id == "F-001"
    assert stored.effort_lines[0].role == "QA Engineer"
    assert stored.computed["totals"]["hours_without_ai"] >= 10

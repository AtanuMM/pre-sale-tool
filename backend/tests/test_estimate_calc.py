from app.steps.estimate_calc import (
    ai_adjusted_hours,
    buffered_hours,
    ceil_to_half,
    compute_estimate,
    weekly_capacity,
)
from app.steps.schemas.estimate import EstimateStored


def _stored(*, leverage: str = "medium", confidence: str = "high") -> EstimateStored:
    return EstimateStored.model_validate(
        {
            "summary": "s",
            "approach": "a",
            "components": [{"name": "Backend API", "description": "API"}],
            "phases": [
                {
                    "key": "mvp",
                    "goal": "Ship core",
                    "scope_rationale": "Must items",
                }
            ],
            "assumptions_and_solutions": [],
            "exclusions": [],
            "feature_estimates": [
                {
                    "feature_id": "F-001",
                    "title": "Sign in",
                    "phase": "mvp",
                    "component": "Backend API",
                    "confidence": confidence,
                    "ai_leverage": leverage,
                    "complexity": "M",
                    "basis": "fixture",
                    "not_estimated": False,
                }
            ],
            "work_packages": [],
            "effort_lines": [
                {"item_id": "F-001", "role": "Developer", "base_hours": 100},
            ],
            "computed": {},
        }
    )


def _team(**overrides: object) -> dict:
    row = {
        "role": "Developer",
        "mode": "estimated",
        "headcount": 2,
        "hours_per_week": 40,
        "utilisation_pct": 100,
        "ai_gain_pct": 20,
    }
    row.update(overrides)
    return {
        "team": [row],
        "phases": ["mvp"],
        "contingency_pct": 10,
    }


def test_hand_checked_medium_leverage_high_confidence() -> None:
    ai = ai_adjusted_hours(100, 20, "medium")
    assert ai == 88.0
    buf = buffered_hours(ai, "high", 10)
    assert buf == 96.8
    cap = weekly_capacity(2, 40, 100)
    assert cap == 80.0
    exact = buf / cap
    assert round(exact, 2) == 1.21
    assert ceil_to_half(exact) == 1.5

    computed = compute_estimate(_stored(), _team())
    totals = computed["totals"]
    assert totals["hours_without_ai"] == 100.0
    assert totals["hours_with_ai"] == 88.0
    assert computed["phase_weeks_exact"]["mvp"] == 1.21
    assert computed["phase_weeks_planned"]["mvp"] == 1.5
    item = computed["feature_rows"][0]
    assert item["per_role"]["Developer"]["buffered"] == 96.8


def test_hand_checked_high_and_low_leverage() -> None:
    assert ai_adjusted_hours(100, 20, "high") == 80.0
    assert ai_adjusted_hours(100, 20, "low") == 95.0


def test_low_confidence_uplift() -> None:
    ai = ai_adjusted_hours(100, 20, "medium")
    buf = buffered_hours(ai, "low", 10)
    assert round(buf, 2) == round(88.0 * 1.35, 2)


def test_percent_of_delivery_and_duration_based() -> None:
    stored = _stored()
    inputs = {
        "team": [
            {
                "role": "Developer",
                "mode": "estimated",
                "headcount": 2,
                "hours_per_week": 40,
                "utilisation_pct": 100,
                "ai_gain_pct": 20,
            },
            {
                "role": "DevOps Engineer",
                "mode": "percent_of_delivery",
                "headcount": 1,
                "hours_per_week": 40,
                "utilisation_pct": 100,
                "ai_gain_pct": 0,
                "overhead_pct": 10,
            },
            {
                "role": "Project Manager",
                "mode": "duration_based",
                "headcount": 1,
                "hours_per_week": 40,
                "utilisation_pct": 100,
                "ai_gain_pct": 0,
            },
        ],
        "phases": ["mvp"],
        "contingency_pct": 10,
    }
    computed = compute_estimate(stored, inputs)
    detail = computed["phase_detail"][0]
    # 10% of 96.8 buffered estimated
    assert detail["overhead_hours"]["DevOps Engineer"] == 9.68
    # capacity 40 * planned 1.5
    assert detail["overhead_hours"]["Project Manager"] == 60.0

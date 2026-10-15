"""Estimate v2 formula fixtures (line-level a–c; project cap d; weeks; could)."""

from __future__ import annotations

from app.steps.estimate_calc import ceil_to_half
from app.steps.estimate_calc_v2 import (
    METHOD_NOTE_V2,
    ai_adjusted_range,
    apply_confidence_guardrails,
    apply_leverage_guardrails,
    buffered_likely,
    compute_estimate_v2,
    default_package_hours,
    line_ai_reduction,
    parse_team_v2,
    sanitize_hours,
)
from app.steps.schemas.estimate_v2 import (
    ComponentItemV2,
    EffortLineV2,
    EstimateV2Stored,
    PhaseItemV2,
    StoredFeatureEstimateV2,
    StoredWorkPackageV2,
)

TEAM = {
    "team": [
        {
            "role": "Developer",
            "discipline": "development",
            "mode": "estimated",
            "headcount": 2,
            "hours_per_week": 40,
            "utilisation_pct": 100,
            "ai_gain_pct": 50,
        }
    ],
    "phases": ["mvp"],
    "domain_experience": "built_similar_before",
}


def test_sanitize_hours_order_and_cap() -> None:
    best, likely, worst = sanitize_hours(12.2, 10, 50)
    assert best == 10
    assert likely == 10
    assert worst == 40  # 4x likely


def test_line_a_high_leverage_high_confidence() -> None:
    reduction = line_ai_reduction(50, "high", discipline="development", risk_domain="none")
    assert reduction == 0.30
    _b, ai, _w = ai_adjusted_range(100, 100, 100, reduction)
    assert ai == 70.0
    rec = buffered_likely(ai, "high")
    assert rec == 80.5
    weeks = rec / 80.0
    assert abs(weeks - 1.00625) < 1e-9
    assert ceil_to_half(weeks) == 1.5


def test_line_b_medium_leverage() -> None:
    reduction = line_ai_reduction(50, "medium", discipline="development", risk_domain="none")
    assert reduction == 0.15
    _b, ai, _w = ai_adjusted_range(100, 100, 100, reduction)
    assert ai == 85.0
    rec = buffered_likely(ai, "high")
    assert rec == 97.75
    assert ceil_to_half(rec / 80.0) == 1.5


def test_line_c_payments_forces_none_and_medium() -> None:
    conf, codes = apply_confidence_guardrails(
        "high",
        domain_exp="built_similar_before",
        gap_severity=None,
        risk_domain="payments",
    )
    assert conf == "medium"
    assert "risk_domain" in codes
    lev = apply_leverage_guardrails("high", risk_domain="payments", discipline="development")
    assert lev == "none"
    reduction = line_ai_reduction(50, lev, discipline="development", risk_domain="payments")
    assert reduction == 0.0
    rec = buffered_likely(100.0, conf)
    assert rec == 125.0
    assert ceil_to_half(125.0 / 80.0) == 2.0


def test_experience_caps_high_confidence() -> None:
    conf, codes = apply_confidence_guardrails(
        "high",
        domain_exp="some_experience",
        gap_severity=None,
        risk_domain="none",
    )
    assert conf == "medium"
    assert "experience_cap" in codes


def test_non_dev_ai_is_zero() -> None:
    assert line_ai_reduction(50, "high", discipline="qa", risk_domain="none") == 0.0


def _stored(likely: float, leverage: str = "high", confidence: str = "high", n: int = 1) -> EstimateV2Stored:
    features = []
    lines = []
    for i in range(n):
        fid = f"F-{i + 1:03d}"
        features.append(
            StoredFeatureEstimateV2(
                feature_id=fid,
                phase="mvp",
                component="API",
                confidence=confidence,  # type: ignore[arg-type]
                confidence_reason="specified",
                ai_leverage=leverage,  # type: ignore[arg-type]
                complexity="M",
                basis="source",
                title=fid,
                not_estimated=False,
                priority="must",
                origin="stated",
                confidence_raw=confidence,  # type: ignore[arg-type]
                ai_leverage_raw=leverage,  # type: ignore[arg-type]
            )
        )
        lines.append(
            EffortLineV2(
                item_id=fid,
                role="Developer",
                task="backend_api",
                best_hours=likely,
                likely_hours=likely,
                worst_hours=likely,
            )
        )
    packages = [
        StoredWorkPackageV2(
            id=f"W-{i}",
            package_type=ptype,  # type: ignore[arg-type]
            title=ptype,
            description="req",
            phase="mvp",
            component="API",
            confidence="medium",
            ai_leverage="none",
            default_allowance=False,
        )
        for i, ptype in enumerate(
            (
                "project_setup_architecture",
                "cicd_environments",
                "uat_support",
                "deployment",
                "documentation_training",
                "stabilization",
                "hypercare",
            ),
            start=1,
        )
    ]
    for pkg in packages:
        lines.append(
            EffortLineV2(
                item_id=pkg.id,
                role="Developer",
                task="other",
                best_hours=1,
                likely_hours=1,
                worst_hours=1,
            )
        )
    return EstimateV2Stored(
        schema_version=2,
        summary="s",
        approach="a",
        components=[ComponentItemV2(name="API", description="api", screens=1)],
        phases=[PhaseItemV2(key="mvp", goal="g", scope_rationale="r")],
        assumptions_and_solutions=[],
        exclusions=[],
        feature_estimates=features,
        work_packages=packages,
        effort_lines=lines,
    )


def test_project_ai_cap_scales_high_leverage() -> None:
    stored = _stored(100, leverage="high", n=10)
    stored = stored.model_copy(
        update={
            "work_packages": [],
            "effort_lines": [
                line for line in stored.effort_lines if line.item_id.startswith("F-")
            ],
        }
    )
    computed = compute_estimate_v2(stored, TEAM)
    factor = computed["totals"]["project_ai_cap_factor"]
    assert abs(factor - 0.8333) < 0.01
    assert abs(computed["totals"]["hours_with_ai"] - 750.0) < 0.5
    assert "no separate contingency" in METHOD_NOTE_V2.lower()


def test_could_excluded_from_committed() -> None:
    stored = _stored(40)
    feat = stored.feature_estimates[0].model_copy(update={"priority": "could"})
    stored = stored.model_copy(update={"feature_estimates": [feat]})
    computed = compute_estimate_v2(stored, TEAM)
    assert computed["totals"]["optional_likely"] >= 40
    assert computed["feature_rows"] == []
    assert computed["optional_rows"]


def test_hypercare_default_at_least_two_weeks_capacity() -> None:
    team = parse_team_v2(TEAM)
    hours = default_package_hours("hypercare", dev_ai_likely=100, delivery=team[0])
    # 2 * 80 = 160 vs 5% of 100 = 5
    assert hours == 160.0


def test_qa_ai_gain_parsed_as_zero() -> None:
    roles = parse_team_v2(
        {
            "team": [
                {
                    "role": "QA Engineer",
                    "discipline": "qa",
                    "mode": "estimated",
                    "headcount": 1,
                    "hours_per_week": 40,
                    "utilisation_pct": 100,
                    "ai_gain_pct": 40,
                }
            ]
        }
    )
    assert roles[0].ai_gain_pct == 0.0

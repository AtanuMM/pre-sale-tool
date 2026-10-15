"""Recompute the latest estimate under team/formula scenarios. Numbers only; never print client text."""

from __future__ import annotations

import copy
from collections import Counter
from typing import Any

from sqlalchemy import select

from app.db import get_session_factory
from app.models.steps import StepVersion
from app.steps.estimate_calc import compute_estimate, parse_team
from app.steps.schemas.estimate import EstimateStored

SCENARIOS = (
    "stored_default",
    "ai_gain_0",
    "ai_gain_30_developers",
    "headcount_x2",
    "headcount_x0_5",
    "contingency_0",
    "contingency_15",
    "pm_duration_based",
    "pm_percent_of_delivery_12",
)


def _clone_inputs(raw: dict[str, Any]) -> dict[str, Any]:
    cloned = copy.deepcopy(raw)
    team = cloned.get("team")
    if not isinstance(team, list):
        cloned["team"] = []
    return cloned


def _scale_headcount(inputs: dict[str, Any], factor: float) -> None:
    team = inputs.get("team")
    if not isinstance(team, list):
        return
    for row in team:
        if isinstance(row, dict) and "headcount" in row:
            try:
                row["headcount"] = float(row["headcount"]) * factor
            except (TypeError, ValueError):
                continue


def _set_ai_gain(inputs: dict[str, Any], *, all_roles: float | None, developers: float | None) -> None:
    team = inputs.get("team")
    if not isinstance(team, list):
        return
    for row in team:
        if not isinstance(row, dict):
            continue
        if all_roles is not None:
            row["ai_gain_pct"] = all_roles
            continue
        role = str(row.get("role") or "").casefold()
        if developers is not None and "develop" in role:
            row["ai_gain_pct"] = developers


def _set_pm_mode(inputs: dict[str, Any], *, mode: str, overhead_pct: float | None) -> None:
    team = inputs.get("team")
    if not isinstance(team, list):
        return
    for row in team:
        if not isinstance(row, dict):
            continue
        role = str(row.get("role") or "").casefold()
        if "project manager" in role or role in {"pm", "management"}:
            row["mode"] = mode
            if overhead_pct is not None:
                row["overhead_pct"] = overhead_pct
            elif "overhead_pct" in row and mode != "percent_of_delivery":
                row.pop("overhead_pct", None)


def _apply_scenario(base: dict[str, Any], name: str) -> dict[str, Any]:
    inputs = _clone_inputs(base)
    if name == "ai_gain_0":
        _set_ai_gain(inputs, all_roles=0.0, developers=None)
    elif name == "ai_gain_30_developers":
        _set_ai_gain(inputs, all_roles=None, developers=30.0)
    elif name == "headcount_x2":
        _scale_headcount(inputs, 2.0)
    elif name == "headcount_x0_5":
        _scale_headcount(inputs, 0.5)
    elif name == "contingency_0":
        inputs["contingency_pct"] = 0
    elif name == "contingency_15":
        inputs["contingency_pct"] = 15
    elif name == "pm_duration_based":
        _set_pm_mode(inputs, mode="duration_based", overhead_pct=None)
    elif name == "pm_percent_of_delivery_12":
        _set_pm_mode(inputs, mode="percent_of_delivery", overhead_pct=12.0)
    return inputs


def _hist(values: list[str]) -> dict[str, int]:
    counts = Counter(values)
    return dict(sorted(counts.items()))


def _row(computed: dict[str, Any]) -> dict[str, float | None]:
    totals = computed.get("totals") if isinstance(computed.get("totals"), dict) else {}
    return {
        "base": totals.get("hours_without_ai"),
        "ai_adjusted": totals.get("hours_with_ai"),
        "buffered": totals.get("buffered_estimated_committed"),
        "overhead": totals.get("overhead_committed"),
        "weeks": totals.get("weeks"),
        "cost": totals.get("cost"),
        "saving_pct": totals.get("saving_pct"),
        "recommended": (
            (totals.get("buffered_estimated_committed") or 0)
            + (totals.get("overhead_committed") or 0)
        ),
    }


def _print_row(name: str, data: dict[str, float | None]) -> None:
    def fmt(value: float | None) -> str:
        if value is None:
            return "-"
        return f"{float(value):.2f}"

    print(
        f"{name:28s}  base={fmt(data['base']):>10}  ai={fmt(data['ai_adjusted']):>10}  "
        f"buf={fmt(data['buffered']):>10}  oh={fmt(data['overhead']):>10}  "
        f"rec={fmt(data['recommended']):>10}  weeks={fmt(data['weeks']):>8}  "
        f"cost={fmt(data['cost']):>10}  save%={fmt(data['saving_pct']):>7}"
    )


def _print_team(inputs: dict[str, Any]) -> None:
    for role in parse_team(inputs):
        print(
            f"  role_len={len(role.role)} mode={role.mode} hc={role.headcount:g} "
            f"hpw={role.hours_per_week:g} util={role.utilisation_pct:g} "
            f"ai={role.ai_gain_pct:g} oh={role.overhead_pct} rate={'y' if role.hourly_rate is not None else 'n'}"
        )


def main() -> int:
    factory = get_session_factory()
    with factory() as session:
        latest = session.scalar(
            select(StepVersion)
            .where(StepVersion.step_key == "estimate", StepVersion.content.is_not(None))
            .order_by(StepVersion.created_at.desc())
        )
        if latest is None or latest.content is None:
            print("NO_ESTIMATE_VERSION")
            return 1
        recent = session.scalars(
            select(StepVersion)
            .where(StepVersion.step_key == "estimate", StepVersion.content.is_not(None))
            .order_by(StepVersion.created_at.desc())
            .limit(8)
        ).all()

        print("latest_status", latest.status, "version_no", latest.version_no)
        print("prompt_version", latest.prompt_version, "tokens_out", latest.tokens_out)
        stored = EstimateStored.model_validate(latest.content)
        features = stored.feature_estimates
        packages = stored.work_packages
        lines = stored.effort_lines
        print("n_features", len(features), "n_work_packages", len(packages), "n_effort_lines", len(lines))
        if features:
            print("avg_lines_per_feature", round(len(lines) / max(1, len(features)), 2))
        print("confidence", _hist([f.confidence for f in features]))
        print("ai_leverage", _hist([f.ai_leverage for f in features]))
        print("complexity", _hist([f.complexity for f in features]))
        print("wp_confidence", _hist([p.confidence for p in packages]))
        print("wp_leverage", _hist([p.ai_leverage for p in packages]))
        lines_per_item = Counter(line.item_id for line in lines)
        print("median_lines_per_item", sorted(lines_per_item.values())[len(lines_per_item) // 2] if lines_per_item else 0)
        print("items_with_one_line", sum(1 for n in lines_per_item.values() if n == 1))

        raw_inputs = latest.inputs if isinstance(latest.inputs, dict) else {}
        user_inputs = raw_inputs.get("user_inputs")
        if not isinstance(user_inputs, dict):
            user_inputs = {}
        print("contingency_pct", user_inputs.get("contingency_pct"))
        print("n_phases", len(user_inputs.get("phases") or []))
        print("stored_team")
        _print_team(user_inputs)

        print("recent_versions")
        for row in recent:
            content = row.content if isinstance(row.content, dict) else {}
            computed = content.get("computed") if isinstance(content.get("computed"), dict) else {}
            totals = computed.get("totals") if isinstance(computed.get("totals"), dict) else {}
            print(
                f"  v{row.version_no} status={row.status} base={totals.get('hours_without_ai')} "
                f"ai={totals.get('hours_with_ai')} buf={totals.get('buffered_estimated_committed')} "
                f"oh={totals.get('overhead_committed')} weeks={totals.get('weeks')} "
                f"cost={totals.get('cost')}"
            )

        print("scenarios")
        baseline_row: dict[str, float | None] | None = None
        for name in SCENARIOS:
            computed = compute_estimate(stored, _apply_scenario(user_inputs, name))
            data = _row(computed)
            _print_row(name, data)
            if name == "stored_default":
                baseline_row = data

        if baseline_row:
            print("deltas_vs_stored_default (recommended)")
            for name in SCENARIOS:
                if name == "stored_default":
                    continue
                computed = compute_estimate(stored, _apply_scenario(user_inputs, name))
                data = _row(computed)
                rec0 = float(baseline_row["recommended"] or 0)
                rec1 = float(data["recommended"] or 0)
                weeks0 = float(baseline_row["weeks"] or 0)
                weeks1 = float(data["weeks"] or 0)
                ratio = (rec1 / rec0) if rec0 else 0.0
                print(
                    f"  {name:28s} rec_ratio={ratio:.3f}  rec_delta={rec1 - rec0:.2f}  "
                    f"weeks_delta={weeks1 - weeks0:.2f}  oh_delta="
                    f"{float(data['overhead'] or 0) - float(baseline_row['overhead'] or 0):.2f}"
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

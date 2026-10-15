"""Pure estimate calculations. No database access. Results live on content.computed."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from app.config import get_settings
from app.steps.schemas.estimate import PHASE_ORDER, EstimateStored

METHOD_NOTE = (
    "Base hours are the model's estimate for a competent mid-level engineer working "
    "without AI tools (implementation, self-testing, code review and bug fixing). "
    "Hours with AI = base × (1 − AI gain % × leverage factor). "
    "Buffered hours = hours with AI × (1 + risk uplift for confidence + contingency %). "
    "Calendar weeks for a phase are the maximum of (buffered hours / weekly capacity) "
    "across estimated roles, rounded up to the next 0.5 week. Phases are assumed to run "
    "sequentially; roles work in parallel within a phase. This is a duration sketch, not "
    "a schedule — the Sprint Plan step does real scheduling later. "
    "Percent-of-delivery roles take a percentage of estimated-role buffered hours in the "
    "phase. Duration-based roles take weekly capacity × planned phase weeks. "
    "Future scope is excluded from committed totals."
)


def round_to_half(value: float) -> float:
    return round(value * 2) / 2


def ceil_to_half(value: float) -> float:
    if value <= 0:
        return 0.0
    return math.ceil(value * 2) / 2


def _r2(value: float) -> float:
    return round(value + 1e-12, 2)


def leverage_factor(ai_leverage: str) -> float:
    settings = get_settings()
    mapping = {
        "high": settings.ESTIMATE_LEVERAGE_HIGH,
        "medium": settings.ESTIMATE_LEVERAGE_MEDIUM,
        "low": settings.ESTIMATE_LEVERAGE_LOW,
    }
    return mapping.get(ai_leverage, settings.ESTIMATE_LEVERAGE_MEDIUM)


def risk_uplift(confidence: str) -> float:
    settings = get_settings()
    mapping = {
        "high": settings.ESTIMATE_RISK_HIGH,
        "medium": settings.ESTIMATE_RISK_MEDIUM,
        "low": settings.ESTIMATE_RISK_LOW,
    }
    return mapping.get(confidence, settings.ESTIMATE_RISK_MEDIUM)


def clamp_base_hours(raw: float) -> float:
    rounded = round_to_half(raw)
    if rounded < 0:
        return 0.0
    if rounded > 400:
        return 400.0
    return rounded


def ai_adjusted_hours(base: float, ai_gain_pct: float, ai_leverage: str) -> float:
    factor = max(0.0, 1.0 - (ai_gain_pct / 100.0) * leverage_factor(ai_leverage))
    return _r2(base * factor)


def buffered_hours(ai_adj: float, confidence: str, contingency_pct: float) -> float:
    return _r2(ai_adj * (1.0 + risk_uplift(confidence) + contingency_pct / 100.0))


def weekly_capacity(headcount: float, hours_per_week: float, utilisation_pct: float) -> float:
    return headcount * hours_per_week * utilisation_pct / 100.0


@dataclass(frozen=True)
class TeamRole:
    role: str
    mode: str
    headcount: float
    hours_per_week: float
    utilisation_pct: float
    ai_gain_pct: float
    hourly_rate: float | None
    overhead_pct: float | None

    @property
    def capacity(self) -> float:
        return weekly_capacity(self.headcount, self.hours_per_week, self.utilisation_pct)


def parse_team(user_inputs: dict[str, Any]) -> list[TeamRole]:
    rows = user_inputs.get("team")
    if not isinstance(rows, list):
        return []
    out: list[TeamRole] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        role = str(row.get("role") or "").strip()
        mode = str(row.get("mode") or "").strip()
        if not role or mode not in ("estimated", "percent_of_delivery", "duration_based"):
            continue
        headcount = float(row.get("headcount") or 0)
        hours_per_week = float(row.get("hours_per_week") or 0)
        utilisation_pct = float(row.get("utilisation_pct") or 0)
        ai_gain_pct = float(row.get("ai_gain_pct") or 0)
        raw_rate = row.get("hourly_rate")
        hourly_rate = float(raw_rate) if isinstance(raw_rate, (int, float)) else None
        raw_oh = row.get("overhead_pct")
        overhead_pct = float(raw_oh) if isinstance(raw_oh, (int, float)) else None
        out.append(
            TeamRole(
                role=role,
                mode=mode,
                headcount=headcount,
                hours_per_week=hours_per_week,
                utilisation_pct=utilisation_pct,
                ai_gain_pct=ai_gain_pct,
                hourly_rate=hourly_rate,
                overhead_pct=overhead_pct,
            )
        )
    return out


def selected_phases(user_inputs: dict[str, Any]) -> list[str]:
    raw = user_inputs.get("phases")
    if not isinstance(raw, list):
        return ["mvp", "phase_1", "phase_2", "future_scope"]
    selected = [p for p in PHASE_ORDER if p in raw]
    if "mvp" not in selected:
        selected.insert(0, "mvp")
    return selected


def contingency_pct(user_inputs: dict[str, Any]) -> float:
    raw = user_inputs.get("contingency_pct")
    if isinstance(raw, (int, float)):
        return float(raw)
    return 15.0


def _phase_index(key: str) -> int:
    try:
        return PHASE_ORDER.index(key)
    except ValueError:
        return 0


def remap_phase(phase: str, selected: list[str] | tuple[str, ...]) -> str:
    selected_set = list(selected)
    if phase in selected_set:
        return phase
    start = _phase_index(phase)
    for later in PHASE_ORDER[start:]:
        if later in selected_set:
            return later
    return "future_scope"


def _hour_cost(hours: float, rate: float | None) -> float | None:
    if rate is None:
        return None
    return _r2(hours * rate)


def compute_estimate(stored: EstimateStored, user_inputs: dict[str, Any]) -> dict[str, Any]:
    team = parse_team(user_inputs)
    estimated = [r for r in team if r.mode == "estimated"]
    overhead_roles = [r for r in team if r.mode != "estimated"]
    estimated_names = {r.role for r in estimated}
    role_by_name = {r.role: r for r in team}
    phases = selected_phases(user_inputs)
    contig = contingency_pct(user_inputs)
    currency = str(user_inputs.get("currency") or "").strip()
    has_any_rate = any(r.hourly_rate is not None for r in team)

    items: dict[str, dict[str, Any]] = {}
    for feat in stored.feature_estimates:
        items[feat.feature_id] = {
            "id": feat.feature_id,
            "title": feat.title,
            "kind": "feature",
            "phase": feat.phase,
            "component": feat.component,
            "confidence": feat.confidence,
            "ai_leverage": feat.ai_leverage,
            "complexity": feat.complexity,
            "not_estimated": feat.not_estimated,
            "status": "Not estimated" if feat.not_estimated else "Estimated",
        }
    for pkg in stored.work_packages:
        items[pkg.id] = {
            "id": pkg.id,
            "title": pkg.title,
            "kind": "work_package",
            "phase": pkg.phase,
            "component": pkg.component,
            "confidence": pkg.confidence,
            "ai_leverage": pkg.ai_leverage,
            "complexity": "",
            "not_estimated": False,
            "status": "Estimated",
        }

    # item -> role -> {base, ai_adjusted, buffered}
    hours: dict[str, dict[str, dict[str, float]]] = {iid: {} for iid in items}
    dropped_roles = 0
    for line in stored.effort_lines:
        if line.role not in estimated_names:
            dropped_roles += 1
            continue
        if line.item_id not in items:
            continue
        role = role_by_name[line.role]
        base = clamp_base_hours(float(line.base_hours))
        if base <= 0:
            continue
        item = items[line.item_id]
        ai_adj = ai_adjusted_hours(base, role.ai_gain_pct, str(item["ai_leverage"]))
        buf = buffered_hours(ai_adj, str(item["confidence"]), contig)
        hours[line.item_id][line.role] = {
            "base": base,
            "ai_adjusted": ai_adj,
            "buffered": buf,
        }

    def _sum_role_hours(
        phase_key: str, role_name: str, field: str, *, committed_only: bool | None = None
    ) -> float:
        total = 0.0
        for iid, item in items.items():
            if item["phase"] != phase_key:
                continue
            if committed_only is True and phase_key == "future_scope":
                continue
            cell = hours.get(iid, {}).get(role_name)
            if cell:
                total += cell[field]
        return total

    phase_meta = {p.key: p for p in stored.phases}
    phase_rows: list[dict[str, Any]] = []
    utilisation_hints: list[dict[str, Any]] = []
    committed_phases = [p for p in phases if p != "future_scope"]

    phase_buffered_estimated: dict[str, float] = {}
    phase_weeks_planned: dict[str, float] = {}
    phase_weeks_exact: dict[str, float] = {}

    used_item_phases = {item["phase"] for item in items.values()}
    for phase_key in PHASE_ORDER:
        if phase_key not in phases and phase_key not in used_item_phases:
            continue
        role_weeks: list[float] = []
        hours_by_role: dict[str, dict[str, float]] = {}
        est_buffered = 0.0
        for role in estimated:
            base = _sum_role_hours(phase_key, role.role, "base")
            ai_adj = _sum_role_hours(phase_key, role.role, "ai_adjusted")
            buf = _sum_role_hours(phase_key, role.role, "buffered")
            hours_by_role[role.role] = {
                "base": _r2(base),
                "ai_adjusted": _r2(ai_adj),
                "buffered": _r2(buf),
            }
            est_buffered += buf
            cap = role.capacity
            weeks_r = (buf / cap) if cap > 0 else 0.0
            role_weeks.append(weeks_r)
        exact = max(role_weeks) if role_weeks else 0.0
        planned = ceil_to_half(exact)
        phase_buffered_estimated[phase_key] = est_buffered
        phase_weeks_exact[phase_key] = exact
        phase_weeks_planned[phase_key] = planned

        overhead_hours: dict[str, float] = {}
        for role in overhead_roles:
            if role.mode == "percent_of_delivery":
                pct = (role.overhead_pct or 0) / 100.0
                oh = pct * est_buffered
            else:
                oh = role.capacity * planned
            overhead_hours[role.role] = _r2(oh)

        for role in estimated:
            cap = role.capacity
            buf = hours_by_role[role.role]["buffered"]
            denom = cap * planned
            util = (buf / denom * 100.0) if denom > 0 else 0.0
            hint = ""
            if planned > 0 and util < 50:
                hint = "under 50%"
            elif planned > 0 and util > 100:
                hint = "over 100%"
            if hint:
                utilisation_hints.append(
                    {
                        "role": role.role,
                        "phase": phase_key,
                        "utilisation_pct": _r2(util),
                        "hint": hint,
                    }
                )
            hours_by_role[role.role]["utilisation_pct"] = _r2(util)

        cost = 0.0
        if has_any_rate:
            for role in estimated:
                part = _hour_cost(hours_by_role[role.role]["buffered"], role.hourly_rate)
                if part is not None:
                    cost += part
            for role in overhead_roles:
                part = _hour_cost(overhead_hours[role.role], role.hourly_rate)
                if part is not None:
                    cost += part

        meta = phase_meta.get(phase_key)
        hours_parts = [
            f"{name}: {_fmt(vals['buffered'])} h"
            for name, vals in hours_by_role.items()
        ]
        hours_parts.extend(f"{name}: {_fmt(h)} h" for name, h in overhead_hours.items())
        hint_text = "; ".join(
            f"{h['role']} {h['hint']}"
            for h in utilisation_hints
            if h["phase"] == phase_key
        )
        phase_rows.append(
            {
                "phase": phase_key,
                "goal": meta.goal if meta else "",
                "scope_rationale": meta.scope_rationale if meta else "",
                "hours_by_role": " · ".join(hours_parts),
                "weeks_exact": _r2(exact),
                "weeks_planned": planned,
                "utilisation_hints": hint_text,
                "cost": _r2(cost) if has_any_rate else None,
                "estimated_hours": {k: dict(v) for k, v in hours_by_role.items()},
                "overhead_hours": overhead_hours,
                "committed": phase_key != "future_scope" and phase_key in committed_phases,
            }
        )

    # Totals
    def _committed_sum(field: str) -> float:
        total = 0.0
        for iid, item in items.items():
            if item["phase"] == "future_scope":
                continue
            if item["phase"] not in committed_phases:
                continue
            for cell in hours.get(iid, {}).values():
                total += cell[field]
        return total

    hours_without_ai = _committed_sum("base")
    hours_with_ai = _committed_sum("ai_adjusted")
    saving_pct = (
        ((hours_without_ai - hours_with_ai) / hours_without_ai * 100.0)
        if hours_without_ai > 0
        else 0.0
    )
    project_weeks = sum(
        phase_weeks_planned.get(p, 0.0) for p in committed_phases
    )
    months = project_weeks / get_settings().ESTIMATE_WEEKS_PER_MONTH if project_weeks else 0.0

    committed_buffered_est = _committed_sum("buffered")
    committed_overhead = 0.0
    for row in phase_rows:
        if row["committed"]:
            committed_overhead += sum(row["overhead_hours"].values())

    total_cost = 0.0
    if has_any_rate:
        for row in phase_rows:
            if row["committed"] and row["cost"] is not None:
                total_cost += row["cost"]

    cards: list[dict[str, str]] = [
        {"key": "hours_with_ai", "label": "Hours with AI tools", "value": f"{_fmt(hours_with_ai)} h"},
        {
            "key": "hours_without_ai",
            "label": "Hours without AI tools",
            "value": f"{_fmt(hours_without_ai)} h",
        },
        {"key": "saving_pct", "label": "AI saving", "value": f"{_fmt(saving_pct)}%"},
        {
            "key": "duration",
            "label": "Committed duration",
            "value": f"{_fmt(project_weeks)} weeks ({_fmt(months)} months)",
        },
    ]
    if has_any_rate:
        label = f"{currency} {_fmt(total_cost)}".strip() if currency else _fmt(total_cost)
        cards.append({"key": "cost", "label": "Estimated cost", "value": label})

    # Feature / work package display rows
    feature_rows: list[dict[str, Any]] = []
    work_package_rows: list[dict[str, Any]] = []
    for iid, item in items.items():
        role_bits: list[str] = []
        total_base = 0.0
        total_ai = 0.0
        total_buf = 0.0
        per_role: dict[str, dict[str, float]] = {}
        for role in estimated:
            cell = hours.get(iid, {}).get(role.role)
            if not cell:
                continue
            per_role[role.role] = {
                "base": cell["base"],
                "ai_adjusted": _r2(cell["ai_adjusted"]),
                "buffered": _r2(cell["buffered"]),
            }
            total_base += cell["base"]
            total_ai += cell["ai_adjusted"]
            total_buf += cell["buffered"]
            role_bits.append(
                f"{role.role} {_fmt(cell['base'])} / {_fmt(cell['ai_adjusted'])}"
            )
        row = {
            "id": item["id"],
            "title": item["title"],
            "kind": item["kind"],
            "phase": item["phase"],
            "component": item["component"],
            "confidence": item["confidence"],
            "ai_leverage": item["ai_leverage"],
            "complexity": item["complexity"],
            "status": item["status"],
            "hours_by_role": "; ".join(role_bits),
            "total_base": _r2(total_base),
            "total_ai": _r2(total_ai),
            "total_buffered": _r2(total_buf),
            "per_role": per_role,
        }
        if item["kind"] == "feature":
            feature_rows.append(row)
        else:
            work_package_rows.append(row)

    # Phase x component matrix (buffered estimated hours)
    components = [c.name for c in stored.components]
    extra_components = sorted(
        {
            str(item["component"])
            for item in items.values()
            if item["component"] and item["component"] not in components
        }
    )
    all_components = components + extra_components
    matrix_rows: list[dict[str, Any]] = []
    for phase_key in [p["phase"] for p in phase_rows]:
        row: dict[str, Any] = {"phase": phase_key}
        for comp in all_components:
            total = 0.0
            for iid, item in items.items():
                if item["phase"] == phase_key and item["component"] == comp:
                    total += sum(cell["buffered"] for cell in hours.get(iid, {}).values())
            row[comp] = _r2(total)
        matrix_rows.append(row)

    component_totals: list[dict[str, Any]] = []
    for comp in all_components:
        totals_by_role: dict[str, float] = {}
        buffered_total = 0.0
        for iid, item in items.items():
            if item["component"] != comp:
                continue
            if item["phase"] == "future_scope":
                continue
            for role_name, cell in hours.get(iid, {}).items():
                totals_by_role[role_name] = totals_by_role.get(role_name, 0.0) + cell["buffered"]
                buffered_total += cell["buffered"]
        component_totals.append(
            {
                "component": comp,
                "buffered_hours": _r2(buffered_total),
                "hours_by_role": " · ".join(
                    f"{name}: {_fmt(val)} h" for name, val in totals_by_role.items()
                ),
            }
        )

    role_totals: list[dict[str, Any]] = []
    for role in estimated:
        base = 0.0
        ai_adj = 0.0
        buf = 0.0
        for iid, item in items.items():
            if item["phase"] == "future_scope":
                continue
            cell = hours.get(iid, {}).get(role.role)
            if not cell:
                continue
            base += cell["base"]
            ai_adj += cell["ai_adjusted"]
            buf += cell["buffered"]
        role_totals.append(
            {
                "role": role.role,
                "mode": role.mode,
                "base": _r2(base),
                "ai_adjusted": _r2(ai_adj),
                "buffered": _r2(buf),
                "headcount": role.headcount,
            }
        )
    for role in overhead_roles:
        oh = sum(
            row["overhead_hours"].get(role.role, 0.0)
            for row in phase_rows
            if row["committed"]
        )
        role_totals.append(
            {
                "role": role.role,
                "mode": role.mode,
                "base": _r2(oh),
                "ai_adjusted": _r2(oh),
                "buffered": _r2(oh),
                "headcount": role.headcount,
            }
        )

    team_snapshot = []
    for row in team:
        snap: dict[str, Any] = {
            "role": row.role,
            "mode": row.mode,
            "headcount": row.headcount,
            "hours_per_week": row.hours_per_week,
            "utilisation_pct": row.utilisation_pct,
            "ai_gain_pct": row.ai_gain_pct,
        }
        if row.hourly_rate is not None:
            snap["hourly_rate"] = row.hourly_rate
        if row.overhead_pct is not None:
            snap["overhead_pct"] = row.overhead_pct
        team_snapshot.append(snap)

    item_export_rows: list[dict[str, Any]] = []
    for row in [*feature_rows, *work_package_rows]:
        export: dict[str, Any] = {
            "status": row["status"],
            "phase": row["phase"],
            "component": row["component"],
            "id": row["id"],
            "title": row["title"],
            "kind": row["kind"],
            "confidence": row["confidence"],
            "ai_leverage": row["ai_leverage"],
            "total_ai": row["total_ai"],
            "total_buffered": row["total_buffered"],
            "per_role": row["per_role"],
        }
        item_export_rows.append(export)

    return {
        "cards": cards,
        "warnings": [],
        "team": team_snapshot,
        "phase_rows": [
            {
                "phase": r["phase"],
                "goal": r["goal"],
                "scope_rationale": r["scope_rationale"],
                "hours_by_role": r["hours_by_role"],
                "weeks_exact": r["weeks_exact"],
                "weeks_planned": r["weeks_planned"],
                "utilisation_hints": r["utilisation_hints"],
                "cost": r["cost"],
            }
            for r in phase_rows
        ],
        "phase_detail": phase_rows,
        "matrix_rows": matrix_rows,
        "matrix_components": all_components,
        "component_totals": component_totals,
        "role_totals": role_totals,
        "feature_rows": feature_rows,
        "work_package_rows": work_package_rows,
        "item_export_rows": item_export_rows,
        "utilisation_hints": utilisation_hints,
        "method_note": METHOD_NOTE,
        "totals": {
            "hours_with_ai": _r2(hours_with_ai),
            "hours_without_ai": _r2(hours_without_ai),
            "saving_pct": _r2(saving_pct),
            "buffered_estimated_committed": _r2(committed_buffered_est),
            "overhead_committed": _r2(committed_overhead),
            "weeks": _r2(project_weeks),
            "months": _r2(months),
            "cost": _r2(total_cost) if has_any_rate else None,
            "currency": currency,
            "has_cost": has_any_rate,
        },
        "estimated_roles": [r.role for r in estimated],
        "dropped_unknown_roles": dropped_roles,
        "contingency_pct": contig,
        "leverage": {
            "high": get_settings().ESTIMATE_LEVERAGE_HIGH,
            "medium": get_settings().ESTIMATE_LEVERAGE_MEDIUM,
            "low": get_settings().ESTIMATE_LEVERAGE_LOW,
        },
        "risk": {
            "high": get_settings().ESTIMATE_RISK_HIGH,
            "medium": get_settings().ESTIMATE_RISK_MEDIUM,
            "low": get_settings().ESTIMATE_RISK_LOW,
        },
        "phase_weeks_planned": phase_weeks_planned,
        "phase_weeks_exact": {k: _r2(v) for k, v in phase_weeks_exact.items()},
    }


def _fmt(value: float) -> str:
    rounded = _r2(value)
    if math.isclose(rounded, int(rounded), abs_tol=1e-9):
        return str(int(rounded))
    return f"{rounded:.2f}".rstrip("0").rstrip(".")



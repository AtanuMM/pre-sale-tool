"""Estimate v2 calculations. No database access. Results live on content.computed."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Any

from app.config import get_settings
from app.steps.estimate_calc import (
    ceil_to_half,
    round_to_half,
    selected_phases,
    weekly_capacity,
)
from app.steps.schemas.estimate_v2 import (
    PHASE_ORDER,
    REQUIRED_PACKAGE_TYPES,
    RISK_CONFIDENCE_CAP_DOMAINS,
    EstimateV2Stored,
    StoredWorkPackageV2,
)

METHOD_NOTE_V2 = (
    "Task hours are the model's range for a competent mid-level engineer working "
    "without AI tools (implementation, self-testing, code review and bug fixing). "
    "AI reduction applies only to development-discipline roles, capped per item by "
    "leverage (high 30%, medium 15%, low 5%, none 0%) and at 25% of development "
    "likely base hours across the project. "
    "Recommended hours = hours with AI (likely) × (1 + confidence buffer: "
    "high 15%, medium 25%, low 40%). There is no separate contingency. "
    "Could-priority items are optional and excluded from committed totals. "
    "Future scope is indicative only. "
    "Calendar weeks for a phase are the maximum of (recommended hours / weekly "
    "capacity) across estimated roles, rounded up to the next 0.5 week. Phases "
    "run sequentially; roles work in parallel within a phase. This is a duration "
    "sketch, not a schedule. "
    "Percent-of-delivery roles take a percentage of estimated-role recommended "
    "hours in the phase. Duration-based roles take weekly capacity × planned weeks."
)


def _r2(value: float) -> float:
    return round(value + 1e-12, 2)


def _fmt(value: float) -> str:
    rounded = _r2(value)
    if math.isclose(rounded, int(rounded), abs_tol=1e-9):
        return str(int(rounded))
    return f"{rounded:.2f}".rstrip("0").rstrip(".")


def domain_experience(user_inputs: dict[str, Any]) -> str:
    raw = str(user_inputs.get("domain_experience") or "some_experience").strip()
    if raw in ("built_similar_before", "some_experience", "new_to_us"):
        return raw
    return "some_experience"


def ai_leverage_cap(leverage: str) -> float:
    settings = get_settings()
    return {
        "high": settings.ESTIMATE_AI_CAP_HIGH,
        "medium": settings.ESTIMATE_AI_CAP_MEDIUM,
        "low": settings.ESTIMATE_AI_CAP_LOW,
        "none": settings.ESTIMATE_AI_CAP_NONE,
    }.get(leverage, settings.ESTIMATE_AI_CAP_NONE)


def confidence_buffer(confidence: str) -> float:
    settings = get_settings()
    return {
        "high": settings.ESTIMATE_BUFFER_HIGH,
        "medium": settings.ESTIMATE_BUFFER_MEDIUM,
        "low": settings.ESTIMATE_BUFFER_LOW,
    }.get(confidence, settings.ESTIMATE_BUFFER_MEDIUM)


def sanitize_hours(best: float, likely: float, worst: float) -> tuple[float, float, float]:
    settings = get_settings()
    cap = settings.ESTIMATE_MAX_HOURS_PER_LINE
    ratio = settings.ESTIMATE_WORST_TO_LIKELY_CAP

    def _one(raw: float) -> float:
        rounded = round_to_half(raw)
        if rounded < 0:
            return 0.0
        if rounded > cap:
            return cap
        return rounded

    best_h = _one(best)
    likely_h = _one(likely)
    worst_h = _one(worst)
    best_h = min(best_h, likely_h)
    worst_h = max(worst_h, likely_h)
    if likely_h > 0 and worst_h > ratio * likely_h:
        worst_h = round_to_half(ratio * likely_h)
        worst_h = max(worst_h, likely_h)
    return best_h, likely_h, worst_h


def apply_confidence_guardrails(
    confidence: str,
    *,
    domain_exp: str,
    gap_severity: str | None,
    risk_domain: str,
) -> tuple[str, list[str]]:
    codes: list[str] = []
    applied = confidence if confidence in ("high", "medium", "low") else "medium"
    if domain_exp != "built_similar_before" and applied == "high":
        applied = "medium"
        codes.append("experience_cap")
    if gap_severity == "high":
        applied = "low"
        codes.append("high_gap")
    elif gap_severity == "medium" and applied == "high":
        applied = "medium"
        codes.append("medium_gap")
    if risk_domain in RISK_CONFIDENCE_CAP_DOMAINS and applied == "high":
        applied = "medium"
        codes.append("risk_domain")
    return applied, codes


def apply_leverage_guardrails(leverage: str, *, risk_domain: str, discipline: str) -> str:
    applied = leverage if leverage in ("high", "medium", "low", "none") else "none"
    if discipline != "development":
        return "none"
    if risk_domain and risk_domain != "none":
        return "none"
    return applied


def line_ai_reduction(ai_gain_pct: float, leverage: str, *, discipline: str, risk_domain: str) -> float:
    if discipline != "development":
        return 0.0
    gated = apply_leverage_guardrails(leverage, risk_domain=risk_domain, discipline=discipline)
    return min(max(ai_gain_pct, 0.0) / 100.0, ai_leverage_cap(gated))


def ai_adjusted_range(
    best: float,
    likely: float,
    worst: float,
    reduction: float,
    *,
    cap_factor: float = 1.0,
) -> tuple[float, float, float]:
    factor = max(0.0, 1.0 - reduction * cap_factor)
    return _r2(best * factor), _r2(likely * factor), _r2(worst * factor)


def buffered_likely(ai_likely: float, confidence: str) -> float:
    return _r2(ai_likely * (1.0 + confidence_buffer(confidence)))


@dataclass(frozen=True)
class TeamRoleV2:
    role: str
    mode: str
    discipline: str
    headcount: float
    hours_per_week: float
    utilisation_pct: float
    ai_gain_pct: float
    hourly_rate: float | None
    overhead_pct: float | None

    @property
    def capacity(self) -> float:
        return weekly_capacity(self.headcount, self.hours_per_week, self.utilisation_pct)


def parse_team_v2(user_inputs: dict[str, Any]) -> list[TeamRoleV2]:
    rows = user_inputs.get("team")
    if not isinstance(rows, list):
        return []
    out: list[TeamRoleV2] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        role = str(row.get("role") or "").strip()
        mode = str(row.get("mode") or "").strip()
        if not role or mode not in ("estimated", "percent_of_delivery", "duration_based"):
            continue
        discipline = str(row.get("discipline") or "other").strip()
        if discipline not in ("development", "qa", "design", "management", "devops", "other"):
            discipline = "other"
        ai_gain_pct = float(row.get("ai_gain_pct") or 0)
        if discipline != "development":
            ai_gain_pct = 0.0
        raw_rate = row.get("hourly_rate")
        hourly_rate = float(raw_rate) if isinstance(raw_rate, (int, float)) else None
        raw_oh = row.get("overhead_pct")
        overhead_pct = float(raw_oh) if isinstance(raw_oh, (int, float)) else None
        out.append(
            TeamRoleV2(
                role=role,
                mode=mode,
                discipline=discipline,
                headcount=float(row.get("headcount") or 0),
                hours_per_week=float(row.get("hours_per_week") or 0),
                utilisation_pct=float(row.get("utilisation_pct") or 0),
                ai_gain_pct=ai_gain_pct,
                hourly_rate=hourly_rate,
                overhead_pct=overhead_pct,
            )
        )
    return out


def _parse_iso_date(raw: Any) -> date | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip()[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _hour_cost(hours: float, rate: float | None) -> float | None:
    if rate is None:
        return None
    return _r2(hours * rate)


def _highest_gap_severity(refs: tuple[str, ...] | list[str], severities: dict[str, str]) -> str | None:
    rank = {"low": 1, "medium": 2, "high": 3}
    best: str | None = None
    best_rank = 0
    for ref in refs:
        sev = severities.get(ref) or severities.get(ref.upper())
        if sev is None:
            continue
        r = rank.get(sev, 0)
        if r > best_rank:
            best = sev
            best_rank = r
    return best


def delivery_role(team: list[TeamRoleV2]) -> TeamRoleV2 | None:
    estimated = [r for r in team if r.mode == "estimated"]
    for role in estimated:
        if role.discipline == "development":
            return role
    return estimated[0] if estimated else None


def default_package_hours(
    package_type: str,
    *,
    dev_ai_likely: float,
    delivery: TeamRoleV2 | None,
) -> float:
    settings = get_settings()
    pct = {
        "stabilization": settings.ESTIMATE_STABILIZATION_FLOOR,
        "uat_support": settings.ESTIMATE_UAT_PCT,
        "deployment": settings.ESTIMATE_DEPLOYMENT_PCT,
        "documentation_training": settings.ESTIMATE_DOCS_PCT,
        "hypercare": settings.ESTIMATE_HYPERCARE_PCT,
        "project_setup_architecture": 0.04,
        "cicd_environments": 0.03,
    }.get(package_type, 0.0)
    by_pct = _r2(dev_ai_likely * pct)
    if package_type == "hypercare":
        weeks_cap = 0.0
        if delivery is not None:
            weeks_cap = _r2(settings.ESTIMATE_HYPERCARE_WEEKS * delivery.capacity)
        return max(by_pct, weeks_cap)
    if package_type == "stabilization":
        return max(by_pct, _r2(dev_ai_likely * settings.ESTIMATE_STABILIZATION_FLOOR))
    return by_pct


def _item_meta(stored: EstimateV2Stored) -> dict[str, dict[str, Any]]:
    items: dict[str, dict[str, Any]] = {}
    for feat in stored.feature_estimates:
        items[feat.feature_id] = {
            "id": feat.feature_id,
            "title": feat.title,
            "kind": "feature",
            "phase": feat.phase,
            "component": feat.component,
            "confidence": feat.confidence,
            "confidence_raw": feat.confidence_raw,
            "ai_leverage": feat.ai_leverage,
            "ai_leverage_raw": feat.ai_leverage_raw,
            "complexity": feat.complexity,
            "not_estimated": feat.not_estimated,
            "priority": feat.priority,
            "origin": feat.origin,
            "primary_risk_domain": feat.primary_risk_domain,
            "default_allowance": False,
            "package_type": "",
            "optional": feat.priority == "could",
            "status": "Not estimated" if feat.not_estimated else "Estimated",
        }
    for added in stored.added_items:
        items[added.id] = {
            "id": added.id,
            "title": added.title,
            "kind": "added",
            "phase": added.phase,
            "component": added.component,
            "confidence": added.confidence,
            "confidence_raw": added.confidence_raw,
            "ai_leverage": added.ai_leverage,
            "ai_leverage_raw": added.ai_leverage_raw,
            "complexity": added.complexity,
            "not_estimated": False,
            "priority": "must",
            "origin": "implied",
            "primary_risk_domain": added.primary_risk_domain,
            "default_allowance": False,
            "package_type": "",
            "optional": False,
            "status": "Added",
        }
    for pkg in stored.work_packages:
        items[pkg.id] = {
            "id": pkg.id,
            "title": pkg.title,
            "kind": "work_package",
            "phase": pkg.phase,
            "component": pkg.component,
            "confidence": pkg.confidence,
            "confidence_raw": pkg.confidence_raw,
            "ai_leverage": pkg.ai_leverage,
            "ai_leverage_raw": pkg.ai_leverage_raw,
            "complexity": "",
            "not_estimated": False,
            "priority": "must",
            "origin": "package",
            "primary_risk_domain": "none",
            "default_allowance": pkg.default_allowance,
            "package_type": pkg.package_type,
            "optional": False,
            "status": "Default allowance" if pkg.default_allowance else "Estimated",
        }
    return items


@dataclass
class _RoleHours:
    best: float = 0.0
    likely: float = 0.0
    worst: float = 0.0
    ai_best: float = 0.0
    ai_likely: float = 0.0
    ai_worst: float = 0.0
    recommended: float = 0.0
    reduction: float = 0.0


def compute_estimate_v2(
    stored: EstimateV2Stored,
    user_inputs: dict[str, Any],
    *,
    gap_severities: dict[str, str] | None = None,
    feature_gap_refs: dict[str, tuple[str, ...]] | None = None,
    implied_count: int = 0,
    suggested_count: int = 0,
    source_requirements_total: int = 0,
) -> dict[str, Any]:
    settings = get_settings()
    team = parse_team_v2(user_inputs)
    estimated = [r for r in team if r.mode == "estimated"]
    overhead_roles = [r for r in team if r.mode != "estimated"]
    estimated_names = {r.role for r in estimated}
    role_by_name = {r.role: r for r in team}
    phases = selected_phases(user_inputs)
    currency = str(user_inputs.get("currency") or "").strip()
    has_any_rate = any(r.hourly_rate is not None for r in team)
    domain_exp = domain_experience(user_inputs)
    items = _item_meta(stored)
    committed_phases = [p for p in phases if p != "future_scope"]
    gap_severities = gap_severities or {}
    feature_gap_refs = feature_gap_refs or {}

    # Re-apply guardrails from raw fields so team/domain changes take effect.
    for iid, item in items.items():
        risk = str(item.get("primary_risk_domain") or "none")
        gap_sev = None
        if item["kind"] == "feature":
            gap_sev = _highest_gap_severity(feature_gap_refs.get(iid, ()), gap_severities)
        conf, codes = apply_confidence_guardrails(
            str(item.get("confidence_raw") or item["confidence"]),
            domain_exp=domain_exp,
            gap_severity=gap_sev,
            risk_domain=risk,
        )
        item["confidence"] = conf
        item["guardrail_codes"] = codes
        item["ai_leverage"] = apply_leverage_guardrails(
            str(item.get("ai_leverage_raw") or item["ai_leverage"]),
            risk_domain=risk,
            discipline="development",
        )

    hours: dict[str, dict[str, _RoleHours]] = {iid: {} for iid in items}
    dropped_roles = 0
    for line in stored.effort_lines:
        if line.role not in estimated_names:
            dropped_roles += 1
            continue
        if line.item_id not in items:
            continue
        item = items[line.item_id]
        if item.get("default_allowance"):
            continue
        role = role_by_name[line.role]
        best, likely, worst = sanitize_hours(
            float(line.best_hours), float(line.likely_hours), float(line.worst_hours)
        )
        if likely <= 0 and best <= 0 and worst <= 0:
            continue
        reduction = line_ai_reduction(
            role.ai_gain_pct,
            str(item["ai_leverage"]),
            discipline=role.discipline,
            risk_domain=str(item["primary_risk_domain"]),
        )
        cell = hours[line.item_id].setdefault(line.role, _RoleHours())
        cell.best += best
        cell.likely += likely
        cell.worst += worst
        cell.reduction = max(cell.reduction, reduction)

    def _is_committed(item: dict[str, Any]) -> bool:
        if item["optional"]:
            return False
        if item["phase"] == "future_scope":
            return False
        return item["phase"] in committed_phases

    def _dev_likely_base() -> float:
        total = 0.0
        for iid, item in items.items():
            if not _is_committed(item) or item.get("default_allowance"):
                continue
            for role_name, cell in hours.get(iid, {}).items():
                role = role_by_name.get(role_name)
                if role is None or role.discipline != "development":
                    continue
                total += cell.likely
        return total

    def _dev_reduction_hours() -> float:
        total = 0.0
        for iid, item in items.items():
            if not _is_committed(item) or item.get("default_allowance"):
                continue
            for role_name, cell in hours.get(iid, {}).items():
                role = role_by_name.get(role_name)
                if role is None or role.discipline != "development":
                    continue
                total += cell.likely * cell.reduction
        return total

    dev_base = _dev_likely_base()
    reduction_hours = _dev_reduction_hours()
    cap_limit = settings.ESTIMATE_AI_PROJECT_CAP * dev_base
    cap_factor = 1.0
    if reduction_hours > cap_limit and reduction_hours > 0:
        cap_factor = cap_limit / reduction_hours

    for iid, by_role in hours.items():
        item = items[iid]
        for role_name, cell in by_role.items():
            role = role_by_name[role_name]
            factor = cap_factor if role.discipline == "development" else 1.0
            cell.ai_best, cell.ai_likely, cell.ai_worst = ai_adjusted_range(
                cell.best, cell.likely, cell.worst, cell.reduction, cap_factor=factor
            )
            cell.recommended = buffered_likely(cell.ai_likely, str(item["confidence"]))

    def _sum_dev_ai_likely_committed() -> float:
        total = 0.0
        for iid, item in items.items():
            if not _is_committed(item) or item.get("default_allowance"):
                continue
            for role_name, cell in hours.get(iid, {}).items():
                role = role_by_name.get(role_name)
                if role is None or role.discipline != "development":
                    continue
                total += cell.ai_likely
        return total

    delivery = delivery_role(team)
    dev_ai_likely = _sum_dev_ai_likely_committed()
    default_role = delivery.role if delivery is not None else (estimated[0].role if estimated else "")
    default_phase = committed_phases[-1] if committed_phases else "mvp"
    default_component = stored.components[0].name if stored.components else "Other"

    # Recalculate default-allowance package hours from current development AI-adjusted likely.
    for pkg in stored.work_packages:
        if not pkg.default_allowance:
            continue
        allowance = default_package_hours(
            pkg.package_type, dev_ai_likely=dev_ai_likely, delivery=delivery
        )
        if not default_role or allowance <= 0:
            continue
        cell = _RoleHours(
            best=allowance,
            likely=allowance,
            worst=allowance,
            ai_best=allowance,
            ai_likely=allowance,
            ai_worst=allowance,
            recommended=buffered_likely(allowance, str(items[pkg.id]["confidence"])),
        )
        hours[pkg.id] = {default_role: cell}

    def _sum_field(
        phase_key: str,
        role_name: str,
        field: str,
        *,
        committed_only: bool = False,
        include_optional: bool = True,
        include_future: bool = True,
    ) -> float:
        total = 0.0
        for iid, item in items.items():
            if item["phase"] != phase_key:
                continue
            if committed_only and not _is_committed(item):
                continue
            if not include_optional and item["optional"]:
                continue
            if not include_future and item["phase"] == "future_scope":
                continue
            cell = hours.get(iid, {}).get(role_name)
            if cell:
                total += float(getattr(cell, field))
        return total

    phase_meta = {p.key: p for p in stored.phases}
    phase_rows: list[dict[str, Any]] = []
    utilisation_hints: list[dict[str, Any]] = []
    phase_weeks_planned: dict[str, float] = {}
    phase_weeks_exact: dict[str, float] = {}
    used_item_phases = {item["phase"] for item in items.values()}

    for phase_key in PHASE_ORDER:
        if phase_key not in phases and phase_key not in used_item_phases:
            continue
        role_weeks: list[float] = []
        hours_by_role: dict[str, dict[str, float]] = {}
        est_recommended = 0.0
        for role in estimated:
            likely = _sum_field(phase_key, role.role, "likely")
            ai_likely = _sum_field(phase_key, role.role, "ai_likely")
            rec = _sum_field(phase_key, role.role, "recommended")
            hours_by_role[role.role] = {
                "likely": _r2(likely),
                "ai_likely": _r2(ai_likely),
                "recommended": _r2(rec),
            }
            est_recommended += rec
            cap = role.capacity
            weeks_r = (rec / cap) if cap > 0 else 0.0
            role_weeks.append(weeks_r)
        exact = max(role_weeks) if role_weeks else 0.0
        planned = ceil_to_half(exact)
        phase_weeks_exact[phase_key] = exact
        phase_weeks_planned[phase_key] = planned

        overhead_hours: dict[str, float] = {}
        for role in overhead_roles:
            if role.mode == "percent_of_delivery":
                pct = (role.overhead_pct or 0) / 100.0
                oh = pct * est_recommended
            else:
                oh = role.capacity * planned
            overhead_hours[role.role] = _r2(oh)

        for role in estimated:
            cap = role.capacity
            rec = hours_by_role[role.role]["recommended"]
            denom = cap * planned
            util = (rec / denom * 100.0) if denom > 0 else 0.0
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
                part = _hour_cost(hours_by_role[role.role]["recommended"], role.hourly_rate)
                if part is not None:
                    cost += part
            for role in overhead_roles:
                part = _hour_cost(overhead_hours[role.role], role.hourly_rate)
                if part is not None:
                    cost += part

        meta = phase_meta.get(phase_key)
        hours_parts = [
            f"{name}: {_fmt(vals['recommended'])} h"
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

    def _bucket_sum(field: str, predicate) -> float:
        total = 0.0
        for iid, item in items.items():
            if not predicate(item):
                continue
            for cell in hours.get(iid, {}).values():
                total += float(getattr(cell, field))
        return total

    committed = _is_committed

    def optional_pred(item: dict[str, Any]) -> bool:
        return bool(item["optional"] and item["phase"] != "future_scope")

    def future_pred(item: dict[str, Any]) -> bool:
        return item["phase"] == "future_scope"

    hours_without_ai = _bucket_sum("likely", committed)
    hours_best = _bucket_sum("best", committed)
    hours_worst = _bucket_sum("worst", committed)
    hours_with_ai = _bucket_sum("ai_likely", committed)
    hours_with_ai_best = _bucket_sum("ai_best", committed)
    hours_with_ai_worst = _bucket_sum("ai_worst", committed)
    recommended_est = _bucket_sum("recommended", committed)
    optional_likely = _bucket_sum("likely", optional_pred)
    optional_recommended = _bucket_sum("recommended", optional_pred)
    future_likely = _bucket_sum("likely", future_pred)
    saving_pct = (
        ((hours_without_ai - hours_with_ai) / hours_without_ai * 100.0)
        if hours_without_ai > 0
        else 0.0
    )
    project_weeks = sum(phase_weeks_planned.get(p, 0.0) for p in committed_phases)
    months = project_weeks / settings.ESTIMATE_WEEKS_PER_MONTH if project_weeks else 0.0

    committed_overhead = 0.0
    for row in phase_rows:
        if row["committed"]:
            committed_overhead += sum(row["overhead_hours"].values())
    recommended_total = recommended_est + committed_overhead

    total_cost = 0.0
    if has_any_rate:
        for row in phase_rows:
            if row["committed"] and row["cost"] is not None:
                total_cost += row["cost"]

    cap_note = ""
    if cap_factor < 1.0 - 1e-9:
        cap_note = (
            f"Project AI cap applied (factor {_fmt(cap_factor)}); "
            f"reduction limited to {_fmt(settings.ESTIMATE_AI_PROJECT_CAP * 100)}% of "
            "development likely base hours."
        )

    cards: list[dict[str, str]] = [
        {
            "key": "hours_likely",
            "label": "Likely hours without AI",
            "value": f"{_fmt(hours_without_ai)} h (best {_fmt(hours_best)} · worst {_fmt(hours_worst)})",
        },
        {
            "key": "hours_with_ai",
            "label": "Likely hours with AI",
            "value": (
                f"{_fmt(hours_with_ai)} h "
                f"(best {_fmt(hours_with_ai_best)} · worst {_fmt(hours_with_ai_worst)})"
            ),
        },
        {"key": "saving_pct", "label": "AI saving", "value": f"{_fmt(saving_pct)}%"},
        {
            "key": "recommended",
            "label": "Recommended committed hours",
            "value": f"{_fmt(recommended_total)} h",
        },
        {
            "key": "duration",
            "label": "Committed duration",
            "value": f"{_fmt(project_weeks)} weeks ({_fmt(months)} months)",
        },
        {
            "key": "optional",
            "label": "Optional (Could)",
            "value": f"{_fmt(optional_recommended)} h",
        },
        {
            "key": "future",
            "label": "Future scope (indicative)",
            "value": f"{_fmt(future_likely)} h",
        },
    ]
    if cap_note:
        cards.append({"key": "ai_cap", "label": "AI cap", "value": cap_note})
    if has_any_rate:
        label = f"{currency} {_fmt(total_cost)}".strip() if currency else _fmt(total_cost)
        cards.append({"key": "cost", "label": "Estimated cost", "value": label})

    feature_rows: list[dict[str, Any]] = []
    added_rows: list[dict[str, Any]] = []
    work_package_rows: list[dict[str, Any]] = []
    optional_rows: list[dict[str, Any]] = []
    future_rows: list[dict[str, Any]] = []
    item_export_rows: list[dict[str, Any]] = []

    for iid, item in items.items():
        role_bits: list[str] = []
        totals = _RoleHours()
        per_role: dict[str, dict[str, float]] = {}
        for role in estimated:
            cell = hours.get(iid, {}).get(role.role)
            if not cell:
                continue
            per_role[role.role] = {
                "best": _r2(cell.best),
                "likely": _r2(cell.likely),
                "worst": _r2(cell.worst),
                "ai_best": _r2(cell.ai_best),
                "ai_adjusted": _r2(cell.ai_likely),
                "ai_likely": _r2(cell.ai_likely),
                "ai_worst": _r2(cell.ai_worst),
                "recommended": _r2(cell.recommended),
                "base": _r2(cell.likely),
                "buffered": _r2(cell.recommended),
            }
            totals.best += cell.best
            totals.likely += cell.likely
            totals.worst += cell.worst
            totals.ai_likely += cell.ai_likely
            totals.recommended += cell.recommended
            role_bits.append(
                f"{role.role} {_fmt(cell.likely)} / {_fmt(cell.ai_likely)} / {_fmt(cell.recommended)}"
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
            "priority": item["priority"],
            "hours_by_role": "; ".join(role_bits),
            "total_best": _r2(totals.best),
            "total_likely": _r2(totals.likely),
            "total_worst": _r2(totals.worst),
            "total_ai": _r2(totals.ai_likely),
            "total_recommended": _r2(totals.recommended),
            "total_buffered": _r2(totals.recommended),
            "per_role": per_role,
        }
        export = {
            "status": row["status"],
            "phase": row["phase"],
            "component": row["component"],
            "id": row["id"],
            "title": row["title"],
            "kind": row["kind"],
            "confidence": row["confidence"],
            "ai_leverage": row["ai_leverage"],
            "total_best": row["total_best"],
            "total_likely": row["total_likely"],
            "total_worst": row["total_worst"],
            "total_ai": row["total_ai"],
            "total_recommended": row["total_recommended"],
            "total_buffered": row["total_recommended"],
            "per_role": per_role,
        }
        item_export_rows.append(export)
        if item["optional"]:
            optional_rows.append(row)
        elif item["phase"] == "future_scope":
            future_rows.append(row)
        elif item["kind"] == "feature":
            feature_rows.append(row)
        elif item["kind"] == "added":
            added_rows.append(row)
        else:
            work_package_rows.append(row)

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
                if item["phase"] == phase_key and item["component"] == comp and not item["optional"]:
                    total += sum(cell.recommended for cell in hours.get(iid, {}).values())
            row[comp] = _r2(total)
        matrix_rows.append(row)

    component_totals: list[dict[str, Any]] = []
    for comp in all_components:
        rec_total = 0.0
        totals_by_role: dict[str, float] = {}
        for iid, item in items.items():
            if item["component"] != comp or not committed(item):
                continue
            for role_name, cell in hours.get(iid, {}).items():
                totals_by_role[role_name] = totals_by_role.get(role_name, 0.0) + cell.recommended
                rec_total += cell.recommended
        component_totals.append(
            {
                "component": comp,
                "buffered_hours": _r2(rec_total),
                "recommended_hours": _r2(rec_total),
                "hours_by_role": " · ".join(
                    f"{name}: {_fmt(val)} h" for name, val in totals_by_role.items()
                ),
            }
        )

    role_totals: list[dict[str, Any]] = []
    for role in estimated:
        likely = 0.0
        ai_adj = 0.0
        rec = 0.0
        for iid, item in items.items():
            if not committed(item):
                continue
            cell = hours.get(iid, {}).get(role.role)
            if not cell:
                continue
            likely += cell.likely
            ai_adj += cell.ai_likely
            rec += cell.recommended
        role_totals.append(
            {
                "role": role.role,
                "mode": role.mode,
                "discipline": role.discipline,
                "base": _r2(likely),
                "ai_adjusted": _r2(ai_adj),
                "buffered": _r2(rec),
                "recommended": _r2(rec),
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
                "discipline": role.discipline,
                "base": _r2(oh),
                "ai_adjusted": _r2(oh),
                "buffered": _r2(oh),
                "recommended": _r2(oh),
                "headcount": role.headcount,
            }
        )

    team_snapshot = []
    for row in team:
        snap: dict[str, Any] = {
            "role": row.role,
            "mode": row.mode,
            "discipline": row.discipline,
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

    kickoff = _parse_iso_date(user_inputs.get("kickoff_date"))
    target = _parse_iso_date(user_inputs.get("target_date"))
    calendar_weeks = 0.0
    if kickoff is not None and target is not None and target > kickoff:
        calendar_weeks = (target - kickoff).days / 7.0
    capacity_cards: list[dict[str, str]] = []
    if calendar_weeks > 0:
        capacity_cards.append(
            {
                "key": "calendar",
                "label": "Calendar window",
                "value": f"{_fmt(calendar_weeks)} weeks",
            }
        )
        capacity_cards.append(
            {
                "key": "needed",
                "label": "Estimated duration",
                "value": f"{_fmt(project_weeks)} weeks",
            }
        )
        fit = "Fits" if calendar_weeks + 1e-9 >= project_weeks else "Does not fit"
        capacity_cards.append({"key": "fit", "label": "Capacity check", "value": fit})

    lead_time_rows = [
        {
            "id": pkg.id,
            "title": pkg.title,
            "lead_time_weeks": pkg.lead_time_weeks,
        }
        for pkg in stored.work_packages
        if pkg.lead_time_weeks and pkg.lead_time_weeks > 0
    ]

    health_rows = _health_rows(
        items=items,
        hours=hours,
        role_by_name=role_by_name,
        domain_exp=domain_exp,
        cap_factor=cap_factor,
        dropped_roles=dropped_roles,
        implied_count=implied_count,
        suggested_count=suggested_count,
        source_requirements_total=source_requirements_total,
        calendar_weeks=calendar_weeks,
        project_weeks=project_weeks,
        default_allowance_count=sum(1 for i in items.values() if i.get("default_allowance")),
    )

    warnings: list[dict[str, str | int]] = []
    for row in health_rows:
        if row["status"] in ("warn", "fail"):
            warnings.append(
                {
                    "code": str(row["check"]),
                    "count": 1,
                    "label": f"{row['check']}: {row['value']}",
                }
            )

    return {
        "schema_version": 2,
        "cards": cards,
        "warnings": warnings,
        "health_rows": health_rows,
        "capacity_cards": capacity_cards,
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
        "added_rows": added_rows,
        "work_package_rows": work_package_rows,
        "optional_rows": optional_rows,
        "future_rows": future_rows,
        "lead_time_rows": lead_time_rows,
        "item_export_rows": item_export_rows,
        "utilisation_hints": utilisation_hints,
        "method_note": METHOD_NOTE_V2,
        "totals": {
            "hours_with_ai": _r2(hours_with_ai),
            "hours_without_ai": _r2(hours_without_ai),
            "hours_best": _r2(hours_best),
            "hours_worst": _r2(hours_worst),
            "hours_with_ai_best": _r2(hours_with_ai_best),
            "hours_with_ai_worst": _r2(hours_with_ai_worst),
            "saving_pct": _r2(saving_pct),
            "recommended_estimated_committed": _r2(recommended_est),
            "buffered_estimated_committed": _r2(recommended_est),
            "overhead_committed": _r2(committed_overhead),
            "recommended_committed": _r2(recommended_total),
            "optional_recommended": _r2(optional_recommended),
            "optional_likely": _r2(optional_likely),
            "future_likely": _r2(future_likely),
            "weeks": _r2(project_weeks),
            "months": _r2(months),
            "cost": _r2(total_cost) if has_any_rate else None,
            "currency": currency,
            "has_cost": has_any_rate,
            "project_ai_cap_factor": _r2(cap_factor),
            "calendar_weeks": _r2(calendar_weeks),
        },
        "estimated_roles": [r.role for r in estimated],
        "dropped_unknown_roles": dropped_roles,
        "domain_experience": domain_exp,
        "leverage_caps": {
            "high": settings.ESTIMATE_AI_CAP_HIGH,
            "medium": settings.ESTIMATE_AI_CAP_MEDIUM,
            "low": settings.ESTIMATE_AI_CAP_LOW,
            "none": settings.ESTIMATE_AI_CAP_NONE,
        },
        "buffers": {
            "high": settings.ESTIMATE_BUFFER_HIGH,
            "medium": settings.ESTIMATE_BUFFER_MEDIUM,
            "low": settings.ESTIMATE_BUFFER_LOW,
        },
        "phase_weeks_planned": phase_weeks_planned,
        "phase_weeks_exact": {k: _r2(v) for k, v in phase_weeks_exact.items()},
        "default_component": default_component,
        "default_phase": default_phase,
        "default_role": default_role,
        "dev_ai_likely_committed": _r2(dev_ai_likely),
    }


def _health_rows(
    *,
    items: dict[str, dict[str, Any]],
    hours: dict[str, dict[str, _RoleHours]],
    role_by_name: dict[str, TeamRoleV2],
    domain_exp: str,
    cap_factor: float,
    dropped_roles: int,
    implied_count: int,
    suggested_count: int,
    source_requirements_total: int,
    calendar_weeks: float,
    project_weeks: float,
    default_allowance_count: int,
) -> list[dict[str, str]]:
    settings = get_settings()
    rows: list[dict[str, str]] = []

    def add(check: str, value: str, threshold: str, status: str) -> None:
        rows.append({"check": check, "value": value, "threshold": threshold, "status": status})

    not_estimated = sum(1 for i in items.values() if i.get("not_estimated"))
    add(
        "Features not estimated",
        str(not_estimated),
        "0",
        "warn" if not_estimated else "ok",
    )

    high_conf = [
        i
        for i in items.values()
        if i["kind"] == "feature" and i["confidence"] == "high" and not i.get("not_estimated")
    ]
    feat_count = sum(1 for i in items.values() if i["kind"] == "feature" and not i.get("not_estimated"))
    share = (len(high_conf) / feat_count * 100.0) if feat_count else 0.0
    high_ok = domain_exp == "built_similar_before" or share <= 40.0
    add(
        "High confidence share",
        f"{_fmt(share)}%",
        "≤ 40% unless built similar before",
        "ok" if high_ok else "warn",
    )

    def _disc_hours(discipline: str, *, risk: bool | None) -> float:
        total = 0.0
        for iid, item in items.items():
            if item["phase"] == "future_scope" or item["optional"]:
                continue
            risk_domain = str(item.get("primary_risk_domain") or "none")
            is_risk = risk_domain != "none"
            if risk is True and not is_risk:
                continue
            if risk is False and is_risk:
                continue
            for role_name, cell in hours.get(iid, {}).items():
                role = role_by_name.get(role_name)
                if role is None or role.discipline != discipline:
                    continue
                total += cell.ai_likely
        return total

    dev_crud = _disc_hours("development", risk=False)
    qa_crud = _disc_hours("qa", risk=False)
    if dev_crud > 0:
        ratio = qa_crud / dev_crud
        target = settings.ESTIMATE_QA_CRUD_RATIO
        add(
            "QA vs development (CRUD)",
            f"{_fmt(ratio * 100)}%",
            f"about {_fmt(target * 100)}% (warn only)",
            "ok" if abs(ratio - target) <= 0.15 else "warn",
        )
    dev_risk = _disc_hours("development", risk=True)
    qa_risk = _disc_hours("qa", risk=True)
    if dev_risk > 0:
        ratio = qa_risk / dev_risk
        lo = settings.ESTIMATE_QA_RISK_RATIO_MIN
        hi = settings.ESTIMATE_QA_RISK_RATIO_MAX
        add(
            "QA vs development (risk domains)",
            f"{_fmt(ratio * 100)}%",
            f"{_fmt(lo * 100)}–{_fmt(hi * 100)}% (warn only)",
            "ok" if lo - 0.1 <= ratio <= hi + 0.1 else "warn",
        )

    added = sum(1 for i in items.values() if i["kind"] == "added")
    if implied_count > 0 and added == 0:
        add("Implied work coverage", "0 added items", "implied features should produce added items", "warn")
    elif implied_count or suggested_count:
        add(
            "Implied / suggested coverage",
            f"{added} added items (implied {implied_count}, suggested {suggested_count})",
            "added items for implied work",
            "ok",
        )

    add(
        "Project AI cap",
        f"factor {_fmt(cap_factor)}",
        f"≤ {_fmt(settings.ESTIMATE_AI_PROJECT_CAP * 100)}% of development likely base",
        "ok" if cap_factor >= 1.0 - 1e-9 else "warn",
    )
    add(
        "Default allowances",
        str(default_allowance_count),
        "required packages present",
        "ok" if default_allowance_count == 0 else "warn",
    )
    add(
        "Unknown roles dropped",
        str(dropped_roles),
        "0",
        "ok" if dropped_roles == 0 else "warn",
    )
    if calendar_weeks > 0:
        add(
            "Capacity vs dates",
            f"{_fmt(project_weeks)} weeks needed / {_fmt(calendar_weeks)} available",
            "estimated duration ≤ calendar window",
            "ok" if calendar_weeks + 1e-9 >= project_weeks else "fail",
        )
    if source_requirements_total:
        add(
            "Source requirements",
            str(source_requirements_total),
            "traceability count from Feature List",
            "ok",
        )
    return rows


def next_work_package_id(existing: list[str]) -> str:
    numbers: list[int] = []
    for pid in existing:
        if pid.startswith("W-"):
            tail = pid[2:]
            if tail.isdigit():
                numbers.append(int(tail))
    nxt = (max(numbers) + 1) if numbers else 1
    return f"W-{nxt}"


DEFAULT_PACKAGE_TITLES: dict[str, str] = {
    "project_setup_architecture": "Project setup and architecture",
    "cicd_environments": "CI/CD and environments",
    "uat_support": "UAT support",
    "deployment": "Deployment",
    "documentation_training": "Documentation and training",
    "stabilization": "Stabilization",
    "hypercare": "Hypercare",
    "data_migration": "Data migration",
    "third_party_integration_setup": "Third-party integration setup",
}


def ensure_required_packages(
    stored: EstimateV2Stored,
    computed_defaults: dict[str, Any],
    *,
    extra_types: tuple[str, ...] = (),
) -> tuple[EstimateV2Stored, int]:
    """Fill missing required work packages with default-allowance hours."""
    from app.steps.schemas.estimate_v2 import EffortLineV2

    present = {pkg.package_type for pkg in stored.work_packages}
    needed = list(REQUIRED_PACKAGE_TYPES)
    for extra in extra_types:
        if extra not in needed:
            needed.append(extra)
    missing = [t for t in needed if t not in present]
    if not missing:
        return stored, 0
    role = str(computed_defaults.get("default_role") or "")
    if not role and stored.effort_lines:
        role = stored.effort_lines[0].role
    phase = str(computed_defaults.get("default_phase") or "mvp")
    component = str(computed_defaults.get("default_component") or "Other")
    if phase not in PHASE_ORDER or phase == "future_scope":
        phase = "mvp"
    existing_ids = [p.id for p in stored.work_packages]
    added: list[StoredWorkPackageV2] = []
    extra_lines = list(stored.effort_lines)
    for ptype in missing:
        pid = next_work_package_id(existing_ids + [a.id for a in added])
        added.append(
            StoredWorkPackageV2(
                id=pid,
                package_type=ptype,  # type: ignore[arg-type]
                title=DEFAULT_PACKAGE_TITLES.get(ptype, ptype.replace("_", " ").title()),
                description="Default allowance; required package was missing from the model output.",
                phase=phase,  # type: ignore[arg-type]
                component=component,
                confidence="medium",
                ai_leverage="none",
                lead_time_weeks=0,
                default_allowance=True,
                confidence_raw="medium",
                ai_leverage_raw="none",
                guardrail_codes=["default_allowance"],
            )
        )
        extra_lines.append(
            EffortLineV2(
                item_id=pid,
                role=role or "Developer",
                task="other",
                best_hours=0,
                likely_hours=0,
                worst_hours=0,
            )
        )
    updated = stored.model_copy(
        update={
            "work_packages": [*stored.work_packages, *added],
            "effort_lines": extra_lines,
        }
    )
    return updated, len(added)


def recover_empty_effort(
    stored: EstimateV2Stored,
    estimated_role_names: tuple[str, ...] = (),
) -> tuple[EstimateV2Stored, int]:
    """When every model hour line was dropped, keep required default allowances."""
    if any(
        line.likely_hours > 0 or line.best_hours > 0 or line.worst_hours > 0
        for line in stored.effort_lines
    ):
        return stored, 0

    default_role = ""
    if estimated_role_names:
        default_role = estimated_role_names[0]
    elif stored.effort_lines:
        default_role = stored.effort_lines[0].role
    computed_defaults = {
        "default_role": default_role or "Developer",
        "default_phase": "mvp",
        "default_component": stored.components[0].name if stored.components else "Other",
    }
    marked = 0
    pkgs: list[StoredWorkPackageV2] = []
    for pkg in stored.work_packages:
        if pkg.package_type in REQUIRED_PACKAGE_TYPES and not pkg.default_allowance:
            pkgs.append(
                pkg.model_copy(
                    update={
                        "default_allowance": True,
                        "guardrail_codes": [*pkg.guardrail_codes, "default_allowance"],
                    }
                )
            )
            marked += 1
        else:
            pkgs.append(pkg)
    updated = stored.model_copy(update={"work_packages": pkgs})
    updated, added = ensure_required_packages(updated, computed_defaults)
    return updated, marked + added

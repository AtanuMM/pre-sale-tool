"""Client-safe context for Sprint Plan prompts."""

from __future__ import annotations

from typing import Any

from app.steps.client_safe import assert_client_safe
from app.steps.schemas.estimate import PHASE_ORDER


def _committed_feature(item: dict[str, Any]) -> bool:
    if str(item.get("priority") or "") == "could":
        return False
    phase = str(item.get("phase") or "mvp")
    return phase != "future_scope"


def build_sprint_plan_context(
    *,
    scope: dict[str, Any],
    gap: dict[str, Any],
    feature_list: dict[str, Any],
    estimate: dict[str, Any],
    estimate_user_inputs: dict[str, Any],
    sow: dict[str, Any],
    srs: dict[str, Any],
    sprint_user_inputs: dict[str, Any],
) -> dict[str, Any]:
    gaps_out: list[dict[str, str]] = []
    for index, item in enumerate(gap.get("gaps") or [], start=1):
        if not isinstance(item, dict):
            continue
        sev = str(item.get("severity") or "")
        if sev not in ("high", "medium"):
            continue
        gaps_out.append(
            {
                "ref": f"G-{index}",
                "title": str(item.get("title") or ""),
                "question": str(item.get("clarification_question") or ""),
            }
        )

    modules: list[dict[str, str]] = []
    for mod in feature_list.get("modules") or []:
        if isinstance(mod, dict):
            modules.append({"name": str(mod.get("name") or "")})

    features_out: list[dict[str, Any]] = []
    for item in feature_list.get("features") or []:
        if not isinstance(item, dict) or not _committed_feature(item):
            continue
        features_out.append(
            {
                "id": str(item.get("id") or ""),
                "title": str(item.get("title") or ""),
                "description": str(item.get("description") or ""),
                "module": str(item.get("module") or ""),
                "priority": str(item.get("priority") or ""),
                "depends_on": item.get("depends_on_ids") or [],
                "primary_risk_domain": str(item.get("primary_risk_domain") or "none"),
                "source_requirement_ids": item.get("source_requirement_ids") or [],
            }
        )

    est_out: dict[str, Any] = {"phases": [], "components": [], "work_packages": [], "team": []}
    if estimate.get("schema_version") == 2:
        for ph in estimate.get("phases") or []:
            if isinstance(ph, dict):
                est_out["phases"].append({"phase": ph.get("phase"), "label": ph.get("label")})
        for comp in estimate.get("components") or []:
            if isinstance(comp, dict):
                est_out["components"].append({"name": comp.get("name")})
        for wp in estimate.get("work_packages") or []:
            if isinstance(wp, dict):
                est_out["work_packages"].append(
                    {
                        "id": wp.get("id"),
                        "title": wp.get("title"),
                        "package_type": wp.get("package_type"),
                        "phase": wp.get("phase"),
                        "component": wp.get("component"),
                    }
                )
        team_rows = estimate_user_inputs.get("team")
        if not isinstance(team_rows, list):
            team_rows = []
        for row in team_rows:
            if isinstance(row, dict):
                est_out["team"].append(
                    {
                        "role": row.get("role"),
                        "discipline": row.get("discipline"),
                        "mode": row.get("mode"),
                    }
                )

    sow_out: dict[str, Any] = {"milestones": [], "deliverables": []}
    narrative = sow.get("narrative") if isinstance(sow.get("narrative"), dict) else {}
    for ms in narrative.get("milestones") or []:
        if isinstance(ms, dict):
            sow_out["milestones"].append({"title": ms.get("title"), "phase": ms.get("phase")})
    assembled = sow.get("assembled") if isinstance(sow.get("assembled"), dict) else {}
    for d in assembled.get("deliverables") or []:
        if isinstance(d, dict):
            sow_out["deliverables"].append({"title": d.get("title")})

    srs_modules: dict[str, list[dict[str, str]]] = {}
    for fr in srs.get("functional_requirements") or []:
        if not isinstance(fr, dict):
            continue
        mod = str(fr.get("module") or "General")
        srs_modules.setdefault(mod, []).append(
            {"id": str(fr.get("id") or ""), "title": str(fr.get("title") or fr.get("statement") or "")[:120]}
        )

    payload = {
        "scope": {
            "executive_summary": scope.get("executive_summary") or "",
            "objectives": scope.get("objectives") or [],
            "risks": scope.get("risks") or [],
        },
        "gaps": gaps_out,
        "feature_list": {"modules": modules, "features": features_out},
        "estimate": est_out,
        "sow": sow_out,
        "srs_modules": srs_modules,
        "planning_preferences": {
            "sprint_length_weeks": sprint_user_inputs.get("sprint_length_weeks"),
            "product_owner_label": sprint_user_inputs.get("product_owner_label"),
            "notes": sprint_user_inputs.get("notes") or "",
        },
        "phase_order": list(PHASE_ORDER),
    }
    assert_client_safe(payload)
    return payload

"""Client-safe upstream projections for SOW prompts (strict allow-list)."""

from __future__ import annotations

import json
from typing import Any

from app.steps.client_safe import assert_client_safe as _assert_client_safe


def project_scope(scope: dict[str, Any]) -> dict[str, Any]:
    out = {
        "executive_summary": scope.get("executive_summary") or "",
        "objectives": scope.get("objectives") or [],
        "stakeholders_and_users": scope.get("stakeholders_and_users") or [],
        "in_scope_items": scope.get("in_scope_items") or [],
        "explicitly_out_of_scope_or_assumed": scope.get(
            "explicitly_out_of_scope_or_assumed"
        )
        or [],
        "risks": scope.get("risks") or [],
        "dependencies": scope.get("dependencies") or [],
        "assumptions": scope.get("assumptions") or [],
    }
    _assert_client_safe(out)
    return out


def project_gap(gap: dict[str, Any]) -> dict[str, Any]:
    gaps_out: list[dict[str, Any]] = []
    gaps = gap.get("gaps")
    if isinstance(gaps, list):
        for index, item in enumerate(gaps, start=1):
            if not isinstance(item, dict):
                continue
            sev = str(item.get("severity") or "")
            if sev not in ("high", "medium", "low"):
                continue
            gaps_out.append(
                {
                    "ref": f"G-{index}",
                    "title": item.get("title") or "",
                    "category": item.get("category") or "",
                    "severity": sev,
                    "description": item.get("description") or "",
                    "why_it_matters": item.get("why_it_matters") or "",
                    "clarification_question": item.get("clarification_question") or "",
                    "suggested_default_assumption": item.get(
                        "suggested_default_assumption"
                    )
                    or "",
                    "evidence": item.get("evidence") or "",
                }
            )
    questions = gap.get("client_questions")
    if not isinstance(questions, list):
        questions = []
    out = {"gaps": gaps_out, "client_questions": questions}
    _assert_client_safe(out)
    return out


def project_feature_list(content: dict[str, Any]) -> dict[str, Any]:
    modules = content.get("modules") if isinstance(content.get("modules"), list) else []
    features_out: list[dict[str, Any]] = []
    features = content.get("features")
    if isinstance(features, list):
        for item in features:
            if not isinstance(item, dict):
                continue
            fid = str(item.get("id") or "").strip()
            if not fid:
                continue
            deps = item.get("depends_on_ids")
            features_out.append(
                {
                    "id": fid,
                    "title": item.get("title") or fid,
                    "description": item.get("description") or "",
                    "priority": item.get("priority") or "must",
                    "module": item.get("module") or "",
                    "depends_on_ids": deps if isinstance(deps, list) else [],
                    "platforms": item.get("platforms") or [],
                }
            )
    out = {"modules": modules, "features": features_out}
    _assert_client_safe(out)
    return out


def project_estimate_for_prompt(
    estimate: dict[str, Any], team_user_inputs: dict[str, Any]
) -> dict[str, Any]:
    phases = []
    for p in estimate.get("phases") or []:
        if isinstance(p, dict):
            phases.append(
                {
                    "key": p.get("key"),
                    "goal": p.get("goal") or "",
                    "scope_rationale": p.get("scope_rationale") or "",
                }
            )
    components = []
    for c in estimate.get("components") or []:
        if isinstance(c, dict):
            components.append(
                {"name": c.get("name") or "", "description": c.get("description") or ""}
            )
    packages = []
    for w in estimate.get("work_packages") or []:
        if isinstance(w, dict):
            packages.append(
                {
                    "id": w.get("id") or "",
                    "title": w.get("title") or "",
                    "package_type": w.get("package_type") or "",
                    "description": w.get("description") or "",
                    "phase": w.get("phase") or "",
                    "component": w.get("component") or "",
                    "lead_time_weeks": w.get("lead_time_weeks") or 0,
                }
            )
    assumptions = []
    for a in estimate.get("assumptions_and_solutions") or []:
        if isinstance(a, dict):
            assumptions.append(
                {
                    "gap_ref": a.get("gap_ref"),
                    "topic": a.get("topic") or "",
                    "solution": a.get("solution") or "",
                    "confirm_with_client": a.get("confirm_with_client") or "",
                }
            )
    exclusions = [
        str(e) for e in (estimate.get("exclusions") or []) if isinstance(e, str)
    ]
    team = team_user_inputs.get("team")
    roles: list[dict[str, str]] = []
    if isinstance(team, list):
        for row in team:
            if isinstance(row, dict) and row.get("mode") == "estimated":
                role = str(row.get("role") or "").strip()
                if role:
                    roles.append(
                        {
                            "role": role,
                            "discipline": str(row.get("discipline") or "other"),
                        }
                    )
    feature_rows: list[dict[str, str]] = []
    for f in estimate.get("feature_estimates") or []:
        if not isinstance(f, dict):
            continue
        priority = str(f.get("priority") or "must")
        feature_rows.append(
            {
                "feature_id": str(f.get("feature_id") or ""),
                "title": str(f.get("title") or ""),
                "phase": str(f.get("phase") or ""),
                "component": str(f.get("component") or ""),
                "priority": priority,
            }
        )
    out = {
        "phases": phases,
        "components": components,
        "work_packages": packages,
        "assumptions_and_solutions": assumptions,
        "exclusions": exclusions,
        "estimated_roles": roles,
        "feature_placements": feature_rows,
    }
    _assert_client_safe(out)
    return out


def bundle_key_commit(phase: str, component: str) -> str:
    return f"commit|{phase}|{component}"


def bundle_key_optional(phase: str, component: str) -> str:
    return f"optional|{phase}|{component}"


def bundle_key_package(package_id: str) -> str:
    return f"package|{package_id}"


def build_prompt_context_json(
    *,
    scope: dict[str, Any],
    gap: dict[str, Any],
    feature_list: dict[str, Any],
    estimate: dict[str, Any],
    estimate_user_inputs: dict[str, Any],
) -> str:
    payload = {
        "scope": project_scope(scope),
        "gap": project_gap(gap),
        "features": project_feature_list(feature_list),
        "estimate": project_estimate_for_prompt(estimate, estimate_user_inputs),
    }
    return json.dumps(payload, ensure_ascii=False)


def estimated_roles_from_inputs(estimate_user_inputs: dict[str, Any]) -> list[dict[str, str]]:
    team = estimate_user_inputs.get("team")
    roles: list[dict[str, str]] = []
    if isinstance(team, list):
        for row in team:
            if isinstance(row, dict) and row.get("mode") == "estimated":
                role = str(row.get("role") or "").strip()
                if role:
                    roles.append(
                        {
                            "role": role,
                            "discipline": str(row.get("discipline") or "other"),
                        }
                    )
    return roles

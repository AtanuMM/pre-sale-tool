"""Client-safe upstream projections for FRS prompts."""

from __future__ import annotations

import json
from typing import Any

from app.steps.client_safe import assert_client_safe
from app.steps.sow_projection import project_scope
from app.steps.sprint_plan_projection import _committed_feature


def _estimate_assumptions(estimate: dict[str, Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for item in estimate.get("assumptions_and_solutions") or []:
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "assumption": str(item.get("assumption") or "")[:500],
                "solution": str(item.get("solution") or "")[:500],
                "confirm_with_client": str(item.get("confirm_with_client") or "no"),
            }
        )
    return out[:40]


def build_frs_context(
    *,
    scope: dict[str, Any],
    gap: dict[str, Any],
    feature_list: dict[str, Any],
    estimate: dict[str, Any],
    sow: dict[str, Any],
    srs: dict[str, Any],
    sprint_plan: dict[str, Any],
    frs_user_inputs: dict[str, Any],
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

    features_out: list[dict[str, Any]] = []
    for item in feature_list.get("features") or []:
        if not isinstance(item, dict) or not _committed_feature(item):
            continue
        features_out.append(
            {
                "id": str(item.get("id") or ""),
                "title": str(item.get("title") or ""),
                "description": str(item.get("description") or "")[:600],
                "module": str(item.get("module") or ""),
                "priority": str(item.get("priority") or ""),
                "phase": str(item.get("phase") or "mvp"),
            }
        )

    srs_reqs: list[dict[str, Any]] = []
    for fr in srs.get("functional_requirements") or []:
        if not isinstance(fr, dict):
            continue
        srs_reqs.append(
            {
                "id": str(fr.get("id") or ""),
                "feature_id": str(fr.get("feature_id") or ""),
                "module": str(fr.get("module") or ""),
                "title": str(fr.get("title") or ""),
                "statement": str(fr.get("statement") or "")[:800],
                "acceptance_criteria": fr.get("acceptance_criteria") or [],
            }
        )

    user_classes: list[dict[str, str]] = []
    planning_a = (srs.get("passes") or {}).get("planning_a") if isinstance(srs.get("passes"), dict) else None
    if isinstance(planning_a, dict):
        for uc in planning_a.get("user_classes") or []:
            if isinstance(uc, str) and uc.strip():
                user_classes.append({"name": uc.strip(), "description": ""})
            elif isinstance(uc, dict):
                user_classes.append(
                    {
                        "name": str(uc.get("name") or ""),
                        "description": str(uc.get("description") or "")[:400],
                    }
                )

    entities: list[dict[str, Any]] = []
    for ent in srs.get("entities") or []:
        if not isinstance(ent, dict):
            continue
        attrs = []
        for a in ent.get("attributes") or []:
            if isinstance(a, dict):
                attrs.append(
                    {
                        "name": str(a.get("name") or ""),
                        "type": str(a.get("type") or ""),
                        "required": str(a.get("required") or ""),
                    }
                )
        entities.append(
            {
                "name": str(ent.get("name") or ""),
                "module": str(ent.get("module") or ""),
                "attributes": attrs,
            }
        )

    interfaces: list[dict[str, str]] = []
    for iface in srs.get("interfaces") or []:
        if isinstance(iface, dict):
            interfaces.append(
                {
                    "name": str(iface.get("name") or ""),
                    "kind": str(iface.get("kind") or ""),
                    "description": str(iface.get("description") or "")[:400],
                }
            )

    stories: list[dict[str, str]] = []
    for st in sprint_plan.get("stories") or []:
        if not isinstance(st, dict):
            continue
        stories.append(
            {
                "id": str(st.get("id") or ""),
                "title": str(st.get("title") or ""),
                "feature_id": str(st.get("feature_id") or ""),
            }
        )

    payload = {
        "scope": project_scope(scope),
        "gaps": gaps_out,
        "features": features_out,
        "assumptions": _estimate_assumptions(estimate),
        "sow_milestones": [
            str(m.get("title") or "")
            for m in (sow.get("narrative") or {}).get("milestones") or []
            if isinstance(m, dict)
        ][:12],
        "srs_requirements": srs_reqs,
        "user_classes": user_classes,
        "entities": entities,
        "interfaces": interfaces,
        "stories": stories,
        "frs_inputs": {
            k: frs_user_inputs.get(k)
            for k in (
                "document_title",
                "detail_level",
                "date_format",
                "time_zone",
                "currency_code",
                "accessibility_target",
                "notification_channels",
            )
        },
    }
    assert_client_safe(payload)
    return payload


def build_frs_context_json(**kwargs: Any) -> str:
    return json.dumps(build_frs_context(**kwargs), ensure_ascii=False, indent=2)


def project_core_summary(context: dict[str, Any]) -> dict[str, Any]:
    scope = context.get("scope") if isinstance(context.get("scope"), dict) else {}
    return {
        "executive_summary": scope.get("executive_summary") or "",
        "objectives": scope.get("objectives") or [],
    }


def batch_features_payload(
    context: dict[str, Any],
    feature_ids: list[str],
    *,
    srs_by_feature: dict[str, list[dict[str, Any]]],
    stories_by_feature: dict[str, list[dict[str, str]]],
    entities_by_module: dict[str, list[dict[str, Any]]],
    module: str,
) -> dict[str, Any]:
    features = [
        f
        for f in context.get("features") or []
        if isinstance(f, dict) and str(f.get("id")) in feature_ids
    ]
    reqs: list[dict[str, Any]] = []
    for fid in feature_ids:
        reqs.extend(srs_by_feature.get(fid, []))
    story_rows: list[dict[str, str]] = []
    for fid in feature_ids:
        story_rows.extend(stories_by_feature.get(fid, []))
    return {
        "module": module,
        "features": features,
        "srs_requirements": reqs,
        "stories": story_rows,
        "entities": entities_by_module.get(module, []),
        "interfaces": context.get("interfaces") or [],
        "assumptions": context.get("assumptions") or [],
        "gaps": context.get("gaps") or [],
    }

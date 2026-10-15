"""Client-safe upstream projections for SRS prompts."""

from __future__ import annotations

import json
from typing import Any

from app.steps.client_safe import assert_client_safe
from app.steps.sow_projection import (
    project_estimate_for_prompt,
    project_feature_list,
    project_gap,
    project_scope,
)


def project_sow_for_srs(sow: dict[str, Any]) -> dict[str, Any]:
    narrative = sow.get("narrative") if isinstance(sow.get("narrative"), dict) else {}
    assembled = sow.get("assembled") if isinstance(sow.get("assembled"), dict) else {}
    bundles = []
    for b in assembled.get("scope_bundles") or []:
        if not isinstance(b, dict):
            continue
        bundles.append(
            {
                "bundle_key": b.get("bundle_key") or "",
                "kind": b.get("kind") or "",
                "title": b.get("title") or "",
                "feature_ids": b.get("feature_ids") or [],
                "feature_titles": b.get("feature_titles") or [],
            }
        )
    timeline = []
    for row in assembled.get("timeline_table") or []:
        if isinstance(row, dict):
            timeline.append(
                {
                    "phase": row.get("phase") or "",
                    "planned_weeks": row.get("planned_weeks") or 0,
                }
            )
    commercials = assembled.get("commercials") if isinstance(assembled.get("commercials"), dict) else {}
    out = {
        "narrative": {
            "purpose": narrative.get("purpose") or "",
            "background": narrative.get("background") or "",
            "objectives": narrative.get("objectives") or [],
            "scope_overview": narrative.get("scope_overview") or "",
            "phase_descriptions": narrative.get("phase_descriptions") or [],
            "out_of_scope": narrative.get("out_of_scope") or [],
            "approach": narrative.get("approach") or "",
            "quality_approach": narrative.get("quality_approach") or "",
            "assumptions": narrative.get("assumptions") or [],
            "constraints_and_dependencies": narrative.get("constraints_and_dependencies") or [],
            "glossary": narrative.get("glossary") or [],
        },
        "assembled": {
            "bundle_keys": assembled.get("bundle_keys") or [],
            "scope_bundles": bundles,
            "timeline_table": timeline,
            "pricing_model_label": commercials.get("pricing_model_label") or "",
        },
    }
    assert_client_safe(out)
    return out


def build_srs_context(
    *,
    scope: dict[str, Any],
    gap: dict[str, Any],
    feature_list: dict[str, Any],
    estimate: dict[str, Any],
    estimate_user_inputs: dict[str, Any],
    sow: dict[str, Any],
    srs_user_inputs: dict[str, Any],
) -> dict[str, Any]:
    payload = {
        "scope": project_scope(scope),
        "gap": project_gap(gap),
        "features": project_feature_list(feature_list),
        "estimate": project_estimate_for_prompt(estimate, estimate_user_inputs),
        "sow": project_sow_for_srs(sow),
        "srs_parameters": srs_user_inputs,
    }
    assert_client_safe(payload)
    return payload


def build_srs_context_json(**kwargs: Any) -> str:
    return json.dumps(build_srs_context(**kwargs), ensure_ascii=False)


def project_core_summary(context: dict[str, Any]) -> dict[str, Any]:
    scope = context.get("scope") if isinstance(context.get("scope"), dict) else {}
    features = context.get("features") if isinstance(context.get("features"), dict) else {}
    sow = context.get("sow") if isinstance(context.get("sow"), dict) else {}
    sow_n = sow.get("narrative") if isinstance(sow.get("narrative"), dict) else {}
    out = {
        "executive_summary": scope.get("executive_summary") or "",
        "objectives": scope.get("objectives") or [],
        "feature_summary": features.get("summary") or "",
        "scope_overview": sow_n.get("scope_overview") or "",
    }
    assert_client_safe(out)
    return out


def architecture_summary_from_pass_a(planning_a: dict[str, Any]) -> dict[str, Any]:
    components = []
    for c in planning_a.get("components") or []:
        if isinstance(c, dict):
            components.append(
                {
                    "name": c.get("name") or "",
                    "layer": c.get("layer") or "",
                    "responsibilities": c.get("responsibilities") or "",
                }
            )
    out = {
        "architecture_style": planning_a.get("architecture_style") or "",
        "components": components,
        "deployment_environments": planning_a.get("deployment_environments") or [],
        "integrations": planning_a.get("integrations") or [],
        "data_stores": planning_a.get("data_stores") or [],
    }
    assert_client_safe(out)
    return out


def batch_features_payload(
    context: dict[str, Any],
    feature_ids: list[str],
    gap_by_ref: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    features = context.get("features") if isinstance(context.get("features"), dict) else {}
    rows = features.get("features") if isinstance(features.get("features"), list) else []
    id_set = set(feature_ids)
    out: list[dict[str, Any]] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        fid = str(item.get("id") or "")
        if fid not in id_set:
            continue
        gaps = []
        for ref in item.get("linked_gap_refs") or []:
            g = gap_by_ref.get(str(ref))
            if g:
                gaps.append(g)
        out.append(
            {
                "id": fid,
                "title": item.get("title") or "",
                "description": item.get("description") or "",
                "module": item.get("module") or "",
                "priority": item.get("priority") or "",
                "platforms": item.get("platforms") or [],
                "source_requirement_ids": item.get("source_requirement_ids") or [],
                "linked_gaps": gaps,
                "linked_assumption_refs": item.get("linked_assumption_refs") or [],
            }
        )
    assert_client_safe({"features": out})
    return out

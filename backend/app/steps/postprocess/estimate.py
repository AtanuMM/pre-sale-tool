"""Estimate post-processing: coverage, remaps, caps, then compute."""

from __future__ import annotations

import re

from pydantic import BaseModel

from app.steps.estimate_calc import compute_estimate, remap_phase
from app.steps.postprocess import PostprocessContext, PostprocessError
from app.steps.schemas.estimate import (
    PHASE_ORDER,
    PRIORITY_DEFAULT_PHASE,
    ComponentItem,
    EffortLine,
    EstimateOutput,
    EstimateRepairOutput,
    EstimateStored,
    FeatureEstimateItem,
    PhaseItem,
    StoredFeatureEstimate,
    WorkPackageItem,
)

_WP_ID_RE = re.compile(r"^W-\d+$")
_FEATURE_ID_RE = re.compile(r"^F-\d{3,}$")


def coverage_gaps(
    output: EstimateOutput, ctx: PostprocessContext
) -> tuple[list[str], list[str]]:
    seen: set[str] = set()
    for item in output.feature_estimates:
        fid = item.feature_id.strip()
        if fid in ctx.feature_ids:
            seen.add(fid)
    missing_features = [fid for fid in ctx.feature_ids if fid not in seen]
    assumed: set[str] = set()
    for row in output.assumptions_and_solutions:
        if row.gap_ref:
            assumed.add(row.gap_ref.strip().upper())
    missing_gaps = [g for g in ctx.high_medium_gap_refs if g.upper() not in assumed]
    return missing_features, missing_gaps


def merge_repair(primary: EstimateOutput, repair: EstimateRepairOutput) -> EstimateOutput:
    existing_features = {f.feature_id.strip() for f in primary.feature_estimates}
    extra_features = [
        f for f in repair.feature_estimates if f.feature_id.strip() not in existing_features
    ]
    existing_gaps = {
        (a.gap_ref or "").strip().upper()
        for a in primary.assumptions_and_solutions
        if a.gap_ref
    }
    extra_assumptions = [
        a
        for a in repair.assumptions_and_solutions
        if not a.gap_ref or a.gap_ref.strip().upper() not in existing_gaps
    ]
    existing_wp = {w.id.strip() for w in primary.work_packages}
    extra_wp = [w for w in repair.work_packages if w.id.strip() not in existing_wp]
    known_items = (
        existing_features
        | {f.feature_id.strip() for f in extra_features}
        | existing_wp
        | {w.id.strip() for w in extra_wp}
    )
    existing_lines = {(e.item_id, e.role) for e in primary.effort_lines}
    extra_lines = [
        line
        for line in repair.effort_lines
        if line.item_id in known_items and (line.item_id, line.role) not in existing_lines
    ]
    return EstimateOutput(
        summary=primary.summary,
        approach=primary.approach,
        components=primary.components,
        phases=primary.phases,
        assumptions_and_solutions=[*primary.assumptions_and_solutions, *extra_assumptions],
        exclusions=primary.exclusions,
        feature_estimates=[*primary.feature_estimates, *extra_features],
        work_packages=[*primary.work_packages, *extra_wp],
        effort_lines=[*primary.effort_lines, *extra_lines],
    )


def _default_phase_for_priority(priority: str, selected: tuple[str, ...]) -> str:
    raw = PRIORITY_DEFAULT_PHASE.get(priority, "mvp")
    return remap_phase(raw, selected)


def _canonical_components(
    declared: list[ComponentItem], used_names: list[str], notes: dict[str, int], max_n: int
) -> tuple[list[ComponentItem], dict[str, str]]:
    canonical: list[ComponentItem] = []
    by_lower: dict[str, str] = {}
    for item in declared:
        name = item.name.strip()
        if not name or name.lower() in by_lower:
            notes["components_deduplicated"] += 1
            continue
        by_lower[name.lower()] = name
        canonical.append(ComponentItem(name=name, description=item.description.strip()))
        if len(canonical) >= max_n:
            break
    mapping: dict[str, str] = {}
    other_added = False
    for raw in used_names:
        name = raw.strip() or "Other"
        known = by_lower.get(name.lower())
        if known is None:
            notes["components_unmapped"] += 1
            if "other" not in by_lower:
                extra = ComponentItem(name="Other", description="Unmapped items.")
                if len(canonical) < max_n or not canonical:
                    canonical.append(extra)
                    by_lower["other"] = "Other"
                    other_added = True
            mapping[raw] = by_lower.get("other", "Other")
        else:
            mapping[raw] = known
    if other_added:
        notes["components_other_added"] = notes.get("components_other_added", 0) + 1
    return canonical, mapping


def _topo_reverse(
    ids: list[str], depends: dict[str, tuple[str, ...]], notes: dict[str, int]
) -> list[str]:
    id_set = set(ids)
    incoming: dict[str, int] = {i: 0 for i in ids}
    edges: dict[str, list[str]] = {i: [] for i in ids}
    for fid in ids:
        for dep in depends.get(fid, ()):
            if dep not in id_set or dep == fid:
                continue
            # edge dep -> fid (fid depends on dep)
            if fid in edges[dep]:
                continue
            edges[dep].append(fid)
            incoming[fid] += 1
    queue = [i for i in ids if incoming[i] == 0]
    order: list[str] = []
    while queue:
        node = queue.pop(0)
        order.append(node)
        for nxt in edges[node]:
            incoming[nxt] -= 1
            if incoming[nxt] == 0:
                queue.append(nxt)
    if len(order) != len(ids):
        notes["dep_cycles_skipped"] += 1
        leftover = [i for i in ids if i not in order]
        order.extend(leftover)
    order.reverse()
    return order


def postprocess_estimate(
    output: BaseModel, ctx: PostprocessContext
) -> tuple[BaseModel, dict[str, int]]:
    if not isinstance(output, EstimateOutput):
        raise PostprocessError("unexpected output type for estimate")

    notes: dict[str, int] = {
        "features_unknown_dropped": 0,
        "features_deduplicated": 0,
        "features_not_estimated": 0,
        "gaps_without_assumption": 0,
        "phases_remapped": 0,
        "deps_pulled_forward": 0,
        "dep_cycles_skipped": 0,
        "components_deduplicated": 0,
        "components_unmapped": 0,
        "components_other_added": 0,
        "roles_dropped": 0,
        "work_packages_dropped": 0,
        "effort_lines_trimmed": 0,
        "assumptions_trimmed": 0,
        "exclusions_trimmed": 0,
    }

    selected = ctx.selected_phases or ("mvp", "phase_1", "phase_2", "future_scope")
    estimated_roles = {r.casefold(): r for r in ctx.estimated_role_names}

    seen_ids: set[str] = set()
    kept_features: list[FeatureEstimateItem] = []
    for item in output.feature_estimates:
        fid = item.feature_id.strip()
        if fid not in ctx.feature_ids:
            notes["features_unknown_dropped"] += 1
            continue
        if fid in seen_ids:
            notes["features_deduplicated"] += 1
            continue
        seen_ids.add(fid)
        phase = remap_phase(item.phase, selected)
        if phase != item.phase:
            notes["phases_remapped"] += 1
        kept_features.append(item.model_copy(update={"feature_id": fid, "phase": phase}))

    missing = [fid for fid in ctx.feature_ids if fid not in seen_ids]
    for fid in missing:
        notes["features_not_estimated"] += 1
        phase = _default_phase_for_priority(ctx.feature_priorities.get(fid, "must"), selected)
        kept_features.append(
            FeatureEstimateItem(
                feature_id=fid,
                phase=phase,  # type: ignore[arg-type]
                component="Other",
                confidence="low",
                ai_leverage="low",
                complexity="M",
                basis="Not estimated; added after coverage check.",
            )
        )

    assumed_gaps = {
        (a.gap_ref or "").strip().upper()
        for a in output.assumptions_and_solutions
        if a.gap_ref
    }
    for gap in ctx.high_medium_gap_refs:
        if gap.upper() not in assumed_gaps:
            notes["gaps_without_assumption"] += 1

    # Pull-forward dependencies
    by_id = {f.feature_id: f for f in kept_features}
    order = _topo_reverse(list(by_id), ctx.feature_depends, notes)
    for fid in order:
        feature = by_id[fid]
        f_idx = PHASE_ORDER.index(feature.phase) if feature.phase in PHASE_ORDER else 0
        for dep in ctx.feature_depends.get(fid, ()):
            parent = by_id.get(dep)
            if parent is None:
                continue
            p_idx = PHASE_ORDER.index(parent.phase) if parent.phase in PHASE_ORDER else 0
            if p_idx > f_idx:
                by_id[dep] = parent.model_copy(update={"phase": feature.phase})
                notes["deps_pulled_forward"] += 1

    kept_features = [by_id[f.feature_id] for f in kept_features]

    used_component_names = [f.component for f in kept_features] + [
        w.component for w in output.work_packages
    ]
    components, comp_map = _canonical_components(
        output.components, used_component_names, notes, ctx.max_components
    )

    stored_features: list[StoredFeatureEstimate] = []
    not_estimated_ids: set[str] = {fid for fid in missing}
    for item in kept_features:
        component = comp_map.get(item.component, "Other")
        payload = item.model_dump()
        payload["component"] = component
        payload["title"] = ctx.feature_titles.get(item.feature_id, item.feature_id)
        payload["not_estimated"] = item.feature_id in not_estimated_ids
        stored_features.append(StoredFeatureEstimate.model_validate(payload))

    seen_wp: set[str] = set()
    work_packages: list[WorkPackageItem] = []
    for pkg in output.work_packages:
        pid = pkg.id.strip()
        if not _WP_ID_RE.match(pid) or pid in seen_wp:
            notes["work_packages_dropped"] += 1
            continue
        seen_wp.add(pid)
        phase = remap_phase(pkg.phase, selected)
        if phase != pkg.phase:
            notes["phases_remapped"] += 1
        component = comp_map.get(pkg.component, "Other")
        work_packages.append(
            pkg.model_copy(update={"id": pid, "phase": phase, "component": component})
        )
        if len(work_packages) >= ctx.max_work_packages:
            extra = len(output.work_packages) - len(work_packages)
            if extra > 0:
                notes["work_packages_dropped"] += extra
            break

    known_items = {f.feature_id for f in stored_features} | {w.id for w in work_packages}
    effort_lines: list[EffortLine] = []
    seen_lines: set[tuple[str, str]] = set()
    for line in output.effort_lines:
        role_key = line.role.strip()
        canonical_role = estimated_roles.get(role_key.casefold())
        if canonical_role is None:
            notes["roles_dropped"] += 1
            continue
        item_id = line.item_id.strip()
        if item_id not in known_items:
            notes["roles_dropped"] += 1
            continue
        key = (item_id, canonical_role)
        if key in seen_lines:
            continue
        seen_lines.add(key)
        effort_lines.append(
            EffortLine(item_id=item_id, role=canonical_role, base_hours=line.base_hours)
        )
        if len(effort_lines) >= ctx.max_effort_lines:
            notes["effort_lines_trimmed"] = max(
                0, len(output.effort_lines) - len(effort_lines)
            )
            break

    if not effort_lines:
        raise PostprocessError("no valid effort lines")

    assumptions = list(output.assumptions_and_solutions[: ctx.max_assumptions])
    if len(output.assumptions_and_solutions) > ctx.max_assumptions:
        notes["assumptions_trimmed"] = (
            len(output.assumptions_and_solutions) - ctx.max_assumptions
        )

    exclusions = [e.strip() for e in output.exclusions if isinstance(e, str) and e.strip()]
    if len(exclusions) > 40:
        notes["exclusions_trimmed"] = len(exclusions) - 40
        exclusions = exclusions[:40]

    # Keep one phase row per selected phase plus any remapped-to keys present
    used_phases = {f.phase for f in stored_features} | {w.phase for w in work_packages}
    phase_by_key = {}
    for phase in output.phases:
        key = remap_phase(phase.key, selected)
        if key not in phase_by_key:
            phase_by_key[key] = PhaseItem(
                key=key,  # type: ignore[arg-type]
                goal=phase.goal,
                scope_rationale=phase.scope_rationale,
            )
    for key in (*selected, *used_phases):
        if key not in phase_by_key:
            phase_by_key[key] = PhaseItem(
                key=key,  # type: ignore[arg-type]
                goal="",
                scope_rationale="",
            )
    phases = [phase_by_key[k] for k in PHASE_ORDER if k in phase_by_key]

    stored = EstimateStored(
        summary=output.summary,
        approach=output.approach,
        components=components,
        phases=phases,
        assumptions_and_solutions=assumptions,
        exclusions=exclusions,
        feature_estimates=stored_features,
        work_packages=work_packages,
        effort_lines=effort_lines,
        computed={},
    )
    computed = compute_estimate(stored, ctx.user_inputs)
    warnings: list[dict[str, str | int]] = []
    warning_map = [
        ("features_not_estimated", "Features not estimated"),
        ("gaps_without_assumption", "High/medium gaps without an explicit assumption"),
        ("phases_remapped", "Items remapped to a selected phase"),
        ("roles_dropped", "Effort lines dropped (unknown role or item)"),
        ("components_unmapped", "Components assigned to Other"),
        ("deps_pulled_forward", "Dependencies pulled forward to an earlier phase"),
    ]
    for code, label in warning_map:
        count = notes.get(code, 0)
        if count:
            warnings.append({"code": code, "count": count, "label": label})
    computed["warnings"] = warnings
    stored = stored.model_copy(update={"computed": computed})
    return stored, notes

"""Estimate v2 post-processing: coverage, remaps, guardrails, packages, then compute."""

from __future__ import annotations

import re
from typing import get_args

from pydantic import BaseModel, ValidationError

from app.steps.estimate_calc import remap_phase
from app.steps.estimate_calc_v2 import (
    apply_confidence_guardrails,
    apply_leverage_guardrails,
    compute_estimate_v2,
    domain_experience,
    ensure_required_packages,
    recover_empty_effort,
    sanitize_hours,
)
from app.steps.postprocess import PostprocessContext, PostprocessError
from app.steps.postprocess.estimate import (
    _canonical_components,
    _default_phase_for_priority,
    _topo_reverse,
)
from app.steps.schemas.estimate import PHASE_ORDER, ComponentItem
from app.steps.schemas.estimate_v2 import (
    AddedItemV2,
    ComponentItemV2,
    EffortLineV2,
    EstimateRepairPackagesOutput,
    EstimateV2Merged,
    EstimateV2Stored,
    FeatureEstimateItemV2,
    PhaseItemV2,
    StoredAddedItemV2,
    StoredFeatureEstimateV2,
    StoredWorkPackageV2,
)
from app.steps.schemas.feature_list import PrimaryRiskDomain

_WP_ID_RE = re.compile(r"^W-\d+$")
_ADDED_ID_RE = re.compile(r"^X-\d+$")
_FEATURE_ID_LOOSE_RE = re.compile(r"^F-?(\d+)$", re.IGNORECASE)
_VALID_RISKS = frozenset(get_args(PrimaryRiskDomain))


def _safe_risk(raw: str | None) -> str:
    value = (raw or "none").strip() or "none"
    return value if value in _VALID_RISKS else "none"


def _match_estimated_role(raw: str, estimated_roles: dict[str, str]) -> str | None:
    key = raw.strip().casefold()
    if not key:
        return None
    if key in estimated_roles:
        return estimated_roles[key]
    raw_tokens = [t for t in re.split(r"[\s/&\-]+", key) if t]
    for canon_key, canon in estimated_roles.items():
        canon_tokens = [t for t in re.split(r"[\s/&\-]+", canon_key) if t]
        if any(token in canon_tokens for token in raw_tokens):
            return canon
        if len(key) >= 3 and (key in canon_key or canon_key in key):
            return canon
        for token in raw_tokens:
            if len(token) < 3:
                continue
            if any(
                len(ct) >= 3 and (ct.startswith(token) or token.startswith(ct))
                for ct in canon_tokens
            ):
                return canon
    return None


def _canonical_item_id(raw: str, known_items: set[str]) -> str | None:
    item_id = raw.strip()
    if item_id in known_items:
        return item_id
    match = _FEATURE_ID_LOOSE_RE.match(item_id)
    if match is None:
        return None
    number = int(match.group(1))
    for candidate in (f"F-{number:03d}", f"F-{number:04d}", f"F-{number}"):
        if candidate in known_items:
            return candidate
    return None


def coverage_gaps_v2(
    output: EstimateV2Merged, ctx: PostprocessContext
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


def merge_batch(primary: EstimateV2Merged, batch: EstimateV2Merged | None) -> EstimateV2Merged:
    if batch is None:
        return primary
    existing_features = {f.feature_id.strip() for f in primary.feature_estimates}
    extra_features = [
        f for f in batch.feature_estimates if f.feature_id.strip() not in existing_features
    ]
    existing_added = {a.id.strip() for a in primary.added_items}
    extra_added = [a for a in batch.added_items if a.id.strip() not in existing_added]
    existing_wp = {w.id.strip() for w in primary.work_packages}
    extra_wp = [w for w in batch.work_packages if w.id.strip() not in existing_wp]
    existing_lines = {(e.item_id, e.role, e.task) for e in primary.effort_lines}
    extra_lines = [
        line
        for line in batch.effort_lines
        if (line.item_id, line.role, line.task) not in existing_lines
    ]
    return EstimateV2Merged(
        summary=primary.summary,
        approach=primary.approach,
        components=primary.components or batch.components,
        phases=primary.phases or batch.phases,
        assumptions_and_solutions=primary.assumptions_and_solutions,
        exclusions=primary.exclusions,
        feature_estimates=[*primary.feature_estimates, *extra_features],
        added_items=[*primary.added_items, *extra_added],
        work_packages=[*primary.work_packages, *extra_wp],
        effort_lines=[*primary.effort_lines, *extra_lines],
    )


def merge_package_repair(
    primary: EstimateV2Merged, repair: EstimateRepairPackagesOutput
) -> EstimateV2Merged:
    existing_wp = {w.id.strip() for w in primary.work_packages}
    extra_wp = [w for w in repair.work_packages if w.id.strip() not in existing_wp]
    existing_types = {w.package_type for w in primary.work_packages}
    extra_wp = [w for w in extra_wp if w.package_type not in existing_types]
    existing_lines = {(e.item_id, e.role, e.task) for e in primary.effort_lines}
    extra_lines = [
        line
        for line in repair.effort_lines
        if (line.item_id, line.role, line.task) not in existing_lines
    ]
    return primary.model_copy(
        update={
            "work_packages": [*primary.work_packages, *extra_wp],
            "effort_lines": [*primary.effort_lines, *extra_lines],
        }
    )


def missing_required_package_types(output: EstimateV2Merged) -> list[str]:
    from app.steps.schemas.estimate_v2 import REQUIRED_PACKAGE_TYPES

    present = {w.package_type for w in output.work_packages}
    return [t for t in REQUIRED_PACKAGE_TYPES if t not in present]


def _highest_gap_severity(refs: tuple[str, ...], severities: dict[str, str]) -> str | None:
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


def postprocess_estimate_v2(
    output: BaseModel, ctx: PostprocessContext
) -> tuple[BaseModel, dict[str, int]]:
    if not isinstance(output, EstimateV2Merged):
        raise PostprocessError("unexpected output type for estimate v2")

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
        "added_items_dropped": 0,
        "effort_lines_trimmed": 0,
        "assumptions_trimmed": 0,
        "exclusions_trimmed": 0,
        "hours_sanitised": 0,
        "confidence_guardrails": 0,
        "default_packages_added": 0,
        "stabilization_floored": 0,
        "effort_lines_empty": 0,
        "roles_fuzzy_matched": 0,
    }

    selected = ctx.selected_phases or ("mvp", "phase_1", "phase_2", "future_scope")
    estimated_roles = {r.casefold(): r for r in ctx.estimated_role_names}
    domain_exp = domain_experience(ctx.user_inputs)

    seen_ids: set[str] = set()
    kept_features: list[FeatureEstimateItemV2] = []
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
        risk = _safe_risk(ctx.feature_risk_domains.get(fid) or item.primary_risk_domain)
        kept_features.append(
            item.model_copy(update={"feature_id": fid, "phase": phase, "primary_risk_domain": risk})
        )

    missing = [fid for fid in ctx.feature_ids if fid not in seen_ids]
    for fid in missing:
        notes["features_not_estimated"] += 1
        phase = _default_phase_for_priority(ctx.feature_priorities.get(fid, "must"), selected)
        kept_features.append(
            FeatureEstimateItemV2(
                feature_id=fid,
                phase=phase,  # type: ignore[arg-type]
                component="Other",
                confidence="low",
                confidence_reason="Not estimated; added after coverage check.",
                ai_leverage="none",
                complexity="M",
                basis="assumed_not_in_source",
                primary_risk_domain=_safe_risk(ctx.feature_risk_domains.get(fid)),  # type: ignore[arg-type]
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

    seen_added: set[str] = set()
    kept_added: list[AddedItemV2] = []
    for item in output.added_items:
        pid = item.id.strip()
        if not _ADDED_ID_RE.match(pid) or pid in seen_added:
            notes["added_items_dropped"] += 1
            continue
        seen_added.add(pid)
        phase = remap_phase(item.phase, selected)
        if phase != item.phase:
            notes["phases_remapped"] += 1
        kept_added.append(item.model_copy(update={"id": pid, "phase": phase}))

    used_component_names = (
        [f.component for f in kept_features]
        + [a.component for a in kept_added]
        + [w.component for w in output.work_packages]
    )
    components, comp_map = _canonical_components(
        [ComponentItem(name=c.name, description=c.description) for c in output.components],
        used_component_names,
        notes,
        ctx.max_components,
    )
    # _canonical_components returns v1 ComponentItem; rebuild v2 with screens.
    screens_by_name = {
        c.name.strip().lower(): int(getattr(c, "screens", 1) or 1) for c in output.components
    }
    components_v2: list[ComponentItemV2] = []
    for c in components:
        screens = screens_by_name.get(c.name.strip().lower(), 1)
        components_v2.append(
            ComponentItemV2(name=c.name, description=c.description, screens=max(0, screens))
        )

    stored_features: list[StoredFeatureEstimateV2] = []
    not_estimated_ids: set[str] = set(missing)
    for item in kept_features:
        component = comp_map.get(item.component, "Other")
        risk = _safe_risk(item.primary_risk_domain)
        gap_sev = _highest_gap_severity(
            ctx.feature_gap_refs.get(item.feature_id, ()), ctx.gap_severities
        )
        conf, codes = apply_confidence_guardrails(
            item.confidence,
            domain_exp=domain_exp,
            gap_severity=gap_sev,
            risk_domain=risk,
        )
        if codes:
            notes["confidence_guardrails"] += 1
        leverage = apply_leverage_guardrails(
            item.ai_leverage, risk_domain=risk, discipline="development"
        )
        stored_features.append(
            StoredFeatureEstimateV2(
                feature_id=item.feature_id,
                phase=item.phase,
                component=component,
                confidence=conf,  # type: ignore[arg-type]
                confidence_reason=item.confidence_reason,
                ai_leverage=leverage,  # type: ignore[arg-type]
                complexity=item.complexity,
                basis=item.basis,
                primary_risk_domain=risk,  # type: ignore[arg-type]
                title=ctx.feature_titles.get(item.feature_id, item.feature_id),
                not_estimated=item.feature_id in not_estimated_ids,
                priority=ctx.feature_priorities.get(item.feature_id, "must"),
                origin=ctx.feature_origins.get(item.feature_id, "stated"),
                confidence_raw=item.confidence,
                ai_leverage_raw=item.ai_leverage,
                guardrail_codes=codes,
            )
        )

    stored_added: list[StoredAddedItemV2] = []
    for item in kept_added:
        component = comp_map.get(item.component, "Other")
        risk = _safe_risk(item.primary_risk_domain)
        conf, codes = apply_confidence_guardrails(
            item.confidence,
            domain_exp=domain_exp,
            gap_severity=None,
            risk_domain=risk,
        )
        leverage = apply_leverage_guardrails(
            item.ai_leverage, risk_domain=risk, discipline="development"
        )
        stored_added.append(
            StoredAddedItemV2(
                id=item.id,
                title=item.title,
                description=item.description,
                phase=item.phase,
                component=component,
                confidence=conf,  # type: ignore[arg-type]
                confidence_reason=item.confidence_reason,
                ai_leverage=leverage,  # type: ignore[arg-type]
                complexity=item.complexity,
                primary_risk_domain=risk,  # type: ignore[arg-type]
                reason=item.reason,
                confidence_raw=item.confidence,
                ai_leverage_raw=item.ai_leverage,
                guardrail_codes=codes,
            )
        )

    seen_wp: set[str] = set()
    seen_types: set[str] = set()
    work_packages: list[StoredWorkPackageV2] = []
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
        ptype = pkg.package_type
        if ptype in seen_types and ptype != "other":
            notes["work_packages_dropped"] += 1
            continue
        seen_types.add(ptype)
        conf, codes = apply_confidence_guardrails(
            pkg.confidence,
            domain_exp=domain_exp,
            gap_severity=None,
            risk_domain="none",
        )
        leverage = apply_leverage_guardrails(
            pkg.ai_leverage, risk_domain="none", discipline="development"
        )
        work_packages.append(
            StoredWorkPackageV2(
                id=pid,
                package_type=ptype,
                title=pkg.title,
                description=pkg.description,
                phase=phase,  # type: ignore[arg-type]
                component=component,
                confidence=conf,  # type: ignore[arg-type]
                ai_leverage=leverage,  # type: ignore[arg-type]
                lead_time_weeks=max(0.0, float(pkg.lead_time_weeks or 0)),
                default_allowance=False,
                confidence_raw=pkg.confidence,
                ai_leverage_raw=pkg.ai_leverage,
                guardrail_codes=codes,
            )
        )
        if len(work_packages) >= ctx.max_work_packages:
            extra = len(output.work_packages) - len(work_packages)
            if extra > 0:
                notes["work_packages_dropped"] += extra
            break

    known_items = (
        {f.feature_id for f in stored_features}
        | {a.id for a in stored_added}
        | {w.id for w in work_packages}
    )
    effort_lines: list[EffortLineV2] = []
    seen_lines: set[tuple[str, str, str]] = set()
    for line in output.effort_lines:
        role_key = line.role.strip()
        canonical_role = _match_estimated_role(role_key, estimated_roles)
        if canonical_role is None:
            notes["roles_dropped"] += 1
            continue
        if canonical_role.casefold() != role_key.casefold():
            notes["roles_fuzzy_matched"] += 1
        item_id = _canonical_item_id(line.item_id, known_items)
        if item_id is None:
            notes["roles_dropped"] += 1
            continue
        best, likely, worst = sanitize_hours(
            float(line.best_hours), float(line.likely_hours), float(line.worst_hours)
        )
        if (best, likely, worst) != (
            round(float(line.best_hours) * 2) / 2,
            round(float(line.likely_hours) * 2) / 2,
            round(float(line.worst_hours) * 2) / 2,
        ):
            notes["hours_sanitised"] += 1
        if likely <= 0 and best <= 0 and worst <= 0:
            continue
        key = (item_id, canonical_role, line.task)
        if key in seen_lines:
            continue
        seen_lines.add(key)
        effort_lines.append(
            EffortLineV2(
                item_id=item_id,
                role=canonical_role,
                task=line.task,
                best_hours=best,
                likely_hours=likely,
                worst_hours=worst,
            )
        )
        if len(effort_lines) >= ctx.max_effort_lines:
            notes["effort_lines_trimmed"] = max(0, len(output.effort_lines) - len(effort_lines))
            break

    if not effort_lines:
        notes["effort_lines_empty"] = 1

    assumptions = list(output.assumptions_and_solutions[: ctx.max_assumptions])
    if len(output.assumptions_and_solutions) > ctx.max_assumptions:
        notes["assumptions_trimmed"] = (
            len(output.assumptions_and_solutions) - ctx.max_assumptions
        )

    exclusions = [e.strip() for e in output.exclusions if isinstance(e, str) and e.strip()]
    if len(exclusions) > 40:
        notes["exclusions_trimmed"] = len(exclusions) - 40
        exclusions = exclusions[:40]

    used_phases = (
        {f.phase for f in stored_features}
        | {a.phase for a in stored_added}
        | {w.phase for w in work_packages}
    )
    phase_by_key: dict[str, PhaseItemV2] = {}
    for phase in output.phases:
        key = remap_phase(phase.key, selected)
        if key not in phase_by_key:
            phase_by_key[key] = PhaseItemV2(
                key=key,  # type: ignore[arg-type]
                goal=phase.goal,
                scope_rationale=phase.scope_rationale,
            )
    for key in (*selected, *used_phases):
        if key not in phase_by_key:
            phase_by_key[key] = PhaseItemV2(
                key=key,  # type: ignore[arg-type]
                goal="",
                scope_rationale="",
            )
    phases = [phase_by_key[k] for k in PHASE_ORDER if k in phase_by_key]

    try:
        stored = EstimateV2Stored(
            schema_version=2,
            summary=output.summary,
            approach=output.approach,
            components=components_v2,
            phases=phases,
            assumptions_and_solutions=assumptions,
            exclusions=exclusions,
            feature_estimates=stored_features,
            added_items=stored_added,
            work_packages=work_packages,
            effort_lines=effort_lines,
            computed={},
        )
        computed = compute_estimate_v2(
            stored,
            ctx.user_inputs,
            gap_severities=ctx.gap_severities,
            feature_gap_refs=ctx.feature_gap_refs,
            implied_count=ctx.implied_count,
            suggested_count=ctx.suggested_count,
            source_requirements_total=ctx.source_requirements_total,
        )
        stored, added_defaults = ensure_required_packages(stored, computed)
        stored, recovered = recover_empty_effort(stored, ctx.estimated_role_names)
        notes["default_packages_added"] += added_defaults + recovered
        if added_defaults or recovered:
            computed = compute_estimate_v2(
                stored,
                ctx.user_inputs,
                gap_severities=ctx.gap_severities,
                feature_gap_refs=ctx.feature_gap_refs,
                implied_count=ctx.implied_count,
                suggested_count=ctx.suggested_count,
                source_requirements_total=ctx.source_requirements_total,
            )
    except ValidationError as exc:
        raise PostprocessError("estimate output failed validation") from exc

    warning_map = [
        ("features_not_estimated", "Features not estimated"),
        ("gaps_without_assumption", "High/medium gaps without an explicit assumption"),
        ("phases_remapped", "Items remapped to a selected phase"),
        ("roles_dropped", "Effort lines dropped (unknown role or item)"),
        ("components_unmapped", "Components assigned to Other"),
        ("deps_pulled_forward", "Dependencies pulled forward to an earlier phase"),
        ("default_packages_added", "Required packages filled as default allowances"),
        ("confidence_guardrails", "Confidence lowered by guardrails"),
        ("effort_lines_empty", "Model returned no usable task hours; default allowances applied"),
        ("roles_fuzzy_matched", "Effort roles matched by name fragment"),
    ]
    extra_warnings: list[dict[str, str | int]] = []
    for code, label in warning_map:
        count = notes.get(code, 0)
        if count:
            extra_warnings.append({"code": code, "count": count, "label": label})
    existing = computed.get("warnings") if isinstance(computed.get("warnings"), list) else []
    computed = {**computed, "warnings": [*existing, *extra_warnings]}
    stored = stored.model_copy(update={"computed": computed})
    return stored, notes


def recompute_estimate_v2(
    stored: EstimateV2Stored, ctx: PostprocessContext
) -> tuple[EstimateV2Stored, dict[str, int]]:
    """Team-only path: reuse stored model JSON and recompute hours."""
    notes = {"team_recompute": 1, "default_packages_added": 0}
    computed = compute_estimate_v2(
        stored,
        ctx.user_inputs,
        gap_severities=ctx.gap_severities,
        feature_gap_refs=ctx.feature_gap_refs,
        implied_count=ctx.implied_count,
        suggested_count=ctx.suggested_count,
        source_requirements_total=ctx.source_requirements_total,
    )
    stored2, added = ensure_required_packages(stored, computed)
    if added:
        notes["default_packages_added"] = added
        computed = compute_estimate_v2(
            stored2,
            ctx.user_inputs,
            gap_severities=ctx.gap_severities,
            feature_gap_refs=ctx.feature_gap_refs,
            implied_count=ctx.implied_count,
            suggested_count=ctx.suggested_count,
            source_requirements_total=ctx.source_requirements_total,
        )
        stored = stored2
    stored = stored.model_copy(update={"schema_version": 2, "computed": computed})
    return stored, notes

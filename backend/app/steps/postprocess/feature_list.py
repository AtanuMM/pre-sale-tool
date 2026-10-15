"""Feature List post-processing: refs, ids, dependencies, links, trim, stats."""

from __future__ import annotations

import math
import re

from pydantic import BaseModel

from app.steps.postprocess import PostprocessContext, PostprocessError
from app.steps.refs import parse_ref
from app.steps.schemas.feature_list import (
    ORIGIN_ORDER,
    PRIORITY_ORDER,
    FeatureListOutput,
    FeatureListStats,
    FeatureListStored,
    FeatureListWarning,
    ModuleItem,
    StoredFeatureItem,
)

GAP_REF_PREFIX = "G"
ASSUMPTION_REF_PREFIX = "A"

_TRIM_MENTION_RE = re.compile(r"trim|truncat|limit|capped|cut off", re.IGNORECASE)
TRIM_NOTE = (
    "The feature list was trimmed to the configured maximum number of features; "
    "lower-priority items beyond that limit were removed."
)


def feature_id(position: int) -> str:
    return f"F-{position:03d}"


def _refs_valid(refs: list[int]) -> bool:
    return all(r >= 1 for r in refs) and len(set(refs)) == len(refs)


def _ref_mapping(refs: list[int]) -> dict[int, int]:
    """Old ref -> 1-based position, only for refs that occur exactly once."""
    counts: dict[int, int] = {}
    for r in refs:
        counts[r] = counts.get(r, 0) + 1
    return {r: idx for idx, r in enumerate(refs, start=1) if counts[r] == 1}


def _has_path(edges: dict[int, set[int]], start: int, target: int) -> bool:
    stack = [start]
    seen: set[int] = set()
    while stack:
        node = stack.pop()
        if node == target:
            return True
        if node in seen:
            continue
        seen.add(node)
        stack.extend(edges.get(node, ()))
    return False


def _resolve_dependencies(
    features: list, mapping: dict[int, int], notes: dict[str, int]
) -> list[list[int]]:
    total = len(features)
    edges: dict[int, set[int]] = {}
    resolved: list[list[int]] = []
    for position, feature in enumerate(features, start=1):
        deps: list[int] = []
        for raw in feature.depends_on_refs:
            target = mapping.get(raw)
            if target is None or target > total:
                notes["deps_dropped_unknown"] += 1
                continue
            if target == position:
                notes["deps_dropped_self"] += 1
                continue
            if target in deps:
                notes["deps_dropped_duplicate"] += 1
                continue
            if _has_path(edges, target, position):
                notes["deps_dropped_cycle"] += 1
                continue
            deps.append(target)
            edges.setdefault(position, set()).add(target)
        resolved.append(deps)
    return resolved


def _clean_linked_refs(
    values: list[str], *, prefix: str, count: int, notes: dict[str, int], note_key: str
) -> list[str]:
    cleaned: list[str] = []
    for value in values:
        parsed = parse_ref(value) if isinstance(value, str) else None
        if parsed is None or parsed[0] != prefix or not (1 <= parsed[1] <= count):
            notes[note_key] += 1
            continue
        label = f"{prefix}-{parsed[1]}"
        if label in cleaned:
            notes[note_key] += 1
            continue
        cleaned.append(label)
    return cleaned


def _reconcile_modules(
    modules: list[ModuleItem], features: list, notes: dict[str, int]
) -> tuple[list[ModuleItem], list[str]]:
    canonical: list[ModuleItem] = []
    by_lower: dict[str, str] = {}
    for module in modules:
        name = module.name.strip()
        if not name or name.lower() in by_lower:
            notes["modules_deduplicated"] += 1
            continue
        by_lower[name.lower()] = name
        canonical.append(ModuleItem(name=name, purpose=module.purpose.strip()))
    feature_modules: list[str] = []
    for feature in features:
        name = feature.module.strip() or "General"
        known = by_lower.get(name.lower())
        if known is None:
            by_lower[name.lower()] = name
            canonical.append(ModuleItem(name=name, purpose=""))
            notes["modules_added"] += 1
            known = name
        feature_modules.append(known)
    return canonical, feature_modules


def _clean_source_ids(values: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in values:
        item = raw.strip()[:80]
        if not item:
            continue
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(item)
        if len(cleaned) >= 30:
            break
    return cleaned


def _source_priority(value: str) -> str:
    text = value.strip()
    return text if text else "not specified"


def _quality_warnings(
    features: list[StoredFeatureItem],
    stats: FeatureListStats,
    source_requirements_total: int,
    notes: dict[str, int],
) -> list[FeatureListWarning]:
    warnings: list[FeatureListWarning] = []
    total = max(0, source_requirements_total)
    n = len(features)
    if total > 0 and n < 1.5 * total:
        deficit = max(1, math.ceil(1.5 * total) - n)
        notes["features_below_source_ratio"] = deficit
        warnings.append(
            FeatureListWarning(
                code="features_below_source_ratio",
                count=deficit,
                label="Features below 1.5× source requirements",
            )
        )
    else:
        notes["features_below_source_ratio"] = 0

    implied_suggested = stats.by_origin.get("implied", 0) + stats.by_origin.get(
        "suggested", 0
    )
    if implied_suggested == 0:
        notes["zero_implied_and_suggested"] = 1
        warnings.append(
            FeatureListWarning(
                code="zero_implied_and_suggested",
                count=1,
                label="No implied or suggested features",
            )
        )
    else:
        notes["zero_implied_and_suggested"] = 0

    source_could = sum(
        1 for feature in features if "could" in feature.source_priority.casefold()
    )
    if source_could > 0 and stats.by_priority.get("could", 0) == 0:
        notes["could_missing_while_source_has_could"] = source_could
        warnings.append(
            FeatureListWarning(
                code="could_missing_while_source_has_could",
                count=source_could,
                label="Source Could items missing from features",
            )
        )
    else:
        notes["could_missing_while_source_has_could"] = 0
    return warnings


def _stats(modules: list[ModuleItem], features: list[StoredFeatureItem]) -> FeatureListStats:
    by_priority = {p: 0 for p in PRIORITY_ORDER}
    by_origin = {o: 0 for o in ORIGIN_ORDER}
    by_module = {m.name: 0 for m in modules}
    for feature in features:
        by_priority[feature.priority] = by_priority.get(feature.priority, 0) + 1
        by_origin[feature.origin] = by_origin.get(feature.origin, 0) + 1
        by_module[feature.module] = by_module.get(feature.module, 0) + 1
    return FeatureListStats(by_priority=by_priority, by_origin=by_origin, by_module=by_module)


def postprocess_feature_list(
    output: BaseModel, ctx: PostprocessContext
) -> tuple[BaseModel, dict[str, int]]:
    if not isinstance(output, FeatureListOutput):
        raise PostprocessError("unexpected output type for feature_list")

    notes: dict[str, int] = {
        "refs_renumbered": 0,
        "features_trimmed": 0,
        "deps_dropped_unknown": 0,
        "deps_dropped_self": 0,
        "deps_dropped_duplicate": 0,
        "deps_dropped_cycle": 0,
        "gap_refs_dropped": 0,
        "assumption_refs_dropped": 0,
        "modules_added": 0,
        "modules_deduplicated": 0,
    }

    features = list(output.features)
    if not features:
        raise PostprocessError("no features after validation")

    original_refs = [f.ref for f in features]
    mapping = _ref_mapping(original_refs)
    if not _refs_valid(original_refs):
        notes["refs_renumbered"] = sum(
            1 for idx, r in enumerate(original_refs, start=1) if r != idx
        )

    max_features = max(1, ctx.max_features)
    coverage_notes = output.coverage_notes.strip()
    if len(features) > max_features:
        notes["features_trimmed"] = len(features) - max_features
        features = features[:max_features]
        if not _TRIM_MENTION_RE.search(coverage_notes):
            coverage_notes = f"{coverage_notes}\n\n{TRIM_NOTE}".strip()

    deps_by_position = _resolve_dependencies(features, mapping, notes)
    modules, feature_modules = _reconcile_modules(list(output.modules), features, notes)
    gap_count = ctx.ref_counts.get(GAP_REF_PREFIX, 0)
    assumption_count = ctx.ref_counts.get(ASSUMPTION_REF_PREFIX, 0)

    stored: list[StoredFeatureItem] = []
    for position, feature in enumerate(features, start=1):
        platforms: list = []
        for platform in feature.platforms:
            if platform not in platforms:
                platforms.append(platform)
        stored.append(
            StoredFeatureItem(
                ref=position,
                id=feature_id(position),
                module=feature_modules[position - 1],
                title=feature.title.strip(),
                description=feature.description.strip(),
                platforms=platforms,
                priority=feature.priority,
                origin=feature.origin,
                depends_on_refs=deps_by_position[position - 1],
                depends_on_ids=[feature_id(p) for p in deps_by_position[position - 1]],
                linked_gap_refs=_clean_linked_refs(
                    feature.linked_gap_refs,
                    prefix=GAP_REF_PREFIX,
                    count=gap_count,
                    notes=notes,
                    note_key="gap_refs_dropped",
                ),
                linked_assumption_refs=_clean_linked_refs(
                    feature.linked_assumption_refs,
                    prefix=ASSUMPTION_REF_PREFIX,
                    count=assumption_count,
                    notes=notes,
                    note_key="assumption_refs_dropped",
                ),
                source_requirement_ids=_clean_source_ids(feature.source_requirement_ids),
                source_priority=_source_priority(feature.source_priority),
                primary_risk_domain=feature.primary_risk_domain,
            )
        )

    if not stored:
        raise PostprocessError("no features after post-processing")

    stats = _stats(modules, stored)
    warnings = _quality_warnings(
        stored, stats, output.source_requirements_total, notes
    )
    result = FeatureListStored(
        summary=output.summary.strip(),
        modules=modules,
        features=stored,
        coverage_notes=coverage_notes,
        stats=stats,
        source_requirements_total=max(0, output.source_requirements_total),
        warnings=warnings,
    )
    return result, notes

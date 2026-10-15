"""SRS post-processing: ids, traceability, validation, assembly."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel

from app.documents.diagrams.spec_validate import (
    validate_er_diagram,
    validate_layered_diagram,
)
from app.steps.postprocess import PostprocessContext, PostprocessError
from app.steps.schemas.srs import (
    MANDATORY_NFR_CATEGORIES,
    DiagramSpec,
    DiagramStatusItem,
    ExternalInterfaceItem,
    FunctionalRequirementDraft,
    SrsHealthMeta,
    SrsPasses,
    SrsStored,
    StoredFunctionalRequirement,
    StoredNfrRequirement,
)
from app.steps.srs_assemble import (
    NFR_CAT_CODES,
    build_assembled,
    estimate_page_count,
    module_code,
)

_WEAK_RE = re.compile(
    r"\b(fast|user-friendly|easy|flexible|adequate|as appropriate|etc\.|and so on|TBD)\b",
    re.IGNORECASE,
)
_SHALL_RE = re.compile(r"\bshall\b", re.IGNORECASE)
_PLACEHOLDER_RE = re.compile(r"\[TBC:[^\]]+\]")
_NUMERIC_TARGET_RE = re.compile(r"\d+(?:\.\d+)?\s*(%|ms|sec|seconds|minutes|hours|users|rps|req)")


def _feature_phase(feature_id: str, estimate: dict[str, Any]) -> str:
    for row in estimate.get("feature_estimates") or []:
        if isinstance(row, dict) and str(row.get("feature_id")) == feature_id:
            phase = str(row.get("phase") or "mvp")
            if phase in ("future_scope",) or str(row.get("priority")) == "wont":
                return "Future, not part of the committed release"
            return phase.replace("_", " ")
    return "mvp"


def _merge_functional_drafts(passes: SrsPasses) -> list[FunctionalRequirementDraft]:
    drafts: list[FunctionalRequirementDraft] = []
    for batch in passes.modules.values():
        drafts.extend(batch.functional_requirements)
    if passes.coverage_repair:
        drafts.extend(passes.coverage_repair.functional_requirements)
    return drafts


def _assign_fr_ids(
    drafts: list[FunctionalRequirementDraft],
    feature_meta: dict[str, dict[str, Any]],
    estimate: dict[str, Any],
    notes: dict[str, int],
) -> list[StoredFunctionalRequirement]:
    mod_codes: dict[str, str] = {}
    used_codes: set[str] = set()
    counters: dict[str, int] = {}
    stored: list[StoredFunctionalRequirement] = []
    seen_statements: set[str] = set()

    for draft in drafts:
        mod = feature_meta.get(draft.feature_id, {}).get("module") or "General"
        if mod not in mod_codes:
            mod_codes[mod] = module_code(mod, used_codes)
        code = mod_codes[mod]
        counters[code] = counters.get(code, 0) + 1
        fr_id = f"FR-{code}-{counters[code]:03d}"

        stmt = draft.statement.strip()
        norm = stmt.casefold()
        if norm in seen_statements:
            notes["duplicates_flagged"] = notes.get("duplicates_flagged", 0) + 1
        seen_statements.add(norm)

        basis = draft.basis
        if basis == "stated" and not draft.source_ref.strip():
            basis = "proposed"
            notes["basis_downgrades"] = notes.get("basis_downgrades", 0) + 1

        proposed_target = False
        target_blob = f"{draft.statement} {draft.rationale}"
        if _NUMERIC_TARGET_RE.search(target_blob) and basis != "stated":
            proposed_target = True
            notes["proposed_targets"] = notes.get("proposed_targets", 0) + 1

        weak = bool(_WEAK_RE.search(stmt))
        missing_shall = not bool(_SHALL_RE.search(stmt))
        if weak:
            notes["weak_language"] = notes.get("weak_language", 0) + 1
        if missing_shall:
            notes["missing_shall"] = notes.get("missing_shall", 0) + 1

        meta = feature_meta.get(draft.feature_id, {})
        stored.append(
            StoredFunctionalRequirement(
                id=fr_id,
                feature_id=draft.feature_id,
                module=mod,
                title=draft.title,
                statement=stmt,
                rationale=draft.rationale,
                acceptance_criteria=list(draft.acceptance_criteria),
                basis=basis,
                source_ref=draft.source_ref,
                source_requirement_ids=list(meta.get("source_requirement_ids") or []),
                priority=str(meta.get("priority") or "must"),
                phase=_feature_phase(draft.feature_id, estimate),
                verification_method=draft.verification_method,
                proposed_target=proposed_target,
                weak_language=weak,
                missing_shall=missing_shall,
            )
        )
    return stored


def _assign_nfr_ids(
    passes: SrsPasses,
    notes: dict[str, int],
) -> list[StoredNfrRequirement]:
    items = []
    if passes.planning_b:
        items.extend(passes.planning_b.nfr_catalogue)
    if passes.coverage_repair:
        items.extend(passes.coverage_repair.nfr_items)
    counters: dict[str, int] = {}
    stored: list[StoredNfrRequirement] = []
    for item in items:
        cat = item.category
        code = NFR_CAT_CODES.get(cat, "NFR")
        counters[code] = counters.get(code, 0) + 1
        basis = item.basis
        if basis == "stated" and not item.source_ref.strip():
            basis = "proposed"
            notes["basis_downgrades"] = notes.get("basis_downgrades", 0) + 1
        proposed = bool(_NUMERIC_TARGET_RE.search(f"{item.metric} {item.target}")) and basis != "stated"
        if proposed:
            notes["proposed_targets"] = notes.get("proposed_targets", 0) + 1
        stored.append(
            StoredNfrRequirement(
                id=f"NFR-{code}-{counters[code]:02d}",
                category=cat,
                statement=item.statement,
                metric=item.metric,
                target=item.target,
                basis=basis,
                source_ref=item.source_ref,
                verification_method=item.verification_method,
                proposed_target=proposed,
            )
        )
    return stored


def _validate_diagrams(
    passes: SrsPasses,
    notes: dict[str, int],
) -> tuple[list[DiagramStatusItem], dict[str, DiagramSpec]]:
    out: list[DiagramStatusItem] = []
    specs: dict[str, DiagramSpec] = {}
    if not passes.planning_a:
        return out, specs
    pa = passes.planning_a
    mapping = {
        "context": pa.context_diagram,
        "architecture": pa.architecture_diagram,
        "deployment": pa.deployment_diagram,
        "er": pa.er_diagram,
    }
    for key, spec in mapping.items():
        result = validate_er_diagram(spec) if spec.kind == "er" else validate_layered_diagram(spec)
        status = "ok"
        warning = ""
        if not result.ok:
            notes["diagram_invalid"] = notes.get("diagram_invalid", 0) + 1
            status = "fallback_table"
            warning = ",".join(result.errors[:3])
        out.append(
            DiagramStatusItem(
                key=key,
                kind=spec.kind,
                title=spec.title,
                caption=spec.caption,
                status=status,  # type: ignore[arg-type]
                warning=warning,
            )
        )
        specs[key] = spec
    return out, specs


def _open_issues(gap: dict[str, Any], scope: dict[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    for g in gap.get("gaps") or []:
        if not isinstance(g, dict):
            continue
        if str(g.get("severity")) in ("high", "medium"):
            issues.append(
                {
                    "ref": str(g.get("ref") or ""),
                    "title": str(g.get("title") or ""),
                    "question": str(g.get("clarification_question") or ""),
                }
            )
    for a in scope.get("assumptions") or []:
        if isinstance(a, dict) and a.get("confirm_with_client"):
            issues.append(
                {
                    "ref": "assumption",
                    "title": str(a.get("statement") or "")[:80],
                    "question": "Confirm with client",
                }
            )
    return issues


def _placeholders_from_text(*blobs: str) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    for blob in blobs:
        for match in _PLACEHOLDER_RE.finditer(blob):
            found.append({"label": match.group(0), "location": "narrative"})
    return found


def postprocess_srs(
    output: BaseModel,
    ctx: PostprocessContext,
) -> tuple[BaseModel, dict[str, int]]:
    if not isinstance(output, SrsStored):
        raise PostprocessError("unexpected output type for srs")

    notes: dict[str, int] = {}
    passes = output.passes
    estimate = ctx.estimate_content or {}
    feature_list = ctx.feature_list_content or {}
    features = feature_list.get("features") if isinstance(feature_list.get("features"), list) else []
    feature_meta: dict[str, dict[str, Any]] = {}
    for f in features:
        if isinstance(f, dict):
            fid = str(f.get("id") or "")
            if fid:
                feature_meta[fid] = f

    drafts = _merge_functional_drafts(passes)
    if not drafts:
        raise PostprocessError("no functional requirements")

    covered = {d.feature_id for d in drafts}
    for fid in ctx.feature_ids:
        if fid not in covered:
            notes["features_without_requirements"] = notes.get("features_without_requirements", 0) + 1

    functional = _assign_fr_ids(drafts, feature_meta, estimate, notes)
    nfrs = _assign_nfr_ids(passes, notes)

    categories = {n.category for n in nfrs}
    for cat in MANDATORY_NFR_CATEGORIES:
        if cat not in categories:
            notes["nfr_category_gaps"] = notes.get("nfr_category_gaps", 0) + 1
    if ctx.user_inputs.get("languages") and "localisation" not in categories:
        notes["nfr_category_gaps"] = notes.get("nfr_category_gaps", 0) + 1

    interfaces: list[ExternalInterfaceItem] = []
    entities = []
    if passes.planning_b:
        interfaces = list(passes.planning_b.external_interfaces)
        entities = list(passes.planning_b.data_entities)

    diagram_meta, _ = _validate_diagrams(passes, notes)
    open_issues = _open_issues(ctx.gap_content or {}, ctx.scope_content or {})
    placeholders = _placeholders_from_text(
        passes.planning_a.overview if passes.planning_a else "",
        passes.planning_b.api_standards if passes.planning_b else "",
    )

    basis_stated = sum(1 for f in functional if f.basis == "stated")
    basis_derived = sum(1 for f in functional if f.basis == "derived")
    basis_proposed = sum(1 for f in functional if f.basis == "proposed")
    weak = sum(1 for f in functional if f.weak_language)
    missing_shall = sum(1 for f in functional if f.missing_shall)
    feat_cov = len({f.feature_id for f in functional}) / max(len(ctx.feature_ids), 1) * 100.0

    health = SrsHealthMeta(
        requirements_per_feature=len(functional) / max(len(ctx.feature_ids), 1),
        features_covered_pct=round(feat_cov, 1),
        basis_stated=basis_stated,
        basis_derived=basis_derived,
        basis_proposed=basis_proposed,
        weak_language_warnings=weak,
        missing_shall=missing_shall,
        nfr_categories_covered=len(categories),
        nfr_categories_required=len(MANDATORY_NFR_CATEGORIES),
        proposed_target_pct=round(
            100.0
            * sum(1 for f in functional if f.proposed_target)
            / max(len(functional), 1),
            1,
        ),
        placeholder_count=len(placeholders),
        approx_pages=estimate_page_count(passes, functional, nfrs),
        diagrams=diagram_meta,
    )

    assembled = build_assembled(
        project_id=ctx.project_id,
        version_no=ctx.version_no,
        user_inputs=ctx.user_inputs,
        passes=passes,
        functional=functional,
        nfrs=nfrs,
        interfaces=interfaces,
        entities=entities,
        diagram_meta=[d.model_dump() for d in diagram_meta],
        open_issues=open_issues,
        placeholders=placeholders,
        health=health,
    )

    stored = SrsStored(
        passes=passes,
        functional_requirements=functional,
        nfr_requirements=nfrs,
        interfaces=interfaces,
        entities=entities,
        assembled=assembled,
        viewer=health,
    )
    notes["functional_requirements"] = len(functional)
    notes["nfr_requirements"] = len(nfrs)
    notes["placeholders"] = len(placeholders)
    return stored, notes

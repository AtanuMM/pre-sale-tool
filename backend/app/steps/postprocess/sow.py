"""SOW post-processing: assembly, coverage, guards."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel

from app.config import get_settings
from app.steps.postprocess import PostprocessContext, PostprocessError
from app.steps.schemas.estimate import PHASE_ORDER
from app.steps.schemas.sow import (
    COMMITTED_PHASES,
    DeliverableItem,
    NumericClaimWarning,
    PlaceholderItem,
    SowNarrativeOutput,
    SowNarrativeStored,
    SowStored,
    SowViewerMeta,
    StoredDeliverableItem,
    StoredMilestoneItem,
    StoredTeamRoleItem,
)
from app.steps.sow_assemble import build_assembled

_PLACEHOLDER_RE = re.compile(r"\[TBC:[^\]]+\]")
_CURRENCY_RE = re.compile(r"[\$€£₹]\s?\d[\d,]*(?:\.\d+)?|\d[\d,]*(?:\.\d+)?\s?(?:USD|INR|EUR|GBP)", re.IGNORECASE)
_DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}\s+[A-Za-z]+\s+\d{4}\b")
_DURATION_RE = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*(weeks?|months?|days?|%|percent)\b", re.IGNORECASE
)


def merge_deliverable_repair(
    primary: SowNarrativeOutput, repair_deliverables: list[DeliverableItem]
) -> SowNarrativeOutput:
    existing = {d.bundle_key for d in primary.deliverables}
    extra = [d for d in repair_deliverables if d.bundle_key not in existing]
    return primary.model_copy(update={"deliverables": [*primary.deliverables, *extra]})


def _estimate_roles(ctx: PostprocessContext) -> set[str]:
    names: set[str] = set(ctx.estimated_role_names)
    team = ctx.estimate_user_inputs.get("team")
    if isinstance(team, list):
        for row in team:
            if isinstance(row, dict) and row.get("mode") == "estimated":
                role = str(row.get("role") or "").strip()
                if role:
                    names.add(role)
    return names


def _scan_numeric_claims(narrative: SowNarrativeStored, allowed: list[str]) -> list[NumericClaimWarning]:
    allowed_set = set(allowed)
    warnings: list[NumericClaimWarning] = []
    blob = narrative.model_dump(mode="json")

    def check_text(path: str, text: str) -> None:
        if not text:
            return
        for match in _CURRENCY_RE.finditer(text):
            snippet = match.group(0)
            if not any(num in snippet.replace(",", "") for num in allowed_set):
                warnings.append(
                    NumericClaimWarning(
                        path=path, label="Check this figure", snippet=snippet[:80]
                    )
                )
        for match in _DATE_RE.finditer(text):
            snippet = match.group(0)
            warnings.append(
                NumericClaimWarning(path=path, label="Check this figure", snippet=snippet[:80])
            )
        for match in _DURATION_RE.finditer(text):
            num = match.group(1)
            if num not in allowed_set:
                warnings.append(
                    NumericClaimWarning(
                        path=path,
                        label="Check this figure",
                        snippet=match.group(0)[:80],
                    )
                )

    def walk(obj: Any, path: str) -> None:
        if isinstance(obj, str):
            check_text(path, obj)
        elif isinstance(obj, dict):
            for k, v in obj.items():
                walk(v, f"{path}.{k}")
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                walk(v, f"{path}[{i}]")

    walk(blob, "narrative")
    return warnings


def _default_deliverable(bundle_key: str, bundles: list[Any]) -> StoredDeliverableItem:
    title = bundle_key
    for b in bundles:
        if getattr(b, "bundle_key", None) == bundle_key:
            title = getattr(b, "title", bundle_key)
            break
    return StoredDeliverableItem(
        bundle_key=bundle_key,
        title=title,
        description="See Appendix A for functionality covered in this bundle.",
        acceptance_criteria=["Functionality listed in Appendix A operates as described."],
        default_deliverable=True,
    )


def postprocess_sow(
    output: BaseModel, ctx: PostprocessContext
) -> tuple[BaseModel, dict[str, int]]:
    if not isinstance(output, SowNarrativeOutput):
        raise PostprocessError("unexpected output type for sow")

    notes: dict[str, int] = {
        "deliverables_defaulted": 0,
        "roles_added": 0,
        "milestones_added": 0,
        "milestones_dropped": 0,
        "numeric_claim_warnings": 0,
        "placeholders": 0,
        "bundle_gaps": 0,
    }
    settings = get_settings()

    estimate = ctx.estimate_content or {}
    if estimate.get("schema_version") != 2:
        raise PostprocessError("estimate must be version 2")

    assembled = build_assembled(
        project_id=ctx.project_id,
        version_no=ctx.version_no,
        status_text="In review",
        user_inputs=ctx.user_inputs,
        scope=ctx.scope_content or {},
        gap=ctx.gap_content or {},
        feature_list=ctx.feature_list_content or {},
        estimate=estimate,
        estimate_user_inputs=ctx.estimate_user_inputs,
    )

    narrative = output
    objectives = list(narrative.objectives[: settings.SOW_MAX_OBJECTIVES])
    success = list(narrative.success_criteria[: settings.SOW_MAX_SUCCESS_CRITERIA])
    glossary = list(narrative.glossary[: settings.SOW_MAX_GLOSSARY])

    expected_keys = set(assembled.bundle_keys)
    seen_del: dict[str, DeliverableItem] = {}
    for d in narrative.deliverables:
        if d.bundle_key in expected_keys and d.bundle_key not in seen_del:
            seen_del[d.bundle_key] = d
    notes["bundle_gaps"] = max(0, len(expected_keys) - len(seen_del))

    deliverables: list[StoredDeliverableItem] = []
    for key in assembled.bundle_keys:
        item = seen_del.get(key)
        if item is None:
            deliverables.append(_default_deliverable(key, assembled.scope_bundles))
            notes["deliverables_defaulted"] += 1
        else:
            deliverables.append(
                StoredDeliverableItem(
                    **item.model_dump(),
                    default_deliverable=False,
                )
            )

    if not deliverables:
        raise PostprocessError("no deliverables")

    roles_allowed = _estimate_roles(ctx)
    team_roles: list[StoredTeamRoleItem] = []
    seen_roles: set[str] = set()
    for tr in narrative.team_roles:
        if tr.role in roles_allowed and tr.role not in seen_roles:
            seen_roles.add(tr.role)
            team_roles.append(StoredTeamRoleItem(**tr.model_dump(), code_added=False))
    for role in roles_allowed:
        if role not in seen_roles:
            team_roles.append(
                StoredTeamRoleItem(
                    role=role,
                    responsibilities=["[TBC: responsibilities for this role]"],
                    code_added=True,
                )
            )
            notes["roles_added"] += 1

    valid_phases = set(PHASE_ORDER)
    milestones: list[StoredMilestoneItem] = []
    seen_phase_milestones: set[str] = set()
    for ms in narrative.milestones[: settings.SOW_MAX_MILESTONES]:
        if ms.phase not in valid_phases:
            notes["milestones_dropped"] += 1
            continue
        milestones.append(StoredMilestoneItem(**ms.model_dump(), code_added=False))
        if ms.phase in COMMITTED_PHASES:
            seen_phase_milestones.add(ms.phase)

    for phase in COMMITTED_PHASES:
        if phase not in seen_phase_milestones:
            milestones.append(
                StoredMilestoneItem(
                    name=f"{phase.replace('_', ' ').title()} complete",
                    phase=phase,  # type: ignore[arg-type]
                    description=f"Completion of committed scope for {phase.replace('_', ' ')}.",
                    completion_criteria="All deliverables for this phase are accepted.",
                    code_added=True,
                )
            )
            notes["milestones_added"] += 1

    if not any(m.name.lower().startswith("project") for m in milestones):
        milestones.append(
            StoredMilestoneItem(
                name="Project completion",
                phase="mvp",  # type: ignore[arg-type]
                description="All committed deliverables accepted and handover complete.",
                completion_criteria="Final acceptance of all committed deliverables.",
                code_added=True,
            )
        )
        notes["milestones_added"] += 1

    stored_narrative = SowNarrativeStored(
        document_title=narrative.document_title,
        purpose=narrative.purpose,
        background=narrative.background,
        objectives=objectives,
        success_criteria=success,
        scope_overview=narrative.scope_overview,
        phase_descriptions=narrative.phase_descriptions,
        out_of_scope=list(narrative.out_of_scope[: settings.SOW_MAX_OUT_OF_SCOPE]),
        deliverables=deliverables,
        approach=narrative.approach,
        quality_approach=narrative.quality_approach,
        milestones=milestones,
        team_roles=team_roles,
        client_responsibilities=list(
            narrative.client_responsibilities[: settings.SOW_MAX_CLIENT_RESPONSIBILITIES]
        ),
        assumptions=list(narrative.assumptions[: settings.SOW_MAX_ASSUMPTIONS]),
        constraints_and_dependencies=list(
            narrative.constraints_and_dependencies[: settings.SOW_MAX_CONSTRAINTS]
        ),
        risks=list(narrative.risks[: settings.SOW_MAX_RISKS]),
        glossary=glossary,
    )

    warnings = _scan_numeric_claims(stored_narrative, assembled.allowed_numbers)
    notes["numeric_claim_warnings"] = len(warnings)

    placeholder_count = len(_PLACEHOLDER_RE.findall(stored_narrative.model_dump_json()))
    placeholder_count += len(assembled.placeholders)
    notes["placeholders"] = placeholder_count

    viewer_placeholders = [
        PlaceholderItem(placeholder_id=p.placeholder_id, location=p.location, label=p.label)
        for p in assembled.placeholders
    ]

    stored = SowStored(
        narrative=stored_narrative,
        assembled=assembled,
        viewer=SowViewerMeta(
            placeholder_count=placeholder_count,
            placeholders=viewer_placeholders,
            numeric_claim_warnings=warnings,
        ),
    )
    return stored, notes


def reassemble_sow(stored: SowStored, ctx: PostprocessContext) -> tuple[SowStored, dict[str, int]]:
    """Reuse narrative; rebuild assembled from inputs/upstream."""
    notes = {"reassemble": 1}
    assembled = build_assembled(
        project_id=ctx.project_id,
        version_no=ctx.version_no,
        status_text="In review",
        user_inputs=ctx.user_inputs,
        scope=ctx.scope_content or {},
        gap=ctx.gap_content or {},
        feature_list=ctx.feature_list_content or {},
        estimate=ctx.estimate_content or {},
        estimate_user_inputs=ctx.estimate_user_inputs,
    )
    warnings = _scan_numeric_claims(stored.narrative, assembled.allowed_numbers)
    placeholder_count = len(_PLACEHOLDER_RE.findall(stored.narrative.model_dump_json()))
    placeholder_count += len(assembled.placeholders)
    updated = stored.model_copy(
        update={
            "assembled": assembled,
            "viewer": SowViewerMeta(
                placeholder_count=placeholder_count,
                placeholders=list(assembled.placeholders),
                numeric_claim_warnings=warnings,
            ),
        }
    )
    notes["numeric_claim_warnings"] = len(warnings)
    notes["placeholders"] = placeholder_count
    return updated, notes

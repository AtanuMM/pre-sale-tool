"""FRS post-processing: ids, coverage, catalogs, health."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel

from app.steps.postprocess import PostprocessContext, PostprocessError
from app.steps.schemas.frs import (
    FrsAssembled,
    FrsHealthMeta,
    FrsPasses,
    FrsStored,
    StoredFeatureSpecification,
)

_WEAK_RE = re.compile(
    r"\b(fast|user-friendly|easy|flexible|appropriate|adequate|etc\.|TBD)\b",
    re.IGNORECASE,
)
_PLACEHOLDER_RE = re.compile(r"\[TBC:[^\]]+\]")


def _committed_feature_ids(ctx: PostprocessContext) -> tuple[str, ...]:
    fl = ctx.feature_list_content or {}
    ids: list[str] = []
    for item in fl.get("features") or []:
        if not isinstance(item, dict):
            continue
        fid = str(item.get("id") or "")
        if not fid:
            continue
        if str(item.get("priority") or "") == "could":
            continue
        if str(item.get("phase") or "") == "future_scope":
            continue
        ids.append(fid)
    return tuple(ids)


def _feature_meta(ctx: PostprocessContext) -> dict[str, dict[str, Any]]:
    fl = ctx.feature_list_content or {}
    meta: dict[str, dict[str, Any]] = {}
    for item in fl.get("features") or []:
        if isinstance(item, dict) and item.get("id"):
            fid = str(item["id"])
            meta[fid] = {
                "title": str(item.get("title") or fid),
                "module": str(item.get("module") or "General"),
                "priority": str(item.get("priority") or "must"),
                "phase": str(item.get("phase") or "mvp"),
            }
    return meta


def _global_conventions(user_inputs: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    mapping = [
        ("date_format", "Date format"),
        ("time_zone", "Time zone"),
        ("currency_code", "Currency code"),
        ("min_password_length", "Minimum password length"),
        ("session_timeout_minutes", "Session timeout (minutes)"),
        ("max_upload_size_mb", "Maximum upload size (MB)"),
        ("default_page_size", "Default page size"),
        ("accessibility_target", "Accessibility target"),
    ]
    for key, label in mapping:
        val = user_inputs.get(key)
        if val is None or val == "":
            continue
        if key == "notification_channels" and isinstance(val, list):
            val = ", ".join(str(v) for v in val)
        rows.append({"parameter": label, "value": str(val), "source": "user input"})
    channels = user_inputs.get("notification_channels")
    if isinstance(channels, list) and channels:
        rows.append(
            {
                "parameter": "Notification channels",
                "value": ", ".join(str(c) for c in channels),
                "source": "user input",
            }
        )
    return rows


def _merge_drafts(passes: FrsPasses) -> list[Any]:
    drafts: list[Any] = []
    for batch in passes.modules.values():
        drafts.extend(batch.specifications)
    if passes.coverage_repair:
        drafts.extend(passes.coverage_repair.specifications)
    return drafts


def _srs_requirement_ids(srs: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for fr in srs.get("functional_requirements") or []:
        if isinstance(fr, dict) and fr.get("id"):
            ids.append(str(fr["id"]))
    return ids


def _story_map(sprint: dict[str, Any]) -> dict[str, list[tuple[str, str]]]:
    by_title: dict[str, list[tuple[str, str]]] = {}
    by_feature: dict[str, list[tuple[str, str]]] = {}
    for st in sprint.get("stories") or []:
        if not isinstance(st, dict):
            continue
        sid = str(st.get("id") or "")
        title = str(st.get("title") or "")
        fid = str(st.get("feature_id") or "")
        if title:
            by_title.setdefault(title.casefold(), []).append((sid, fid))
        if fid:
            by_feature.setdefault(fid, []).append((sid, title))
    return by_feature


def postprocess_frs(draft: BaseModel, ctx: PostprocessContext) -> tuple[BaseModel, dict[str, int]]:
    if not isinstance(draft, FrsStored):
        raise PostprocessError("unexpected FRS draft type")
    passes = draft.passes
    if passes.planning is None:
        raise PostprocessError("FRS planning pass missing")

    notes: dict[str, int] = {}
    meta = _feature_meta(ctx)
    committed = _committed_feature_ids(ctx)
    srs = getattr(ctx, "srs_content", None) or {}
    sprint = getattr(ctx, "sprint_plan_content", None) or {}
    srs_ids = _srs_requirement_ids(srs)
    story_by_feature = _story_map(sprint)

    drafts = _merge_drafts(passes)
    if not drafts:
        raise PostprocessError("no feature specifications produced")

    seen_features: set[str] = set()
    stored: list[StoredFeatureSpecification] = []
    screen_dedupe: dict[str, str] = {}
    msg_dedupe: dict[str, str] = {}
    scr_n = 0
    msg_n = 0
    br_n: dict[str, int] = {}
    fld_n: dict[str, int] = {}

    covered_srs: set[str] = set()
    weak_count = 0
    proposed_rules = 0

    for spec in drafts:
        fid = str(spec.feature_id)
        if fid in seen_features:
            notes["duplicate_feature_specs"] = notes.get("duplicate_feature_specs", 0) + 1
            continue
        seen_features.add(fid)
        fm = meta.get(fid, {"title": fid, "module": "General", "priority": "must", "phase": "mvp"})
        fs_id = f"FS-{fid}"
        flow_ids = {"main": f"FL-{fid}-M"}
        for i, _ in enumerate(spec.alternate_flows, start=1):
            flow_ids[f"alt{i}"] = f"FL-{fid}-A{i}"
        for i, _ in enumerate(spec.exception_flows, start=1):
            flow_ids[f"exc{i}"] = f"FL-{fid}-E{i}"

        mod = str(fm["module"])
        br_n.setdefault(mod, 0)

        rules_out: list[dict[str, Any]] = []
        for rule in spec.business_rules:
            br_n[mod] += 1
            basis = rule.basis
            if basis == "stated" and not rule.source_ref.strip():
                basis = "proposed"
                notes["basis_downgrades"] = notes.get("basis_downgrades", 0) + 1
            if basis == "proposed":
                proposed_rules += 1
            if _WEAK_RE.search(rule.statement):
                weak_count += 1
            rules_out.append(
                {
                    "id": f"BR-{mod[:8]}-{br_n[mod]:02d}",
                    "statement": rule.statement,
                    "basis": basis,
                    "source_ref": rule.source_ref,
                    "proposed_label": basis == "proposed",
                }
            )

        fld_n.setdefault(fid, 0)
        fields_out: list[dict[str, Any]] = []
        for field in spec.fields:
            fld_n[fid] += 1
            fields_out.append(
                {
                    "id": f"FLD-{fid}-{fld_n[fid]:02d}",
                    "name": field.name,
                    "label": field.label,
                    "type": field.field_type,
                    "required": field.required_mode,
                    "validation": field.validation,
                    "default": field.default_value,
                    "entity_ref": field.entity_ref,
                    "help_text": field.help_text,
                    "basis": field.basis,
                }
            )

        screens_out: list[dict[str, Any]] = []
        for screen in spec.screens:
            key = screen.name.casefold()
            if key not in screen_dedupe:
                scr_n += 1
                screen_dedupe[key] = f"SCR-{scr_n:02d}"
            screens_out.append(
                {
                    "id": screen_dedupe[key],
                    "name": screen.name,
                    "purpose": screen.purpose,
                    "key_components": screen.key_components,
                    "states_note": screen.states_note,
                }
            )

        messages_out: list[dict[str, Any]] = []
        for msg in spec.messages:
            dkey = f"{msg.kind}:{msg.text.casefold()}"
            if dkey not in msg_dedupe:
                msg_n += 1
                msg_dedupe[dkey] = f"MSG-{msg_n:02d}"
            messages_out.append(
                {
                    "id": msg_dedupe[dkey],
                    "kind": msg.kind,
                    "trigger": msg.trigger,
                    "text": msg.text,
                }
            )

        criteria_out: list[dict[str, Any]] = []
        for crit in spec.acceptance_criteria:
            for rid in crit.covers_requirement_ids:
                covered_srs.add(str(rid))
            criteria_out.append(
                {
                    "scenario_title": crit.scenario_title,
                    "given": crit.given,
                    "when": crit.when,
                    "then": crit.then,
                    "covers_requirement_ids": list(crit.covers_requirement_ids),
                }
            )
        for rid in spec.linked_requirement_ids:
            covered_srs.add(str(rid))

        story_ids: list[str] = []
        for title in spec.linked_story_titles:
            for sid, _ in story_by_feature.get(fid, []):
                if title.casefold() == sid.casefold():
                    story_ids.append(sid)
            for sid, stitle in story_by_feature.get(fid, []):
                if title.casefold() == stitle.casefold():
                    story_ids.append(sid)

        stored.append(
            StoredFeatureSpecification(
                id=fs_id,
                feature_id=fid,
                module=mod,
                title=str(fm["title"]),
                priority=str(fm["priority"]),
                phase=str(fm["phase"]),
                summary=spec.summary,
                actors=list(spec.actors),
                preconditions=list(spec.preconditions),
                trigger=spec.trigger,
                main_flow=[s.model_dump() for s in spec.main_flow],
                alternate_flows=[a.model_dump() for a in spec.alternate_flows],
                exception_flows=[e.model_dump() for e in spec.exception_flows],
                postconditions=list(spec.postconditions),
                business_rules=rules_out,
                fields=fields_out,
                screens=screens_out,
                messages=messages_out,
                notifications=[n.model_dump() for n in spec.notifications],
                permissions=[p.model_dump() for p in spec.permissions],
                audit_events=[a.model_dump() for a in spec.audit_events],
                integrations=[i.model_dump() for i in spec.integrations],
                acceptance_criteria=criteria_out,
                linked_requirement_ids=list(spec.linked_requirement_ids),
                linked_story_ids=sorted(set(story_ids)),
                flow_ids=flow_ids,
            )
        )

    missing_features = [fid for fid in committed if fid not in seen_features]
    uncovered = [rid for rid in srs_ids if rid not in covered_srs]
    coverage_pct = (
        round(100.0 * (len(srs_ids) - len(uncovered)) / max(len(srs_ids), 1), 1)
        if srs_ids
        else 100.0
    )

    if missing_features:
        notes["missing_feature_specs"] = len(missing_features)

    placeholders: list[dict[str, str]] = []
    blob = passes.planning.model_dump_json()
    for match in _PLACEHOLDER_RE.finditer(blob):
        placeholders.append({"text": match.group(0), "location": "planning"})

    health_rows = [
        {
            "label": "Feature specifications",
            "value": str(len(stored)),
            "threshold": str(len(committed)),
            "status": "OK" if not missing_features else "Warn",
        },
        {
            "label": "SRS requirement coverage",
            "value": f"{coverage_pct}%",
            "threshold": "100%",
            "status": "OK" if not uncovered else "Warn",
        },
        {
            "label": "Uncovered SRS ids",
            "value": str(len(uncovered)),
            "threshold": "0",
            "status": "OK" if not uncovered else "Warn",
        },
        {
            "label": "Weak language (rules/criteria)",
            "value": str(weak_count),
            "threshold": "0",
            "status": "OK" if weak_count == 0 else "Warn",
        },
        {
            "label": "Proposed rules share",
            "value": str(proposed_rules),
            "threshold": "—",
            "status": "OK",
        },
    ]

    approx_pages = max(20.0, len(stored) * 2.5 + 15.0)
    viewer = FrsHealthMeta(
        health_rows=health_rows,
        srs_coverage_pct=coverage_pct,
        uncovered_srs_ids=uncovered,
        spec_count=len(stored),
        placeholder_count=len(placeholders),
        approx_pages=round(approx_pages, 1),
    )

    pid = ctx.project_id.replace("-", "")[:6].upper() or "000000"
    from datetime import UTC, datetime

    ym = datetime.now(UTC).strftime("%Y%m")
    doc_ref = f"FRS-{ym}-{pid}-v{ctx.version_no}"

    perm_rows: list[dict[str, Any]] = []
    for spec in stored:
        for perm in spec.permissions:
            perm_rows.append(
                {
                    "role": perm.get("role"),
                    "feature_id": spec.feature_id,
                    "actions": ", ".join(perm.get("allowed_actions") or []),
                }
            )

    trace_rows: list[dict[str, Any]] = []
    for spec in stored:
        for rid in spec.linked_requirement_ids:
            trace_rows.append(
                {
                    "srs_id": rid,
                    "feature_id": spec.feature_id,
                    "fs_id": spec.id,
                    "story_ids": ", ".join(spec.linked_story_ids),
                }
            )

    assembled = FrsAssembled(
        document_reference=doc_ref,
        global_conventions=_global_conventions(ctx.user_inputs),
        roles=[r.model_dump() for r in passes.planning.roles],
        permission_matrix=perm_rows,
        permission_module_summary=[],
        catalogs={
            "screens": [{"id": v, "name": k} for k, v in screen_dedupe.items()],
            "messages": [{"id": v, "key": k} for k, v in msg_dedupe.items()],
        },
        state_tables=[sm.model_dump() for sm in passes.planning.state_models],
        traceability={
            "srs_total": len(srs_ids),
            "srs_covered": len(srs_ids) - len(uncovered),
            "coverage_pct": coverage_pct,
            "uncovered_srs_ids": uncovered,
        },
        open_issues=[],
        placeholders=placeholders,
        glossary=[],
        standards_references=["ISO/IEC/IEEE 29148 (SRS traceability)"],
        feature_specs_view=[s.model_dump() for s in stored],
        revision_parts=list(getattr(ctx, "frs_revision_parts", []) or []),
        traceability_rows=trace_rows,
    )

    out = FrsStored(
        passes=passes,
        specifications=stored,
        assembled=assembled,
        viewer=viewer,
    )
    notes["specifications"] = len(stored)
    notes["placeholders"] = len(placeholders)
    return out, notes

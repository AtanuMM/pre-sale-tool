"""Build code-owned SRS assembled block."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from app.steps.schemas.srs import (
    DataEntityItem,
    ExternalInterfaceItem,
    SrsAssembled,
    SrsHealthMeta,
    SrsPasses,
    StoredFunctionalRequirement,
    StoredNfrRequirement,
)

_PLACEHOLDER_RE = re.compile(r"\[TBC:[^\]]+\]")
_MOD_CODE_RE = re.compile(r"[^A-Za-z0-9]+")


def module_code(name: str, used: set[str]) -> str:
    base = _MOD_CODE_RE.sub("", name.upper())[:8] or "MOD"
    code = base
    suffix = 1
    while code in used:
        suffix += 1
        code = f"{base[:6]}{suffix}"
    used.add(code)
    return code


def document_reference(project_id: str, version_no: int) -> str:
    now = datetime.now(UTC)
    short = project_id.replace("-", "")[:6].upper()
    return f"SRS-{now.year}{now.month:02d}-{short}-v{version_no}"


def build_parameter_table(user_inputs: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    labels = {
        "cloud_provider": "Cloud provider",
        "environments": "Environments",
        "availability_target": "Availability target",
        "data_residency": "Data residency",
        "compliance_standards": "Compliance standards",
        "authentication_methods": "Authentication methods",
        "languages": "Languages",
        "supported_clients": "Supported clients",
    }
    for key, label in labels.items():
        val = user_inputs.get(key)
        if val is None or val == "" or val == []:
            continue
        if isinstance(val, list):
            text = ", ".join(str(v) for v in val)
        else:
            text = str(val)
        rows.append({"parameter": label, "value": text})
    for key, label in (
        ("expected_concurrent_users", "Expected concurrent users"),
        ("expected_peak_requests_per_second", "Expected peak RPS"),
        ("rpo_minutes", "RPO (minutes)"),
        ("rto_minutes", "RTO (minutes)"),
    ):
        val = user_inputs.get(key)
        if val is None:
            rows.append(
                {
                    "parameter": label,
                    "value": "Proposed default, to be confirmed",
                }
            )
        else:
            rows.append({"parameter": label, "value": str(val)})
    return rows


NFR_CAT_CODES = {
    "performance": "PERF",
    "scalability": "SCALE",
    "availability_and_reliability": "AVAIL",
    "security": "SEC",
    "privacy_and_compliance": "PRIV",
    "usability_and_accessibility": "USAB",
    "maintainability": "MAINT",
    "compatibility": "COMPAT",
    "observability_and_logging": "OBS",
    "backup_and_dr": "BDR",
    "localisation": "L10N",
}


def build_assembled(
    *,
    project_id: str,
    version_no: int,
    user_inputs: dict[str, Any],
    passes: SrsPasses,
    functional: list[StoredFunctionalRequirement],
    nfrs: list[StoredNfrRequirement],
    interfaces: list[ExternalInterfaceItem],
    entities: list[DataEntityItem],
    diagram_meta: list[dict[str, str]],
    open_issues: list[dict[str, str]],
    placeholders: list[dict[str, str]],
    health: SrsHealthMeta,
) -> SrsAssembled:
    standards = ["ISO/IEC/IEEE 29148 (structure and conventions)"]
    for std in user_inputs.get("compliance_standards") or []:
        if std != "none_known":
            standards.append(str(std).upper())
    figures = [
        {"number": str(i + 1), "caption": item.get("caption", "")}
        for i, item in enumerate(diagram_meta)
    ]
    trace = _traceability(functional)
    counts = {
        "functional": len(functional),
        "nfr": len(nfrs),
        "by_priority": _count_field(functional, "priority"),
        "by_module": _count_field(functional, "module"),
    }
    glossary: list[dict[str, str]] = []
    if passes.planning_b and passes.planning_b.glossary_terms:
        for g in passes.planning_b.glossary_terms:
            if isinstance(g, dict):
                glossary.append({"term": g.get("term", ""), "definition": g.get("definition", "")})
    specs: dict[str, dict[str, Any]] = {}
    if passes.planning_a:
        pa = passes.planning_a
        specs["context"] = pa.context_diagram.model_dump(mode="json")
        specs["architecture"] = pa.architecture_diagram.model_dump(mode="json")
        specs["deployment"] = pa.deployment_diagram.model_dump(mode="json")
        specs["er"] = pa.er_diagram.model_dump(mode="json")
    return SrsAssembled(
        document_reference=document_reference(project_id, version_no),
        revision_history=[
            {
                "version": str(version_no),
                "date": datetime.now(UTC).date().isoformat(),
                "description": "Generated",
            }
        ],
        status_text="In review",
        parameter_table=build_parameter_table(user_inputs),
        standards_references=standards,
        figures=figures,
        tables=[],
        placeholders=placeholders,
        open_issues=open_issues,
        glossary=glossary,
        traceability=trace,
        counts=counts,
        diagram_specs=specs,
        module_sections=[],
    )


def _count_field(rows: list[StoredFunctionalRequirement], field: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in rows:
        val = getattr(row, field, "")
        out[str(val)] = out.get(str(val), 0) + 1
    return out


def _traceability(functional: list[StoredFunctionalRequirement]) -> dict[str, Any]:
    source_to_fr: dict[str, list[str]] = {}
    feature_to_fr: dict[str, list[str]] = {}
    method_map: dict[str, str] = {}
    for fr in functional:
        feature_to_fr.setdefault(fr.feature_id, []).append(fr.id)
        method_map[fr.id] = fr.verification_method
        for src in fr.source_requirement_ids:
            source_to_fr.setdefault(src, []).append(fr.id)
    return {
        "source_to_requirements": source_to_fr,
        "feature_to_requirements": feature_to_fr,
        "requirement_to_verification": method_map,
    }


def estimate_page_count(
    passes: SrsPasses,
    functional: list[StoredFunctionalRequirement],
    nfrs: list[StoredNfrRequirement],
) -> float:
    words = 0
    if passes.planning_a:
        words += len(passes.planning_a.overview.split())
    if passes.planning_b:
        words += len(passes.planning_b.api_standards.split())
    for fr in functional:
        words += len(fr.statement.split())
    for nfr in nfrs:
        words += len(nfr.statement.split())
    tables = len(functional) // 15 + len(nfrs) // 10
    return round(words / 300 + tables * 0.5 + 4, 1)

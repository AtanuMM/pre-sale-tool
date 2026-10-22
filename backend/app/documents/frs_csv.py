"""FRS acceptance criteria CSV register."""

from __future__ import annotations

from typing import Any

from app.documents.csv_export import csv_safe_cell
from app.steps.schemas.frs import FrsStored


def build_frs_csv(content: dict[str, Any]) -> bytes:
    stored = FrsStored.model_validate(content)
    lines = [
        "ID,Module,Feature,Scenario,Given,When,Then,Covers SRS requirements,Priority,Phase"
    ]
    idx = 0
    for spec in stored.specifications:
        for crit in spec.acceptance_criteria:
            idx += 1
            row = [
                f"AC-{idx:04d}",
                spec.module,
                spec.title,
                str(crit.get("scenario_title") or ""),
                str(crit.get("given") or ""),
                str(crit.get("when") or ""),
                str(crit.get("then") or ""),
                ";".join(crit.get("covers_requirement_ids") or []),
                spec.priority,
                spec.phase,
            ]
            lines.append(",".join(csv_safe_cell(v) for v in row))
    body = "\r\n".join(lines)
    return b"\xef\xbb\xbf" + body.encode("utf-8")

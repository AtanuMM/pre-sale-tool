"""FRS XLSX register export."""

from __future__ import annotations

from io import BytesIO
from typing import Any

from openpyxl import Workbook

from app.steps.schemas.frs import FrsStored


def build_frs_xlsx(content: dict[str, Any], _meta: Any) -> bytes:
    stored = FrsStored.model_validate(content)
    wb = Workbook()
    ws = wb.active
    ws.title = "Specifications"
    ws.append(["FS ID", "Module", "Feature", "Priority", "Phase", "Summary"])
    for spec in stored.specifications:
        ws.append(
            [
                spec.id,
                spec.module,
                spec.title,
                spec.priority,
                spec.phase,
                spec.summary[:500],
            ]
        )
    ws.freeze_panes = "A2"

    ac = wb.create_sheet("Acceptance Criteria")
    ac.append(["ID", "Module", "Feature", "Scenario", "Given", "When", "Then", "Covers SRS"])
    idx = 0
    for spec in stored.specifications:
        for crit in spec.acceptance_criteria:
            idx += 1
            ac.append(
                [
                    f"AC-{idx:04d}",
                    spec.module,
                    spec.title,
                    crit.get("scenario_title", ""),
                    crit.get("given", ""),
                    crit.get("when", ""),
                    crit.get("then", ""),
                    ", ".join(crit.get("covers_requirement_ids") or []),
                ]
            )
    ac.freeze_panes = "A2"

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()

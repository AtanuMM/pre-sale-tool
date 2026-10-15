"""Sprint Plan XLSX export."""

from __future__ import annotations

from io import BytesIO
from typing import Any

from openpyxl import Workbook

from app.documents.meta import ExportMeta
from app.steps.schemas.sprint_plan import SprintPlanStored


def build_sprint_plan_xlsx(content: dict[str, Any], meta: ExportMeta) -> bytes:
    stored = SprintPlanStored.model_validate(content)
    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    ws.append(["Sprint Plan", meta.project_name])
    backlog = wb.create_sheet("Backlog")
    backlog.append(["ID", "Title", "Feature", "Sprint"])
    for story in stored.stories:
        backlog.append(
            [
                str(story.id),
                str(story.title),
                str(story.feature_id),
                story.sprint_number,
            ]
        )
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()

"""Sprint Plan CSV (Jira-style backlog)."""

from __future__ import annotations

import csv
from io import StringIO
from typing import Any

from app.documents.csv_export import csv_safe_cell
from app.steps.schemas.sprint_plan import SprintPlanStored


def build_sprint_plan_csv(content: dict[str, Any], show_hours: bool, show_points: bool) -> bytes:
    stored = SprintPlanStored.model_validate(content)
    buf = StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")
    headers = ["Issue Type", "Summary", "Description", "Acceptance Criteria", "Sprint", "Priority"]
    if show_hours:
        headers.append("Original Estimate")
    if show_points:
        headers.append("Story Points")
    writer.writerow(headers)
    for story in stored.stories:
        row = [
            csv_safe_cell("Spike" if story.is_spike else "Story"),
            csv_safe_cell(story.title),
            csv_safe_cell(story.story_statement),
            csv_safe_cell("; ".join(story.acceptance_criteria)),
            csv_safe_cell(str(story.sprint_number or "")),
            csv_safe_cell(""),
        ]
        if show_hours:
            row.append(csv_safe_cell(str(sum(story.hours_by_role.values()))))
        if show_points:
            row.append(csv_safe_cell(str(story.story_points or "")))
        writer.writerow(row)
    return ("\ufeff" + buf.getvalue()).encode("utf-8")

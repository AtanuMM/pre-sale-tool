"""Sprint Plan user input field specs."""

from __future__ import annotations

from app.steps.input_fields import InputFieldSpec, TableColumnSpec

_NON_WORKING_COLUMNS: tuple[TableColumnSpec, ...] = (
    TableColumnSpec(key="label", label="Label", kind="text", max_length=120),
    TableColumnSpec(
        key="start_date",
        label="Start date",
        kind="text",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    ),
    TableColumnSpec(
        key="end_date",
        label="End date",
        kind="text",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    ),
)

SPRINT_PLAN_INPUT_FIELDS: tuple[InputFieldSpec, ...] = (
    InputFieldSpec(
        key="sprint_length_weeks",
        label="Sprint length (weeks)",
        help_text="Scrum sprint length (1–4 weeks). Defaults from the SOW when available.",
        kind="number",
        required=True,
        min_value=1,
        max_value=4,
        default=2,
    ),
    InputFieldSpec(
        key="start_date",
        label="Plan start date",
        help_text="Optional. Used for indicative sprint calendar dates.",
        kind="date",
        required=False,
    ),
    InputFieldSpec(
        key="include_sprint_zero",
        label="Include Sprint 0",
        help_text="Reserve an initial sprint for setup and onboarding work packages.",
        kind="select",
        required=True,
        options=("yes", "no"),
        default="yes",
    ),
    InputFieldSpec(
        key="hardening_sprint_per_release",
        label="Hardening sprint per release",
        help_text="Add a hardening sprint at the end of each committed release phase.",
        kind="select",
        required=True,
        options=("yes", "no"),
        default="yes",
    ),
    InputFieldSpec(
        key="ceremony_overhead_pct",
        label="Ceremony overhead (%)",
        help_text=(
            "Percentage of capacity reserved for planning, reviews, retrospectives and refinement."
        ),
        kind="number",
        required=True,
        min_value=0,
        max_value=30,
        default=10,
    ),
    InputFieldSpec(
        key="non_working_periods",
        label="Non-working periods",
        help_text="Optional holidays or closures (up to 20 rows).",
        kind="table",
        required=False,
        max_rows=20,
        columns=_NON_WORKING_COLUMNS,
    ),
    InputFieldSpec(
        key="product_owner_label",
        label="Product owner label",
        help_text="Label used in governance text (for example Client Product Owner).",
        kind="text",
        required=False,
        max_length=120,
        default="Client Product Owner",
    ),
    InputFieldSpec(
        key="show_effort_hours",
        label="Show effort hours in exports",
        help_text="When no, hours are hidden in client-facing DOCX/XLSX/CSV.",
        kind="select",
        required=True,
        options=("no", "yes"),
        default="no",
    ),
    InputFieldSpec(
        key="show_story_points",
        label="Show story points",
        help_text="Indicative Fibonacci points derived from story hours.",
        kind="select",
        required=True,
        options=("no", "yes"),
        default="no",
    ),
    InputFieldSpec(
        key="notes",
        label="Planning notes",
        help_text="Optional notes for the model when generating stories and narrative.",
        kind="textarea",
        max_length=8000,
        required=False,
    ),
)

SPRINT_PLAN_RESCHEDULE_KEYS: frozenset[str] = frozenset(
    {
        "sprint_length_weeks",
        "start_date",
        "include_sprint_zero",
        "hardening_sprint_per_release",
        "ceremony_overhead_pct",
        "non_working_periods",
        "show_effort_hours",
        "show_story_points",
    }
)


def scheduling_inputs_changed(base: dict, new: dict) -> bool:
    for key in SPRINT_PLAN_RESCHEDULE_KEYS:
        if base.get(key) != new.get(key):
            return True
    return False

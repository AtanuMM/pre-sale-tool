"""Estimate extra-input field specs (validated server-side)."""

from __future__ import annotations

from app.steps.input_fields import InputFieldSpec, TableColumnSpec
from app.steps.schemas.estimate import PHASE_ORDER

TEAM_COLUMNS: tuple[TableColumnSpec, ...] = (
    TableColumnSpec(
        key="role",
        label="Role",
        kind="text",
        min_length=2,
        max_length=40,
        pattern="role_name",
    ),
    TableColumnSpec(
        key="discipline",
        label="Discipline",
        kind="select",
        options=("development", "qa", "design", "management", "devops", "other"),
        default="other",
    ),
    TableColumnSpec(
        key="mode",
        label="Mode",
        kind="select",
        options=("estimated", "percent_of_delivery", "duration_based"),
        default="estimated",
    ),
    TableColumnSpec(
        key="headcount",
        label="Headcount",
        kind="number",
        min_value=0.5,
        max_value=100,
        step=0.5,
        default=1,
    ),
    TableColumnSpec(
        key="hours_per_week",
        label="Hours / week",
        kind="number",
        min_value=1,
        max_value=60,
        default=40,
    ),
    TableColumnSpec(
        key="utilisation_pct",
        label="Utilisation %",
        kind="number",
        min_value=10,
        max_value=100,
        default=100,
    ),
    TableColumnSpec(
        key="ai_gain_pct",
        label="AI gain %",
        kind="number",
        min_value=0,
        max_value=70,
        default=0,
        enabled_when=("discipline", "development"),
    ),
    TableColumnSpec(
        key="hourly_rate",
        label="Hourly rate",
        kind="number",
        min_value=0,
        required=False,
    ),
    TableColumnSpec(
        key="overhead_pct",
        label="Overhead %",
        kind="number",
        min_value=1,
        max_value=60,
        required=True,
        visible_when=("mode", "percent_of_delivery"),
    ),
)

ESTIMATE_INPUT_FIELDS: tuple[InputFieldSpec, ...] = (
    InputFieldSpec(
        key="team",
        label="Team",
        help_text=(
            "Roles that will deliver this work. At least one estimated role is required. "
            "AI gain % applies only to development-discipline roles and is applied in code, "
            "not by the model."
        ),
        kind="table",
        required=True,
        min_rows=1,
        max_rows=15,
        columns=TEAM_COLUMNS,
        unique_column="role",
        require_estimated_row=True,
    ),
    InputFieldSpec(
        key="phases",
        label="Phases",
        help_text="MVP is always included. Future scope is excluded from committed totals.",
        kind="multi_select",
        required=True,
        options=PHASE_ORDER,
        default=["mvp", "phase_1", "phase_2", "future_scope"],
        required_option="mvp",
    ),
    InputFieldSpec(
        key="domain_experience",
        label="Domain experience",
        help_text=(
            "How familiar the delivery team is with this kind of product. "
            "High confidence is allowed only when the team has built something similar before."
        ),
        kind="select",
        required=True,
        options=("built_similar_before", "some_experience", "new_to_us"),
        default="some_experience",
    ),
    InputFieldSpec(
        key="kickoff_date",
        label="Kickoff date",
        help_text="Optional. Used only for a capacity check against estimated weeks.",
        kind="text",
        max_length=10,
        required=False,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    ),
    InputFieldSpec(
        key="target_date",
        label="Target date",
        help_text="Optional. Used only for a capacity check against estimated weeks.",
        kind="text",
        max_length=10,
        required=False,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    ),
    InputFieldSpec(
        key="currency",
        label="Currency",
        help_text="Optional short code used only when hourly rates are entered (for example INR).",
        kind="text",
        max_length=8,
        required=False,
        pattern=r"^[A-Za-z]{0,8}$",
    ),
    InputFieldSpec(
        key="notes",
        label="Estimation notes and client answers",
        help_text="Optional notes or client answers used only for this step.",
        kind="textarea",
        max_length=8000,
        required=False,
    ),
)

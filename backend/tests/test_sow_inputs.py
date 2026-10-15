import pytest

from app.steps.input_fields import StepInputValidationError, validate_step_inputs
from app.steps.sow_inputs import SOW_INPUT_FIELDS


def _base_inputs(**overrides: object) -> dict:
    data: dict[str, object] = {
        "client_legal_name": "Client Legal Name Pty Ltd",
        "company_legal_name": "Supplier Legal Name Ltd",
        "pricing_model": "fixed_price",
        "review_period_business_days": 5,
        "warranty_days": 30,
        "sprint_length_weeks": 2,
        "show_effort_hours": "no",
        "team_display": "roles_only",
        "payment_schedule": [
            {"label": "Signing", "percent": 50, "trigger": "signing"},
            {"label": "Completion", "percent": 50, "trigger": "phase_complete"},
        ],
    }
    data.update(overrides)
    return data


def test_payment_schedule_must_total_100_for_fixed_price() -> None:
    with pytest.raises(StepInputValidationError):
        validate_step_inputs(
            SOW_INPUT_FIELDS,
            _base_inputs(
                payment_schedule=[
                    {"label": "Signing", "percent": 40, "trigger": "signing"},
                ]
            ),
        )


def test_kickoff_date_accepts_iso_date() -> None:
    cleaned = validate_step_inputs(
        SOW_INPUT_FIELDS,
        _base_inputs(pricing_model="not_specified", payment_schedule=[], kickoff_date="2026-04-01"),
    )
    assert cleaned["kickoff_date"] == "2026-04-01"

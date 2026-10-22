"""FRS input validation."""

from app.steps.definitions import get_step
from app.steps.input_fields import StepInputValidationError, validate_step_inputs


def test_frs_inputs_validate_defaults() -> None:
    defn = get_step("frs")
    cleaned = validate_step_inputs(
        defn.input_fields,
        {
            "document_title": "FRS",
            "company_legal_name": "Supplier Ltd",
            "client_legal_name": "Client Ltd",
            "detail_level": "detailed",
            "date_format": "DD/MM/YYYY",
            "accessibility_target": "WCAG 2.1 AA",
        },
    )
    assert cleaned["detail_level"] == "detailed"


def test_frs_password_length_bounds() -> None:
    defn = get_step("frs")
    try:
        validate_step_inputs(
            defn.input_fields,
            {
                "document_title": "FRS",
                "company_legal_name": "S",
                "client_legal_name": "C",
                "detail_level": "detailed",
                "date_format": "DD/MM/YYYY",
                "accessibility_target": "not_specified",
                "min_password_length": 3,
            },
        )
        raise AssertionError("expected validation error")
    except StepInputValidationError:
        pass

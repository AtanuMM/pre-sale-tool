from app.steps.input_fields import validate_step_inputs
from app.steps.srs_inputs import SRS_INPUT_FIELDS


def test_srs_defaults_applied() -> None:
    cleaned = validate_step_inputs(
        SRS_INPUT_FIELDS,
        {
            "document_title": "SRS",
            "company_legal_name": "Supplier Ltd",
            "client_legal_name": "Client Ltd",
            "cloud_provider": "not_decided",
            "compliance_standards": ["none_known"],
            "authentication_methods": ["email_password"],
        },
    )
    assert cleaned["detail_level"] == "detailed"
    assert "development" in cleaned["environments"]

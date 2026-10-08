import json

from app.steps.schema_gemini import (
    collect_forbidden_keywords,
    gemini_processed_schema_dict,
)
from app.steps.schemas.scope_analysis import ScopeAnalysisOutput


def test_scope_analysis_round_trip() -> None:
    sample = ScopeAnalysisOutput.model_validate(
        {
            "executive_summary": "Summary.",
            "objectives": ["Obj"],
            "stakeholders_and_users": [
                {
                    "name": "Ops",
                    "role_or_group": "Internal",
                    "needs_or_interest": "Visibility",
                }
            ],
            "in_scope": ["Portal"],
            "out_of_scope_or_assumed": [
                {"item": "ERP build", "rationale": "External system"}
            ],
            "ambiguities_and_questions": [
                {"question": "Which auth?", "why_it_matters": "Security design"}
            ],
            "risks": [
                {
                    "risk": "Unclear ERP API",
                    "impact": "Delay",
                    "suggested_mitigation": "Workshop",
                }
            ],
            "dependencies": ["ExampleERP"],
            "assumptions": ["API docs exist"],
        }
    )
    again = ScopeAnalysisOutput.model_validate_json(sample.model_dump_json())
    assert again == sample


def test_gemini_processed_schema_has_no_unsupported_keywords() -> None:
    processed = gemini_processed_schema_dict(ScopeAnalysisOutput)
    forbidden = collect_forbidden_keywords(processed)
    assert forbidden == []
    # Ensure conversion produced a concrete object schema
    assert json.dumps(processed)

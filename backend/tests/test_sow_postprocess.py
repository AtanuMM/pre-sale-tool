from app.steps.postprocess import PostprocessContext
from app.steps.postprocess.sow import postprocess_sow, reassemble_sow
from app.steps.schemas.sow import SowNarrativeOutput, SowStored


def _estimate_v2() -> dict:
    return {
        "schema_version": 2,
        "phases": [{"key": "mvp", "goal": "core", "scope_rationale": "must"}],
        "components": [{"name": "API", "description": "Services"}],
        "work_packages": [],
        "feature_estimates": [
            {
                "feature_id": "F-001",
                "title": "Login",
                "phase": "mvp",
                "component": "API",
                "priority": "must",
            }
        ],
        "computed": {
            "phase_rows": [{"phase": "mvp", "weeks_planned": 4.0}],
            "totals": {"weeks_planned": 4.0},
        },
    }


def _sow_inputs() -> dict:
    return {
        "client_legal_name": "Client Co",
        "company_legal_name": "Supplier Ltd",
        "pricing_model": "not_specified",
        "review_period_business_days": 5,
        "warranty_days": 30,
        "sprint_length_weeks": 2,
        "show_effort_hours": "no",
        "team_display": "roles_only",
    }


def _ctx(**overrides: object) -> PostprocessContext:
    base: dict[str, object] = {
        "project_id": "00000000-0000-0000-0000-000000000001",
        "version_no": 1,
        "scope_content": {"executive_summary": "Scope", "objectives": []},
        "gap_content": {"gaps": [], "client_questions": []},
        "feature_list_content": {"features": [], "modules": []},
        "estimate_content": _estimate_v2(),
        "estimate_user_inputs": {
            "team": [
                {
                    "role": "Developer",
                    "discipline": "development",
                    "mode": "estimated",
                    "headcount": 1,
                    "hours_per_week": 40,
                    "utilisation_pct": 100,
                    "ai_gain_pct": 0,
                }
            ]
        },
        "user_inputs": _sow_inputs(),
        "estimated_role_names": ("Developer",),
    }
    base.update(overrides)
    return PostprocessContext(**base)  # type: ignore[arg-type]


def _narrative(**overrides: object) -> SowNarrativeOutput:
    bundle_key = "commit|mvp|API"
    data: dict[str, object] = {
        "document_title": "Statement of Work",
        "purpose": "Deliver software.",
        "background": "Client needs a product.",
        "objectives": ["Launch MVP"],
        "success_criteria": ["Users can sign in"],
        "scope_overview": "MVP scope only.",
        "phase_descriptions": [
            {"phase": "mvp", "description": "Core authentication and API."}
        ],
        "out_of_scope": [],
        "deliverables": [
            {
                "bundle_key": bundle_key,
                "title": "API (mvp)",
                "description": "Working API for committed features.",
                "acceptance_criteria": ["Login works end to end."],
            }
        ],
        "approach": "Agile delivery.",
        "quality_approach": "Testing and reviews.",
        "milestones": [
            {
                "name": "MVP complete",
                "phase": "mvp",
                "description": "MVP accepted.",
                "completion_criteria": "All MVP deliverables accepted.",
            }
        ],
        "team_roles": [
            {"role": "Developer", "responsibilities": ["Build and test features."]}
        ],
        "client_responsibilities": [],
        "assumptions": [],
        "constraints_and_dependencies": [],
        "risks": [],
        "glossary": [],
    }
    data.update(overrides)
    return SowNarrativeOutput.model_validate(data)


def test_postprocess_builds_assembled_and_defaults_missing_roles() -> None:
    stored, notes = postprocess_sow(_narrative(team_roles=[]), _ctx())
    assert notes["roles_added"] == 1
    assert stored.assembled.bundle_keys == ["commit|mvp|API"]
    assert stored.viewer.placeholder_count >= 0
    assert isinstance(stored, SowStored)


def test_reassemble_keeps_narrative_and_refreshes_commercials() -> None:
    stored, _ = postprocess_sow(_narrative(), _ctx())
    new_inputs = {**_sow_inputs(), "total_fee": 100_000, "currency": "USD"}
    ctx2 = _ctx(user_inputs=new_inputs)
    updated, notes = reassemble_sow(stored, ctx2)
    assert notes["reassemble"] == 1
    assert updated.narrative.document_title == stored.narrative.document_title
    assert updated.assembled.commercials.total_fee == 100_000
    assert updated.assembled.commercials.currency == "USD"

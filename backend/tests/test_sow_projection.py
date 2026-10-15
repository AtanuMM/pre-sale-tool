import json

import pytest

from app.steps.client_safe import FORBIDDEN_PROMPT_SUBSTRINGS
from app.steps.sow_projection import build_prompt_context_json, project_scope


def test_project_scope_strips_internal_fields() -> None:
    scope = {
        "executive_summary": "Summary",
        "objectives": ["Ship MVP"],
        "internal_token": "effort_lines should not appear in output keys",
    }
    out = project_scope(scope)
    assert out["executive_summary"] == "Summary"
    assert "internal_token" not in out
    blob = json.dumps(out).casefold()
    for token in FORBIDDEN_PROMPT_SUBSTRINGS:
        assert token.casefold() not in blob


def test_project_scope_rejects_forbidden_substrings_in_text() -> None:
    with pytest.raises(ValueError, match="client-unsafe"):
        project_scope(
            {
                "executive_summary": "Do not leak effort_lines to the client.",
                "objectives": [],
            }
        )


def test_build_prompt_context_accepts_safe_estimate_projection() -> None:
    text = build_prompt_context_json(
        scope={"executive_summary": "s", "objectives": ["o"]},
        gap={"gaps": [], "client_questions": []},
        feature_list={"features": [], "modules": []},
        estimate={
            "phases": [{"key": "mvp", "goal": "g", "scope_rationale": "r"}],
            "components": [{"name": "API", "description": "d"}],
            "work_packages": [],
            "assumptions_and_solutions": [],
            "exclusions": [],
            "feature_estimates": [
                {
                    "feature_id": "F-001",
                    "title": "Login",
                    "phase": "mvp",
                    "component": "API",
                    "priority": "must",
                }
            ],
        },
        estimate_user_inputs={
            "team": [
                {
                    "role": "Developer",
                    "discipline": "development",
                    "mode": "estimated",
                }
            ]
        },
    )
    parsed = json.loads(text)
    assert parsed["scope"]["executive_summary"] == "s"
    assert parsed["estimate"]["feature_placements"][0]["feature_id"] == "F-001"
    blob = text.casefold()
    for token in FORBIDDEN_PROMPT_SUBSTRINGS:
        assert token.casefold() not in blob

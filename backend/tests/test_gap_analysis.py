"""Gap analysis step (mocked Gemini)."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.models.steps import StepVersion
from app.steps.schemas.gap_analysis import GapAnalysisOutput
from tests.test_steps import (
    _auth,
    _create_project_multipart,
    _mock_gemini_success,
)

pytest_plugins = ["tests.test_steps"]


def _sample_gap_output() -> GapAnalysisOutput:
    return GapAnalysisOutput.model_validate(
        {
            "summary": "Several clarifications needed.",
            "gaps": [
                {
                    "title": "Auth provider unknown",
                    "category": "ambiguity",
                    "severity": "high",
                    "description": "Scope mentions SSO but not IdP.",
                    "why_it_matters": "Blocks security design.",
                    "clarification_question": "Which identity provider?",
                    "suggested_default_assumption": "Assume Azure AD.",
                    "related_scope_section": "In scope",
                }
            ],
            "client_questions": ["Which identity provider will be used?"],
        }
    )


@patch("app.services.step_generation.generate_structured_result")
def test_gap_locked_until_scope_approved(
    mock_gen: MagicMock,
    client: TestClient,
    seeded_session,
) -> None:
    mock_gen.return_value = _mock_gemini_success()
    _, settings = seeded_session
    headers = _auth(client, settings)
    created = _create_project_multipart(client, headers)
    pid = created["project"]["id"]
    steps = client.get(f"/projects/{pid}/steps", headers=headers).json()
    gap = next(s for s in steps["steps"] if s["key"] == "gap_analysis")
    assert gap["status"] == "locked"
    assert gap["can_generate"] is False


@patch("app.services.step_generation.generate_structured_result")
def test_gap_generate_records_scope_dependency(
    mock_gen: MagicMock,
    client: TestClient,
    seeded_session,
) -> None:
    from app.llm.gemini import StructuredGenerationResult

    mock_gen.side_effect = [
        _mock_gemini_success(),
        StructuredGenerationResult(
            data=_sample_gap_output(),
            model_id="m",
            tokens_in=10,
            tokens_out=20,
            api_attempt_count=1,
        ),
    ]
    factory, settings = seeded_session
    headers = _auth(client, settings)
    created = _create_project_multipart(client, headers)
    pid = created["project"]["id"]
    scope_resp = client.post(
        f"/projects/{pid}/steps/scope_analysis/generate", headers=headers
    )
    assert scope_resp.status_code == 202
    scope_id = scope_resp.json()["version"]["id"]
    approve = client.post(f"/step-versions/{scope_id}/approve", headers=headers, json={})
    assert approve.status_code == 200

    gap_resp = client.post(
        f"/projects/{pid}/steps/gap_analysis/generate", headers=headers
    )
    assert gap_resp.status_code == 202, gap_resp.text
    gap_vid = gap_resp.json()["version"]["id"]

    with factory() as session:
        deps = session.execute(
            text(
                "SELECT depends_on_version_id FROM step_version_dependencies "
                "WHERE step_version_id = :id"
            ),
            {"id": gap_vid},
        ).all()
        assert len(deps) == 1
        dep_version = session.get(StepVersion, deps[0][0])
        assert dep_version is not None
        assert dep_version.step_key == "scope_analysis"
        assert dep_version.status == "approved"

    detail = client.get(f"/step-versions/{gap_vid}", headers=headers).json()
    assert detail["status"] == "in_review"
    assert detail["content"]["gaps"][0]["title"] == "Auth provider unknown"


@patch("app.services.step_generation.generate_structured_result")
def test_gap_prompt_contains_scope_block(
    mock_gen: MagicMock,
    client: TestClient,
    seeded_session,
) -> None:
    from app.llm.gemini import StructuredGenerationResult

    mock_gen.side_effect = [
        _mock_gemini_success(),
        StructuredGenerationResult(
            data=_sample_gap_output(),
            model_id="m",
            tokens_in=10,
            tokens_out=20,
            api_attempt_count=1,
        ),
    ]
    _, settings = seeded_session
    headers = _auth(client, settings)
    created = _create_project_multipart(client, headers)
    pid = created["project"]["id"]
    scope_id = client.post(
        f"/projects/{pid}/steps/scope_analysis/generate", headers=headers
    ).json()["version"]["id"]
    client.post(f"/step-versions/{scope_id}/approve", headers=headers, json={})
    gap_id = client.post(
        f"/projects/{pid}/steps/gap_analysis/generate", headers=headers
    ).json()["version"]["id"]

    with seeded_session[0]() as session:
        row = session.get(StepVersion, uuid.UUID(gap_id))
        assert row is not None
        prompt = row.assembled_prompt or ""
        assert "BEGIN UNTRUSTED DATA" in prompt
        assert "scope_analysis" in prompt
        assert "executive_summary" in prompt

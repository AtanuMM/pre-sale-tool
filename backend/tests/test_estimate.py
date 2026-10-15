"""Estimate step (mocked Gemini)."""

from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.llm.gemini import LLMError, StructuredGenerationResult
from app.models.steps import StepVersion
from app.models.system import AuditLog
from app.services.audit import AuditAction
from app.steps.schemas.estimate_v2 import EstimateBatchOutput, EstimatePlanningOutput
from tests.test_feature_list import _approve_scope_and_gap, _gemini_feature
from tests.test_steps import _auth, _create_project_multipart

pytest_plugins = ["tests.test_steps"]

_REQUIRED_TYPES = (
    "project_setup_architecture",
    "cicd_environments",
    "uat_support",
    "deployment",
    "documentation_training",
    "stabilization",
    "hypercare",
)


def _sample_planning() -> EstimatePlanningOutput:
    packages = [
        {
            "id": f"W-{index}",
            "package_type": ptype,
            "title": ptype.replace("_", " ").title(),
            "description": "Required package",
            "phase": "mvp",
            "component": "Backend API",
            "confidence": "medium",
            "ai_leverage": "none",
            "lead_time_weeks": 0,
        }
        for index, ptype in enumerate(_REQUIRED_TYPES, start=1)
    ]
    return EstimatePlanningOutput.model_validate(
        {
            "summary": "Dummy portal estimate.",
            "approach": "API plus a small web app.",
            "components": [
                {"name": "Backend API", "description": "Services", "screens": 2},
                {"name": "Website", "description": "UI", "screens": 4},
            ],
            "phases": [
                {"key": "mvp", "goal": "Sign in", "scope_rationale": "Core value"},
                {"key": "phase_1", "goal": "Orders", "scope_rationale": "Next"},
            ],
            "assumptions_and_solutions": [
                {
                    "gap_ref": "G-1",
                    "topic": "Identity provider",
                    "solution": "Azure AD",
                    "rationale": "Fits the dummy brief",
                    "effort_impact": "medium",
                    "alternatives": "Okta",
                    "confirm_with_client": "Confirm IdP",
                    "basis": "assumed_not_in_source",
                }
            ],
            "exclusions": ["Hosting fees", "Content creation"],
            "work_packages": packages,
        }
    )


def _sample_batch() -> EstimateBatchOutput:
    wp_lines = [
        {
            "item_id": f"W-{index}",
            "role": "Developer",
            "task": "other",
            "best_hours": 2,
            "likely_hours": 2,
            "worst_hours": 4,
        }
        for index in range(1, 8)
    ]
    return EstimateBatchOutput.model_validate(
        {
            "feature_estimates": [
                {
                    "feature_id": "F-001",
                    "phase": "mvp",
                    "component": "Backend API",
                    "confidence": "medium",
                    "confidence_reason": "SSO is assumed, not fully specified.",
                    "ai_leverage": "medium",
                    "complexity": "M",
                    "basis": "source",
                    "primary_risk_domain": "none",
                },
                {
                    "feature_id": "F-002",
                    "phase": "phase_1",
                    "component": "Website",
                    "confidence": "medium",
                    "confidence_reason": "List view is sketched only.",
                    "ai_leverage": "low",
                    "complexity": "S",
                    "basis": "source",
                    "primary_risk_domain": "none",
                },
            ],
            "added_items": [],
            "effort_lines": [
                {
                    "item_id": "F-001",
                    "role": "Developer",
                    "task": "backend_api",
                    "best_hours": 32,
                    "likely_hours": 40,
                    "worst_hours": 56,
                },
                {
                    "item_id": "F-002",
                    "role": "Developer",
                    "task": "web_ui",
                    "best_hours": 12,
                    "likely_hours": 16,
                    "worst_hours": 24,
                },
                *wp_lines,
            ],
        }
    )


def _gemini_planning():
    return StructuredGenerationResult(
        data=_sample_planning(),
        model_id="m",
        tokens_in=10,
        tokens_out=20,
        api_attempt_count=1,
    )


def _gemini_batch():
    return StructuredGenerationResult(
        data=_sample_batch(),
        model_id="m",
        tokens_in=8,
        tokens_out=16,
        api_attempt_count=1,
    )


def _gemini_estimate_calls():
    return [_gemini_planning(), _gemini_batch()]


def _team_inputs() -> dict:
    return {
        "team": [
            {
                "role": "Developer",
                "discipline": "development",
                "mode": "estimated",
                "headcount": 2,
                "hours_per_week": 40,
                "utilisation_pct": 100,
                "ai_gain_pct": 20,
            }
        ],
        "phases": ["mvp", "phase_1", "future_scope"],
        "domain_experience": "some_experience",
        "notes": "Dummy note: SSO can be Azure AD.",
    }


def _approve_through_features(
    client: TestClient, headers: dict[str, str], mock_gen: MagicMock, pid: str
) -> None:
    _approve_scope_and_gap(client, headers, mock_gen, pid)
    mock_gen.side_effect = [_gemini_feature()]
    fid = client.post(
        f"/projects/{pid}/steps/feature_list/generate", headers=headers
    ).json()["version"]["id"]
    assert (
        client.post(f"/step-versions/{fid}/approve", headers=headers, json={}).status_code
        == 200
    )


@patch("app.services.step_generation.generate_structured_result")
def test_estimate_locked_until_feature_list_approved(
    mock_gen: MagicMock,
    client: TestClient,
    seeded_session,
) -> None:
    _, settings = seeded_session
    headers = _auth(client, settings)
    pid = _create_project_multipart(client, headers)["project"]["id"]
    steps = client.get(f"/projects/{pid}/steps", headers=headers).json()
    estimate = next(s for s in steps["steps"] if s["key"] == "estimate")
    assert estimate["status"] == "locked"
    assert estimate["implemented"] is True
    assert estimate["export_formats"] == ["docx", "xlsx", "csv"]
    assert any(f["key"] == "team" for f in estimate["input_fields"])
    resp = client.post(
        f"/projects/{pid}/steps/estimate/generate",
        headers=headers,
        json={"inputs": _team_inputs()},
    )
    assert resp.status_code == 409


@patch("app.services.step_generation.generate_structured_result")
def test_estimate_generate_computes_and_prompt_safety(
    mock_gen: MagicMock,
    client: TestClient,
    seeded_session,
) -> None:
    factory, settings = seeded_session
    headers = _auth(client, settings)
    pid = _create_project_multipart(client, headers)["project"]["id"]
    _approve_through_features(client, headers, mock_gen, pid)
    mock_gen.side_effect = _gemini_estimate_calls()
    resp = client.post(
        f"/projects/{pid}/steps/estimate/generate",
        headers=headers,
        json={"inputs": _team_inputs()},
    )
    assert resp.status_code == 202, resp.text
    vid = resp.json()["version"]["id"]
    detail = client.get(f"/step-versions/{vid}", headers=headers).json()
    assert detail["status"] == "in_review"
    content = detail["content"]
    assert content["schema_version"] == 2
    assert content["feature_estimates"][0]["title"] == "Sign in"
    assert "computed" in content
    totals = content["computed"]["totals"]
    assert totals["hours_without_ai"] > 0
    assert totals["weeks"] > 0
    assert "health_rows" in content["computed"]
    assert detail["inputs"]["repair_attempted"] == 0

    with factory() as session:
        version = session.get(StepVersion, uuid.UUID(vid))
        assert version is not None
        deps = session.execute(
            text(
                "SELECT sv.step_key FROM step_version_dependencies d "
                "JOIN step_versions sv ON sv.id = d.depends_on_version_id "
                "WHERE d.step_version_id = :id ORDER BY sv.step_key"
            ),
            {"id": vid},
        ).all()
        assert [row[0] for row in deps] == [
            "feature_list",
            "gap_analysis",
            "scope_analysis",
        ]
        prompt = version.assembled_prompt or ""
        assert "BEGIN UNTRUSTED DATA" in prompt
        assert "Developer" in prompt
        assert "F-001" in prompt or '"id": "F-001"' in prompt
        assert "G-1" in prompt
        assert "ai_gain" not in prompt.lower()
        assert "headcount" not in prompt.lower()
        assert "hourly_rate" not in prompt.lower()
        assert "contingency" not in prompt.lower()
        audit = session.scalar(
            select(AuditLog).where(
                AuditLog.action == AuditAction.STEP_GENERATE_REQUESTED,
                AuditLog.entity_id == uuid.UUID(vid),
            )
        )
        assert audit is not None
        meta = json.dumps(audit.meta)
        assert "Dummy note" not in meta
        assert "20" not in str(audit.meta.get("user_inputs", {}))


@patch("app.services.step_generation.generate_structured_result")
def test_estimate_missing_team_422(
    mock_gen: MagicMock,
    client: TestClient,
    seeded_session,
) -> None:
    _, settings = seeded_session
    headers = _auth(client, settings)
    pid = _create_project_multipart(client, headers)["project"]["id"]
    _approve_through_features(client, headers, mock_gen, pid)
    resp = client.post(f"/projects/{pid}/steps/estimate/generate", headers=headers)
    assert resp.status_code == 422


@patch("app.services.step_generation.generate_structured_result")
def test_request_changes_with_edited_team(
    mock_gen: MagicMock,
    client: TestClient,
    seeded_session,
) -> None:
    _, settings = seeded_session
    headers = _auth(client, settings)
    pid = _create_project_multipart(client, headers)["project"]["id"]
    _approve_through_features(client, headers, mock_gen, pid)
    mock_gen.side_effect = [*_gemini_estimate_calls(), *_gemini_estimate_calls()]
    v1 = client.post(
        f"/projects/{pid}/steps/estimate/generate",
        headers=headers,
        json={"inputs": _team_inputs()},
    ).json()["version"]["id"]
    edited = _team_inputs()
    edited["team"][0]["headcount"] = 4
    rev = client.post(
        f"/step-versions/{v1}/request-changes",
        headers=headers,
        json={"instructions": "Split QA hours into task lines.", "inputs": edited},
    )
    assert rev.status_code == 202, rev.text
    v2 = rev.json()["version"]["id"]
    d1 = client.get(f"/step-versions/{v1}", headers=headers).json()
    d2 = client.get(f"/step-versions/{v2}", headers=headers).json()
    assert d2["inputs"]["user_inputs"]["team"][0]["headcount"] == 4
    w1 = d1["content"]["computed"]["totals"]["weeks"]
    w2 = d2["content"]["computed"]["totals"]["weeks"]
    assert w2 <= w1
    assert (
        client.post(f"/step-versions/{v2}/approve", headers=headers, json={}).status_code
        == 200
    )


@patch("app.services.step_generation.generate_structured_result")
def test_team_only_recompute_skips_llm(
    mock_gen: MagicMock,
    client: TestClient,
    seeded_session,
) -> None:
    _, settings = seeded_session
    headers = _auth(client, settings)
    pid = _create_project_multipart(client, headers)["project"]["id"]
    _approve_through_features(client, headers, mock_gen, pid)
    mock_gen.side_effect = _gemini_estimate_calls()
    v1 = client.post(
        f"/projects/{pid}/steps/estimate/generate",
        headers=headers,
        json={"inputs": _team_inputs()},
    ).json()["version"]["id"]
    calls_after_generate = mock_gen.call_count
    edited = _team_inputs()
    edited["team"][0]["headcount"] = 4
    rev = client.post(
        f"/step-versions/{v1}/request-changes",
        headers=headers,
        json={"instructions": "Recalculate with the updated team.", "inputs": edited},
    )
    assert rev.status_code == 202, rev.text
    assert mock_gen.call_count == calls_after_generate
    v2 = rev.json()["version"]["id"]
    d1 = client.get(f"/step-versions/{v1}", headers=headers).json()
    d2 = client.get(f"/step-versions/{v2}", headers=headers).json()
    assert d2["inputs"].get("team_recompute") == 1
    assert d2["content"]["schema_version"] == 2
    assert d2["content"]["computed"]["totals"]["hours_without_ai"] == d1["content"][
        "computed"
    ]["totals"]["hours_without_ai"]
    assert d2["content"]["computed"]["totals"]["weeks"] <= d1["content"]["computed"][
        "totals"
    ]["weeks"]


@patch("app.services.step_generation.generate_structured_result")
def test_batch_fail_saves_nothing(
    mock_gen: MagicMock,
    client: TestClient,
    seeded_session,
) -> None:
    _, settings = seeded_session
    headers = _auth(client, settings)
    pid = _create_project_multipart(client, headers)["project"]["id"]
    _approve_through_features(client, headers, mock_gen, pid)
    mock_gen.side_effect = [_gemini_planning(), LLMError("batch failed")]
    vid = client.post(
        f"/projects/{pid}/steps/estimate/generate",
        headers=headers,
        json={"inputs": _team_inputs()},
    ).json()["version"]["id"]
    detail = client.get(f"/step-versions/{vid}", headers=headers).json()
    assert detail["status"] == "failed"
    assert detail["content"] is None

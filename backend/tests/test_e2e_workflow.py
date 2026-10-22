"""Workflow E2E: mocked generation through estimate; sprint plan with seeded prerequisites."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings
from app.db import reset_engine
from app.main import app as fastapi_app
from app.models.auth import User
from app.models.steps import StepVersion
from app.security.rate_limit import login_rate_limiter
from app.seed import run_seed
from app.services.step_generation import reset_generation_limits_for_tests
from app.steps.schemas.sprint_plan import (
    SprintPlanAssembled,
    SprintPlanPasses,
    SprintPlanStored,
)
from tests.db_utils import reset_rbac_test_data
from tests.e2e.workflow_seed import seed_sprint_plan_prerequisites
from tests.test_estimate import (
    _approve_through_features,
    _gemini_estimate_calls,
    _team_inputs,
)
from tests.test_projects import _auth, _create_project_multipart
from tests.test_steps import _mock_gemini_success


@pytest.fixture(autouse=True)
def _workflow_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "JWT_SECRET",
        "test-jwt-secret-at-least-thirty-two-characters-long",
    )
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ADMIN_EMAIL", "workflow-e2e@example.test")
    monkeypatch.setenv("ADMIN_PASSWORD", "workflow-e2e-pass")
    monkeypatch.setenv("ADMIN_FULL_NAME", "Workflow E2E")
    monkeypatch.setenv("GENERATION_TIMEOUT_SECONDS", "300")
    get_settings.cache_clear()
    login_rate_limiter._failures.clear()
    reset_generation_limits_for_tests()
    yield
    get_settings.cache_clear()
    reset_generation_limits_for_tests()


@pytest.fixture(autouse=True)
def clean_db(migrated_test_engine) -> None:
    with migrated_test_engine.begin() as connection:
        reset_rbac_test_data(connection)


@pytest.fixture
def seeded_session(
    migrated_test_engine,
    _workflow_env: None,
) -> tuple[sessionmaker[Session], Settings]:
    settings = get_settings()
    factory = sessionmaker(bind=migrated_test_engine, autoflush=False, autocommit=False)
    with factory() as session:
        run_seed(session, settings)
        session.commit()
    return factory, settings


@pytest.fixture
def client(seeded_session) -> TestClient:
    reset_engine()
    return TestClient(fastapi_app)


@patch("app.services.step_generation.generate_structured_result")
def test_e2e_workflow_scope_through_estimate_approve(
    mock_gen: MagicMock,
    client: TestClient,
    seeded_session,
) -> None:
    _, settings = seeded_session
    headers = _auth(client, settings)
    pid = _create_project_multipart(client, headers)["project"]["id"]

    _approve_through_features(client, headers, mock_gen, pid)
    mock_gen.side_effect = _gemini_estimate_calls()
    est = client.post(
        f"/projects/{pid}/steps/estimate/generate",
        headers=headers,
        json={"inputs": _team_inputs()},
    )
    assert est.status_code == 202
    est_id = est.json()["version"]["id"]
    assert (
        client.post(f"/step-versions/{est_id}/approve", headers=headers, json={}).status_code
        == 200
    )

    steps = client.get(f"/projects/{pid}/steps", headers=headers).json()
    by_key = {s["key"]: s for s in steps["steps"]}
    assert by_key["scope_analysis"]["status"] == "approved"
    assert by_key["gap_analysis"]["status"] == "approved"
    assert by_key["feature_list"]["status"] == "approved"
    assert by_key["estimate"]["status"] == "approved"
    assert by_key["sow"]["status"] == "ready"
    assert by_key["sprint_plan"]["status"] == "locked"


def _minimal_sprint_stored() -> SprintPlanStored:
    return SprintPlanStored(
        passes=SprintPlanPasses(),
        stories=[],
        assembled=SprintPlanAssembled(document_reference="SPR-E2E-001"),
    )


@patch("app.services.sprint_plan_generation.run_sprint_plan")
def test_e2e_sprint_plan_generate_with_seeded_prerequisites(
    mock_run: MagicMock,
    client: TestClient,
    seeded_session,
) -> None:
    factory, settings = seeded_session
    headers = _auth(client, settings)
    pid = _create_project_multipart(client, headers)["project"]["id"]

    with factory() as session:
        admin = session.scalar(
            select(User).where(User.email == settings.ADMIN_EMAIL.lower())
        )
        seed_sprint_plan_prerequisites(
            session, project_id=uuid.UUID(pid), admin_id=admin.id if admin else None
        )

    steps_before = client.get(f"/projects/{pid}/steps", headers=headers).json()
    sprint_step = next(s for s in steps_before["steps"] if s["key"] == "sprint_plan")
    assert sprint_step["status"] == "ready"
    assert sprint_step["can_generate"] is True

    stored = _minimal_sprint_stored()
    mock_run.return_value = (
        stored,
        {"validation_notes": {"stories": 0}},
        '{"step":"sprint_plan"}',
        "v1",
        100,
        50,
        1,
    )

    sprint_inputs = {
        "sprint_length_weeks": 2,
        "ceremony_overhead_pct": 10,
        "include_sprint_zero": "yes",
        "hardening_sprint_per_release": "yes",
        "show_story_points": "no",
    }
    resp = client.post(
        f"/projects/{pid}/steps/sprint_plan/generate",
        headers=headers,
        json={"inputs": sprint_inputs},
    )
    assert resp.status_code == 202, resp.text
    version_id = resp.json()["version"]["id"]

    detail = client.get(f"/step-versions/{version_id}", headers=headers).json()
    assert detail["status"] == "in_review"
    assert detail["content"]["assembled"]["document_reference"] == "SPR-E2E-001"
    mock_run.assert_called_once()

    with factory() as session:
        row = session.get(StepVersion, uuid.UUID(version_id))
        assert row is not None
        assert row.step_key == "sprint_plan"


@patch("app.services.step_generation.generate_structured_result")
def test_e2e_generation_failure_surfaces_progress_and_code(
    mock_gen: MagicMock,
    client: TestClient,
    seeded_session,
) -> None:
    from app.llm.gemini import LLMError

    mock_gen.side_effect = LLMError("400 INVALID_ARGUMENT bad schema")
    _, settings = seeded_session
    headers = _auth(client, settings)
    pid = _create_project_multipart(client, headers)["project"]["id"]
    resp = client.post(f"/projects/{pid}/steps/scope_analysis/generate", headers=headers)
    assert resp.status_code == 202
    version_id = resp.json()["version"]["id"]
    detail = client.get(f"/step-versions/{version_id}", headers=headers).json()
    assert detail["status"] == "failed"
    assert detail["inputs"].get("failure_code") in ("llm_schema_rejected", "llm_error", None)

    steps = client.get(f"/projects/{pid}/steps", headers=headers).json()
    scope = steps["steps"][0]
    assert scope["has_failed_attempt"] is True
    latest = scope.get("latest_version") or {}
    if latest.get("failure_code"):
        assert latest["failure_code"]

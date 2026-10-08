from __future__ import annotations

import json
import time
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.db import reset_engine
from app.llm.gemini import LLMError, LLMValidationError, StructuredGenerationResult
from app.main import app as fastapi_app
from app.models.auth import Role, User, UserRole
from app.models.steps import StepVersion
from app.models.system import AuditLog
from app.security.passwords import hash_password
from app.seed import run_seed
from app.services.audit import AuditAction
from app.services.step_generation import (
    ERR_NO_CONTENT,
    reset_generation_limits_for_tests,
)
from app.services.storage import ensure_bucket
from app.steps.schemas.scope_analysis import ScopeAnalysisOutput
from tests.db_utils import reset_rbac_test_data
from tests.test_projects import (
    MINIO,
    _auth,
    _create_project_multipart,
    _login,
    _viewer_headers,
)

pytestmark = pytest.mark.usefixtures("_steps_env")


@pytest.fixture(autouse=True)
def _projects_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "JWT_SECRET",
        "test-jwt-secret-at-least-thirty-two-characters-long",
    )
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ADMIN_EMAIL", "steps-admin@example.test")
    monkeypatch.setenv("ADMIN_PASSWORD", "steps-admin-password")
    monkeypatch.setenv("ADMIN_FULL_NAME", "Steps Admin")
    if MINIO:
        monkeypatch.setenv("S3_BUCKET", get_settings().S3_TEST_BUCKET)
        monkeypatch.setenv("S3_PATH_STYLE", "true")
    get_settings.cache_clear()
    login_rate_limiter = __import__(
        "app.security.rate_limit", fromlist=["login_rate_limiter"]
    ).login_rate_limiter
    login_rate_limiter._failures.clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def seeded_session(
    migrated_test_engine,
    _projects_env: None,
) -> tuple[sessionmaker[Session], object]:
    settings = get_settings()
    factory = sessionmaker(bind=migrated_test_engine, autoflush=False, autocommit=False)
    with factory() as session:
        run_seed(session, settings)
        session.commit()
    if MINIO:
        ensure_bucket(bucket=settings.S3_TEST_BUCKET)
    return factory, settings


@pytest.fixture(autouse=True)
def _steps_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "JWT_SECRET",
        "test-jwt-secret-at-least-thirty-two-characters-long",
    )
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("GENERATION_TIMEOUT_SECONDS", "300")
    monkeypatch.setenv("MAX_CONCURRENT_GENERATIONS", "2")
    get_settings.cache_clear()
    reset_generation_limits_for_tests()
    yield
    get_settings.cache_clear()
    reset_generation_limits_for_tests()


@pytest.fixture(autouse=True)
def clean_db(migrated_test_engine) -> None:
    with migrated_test_engine.begin() as connection:
        reset_rbac_test_data(connection)


@pytest.fixture
def client(seeded_session) -> TestClient:
    reset_engine()
    return TestClient(fastapi_app)


def _analyst_headers(client: TestClient, factory: sessionmaker[Session]) -> dict[str, str]:
    with factory() as session:
        role = session.scalar(select(Role).where(Role.name == "Analyst"))
        assert role is not None
        user = User(
            email="analyst-steps@example.test",
            full_name="Steps Analyst",
            password_hash=hash_password("analyst-pass-12"),
            is_active=True,
        )
        session.add(user)
        session.flush()
        session.add(UserRole(user_id=user.id, role_id=role.id))
        session.commit()
    token = _login(client, "analyst-steps@example.test", "analyst-pass-12")
    return {"Authorization": f"Bearer {token}"}


def _sample_scope_output() -> ScopeAnalysisOutput:
    return ScopeAnalysisOutput.model_validate(
        {
            "executive_summary": "Fictional summary.",
            "objectives": ["Objective A"],
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
                    "risk": "Unclear API",
                    "impact": "Delay",
                    "suggested_mitigation": "Workshop",
                }
            ],
            "dependencies": ["ExampleERP"],
            "assumptions": ["API docs exist"],
        }
    )


def _mock_gemini_success(
    *,
    tokens_in: int = 100,
    tokens_out: int = 200,
    model_id: str = "reported-model",
    api_attempt_count: int = 1,
):
    return StructuredGenerationResult(
        data=_sample_scope_output(),
        model_id=model_id,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        api_attempt_count=api_attempt_count,
    )


@patch("app.services.step_generation.generate_structured_result")
def test_generate_success_path(
    mock_gen: MagicMock,
    client: TestClient,
    seeded_session,
) -> None:
    mock_gen.return_value = _mock_gemini_success()
    factory, settings = seeded_session
    headers = _auth(client, settings)
    created = _create_project_multipart(client, headers)
    pid = created["project"]["id"]

    resp = client.post(f"/projects/{pid}/steps/scope_analysis/generate", headers=headers)
    assert resp.status_code == 202, resp.text
    version_id = resp.json()["version"]["id"]

    detail = client.get(f"/step-versions/{version_id}", headers=headers)
    assert detail.status_code == 200
    body = detail.json()
    assert body["status"] == "in_review"
    assert body["content"]["executive_summary"]
    assert body["tokens_in"] == 100
    assert body["tokens_out"] == 200
    assert body["model_id"] == "reported-model"

    with factory() as session:
        version = session.get(StepVersion, uuid.UUID(version_id))
        assert version is not None
        assert version.assembled_prompt
        deps = session.execute(
            text(
                "SELECT COUNT(*) FROM step_version_dependencies WHERE step_version_id = :id"
            ),
            {"id": version_id},
        ).scalar()
        assert deps == 0
        audits = session.scalars(
            select(AuditLog).where(
                AuditLog.project_id == uuid.UUID(pid),
                AuditLog.action.in_(
                    (
                        AuditAction.STEP_GENERATE_REQUESTED,
                        AuditAction.STEP_GENERATED,
                    )
                ),
            )
        ).all()
        assert len(audits) == 2
        for row in audits:
            assert "Fictional" not in json.dumps(row.meta)


@patch("app.services.step_generation.generate_structured_result")
def test_validation_retry_sums_tokens(
    mock_gen: MagicMock,
    client: TestClient,
    seeded_session,
) -> None:
    mock_gen.return_value = _mock_gemini_success(
        tokens_in=50 + 70,
        tokens_out=10 + 20,
        api_attempt_count=2,
    )
    _, settings = seeded_session
    headers = _auth(client, settings)
    created = _create_project_multipart(client, headers)
    pid = created["project"]["id"]
    resp = client.post(f"/projects/{pid}/steps/scope_analysis/generate", headers=headers)
    version_id = resp.json()["version"]["id"]
    detail = client.get(f"/step-versions/{version_id}", headers=headers).json()
    assert detail["tokens_in"] == 120
    assert detail["tokens_out"] == 30
    assert detail["inputs"]["generation_attempt_count"] == 2


def test_steps_list_no_content(client: TestClient, seeded_session) -> None:
    _, settings = seeded_session
    headers = _auth(client, settings)
    created = _create_project_multipart(client, headers)
    pid = created["project"]["id"]
    resp = client.get(f"/projects/{pid}/steps", headers=headers)
    assert resp.status_code == 200
    payload = resp.json()
    assert len(payload["steps"]) == 8
    text_blob = json.dumps(payload)
    assert "assembled_prompt" not in text_blob
    assert '"content"' not in text_blob
    scope = payload["steps"][0]
    assert scope["key"] == "scope_analysis"
    assert scope["can_generate"] is True
    assert scope["blocked_reason"] is None
    assert payload["steps"][1]["status"] == "locked"


def test_unimplemented_step_409(client: TestClient, seeded_session) -> None:
    _, settings = seeded_session
    headers = _auth(client, settings)
    created = _create_project_multipart(client, headers)
    pid = created["project"]["id"]
    resp = client.post(f"/projects/{pid}/steps/feature_list/generate", headers=headers)
    assert resp.status_code == 409


@patch("app.services.step_generation.project_has_readable_content", return_value=False)
def test_no_readable_content_422(
    _mock_readable: MagicMock,
    client: TestClient,
    seeded_session,
) -> None:
    _, settings = seeded_session
    headers = _auth(client, settings)
    created = _create_project_multipart(client, headers)
    pid = created["project"]["id"]
    resp = client.post(f"/projects/{pid}/steps/scope_analysis/generate", headers=headers)
    assert resp.status_code == 422
    assert resp.json()["detail"] == ERR_NO_CONTENT


@patch("app.services.step_generation.run_generation")
def test_double_generate_409(
    mock_run: MagicMock,
    client: TestClient,
    seeded_session,
) -> None:
    mock_run.return_value = None
    _, settings = seeded_session
    headers = _auth(client, settings)
    created = _create_project_multipart(client, headers)
    pid = created["project"]["id"]
    first = client.post(f"/projects/{pid}/steps/scope_analysis/generate", headers=headers)
    assert first.status_code == 202
    second = client.post(f"/projects/{pid}/steps/scope_analysis/generate", headers=headers)
    assert second.status_code == 409
    factory, _ = seeded_session
    from sqlalchemy import func

    with factory() as session:
        count = session.scalar(
            select(func.count())
            .select_from(StepVersion)
            .where(
                StepVersion.project_id == uuid.UUID(pid),
                StepVersion.step_key == "scope_analysis",
            )
        )
        assert count == 1


@patch("app.services.step_generation.generate_structured_result")
def test_failed_then_regenerate_version_2(
    mock_gen: MagicMock,
    client: TestClient,
    seeded_session,
) -> None:
    mock_gen.side_effect = LLMError("provider down")
    _, settings = seeded_session
    headers = _auth(client, settings)
    created = _create_project_multipart(client, headers)
    pid = created["project"]["id"]
    first = client.post(f"/projects/{pid}/steps/scope_analysis/generate", headers=headers)
    vid = first.json()["version"]["id"]
    failed = client.get(f"/step-versions/{vid}", headers=headers).json()
    assert failed["status"] == "failed"
    assert "provider" not in (failed["error"] or "")

    mock_gen.side_effect = None
    mock_gen.return_value = _mock_gemini_success()
    second = client.post(f"/projects/{pid}/steps/scope_analysis/generate", headers=headers)
    assert second.status_code == 202
    steps = client.get(f"/projects/{pid}/steps", headers=headers).json()
    scope = steps["steps"][0]
    assert scope["can_generate"] is False
    assert scope["has_failed_attempt"] is False
    assert scope["status"] == "in_review"
    assert scope["latest_version"]["version_no"] == 2


@patch("app.services.step_generation.generate_structured_result")
def test_prompt_view_permission(
    mock_gen: MagicMock,
    client: TestClient,
    seeded_session,
) -> None:
    mock_gen.return_value = _mock_gemini_success()
    factory, settings = seeded_session
    headers = _auth(client, settings)
    analyst = _analyst_headers(client, factory)
    created = _create_project_multipart(client, headers)
    pid = created["project"]["id"]
    version_id = client.post(
        f"/projects/{pid}/steps/scope_analysis/generate", headers=headers
    ).json()["version"]["id"]

    denied = client.get(f"/step-versions/{version_id}/prompt", headers=analyst)
    assert denied.status_code == 403

    ok = client.get(f"/step-versions/{version_id}/prompt", headers=headers)
    assert ok.status_code == 200
    assert ok.json()["assembled_prompt"]

    with factory() as session:
        viewed = session.scalar(
            select(AuditLog).where(
                AuditLog.action == AuditAction.PROMPT_VIEWED,
                AuditLog.entity_id == uuid.UUID(version_id),
            )
        )
        assert viewed is not None


def test_permission_matrix(client: TestClient, seeded_session) -> None:
    factory, settings = seeded_session
    headers = _auth(client, settings)
    viewer = _viewer_headers(client, factory)
    created = _create_project_multipart(client, headers)
    pid = created["project"]["id"]

    assert client.get(f"/projects/{pid}/steps").status_code == 401
    assert client.get(f"/projects/{pid}/steps", headers=viewer).status_code == 200
    assert (
        client.post(
            f"/projects/{pid}/steps/scope_analysis/generate", headers=viewer
        ).status_code
        == 403
    )


@patch("app.services.step_generation.generate_structured_result")
def test_lazy_recovery_unblocks_stuck_row(
    mock_gen: MagicMock,
    client: TestClient,
    seeded_session,
    migrated_test_engine,
) -> None:
    mock_gen.return_value = _mock_gemini_success()
    _, settings = seeded_session
    headers = _auth(client, settings)
    created = _create_project_multipart(client, headers)
    pid = uuid.UUID(created["project"]["id"])
    user_id = None
    factory, _ = seeded_session
    with factory() as session:
        from app.models.auth import User as UserModel

        user_id = session.scalar(
            select(UserModel.id).where(UserModel.email == settings.ADMIN_EMAIL)
        )

    old = datetime.now(UTC) - timedelta(seconds=600)
    with migrated_test_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO step_versions (
                    id, project_id, step_key, version_no, status, source,
                    inputs, created_by, created_at, generation_started_at
                )
                VALUES (
                    :id, :pid, 'scope_analysis', 1, 'generating', 'generated',
                    '{}'::jsonb, :uid, :old, :old
                )
                """
            ),
            {"id": uuid.uuid4(), "pid": pid, "uid": user_id, "old": old},
        )

    steps = client.get(f"/projects/{pid}/steps", headers=headers)
    assert steps.json()["steps"][0]["can_generate"] is True

    resp = client.post(
        f"/projects/{pid}/steps/scope_analysis/generate", headers=headers
    )
    assert resp.status_code == 202
    assert resp.json()["version"]["version_no"] == 2


@patch("app.services.step_generation.generate_structured_result")
def test_generation_timeout_slow_mock(
    mock_gen: MagicMock,
    client: TestClient,
    seeded_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GENERATION_TIMEOUT_SECONDS", "0.2")
    get_settings.cache_clear()

    def slow(*args, **kwargs):
        time.sleep(1.0)
        return _mock_gemini_success()

    mock_gen.side_effect = slow
    _, settings = seeded_session
    headers = _auth(client, settings)
    created = _create_project_multipart(client, headers)
    pid = created["project"]["id"]
    resp = client.post(f"/projects/{pid}/steps/scope_analysis/generate", headers=headers)
    version_id = resp.json()["version"]["id"]
    detail = client.get(f"/step-versions/{version_id}", headers=headers).json()
    assert detail["status"] == "failed"
    assert "timed out" in detail["error"].lower()


@patch("app.services.step_generation.generate_structured_result")
def test_llm_validation_failure_generic_error(
    mock_gen: MagicMock,
    client: TestClient,
    seeded_session,
) -> None:
    mock_gen.side_effect = LLMValidationError("validation failed internally")
    _, settings = seeded_session
    headers = _auth(client, settings)
    created = _create_project_multipart(client, headers)
    pid = created["project"]["id"]
    version_id = client.post(
        f"/projects/{pid}/steps/scope_analysis/generate", headers=headers
    ).json()["version"]["id"]
    detail = client.get(f"/step-versions/{version_id}", headers=headers).json()
    assert detail["status"] == "failed"
    assert "validation" not in detail["error"].lower()


@patch("app.services.step_generation.run_generation")
def test_post_generate_accepts_empty_json(
    mock_run: MagicMock,
    client: TestClient,
    seeded_session,
) -> None:
    mock_run.return_value = None
    _, settings = seeded_session
    headers = _auth(client, settings)
    created = _create_project_multipart(client, headers)
    pid = created["project"]["id"]
    no_body = client.post(
        f"/projects/{pid}/steps/scope_analysis/generate", headers=headers
    )
    assert no_body.status_code == 202
    empty = client.post(
        f"/projects/{pid}/steps/scope_analysis/generate",
        headers={**headers, "Content-Type": "application/json"},
        json={},
    )
    assert empty.status_code == 409

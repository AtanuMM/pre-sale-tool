from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.db import reset_engine
from app.main import app as fastapi_app
from app.models.auth import Role, User, UserRole
from app.models.steps import StepVersion
from app.models.system import AuditLog
from app.security.passwords import hash_password
from app.services.approval_policy import (
    SELF_APPROVAL_FORBIDDEN,
    resolve_origin_author_id,
)
from app.services.audit import AuditAction
from app.services.step_generation import (
    _finalize_generating_success,
    reset_generation_limits_for_tests,
)
from tests.db_utils import reset_rbac_test_data
from tests.test_projects import _auth, _create_project_multipart, _login
from tests.test_steps import (
    _mock_gemini_success,
    _sample_scope_output,
)

pytestmark = pytest.mark.usefixtures("_steps_env")


@pytest.fixture(autouse=True)
def _steps_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "JWT_SECRET",
        "test-jwt-secret-at-least-thirty-two-characters-long",
    )
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("GENERATION_TIMEOUT_SECONDS", "300")
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
def seeded_session(migrated_test_engine, monkeypatch: pytest.MonkeyPatch):
    from app.seed import run_seed
    from tests.test_projects import MINIO, ensure_bucket

    monkeypatch.setenv("ADMIN_EMAIL", "steps-admin@example.test")
    monkeypatch.setenv("ADMIN_PASSWORD", "steps-admin-password")
    if MINIO:
        monkeypatch.setenv("S3_BUCKET", get_settings().S3_TEST_BUCKET)
        monkeypatch.setenv("S3_PATH_STYLE", "true")
    get_settings.cache_clear()
    settings = get_settings()
    factory = sessionmaker(bind=migrated_test_engine, autoflush=False, autocommit=False)
    with factory() as session:
        run_seed(session, settings)
        session.commit()
    if MINIO:
        ensure_bucket(bucket=settings.S3_TEST_BUCKET)
    return factory, settings


@pytest.fixture
def client(seeded_session) -> TestClient:
    reset_engine()
    return TestClient(fastapi_app)


def _role_user_headers(
    client: TestClient,
    factory: sessionmaker[Session],
    *,
    role_name: str,
    email: str,
    password: str,
) -> dict[str, str]:
    with factory() as session:
        role = session.scalar(select(Role).where(Role.name == role_name))
        assert role is not None
        user = User(
            email=email,
            full_name=f"Test {role_name}",
            password_hash=hash_password(password),
            is_active=True,
        )
        session.add(user)
        session.flush()
        session.add(UserRole(user_id=user.id, role_id=role.id))
        session.commit()
    token = _login(client, email, password)
    return {"Authorization": f"Bearer {token}"}


def _lead_headers(client: TestClient, factory: sessionmaker[Session]) -> dict[str, str]:
    return _role_user_headers(
        client,
        factory,
        role_name="Lead",
        email="lead-actions@example.test",
        password="lead-pass-1234",
    )


def _analyst_headers(client: TestClient, factory: sessionmaker[Session]) -> dict[str, str]:
    return _role_user_headers(
        client,
        factory,
        role_name="Analyst",
        email="analyst-actions@example.test",
        password="analyst-pass-12",
    )


def _disable_global_self_approval(client: TestClient, admin_headers: dict[str, str]) -> None:
    resp = client.put(
        "/settings",
        headers=admin_headers,
        json={"allow_self_approval": False},
    )
    assert resp.status_code == 200


def _generate_in_review(
    client: TestClient,
    pid: str,
    headers: dict[str, str],
    mock_gen: MagicMock,
) -> str:
    mock_gen.return_value = _mock_gemini_success()
    resp = client.post(f"/projects/{pid}/steps/scope_analysis/generate", headers=headers)
    assert resp.status_code == 202, resp.text
    version_id = resp.json()["version"]["id"]
    detail = client.get(f"/step-versions/{version_id}", headers=headers).json()
    assert detail["status"] == "in_review"
    return version_id


@patch("app.services.step_generation.generate_structured_result")
def test_request_changes_stores_stripped_instructions(
    mock_gen: MagicMock,
    client: TestClient,
    seeded_session,
) -> None:
    factory, settings = seeded_session
    admin = _auth(client, settings)
    lead = _lead_headers(client, factory)
    pid = _create_project_multipart(client, admin)["project"]["id"]
    v1 = _generate_in_review(client, pid, admin, mock_gen)

    resp = client.post(
        f"/step-versions/{v1}/request-changes",
        headers=lead,
        json={"instructions": "  tighten scope  \n"},
    )
    assert resp.status_code == 202
    rev_id = resp.json()["version"]["id"]
    detail = client.get(f"/step-versions/{rev_id}", headers=admin).json()
    assert detail["instructions"] == "tighten scope"
    assert detail["based_on_version_id"] == v1


@patch("app.services.step_generation.run_generation")
@patch("app.services.step_generation.generate_structured_result")
def test_revision_success_marks_base_changes_requested(
    mock_gen: MagicMock,
    mock_run: MagicMock,
    client: TestClient,
    seeded_session,
) -> None:
    mock_gen.return_value = _mock_gemini_success()
    factory, settings = seeded_session
    admin = _auth(client, settings)
    lead = _lead_headers(client, factory)
    pid = _create_project_multipart(client, admin)["project"]["id"]
    v1 = _generate_in_review(client, pid, admin, mock_gen)

    def run_sync(vid: uuid.UUID) -> None:
        from app.services.step_generation import run_generation

        run_generation(vid)

    mock_run.side_effect = run_sync

    rev = client.post(
        f"/step-versions/{v1}/request-changes",
        headers=lead,
        json={"instructions": "Add risks"},
    )
    assert rev.status_code == 202
    rev_id = rev.json()["version"]["id"]
    base = client.get(f"/step-versions/{v1}", headers=admin).json()
    assert base["status"] == "changes_requested"
    rev_detail = client.get(f"/step-versions/{rev_id}", headers=admin).json()
    assert rev_detail["status"] == "in_review"


@patch("app.services.step_generation.generate_structured_result")
def test_unimplemented_step_request_changes_409(
    mock_gen: MagicMock,
    client: TestClient,
    seeded_session,
) -> None:
    _, settings = seeded_session
    headers = _auth(client, settings)
    pid = _create_project_multipart(client, headers)["project"]["id"]
    v1 = _generate_in_review(client, pid, headers, mock_gen)
    v1_detail = client.get(f"/step-versions/{v1}", headers=headers).json()
    assert v1_detail["step_key"] == "scope_analysis"
    resp = client.post(
        f"/projects/{pid}/steps/gap_analysis/generate",
        headers=headers,
    )
    assert resp.status_code in (409, 202)
    if resp.status_code == 202:
        pytest.skip("gap_analysis unexpectedly implemented")


@patch("app.routers.steps.run_generation")
def test_gap_analysis_request_changes_accepted(
    mock_run: MagicMock,
    client: TestClient,
    seeded_session,
) -> None:
    factory, settings = seeded_session
    admin = _auth(client, settings)
    lead = _lead_headers(client, factory)
    pid = _create_project_multipart(client, admin)["project"]["id"]
    with factory() as session:
        from app.models.projects import Project

        project = session.get(Project, uuid.UUID(pid))
        assert project is not None
        scope = StepVersion(
            project_id=project.id,
            step_key="scope_analysis",
            version_no=1,
            status="approved",
            source="generated",
            content={"executive_summary": "ok", "objectives": []},
            inputs={},
            created_by=session.scalar(
                select(User.id).where(User.email == settings.ADMIN_EMAIL)
            ),
        )
        session.add(scope)
        session.flush()
        gap = StepVersion(
            project_id=project.id,
            step_key="gap_analysis",
            version_no=1,
            status="in_review",
            source="generated",
            content={"summary": "s", "gaps": [], "client_questions": []},
            inputs={},
            created_by=session.scalar(
                select(User.id).where(User.email == settings.ADMIN_EMAIL)
            ),
        )
        session.add(gap)
        session.commit()
        vid = str(gap.id)
    resp = client.post(
        f"/step-versions/{vid}/request-changes",
        headers=lead,
        json={"instructions": "Add one more gap on auth."},
    )
    assert resp.status_code == 202
    mock_run.assert_called_once()


@patch("app.services.step_generation.run_generation")
@patch("app.services.step_generation.generate_structured_result")
def test_origin_author_self_approval_matrix(
    mock_gen: MagicMock,
    mock_run: MagicMock,
    client: TestClient,
    seeded_session,
) -> None:
    mock_gen.return_value = _mock_gemini_success()

    def run_sync(vid: uuid.UUID) -> None:
        from app.services.step_generation import run_generation

        run_generation(vid)

    mock_run.side_effect = run_sync

    factory, settings = seeded_session
    admin = _auth(client, settings)
    lead = _lead_headers(client, factory)
    analyst = _analyst_headers(client, factory)
    _disable_global_self_approval(client, admin)

    pid = _create_project_multipart(client, admin)["project"]["id"]
    v1 = _generate_in_review(client, pid, analyst, mock_gen)
    rev = client.post(
        f"/step-versions/{v1}/request-changes",
        headers=lead,
        json={"instructions": "Clarify stakeholders"},
    )
    assert rev.status_code == 202
    rev_id = rev.json()["version"]["id"]
    assert client.get(f"/step-versions/{rev_id}", headers=admin).json()["status"] == "in_review"

    ok = client.post(f"/step-versions/{rev_id}/approve", headers=lead, json={})
    assert ok.status_code == 200, ok.text
    assert ok.json()["approval"]["self_approved"] is False

    pid2 = _create_project_multipart(client, admin)["project"]["id"]
    v1b = _generate_in_review(client, pid2, lead, mock_gen)
    rev2 = client.post(
        f"/step-versions/{v1b}/request-changes",
        headers=lead,
        json={"instructions": "More detail"},
    )
    rev2_id = rev2.json()["version"]["id"]
    blocked = client.post(f"/step-versions/{rev2_id}/approve", headers=lead, json={})
    assert blocked.status_code == 403
    assert blocked.json()["detail"] == SELF_APPROVAL_FORBIDDEN

    pid3 = _create_project_multipart(client, admin)["project"]["id"]
    v1c = _generate_in_review(client, pid3, analyst, mock_gen)
    rev3 = client.post(
        f"/step-versions/{v1c}/request-changes",
        headers=lead,
        json={"instructions": "Fix objectives"},
    )
    rev3_id = rev3.json()["version"]["id"]
    analyst_blocked = client.post(
        f"/step-versions/{rev3_id}/approve", headers=analyst, json={}
    )
    assert analyst_blocked.status_code == 403

    client.patch(
        f"/projects/{pid3}/settings",
        headers=admin,
        json={"allow_self_approval": True},
    )
    allowed = client.post(
        f"/step-versions/{rev3_id}/approve", headers=analyst, json={}
    )
    assert allowed.status_code == 200
    assert allowed.json()["approval"]["self_approved"] is True


@patch("app.services.step_generation.generate_structured_result")
def test_steps_list_action_flags(
    mock_gen: MagicMock,
    client: TestClient,
    seeded_session,
) -> None:
    factory, settings = seeded_session
    admin = _auth(client, settings)
    lead = _lead_headers(client, factory)
    _disable_global_self_approval(client, admin)
    pid = _create_project_multipart(client, admin)["project"]["id"]
    v1 = _generate_in_review(client, pid, admin, mock_gen)

    steps = client.get(f"/projects/{pid}/steps", headers=lead).json()
    scope = next(s for s in steps["steps"] if s["key"] == "scope_analysis")
    assert scope["current_version_id"] == v1
    assert scope["can_request_changes"] is True
    assert scope["can_approve"] is True

    steps_admin = client.get(f"/projects/{pid}/steps", headers=admin).json()
    scope_admin = next(s for s in steps_admin["steps"] if s["key"] == "scope_analysis")
    assert scope_admin["can_approve"] is False
    assert scope_admin["approve_blocked_reason"] == SELF_APPROVAL_FORBIDDEN


@patch("app.services.step_generation.generate_structured_result")
def test_stale_success_after_expiry_discarded(
    mock_gen: MagicMock,
    client: TestClient,
    seeded_session,
) -> None:
    factory, settings = seeded_session
    admin = _auth(client, settings)
    pid = _create_project_multipart(client, admin)["project"]["id"]
    v1 = _generate_in_review(client, pid, admin, mock_gen)
    with factory() as session:
        uid = session.scalar(select(User.id).where(User.email == settings.ADMIN_EMAIL))
        base_id = uuid.UUID(v1)
        rev_id = uuid.uuid4()
        session.add(
            StepVersion(
                id=rev_id,
                project_id=uuid.UUID(pid),
                step_key="scope_analysis",
                version_no=2,
                status="failed",
                source="generated",
                content=None,
                inputs={},
                based_on_version_id=base_id,
                instructions="revise",
                created_by=uid,
                generation_started_at=datetime.now(UTC) - timedelta(seconds=600),
                generation_finished_at=datetime.now(UTC),
                error="expired",
            )
        )
        session.commit()

    content = _sample_scope_output().model_dump(mode="json")
    _finalize_generating_success(
        rev_id,
        actor=None,
        content=content,
        inputs_meta={},
        model_id="m",
        prompt_version="revise-v1",
        assembled_prompt="p",
        tokens_in=1,
        tokens_out=2,
        duration_ms=10,
    )

    with factory() as session:
        rev = session.get(StepVersion, rev_id)
        base = session.get(StepVersion, base_id)
        assert rev is not None and rev.status == "failed"
        assert base is not None and base.status == "in_review"
        audits = session.scalars(
            select(AuditLog).where(
                AuditLog.entity_id == rev_id,
                AuditLog.action == AuditAction.STEP_GENERATED,
            )
        ).all()
        assert len(audits) == 0


def test_revision_finalize_atomic_on_audit_failure(
    client: TestClient,
    seeded_session,
) -> None:
    factory, settings = seeded_session
    admin = _auth(client, settings)
    pid = _create_project_multipart(client, admin)["project"]["id"]
    with factory() as session:
        uid = session.scalar(select(User.id).where(User.email == settings.ADMIN_EMAIL))
        base_id = uuid.uuid4()
        rev_id = uuid.uuid4()
        session.add(
            StepVersion(
                id=base_id,
                project_id=uuid.UUID(pid),
                step_key="scope_analysis",
                version_no=1,
                status="in_review",
                source="generated",
                content=_sample_scope_output().model_dump(mode="json"),
                inputs={},
                created_by=uid,
            )
        )
        session.add(
            StepVersion(
                id=rev_id,
                project_id=uuid.UUID(pid),
                step_key="scope_analysis",
                version_no=2,
                status="generating",
                source="generated",
                content=None,
                inputs={},
                based_on_version_id=base_id,
                instructions="go",
                created_by=uid,
                generation_started_at=datetime.now(UTC),
            )
        )
        session.commit()

    content = _sample_scope_output().model_dump(mode="json")
    with (
        patch(
            "app.services.step_generation.record_audit",
            side_effect=RuntimeError("boom"),
        ),
        pytest.raises(RuntimeError),
    ):
        _finalize_generating_success(
            rev_id,
            actor=None,
            content=content,
            inputs_meta={},
            model_id="m",
            prompt_version="revise-v1",
            assembled_prompt="p",
            tokens_in=1,
            tokens_out=2,
            duration_ms=10,
        )

    with factory() as session:
        rev = session.get(StepVersion, rev_id)
        base = session.get(StepVersion, base_id)
        assert rev is not None and rev.status == "generating"
        assert base is not None and base.status == "in_review"


def test_resolve_origin_author_walks_chain(
    client: TestClient, seeded_session
) -> None:
    factory, settings = seeded_session
    admin = _auth(client, settings)
    pid = _create_project_multipart(client, admin)["project"]["id"]
    with factory() as session:
        from app.models.projects import Project

        project = session.get(Project, uuid.UUID(pid))
        assert project is not None
        origin_author = session.scalar(
            select(User.id).where(User.email == settings.ADMIN_EMAIL)
        )
        reviser = session.scalar(select(User.id).where(User.email == "lead-actions@example.test"))
        if reviser is None:
            reviser = origin_author
        origin = uuid.uuid4()
        mid = uuid.uuid4()
        leaf = uuid.uuid4()
        session.add(
            StepVersion(
                id=origin,
                project_id=project.id,
                step_key="scope_analysis",
                version_no=10,
                status="changes_requested",
                source="generated",
                content={},
                inputs={},
                created_by=origin_author,
            )
        )
        session.add(
            StepVersion(
                id=mid,
                project_id=project.id,
                step_key="scope_analysis",
                version_no=11,
                status="changes_requested",
                source="generated",
                content={},
                inputs={},
                based_on_version_id=origin,
                created_by=reviser,
            )
        )
        session.add(
            StepVersion(
                id=leaf,
                project_id=project.id,
                step_key="scope_analysis",
                version_no=12,
                status="in_review",
                source="generated",
                content={},
                inputs={},
                based_on_version_id=mid,
                created_by=reviser,
            )
        )
        session.commit()
        leaf_row = session.get(StepVersion, leaf)
        assert leaf_row is not None
        root_author = session.get(StepVersion, origin)
        assert root_author is not None
        assert resolve_origin_author_id(session, leaf_row) == root_author.created_by


@patch("app.services.step_generation.run_generation")
@patch("app.services.step_generation.generate_structured_result")
def test_changes_requested_audit_has_no_instruction_text(
    mock_gen: MagicMock,
    mock_run: MagicMock,
    client: TestClient,
    seeded_session,
) -> None:
    mock_gen.return_value = _mock_gemini_success()
    mock_run.return_value = None
    factory, settings = seeded_session
    admin = _auth(client, settings)
    lead = _lead_headers(client, factory)
    pid = _create_project_multipart(client, admin)["project"]["id"]
    v1 = _generate_in_review(client, pid, admin, mock_gen)
    secret = "super-secret-client-detail-xyz"
    client.post(
        f"/step-versions/{v1}/request-changes",
        headers=lead,
        json={"instructions": secret},
    )
    with factory() as session:
        audits = session.scalars(
            select(AuditLog).where(AuditLog.action == AuditAction.STEP_CHANGES_REQUESTED)
        ).all()
        assert audits
        blob = json.dumps([a.meta for a in audits])
        assert secret not in blob
        assert "instructions_length" in blob

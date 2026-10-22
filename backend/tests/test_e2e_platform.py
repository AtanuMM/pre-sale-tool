"""Platform-level E2E: auth, admin, projects (API + TestClient)."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings
from app.db import reset_engine
from app.main import app as fastapi_app
from app.security.rate_limit import login_rate_limiter
from app.seed import run_seed
from tests.db_utils import reset_rbac_test_data
from tests.test_projects import (
    _auth,
    _create_project_multipart,
    _login,
    _viewer_headers,
)


@pytest.fixture(autouse=True)
def _e2e_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "JWT_SECRET",
        "test-jwt-secret-at-least-thirty-two-characters-long",
    )
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ADMIN_EMAIL", "e2e-admin@example.test")
    monkeypatch.setenv("ADMIN_PASSWORD", "e2e-admin-password")
    monkeypatch.setenv("ADMIN_FULL_NAME", "E2E Admin")
    get_settings.cache_clear()
    login_rate_limiter._failures.clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def clean_db(migrated_test_engine) -> None:
    with migrated_test_engine.begin() as connection:
        reset_rbac_test_data(connection)


@pytest.fixture
def seeded_session(
    migrated_test_engine,
    _e2e_env: None,
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


def test_e2e_health_and_auth_session(client: TestClient, seeded_session) -> None:
    assert client.get("/health").json()["status"] == "ok"
    settings = seeded_session[1]
    token = _login(client, settings.ADMIN_EMAIL, settings.ADMIN_PASSWORD)
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == settings.ADMIN_EMAIL.lower()
    logout = client.post("/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert logout.status_code in (200, 204)


def test_e2e_admin_settings_roles_users(client: TestClient, seeded_session) -> None:
    settings = seeded_session[1]
    headers = _auth(client, settings)

    roles = client.get("/roles", headers=headers)
    assert roles.status_code == 200
    assert any(r["name"] == "Admin" for r in roles.json())

    get_settings_resp = client.get("/settings", headers=headers)
    assert get_settings_resp.status_code == 200

    viewer_id = next(r["id"] for r in roles.json() if r["name"] == "Viewer")
    created = client.post(
        "/users",
        headers=headers,
        json={
            "email": "e2e-temp@example.test",
            "full_name": "E2E Temp",
            "password": "e2e-temp-pass1",
            "role_ids": [viewer_id],
        },
    )
    assert created.status_code == 201
    user_id = created.json()["id"]

    deleted = client.delete(f"/users/{user_id}", headers=headers)
    assert deleted.status_code == 204

    viewer = _viewer_headers(client, seeded_session[0])
    assert client.get("/users", headers=viewer).status_code == 403


def test_e2e_project_create_list_archive_delete(client: TestClient, seeded_session) -> None:
    settings = seeded_session[1]
    headers = _auth(client, settings)
    created = _create_project_multipart(
        client,
        headers,
        name="E2E Portal",
        client_name="E2E Client",
        body="End-to-end project body.",
    )
    pid = created["project"]["id"]

    listing = client.get("/projects", headers=headers)
    assert listing.status_code == 200
    assert any(p["id"] == pid for p in listing.json()["items"])

    overview = client.get(f"/projects/{pid}/overview", headers=headers)
    assert overview.status_code == 200
    assert overview.json()["project"]["name"] == "E2E Portal"

    steps = client.get(f"/projects/{pid}/steps", headers=headers)
    assert steps.status_code == 200
    assert len(steps.json()["steps"]) == 8
    assert steps.json()["steps"][0]["key"] == "scope_analysis"
    assert steps.json()["steps"][0]["can_generate"] is True

    archived = client.post(f"/projects/{pid}/archive", headers=headers)
    assert archived.status_code == 200

    restored = client.post(f"/projects/{pid}/restore", headers=headers)
    assert restored.status_code == 200

    deleted = client.delete(f"/projects/{pid}", headers=headers)
    assert deleted.status_code == 204
    assert client.get(f"/projects/{pid}", headers=headers).status_code == 404


def test_e2e_cannot_delete_user_with_workflow_history(
    client: TestClient,
    seeded_session,
) -> None:
    factory, settings = seeded_session
    headers = _auth(client, settings)
    created = _create_project_multipart(client, headers)
    pid = uuid.UUID(created["project"]["id"])

    roles = client.get("/roles", headers=headers).json()
    viewer_id = next(r["id"] for r in roles if r["name"] == "Viewer")
    temp = client.post(
        "/users",
        headers=headers,
        json={
            "email": "e2e-history@example.test",
            "full_name": "History User",
            "password": "e2e-hist-pass1",
            "role_ids": [viewer_id],
        },
    )
    assert temp.status_code == 201
    target_id = uuid.UUID(temp.json()["id"])

    with factory() as session:
        from app.models.steps import StepVersion

        session.add(
            StepVersion(
                project_id=pid,
                step_key="scope_analysis",
                version_no=1,
                status="approved",
                source="generated",
                content={"executive_summary": "x", "objectives": []},
                inputs={},
                created_by=target_id,
            )
        )
        session.commit()

    resp = client.delete(f"/users/{target_id}", headers=headers)
    assert resp.status_code == 409
    assert "workflow" in resp.json()["detail"].lower()

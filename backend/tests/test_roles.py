from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.config import Settings, get_settings
from app.db import reset_engine
from app.models.auth import Role
from app.models.system import AuditLog
from app.security.rate_limit import login_rate_limiter
from app.seed import run_seed
from tests.db_utils import reset_rbac_test_data


@pytest.fixture(autouse=True)
def _roles_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "JWT_SECRET",
        "test-jwt-secret-at-least-thirty-two-characters-long",
    )
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ADMIN_EMAIL", "roles-admin@example.test")
    monkeypatch.setenv("ADMIN_PASSWORD", "roles-admin-password")
    monkeypatch.setenv("ADMIN_FULL_NAME", "Roles Admin")
    get_settings.cache_clear()
    login_rate_limiter._failures.clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def clean_rbac(migrated_test_engine) -> None:
    with migrated_test_engine.begin() as connection:
        reset_rbac_test_data(connection)


@pytest.fixture
def seeded_session(migrated_test_engine, _roles_env: None):
    settings = get_settings()
    factory = sessionmaker(bind=migrated_test_engine, autoflush=False, autocommit=False)
    with factory() as session:
        run_seed(session, settings)
        session.commit()
    return factory, settings


@pytest.fixture
def client(seeded_session, _roles_env: None) -> TestClient:
    get_settings.cache_clear()
    reset_engine()
    from app.main import app

    return TestClient(app)


def _admin_token(client: TestClient, settings: Settings) -> str:
    resp = client.post(
        "/auth/login",
        json={"email": settings.ADMIN_EMAIL, "password": settings.ADMIN_PASSWORD},
    )
    return resp.json()["access_token"]


def test_create_role_and_permissions(client: TestClient, seeded_session) -> None:
    factory, settings = seeded_session
    token = _admin_token(client, settings)

    created = client.post(
        "/roles",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Custom",
            "description": "Custom role",
            "permission_codes": ["project.view", "document.download"],
        },
    )
    assert created.status_code == 201

    with factory() as session:
        audits = session.scalars(
            select(AuditLog).where(AuditLog.action == "role.created")
        ).all()
        assert len(audits) == 1


def test_admin_role_permissions_immutable(client: TestClient, seeded_session) -> None:
    factory, settings = seeded_session
    token = _admin_token(client, settings)
    with factory() as session:
        admin_role = session.scalar(select(Role).where(Role.name == "Admin"))

    resp = client.put(
        f"/roles/{admin_role.id}/permissions",
        headers={"Authorization": f"Bearer {token}"},
        json={"permission_codes": ["project.view"]},
    )
    assert resp.status_code == 409


def test_replace_role_permissions_audits(client: TestClient, seeded_session) -> None:
    factory, settings = seeded_session
    token = _admin_token(client, settings)
    created = client.post(
        "/roles",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Mutable",
            "permission_codes": ["project.view"],
        },
    )
    role_id = created.json()["id"]

    updated = client.put(
        f"/roles/{role_id}/permissions",
        headers={"Authorization": f"Bearer {token}"},
        json={"permission_codes": ["project.view", "project.create"]},
    )
    assert updated.status_code == 200

    with factory() as session:
        audits = session.scalars(
            select(AuditLog).where(AuditLog.action == "role.changed")
        ).all()
        assert len(audits) == 1
        assert "project.create" in audits[0].meta["new"]["permissions"]


def test_permissions_list_forbidden_without_role_manage(
    client: TestClient, seeded_session
) -> None:
    settings = seeded_session[1]
    token = _admin_token(client, settings)
    roles = client.get("/roles", headers={"Authorization": f"Bearer {token}"})
    viewer_id = next(r["id"] for r in roles.json() if r["name"] == "Viewer")
    client.post(
        "/users",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "email": "norole@example.test",
            "full_name": "No Role Manage",
            "password": "norole-pass-12",
            "role_ids": [viewer_id],
        },
    )
    viewer_token = client.post(
        "/auth/login",
        json={"email": "norole@example.test", "password": "norole-pass-12"},
    ).json()["access_token"]
    resp = client.get("/permissions", headers={"Authorization": f"Bearer {viewer_token}"})
    assert resp.status_code == 403

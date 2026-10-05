from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.config import Settings, get_settings
from app.db import reset_engine
from app.models.system import AuditLog
from app.security.rate_limit import login_rate_limiter
from app.seed import run_seed
from tests.db_utils import reset_rbac_test_data


@pytest.fixture(autouse=True)
def _settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "JWT_SECRET",
        "test-jwt-secret-at-least-thirty-two-characters-long",
    )
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ADMIN_EMAIL", "settings-admin@example.test")
    monkeypatch.setenv("ADMIN_PASSWORD", "settings-admin-password")
    monkeypatch.setenv("ADMIN_FULL_NAME", "Settings Admin")
    get_settings.cache_clear()
    login_rate_limiter._failures.clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def clean_rbac(migrated_test_engine) -> None:
    with migrated_test_engine.begin() as connection:
        reset_rbac_test_data(connection)


@pytest.fixture
def seeded_session(migrated_test_engine, _settings_env: None):
    settings = get_settings()
    factory = sessionmaker(bind=migrated_test_engine, autoflush=False, autocommit=False)
    with factory() as session:
        run_seed(session, settings)
        session.commit()
    return factory, settings


@pytest.fixture
def client(seeded_session, _settings_env: None) -> TestClient:
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


def test_settings_unknown_key_422(client: TestClient, seeded_session) -> None:
    settings = seeded_session[1]
    token = _admin_token(client, settings)
    resp = client.put(
        "/settings",
        headers={"Authorization": f"Bearer {token}"},
        json={"allow_self_approval": False, "unknown_key": True},
    )
    assert resp.status_code == 422


def test_settings_update_audits(client: TestClient, seeded_session) -> None:
    factory, settings = seeded_session
    token = _admin_token(client, settings)

    resp = client.put(
        "/settings",
        headers={"Authorization": f"Bearer {token}"},
        json={"allow_self_approval": False},
    )
    assert resp.status_code == 200
    assert resp.json()["allow_self_approval"] is False

    with factory() as session:
        audits = session.scalars(
            select(AuditLog).where(AuditLog.action == "settings.changed")
        ).all()
        assert len(audits) == 1
        assert audits[0].meta["old"]["allow_self_approval"] is True
        assert audits[0].meta["new"]["allow_self_approval"] is False


def test_settings_get_forbidden_without_permission(
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
            "email": "nosettings@example.test",
            "full_name": "No Settings",
            "password": "nosettings-12",
            "role_ids": [viewer_id],
        },
    )
    viewer_token = client.post(
        "/auth/login",
        json={"email": "nosettings@example.test", "password": "nosettings-12"},
    ).json()["access_token"]
    resp = client.get("/settings", headers={"Authorization": f"Bearer {viewer_token}"})
    assert resp.status_code == 403

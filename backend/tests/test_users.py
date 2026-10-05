from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings
from app.db import reset_engine
from app.models.auth import RefreshToken, User
from app.models.system import AuditLog
from app.security.rate_limit import login_rate_limiter
from app.seed import run_seed
from tests.db_utils import reset_rbac_test_data


@pytest.fixture(autouse=True)
def _admin_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "JWT_SECRET",
        "test-jwt-secret-at-least-thirty-two-characters-long",
    )
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ADMIN_EMAIL", "users-admin@example.test")
    monkeypatch.setenv("ADMIN_PASSWORD", "users-admin-password")
    monkeypatch.setenv("ADMIN_FULL_NAME", "Users Admin")
    get_settings.cache_clear()
    login_rate_limiter._failures.clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def clean_rbac(migrated_test_engine) -> None:
    with migrated_test_engine.begin() as connection:
        reset_rbac_test_data(connection)


@pytest.fixture
def seeded_session(
    migrated_test_engine,
    _admin_env: None,
) -> tuple[sessionmaker[Session], Settings]:
    settings = get_settings()
    factory = sessionmaker(bind=migrated_test_engine, autoflush=False, autocommit=False)
    with factory() as session:
        run_seed(session, settings)
        session.commit()
    return factory, settings


@pytest.fixture
def client(seeded_session, _admin_env: None) -> TestClient:
    get_settings.cache_clear()
    reset_engine()
    from app.main import app

    return TestClient(app)


def _login(client: TestClient, email: str, password: str):
    return client.post("/auth/login", json={"email": email, "password": password})


def _admin_token(client: TestClient, settings: Settings) -> str:
    resp = _login(client, settings.ADMIN_EMAIL, settings.ADMIN_PASSWORD)
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _viewer_role_id(client: TestClient, token: str) -> str:
    roles = client.get("/roles", headers={"Authorization": f"Bearer {token}"})
    assert roles.status_code == 200
    viewer = next(r for r in roles.json() if r["name"] == "Viewer")
    return viewer["id"]


def test_list_users_requires_permission(client: TestClient, seeded_session) -> None:
    settings = seeded_session[1]
    token = _admin_token(client, settings)
    ok = client.get("/users", headers={"Authorization": f"Bearer {token}"})
    assert ok.status_code == 200
    assert ok.json()["total"] >= 1

    viewer_id = _viewer_role_id(client, token)
    create = client.post(
        "/users",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "email": "viewer-only@example.test",
            "full_name": "Viewer Only",
            "password": "viewer-pass-12",
            "role_ids": [viewer_id],
        },
    )
    assert create.status_code == 201
    viewer_login = _login(client, "viewer-only@example.test", "viewer-pass-12")
    viewer_token = viewer_login.json()["access_token"]
    forbidden = client.get("/users", headers={"Authorization": f"Bearer {viewer_token}"})
    assert forbidden.status_code == 403


def test_create_user_audit_and_duplicate_email(client: TestClient, seeded_session) -> None:
    factory, settings = seeded_session
    token = _admin_token(client, settings)
    viewer_id = _viewer_role_id(client, token)

    created = client.post(
        "/users",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "email": "New.User@example.test",
            "full_name": "New User",
            "password": "secure-pass-12",
            "role_ids": [viewer_id],
        },
    )
    assert created.status_code == 201
    assert created.json()["email"] == "new.user@example.test"

    with factory() as session:
        audits = session.scalars(
            select(AuditLog).where(AuditLog.action == "user.created")
        ).all()
        assert len(audits) == 1
        assert audits[0].meta["new"]["email"] == "new.user@example.test"

    dup = client.post(
        "/users",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "email": "NEW.USER@example.test",
            "full_name": "Dup",
            "password": "secure-pass-12",
            "role_ids": [viewer_id],
        },
    )
    assert dup.status_code == 409


def test_deactivate_revokes_tokens_and_blocks_login(client: TestClient, seeded_session) -> None:
    factory, settings = seeded_session
    token = _admin_token(client, settings)
    viewer_id = _viewer_role_id(client, token)

    created = client.post(
        "/users",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "email": "deact@example.test",
            "full_name": "Deact Me",
            "password": "deact-pass-12",
            "role_ids": [viewer_id],
        },
    )
    user_id = created.json()["id"]
    login = _login(client, "deact@example.test", "deact-pass-12")
    assert login.status_code == 200

    patch = client.patch(
        f"/users/{user_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"is_active": False},
    )
    assert patch.status_code == 200

    with factory() as session:
        uid = uuid.UUID(user_id)
        open_tokens = session.scalar(
            select(func.count())
            .select_from(RefreshToken)
            .where(RefreshToken.user_id == uid)
            .where(RefreshToken.revoked_at.is_(None))
        )
        assert open_tokens == 0
        audits = session.scalars(
            select(AuditLog)
            .where(AuditLog.action == "user.deactivated")
            .where(AuditLog.entity_id == uid)
        ).all()
        assert len(audits) == 1

    blocked = _login(client, "deact@example.test", "deact-pass-12")
    assert blocked.status_code == 401


def test_self_deactivate_blocked(client: TestClient, seeded_session) -> None:
    settings = seeded_session[1]
    token = _admin_token(client, settings)
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    admin_id = me.json()["id"]

    resp = client.patch(
        f"/users/{admin_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"is_active": False},
    )
    assert resp.status_code == 409


def test_last_admin_cannot_be_deactivated(client: TestClient, seeded_session) -> None:
    factory, settings = seeded_session
    token = _admin_token(client, settings)
    with factory() as session:
        admin = session.scalar(
            select(User).where(func.lower(User.email) == settings.ADMIN_EMAIL.lower())
        )
        assert admin is not None
        admin_id = str(admin.id)

    mgr_role = client.post(
        "/roles",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "UserManagers", "permission_codes": ["user.manage"]},
    )
    mgr_role_id = mgr_role.json()["id"]
    client.post(
        "/users",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "email": "usermgr@example.test",
            "full_name": "User Manager",
            "password": "usermgr-pass1",
            "role_ids": [mgr_role_id],
        },
    )
    mgr_token = _login(client, "usermgr@example.test", "usermgr-pass1").json()[
        "access_token"
    ]

    resp = client.patch(
        f"/users/{admin_id}",
        headers={"Authorization": f"Bearer {mgr_token}"},
        json={"is_active": False},
    )
    assert resp.status_code == 409
    assert "last active Admin" in resp.json()["detail"]


def test_reset_password_revokes_and_audits(client: TestClient, seeded_session) -> None:
    factory, settings = seeded_session
    token = _admin_token(client, settings)
    viewer_id = _viewer_role_id(client, token)
    created = client.post(
        "/users",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "email": "reset@example.test",
            "full_name": "Reset User",
            "password": "reset-pass-12",
            "role_ids": [viewer_id],
        },
    )
    user_id = uuid.UUID(created.json()["id"])
    _login(client, "reset@example.test", "reset-pass-12")

    resp = client.post(
        f"/users/{user_id}/reset-password",
        headers={"Authorization": f"Bearer {token}"},
        json={"password": "new-reset-pass1"},
    )
    assert resp.status_code == 204

    with factory() as session:
        audits = session.scalars(
            select(AuditLog).where(AuditLog.action == "user.password_reset")
        ).all()
        assert len(audits) == 1
        assert "password" not in str(audits[0].meta).lower()

    old_login = _login(client, "reset@example.test", "reset-pass-12")
    assert old_login.status_code == 401
    new_login = _login(client, "reset@example.test", "new-reset-pass1")
    assert new_login.status_code == 200

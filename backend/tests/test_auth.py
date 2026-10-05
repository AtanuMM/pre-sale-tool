from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings
from app.db import reset_engine
from app.models.auth import RefreshToken
from app.models.system import AuditLog
from app.security.rate_limit import login_rate_limiter
from app.seed import run_seed
from tests.db_utils import reset_rbac_test_data


@pytest.fixture(autouse=True)
def _auth_test_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "JWT_SECRET",
        "test-jwt-secret-at-least-thirty-two-characters-long",
    )
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ENABLE_TEST_ROUTES", "true")
    monkeypatch.setenv("ADMIN_EMAIL", "auth-admin@example.test")
    monkeypatch.setenv("ADMIN_PASSWORD", "auth-admin-password")
    monkeypatch.setenv("ADMIN_FULL_NAME", "Auth Admin")
    get_settings.cache_clear()
    login_rate_limiter._failures.clear()
    yield
    get_settings.cache_clear()
    login_rate_limiter._failures.clear()


@pytest.fixture(autouse=True)
def clean_rbac(migrated_test_engine) -> None:
    with migrated_test_engine.begin() as connection:
        reset_rbac_test_data(connection)


@pytest.fixture
def seeded_session(
    migrated_test_engine,
    _auth_test_env: None,
) -> tuple[sessionmaker[Session], Settings]:
    settings = get_settings()
    factory = sessionmaker(bind=migrated_test_engine, autoflush=False, autocommit=False)
    with factory() as session:
        run_seed(session, settings)
        session.commit()
    return factory, settings


@pytest.fixture
def client(seeded_session, _auth_test_env: None) -> TestClient:
    get_settings.cache_clear()
    reset_engine()
    from app.main import app

    return TestClient(app)


def _login(client: TestClient, email: str, password: str):
    return client.post("/auth/login", json={"email": email, "password": password})


def _set_refresh_cookie(client: TestClient, value: str) -> None:
    client.cookies.set("scopedesk_refresh", value, path="/auth")


def test_login_success_and_me(client: TestClient, seeded_session) -> None:
    _, settings = seeded_session
    response = _login(client, settings.ADMIN_EMAIL, settings.ADMIN_PASSWORD)
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert "audit.view" in body["user"]["permissions"]

    me = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["email"] == settings.ADMIN_EMAIL


def test_login_unknown_email_generic_error(client: TestClient, seeded_session) -> None:
    factory, _ = seeded_session
    response = _login(client, "nobody@example.test", "wrong-password")
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"

    with factory() as session:
        count = session.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.action == "user.login_failed")
        )
        assert count == 1


def test_login_wrong_password(client: TestClient, seeded_session) -> None:
    _, settings = seeded_session
    response = _login(client, settings.ADMIN_EMAIL, "not-the-password")
    assert response.status_code == 401


def test_refresh_rotates_cookie(client: TestClient, seeded_session) -> None:
    _, settings = seeded_session
    first = _login(client, settings.ADMIN_EMAIL, settings.ADMIN_PASSWORD)
    cookie_a = first.cookies.get("scopedesk_refresh")
    assert cookie_a
    _set_refresh_cookie(client, cookie_a)

    refreshed = client.post("/auth/refresh")
    assert refreshed.status_code == 200
    cookie_b = refreshed.cookies.get("scopedesk_refresh")
    assert cookie_b
    assert cookie_b != cookie_a


def test_refresh_reuse_revokes_family(client: TestClient, seeded_session) -> None:
    _, settings = seeded_session
    first = _login(client, settings.ADMIN_EMAIL, settings.ADMIN_PASSWORD)
    stolen_cookie = first.cookies.get("scopedesk_refresh")
    assert stolen_cookie

    _set_refresh_cookie(client, stolen_cookie)
    rotate = client.post("/auth/refresh")
    assert rotate.status_code == 200

    _set_refresh_cookie(client, stolen_cookie)
    reuse = client.post("/auth/refresh")
    assert reuse.status_code == 401

    factory, _ = seeded_session
    with factory() as session:
        reuse_audits = session.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.action == "auth.refresh_token_reuse")
        )
        assert reuse_audits == 1

    with factory() as session:
        active = session.scalar(
            select(func.count())
            .select_from(RefreshToken)
            .where(RefreshToken.revoked_at.is_(None))
        )
        assert active == 0


def test_failed_login_audit_persisted_after_401(client: TestClient, seeded_session) -> None:
    factory, _ = seeded_session
    _login(client, "persist-fail@example.test", "wrong")
    with factory() as session:
        row = session.scalar(
            select(AuditLog).where(AuditLog.action == "user.login_failed")
        )
        assert row is not None
        assert row.meta.get("attempted_email") == "persist-fail@example.test"


def test_test_routes_hidden_when_not_dev_or_test(
    monkeypatch: pytest.MonkeyPatch, seeded_session
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ENABLE_TEST_ROUTES", "true")
    get_settings.cache_clear()
    reset_engine()
    import importlib

    import app.main as main_module

    importlib.reload(main_module)
    client = TestClient(main_module.app)
    _, settings = seeded_session
    login = _login(client, settings.ADMIN_EMAIL, settings.ADMIN_PASSWORD)
    token = login.json()["access_token"]
    resp = client.get("/test/protected", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404
    monkeypatch.setenv("APP_ENV", "test")
    get_settings.cache_clear()
    reset_engine()
    importlib.reload(main_module)


def test_logout_clears_session(client: TestClient, seeded_session) -> None:
    _, settings = seeded_session
    login = _login(client, settings.ADMIN_EMAIL, settings.ADMIN_PASSWORD)
    cookie = login.cookies.get("scopedesk_refresh")
    assert cookie
    _set_refresh_cookie(client, cookie)

    logout = client.post("/auth/logout")
    assert logout.status_code == 204

    refresh = client.post("/auth/refresh")
    assert refresh.status_code == 401


def test_protected_route_permission(client: TestClient, seeded_session) -> None:
    _, settings = seeded_session
    login_resp = _login(client, settings.ADMIN_EMAIL, settings.ADMIN_PASSWORD)
    token = login_resp.json()["access_token"]

    ok = client.get(
        "/test/protected",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert ok.status_code == 200
    assert ok.json() == {"ok": True}

    no_auth = client.get("/test/protected")
    assert no_auth.status_code == 401


def test_login_rate_limit(client: TestClient, seeded_session) -> None:
    _, settings = seeded_session
    for _ in range(5):
        resp = _login(client, settings.ADMIN_EMAIL, "bad-password")
        assert resp.status_code == 401

    blocked = _login(client, settings.ADMIN_EMAIL, settings.ADMIN_PASSWORD)
    assert blocked.status_code == 429


def test_audit_rollback_does_not_persist(migrated_test_engine, seeded_session) -> None:
    from app.services.audit import AuditAction, record_audit

    factory, _ = seeded_session
    with factory() as session:
        record_audit(
            session,
            action=AuditAction.USER_LOGIN_FAILED,
            metadata={"attempted_email": "rollback@example.test"},
        )
        session.rollback()

    with factory() as session:
        count = session.scalar(select(func.count()).select_from(AuditLog))
        assert count == 0

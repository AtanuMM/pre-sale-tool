from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings
from app.models.auth import Permission, Role, RolePermission, User
from app.models.system import Setting
from app.security.passwords import hash_password
from app.seed import ALL_PERMISSIONS, ALLOW_SELF_APPROVAL_KEY, run_seed
from tests.db_utils import reset_rbac_test_data


@pytest.fixture
def seed_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("ADMIN_EMAIL", "seed-admin@example.test")
    monkeypatch.setenv("ADMIN_PASSWORD", "seed-test-password")
    monkeypatch.setenv("ADMIN_FULL_NAME", "Seed Admin")
    get_settings.cache_clear()
    settings = get_settings()
    yield settings
    get_settings.cache_clear()


def _session_factory(engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


@pytest.fixture(autouse=True)
def clean_rbac_tables(migrated_test_engine) -> None:
    with migrated_test_engine.begin() as connection:
        reset_rbac_test_data(connection)


def test_seed_creates_permissions_roles_admin_and_setting(
    migrated_test_engine, seed_settings: Settings
) -> None:
    session_local = _session_factory(migrated_test_engine)
    with session_local() as session:
        summary = run_seed(session, seed_settings)
        session.commit()

    assert summary.permissions_created == len(ALL_PERMISSIONS)
    assert summary.roles_created == 4
    assert summary.admin_user_created is True
    assert summary.setting_created is True

    with session_local() as session:
        assert session.scalar(select(func.count()).select_from(Permission)) == len(
            ALL_PERMISSIONS
        )
        assert session.scalar(select(func.count()).select_from(Role)) == 4
        admin = session.scalar(
            select(User).where(User.email == seed_settings.ADMIN_EMAIL)
        )
        assert admin is not None
        setting = session.get(Setting, ALLOW_SELF_APPROVAL_KEY)
        assert setting is not None
        assert setting.value is True


def test_seed_is_idempotent(migrated_test_engine, seed_settings: Settings) -> None:
    session_local = _session_factory(migrated_test_engine)
    with session_local() as session:
        run_seed(session, seed_settings)
        session.commit()
        counts_first = (
            session.scalar(select(func.count()).select_from(Permission)),
            session.scalar(select(func.count()).select_from(Role)),
            session.scalar(select(func.count()).select_from(RolePermission)),
        )

    with session_local() as session:
        summary = run_seed(session, seed_settings)
        session.commit()
        counts_second = (
            session.scalar(select(func.count()).select_from(Permission)),
            session.scalar(select(func.count()).select_from(Role)),
            session.scalar(select(func.count()).select_from(RolePermission)),
        )

    assert counts_first == counts_second
    assert summary.permissions_created == 0
    assert summary.roles_created == 0
    assert summary.role_links_created == 0


def test_existing_admin_password_not_overwritten(
    migrated_test_engine, seed_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    session_local = _session_factory(migrated_test_engine)
    original_hash = hash_password("original-password")

    with session_local() as session:
        session.add(
            User(
                email=seed_settings.ADMIN_EMAIL,
                full_name="Existing Admin",
                password_hash=original_hash,
                is_active=True,
            )
        )
        session.commit()

    monkeypatch.setenv("ADMIN_PASSWORD", "different-password")
    get_settings.cache_clear()
    updated_settings = get_settings()

    with session_local() as session:
        summary = run_seed(session, updated_settings)
        session.commit()
        assert summary.admin_user_existing is True
        assert summary.admin_user_created is False
        admin = session.scalar(
            select(User).where(User.email == seed_settings.ADMIN_EMAIL)
        )
        assert admin is not None
        assert admin.password_hash == original_hash


def test_manual_role_permission_link_survives_reseed(
    migrated_test_engine, seed_settings: Settings
) -> None:
    session_local = _session_factory(migrated_test_engine)
    with session_local() as session:
        run_seed(session, seed_settings)
        session.commit()

    extra_permission_id = uuid.uuid4()
    viewer_id: uuid.UUID
    with session_local() as session:
        viewer = session.scalar(select(Role).where(Role.name == "Viewer"))
        assert viewer is not None
        viewer_id = viewer.id
        session.add(Permission(id=extra_permission_id, code="custom.extra.permission"))
        session.flush()
        session.add(
            RolePermission(role_id=viewer_id, permission_id=extra_permission_id)
        )
        session.commit()

    with session_local() as session:
        run_seed(session, seed_settings)
        session.commit()
        link_exists = session.scalar(
            select(RolePermission.role_id).where(
                RolePermission.role_id == viewer_id,
                RolePermission.permission_id == extra_permission_id,
            )
        )
        assert link_exists is not None

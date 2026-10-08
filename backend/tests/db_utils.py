from __future__ import annotations

import os

from sqlalchemy import Connection, create_engine, text
from sqlalchemy.engine import make_url

from app.config import get_settings


def get_test_database_url() -> str:
    explicit = os.environ.get("TEST_DATABASE_URL")
    if explicit:
        return explicit
    base = make_url(get_settings().DATABASE_URL)
    test_name = "scopedesk_test"
    return base.set(database=test_name).render_as_string(hide_password=False)


def get_admin_database_url(database_url: str) -> str:
    url = make_url(database_url)
    return url.set(database="postgres").render_as_string(hide_password=False)


def ensure_database_exists(database_url: str) -> None:
    url = make_url(database_url)
    db_name = url.database
    if not db_name:
        raise ValueError("Database URL must include a database name")

    admin_engine = create_engine(get_admin_database_url(database_url), isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as connection:
        exists = connection.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": db_name},
        ).scalar()
        if not exists:
            connection.execute(text(f'CREATE DATABASE "{db_name}"'))


def assert_test_database(connection: Connection) -> None:
    db_name = connection.execute(text("SELECT current_database()")).scalar()
    if not db_name or not str(db_name).endswith("_test"):
        raise RuntimeError(
            f"Refusing to reset data: database {db_name!r} does not end with '_test'"
        )


def reset_rbac_test_data(connection: Connection) -> None:
    """Clear RBAC and core project tables (tests only; requires *_test database)."""
    assert_test_database(connection)
    connection.execute(text("ALTER TABLE audit_log DISABLE TRIGGER ALL"))
    connection.execute(text("ALTER TABLE project_inputs DISABLE TRIGGER ALL"))
    connection.execute(text("ALTER TABLE files DISABLE TRIGGER ALL"))
    connection.execute(text("ALTER TABLE approvals DISABLE TRIGGER ALL"))
    connection.execute(text("ALTER TABLE step_version_dependencies DISABLE TRIGGER ALL"))
    connection.execute(text("ALTER TABLE step_versions DISABLE TRIGGER ALL"))
    connection.execute(
        text(
            "TRUNCATE approvals, step_version_dependencies, step_versions, "
            "project_input_files, project_inputs, files, projects, "
            "refresh_tokens, role_permissions, user_roles, settings, "
            "audit_log, users, permissions, roles RESTART IDENTITY CASCADE"
        )
    )
    connection.execute(text("ALTER TABLE step_versions ENABLE TRIGGER ALL"))
    connection.execute(text("ALTER TABLE step_version_dependencies ENABLE TRIGGER ALL"))
    connection.execute(text("ALTER TABLE approvals ENABLE TRIGGER ALL"))
    connection.execute(text("ALTER TABLE files ENABLE TRIGGER ALL"))
    connection.execute(text("ALTER TABLE project_inputs ENABLE TRIGGER ALL"))
    connection.execute(text("ALTER TABLE audit_log ENABLE TRIGGER ALL"))


def expected_tables() -> set[str]:
    return {
        "users",
        "roles",
        "permissions",
        "role_permissions",
        "user_roles",
        "settings",
        "audit_log",
        "refresh_tokens",
        "projects",
        "project_inputs",
        "files",
        "project_input_files",
        "step_versions",
        "step_version_dependencies",
        "approvals",
    }

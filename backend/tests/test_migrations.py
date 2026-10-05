from __future__ import annotations

import uuid

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from tests.db_utils import expected_tables


def test_all_phase1_tables_exist(migrated_test_engine) -> None:
    inspector = inspect(migrated_test_engine)
    tables = set(inspector.get_table_names())
    assert expected_tables() <= tables


def test_users_email_is_unique_case_insensitive(migrated_test_engine) -> None:
    suffix = uuid.uuid4().hex[:8]
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()
    insert_sql = text(
        """
        INSERT INTO users (id, email, full_name, password_hash, is_active)
        VALUES (:id, :email, :full_name, :password_hash, true)
        """
    )
    with migrated_test_engine.begin() as connection:
        connection.execute(
            insert_sql,
            {
                "id": user_a,
                "email": f"Analyst-{suffix}@Example.com",
                "full_name": "Analyst One",
                "password_hash": "hash",
            },
        )
    with migrated_test_engine.begin() as connection, pytest.raises(IntegrityError):
        connection.execute(
            insert_sql,
            {
                "id": user_b,
                    "email": f"analyst-{suffix}@example.com",
                "full_name": "Analyst Two",
                "password_hash": "hash",
            },
        )


def test_roles_name_unique(migrated_test_engine) -> None:
    role_name = f"Admin-{uuid.uuid4().hex[:8]}"
    role_a = uuid.uuid4()
    role_b = uuid.uuid4()
    insert_sql = text("INSERT INTO roles (id, name) VALUES (:id, :name)")
    with migrated_test_engine.begin() as connection:
        connection.execute(insert_sql, {"id": role_a, "name": role_name})
    with migrated_test_engine.begin() as connection, pytest.raises(IntegrityError):
        connection.execute(insert_sql, {"id": role_b, "name": role_name})


def test_permissions_code_unique(migrated_test_engine) -> None:
    code = f"project.view.{uuid.uuid4().hex[:8]}"
    perm_a = uuid.uuid4()
    perm_b = uuid.uuid4()
    insert_sql = text("INSERT INTO permissions (id, code) VALUES (:id, :code)")
    with migrated_test_engine.begin() as connection:
        connection.execute(insert_sql, {"id": perm_a, "code": code})
    with migrated_test_engine.begin() as connection, pytest.raises(IntegrityError):
        connection.execute(insert_sql, {"id": perm_b, "code": code})

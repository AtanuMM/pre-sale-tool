from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from tests.db_utils import expected_tables


def _insert_user(connection, user_id: uuid.UUID | None = None) -> uuid.UUID:
    uid = user_id or uuid.uuid4()
    connection.execute(
        text(
            """
            INSERT INTO users (id, email, full_name, password_hash, is_active)
            VALUES (:id, :email, :full_name, :password_hash, true)
            """
        ),
        {
            "id": uid,
            "email": f"migrate-{uid.hex[:8]}@example.test",
            "full_name": "Migration Test User",
            "password_hash": "hash",
        },
    )
    return uid


def _insert_project(connection, user_id: uuid.UUID, project_id: uuid.UUID | None = None) -> uuid.UUID:
    pid = project_id or uuid.uuid4()
    connection.execute(
        text(
            """
            INSERT INTO projects (id, name, client_name, status, created_by)
            VALUES (:id, :name, :client_name, 'active', :created_by)
            """
        ),
        {
            "id": pid,
            "name": "Test Project",
            "client_name": "Test Client",
            "created_by": user_id,
        },
    )
    return pid


def _insert_input(
    connection,
    *,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    is_followup: bool = False,
    input_id: uuid.UUID | None = None,
) -> uuid.UUID:
    iid = input_id or uuid.uuid4()
    connection.execute(
        text(
            """
            INSERT INTO project_inputs (
                id, project_id, kind, received_at, body, is_followup, created_by
            )
            VALUES (
                :id, :project_id, 'email', :received_at, 'body', :is_followup, :created_by
            )
            """
        ),
        {
            "id": iid,
            "project_id": project_id,
            "received_at": datetime.now(UTC),
            "is_followup": is_followup,
            "created_by": user_id,
        },
    )
    return iid


def test_core_tables_exist(migrated_test_engine) -> None:
    inspector = inspect(migrated_test_engine)
    tables = set(inspector.get_table_names())
    for name in ("projects", "project_inputs", "files", "project_input_files"):
        assert name in tables
    assert expected_tables() <= tables


def test_projects_status_check_rejects_bad_value(migrated_test_engine) -> None:
    with migrated_test_engine.begin() as connection:
        user_id = _insert_user(connection)
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    """
                    INSERT INTO projects (id, name, client_name, status, created_by)
                    VALUES (:id, 'N', 'C', 'invalid', :created_by)
                    """
                ),
                {"id": uuid.uuid4(), "created_by": user_id},
            )


def test_project_inputs_kind_check_rejects_bad_value(migrated_test_engine) -> None:
    with migrated_test_engine.begin() as connection:
        user_id = _insert_user(connection)
        project_id = _insert_project(connection, user_id)
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    """
                    INSERT INTO project_inputs (
                        id, project_id, kind, received_at, body, is_followup, created_by
                    )
                    VALUES (
                        :id, :project_id, 'fax', :received_at, '', false, :created_by
                    )
                    """
                ),
                {
                    "id": uuid.uuid4(),
                    "project_id": project_id,
                    "received_at": datetime.now(UTC),
                    "created_by": user_id,
                },
            )


def test_one_initial_input_per_project(migrated_test_engine) -> None:
    with migrated_test_engine.begin() as connection:
        user_id = _insert_user(connection)
        project_id = _insert_project(connection, user_id)
        _insert_input(connection, project_id=project_id, user_id=user_id, is_followup=False)

    with migrated_test_engine.begin() as connection, pytest.raises(IntegrityError):
        _insert_input(
            connection,
            project_id=project_id,
            user_id=user_id,
            is_followup=False,
        )

    with migrated_test_engine.begin() as connection:
        _insert_input(
            connection,
            project_id=project_id,
            user_id=user_id,
            is_followup=True,
        )


def test_project_inputs_update_delete_truncate_blocked(migrated_test_engine) -> None:
    with migrated_test_engine.begin() as connection:
        user_id = _insert_user(connection)
        project_id = _insert_project(connection, user_id)
        input_id = _insert_input(connection, project_id=project_id, user_id=user_id)

    with migrated_test_engine.begin() as connection, pytest.raises(DBAPIError) as exc:
        connection.execute(
            text("UPDATE project_inputs SET body = 'changed' WHERE id = :id"),
            {"id": input_id},
        )
    assert "project_inputs is append-only" in str(exc.value)

    with migrated_test_engine.begin() as connection, pytest.raises(DBAPIError) as exc:
        connection.execute(
            text("DELETE FROM project_inputs WHERE id = :id"),
            {"id": input_id},
        )
    assert "project_inputs is append-only" in str(exc.value)

    with migrated_test_engine.begin() as connection, pytest.raises(DBAPIError) as exc:
        connection.execute(text("TRUNCATE project_input_files, project_inputs"))
    assert "project_inputs is append-only" in str(exc.value)


def test_audit_log_project_id_foreign_key(migrated_test_engine) -> None:
    user_id = uuid.uuid4()
    project_id = uuid.uuid4()
    bogus_project = uuid.uuid4()
    with migrated_test_engine.begin() as connection:
        _insert_user(connection, user_id)
        _insert_project(connection, user_id, project_id)

    with migrated_test_engine.begin() as connection, pytest.raises(IntegrityError):
        connection.execute(
            text(
                """
                INSERT INTO audit_log (
                    id, actor_email, action, entity_type, project_id
                )
                VALUES (:id, 'test@example.test', 'project.created', 'project', :project_id)
                """
            ),
            {"id": uuid.uuid4(), "project_id": bogus_project},
        )

    audit_id = uuid.uuid4()
    with migrated_test_engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO audit_log (
                    id, actor_email, action, entity_type, project_id
                )
                VALUES (:id, 'test@example.test', 'project.created', 'project', :project_id)
                """
            ),
            {"id": audit_id, "project_id": project_id},
        )
    with migrated_test_engine.begin() as connection:
        row = connection.execute(
            text("SELECT project_id FROM audit_log WHERE id = :id"),
            {"id": audit_id},
        ).one()
        assert row.project_id == project_id

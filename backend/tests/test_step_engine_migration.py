from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from tests.db_utils import expected_tables
from tests.test_projects_migration import _insert_project, _insert_user


def _insert_step_version(
    connection,
    *,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    step_key: str = "scope_analysis",
    version_no: int = 1,
    status: str = "in_review",
    source: str = "generated",
    version_id: uuid.UUID | None = None,
    content: str | None = '{"executive_summary":"x"}',
) -> uuid.UUID:
    vid = version_id or uuid.uuid4()
    connection.execute(
        text(
            """
            INSERT INTO step_versions (
                id, project_id, step_key, version_no, status, source, content, created_by
            )
            VALUES (
                :id, :project_id, :step_key, :version_no, :status, :source,
                CAST(:content AS jsonb), :created_by
            )
            """
        ),
        {
            "id": vid,
            "project_id": project_id,
            "step_key": step_key,
            "version_no": version_no,
            "status": status,
            "source": source,
            "content": content,
            "created_by": user_id,
        },
    )
    return vid


def test_step_tables_exist(migrated_test_engine) -> None:
    inspector = inspect(migrated_test_engine)
    tables = set(inspector.get_table_names())
    for name in ("step_versions", "step_version_dependencies", "approvals"):
        assert name in tables
    assert expected_tables() <= tables


def test_step_versions_status_check_rejects_bad_value(migrated_test_engine) -> None:
    with migrated_test_engine.begin() as connection:
        user_id = _insert_user(connection)
        project_id = _insert_project(connection, user_id)
        with pytest.raises(IntegrityError):
            _insert_step_version(
                connection,
                project_id=project_id,
                user_id=user_id,
                status="not_a_status",
            )


def test_step_versions_partial_unique_in_flight(migrated_test_engine) -> None:
    with migrated_test_engine.begin() as connection:
        user_id = _insert_user(connection)
        project_id = _insert_project(connection, user_id)
        _insert_step_version(
            connection,
            project_id=project_id,
            user_id=user_id,
            status="queued",
        )
        with pytest.raises(IntegrityError):
            _insert_step_version(
                connection,
                project_id=project_id,
                user_id=user_id,
                version_no=2,
                status="generating",
            )


def test_step_versions_partial_unique_approved(migrated_test_engine) -> None:
    with migrated_test_engine.begin() as connection:
        user_id = _insert_user(connection)
        project_id = _insert_project(connection, user_id)
        _insert_step_version(
            connection,
            project_id=project_id,
            user_id=user_id,
            status="approved",
        )
        with pytest.raises(IntegrityError):
            _insert_step_version(
                connection,
                project_id=project_id,
                user_id=user_id,
                version_no=2,
                status="approved",
            )


def test_two_approved_allowed_on_different_steps(migrated_test_engine) -> None:
    with migrated_test_engine.begin() as connection:
        user_id = _insert_user(connection)
        project_id = _insert_project(connection, user_id)
        _insert_step_version(
            connection,
            project_id=project_id,
            user_id=user_id,
            step_key="scope_analysis",
            status="approved",
        )
        _insert_step_version(
            connection,
            project_id=project_id,
            user_id=user_id,
            step_key="gap_analysis",
            version_no=1,
            status="approved",
        )


def test_approved_content_update_rejected(migrated_test_engine) -> None:
    with migrated_test_engine.begin() as connection:
        user_id = _insert_user(connection)
        project_id = _insert_project(connection, user_id)
        vid = _insert_step_version(
            connection,
            project_id=project_id,
            user_id=user_id,
            status="approved",
        )
        with pytest.raises(DBAPIError) as exc:
            connection.execute(
                text(
                    "UPDATE step_versions SET content = '{\"executive_summary\":\"changed\"}'::jsonb "
                    "WHERE id = :id"
                ),
                {"id": vid},
            )
        assert "immutable" in str(exc.value).lower()


def test_approved_to_stale_allowed(migrated_test_engine) -> None:
    with migrated_test_engine.begin() as connection:
        user_id = _insert_user(connection)
        project_id = _insert_project(connection, user_id)
        vid = _insert_step_version(
            connection,
            project_id=project_id,
            user_id=user_id,
            status="approved",
        )
        connection.execute(
            text("UPDATE step_versions SET status = 'stale' WHERE id = :id"),
            {"id": vid},
        )
        status = connection.execute(
            text("SELECT status FROM step_versions WHERE id = :id"),
            {"id": vid},
        ).scalar()
        assert status == "stale"


def test_stale_content_update_rejected(migrated_test_engine) -> None:
    with migrated_test_engine.begin() as connection:
        user_id = _insert_user(connection)
        project_id = _insert_project(connection, user_id)
        vid = _insert_step_version(
            connection,
            project_id=project_id,
            user_id=user_id,
            status="stale",
        )
        with pytest.raises(DBAPIError):
            connection.execute(
                text(
                    "UPDATE step_versions SET content = '{\"executive_summary\":\"x2\"}'::jsonb "
                    "WHERE id = :id"
                ),
                {"id": vid},
            )


def test_superseded_content_update_rejected(migrated_test_engine) -> None:
    with migrated_test_engine.begin() as connection:
        user_id = _insert_user(connection)
        project_id = _insert_project(connection, user_id)
        vid = _insert_step_version(
            connection,
            project_id=project_id,
            user_id=user_id,
            status="superseded",
        )
        with pytest.raises(DBAPIError):
            connection.execute(
                text("UPDATE step_versions SET instructions = 'nope' WHERE id = :id"),
                {"id": vid},
            )


def test_failed_row_update_rejected(migrated_test_engine) -> None:
    with migrated_test_engine.begin() as connection:
        user_id = _insert_user(connection)
        project_id = _insert_project(connection, user_id)
        vid = _insert_step_version(
            connection,
            project_id=project_id,
            user_id=user_id,
            status="failed",
        )
        with pytest.raises(DBAPIError) as exc:
            connection.execute(
                text("UPDATE step_versions SET status = 'queued' WHERE id = :id"),
                {"id": vid},
            )
        assert "failed" in str(exc.value).lower()


def test_non_approved_content_update_allowed(migrated_test_engine) -> None:
    with migrated_test_engine.begin() as connection:
        user_id = _insert_user(connection)
        project_id = _insert_project(connection, user_id)
        vid = _insert_step_version(
            connection,
            project_id=project_id,
            user_id=user_id,
            status="generating",
        )
        connection.execute(
            text(
                "UPDATE step_versions SET content = '{\"executive_summary\":\"done\"}'::jsonb, "
                "status = 'in_review' WHERE id = :id"
            ),
            {"id": vid},
        )


def test_step_versions_delete_rejected(migrated_test_engine) -> None:
    with migrated_test_engine.begin() as connection:
        user_id = _insert_user(connection)
        project_id = _insert_project(connection, user_id)
        vid = _insert_step_version(connection, project_id=project_id, user_id=user_id)
        with pytest.raises(DBAPIError):
            connection.execute(
                text("DELETE FROM step_versions WHERE id = :id"),
                {"id": vid},
            )


def test_approvals_update_rejected(migrated_test_engine) -> None:
    with migrated_test_engine.begin() as connection:
        user_id = _insert_user(connection)
        project_id = _insert_project(connection, user_id)
        vid = _insert_step_version(
            connection,
            project_id=project_id,
            user_id=user_id,
            status="approved",
        )
        approval_id = uuid.uuid4()
        connection.execute(
            text(
                """
                INSERT INTO approvals (id, step_version_id, approved_by, approved_at, self_approved)
                VALUES (:id, :step_version_id, :approved_by, :approved_at, false)
                """
            ),
            {
                "id": approval_id,
                "step_version_id": vid,
                "approved_by": user_id,
                "approved_at": datetime.now(UTC),
            },
        )
        with pytest.raises(DBAPIError):
            connection.execute(
                text("UPDATE approvals SET comment = 'changed' WHERE id = :id"),
                {"id": approval_id},
            )


def test_step_version_dependencies_mutation_rejected(migrated_test_engine) -> None:
    with migrated_test_engine.begin() as connection:
        user_id = _insert_user(connection)
        project_id = _insert_project(connection, user_id)
        v1 = _insert_step_version(
            connection,
            project_id=project_id,
            user_id=user_id,
            status="approved",
        )
        v2 = _insert_step_version(
            connection,
            project_id=project_id,
            user_id=user_id,
            version_no=2,
            status="in_review",
        )
        connection.execute(
            text(
                """
                INSERT INTO step_version_dependencies (step_version_id, depends_on_version_id)
                VALUES (:a, :b)
                """
            ),
            {"a": v2, "b": v1},
        )
        with pytest.raises(DBAPIError):
            connection.execute(
                text(
                    "DELETE FROM step_version_dependencies WHERE step_version_id = :a"
                ),
                {"a": v2},
            )

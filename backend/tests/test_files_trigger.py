from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests.test_projects_migration import _insert_input, _insert_project, _insert_user


def test_files_update_extracted_text_allowed(migrated_test_engine) -> None:
    file_id = uuid.uuid4()
    user_id = uuid.uuid4()
    project_id = uuid.uuid4()
    with migrated_test_engine.begin() as connection:
        _insert_user(connection, user_id)
        _insert_project(connection, user_id, project_id)
        _insert_input(connection, project_id=project_id, user_id=user_id)
        connection.execute(
            text(
                """
                INSERT INTO files (
                    id, storage_key, original_name, mime_type, size_bytes, sha256
                )
                VALUES (
                    :id, :key, 'a.txt', 'text/plain', 1, :sha
                )
                """
            ),
            {"id": file_id, "key": f"uploads/test/{file_id}", "sha": "a" * 64},
        )

    with migrated_test_engine.begin() as connection:
        connection.execute(
            text("UPDATE files SET extracted_text = 'extracted' WHERE id = :id"),
            {"id": file_id},
        )

    with migrated_test_engine.begin() as connection, pytest.raises(DBAPIError) as exc:
        connection.execute(
            text("UPDATE files SET original_name = 'changed.txt' WHERE id = :id"),
            {"id": file_id},
        )
    assert "files is append-only except extracted_text" in str(exc.value)

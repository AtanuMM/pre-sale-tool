from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from app.models.auth import User
from app.models.system import AuditLog
from app.security.passwords import hash_password
from app.services.audit import AuditAction, record_audit
from tests.db_utils import reset_rbac_test_data

APPEND_ONLY_MESSAGE = "audit_log is append-only"


@pytest.fixture(autouse=True)
def clean_audit_test_data(migrated_test_engine) -> None:
    with migrated_test_engine.begin() as connection:
        reset_rbac_test_data(connection)


def _session_local(engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def test_record_audit_persists_on_commit(migrated_test_engine) -> None:
    session_local = _session_local(migrated_test_engine)
    with session_local() as session:
        user = User(
            email="audit-user@example.test",
            full_name="Audit User",
            password_hash=hash_password("pw"),
            is_active=True,
        )
        session.add(user)
        session.flush()
        record_audit(
            session,
            action=AuditAction.USER_CREATED,
            actor=user,
            entity_type="user",
            entity_id=user.id,
        )
        session.commit()

    with session_local() as session:
        count = session.scalar(select(func.count()).select_from(AuditLog))
        assert count == 1


def test_record_audit_rolled_back_leaves_no_row(migrated_test_engine) -> None:
    session_local = _session_local(migrated_test_engine)
    with session_local() as session:
        user = User(
            email="rollback@example.test",
            full_name="Rollback User",
            password_hash=hash_password("pw"),
            is_active=True,
        )
        session.add(user)
        session.flush()
        record_audit(
            session,
            action=AuditAction.USER_CREATED,
            actor=user,
            entity_type="user",
            entity_id=user.id,
        )
        session.rollback()

    with session_local() as session:
        count = session.scalar(select(func.count()).select_from(AuditLog))
        assert count == 0


def test_actor_email_snapshot_after_user_email_change(migrated_test_engine) -> None:
    session_local = _session_local(migrated_test_engine)
    user_id: uuid.UUID
    with session_local() as session:
        user = User(
            email="before@example.test",
            full_name="Snapshot User",
            password_hash=hash_password("pw"),
            is_active=True,
        )
        session.add(user)
        session.flush()
        user_id = user.id
        record_audit(
            session,
            action=AuditAction.USER_UPDATED,
            actor=user,
            entity_type="user",
            entity_id=user.id,
        )
        user.email = "after@example.test"
        session.commit()

    with session_local() as session:
        row = session.scalar(select(AuditLog).where(AuditLog.actor_id == user_id))
        assert row is not None
        assert row.actor_email == "before@example.test"


def _insert_audit_row(migrated_test_engine) -> uuid.UUID:
    session_local = _session_local(migrated_test_engine)
    audit_id: uuid.UUID
    suffix = uuid.uuid4().hex[:8]
    with session_local() as session:
        user = User(
            email=f"immutable-{suffix}@example.test",
            full_name="Immutable Audit",
            password_hash=hash_password("pw"),
            is_active=True,
        )
        session.add(user)
        session.flush()
        entry = record_audit(
            session,
            action=AuditAction.USER_LOGIN,
            actor=user,
            entity_type="user",
            entity_id=user.id,
        )
        session.flush()
        audit_id = entry.id
        session.commit()
    return audit_id


def test_audit_log_update_rejected(migrated_test_engine) -> None:
    audit_id = _insert_audit_row(migrated_test_engine)
    with migrated_test_engine.begin() as connection, pytest.raises(
        DBAPIError, match=APPEND_ONLY_MESSAGE
    ):
        connection.execute(
            text("UPDATE audit_log SET action = :action WHERE id = :id"),
            {"action": "tampered", "id": audit_id},
        )


def test_audit_log_delete_rejected(migrated_test_engine) -> None:
    audit_id = _insert_audit_row(migrated_test_engine)
    with migrated_test_engine.begin() as connection, pytest.raises(
        DBAPIError, match=APPEND_ONLY_MESSAGE
    ):
        connection.execute(
            text("DELETE FROM audit_log WHERE id = :id"),
            {"id": audit_id},
        )


def test_audit_log_truncate_rejected(migrated_test_engine) -> None:
    _insert_audit_row(migrated_test_engine)
    with migrated_test_engine.begin() as connection, pytest.raises(
        DBAPIError, match=APPEND_ONLY_MESSAGE
    ):
        connection.execute(text("TRUNCATE audit_log"))

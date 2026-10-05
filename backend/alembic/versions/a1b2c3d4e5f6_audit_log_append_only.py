"""audit_log append-only triggers

Revision ID: a1b2c3d4e5f6
Revises: 60b07ec4ee7f
Create Date: 2026-10-05 17:30:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "60b07ec4ee7f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DENY_FUNCTION = """
CREATE OR REPLACE FUNCTION audit_log_deny_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION 'audit_log is append-only';
END;
$$;
"""

_CREATE_UPDATE_TRIGGER = """
CREATE TRIGGER audit_log_no_update
BEFORE UPDATE ON audit_log
FOR EACH ROW
EXECUTE FUNCTION audit_log_deny_mutation();
"""

_CREATE_DELETE_TRIGGER = """
CREATE TRIGGER audit_log_no_delete
BEFORE DELETE ON audit_log
FOR EACH ROW
EXECUTE FUNCTION audit_log_deny_mutation();
"""

_CREATE_TRUNCATE_TRIGGER = """
CREATE TRIGGER audit_log_no_truncate
BEFORE TRUNCATE ON audit_log
FOR EACH STATEMENT
EXECUTE FUNCTION audit_log_deny_mutation();
"""


def upgrade() -> None:
    op.execute(_DENY_FUNCTION)
    op.execute(_CREATE_UPDATE_TRIGGER)
    op.execute(_CREATE_DELETE_TRIGGER)
    op.execute(_CREATE_TRUNCATE_TRIGGER)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_log_no_truncate ON audit_log;")
    op.execute("DROP TRIGGER IF EXISTS audit_log_no_delete ON audit_log;")
    op.execute("DROP TRIGGER IF EXISTS audit_log_no_update ON audit_log;")
    op.execute("DROP FUNCTION IF EXISTS audit_log_deny_mutation();")

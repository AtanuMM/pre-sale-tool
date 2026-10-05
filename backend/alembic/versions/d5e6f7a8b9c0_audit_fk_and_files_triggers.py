"""audit_log project FK NO ACTION; files append-only except extracted_text

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-10-05 14:45:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "d5e6f7a8b9c0"
down_revision: str | Sequence[str] | None = "c4d5e6f7a8b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FILES_DENY_FUNCTION = """
CREATE OR REPLACE FUNCTION files_deny_immutable_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF TG_OP = 'UPDATE' THEN
    IF NEW.id IS DISTINCT FROM OLD.id
       OR NEW.storage_key IS DISTINCT FROM OLD.storage_key
       OR NEW.original_name IS DISTINCT FROM OLD.original_name
       OR NEW.mime_type IS DISTINCT FROM OLD.mime_type
       OR NEW.size_bytes IS DISTINCT FROM OLD.size_bytes
       OR NEW.sha256 IS DISTINCT FROM OLD.sha256
       OR NEW.uploaded_by IS DISTINCT FROM OLD.uploaded_by
       OR NEW.created_at IS DISTINCT FROM OLD.created_at
    THEN
      RAISE EXCEPTION 'files is append-only except extracted_text';
    END IF;
    RETURN NEW;
  ELSIF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'files is append-only except extracted_text';
  END IF;
  RETURN NULL;
END;
$$;
"""

_FILES_UPDATE_TRIGGER = """
CREATE TRIGGER files_no_immutable_update
BEFORE UPDATE ON files
FOR EACH ROW
EXECUTE FUNCTION files_deny_immutable_mutation();
"""

_FILES_DELETE_TRIGGER = """
CREATE TRIGGER files_no_delete
BEFORE DELETE ON files
FOR EACH ROW
EXECUTE FUNCTION files_deny_immutable_mutation();
"""

_FILES_TRUNCATE_TRIGGER = """
CREATE TRIGGER files_no_truncate
BEFORE TRUNCATE ON files
FOR EACH STATEMENT
EXECUTE FUNCTION files_deny_immutable_mutation();
"""


def upgrade() -> None:
    op.drop_constraint(
        op.f("fk_audit_log_project_id_projects"),
        "audit_log",
        type_="foreignkey",
    )
    op.create_foreign_key(
        op.f("fk_audit_log_project_id_projects"),
        "audit_log",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="NO ACTION",
    )
    op.execute(_FILES_DENY_FUNCTION)
    op.execute(_FILES_UPDATE_TRIGGER)
    op.execute(_FILES_DELETE_TRIGGER)
    op.execute(_FILES_TRUNCATE_TRIGGER)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS files_no_truncate ON files;")
    op.execute("DROP TRIGGER IF EXISTS files_no_delete ON files;")
    op.execute("DROP TRIGGER IF EXISTS files_no_immutable_update ON files;")
    op.execute("DROP FUNCTION IF EXISTS files_deny_immutable_mutation();")
    op.drop_constraint(
        op.f("fk_audit_log_project_id_projects"),
        "audit_log",
        type_="foreignkey",
    )
    op.create_foreign_key(
        op.f("fk_audit_log_project_id_projects"),
        "audit_log",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="SET NULL",
    )

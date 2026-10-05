"""projects core tables, audit_log project FK, project_inputs append-only

Revision ID: c4d5e6f7a8b9
Revises: b2c3d4e5f6a7
Create Date: 2026-10-05 14:15:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c4d5e6f7a8b9"
down_revision: str | Sequence[str] | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DENY_FUNCTION = """
CREATE OR REPLACE FUNCTION project_inputs_deny_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION 'project_inputs is append-only';
END;
$$;
"""

_CREATE_UPDATE_TRIGGER = """
CREATE TRIGGER project_inputs_no_update
BEFORE UPDATE ON project_inputs
FOR EACH ROW
EXECUTE FUNCTION project_inputs_deny_mutation();
"""

_CREATE_DELETE_TRIGGER = """
CREATE TRIGGER project_inputs_no_delete
BEFORE DELETE ON project_inputs
FOR EACH ROW
EXECUTE FUNCTION project_inputs_deny_mutation();
"""

_CREATE_TRUNCATE_TRIGGER = """
CREATE TRIGGER project_inputs_no_truncate
BEFORE TRUNCATE ON project_inputs
FOR EACH STATEMENT
EXECUTE FUNCTION project_inputs_deny_mutation();
"""


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("client_name", sa.String(length=255), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default="active",
            nullable=False,
        ),
        sa.Column("allow_self_approval", sa.Boolean(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('active', 'completed', 'archived')",
            name=op.f("ck_projects_status"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_projects_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_projects")),
    )
    op.create_table(
        "project_inputs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_from", sa.String(length=320), nullable=True),
        sa.Column("subject", sa.String(length=500), nullable=True),
        sa.Column("body", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "is_followup",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('email', 'document', 'meeting_notes', 'other')",
            name=op.f("ck_project_inputs_kind"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_project_inputs_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_project_inputs_project_id_projects"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_project_inputs")),
    )
    op.create_index(
        "ix_project_inputs_project_id_created_at",
        "project_inputs",
        ["project_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "uq_project_inputs_one_initial_per_project",
        "project_inputs",
        ["project_id"],
        unique=True,
        postgresql_where=sa.text("is_followup IS FALSE"),
    )
    op.create_table(
        "files",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("original_name", sa.String(length=512), nullable=False),
        sa.Column("mime_type", sa.String(length=127), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by"],
            ["users.id"],
            name=op.f("fk_files_uploaded_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_files")),
        sa.UniqueConstraint("storage_key", name=op.f("uq_files_storage_key")),
    )
    op.create_index("ix_files_sha256", "files", ["sha256"], unique=False)
    op.create_table(
        "project_input_files",
        sa.Column("input_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["file_id"],
            ["files.id"],
            name=op.f("fk_project_input_files_file_id_files"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["input_id"],
            ["project_inputs.id"],
            name=op.f("fk_project_input_files_input_id_project_inputs"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "input_id", "file_id", name=op.f("pk_project_input_files")
        ),
    )
    op.create_foreign_key(
        op.f("fk_audit_log_project_id_projects"),
        "audit_log",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.execute(_DENY_FUNCTION)
    op.execute(_CREATE_UPDATE_TRIGGER)
    op.execute(_CREATE_DELETE_TRIGGER)
    op.execute(_CREATE_TRUNCATE_TRIGGER)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS project_inputs_no_truncate ON project_inputs;")
    op.execute("DROP TRIGGER IF EXISTS project_inputs_no_delete ON project_inputs;")
    op.execute("DROP TRIGGER IF EXISTS project_inputs_no_update ON project_inputs;")
    op.execute("DROP FUNCTION IF EXISTS project_inputs_deny_mutation();")
    op.drop_constraint(
        op.f("fk_audit_log_project_id_projects"),
        "audit_log",
        type_="foreignkey",
    )
    op.drop_table("project_input_files")
    op.drop_index("ix_files_sha256", table_name="files")
    op.drop_table("files")
    op.drop_index(
        "uq_project_inputs_one_initial_per_project",
        table_name="project_inputs",
    )
    op.drop_index(
        "ix_project_inputs_project_id_created_at",
        table_name="project_inputs",
    )
    op.drop_table("project_inputs")
    op.drop_table("projects")

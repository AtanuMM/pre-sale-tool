"""step_versions, approvals, dependencies, immutability triggers

Revision ID: e7f8a9b0c1d2
Revises: d5e6f7a8b9c0
Create Date: 2026-10-08 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "e7f8a9b0c1d2"
down_revision: str | Sequence[str] | None = "d5e6f7a8b9c0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STEP_VERSIONS_GUARD_UPDATE = """
CREATE OR REPLACE FUNCTION step_versions_guard_update()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF OLD.status = 'failed' THEN
    RAISE EXCEPTION 'failed step_version rows cannot be updated';
  END IF;

  IF OLD.status IN ('approved', 'stale', 'superseded') THEN
    IF OLD.status = 'approved' AND NEW.status = 'stale' THEN
      NULL;
    ELSIF OLD.status = 'approved' AND NEW.status = 'superseded' THEN
      NULL;
    ELSIF OLD.status = 'stale' AND NEW.status = 'superseded' THEN
      NULL;
    ELSE
      RAISE EXCEPTION 'step_version status transition not allowed from immutable row';
    END IF;

    IF NEW.id IS DISTINCT FROM OLD.id
       OR NEW.project_id IS DISTINCT FROM OLD.project_id
       OR NEW.step_key IS DISTINCT FROM OLD.step_key
       OR NEW.version_no IS DISTINCT FROM OLD.version_no
       OR NEW.source IS DISTINCT FROM OLD.source
       OR NEW.content IS DISTINCT FROM OLD.content
       OR NEW.inputs IS DISTINCT FROM OLD.inputs
       OR NEW.instructions IS DISTINCT FROM OLD.instructions
       OR NEW.section_path IS DISTINCT FROM OLD.section_path
       OR NEW.based_on_version_id IS DISTINCT FROM OLD.based_on_version_id
       OR NEW.model_id IS DISTINCT FROM OLD.model_id
       OR NEW.prompt_version IS DISTINCT FROM OLD.prompt_version
       OR NEW.assembled_prompt IS DISTINCT FROM OLD.assembled_prompt
       OR NEW.tokens_in IS DISTINCT FROM OLD.tokens_in
       OR NEW.tokens_out IS DISTINCT FROM OLD.tokens_out
       OR NEW.error IS DISTINCT FROM OLD.error
       OR NEW.created_by IS DISTINCT FROM OLD.created_by
       OR NEW.created_at IS DISTINCT FROM OLD.created_at
       OR NEW.generation_started_at IS DISTINCT FROM OLD.generation_started_at
       OR NEW.generation_finished_at IS DISTINCT FROM OLD.generation_finished_at
    THEN
      RAISE EXCEPTION 'step_version content is immutable once approved, stale, or superseded';
    END IF;

    RETURN NEW;
  END IF;

  RETURN NEW;
END;
$$;
"""

_STEP_VERSIONS_DENY_DELETE = """
CREATE OR REPLACE FUNCTION step_versions_deny_delete()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION 'step_versions rows cannot be deleted';
END;
$$;
"""

_APPROVALS_DENY = """
CREATE OR REPLACE FUNCTION approvals_deny_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION 'approvals is append-only';
END;
$$;
"""

_DEPS_DENY = """
CREATE OR REPLACE FUNCTION step_version_dependencies_deny_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION 'step_version_dependencies is append-only';
END;
$$;
"""


def upgrade() -> None:
    op.create_table(
        "step_versions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("step_key", sa.String(length=64), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "inputs",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("instructions", sa.Text(), nullable=True),
        sa.Column("section_path", sa.Text(), nullable=True),
        sa.Column("based_on_version_id", sa.UUID(), nullable=True),
        sa.Column("model_id", sa.String(length=128), nullable=True),
        sa.Column("prompt_version", sa.String(length=32), nullable=True),
        sa.Column("assembled_prompt", sa.Text(), nullable=True),
        sa.Column("tokens_in", sa.Integer(), nullable=True),
        sa.Column("tokens_out", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("generation_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("generation_finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ("
            "'queued', 'generating', 'in_review', 'approved', 'failed', "
            "'changes_requested', 'superseded', 'stale'"
            ")",
            name=op.f("ck_step_versions_status"),
        ),
        sa.CheckConstraint(
            "source IN ('generated', 'manual_edit', 'section_regen')",
            name=op.f("ck_step_versions_source"),
        ),
        sa.CheckConstraint("version_no >= 1", name=op.f("ck_step_versions_version_no")),
        sa.ForeignKeyConstraint(
            ["based_on_version_id"],
            ["step_versions.id"],
            name=op.f("fk_step_versions_based_on_version_id_step_versions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_step_versions_created_by_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_step_versions_project_id_projects"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_step_versions")),
        sa.UniqueConstraint(
            "project_id",
            "step_key",
            "version_no",
            name=op.f("uq_step_versions_project_id_step_key_version_no"),
        ),
    )
    op.create_index(
        "ix_step_versions_project_id_step_key_created_at",
        "step_versions",
        ["project_id", "step_key", "created_at"],
        unique=False,
    )
    op.create_index(
        "uq_step_versions_one_in_flight",
        "step_versions",
        ["project_id", "step_key"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'generating')"),
    )
    op.create_index(
        "uq_step_versions_one_approved",
        "step_versions",
        ["project_id", "step_key"],
        unique=True,
        postgresql_where=sa.text("status = 'approved'"),
    )

    op.create_table(
        "step_version_dependencies",
        sa.Column("step_version_id", sa.UUID(), nullable=False),
        sa.Column("depends_on_version_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["depends_on_version_id"],
            ["step_versions.id"],
            name=op.f("fk_step_version_dependencies_depends_on_version_id_step_versions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["step_version_id"],
            ["step_versions.id"],
            name=op.f("fk_step_version_dependencies_step_version_id_step_versions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "step_version_id",
            "depends_on_version_id",
            name=op.f("pk_step_version_dependencies"),
        ),
    )

    op.create_table(
        "approvals",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("step_version_id", sa.UUID(), nullable=False),
        sa.Column("approved_by", sa.UUID(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("self_approved", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["approved_by"],
            ["users.id"],
            name=op.f("fk_approvals_approved_by_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["step_version_id"],
            ["step_versions.id"],
            name=op.f("fk_approvals_step_version_id_step_versions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_approvals")),
        sa.UniqueConstraint("step_version_id", name=op.f("uq_approvals_step_version_id")),
    )

    op.execute(_STEP_VERSIONS_GUARD_UPDATE)
    op.execute(
        """
        CREATE TRIGGER step_versions_guard_update
        BEFORE UPDATE ON step_versions
        FOR EACH ROW
        EXECUTE FUNCTION step_versions_guard_update();
        """
    )
    op.execute(_STEP_VERSIONS_DENY_DELETE)
    op.execute(
        """
        CREATE TRIGGER step_versions_no_delete
        BEFORE DELETE ON step_versions
        FOR EACH ROW
        EXECUTE FUNCTION step_versions_deny_delete();
        """
    )
    op.execute(
        """
        CREATE TRIGGER step_versions_no_truncate
        BEFORE TRUNCATE ON step_versions
        FOR EACH STATEMENT
        EXECUTE FUNCTION step_versions_deny_delete();
        """
    )

    op.execute(_APPROVALS_DENY)
    op.execute(
        """
        CREATE TRIGGER approvals_no_update
        BEFORE UPDATE ON approvals
        FOR EACH ROW
        EXECUTE FUNCTION approvals_deny_mutation();
        """
    )
    op.execute(
        """
        CREATE TRIGGER approvals_no_delete
        BEFORE DELETE ON approvals
        FOR EACH ROW
        EXECUTE FUNCTION approvals_deny_mutation();
        """
    )
    op.execute(
        """
        CREATE TRIGGER approvals_no_truncate
        BEFORE TRUNCATE ON approvals
        FOR EACH STATEMENT
        EXECUTE FUNCTION approvals_deny_mutation();
        """
    )

    op.execute(_DEPS_DENY)
    op.execute(
        """
        CREATE TRIGGER step_version_dependencies_no_update
        BEFORE UPDATE ON step_version_dependencies
        FOR EACH ROW
        EXECUTE FUNCTION step_version_dependencies_deny_mutation();
        """
    )
    op.execute(
        """
        CREATE TRIGGER step_version_dependencies_no_delete
        BEFORE DELETE ON step_version_dependencies
        FOR EACH ROW
        EXECUTE FUNCTION step_version_dependencies_deny_mutation();
        """
    )
    op.execute(
        """
        CREATE TRIGGER step_version_dependencies_no_truncate
        BEFORE TRUNCATE ON step_version_dependencies
        FOR EACH STATEMENT
        EXECUTE FUNCTION step_version_dependencies_deny_mutation();
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS step_version_dependencies_no_truncate "
        "ON step_version_dependencies;"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS step_version_dependencies_no_delete "
        "ON step_version_dependencies;"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS step_version_dependencies_no_update "
        "ON step_version_dependencies;"
    )
    op.execute("DROP FUNCTION IF EXISTS step_version_dependencies_deny_mutation();")

    op.execute("DROP TRIGGER IF EXISTS approvals_no_truncate ON approvals;")
    op.execute("DROP TRIGGER IF EXISTS approvals_no_delete ON approvals;")
    op.execute("DROP TRIGGER IF EXISTS approvals_no_update ON approvals;")
    op.execute("DROP FUNCTION IF EXISTS approvals_deny_mutation();")

    op.execute("DROP TRIGGER IF EXISTS step_versions_no_truncate ON step_versions;")
    op.execute("DROP TRIGGER IF EXISTS step_versions_no_delete ON step_versions;")
    op.execute("DROP TRIGGER IF EXISTS step_versions_guard_update ON step_versions;")
    op.execute("DROP FUNCTION IF EXISTS step_versions_deny_delete();")
    op.execute("DROP FUNCTION IF EXISTS step_versions_guard_update();")

    op.drop_table("approvals")
    op.drop_table("step_version_dependencies")
    op.drop_index("uq_step_versions_one_approved", table_name="step_versions")
    op.drop_index("uq_step_versions_one_in_flight", table_name="step_versions")
    op.drop_index(
        "ix_step_versions_project_id_step_key_created_at",
        table_name="step_versions",
    )
    op.drop_table("step_versions")

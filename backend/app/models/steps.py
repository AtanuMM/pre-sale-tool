from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

STEP_VERSION_STATUSES = (
    "queued",
    "generating",
    "in_review",
    "approved",
    "failed",
    "changes_requested",
    "superseded",
    "stale",
)
STEP_VERSION_SOURCES = ("generated", "manual_edit", "section_regen")


class StepVersion(Base):
    __tablename__ = "step_versions"
    __table_args__ = (
        CheckConstraint(
            "status IN ("
            "'queued', 'generating', 'in_review', 'approved', 'failed', "
            "'changes_requested', 'superseded', 'stale'"
            ")",
            name="ck_step_versions_status",
        ),
        CheckConstraint(
            "source IN ('generated', 'manual_edit', 'section_regen')",
            name="ck_step_versions_source",
        ),
        CheckConstraint("version_no >= 1", name="ck_step_versions_version_no"),
        UniqueConstraint(
            "project_id",
            "step_key",
            "version_no",
            name="uq_step_versions_project_id_step_key_version_no",
        ),
        Index(
            "uq_step_versions_one_in_flight",
            "project_id",
            "step_key",
            unique=True,
            postgresql_where=text("status IN ('queued', 'generating')"),
        ),
        Index(
            "uq_step_versions_one_approved",
            "project_id",
            "step_key",
            unique=True,
            postgresql_where=text("status = 'approved'"),
        ),
        Index("ix_step_versions_project_id_step_key_created_at", "project_id", "step_key", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="RESTRICT"),
        nullable=False,
    )
    step_key: Mapped[str] = mapped_column(String(64), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    inputs: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    section_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    based_on_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("step_versions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    model_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # May contain client text; never expose in list APIs, audit metadata, or logs.
    assembled_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    tokens_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    generation_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    generation_finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class StepVersionDependency(Base):
    __tablename__ = "step_version_dependencies"

    step_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("step_versions.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    depends_on_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("step_versions.id", ondelete="RESTRICT"),
        primary_key=True,
    )


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    step_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("step_versions.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    approved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    self_approved: Mapped[bool] = mapped_column(nullable=False)

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

DerivedStepStatus = Literal[
    "locked",
    "ready",
    "generating",
    "in_review",
    "approved",
    "stale",
]
StepVersionStatus = Literal[
    "queued",
    "generating",
    "in_review",
    "approved",
    "failed",
    "changes_requested",
    "superseded",
    "stale",
]
StepVersionSource = Literal["generated", "manual_edit", "section_regen"]


class StepVersionSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    version_no: int
    status: StepVersionStatus
    source: StepVersionSource
    created_at: datetime
    created_by_name: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    error: str | None = None


class ApprovalOut(BaseModel):
    approved_by_name: str | None
    approved_at: datetime
    comment: str | None
    self_approved: bool


class StepLayoutColumnOut(BaseModel):
    key: str
    header: str


class StepLayoutSectionOut(BaseModel):
    key: str
    title: str
    kind: str
    copyable: bool = False
    columns: list[StepLayoutColumnOut] = []
    record_fields: list[StepLayoutColumnOut] = []
    badge_fields: list[str] = []


class StepContextStepOut(BaseModel):
    key: str
    title: str


class ProjectStepOut(BaseModel):
    key: str
    title: str
    order: int
    implemented: bool
    status: DerivedStepStatus
    has_failed_attempt: bool
    can_generate: bool
    blocked_reason: str | None = None
    current_version_id: uuid.UUID | None = None
    can_request_changes: bool = False
    can_approve: bool = False
    approve_blocked_reason: str | None = None
    latest_version: StepVersionSummaryOut | None = None
    layout: list[StepLayoutSectionOut] = []
    reads_description: str = ""
    writes_description: str = ""
    context_steps: list[StepContextStepOut] = []


class ProjectStepsOut(BaseModel):
    steps: list[ProjectStepOut]


class StepVersionDetailOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    step_key: str
    version_no: int
    status: StepVersionStatus
    source: StepVersionSource
    content: dict | None
    inputs: dict
    based_on_version_id: uuid.UUID | None
    instructions: str | None
    error: str | None
    model_id: str | None
    prompt_version: str | None
    tokens_in: int | None
    tokens_out: int | None
    created_at: datetime
    created_by_name: str | None
    generation_started_at: datetime | None
    generation_finished_at: datetime | None
    approval: ApprovalOut | None = None


class StepVersionPromptOut(BaseModel):
    step_version_id: uuid.UUID
    assembled_prompt: str


class GenerateStepAcceptedOut(BaseModel):
    version: StepVersionSummaryOut


class RequestChangesAcceptedOut(BaseModel):
    version: StepVersionSummaryOut

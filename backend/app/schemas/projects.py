from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

InputKind = Literal["email", "document", "meeting_notes", "other"]
ProjectStatus = Literal["active", "completed", "archived"]
ExtractionStatus = Literal["ok", "empty", "truncated"]


class ProjectSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    client_name: str
    status: ProjectStatus
    allow_self_approval: bool | None
    created_by_name: str | None
    created_at: datetime
    completed_at: datetime | None = None


class ProjectListItemOut(BaseModel):
    id: uuid.UUID
    name: str
    client_name: str
    status: ProjectStatus
    created_by_name: str | None
    created_at: datetime


class ProjectListOut(BaseModel):
    items: list[ProjectListItemOut]
    total: int


class FileSummaryOut(BaseModel):
    id: uuid.UUID
    original_name: str
    mime_type: str
    size_bytes: int
    sha256: str
    extraction_status: ExtractionStatus
    extracted_char_count: int


class InputOut(BaseModel):
    id: uuid.UUID
    kind: InputKind
    received_at: datetime
    received_from: str | None
    subject: str | None
    body: str
    is_followup: bool
    created_by_name: str | None
    created_at: datetime
    files: list[FileSummaryOut]


class ProjectIntakeLimitsOut(BaseModel):
    max_file_bytes: int
    max_files_per_input: int
    allowed_extensions: list[str]
    max_extracted_chars: int


class TimelineEntryOut(BaseModel):
    action: str
    actor_name: str
    occurred_at: datetime


class ProjectOverviewOut(BaseModel):
    project: ProjectSummaryOut
    effective_allow_self_approval: bool
    inputs: list[InputOut]
    timeline: list[TimelineEntryOut]


class ProjectCreateOut(BaseModel):
    project: ProjectSummaryOut
    input: InputOut
    files: list[FileSummaryOut]


class FileTextOut(BaseModel):
    extraction_status: ExtractionStatus
    extracted_char_count: int
    text: str


class ProjectSettingsPatch(BaseModel):
    allow_self_approval: bool | None = Field(
        ...,
        description="Per-project override; null uses global setting.",
    )


class ProjectSettingsOut(BaseModel):
    allow_self_approval: bool | None
    effective_allow_self_approval: bool

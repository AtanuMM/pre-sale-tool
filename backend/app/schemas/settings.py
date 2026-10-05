from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class SettingsOut(BaseModel):
    allow_self_approval: bool


class SettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allow_self_approval: bool | None = None

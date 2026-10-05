from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class PermissionOut(BaseModel):
    id: uuid.UUID
    code: str

    model_config = {"from_attributes": True}


class RoleOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    permissions: list[str]


class RoleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    permission_codes: list[str] = Field(default_factory=list)


class RolePermissionsUpdate(BaseModel):
    permission_codes: list[str]

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class RoleBrief(BaseModel):
    id: uuid.UUID
    name: str

    model_config = {"from_attributes": True}


class UserAdmin(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    is_active: bool
    last_login_at: datetime | None
    roles: list[RoleBrief]

    model_config = {"from_attributes": True}


class UserListResponse(BaseModel):
    items: list[UserAdmin]
    total: int


class UserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    full_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=12, max_length=512)
    role_ids: list[uuid.UUID] = Field(min_length=1)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        local, sep, domain = normalized.partition("@")
        if not sep or not local or not domain:
            raise ValueError("Invalid email")
        return normalized


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    is_active: bool | None = None
    role_ids: list[uuid.UUID] | None = Field(default=None, min_length=1)


class ResetPasswordRequest(BaseModel):
    password: str = Field(min_length=12, max_length=512)

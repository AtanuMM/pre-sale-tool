from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.auth import User
from app.schemas.settings import SettingsOut, SettingsUpdate
from app.security.deps import require_permission
from app.services.audit import (
    AuditAction,
    client_ip_from_request,
    record_audit,
    user_agent_from_request,
)
from app.services.settings_admin import apply_settings_updates, get_settings_out

router = APIRouter(prefix="/settings", tags=["settings"])

_manage = require_permission("settings.manage")


@router.get("", response_model=SettingsOut)
def read_settings(
    db: Annotated[Session, Depends(get_db)],
    _actor: Annotated[User, Depends(_manage)],
) -> SettingsOut:
    return get_settings_out(db)


@router.put("", response_model=SettingsOut)
def update_settings(
    body: SettingsUpdate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[User, Depends(_manage)],
) -> SettingsOut:
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one setting must be provided",
        )

    try:
        new_out, old_values, new_values = apply_settings_updates(
            db, updates=updates, actor=actor
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    if old_values != new_values:
        record_audit(
            db,
            action=AuditAction.SETTINGS_CHANGED,
            actor=actor,
            entity_type="setting",
            metadata={"old": old_values, "new": new_values},
            ip_address=client_ip_from_request(request),
            user_agent=user_agent_from_request(request),
        )
        db.commit()

    return new_out

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.models.auth import User
from app.schemas.users import (
    ResetPasswordRequest,
    RoleBrief,
    UserAdmin,
    UserCreate,
    UserListResponse,
    UserUpdate,
)
from app.security.deps import require_permission
from app.security.passwords import hash_password
from app.security.refresh_tokens import revoke_all_for_user
from app.services.audit import (
    AuditAction,
    client_ip_from_request,
    record_audit,
    user_agent_from_request,
)
from app.services.rbac_admin import (
    find_user_by_email_insensitive,
    is_sole_active_admin,
    load_user_admin_view,
    replace_user_roles,
    resolve_roles_by_ids,
    role_names,
    would_remove_admin_role,
)

router = APIRouter(prefix="/users", tags=["users"])

_manage = require_permission("user.manage")


def _to_user_admin(user: User) -> UserAdmin:
    return UserAdmin(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        last_login_at=user.last_login_at,
        roles=[RoleBrief(id=r.id, name=r.name) for r in user.roles],
    )


@router.get("", response_model=UserListResponse)
def list_users(
    db: Annotated[Session, Depends(get_db)],
    _actor: Annotated[User, Depends(_manage)],
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> UserListResponse:
    total = db.scalar(select(func.count()).select_from(User)) or 0
    users = db.scalars(
        select(User)
        .options(selectinload(User.roles))
        .order_by(User.email)
        .limit(limit)
        .offset(offset)
    ).all()
    return UserListResponse(items=[_to_user_admin(u) for u in users], total=total)


@router.post("", response_model=UserAdmin, status_code=status.HTTP_201_CREATED)
def create_user(
    body: UserCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[User, Depends(_manage)],
) -> UserAdmin:
    if find_user_by_email_insensitive(db, body.email) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists",
        )

    try:
        roles = resolve_roles_by_ids(db, body.role_ids)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    user = User(
        email=body.email,
        full_name=body.full_name.strip(),
        password_hash=hash_password(body.password),
        is_active=True,
    )
    db.add(user)
    db.flush()
    replace_user_roles(db, user, [r.id for r in roles])
    db.flush()
    user = load_user_admin_view(db, user.id)
    assert user is not None

    record_audit(
        db,
        action=AuditAction.USER_CREATED,
        actor=actor,
        entity_type="user",
        entity_id=user.id,
        metadata={
            "new": {
                "email": user.email,
                "full_name": user.full_name,
                "is_active": user.is_active,
                "roles": role_names(user),
            }
        },
        ip_address=client_ip_from_request(request),
        user_agent=user_agent_from_request(request),
    )
    db.commit()
    user = load_user_admin_view(db, user.id)
    assert user is not None
    return _to_user_admin(user)


@router.patch("/{user_id}", response_model=UserAdmin)
def update_user(
    user_id: uuid.UUID,
    body: UserUpdate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[User, Depends(_manage)],
) -> UserAdmin:
    user = load_user_admin_view(db, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if body.full_name is None and body.is_active is None and body.role_ids is None:
        return _to_user_admin(user)

    if (
        body.is_active is False
        and actor.id == user.id
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You cannot deactivate your own account",
        )

    old_snapshot = {
        "full_name": user.full_name,
        "is_active": user.is_active,
        "roles": role_names(user),
    }

    if body.is_active is False and user.is_active and is_sole_active_admin(db, user):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot deactivate the last active Admin user",
        )

    if body.role_ids is not None:
        try:
            roles = resolve_roles_by_ids(db, body.role_ids)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
            ) from exc
        new_ids = {r.id for r in roles}
        if (
            user.is_active
            and would_remove_admin_role(db, user, new_ids)
            and is_sole_active_admin(db, user)
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot remove the Admin role from the last active Admin user",
            )
        replace_user_roles(db, user, list(new_ids))
        db.refresh(user, attribute_names=["roles"])

    if body.full_name is not None:
        user.full_name = body.full_name.strip()

    deactivated = False
    if body.is_active is not None and body.is_active != user.is_active:
        user.is_active = body.is_active
        if not user.is_active:
            deactivated = True
            revoke_all_for_user(db, user.id)

    new_snapshot = {
        "full_name": user.full_name,
        "is_active": user.is_active,
        "roles": role_names(user),
    }

    if old_snapshot != new_snapshot:
        record_audit(
            db,
            action=AuditAction.USER_DEACTIVATED if deactivated else AuditAction.USER_UPDATED,
            actor=actor,
            entity_type="user",
            entity_id=user.id,
            metadata={"old": old_snapshot, "new": new_snapshot},
            ip_address=client_ip_from_request(request),
            user_agent=user_agent_from_request(request),
        )
        db.commit()

    user = load_user_admin_view(db, user.id)
    assert user is not None
    return _to_user_admin(user)


@router.post("/{user_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(
    user_id: uuid.UUID,
    body: ResetPasswordRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[User, Depends(_manage)],
) -> None:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.password_hash = hash_password(body.password)
    revoke_all_for_user(db, user.id)

    record_audit(
        db,
        action=AuditAction.USER_PASSWORD_RESET,
        actor=actor,
        entity_type="user",
        entity_id=user.id,
        metadata={"target_user_id": str(user.id), "target_email": user.email},
        ip_address=client_ip_from_request(request),
        user_agent=user_agent_from_request(request),
    )
    db.commit()

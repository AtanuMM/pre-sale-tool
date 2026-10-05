from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.models.auth import Permission, Role, RolePermission, User
from app.schemas.roles import PermissionOut, RoleCreate, RoleOut, RolePermissionsUpdate
from app.security.deps import require_permission
from app.seed import ADMIN_ROLE_NAME
from app.services.audit import (
    AuditAction,
    client_ip_from_request,
    record_audit,
    user_agent_from_request,
)

router = APIRouter(tags=["roles"])

_manage = require_permission("role.manage")


def _permission_codes(role: Role) -> list[str]:
    return sorted(perm.code for perm in role.permissions)


def _permission_codes_for_role(session: Session, role_id: uuid.UUID) -> list[str]:
    codes = session.scalars(
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .where(RolePermission.role_id == role_id)
        .order_by(Permission.code)
    ).all()
    return list(codes)


def _permission_codes_for_role(session: Session, role_id: uuid.UUID) -> list[str]:
    codes = session.scalars(
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .where(RolePermission.role_id == role_id)
        .order_by(Permission.code)
    ).all()
    return list(codes)


def _to_role_out(role: Role) -> RoleOut:
    return RoleOut(
        id=role.id,
        name=role.name,
        description=role.description,
        permissions=_permission_codes(role),
    )


def _resolve_permissions(session: Session, codes: list[str]) -> list[Permission]:
    if not codes:
        return []
    unique = sorted(set(codes))
    perms = list(session.scalars(select(Permission).where(Permission.code.in_(unique))).all())
    if len(perms) != len(unique):
        found = {p.code for p in perms}
        unknown = sorted(set(unique) - found)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown permission codes: {unknown}",
        )
    return perms


def _replace_role_permissions(session: Session, role: Role, permissions: list[Permission]) -> None:
    session.execute(delete(RolePermission).where(RolePermission.role_id == role.id))
    for perm in permissions:
        session.add(RolePermission(role_id=role.id, permission_id=perm.id))


@router.get("/permissions", response_model=list[PermissionOut])
def list_permissions(
    db: Annotated[Session, Depends(get_db)],
    _actor: Annotated[User, Depends(_manage)],
) -> list[PermissionOut]:
    return list(db.scalars(select(Permission).order_by(Permission.code)).all())


@router.get("/roles", response_model=list[RoleOut])
def list_roles(
    db: Annotated[Session, Depends(get_db)],
    _actor: Annotated[User, Depends(_manage)],
) -> list[RoleOut]:
    roles = db.scalars(
        select(Role).options(selectinload(Role.permissions)).order_by(Role.name)
    ).all()
    return [_to_role_out(r) for r in roles]


@router.post("/roles", response_model=RoleOut, status_code=status.HTTP_201_CREATED)
def create_role(
    body: RoleCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[User, Depends(_manage)],
) -> RoleOut:
    existing = db.scalar(select(Role).where(Role.name == body.name.strip()))
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A role with this name already exists",
        )

    permissions = _resolve_permissions(db, body.permission_codes)
    role = Role(name=body.name.strip(), description=body.description)
    db.add(role)
    db.flush()
    for perm in permissions:
        db.add(RolePermission(role_id=role.id, permission_id=perm.id))
    db.refresh(role, attribute_names=["permissions"])

    record_audit(
        db,
        action=AuditAction.ROLE_CREATED,
        actor=actor,
        entity_type="role",
        entity_id=role.id,
        metadata={
            "new": {
                "name": role.name,
                "description": role.description,
                "permissions": _permission_codes(role),
            }
        },
        ip_address=client_ip_from_request(request),
        user_agent=user_agent_from_request(request),
    )
    db.commit()
    role = db.scalar(
        select(Role).where(Role.id == role.id).options(selectinload(Role.permissions))
    )
    assert role is not None
    return _to_role_out(role)


@router.put("/roles/{role_id}/permissions", response_model=RoleOut)
def replace_role_permissions(
    role_id: uuid.UUID,
    body: RolePermissionsUpdate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[User, Depends(_manage)],
) -> RoleOut:
    role = db.scalar(
        select(Role).where(Role.id == role_id).options(selectinload(Role.permissions))
    )
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")

    if role.name == ADMIN_ROLE_NAME:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The built-in Admin role cannot be modified",
        )

    old_codes = _permission_codes(role)
    permissions = _resolve_permissions(db, body.permission_codes)
    _replace_role_permissions(db, role, permissions)
    db.flush()
    new_codes = _permission_codes_for_role(db, role.id)
    role = db.scalar(
        select(Role).where(Role.id == role.id).options(selectinload(Role.permissions))
    )
    assert role is not None

    record_audit(
        db,
        action=AuditAction.ROLE_CHANGED,
        actor=actor,
        entity_type="role",
        entity_id=role.id,
        metadata={"old": {"permissions": old_codes}, "new": {"permissions": new_codes}},
        ip_address=client_ip_from_request(request),
        user_agent=user_agent_from_request(request),
    )
    db.commit()
    return _to_role_out(role)

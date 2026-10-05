"""Idempotent database seed for RBAC and default settings."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import SessionLocal
from app.models.auth import Permission, Role, RolePermission, User, UserRole
from app.models.system import Setting
from app.security.passwords import hash_password

ALL_PERMISSIONS: tuple[str, ...] = (
    "project.create",
    "project.view",
    "project.archive",
    "input.add",
    "step.generate",
    "step.request_changes",
    "step.edit",
    "step.approve",
    "step.reopen",
    "document.download",
    "reference.view",
    "reference.manage",
    "template.view",
    "template.manage",
    "prompt.view",
    "audit.view",
    "audit.export",
    "user.manage",
    "role.manage",
    "settings.manage",
)

ROLE_DEFINITIONS: dict[str, str] = {
    "Admin": "Full access to all permissions.",
    "Lead": "Create, generate, edit, approve, reopen, download, audit and prompt view.",
    "Analyst": "Create and work steps; approve subject to self-approval policy.",
    "Viewer": "Read-only project access and downloads.",
}

ROLE_PERMISSIONS: dict[str, tuple[str, ...]] = {
    "Admin": ALL_PERMISSIONS,
    "Lead": (
        "project.create",
        "project.view",
        "input.add",
        "step.generate",
        "step.request_changes",
        "step.edit",
        "step.approve",
        "step.reopen",
        "document.download",
        "reference.view",
        "template.view",
        "prompt.view",
        "audit.view",
    ),
    "Analyst": (
        "project.create",
        "project.view",
        "input.add",
        "step.generate",
        "step.request_changes",
        "step.edit",
        "step.approve",
        "document.download",
        "reference.view",
        "template.view",
    ),
    "Viewer": (
        "project.view",
        "document.download",
        "reference.view",
        "template.view",
    ),
}

ALLOW_SELF_APPROVAL_KEY = "allow_self_approval"
ADMIN_ROLE_NAME = "Admin"
MIN_USER_PASSWORD_LENGTH = 12


@dataclass
class SeedSummary:
    permissions_created: int = 0
    permissions_existing: int = 0
    roles_created: int = 0
    roles_existing: int = 0
    role_links_created: int = 0
    role_links_existing: int = 0
    admin_user_created: bool = False
    admin_user_existing: bool = False
    admin_role_linked: bool = False
    setting_created: bool = False
    setting_existing: bool = False


def _get_or_create_permission(session: Session, code: str) -> tuple[Permission, bool]:
    permission = session.scalar(select(Permission).where(Permission.code == code))
    if permission is not None:
        return permission, False
    permission = Permission(code=code)
    session.add(permission)
    session.flush()
    return permission, True


def _get_or_create_role(session: Session, name: str, description: str) -> tuple[Role, bool]:
    role = session.scalar(select(Role).where(Role.name == name))
    if role is not None:
        return role, False
    role = Role(name=name, description=description)
    session.add(role)
    session.flush()
    return role, True


def _ensure_role_permission(
    session: Session, role: Role, permission: Permission
) -> bool:
    exists = session.scalar(
        select(RolePermission.role_id).where(
            RolePermission.role_id == role.id,
            RolePermission.permission_id == permission.id,
        )
    )
    if exists is not None:
        return False
    session.add(RolePermission(role_id=role.id, permission_id=permission.id))
    return True


def _find_user_by_email_insensitive(session: Session, email: str) -> User | None:
    normalized = email.strip().lower()
    return session.scalar(
        select(User).where(func.lower(User.email) == normalized)
    )


def run_seed(session: Session, settings: Settings) -> SeedSummary:
    summary = SeedSummary()

    permission_by_code: dict[str, Permission] = {}
    for code in ALL_PERMISSIONS:
        permission, created = _get_or_create_permission(session, code)
        permission_by_code[code] = permission
        if created:
            summary.permissions_created += 1
        else:
            summary.permissions_existing += 1

    role_by_name: dict[str, Role] = {}
    for name, description in ROLE_DEFINITIONS.items():
        role, created = _get_or_create_role(session, name, description)
        role_by_name[name] = role
        if created:
            summary.roles_created += 1
        else:
            summary.roles_existing += 1

    for role_name, codes in ROLE_PERMISSIONS.items():
        role = role_by_name[role_name]
        for code in codes:
            permission = permission_by_code[code]
            if _ensure_role_permission(session, role, permission):
                summary.role_links_created += 1
            else:
                summary.role_links_existing += 1

    admin_email = settings.ADMIN_EMAIL.strip()
    admin_user = _find_user_by_email_insensitive(session, admin_email)
    if admin_user is None:
        admin_user = User(
            email=admin_email,
            full_name=settings.ADMIN_FULL_NAME.strip(),
            password_hash=hash_password(settings.ADMIN_PASSWORD),
            is_active=True,
        )
        session.add(admin_user)
        session.flush()
        summary.admin_user_created = True
    else:
        summary.admin_user_existing = True

    admin_role = role_by_name["Admin"]
    user_role_exists = session.scalar(
        select(UserRole.user_id).where(
            UserRole.user_id == admin_user.id,
            UserRole.role_id == admin_role.id,
        )
    )
    if user_role_exists is None:
        session.add(UserRole(user_id=admin_user.id, role_id=admin_role.id))
        summary.admin_role_linked = True

    setting = session.get(Setting, ALLOW_SELF_APPROVAL_KEY)
    if setting is None:
        session.add(
            Setting(key=ALLOW_SELF_APPROVAL_KEY, value=True, updated_by=None)
        )
        summary.setting_created = True
    else:
        summary.setting_existing = True

    return summary


def print_summary(summary: SeedSummary) -> None:
    print("Seed summary:")
    print(
        f"  permissions: {summary.permissions_created} created, "
        f"{summary.permissions_existing} already present"
    )
    print(
        f"  roles: {summary.roles_created} created, "
        f"{summary.roles_existing} already present"
    )
    print(
        f"  role-permission links: {summary.role_links_created} created, "
        f"{summary.role_links_existing} already present"
    )
    if summary.admin_user_created:
        print("  admin user: created")
    elif summary.admin_user_existing:
        print("  admin user: already present (password unchanged)")
    if summary.admin_role_linked:
        print("  admin role assignment: linked")
    if summary.setting_created:
        print("  setting allow_self_approval: created (true)")
    elif summary.setting_existing:
        print("  setting allow_self_approval: already present")


def main() -> None:
    settings = get_settings()
    with SessionLocal() as session:
        summary = run_seed(session, settings)
        session.commit()
    print_summary(summary)


if __name__ == "__main__":
    main()

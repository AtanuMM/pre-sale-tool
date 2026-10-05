from __future__ import annotations

import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, selectinload

from app.models.auth import Role, User, UserRole
from app.seed import ADMIN_ROLE_NAME


def normalize_email(email: str) -> str:
    return email.strip().lower()


def find_user_by_email_insensitive(session: Session, email: str) -> User | None:
    return session.scalar(
        select(User).where(func.lower(User.email) == normalize_email(email))
    )


def load_user_admin_view(session: Session, user_id: uuid.UUID) -> User | None:
    return session.scalar(
        select(User)
        .where(User.id == user_id)
        .options(selectinload(User.roles))
    )


def role_names(user: User) -> list[str]:
    return sorted(role.name for role in user.roles)


def user_has_role(user: User, role_name: str) -> bool:
    return any(role.name == role_name for role in user.roles)


def count_active_users_with_role(session: Session, role_name: str) -> int:
    return session.scalar(
        select(func.count(func.distinct(User.id)))
        .select_from(User)
        .join(UserRole, UserRole.user_id == User.id)
        .join(Role, Role.id == UserRole.role_id)
        .where(User.is_active.is_(True))
        .where(Role.name == role_name)
    ) or 0


def is_sole_active_admin(session: Session, user: User) -> bool:
    if not user.is_active or not user_has_role(user, ADMIN_ROLE_NAME):
        return False
    return count_active_users_with_role(session, ADMIN_ROLE_NAME) == 1


def admin_role_id(session: Session) -> uuid.UUID | None:
    role = session.scalar(select(Role).where(Role.name == ADMIN_ROLE_NAME))
    return role.id if role else None


def would_remove_admin_role(
    session: Session, user: User, new_role_ids: set[uuid.UUID]
) -> bool:
    admin_id = admin_role_id(session)
    if admin_id is None:
        return False
    if not user_has_role(user, ADMIN_ROLE_NAME):
        return False
    return admin_id not in new_role_ids


def replace_user_roles(session: Session, user: User, role_ids: list[uuid.UUID]) -> None:
    session.execute(delete(UserRole).where(UserRole.user_id == user.id))
    for role_id in role_ids:
        session.add(UserRole(user_id=user.id, role_id=role_id))


def resolve_roles_by_ids(session: Session, role_ids: list[uuid.UUID]) -> list[Role]:
    if not role_ids:
        return []
    roles = list(
        session.scalars(select(Role).where(Role.id.in_(role_ids))).all()
    )
    if len(roles) != len(set(role_ids)):
        missing = set(role_ids) - {role.id for role in roles}
        raise ValueError(f"Unknown role ids: {missing}")
    return roles

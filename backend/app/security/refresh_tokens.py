from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.auth import RefreshToken, User


class RefreshTokenError(Exception):
    pass


class RefreshTokenReuseError(RefreshTokenError):
    def __init__(self, message: str, *, user: User) -> None:
        super().__init__(message)
        self.user = user


def hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _expires_at() -> datetime:
    settings = get_settings()
    return datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_DAYS)


def issue_refresh_token(
    session: Session,
    *,
    user: User,
    ip_address: str | None,
    user_agent: str | None,
) -> tuple[str, RefreshToken]:
    raw = secrets.token_urlsafe(48)
    row = RefreshToken(
        user_id=user.id,
        token_hash=hash_refresh_token(raw),
        expires_at=_expires_at(),
        ip_address=ip_address,
        user_agent=user_agent,
    )
    session.add(row)
    return raw, row


def revoke_all_for_user(session: Session, user_id: uuid.UUID) -> None:
    now = datetime.now(UTC)
    session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id)
        .where(RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )


def rotate_refresh_token(
    session: Session,
    *,
    raw_token: str,
    ip_address: str | None,
    user_agent: str | None,
) -> tuple[str, RefreshToken, User]:
    token_hash = hash_refresh_token(raw_token)
    row = session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    if row is None:
        raise RefreshTokenError("invalid refresh token")

    if row.revoked_at is not None:
        user = session.get(User, row.user_id)
        if user is None:
            raise RefreshTokenError("invalid refresh token")
        revoke_all_for_user(session, user.id)
        raise RefreshTokenReuseError("refresh token reuse", user=user)

    now = datetime.now(UTC)
    if row.expires_at <= now:
        row.revoked_at = now
        raise RefreshTokenError("refresh token expired")

    user = session.get(User, row.user_id)
    if user is None or not user.is_active:
        row.revoked_at = now
        raise RefreshTokenError("invalid refresh token")

    new_raw, new_row = issue_refresh_token(
        session,
        user=user,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    row.revoked_at = now
    row.replaced_by_id = new_row.id
    return new_raw, new_row, user


def revoke_by_raw(session: Session, raw_token: str) -> RefreshToken | None:
    token_hash = hash_refresh_token(raw_token)
    row = session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    if row is None or row.revoked_at is not None:
        return row
    row.revoked_at = datetime.now(UTC)
    return row

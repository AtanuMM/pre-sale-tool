from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.db import get_db
from app.models.auth import Role, User
from app.schemas.auth import LoginRequest, LoginResponse, UserPublic
from app.security.deps import get_current_user
from app.security.dummy import DUMMY_PASSWORD_HASH
from app.security.jwt_access import create_access_token
from app.security.passwords import hash_password, needs_rehash, verify_password
from app.security.rate_limit import login_rate_limiter
from app.security.refresh_tokens import (
    RefreshTokenError,
    RefreshTokenReuseError,
    issue_refresh_token,
    revoke_by_raw,
    rotate_refresh_token,
)
from app.services.audit import (
    AuditAction,
    client_ip_from_request,
    record_audit,
    user_agent_from_request,
)

router = APIRouter(prefix="/auth", tags=["auth"])

GENERIC_AUTH_ERROR = "Invalid email or password"


def _user_permissions(user: User) -> list[str]:
    codes: set[str] = set()
    for role in user.roles:
        for perm in role.permissions:
            codes.add(perm.code)
    return sorted(codes)


def _load_user_with_permissions(db: Session, user_id) -> User | None:
    return db.scalar(
        select(User)
        .where(User.id == user_id)
        .options(selectinload(User.roles).selectinload(Role.permissions))
    )


def user_to_public(user: User) -> UserPublic:
    return UserPublic(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        permissions=_user_permissions(user),
    )


def _refresh_cookie_kwargs() -> dict:
    settings = get_settings()
    secure = settings.APP_ENV != "development"
    return {
        "key": settings.REFRESH_COOKIE_NAME,
        "httponly": True,
        "samesite": "strict",
        "path": "/auth",
        "secure": secure,
    }


def _set_refresh_cookie(response: Response, raw_token: str) -> None:
    settings = get_settings()
    max_age = settings.REFRESH_TOKEN_DAYS * 24 * 3600
    response.set_cookie(**_refresh_cookie_kwargs(), value=raw_token, max_age=max_age)


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(**_refresh_cookie_kwargs())


@router.post("/login", response_model=LoginResponse)
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> LoginResponse:
    email_normalized = body.email.strip().lower()
    ip = client_ip_from_request(request)
    ua = user_agent_from_request(request)

    ip_key = f"ip:{ip or 'unknown'}"
    email_key = f"email:{email_normalized}"
    if login_rate_limiter.is_blocked(ip_key) or login_rate_limiter.is_blocked(email_key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts",
        )

    user = db.scalar(
        select(User)
        .where(func.lower(User.email) == email_normalized)
        .options(selectinload(User.roles).selectinload(Role.permissions))
    )

    password_hash = user.password_hash if user else DUMMY_PASSWORD_HASH
    password_ok = verify_password(body.password, password_hash)

    if user is None or not password_ok or not user.is_active:
        login_rate_limiter.record_failure(ip_key)
        login_rate_limiter.record_failure(email_key)
        record_audit(
            db,
            action=AuditAction.USER_LOGIN_FAILED,
            metadata={"attempted_email": email_normalized},
            ip_address=ip,
            user_agent=ua,
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=GENERIC_AUTH_ERROR,
        )

    login_rate_limiter.clear_keys(ip_key, email_key)

    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)

    user.last_login_at = datetime.now(UTC)
    access_token, expires_in = create_access_token(user.id)
    raw_refresh, _ = issue_refresh_token(db, user=user, ip_address=ip, user_agent=ua)

    record_audit(
        db,
        action=AuditAction.USER_LOGIN,
        actor=user,
        entity_type="user",
        entity_id=user.id,
        ip_address=ip,
        user_agent=ua,
    )
    db.commit()

    _set_refresh_cookie(response, raw_refresh)
    return LoginResponse(
        access_token=access_token,
        expires_in=expires_in,
        user=user_to_public(user),
    )


@router.post("/refresh", response_model=LoginResponse)
def refresh(
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> LoginResponse:
    settings = get_settings()
    raw = request.cookies.get(settings.REFRESH_COOKIE_NAME)
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    ip = client_ip_from_request(request)
    ua = user_agent_from_request(request)

    try:
        new_raw, _, user = rotate_refresh_token(
            db,
            raw_token=raw,
            ip_address=ip,
            user_agent=ua,
        )
    except RefreshTokenReuseError as exc:
        record_audit(
            db,
            action=AuditAction.REFRESH_TOKEN_REUSE,
            actor=exc.user,
            entity_type="user",
            entity_id=exc.user.id,
            metadata={"reason": "revoked_token_presented"},
            ip_address=ip,
            user_agent=ua,
        )
        db.commit()
        _clear_refresh_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        ) from None
    except RefreshTokenError:
        db.commit()
        _clear_refresh_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        ) from None

    user = _load_user_with_permissions(db, user.id) or user
    access_token, expires_in = create_access_token(user.id)
    record_audit(
        db,
        action=AuditAction.USER_LOGIN,
        actor=user,
        entity_type="user",
        entity_id=user.id,
        metadata={"via": "refresh"},
        ip_address=ip,
        user_agent=ua,
    )
    db.commit()

    _set_refresh_cookie(response, new_raw)
    return LoginResponse(
        access_token=access_token,
        expires_in=expires_in,
        user=user_to_public(user),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    settings = get_settings()
    raw = request.cookies.get(settings.REFRESH_COOKIE_NAME)
    ip = client_ip_from_request(request)
    ua = user_agent_from_request(request)

    actor: User | None = None
    if raw:
        row = revoke_by_raw(db, raw)
        if row is not None:
            actor = db.get(User, row.user_id)

    if actor is not None:
        record_audit(
            db,
            action=AuditAction.USER_LOGOUT,
            actor=actor,
            entity_type="user",
            entity_id=actor.id,
            ip_address=ip,
            user_agent=ua,
        )
        db.commit()

    _clear_refresh_cookie(response)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserPublic)
def me(user: Annotated[User, Depends(get_current_user)]) -> UserPublic:
    return user_to_public(user)

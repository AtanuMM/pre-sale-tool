from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt

from app.config import get_settings


class AccessTokenError(Exception):
    pass


def create_access_token(user_id: uuid.UUID) -> tuple[str, int]:
    settings = get_settings()
    now = datetime.now(UTC)
    exp = now + timedelta(minutes=settings.ACCESS_TOKEN_MINUTES)
    payload = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "jti": str(uuid.uuid4()),
    }
    token = jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")
    expires_in = max(1, int((exp - now).total_seconds()))
    return token, expires_in


def decode_access_token(token: str) -> uuid.UUID:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=["HS256"],
        )
    except jwt.PyJWTError as exc:
        raise AccessTokenError("invalid token") from exc
    sub = payload.get("sub")
    if not sub:
        raise AccessTokenError("invalid token")
    try:
        return uuid.UUID(str(sub))
    except ValueError as exc:
        raise AccessTokenError("invalid token") from exc

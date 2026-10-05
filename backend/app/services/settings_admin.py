from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.auth import User
from app.models.system import Setting
from app.schemas.settings import SettingsOut
from app.seed import ALLOW_SELF_APPROVAL_KEY

SETTINGS_ALLOWLIST: frozenset[str] = frozenset({ALLOW_SELF_APPROVAL_KEY})


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, dict) and "value" in value:
        return bool(value["value"])
    return bool(value)


def get_settings_out(session: Session) -> SettingsOut:
    row = session.get(Setting, ALLOW_SELF_APPROVAL_KEY)
    if row is None:
        return SettingsOut(allow_self_approval=True)
    return SettingsOut(allow_self_approval=_coerce_bool(row.value))


def apply_settings_updates(
    session: Session,
    *,
    updates: dict[str, bool],
    actor: User,
) -> tuple[SettingsOut, dict[str, Any], dict[str, Any]]:
    old = get_settings_out(session)
    old_values = old.model_dump()

    new_values = dict(old_values)
    for key, value in updates.items():
        if key not in SETTINGS_ALLOWLIST:
            raise ValueError(f"Unknown setting key: {key}")
        new_values[key] = value

    for key, value in updates.items():
        row = session.get(Setting, key)
        if row is None:
            row = Setting(key=key, value=value, updated_by=actor.id)
            session.add(row)
        else:
            row.value = value
            row.updated_by = actor.id
            row.updated_at = datetime.now(UTC)

    new_out = SettingsOut(**new_values)
    return new_out, old_values, new_out.model_dump()

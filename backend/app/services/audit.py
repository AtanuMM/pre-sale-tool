"""Audit trail helper: append-only rows in the caller's transaction."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.auth import User
from app.models.system import AuditLog


class AuditAction:
    USER_LOGIN = "user.login"
    USER_LOGIN_FAILED = "user.login_failed"
    USER_LOGOUT = "user.logout"
    REFRESH_TOKEN_REUSE = "auth.refresh_token_reuse"
    USER_CREATED = "user.created"
    USER_UPDATED = "user.updated"
    USER_DEACTIVATED = "user.deactivated"
    USER_PASSWORD_RESET = "user.password_reset"
    ROLE_CREATED = "role.created"
    ROLE_CHANGED = "role.changed"
    PROJECT_CREATED = "project.created"
    INPUT_ADDED = "input.added"
    STEP_GENERATE_REQUESTED = "step.generate_requested"
    STEP_GENERATED = "step.generated"
    STEP_GENERATION_FAILED = "step.generation_failed"
    STEP_CHANGES_REQUESTED = "step.changes_requested"
    STEP_EDITED = "step.edited"
    STEP_SECTION_REGENERATED = "step.section_regenerated"
    STEP_APPROVED = "step.approved"
    STEP_REOPENED = "step.reopened"
    DOCUMENT_DOWNLOADED = "document.downloaded"
    PROMPT_VIEWED = "prompt.viewed"
    REFERENCE_UPLOADED = "reference.uploaded"
    REFERENCE_ACTIVATED = "reference.activated"
    REFERENCE_DEACTIVATED = "reference.deactivated"
    REFERENCE_DELETED = "reference.deleted"
    TEMPLATE_UPLOADED = "template.uploaded"
    TEMPLATE_ACTIVATED = "template.activated"
    SETTINGS_CHANGED = "settings.changed"
    PROJECT_SETTINGS_CHANGED = "project.settings_changed"
    AUDIT_EXPORTED = "audit.exported"


UNKNOWN_ACTOR_EMAIL = "unknown"
DEFAULT_ENTITY_TYPE = "system"


def _resolve_actor_email(
    actor: User | None, metadata: dict[str, Any] | None
) -> str:
    if actor is not None:
        return actor.email
    if metadata and isinstance(metadata.get("attempted_email"), str):
        attempted = metadata["attempted_email"].strip()
        if attempted:
            return attempted
    return UNKNOWN_ACTOR_EMAIL


def record_audit(
    session: Session,
    *,
    action: str,
    actor: User | None = None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    metadata: dict[str, Any] | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> AuditLog:
    """Append an audit row to session. Does not commit or flush.

    Do not store passwords, tokens, API keys, or other secrets in metadata.
    """
    meta = dict(metadata) if metadata else {}
    entry = AuditLog(
        actor_id=actor.id if actor is not None else None,
        actor_email=_resolve_actor_email(actor, meta),
        action=action,
        entity_type=entity_type or DEFAULT_ENTITY_TYPE,
        entity_id=entity_id,
        project_id=project_id,
        meta=meta,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    session.add(entry)
    return entry


def client_ip_from_request(
    request: Request, *, trust_forwarded: bool | None = None
) -> str | None:
    if trust_forwarded is None:
        trust_forwarded = get_settings().TRUST_X_FORWARDED_FOR
    if trust_forwarded:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            client = forwarded.split(",")[0].strip()
            if client:
                return client
    if request.client is None:
        return None
    return request.client.host


def user_agent_from_request(request: Request) -> str | None:
    return request.headers.get("user-agent")

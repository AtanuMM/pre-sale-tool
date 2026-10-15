"""SRS diagram listing and rendering for API."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.documents.diagrams.cache import render_diagram
from app.models.steps import StepVersion
from app.steps.schemas.srs import DiagramSpec, SrsStored

Format = Literal["png", "svg"]


def list_diagrams(content: dict[str, Any]) -> list[dict[str, str]]:
    stored = SrsStored.model_validate(content)
    items: list[dict[str, str]] = []
    for key, spec_dict in stored.assembled.diagram_specs.items():
        spec = DiagramSpec.model_validate(spec_dict)
        items.append(
            {
                "key": key,
                "kind": spec.kind,
                "title": spec.title,
                "caption": spec.caption,
            }
        )
    for item in stored.viewer.diagrams:
        if item.key not in {i["key"] for i in items}:
            items.append(
                {
                    "key": item.key,
                    "kind": item.kind,
                    "title": item.title,
                    "caption": item.caption,
                }
            )
    return items


def render_version_diagram(
    session: Session,
    version_id: uuid.UUID,
    diagram_key: str,
    fmt: Format,
) -> tuple[bytes, str]:
    version = session.get(StepVersion, version_id)
    if version is None or not isinstance(version.content, dict):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")
    stored = SrsStored.model_validate(version.content)
    spec_dict = stored.assembled.diagram_specs.get(diagram_key)
    if spec_dict is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Diagram not found")
    spec = DiagramSpec.model_validate(spec_dict)
    data = render_diagram(version_id, diagram_key, spec, fmt)
    media = "image/png" if fmt == "png" else "image/svg+xml"
    return data, media

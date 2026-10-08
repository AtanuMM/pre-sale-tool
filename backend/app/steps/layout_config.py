"""Shared step layout: drives API, web viewer, and DOCX export."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from pydantic import BaseModel


class SectionKind(str, Enum):
    TEXT = "text"
    LIST = "list"
    TABLE = "table"
    RECORDS = "records"
    NUMBERED_LIST = "numbered_list"


@dataclass(frozen=True)
class LayoutColumn:
    key: str
    header: str


@dataclass(frozen=True)
class SectionLayoutSpec:
    key: str
    title: str
    kind: SectionKind
    columns: tuple[LayoutColumn, ...] = ()
    record_fields: tuple[LayoutColumn, ...] = ()
    badge_fields: tuple[str, ...] = ()
    copyable: bool = False


def layout_section_keys(layout: tuple[SectionLayoutSpec, ...]) -> set[str]:
    return {s.key for s in layout}


def validate_layout_against_schema(
    layout: tuple[SectionLayoutSpec, ...],
    schema: type[BaseModel],
) -> None:
    allowed = set(schema.model_fields.keys())
    for section in layout:
        if section.key not in allowed:
            raise RuntimeError(
                f"Layout section {section.key!r} is not a field on {schema.__name__}"
            )
        if section.kind == SectionKind.TABLE and not section.columns:
            raise RuntimeError(f"Table section {section.key} requires columns")
        if section.kind == SectionKind.RECORDS and not section.record_fields:
            raise RuntimeError(f"Records section {section.key} requires record_fields")


def layout_to_api(layout: tuple[SectionLayoutSpec, ...]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for s in layout:
        item: dict[str, Any] = {
            "key": s.key,
            "title": s.title,
            "kind": s.kind.value,
            "copyable": s.copyable,
        }
        if s.columns:
            item["columns"] = [{"key": c.key, "header": c.header} for c in s.columns]
        if s.record_fields:
            item["record_fields"] = [
                {"key": c.key, "header": c.header} for c in s.record_fields
            ]
        if s.badge_fields:
            item["badge_fields"] = list(s.badge_fields)
        out.append(item)
    return out

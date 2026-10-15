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
    STATS = "stats"
    COMPUTED_CARDS = "computed_cards"
    COMPUTED_TABLE = "computed_table"
    WARNING_STRIP = "warning_strip"
    METHOD_NOTE = "method_note"
    OPEN_ITEMS = "open_items"
    STANDARD_TERMS = "standard_terms"
    RICH_TEXT = "rich_text"
    HEALTH_PANEL = "health_panel"
    DIAGRAM = "diagram"
    REQUIREMENT_TABLE = "requirement_table"


@dataclass(frozen=True)
class LayoutColumn:
    key: str
    header: str


@dataclass(frozen=True)
class GroupSource:
    """Where group headings/intros come from for a grouped records section."""

    section: str
    key_field: str
    intro_field: str


@dataclass(frozen=True)
class SectionLayoutSpec:
    key: str
    title: str
    kind: SectionKind
    columns: tuple[LayoutColumn, ...] = ()
    record_fields: tuple[LayoutColumn, ...] = ()
    badge_fields: tuple[str, ...] = ()
    copyable: bool = False
    # Position-based reference labels (e.g. "G" -> G-1, G-2) shown for each item.
    ref_prefix: str | None = None
    # Records: field holding a stable id rendered as a chip (e.g. "id" -> F-001).
    id_field: str | None = None
    # Records: list-valued fields rendered as small chips (e.g. depends_on_ids).
    chip_fields: tuple[str, ...] = ()
    # Records: group items by this field; headings/intros from group_source.
    group_by: str | None = None
    group_source: GroupSource | None = None
    # Records: fields offering client-side filters (scalar or list-valued).
    filter_fields: tuple[str, ...] = ()
    # Stats: (content key, label) pairs; each value is a mapping label -> count.
    stats_groups: tuple[LayoutColumn, ...] = ()
    # Dotted path from content, e.g. "computed.cards". When set, key need not be a schema field.
    source: str | None = None


def layout_section_keys(layout: tuple[SectionLayoutSpec, ...]) -> set[str]:
    return {s.key for s in layout}


def resolve_section_value(content: dict[str, Any], section: SectionLayoutSpec) -> Any:
    if not section.source:
        return content.get(section.key)
    current: Any = content
    for part in section.source.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _record_item_fields(schema: type[BaseModel], key: str) -> set[str] | None:
    field = schema.model_fields.get(key)
    if field is None:
        return None
    annotation = field.annotation
    args = getattr(annotation, "__args__", ())
    for arg in args:
        if isinstance(arg, type) and issubclass(arg, BaseModel):
            return set(arg.model_fields.keys())
    return None


def validate_layout_against_schema(
    layout: tuple[SectionLayoutSpec, ...],
    schema: type[BaseModel],
) -> None:
    allowed = set(schema.model_fields.keys())
    keys_seen: set[str] = set()
    for section in layout:
        if section.key in keys_seen:
            raise RuntimeError(f"Duplicate layout section {section.key!r}")
        keys_seen.add(section.key)
        computed_kinds = {
            SectionKind.COMPUTED_CARDS,
            SectionKind.COMPUTED_TABLE,
            SectionKind.WARNING_STRIP,
            SectionKind.METHOD_NOTE,
            SectionKind.OPEN_ITEMS,
            SectionKind.STANDARD_TERMS,
            SectionKind.RICH_TEXT,
            SectionKind.HEALTH_PANEL,
            SectionKind.DIAGRAM,
            SectionKind.REQUIREMENT_TABLE,
        }
        if section.source:
            sourced_kinds = computed_kinds | {
                SectionKind.TABLE,
                SectionKind.LIST,
                SectionKind.TEXT,
                SectionKind.RECORDS,
                SectionKind.RICH_TEXT,
            }
            if section.kind not in sourced_kinds:
                raise RuntimeError(
                    f"Layout section {section.key} has source but is not a computed kind"
                )
            root = section.source.split(".", 1)[0]
            if root not in allowed:
                raise RuntimeError(
                    f"Layout source {section.source!r} root is not a field on {schema.__name__}"
                )
        elif section.key not in allowed:
            raise RuntimeError(
                f"Layout section {section.key!r} is not a field on {schema.__name__}"
            )
        if section.kind in (SectionKind.TABLE, SectionKind.COMPUTED_TABLE) and (
            not section.columns and section.kind == SectionKind.TABLE
        ):
            raise RuntimeError(f"Table section {section.key} requires columns")
        if section.kind == SectionKind.RECORDS and not section.record_fields:
            raise RuntimeError(f"Records section {section.key} requires record_fields")
        if section.kind == SectionKind.STATS and not section.stats_groups:
            raise RuntimeError(f"Stats section {section.key} requires stats_groups")
        if section.ref_prefix is not None and section.kind not in (
            SectionKind.LIST,
            SectionKind.NUMBERED_LIST,
            SectionKind.TABLE,
            SectionKind.RECORDS,
        ):
            raise RuntimeError(f"ref_prefix on {section.key} requires a list-like kind")
        if section.ref_prefix is not None and not section.ref_prefix.isalpha():
            raise RuntimeError(f"ref_prefix on {section.key} must be alphabetic")
        if section.kind == SectionKind.RECORDS:
            item_fields = _record_item_fields(schema, section.key)
            if item_fields is not None:
                named = (
                    *(c.key for c in section.record_fields),
                    *section.badge_fields,
                    *section.chip_fields,
                    *section.filter_fields,
                    *((section.id_field,) if section.id_field else ()),
                    *((section.group_by,) if section.group_by else ()),
                )
                for name in named:
                    if name not in item_fields:
                        raise RuntimeError(
                            f"Records section {section.key} references unknown item "
                            f"field {name!r}"
                        )
        if (section.group_by is None) != (section.group_source is None):
            raise RuntimeError(
                f"Section {section.key} must set both group_by and group_source"
            )
        if section.group_source is not None:
            if section.kind != SectionKind.RECORDS:
                raise RuntimeError(f"group_by on {section.key} requires records kind")
            if section.group_source.section not in allowed:
                raise RuntimeError(
                    f"group_source section {section.group_source.section!r} missing on "
                    f"{schema.__name__}"
                )
            src_fields = _record_item_fields(schema, section.group_source.section)
            if src_fields is not None:
                for name in (section.group_source.key_field, section.group_source.intro_field):
                    if name not in src_fields:
                        raise RuntimeError(
                            f"group_source for {section.key} references unknown field {name!r}"
                        )


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
        if s.ref_prefix:
            item["ref_prefix"] = s.ref_prefix
        if s.id_field:
            item["id_field"] = s.id_field
        if s.chip_fields:
            item["chip_fields"] = list(s.chip_fields)
        if s.group_by and s.group_source:
            item["group_by"] = s.group_by
            item["group_source"] = {
                "section": s.group_source.section,
                "key_field": s.group_source.key_field,
                "intro_field": s.group_source.intro_field,
            }
        if s.filter_fields:
            item["filter_fields"] = list(s.filter_fields)
        if s.stats_groups:
            item["stats_groups"] = [
                {"key": c.key, "header": c.header} for c in s.stats_groups
            ]
        if s.source:
            item["source"] = s.source
        out.append(item)
    return out

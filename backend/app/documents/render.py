"""Generic step content → DOCX bytes."""

from __future__ import annotations

from io import BytesIO
from typing import Any

from docx import Document
from docx.shared import Pt
from fastapi import HTTPException, status

from app.config import get_settings
from app.documents.docx_builder import create_export_document
from app.documents.layouts import layout_for_step
from app.documents.meta import ExportMeta
from app.documents.sanitize import sanitize_docx_text
from app.steps.layout_config import SectionKind, SectionLayoutSpec


def content_char_weight(value: Any) -> int:
    if isinstance(value, str):
        return len(value)
    if isinstance(value, dict):
        return sum(content_char_weight(v) for v in value.values())
    if isinstance(value, list):
        return sum(content_char_weight(item) for item in value)
    return 0


def assert_content_within_export_limit(content: dict[str, Any]) -> None:
    settings = get_settings()
    total = content_char_weight(content)
    if total > settings.MAX_DOCX_EXPORT_CONTENT_CHARS:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                "Step version content exceeds the maximum size allowed for export "
                f"({settings.MAX_DOCX_EXPORT_CONTENT_CHARS} characters)"
            ),
        )


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return sanitize_docx_text(value)
    return sanitize_docx_text(str(value))


def _add_section_heading(doc: Document, title: str) -> None:
    para = doc.add_paragraph(style="Heading 1")
    run = para.add_run(sanitize_docx_text(title))
    run.font.name = "Calibri"
    run.font.size = Pt(14)
    run.bold = True


def _render_text(doc: Document, raw: Any) -> None:
    if not isinstance(raw, str) or not raw.strip():
        return
    doc.add_paragraph(sanitize_docx_text(raw))


def _render_list(doc: Document, raw: Any) -> None:
    if not isinstance(raw, list):
        return
    for item in raw:
        if not isinstance(item, str) or not item.strip():
            continue
        doc.add_paragraph(sanitize_docx_text(item), style="List Bullet")


def _render_numbered_list(doc: Document, raw: Any) -> None:
    if not isinstance(raw, list):
        return
    for item in raw:
        if not isinstance(item, str) or not item.strip():
            continue
        doc.add_paragraph(sanitize_docx_text(item), style="List Number")


def _render_table(doc: Document, raw: Any, layout: SectionLayoutSpec) -> None:
    if not isinstance(raw, list) or not layout.columns:
        return
    objects = [row for row in raw if isinstance(row, dict)]
    if not objects:
        return
    table = doc.add_table(rows=1 + len(objects), cols=len(layout.columns))
    table.style = "Table Grid"
    for col_idx, col in enumerate(layout.columns):
        table.rows[0].cells[col_idx].text = sanitize_docx_text(col.header)
    for row_idx, obj in enumerate(objects, start=1):
        for col_idx, col in enumerate(layout.columns):
            table.rows[row_idx].cells[col_idx].text = _cell_text(obj.get(col.key))


def _render_records(doc: Document, raw: Any, layout: SectionLayoutSpec) -> None:
    if not isinstance(raw, list) or not layout.record_fields:
        return
    objects = [row for row in raw if isinstance(row, dict)]
    if not objects:
        return
    for obj in objects:
        badge_parts: list[str] = []
        for badge_key in layout.badge_fields:
            val = obj.get(badge_key)
            if val is not None and str(val).strip():
                badge_parts.append(f"{badge_key.replace('_', ' ').title()}: {val}")
        if badge_parts:
            doc.add_paragraph(sanitize_docx_text(" · ".join(badge_parts)))
        for field in layout.record_fields:
            val = obj.get(field.key)
            if val is None or (isinstance(val, str) and not val.strip()):
                continue
            line = f"{field.header}: {_cell_text(val)}"
            doc.add_paragraph(sanitize_docx_text(line))
        doc.add_paragraph()


def _render_section(doc: Document, content: dict[str, Any], layout: SectionLayoutSpec) -> None:
    raw = content.get(layout.key)
    if raw is None:
        return
    if layout.kind == SectionKind.TEXT:
        if not isinstance(raw, str) or not raw.strip():
            return
    elif layout.kind == SectionKind.LIST or layout.kind == SectionKind.NUMBERED_LIST:
        if not isinstance(raw, list) or not any(isinstance(x, str) and x.strip() for x in raw):
            return
    elif layout.kind == SectionKind.TABLE and (
        not isinstance(raw, list) or not any(isinstance(x, dict) for x in raw)
    ) or layout.kind == SectionKind.RECORDS and (
        not isinstance(raw, list) or not any(isinstance(x, dict) for x in raw)
    ):
        return
    _add_section_heading(doc, layout.title)
    if layout.kind == SectionKind.TEXT:
        _render_text(doc, raw)
    elif layout.kind == SectionKind.LIST:
        _render_list(doc, raw)
    elif layout.kind == SectionKind.NUMBERED_LIST:
        _render_numbered_list(doc, raw)
    elif layout.kind == SectionKind.TABLE:
        _render_table(doc, raw, layout)
    elif layout.kind == SectionKind.RECORDS:
        _render_records(doc, raw, layout)
    doc.add_paragraph()


def render_step_docx(step_key: str, content: dict[str, Any], meta: ExportMeta) -> bytes:
    layout = layout_for_step(step_key)
    if layout is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="DOCX export is not available for this step",
        )
    assert_content_within_export_limit(content)
    doc = create_export_document(meta)
    for section in layout:
        _render_section(doc, content, section)
    buffer = BytesIO()
    doc.save(buffer)
    return buffer.getvalue()

"""SRS DOCX export."""

from __future__ import annotations

import uuid
from io import BytesIO
from typing import Any

from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm

from app.documents.docx_builder import _set_run_font, create_export_document
from app.documents.meta import ExportMeta
from app.documents.sanitize import sanitize_docx_text
from app.steps.schemas.srs import DiagramSpec, SrsStored


def _srs_marker(meta: ExportMeta) -> str:
    if meta.status == "approved":
        return "Approved for issue"
    return meta.marker_line


def _add_heading(doc, text: str, level: int = 1) -> None:
    style = "Heading 1" if level == 1 else "Heading 2"
    para = doc.add_paragraph(style=style)
    run = para.add_run(sanitize_docx_text(text))
    _set_run_font(run, size_pt=14 if level == 1 else 12, bold=True)


def render_srs_docx(content: dict[str, Any], meta: ExportMeta, version_id: uuid.UUID | None = None) -> bytes:
    stored = SrsStored.model_validate(content)
    doc = create_export_document(
        ExportMeta(
            step_key=meta.step_key,
            step_title=meta.step_title,
            project_name=meta.project_name,
            client_name=meta.client_name,
            version_no=meta.version_no,
            status=meta.status,
            status_label=meta.status_label,
            marker_line=_srs_marker(meta),
            metadata_date_label=meta.metadata_date_label,
            metadata_date_value=meta.metadata_date_value,
            created_by_name=meta.created_by_name,
            is_draft_filename=meta.is_draft_filename,
        )
    )
    section = doc.sections[0]
    header = section.header.paragraphs[0]
    header.clear()
    marker = _srs_marker(meta)
    if marker:
        run = header.add_run(sanitize_docx_text(marker))
        _set_run_font(run, size_pt=9, bold=True)
        header.alignment = WD_ALIGN_PARAGRAPH.CENTER

    cover = doc.add_paragraph()
    cover.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for line in (
        meta.client_name,
        meta.project_name,
        "Software Requirements Specification",
        stored.assembled.document_reference,
        meta.metadata_date_label + ": " + meta.metadata_date_value,
    ):
        run = cover.add_run(sanitize_docx_text(line) + "\n")
        _set_run_font(run, size_pt=11)

    doc.add_page_break()
    _add_heading(doc, "Table of contents", level=1)
    toc = doc.add_paragraph()
    run = toc.add_run("(Update field in Word to refresh page numbers.)")
    _set_run_font(run, size_pt=10)

    if stored.passes.planning_a:
        _add_heading(doc, "1 Introduction", level=1)
        p = doc.add_paragraph()
        run = p.add_run(sanitize_docx_text(stored.passes.planning_a.purpose))
        _set_run_font(run, size_pt=11)
        _add_heading(doc, "2 Overall description", level=1)
        p2 = doc.add_paragraph()
        run2 = p2.add_run(sanitize_docx_text(stored.passes.planning_a.overview))
        _set_run_font(run2, size_pt=11)

    if version_id and stored.assembled.diagram_specs:
        from app.documents.diagrams.cache import render_diagram

        fig_no = 1
        for key, spec_dict in stored.assembled.diagram_specs.items():
            spec = DiagramSpec.model_validate(spec_dict)
            _add_heading(doc, f"Figure {fig_no}: {spec.title}", level=2)
            try:
                png = render_diagram(version_id, key, spec, "png")
                doc.add_picture(BytesIO(png), width=Cm(16))
            except Exception:
                note = doc.add_paragraph()
                run = note.add_run(
                    sanitize_docx_text(
                        "(Diagram could not be rendered for export; open ScopeDesk to view it.)"
                    )
                )
                _set_run_font(run, size_pt=10)
            fig_no += 1

    _add_heading(doc, "5 Functional requirements", level=1)
    table = doc.add_table(rows=1, cols=5)
    table.style = "Table Grid"
    hdr = table.rows[0].cells
    for idx, title in enumerate(("ID", "Requirement", "Priority", "Phase", "Basis")):
        hdr[idx].text = title
    for fr in stored.functional_requirements[:500]:
        row = table.add_row().cells
        row[0].text = sanitize_docx_text(fr.id)
        row[1].text = sanitize_docx_text(fr.statement)
        row[2].text = sanitize_docx_text(fr.priority)
        row[3].text = sanitize_docx_text(fr.phase)
        row[4].text = sanitize_docx_text(fr.basis)

    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()

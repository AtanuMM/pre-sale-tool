from __future__ import annotations

import uuid
from io import BytesIO

from docx import Document

from app.documents.meta import ExportMeta
from app.documents.srs_docx import render_srs_docx
from app.steps.schemas.srs import SrsAssembled, SrsHealthMeta, SrsPasses, SrsStored


def test_render_srs_docx_minimal() -> None:
    stored = SrsStored(
        passes=SrsPasses(),
        functional_requirements=[],
        nfr_requirements=[],
        interfaces=[],
        entities=[],
        assembled=SrsAssembled(document_reference="SRS-001"),
        viewer=SrsHealthMeta(),
    )
    meta = ExportMeta(
        step_key="srs",
        step_title="Software Requirements Specification",
        project_name="Demo",
        client_name="Client",
        version_no=1,
        status="approved",
        status_label="Approved",
        marker_line="Approved for issue",
        metadata_date_label="Approved",
        metadata_date_value="2026-01-01",
        created_by_name="Tester",
        is_draft_filename=False,
    )
    data = render_srs_docx(stored.model_dump(), meta, version_id=uuid.uuid4())
    doc = Document(BytesIO(data))
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "Software Requirements Specification" in text
    assert "Functional requirements" in text

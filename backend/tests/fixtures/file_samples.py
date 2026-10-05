from __future__ import annotations

import zipfile
from email.message import EmailMessage
from io import BytesIO

from docx import Document
from openpyxl import Workbook
from pypdf import PdfReader, PdfWriter


def sample_txt() -> bytes:
    return b"Hello ScopeDesk plain text.\n"


def sample_md() -> bytes:
    return b"# Title\n\nMarkdown **body**.\n"


def sample_csv() -> bytes:
    return b"col_a,col_b\n1,two\n"


def sample_pdf_with_text() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = BytesIO()
    writer.write(buf)
    buf.seek(0)
    return buf.getvalue()


def sample_pdf_no_text_layer() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    buf = BytesIO()
    writer.write(buf)
    data = buf.getvalue()
    reader = PdfReader(BytesIO(data))
    text = reader.pages[0].extract_text() or ""
    assert not text.strip()
    return data


def sample_docx() -> bytes:
    doc = Document()
    doc.add_paragraph("Docx paragraph")
    table = doc.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "A1"
    table.rows[0].cells[1].text = "B1"
    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


def sample_xlsx() -> bytes:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Sheet1"
    ws["A1"] = "hello"
    ws["B1"] = 42
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def sample_eml() -> bytes:
    msg = EmailMessage()
    msg["From"] = "client@example.com"
    msg["To"] = "team@scopedesk.test"
    msg["Subject"] = "Intake"
    msg.set_content("Plain body text.")
    return msg.as_bytes()


def fake_pdf_exe() -> bytes:
    return b"MZ" + b"\x00" * 100


def zip_bomb_docx_like() -> bytes:
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for i in range(600):
            zf.writestr(f"word/part{i}.xml", "x" * 100)
    return buf.getvalue()

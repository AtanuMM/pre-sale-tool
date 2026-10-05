from __future__ import annotations

import pytest

from app.config import get_settings
from app.services.extraction import TRUNCATION_MARKER, extract_text
from app.services.file_validation import DetectedFileType
from tests.fixtures.file_samples import (
    sample_csv,
    sample_docx,
    sample_eml,
    sample_md,
    sample_pdf_no_text_layer,
    sample_txt,
    sample_xlsx,
)


@pytest.fixture(autouse=True)
def _limits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAX_EXTRACTED_TEXT_CHARS", "500000")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_extract_txt_md_csv() -> None:
    assert "ScopeDesk" in extract_text(sample_txt(), DetectedFileType.TXT).text
    assert "Markdown" in extract_text(sample_md(), DetectedFileType.MD).text
    assert "col_a" in extract_text(sample_csv(), DetectedFileType.CSV).text


def test_extract_docx_includes_table() -> None:
    result = extract_text(sample_docx(), DetectedFileType.DOCX)
    assert "Docx paragraph" in result.text
    assert "A1" in result.text and "B1" in result.text


def test_extract_xlsx() -> None:
    result = extract_text(sample_xlsx(), DetectedFileType.XLSX)
    assert "hello" in result.text
    assert "42" in result.text


def test_extract_eml_headers_and_body() -> None:
    result = extract_text(sample_eml(), DetectedFileType.EML)
    assert "client@example.com" in result.text
    assert "Plain body text" in result.text


def test_scanned_pdf_empty_reason() -> None:
    result = extract_text(sample_pdf_no_text_layer(), DetectedFileType.PDF)
    assert result.text == ""
    assert result.empty_reason == "no_text_layer"


def test_truncation_marker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAX_EXTRACTED_TEXT_CHARS", "10")
    get_settings.cache_clear()
    result = extract_text(b"012345678901234567890", DetectedFileType.TXT)
    assert result.truncated is True
    assert TRUNCATION_MARKER in result.text

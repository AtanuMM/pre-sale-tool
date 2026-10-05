from __future__ import annotations

from io import BytesIO

import pytest

from app.config import get_settings
from app.services.file_validation import (
    DetectedFileType,
    FileValidationError,
    assert_file_count_for_input,
    sanitize_original_name,
    validate_upload,
)
from app.services.storage import StorageError, read_bounded_stream
from tests.fixtures.file_samples import (
    fake_pdf_exe,
    sample_csv,
    sample_docx,
    sample_eml,
    sample_md,
    sample_pdf_with_text,
    sample_txt,
    sample_xlsx,
    zip_bomb_docx_like,
)


@pytest.fixture(autouse=True)
def _limits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAX_UPLOAD_FILE_BYTES", "10485760")
    monkeypatch.setenv("MAX_FILES_PER_INPUT", "10")
    monkeypatch.setenv("ZIP_MAX_ENTRY_COUNT", "500")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.parametrize(
    ("data", "name", "expected"),
    [
        (sample_pdf_with_text(), "doc.pdf", DetectedFileType.PDF),
        (sample_docx(), "brief.docx", DetectedFileType.DOCX),
        (sample_txt(), "notes.txt", DetectedFileType.TXT),
        (sample_md(), "readme.md", DetectedFileType.MD),
        (sample_eml(), "mail.eml", DetectedFileType.EML),
        (sample_csv(), "data.csv", DetectedFileType.CSV),
        (sample_xlsx(), "sheet.xlsx", DetectedFileType.XLSX),
    ],
)
def test_validate_accepts_allowed_types(data: bytes, name: str, expected: DetectedFileType) -> None:
    assert validate_upload(data, original_name=name) == expected


def test_rejects_wrong_magic_for_extension() -> None:
    with pytest.raises(FileValidationError):
        validate_upload(fake_pdf_exe(), original_name="evil.pdf")


def test_oversize_rejected_while_streaming() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    stream = BytesIO(b"x" * (settings.MAX_UPLOAD_FILE_BYTES + 1))
    with pytest.raises(StorageError):
        read_bounded_stream(stream, max_bytes=settings.MAX_UPLOAD_FILE_BYTES)


def test_zip_bomb_rejected() -> None:
    with pytest.raises(FileValidationError):
        validate_upload(zip_bomb_docx_like(), original_name="bomb.docx")


def test_sanitize_original_name() -> None:
    assert sanitize_original_name("../../etc/passwd\x00bad") == "passwdbad"
    assert len(sanitize_original_name("a" * 600)) <= 512


def test_file_count_limit() -> None:
    assert_file_count_for_input(10)
    with pytest.raises(FileValidationError):
        assert_file_count_for_input(11)

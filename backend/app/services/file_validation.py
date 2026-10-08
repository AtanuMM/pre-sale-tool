from __future__ import annotations

import email
import re
import zipfile
from enum import Enum
from io import BytesIO
from pathlib import PurePath

from app.config import get_settings

CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
MAX_ORIGINAL_NAME_LEN = 512


class DetectedFileType(str, Enum):
    PDF = "pdf"
    DOCX = "docx"
    TXT = "txt"
    MD = "md"
    EML = "eml"
    CSV = "csv"
    XLSX = "xlsx"


class FileValidationError(Exception):
    """Uploaded file failed content or policy validation."""


class FileTooLargeError(Exception):
    """Uploaded file exceeds configured size limit."""


MIME_BY_TYPE: dict[DetectedFileType, str] = {
    DetectedFileType.PDF: "application/pdf",
    DetectedFileType.DOCX: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    DetectedFileType.TXT: "text/plain",
    DetectedFileType.MD: "text/markdown",
    DetectedFileType.EML: "message/rfc822",
    DetectedFileType.CSV: "text/csv",
    DetectedFileType.XLSX: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def sanitize_original_name(original_name: str) -> str:
    name = original_name.replace("\\", "/").split("/")[-1].strip()
    name = CONTROL_CHARS.sub("", name)
    if not name:
        name = "upload"
    return name[:MAX_ORIGINAL_NAME_LEN]


def assert_file_count_for_input(count: int) -> None:
    settings = get_settings()
    if count > settings.MAX_FILES_PER_INPUT:
        raise FileValidationError(
            f"At most {settings.MAX_FILES_PER_INPUT} files allowed per input"
        )


def _check_zip_bomb(data: bytes) -> None:
    settings = get_settings()
    try:
        with zipfile.ZipFile(BytesIO(data)) as zf:
            if len(zf.infolist()) > settings.ZIP_MAX_ENTRY_COUNT:
                raise FileValidationError("Archive contains too many entries")
            total = sum(info.file_size for info in zf.infolist())
            if total > settings.ZIP_MAX_UNCOMPRESSED_BYTES:
                raise FileValidationError("Archive uncompressed size exceeds limit")
    except zipfile.BadZipFile as exc:
        raise FileValidationError("Invalid ZIP archive") from exc


def _is_pdf(data: bytes) -> bool:
    return data.startswith(b"%PDF-")


def _is_ooxml_word(data: bytes) -> bool:
    if not data.startswith(b"PK"):
        return False
    _check_zip_bomb(data)
    with zipfile.ZipFile(BytesIO(data)) as zf:
        return any(n.startswith("word/") for n in zf.namelist())


def _is_ooxml_xlsx(data: bytes) -> bool:
    if not data.startswith(b"PK"):
        return False
    _check_zip_bomb(data)
    with zipfile.ZipFile(BytesIO(data)) as zf:
        names = zf.namelist()
        return any(n.startswith("xl/") for n in names) and "[Content_Types].xml" in names


def _is_eml(data: bytes) -> bool:
    head = data[:4096]
    if b"From:" not in head and b"from:" not in head:
        return False
    try:
        msg = email.message_from_bytes(data)
    except (UnicodeDecodeError, ValueError, TypeError):
        return False
    return msg.get("From") is not None or msg.get("Subject") is not None


def _is_text_like(data: bytes) -> bool:
    if b"\x00" in data[:8192]:
        return False
    sample = data[:8192]
    try:
        sample.decode("utf-8")
        return True
    except UnicodeDecodeError:
        try:
            sample.decode("latin-1")
            return True
        except UnicodeDecodeError:
            return False


_UPLOAD_EXTENSION_MAP: dict[str, DetectedFileType] = {
    "pdf": DetectedFileType.PDF,
    "docx": DetectedFileType.DOCX,
    "txt": DetectedFileType.TXT,
    "md": DetectedFileType.MD,
    "markdown": DetectedFileType.MD,
    "eml": DetectedFileType.EML,
    "csv": DetectedFileType.CSV,
    "xlsx": DetectedFileType.XLSX,
}

ALLOWED_UPLOAD_EXTENSIONS: tuple[str, ...] = tuple(
    sorted({ext for ext in _UPLOAD_EXTENSION_MAP if ext != "markdown"})
)


def _extension_hint(name: str) -> DetectedFileType | None:
    ext = PurePath(name).suffix.lower().lstrip(".")
    return _UPLOAD_EXTENSION_MAP.get(ext)


def detect_file_type(content: bytes, *, sanitized_name: str) -> DetectedFileType:
    if len(content) == 0:
        raise FileValidationError("Empty file")
    if _is_pdf(content):
        detected = DetectedFileType.PDF
    elif _is_ooxml_word(content):
        detected = DetectedFileType.DOCX
    elif _is_ooxml_xlsx(content):
        detected = DetectedFileType.XLSX
    elif _is_eml(content):
        detected = DetectedFileType.EML
    elif _is_text_like(content):
        hint = _extension_hint(sanitized_name)
        if hint in (DetectedFileType.MD, DetectedFileType.CSV, DetectedFileType.TXT):
            detected = hint
        elif hint == DetectedFileType.EML:
            detected = DetectedFileType.EML
        else:
            detected = DetectedFileType.TXT
    else:
        raise FileValidationError("Unrecognized or disallowed file type")

    hint = _extension_hint(sanitized_name)
    if hint is not None and hint != detected:
        raise FileValidationError(
            f"File content does not match extension (expected {hint.value}, detected {detected.value})"
        )
    return detected


def validate_upload(
    content: bytes,
    *,
    original_name: str,
    content_type: str | None = None,
) -> DetectedFileType:
    settings = get_settings()
    if len(content) > settings.MAX_UPLOAD_FILE_BYTES:
        raise FileTooLargeError(
            f"File exceeds maximum size of {settings.MAX_UPLOAD_FILE_BYTES} bytes"
        )
    sanitized = sanitize_original_name(original_name)
    detected = detect_file_type(content, sanitized_name=sanitized)
    if content_type:
        expected = MIME_BY_TYPE.get(detected, "")
        if expected and content_type.split(";")[0].strip().lower() not in (
            expected.lower(),
            "application/octet-stream",
        ):
            raise FileValidationError("Content-Type does not match detected file type")
    return detected

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from io import BytesIO
from typing import BinaryIO

from app.config import get_settings
from app.services.extraction import ExtractionResult, extract_text
from app.services.file_validation import (
    MIME_BY_TYPE,
    DetectedFileType,
    sanitize_original_name,
    validate_upload,
)
from app.services.storage import delete_file, put_file, read_bounded_stream

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PreparedFileUpload:
    storage_key: str
    sanitized_original_name: str
    mime_type: str
    size_bytes: int
    sha256: str
    detected_type: DetectedFileType
    extraction: ExtractionResult


def prepare_file_upload(
    stream: BinaryIO,
    *,
    original_name: str,
    content_type: str | None = None,
) -> PreparedFileUpload:
    settings = get_settings()
    sanitized = sanitize_original_name(original_name)
    content, sha256, size = read_bounded_stream(
        stream, max_bytes=settings.MAX_UPLOAD_FILE_BYTES
    )
    detected = validate_upload(
        content, original_name=sanitized, content_type=content_type
    )
    mime = MIME_BY_TYPE[detected]
    extraction = extract_text(content, detected)
    put_result = put_file(
        BytesIO(content),
        mime,
        max_bytes=settings.MAX_UPLOAD_FILE_BYTES,
    )
    return PreparedFileUpload(
        storage_key=put_result.storage_key,
        sanitized_original_name=sanitized,
        mime_type=mime,
        size_bytes=size,
        sha256=sha256,
        detected_type=detected,
        extraction=extraction,
    )


def rollback_storage_keys(storage_keys: Sequence[str]) -> None:
    for key in storage_keys:
        try:
            delete_file(key)
        except Exception:  # noqa: BLE001 — best-effort per key; never abort the batch
            logger.warning("Failed to rollback storage object: %s", key)

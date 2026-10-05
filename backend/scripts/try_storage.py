"""Upload a sample file to MinIO, verify SHA-256, extract text, delete."""

from __future__ import annotations

import hashlib
import sys
from io import BytesIO
from pathlib import Path

from app.services.file_service import prepare_file_upload, rollback_storage_keys
from app.services.storage import delete_file, ensure_bucket, get_file_stream


def main() -> int:
    sample = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "sample_upload.txt"
    if not sample.exists():
        sample.write_text("ScopeDesk storage smoke test.\n", encoding="utf-8")
    data = sample.read_bytes()
    ensure_bucket()
    prepared = prepare_file_upload(
        BytesIO(data),
        original_name="sample_upload.txt",
        content_type="text/plain",
    )
    print(f"storage_key={prepared.storage_key}")
    print(f"sha256={prepared.sha256}")
    print(f"size_bytes={prepared.size_bytes}")

    downloaded = get_file_stream(prepared.storage_key).read()
    digest = hashlib.sha256(downloaded).hexdigest()
    print(f"download_sha256={digest}")
    print(f"sha_match={digest == prepared.sha256}")
    print(f"extracted_preview={prepared.extraction.text[:200]!r}")

    delete_file(prepared.storage_key)
    rollback_storage_keys([prepared.storage_key])
    print("deleted_ok=True")
    return 0 if digest == prepared.sha256 else 1


if __name__ == "__main__":
    sys.exit(main())

from __future__ import annotations

from io import BytesIO

import pytest
from botocore.exceptions import ClientError

from app.config import get_settings
from app.services.file_service import prepare_file_upload, rollback_storage_keys
from app.services.storage import (
    delete_file,
    ensure_bucket,
    get_file_stream,
    get_s3_client,
    put_file,
)
from tests.fixtures.file_samples import sample_txt


def _minio_available() -> bool:
    settings = get_settings()
    client = get_s3_client(settings=settings)
    try:
        client.head_bucket(Bucket=settings.S3_TEST_BUCKET)
        return True
    except ClientError:
        try:
            ensure_bucket(client=client, bucket=settings.S3_TEST_BUCKET)
            return True
        except ClientError:
            return False


pytestmark = pytest.mark.skipif(not _minio_available(), reason="MinIO not available")


@pytest.fixture(autouse=True)
def _use_test_bucket(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("S3_BUCKET", get_settings().S3_TEST_BUCKET)
    monkeypatch.setenv("S3_PATH_STYLE", "true")
    get_settings.cache_clear()
    ensure_bucket(bucket=get_settings().S3_TEST_BUCKET)
    yield
    get_settings.cache_clear()


def test_put_get_delete_sha256() -> None:
    settings = get_settings()
    data = sample_txt()
    result = put_file(
        BytesIO(data),
        "text/plain",
        bucket=settings.S3_TEST_BUCKET,
    )
    assert "/" in result.storage_key
    assert "notes" not in result.storage_key
    assert result.sha256
    assert result.size_bytes == len(data)

    downloaded = get_file_stream(result.storage_key, bucket=settings.S3_TEST_BUCKET).read()
    assert downloaded == data

    delete_file(result.storage_key, bucket=settings.S3_TEST_BUCKET)


def test_prepare_file_upload_integration() -> None:
    prepared = prepare_file_upload(
        BytesIO(sample_txt()),
        original_name="notes.txt",
        content_type="text/plain",
    )
    assert prepared.sha256
    assert "notes.txt" not in prepared.storage_key
    rollback_storage_keys([prepared.storage_key])

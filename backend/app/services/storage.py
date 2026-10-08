from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from typing import BinaryIO

import boto3
from botocore.client import BaseClient
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.config import Settings, get_settings
from app.services.file_validation import FileTooLargeError

logger = logging.getLogger(__name__)

STORAGE_UNAVAILABLE_DETAIL = "Storage temporarily unavailable"


class StorageError(Exception):
    """S3-compatible storage operation failed."""


@dataclass(frozen=True)
class PutFileResult:
    storage_key: str
    size_bytes: int
    sha256: str


def _s3_config(settings: Settings) -> Config:
    if settings.S3_PATH_STYLE:
        return Config(s3={"addressing_style": "path"})
    return Config()


def get_s3_client(*, settings: Settings | None = None) -> BaseClient:
    settings = settings or get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.S3_ENDPOINT_URL,
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET_KEY,
        region_name=settings.S3_REGION,
        config=_s3_config(settings),
    )


def generate_storage_key(*, now: datetime | None = None) -> str:
    ts = now or datetime.now(UTC)
    return f"uploads/{ts:%Y/%m}/{uuid.uuid4()}"


def _bucket_name(settings: Settings, bucket: str | None) -> str:
    return bucket or settings.S3_BUCKET


def _wrap_client_error(exc: Exception, action: str) -> StorageError:
    logger.debug("Storage %s failed: %s", action, type(exc).__name__)
    return StorageError(f"Storage {action} failed")


def ensure_bucket(*, client: BaseClient | None = None, bucket: str | None = None) -> None:
    settings = get_settings()
    client = client or get_s3_client(settings=settings)
    name = _bucket_name(settings, bucket)
    try:
        client.head_bucket(Bucket=name)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code not in ("404", "NoSuchBucket", "403", "NotFound"):
            raise _wrap_client_error(exc, "head_bucket") from exc
        try:
            client.create_bucket(Bucket=name)
        except (ClientError, BotoCoreError) as create_exc:
            raise _wrap_client_error(create_exc, "create_bucket") from create_exc


def read_bounded_stream(
    body: BinaryIO,
    *,
    max_bytes: int,
) -> tuple[bytes, str, int]:
    hasher = hashlib.sha256()
    size = 0
    chunks: list[bytes] = []
    while True:
        chunk = body.read(65536)
        if not chunk:
            break
        size += len(chunk)
        if size > max_bytes:
            raise FileTooLargeError(f"File exceeds maximum size of {max_bytes} bytes")
        hasher.update(chunk)
        chunks.append(chunk)
    data = b"".join(chunks)
    return data, hasher.hexdigest(), size


def put_file(
    body: BinaryIO,
    content_type: str,
    *,
    max_bytes: int | None = None,
    client: BaseClient | None = None,
    bucket: str | None = None,
    storage_key: str | None = None,
) -> PutFileResult:
    settings = get_settings()
    client = client or get_s3_client(settings=settings)
    name = _bucket_name(settings, bucket)
    limit = max_bytes if max_bytes is not None else settings.MAX_UPLOAD_FILE_BYTES
    key = storage_key or generate_storage_key()
    data, digest, size = read_bounded_stream(body, max_bytes=limit)
    try:
        client.put_object(
            Bucket=name,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
    except (ClientError, BotoCoreError) as exc:
        raise _wrap_client_error(exc, "put_object") from exc
    return PutFileResult(storage_key=key, size_bytes=size, sha256=digest)


def get_file_stream(
    storage_key: str,
    *,
    client: BaseClient | None = None,
    bucket: str | None = None,
) -> BinaryIO:
    settings = get_settings()
    client = client or get_s3_client(settings=settings)
    name = _bucket_name(settings, bucket)
    try:
        response = client.get_object(Bucket=name, Key=storage_key)
    except (ClientError, BotoCoreError) as exc:
        raise _wrap_client_error(exc, "get_object") from exc
    body = response["Body"].read()
    return BytesIO(body)


def delete_file(
    storage_key: str,
    *,
    client: BaseClient | None = None,
    bucket: str | None = None,
) -> None:
    settings = get_settings()
    client = client or get_s3_client(settings=settings)
    name = _bucket_name(settings, bucket)
    try:
        client.delete_object(Bucket=name, Key=storage_key)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in ("NoSuchKey", "404"):
            return
        raise _wrap_client_error(exc, "delete_object") from exc
    except BotoCoreError as exc:
        raise _wrap_client_error(exc, "delete_object") from exc

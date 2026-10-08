"""Matrix diagnostic for S3 put/get against MinIO (scopedesk-test only)."""

from __future__ import annotations

import hashlib
import sys
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from io import BytesIO

import boto3
from botocore.client import BaseClient
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.config import Settings, get_settings
from app.services.storage import get_s3_client

KEY_PREFIX = "diagnostics/"
REQUIRED_BUCKET_SUFFIX = "-test"
SIZES_BYTES = [
    1024,
    4 * 1024,
    6 * 1024,
    64 * 1024,
    1024 * 1024,
    10 * 1024 * 1024,
]
SIZE_LABELS = ["1KB", "4KB", "6KB", "64KB", "1MB", "10MB"]
CONFIG_IDS = ("a", "b", "c", "d", "e")
CELL_PAUSE_SECONDS = 1.0


@dataclass
class CellResult:
    ok: bool
    error_code: str | None = None
    http_status: int | None = None
    message: str | None = None
    request_id: str | None = None
    retry_attempts: int | None = None
    headers: dict[str, str] = field(default_factory=dict)
    retried: bool = False


@dataclass
class RunState:
    bucket: str
    run_id: str
    written_keys: list[str] = field(default_factory=list)


def _assert_safe_bucket(bucket: str) -> None:
    if not bucket.endswith(REQUIRED_BUCKET_SUFFIX):
        raise SystemExit(
            f"Refusing to run: bucket {bucket!r} must end with {REQUIRED_BUCKET_SUFFIX!r}",
        )


def _assert_safe_key(key: str) -> None:
    if not key.startswith(KEY_PREFIX):
        raise SystemExit(f"Refusing to run: key {key!r} must start with {KEY_PREFIX!r}")


def _payload(size: int) -> bytes:
    digest = hashlib.sha256(str(size).encode()).digest()
    out = bytearray(size)
    for i in range(size):
        out[i] = digest[i % len(digest)]
    return bytes(out)


def _client_a(settings: Settings) -> BaseClient:
    return get_s3_client(settings=settings)


def _client_b(settings: Settings) -> BaseClient:
    return boto3.client(
        "s3",
        endpoint_url=settings.S3_ENDPOINT_URL,
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET_KEY,
        region_name=settings.S3_REGION,
        config=Config(
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        ),
    )


def _client_c(settings: Settings) -> BaseClient:
    return boto3.client(
        "s3",
        endpoint_url=settings.S3_ENDPOINT_URL,
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET_KEY,
        region_name=settings.S3_REGION,
        config=Config(
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
            signature_version="s3v4",
            s3={"addressing_style": "path"},
        ),
    )


def _failure_from_exc(exc: Exception) -> CellResult:
    if isinstance(exc, ClientError):
        meta = exc.response.get("ResponseMetadata", {})
        err = exc.response.get("Error", {})
        headers = {
            k: v
            for k, v in (meta.get("HTTPHeaders") or {}).items()
            if k.lower() not in ("authorization", "x-amz-security-token")
        }
        return CellResult(
            ok=False,
            error_code=err.get("Code"),
            http_status=meta.get("HTTPStatusCode"),
            message=err.get("Message"),
            request_id=meta.get("RequestId"),
            retry_attempts=meta.get("RetryAttempts"),
            headers=headers,
        )
    return CellResult(
        ok=False,
        error_code=type(exc).__name__,
        message=str(exc)[:500],
    )


def _put_get_verify_delete(
    client: BaseClient,
    *,
    bucket: str,
    key: str,
    data: bytes,
    config_id: str,
) -> tuple[CellResult, bool]:
    """Return (result, needs_cleanup) — needs_cleanup if object may still exist."""
    _assert_safe_key(key)
    put_completed = False
    try:
        if config_id == "d":
            buf = BytesIO(data)
            buf.seek(0)
            client.upload_fileobj(
                buf,
                bucket,
                key,
                ExtraArgs={"ContentType": "application/octet-stream"},
            )
        elif config_id == "e":
            client.put_object(
                Bucket=bucket,
                Key=key,
                Body=data,
                ContentLength=len(data),
                ContentType="application/octet-stream",
            )
        else:
            client.put_object(
                Bucket=bucket,
                Key=key,
                Body=data,
                ContentType="application/octet-stream",
            )
        put_completed = True
        response = client.get_object(Bucket=bucket, Key=key)
        body = response["Body"].read()
        if hashlib.sha256(body).hexdigest() != hashlib.sha256(data).hexdigest():
            return (
                CellResult(ok=False, error_code="SHA256Mismatch", message="get_object digest mismatch"),
                True,
            )
        client.delete_object(Bucket=bucket, Key=key)
        return CellResult(ok=True), False
    except (ClientError, BotoCoreError) as exc:
        return _failure_from_exc(exc), put_completed


def _cleanup_keys(client: BaseClient, bucket: str, keys: list[str]) -> None:
    for key in keys:
        _assert_safe_key(key)
        try:
            client.delete_object(Bucket=bucket, Key=key)
        except ClientError:
            pass


def _run_cell(
    client_factory: Callable[[], BaseClient],
    state: RunState,
    size: int,
    config_id: str,
) -> CellResult:
    bucket = state.bucket
    key = f"{KEY_PREFIX}{state.run_id}/{config_id}/{size}.bin"
    _assert_safe_key(key)
    data = _payload(size)
    client = client_factory()
    result, needs_cleanup = _put_get_verify_delete(
        client,
        bucket=bucket,
        key=key,
        data=data,
        config_id=config_id,
    )
    if needs_cleanup:
        state.written_keys.append(key)
    return result


def _ensure_test_bucket(client: BaseClient, bucket: str) -> None:
    _assert_safe_bucket(bucket)
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in ("404", "NoSuchBucket", "NotFound"):
            client.create_bucket(Bucket=bucket)
        else:
            raise


def _bisect_threshold(client_factory: Callable[[], BaseClient], state: RunState) -> int | None:
    low = 1024
    high = 6 * 1024
    for size in SIZES_BYTES:
        r = _run_cell(client_factory, state, size, "a")
        if r.ok:
            low = size
        else:
            high = size
            break
    if low >= high:
        return None
    while low + 1 < high:
        mid = (low + high) // 2
        r = _run_cell(client_factory, state, mid, "a")
        if r.ok:
            low = mid
        else:
            high = mid
        time.sleep(CELL_PAUSE_SECONDS)
    return high


def _print_failure_detail(label: str, result: CellResult) -> None:
    print(f"  [{label}] FAIL code={result.error_code} http={result.http_status}")
    print(f"    message={result.message!r}")
    print(f"    RequestId={result.request_id} RetryAttempts={result.retry_attempts}")
    if result.headers:
        safe = {k: v for k, v in result.headers.items()}
        print(f"    headers={safe}")


def _matrix_table(results: dict[str, dict[int, CellResult]]) -> None:
    header = "size".ljust(8) + "".join(c.rjust(10) for c in CONFIG_IDS)
    print(header)
    print("-" * len(header))
    for label, size in zip(SIZE_LABELS, SIZES_BYTES, strict=True):
        row = label.ljust(8)
        for cid in CONFIG_IDS:
            cell = results[cid][size]
            if cell.ok:
                row += "ok".rjust(14)
            else:
                code = cell.error_code or "?"
                row += code.rjust(14)
        print(row)


def main() -> int:
    settings = get_settings()
    bucket = settings.S3_TEST_BUCKET
    _assert_safe_bucket(bucket)

    run_id = uuid.uuid4().hex[:12]
    state = RunState(bucket=bucket, run_id=run_id)
    def client_a() -> BaseClient:
        return _client_a(settings)

    def client_b() -> BaseClient:
        return _client_b(settings)

    def client_c() -> BaseClient:
        return _client_c(settings)

    factories: dict[str, Callable[[], BaseClient]] = {
        "a": client_a,
        "b": client_b,
        "c": client_c,
        "d": client_a,
        "e": client_a,
    }

    results: dict[str, dict[int, CellResult]] = {c: {} for c in CONFIG_IDS}
    first_failure: tuple[str, int, CellResult] | None = None

    try:
        _ensure_test_bucket(client_a(), bucket)
        for config_id in CONFIG_IDS:
            for size in SIZES_BYTES:
                cell = _run_cell(factories[config_id], state, size, config_id)
                if not cell.ok and first_failure is None:
                    time.sleep(CELL_PAUSE_SECONDS)
                    retry = _run_cell(factories[config_id], state, size, config_id)
                    retry.retried = True
                    cell = retry
                    first_failure = (config_id, size, cell)
                    print(
                        f"\nFirst failure (with one retry): config={config_id} size={size}",
                    )
                    _print_failure_detail(f"{config_id}/{size}", cell)
                results[config_id][size] = cell
                time.sleep(CELL_PAUSE_SECONDS)

        print("\n=== Results matrix (size × config) ===")
        _matrix_table(results)

        all_ok = all(r.ok for cid in CONFIG_IDS for r in results[cid].values())
        any_config_all_ok = any(
            all(results[cid][s].ok for s in SIZES_BYTES) for cid in ("a", "b", "c")
        )

        if all_ok:
            print("\nAll configurations passed all sizes.")
            return 0

        boundaries: set[tuple[int | None, str | None]] = set()
        for cid in ("a", "b", "c"):
            fail_size = next((s for s in SIZES_BYTES if not results[cid][s].ok), None)
            pass_max = None
            for s in SIZES_BYTES:
                if results[cid][s].ok:
                    pass_max = s
            boundaries.add((pass_max, fail_size and results[cid][fail_size].error_code))

        same_boundary = len({b[0] for b in boundaries}) == 1 and len({b[1] for b in boundaries}) == 1

        if not any_config_all_ok and same_boundary:
            print("\nEvery put-style config fails at the same boundary; bisecting config (a)...")
            threshold = _bisect_threshold(client_a, state)
            if threshold is not None:
                print(f"Exact byte threshold (first failing size): {threshold}")
            return 2

        if results["b"] and all(results["b"][s].ok for s in SIZES_BYTES):
            print("\nConfig (b) passes all sizes — apply checksum when_required in storage.py.")
            return 0

        for cid in ("b", "c"):
            if all(results[cid][s].ok for s in SIZES_BYTES):
                print(f"\nConfig ({cid}) passes all sizes.")
                return 0

        return 1
    finally:
        cleanup_client = client_a()
        unique_keys = list(dict.fromkeys(state.written_keys))
        if unique_keys:
            print(f"\nCleaning up {len(unique_keys)} diagnostic key(s)...")
            _cleanup_keys(cleanup_client, bucket, unique_keys)


if __name__ == "__main__":
    sys.exit(main())

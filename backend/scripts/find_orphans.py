"""List (and optionally delete) S3 objects under uploads/ with no files.storage_key row."""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

from sqlalchemy import create_engine, func, select

from app.config import get_settings
from app.models.files import File
from app.services.storage import StorageError, delete_file, get_s3_client


def _database_name(database_url: str) -> str:
    parsed = urlparse(database_url.replace("+psycopg", ""))
    path = parsed.path.lstrip("/")
    return path.split("?")[0] if path else "(unknown)"


def _list_orphans(*, min_age_seconds: int) -> list[tuple[str, int, datetime]]:
    settings = get_settings()
    client = get_s3_client(settings=settings)
    engine = create_engine(settings.DATABASE_URL)
    cutoff = datetime.now(UTC) - timedelta(seconds=min_age_seconds)

    with engine.connect() as conn:
        known = set(conn.scalars(select(File.storage_key)).all())

    orphans: list[tuple[str, int, datetime]] = []
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=settings.S3_BUCKET, Prefix="uploads/"):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key in known:
                continue
            modified = obj["LastModified"]
            if modified.tzinfo is None:
                modified = modified.replace(tzinfo=UTC)
            else:
                modified = modified.astimezone(UTC)
            if modified > cutoff:
                continue
            orphans.append((key, int(obj["Size"]), modified))
    orphans.sort(key=lambda row: row[0])
    return orphans


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--min-age",
        type=int,
        default=3600,
        metavar="SECONDS",
        help="Only include objects older than this many seconds (default: 3600; use 0 for all)",
    )
    parser.add_argument(
        "--delete",
        action="store_true",
        help="Delete listed orphans after confirmation (development only)",
    )
    args = parser.parse_args(argv)
    if args.min_age < 0:
        print("--min-age must be >= 0", file=sys.stderr)
        return 2

    settings = get_settings()
    orphans = _list_orphans(min_age_seconds=args.min_age)

    print(f"database={_database_name(settings.DATABASE_URL)}")
    print(f"s3_endpoint={settings.S3_ENDPOINT_URL}")
    print(f"s3_bucket={settings.S3_BUCKET}")
    print(f"min_age_seconds={args.min_age}")
    print(f"orphan_count={len(orphans)}")
    for key, size, modified in orphans:
        print(f"{key}\tsize={size}\tlast_modified={modified.isoformat()}")

    if not args.delete:
        return 0

    if settings.APP_ENV != "development":
        print(
            f"Refusing --delete: APP_ENV is {settings.APP_ENV!r} (must be 'development').",
            file=sys.stderr,
        )
        return 1

    engine = create_engine(settings.DATABASE_URL)
    with engine.connect() as conn:
        file_count = conn.scalar(select(func.count()).select_from(File))

    if file_count == 0:
        print(
            "\n*** WARNING: files table is EMPTY but the bucket may contain objects. ***",
            file=sys.stderr,
        )
        print(
            "*** Deleting orphans could remove data from a misconfigured environment. ***\n",
            file=sys.stderr,
        )

    if not orphans:
        print("Nothing to delete.")
        return 0

    print(
        f"\nAbout to delete {len(orphans)} object(s) from bucket {settings.S3_BUCKET!r} "
        f"at {settings.S3_ENDPOINT_URL}."
    )
    typed = input("Type the bucket name to confirm deletion: ").strip()
    if typed != settings.S3_BUCKET:
        print("Bucket name did not match; aborting.")
        return 1

    deleted = 0
    for key, _size, _modified in orphans:
        try:
            delete_file(key)
            deleted += 1
            print(f"deleted {key}")
        except StorageError:
            print(f"failed to delete {key}: StorageError", file=sys.stderr)

    print(f"deleted_count={deleted}")
    return 0 if deleted == len(orphans) else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Report files rows whose storage_key is missing in the configured S3 bucket (read-only)."""

from __future__ import annotations

import sys

from botocore.exceptions import ClientError
from sqlalchemy import create_engine, select

from app.config import get_settings
from app.models.files import File
from app.services.storage import get_s3_client


def main() -> int:
    settings = get_settings()
    client = get_s3_client()
    bucket = settings.S3_BUCKET
    engine = create_engine(settings.DATABASE_URL)

    missing: list[str] = []
    total = 0
    with engine.connect() as conn:
        keys = conn.scalars(select(File.storage_key)).all()
        total = len(keys)
        for key in keys:
            try:
                client.head_object(Bucket=bucket, Key=key)
            except ClientError as exc:
                code = exc.response.get("Error", {}).get("Code", "")
                if code in ("404", "NoSuchKey", "NotFound"):
                    missing.append(key)
                else:
                    print(f"error checking {key}: {code}", file=sys.stderr)

    print(f"database={settings.DATABASE_URL.split('/')[-1].split('?')[0]}")
    print(f"s3_bucket={bucket}")
    print(f"files_rows={total}")
    print(f"missing_in_bucket={len(missing)}")
    for key in missing[:50]:
        print(f"missing {key}")
    if len(missing) > 50:
        print(f"... and {len(missing) - 50} more")
    return 0


if __name__ == "__main__":
    sys.exit(main())

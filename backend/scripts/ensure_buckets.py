"""Create S3 buckets from settings if they do not exist."""

from __future__ import annotations

import sys

from app.config import get_settings
from app.services.storage import ensure_bucket


def main() -> int:
    settings = get_settings()
    ensure_bucket()
    ensure_bucket(bucket=settings.S3_TEST_BUCKET)
    print(f"ok bucket={settings.S3_BUCKET}")
    print(f"ok bucket={settings.S3_TEST_BUCKET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

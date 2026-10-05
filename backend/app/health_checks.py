from dataclasses import dataclass

from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.config import get_settings
from app.db import engine
from app.services.storage import get_s3_client


@dataclass(frozen=True)
class DependencyStatus:
    database: str
    object_storage: str

    @property
    def is_ready(self) -> bool:
        return self.database == "ok" and self.object_storage == "ok"


def _check_database() -> str:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return "ok"
    except SQLAlchemyError as exc:
        return f"error: {exc}"


def _check_object_storage() -> str:
    settings = get_settings()
    try:
        client = get_s3_client()
        client.head_bucket(Bucket=settings.S3_BUCKET)
        return "ok"
    except (BotoCoreError, ClientError) as exc:
        return f"error: {exc}"


def run_dependency_checks() -> DependencyStatus:
    return DependencyStatus(
        database=_check_database(),
        object_storage=_check_object_storage(),
    )


def assert_dependencies_ready() -> None:
    status = run_dependency_checks()
    if status.is_ready:
        return
    failures = [
        f"database={status.database}",
        f"object_storage={status.object_storage}",
    ]
    raise RuntimeError("Dependency checks failed: " + "; ".join(failures))

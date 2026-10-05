import os

import pytest
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError

from alembic import command
from app.config import get_settings
from app.db import reset_engine
from tests.db_utils import ensure_database_exists, get_test_database_url

# Tests run without Docker; real dependency checks run in dev/prod startup.
os.environ.setdefault("SKIP_STARTUP_CHECKS", "true")
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("ENABLE_TEST_ROUTES", "true")
os.environ.setdefault("ADMIN_EMAIL", "admin@example.test")
os.environ.setdefault("ADMIN_PASSWORD", "test-admin-password")
os.environ.setdefault("ADMIN_FULL_NAME", "Test Admin")


@pytest.fixture(scope="session")
def migrated_test_engine():
    test_url = get_test_database_url()
    try:
        ensure_database_exists(test_url)
    except (OSError, SQLAlchemyError) as exc:
        pytest.skip(f"Postgres not available for migration tests: {exc}")

    os.environ["DATABASE_URL"] = test_url
    get_settings.cache_clear()
    reset_engine()

    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")

    engine = create_engine(test_url)
    yield engine
    engine.dispose()
    get_settings.cache_clear()
    reset_engine()

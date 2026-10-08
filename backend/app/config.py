from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_ENV: str = "development"
    SKIP_STARTUP_CHECKS: bool = False
    TRUST_X_FORWARDED_FOR: bool = False
    DATABASE_URL: str
    GEMINI_API_KEY: str
    GEMINI_MODEL: str
    S3_ENDPOINT_URL: str
    S3_BUCKET: str
    S3_ACCESS_KEY: str
    S3_SECRET_KEY: str
    S3_REGION: str = "us-east-1"
    S3_TEST_BUCKET: str = "scopedesk-test"
    S3_PATH_STYLE: bool = True
    MAX_UPLOAD_FILE_BYTES: int = 10_485_760
    MAX_FILES_PER_INPUT: int = 10
    RECEIVED_AT_FUTURE_TOLERANCE_SECONDS: int = 300
    MAX_INTAKE_REQUEST_BYTES: int = 10_485_760 * 10 + 1_048_576
    MAX_EXTRACTED_TEXT_CHARS: int = 500_000
    ZIP_MAX_UNCOMPRESSED_BYTES: int = 50_000_000
    ZIP_MAX_ENTRY_COUNT: int = 500
    JWT_SECRET: str
    ACCESS_TOKEN_MINUTES: int = 15
    REFRESH_TOKEN_DAYS: int = 7
    REFRESH_COOKIE_NAME: str = "scopedesk_refresh"
    ADMIN_EMAIL: str
    ADMIN_PASSWORD: str
    ADMIN_FULL_NAME: str
    ALLOWED_ORIGINS: Annotated[list[str], NoDecode]
    GENERATION_TIMEOUT_SECONDS: float = 300.0
    GENERATION_RECOVERY_MARGIN_SECONDS: float = 60.0
    MAX_CONCURRENT_GENERATIONS: int = 2
    MAX_PROMPT_CHARS: int = 300_000
    SOFT_CAP_AMBIGUITIES: int = 25
    SOFT_CAP_DEPENDENCIES: int = 20
    SOFT_CAP_ASSUMPTIONS: int = 20
    SOFT_CAP_GAPS: int = 40
    SOFT_CAP_GAP_CLIENT_QUESTIONS: int = 30
    MAX_DOCX_EXPORT_CONTENT_CHARS: int = 1_000_000

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_allowed_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("["):
                import json

                return json.loads(stripped)
            return [origin.strip() for origin in stripped.split(",") if origin.strip()]
        raise ValueError("ALLOWED_ORIGINS must be a comma-separated string or JSON list")

    @model_validator(mode="after")
    def validate_jwt_secret_strength(self) -> Settings:
        if self.APP_ENV != "development" and len(self.JWT_SECRET) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters outside development")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()

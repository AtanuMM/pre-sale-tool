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
    SOFT_CAP_FEATURE_MODULES: int = 30
    FEATURE_LIST_MAX_FEATURES: int = 250
    MAX_DOCX_EXPORT_CONTENT_CHARS: int = 1_000_000
    ESTIMATE_MAX_COMPONENTS: int = 10
    ESTIMATE_MAX_WORK_PACKAGES: int = 40
    ESTIMATE_MAX_EFFORT_LINES: int = 1800
    ESTIMATE_MAX_ASSUMPTIONS: int = 40
    ESTIMATE_MAX_OUTPUT_TOKENS: int = 65_536
    ESTIMATE_LEVERAGE_HIGH: float = 1.0
    ESTIMATE_LEVERAGE_MEDIUM: float = 0.6
    ESTIMATE_LEVERAGE_LOW: float = 0.25
    ESTIMATE_RISK_HIGH: float = 0.0
    ESTIMATE_RISK_MEDIUM: float = 0.10
    ESTIMATE_RISK_LOW: float = 0.25
    ESTIMATE_WEEKS_PER_MONTH: float = 4.33
    ESTIMATE_GENERATION_TIMEOUT_SECONDS: float = 900.0
    ESTIMATE_BATCH_SIZE: int = 20
    ESTIMATE_AI_CAP_HIGH: float = 0.30
    ESTIMATE_AI_CAP_MEDIUM: float = 0.15
    ESTIMATE_AI_CAP_LOW: float = 0.05
    ESTIMATE_AI_CAP_NONE: float = 0.0
    ESTIMATE_AI_PROJECT_CAP: float = 0.25
    ESTIMATE_BUFFER_HIGH: float = 0.15
    ESTIMATE_BUFFER_MEDIUM: float = 0.25
    ESTIMATE_BUFFER_LOW: float = 0.40
    ESTIMATE_MAX_HOURS_PER_LINE: float = 400.0
    ESTIMATE_WORST_TO_LIKELY_CAP: float = 4.0
    ESTIMATE_STABILIZATION_FLOOR: float = 0.15
    ESTIMATE_UAT_PCT: float = 0.05
    ESTIMATE_DEPLOYMENT_PCT: float = 0.03
    ESTIMATE_DOCS_PCT: float = 0.04
    ESTIMATE_HYPERCARE_PCT: float = 0.05
    ESTIMATE_HYPERCARE_WEEKS: float = 2.0
    ESTIMATE_QA_CRUD_RATIO: float = 0.30
    ESTIMATE_QA_RISK_RATIO_MIN: float = 0.40
    ESTIMATE_QA_RISK_RATIO_MAX: float = 0.50
    SOW_STANDARD_TERMS_VERSION: str = "2026-1"
    SOW_MAX_OUTPUT_TOKENS: int = 65_536
    SOW_MAX_OBJECTIVES: int = 12
    SOW_MAX_SUCCESS_CRITERIA: int = 12
    SOW_MAX_GLOSSARY: int = 15
    SOW_MAX_MILESTONES: int = 24
    SOW_MAX_CLIENT_RESPONSIBILITIES: int = 25
    SOW_MAX_ASSUMPTIONS: int = 30
    SOW_MAX_RISKS: int = 20
    SOW_MAX_OUT_OF_SCOPE: int = 20
    SOW_MAX_CONSTRAINTS: int = 20
    SRS_GENERATION_TIMEOUT_SECONDS: float = 1800.0
    SRS_MODULE_BATCH_SIZE: int = 10
    SRS_MAX_OUTPUT_TOKENS: int = 65_536
    SPRINT_PLAN_GENERATION_TIMEOUT_SECONDS: float = 1200.0
    SPRINT_PLAN_MODULE_BATCH_SIZE: int = 2
    SPRINT_PLAN_GOALS_BATCH_SIZE: int = 25
    SPRINT_PLAN_MAX_OUTPUT_TOKENS: int = 65_536

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

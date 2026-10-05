"""Gemini structured generation with retries and validation."""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from typing import Generic, TypeVar

from google.genai import Client, types
from google.genai.errors import ClientError, ServerError
from pydantic import BaseModel, ValidationError

from app.config import get_settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

MAX_API_ATTEMPTS = 5
MAX_API_WAIT_SECONDS = 60.0
BASE_DELAY_SECONDS = 1.0
MAX_DELAY_SECONDS = 30.0
JITTER_SECONDS = 0.5

_client: Client | None = None


class LLMError(Exception):
    """Base error for Gemini integration failures."""


class LLMRateLimitError(LLMError):
    """Rate limit (429) persisted after retries."""


class LLMValidationError(LLMError):
    """Structured output failed Pydantic validation after retries."""


@dataclass(frozen=True)
class StructuredGenerationResult(Generic[T]):
    data: T
    model_id: str
    tokens_in: int | None
    tokens_out: int | None


def _get_client() -> Client:
    global _client
    if _client is None:
        settings = get_settings()
        _client = Client(api_key=settings.GEMINI_API_KEY)
    return _client


def reset_client_for_tests() -> None:
    """Clear cached client (tests only)."""
    global _client
    _client = None


def _parse_retry_after_seconds(exc: ClientError | ServerError) -> float | None:
    response = getattr(exc, "response", None)
    if response is None:
        return None
    headers = getattr(response, "headers", None)
    if headers is None:
        return None
    raw = headers.get("retry-after") or headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return None


def _compute_backoff_seconds(
    attempt: int, exc: ClientError | ServerError
) -> float:
    retry_after = _parse_retry_after_seconds(exc)
    if retry_after is not None:
        delay = retry_after
    else:
        delay = min(MAX_DELAY_SECONDS, BASE_DELAY_SECONDS * (2**attempt))
    delay += random.uniform(0.0, JITTER_SECONDS)
    return min(delay, MAX_DELAY_SECONDS)


def _is_retryable_api_error(exc: Exception) -> bool:
    if isinstance(exc, ServerError):
        return True
    if isinstance(exc, ClientError):
        return exc.code == 429
    return False


def _raise_llm_error(exc: Exception) -> None:
    if isinstance(exc, ClientError) and exc.code == 429:
        raise LLMRateLimitError(str(exc)) from exc
    if isinstance(exc, (ClientError, ServerError)):
        raise LLMError(str(exc)) from exc
    raise LLMError(str(exc)) from exc


def _extract_usage(
    response: types.GenerateContentResponse,
) -> tuple[int | None, int | None]:
    usage = response.usage_metadata
    if usage is None:
        return None, None
    tokens_in = usage.prompt_token_count
    tokens_out = usage.candidates_token_count
    return tokens_in, tokens_out


def _generate_content_once(
    *,
    model_id: str,
    prompt: str,
    schema: type[T],
    system: str | None,
) -> types.GenerateContentResponse:
    config_kwargs: dict[str, object] = {
        "response_mime_type": "application/json",
        "response_schema": schema,
    }
    if system is not None:
        config_kwargs["system_instruction"] = system
    config = types.GenerateContentConfig(**config_kwargs)
    client = _get_client()
    return client.models.generate_content(
        model=model_id,
        contents=prompt,
        config=config,
    )


def _call_with_api_retries(
    *,
    model_id: str,
    prompt: str,
    schema: type[T],
    system: str | None,
) -> types.GenerateContentResponse:
    total_wait = 0.0
    last_retryable: ClientError | ServerError | None = None

    for attempt in range(MAX_API_ATTEMPTS):
        try:
            return _generate_content_once(
                model_id=model_id,
                prompt=prompt,
                schema=schema,
                system=system,
            )
        except (ClientError, ServerError) as exc:
            if isinstance(exc, ClientError) and exc.code != 429:
                logger.info(
                    "Gemini non-retryable client error code=%s attempt=%s",
                    exc.code,
                    attempt + 1,
                )
                raise LLMError(str(exc)) from exc
            if not _is_retryable_api_error(exc):
                _raise_llm_error(exc)
            last_retryable = exc
            if attempt + 1 >= MAX_API_ATTEMPTS:
                break
            delay = _compute_backoff_seconds(attempt, exc)
            if total_wait + delay > MAX_API_WAIT_SECONDS:
                break
            logger.info(
                "Gemini retryable error code=%s attempt=%s sleep=%.2fs",
                exc.code,
                attempt + 1,
                delay,
            )
            time.sleep(delay)
            total_wait += delay

    if last_retryable is not None and last_retryable.code == 429:
        raise LLMRateLimitError(str(last_retryable)) from last_retryable
    if last_retryable is not None:
        raise LLMError(str(last_retryable)) from last_retryable
    raise LLMError("Gemini request failed without a response")


def _validate_response_text(text: str | None, schema: type[T]) -> T:
    if text is None or not text.strip():
        return schema.model_validate_json("{}")
    return schema.model_validate_json(text)


def generate_structured_result(
    prompt: str,
    schema: type[T],
    *,
    system: str | None = None,
    validation_max_attempts: int = 2,
) -> StructuredGenerationResult[T]:
    if validation_max_attempts < 1:
        raise ValueError("validation_max_attempts must be at least 1")

    settings = get_settings()
    model_id = settings.GEMINI_MODEL
    current_prompt = prompt
    last_validation_error: ValidationError | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None

    for validation_attempt in range(validation_max_attempts):
        logger.info(
            "Structured generation attempt %s/%s model=%s prompt_chars=%s",
            validation_attempt + 1,
            validation_max_attempts,
            model_id,
            len(current_prompt),
        )
        response = _call_with_api_retries(
            model_id=model_id,
            prompt=current_prompt,
            schema=schema,
            system=system,
        )
        in_count, out_count = _extract_usage(response)
        tokens_in = in_count if in_count is not None else tokens_in
        tokens_out = out_count if out_count is not None else tokens_out

        try:
            validated = _validate_response_text(response.text, schema)
            return StructuredGenerationResult(
                data=validated,
                model_id=model_id,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
            )
        except ValidationError as exc:
            last_validation_error = exc
            logger.info(
                "Validation failed on attempt %s/%s: %s",
                validation_attempt + 1,
                validation_max_attempts,
                exc.error_count(),
            )
            if validation_attempt + 1 >= validation_max_attempts:
                break
            current_prompt = (
                f"{prompt}\n\n"
                "Previous JSON failed validation. Fix the output so it strictly "
                f"matches the schema. Validation errors:\n{exc}"
            )

    message = "Structured output validation failed"
    if last_validation_error is not None:
        message = f"{message}: {last_validation_error}"
    raise LLMValidationError(message)


def generate_structured(
    prompt: str,
    schema: type[T],
    *,
    system: str | None = None,
    validation_max_attempts: int = 2,
) -> T:
    return generate_structured_result(
        prompt,
        schema,
        system=system,
        validation_max_attempts=validation_max_attempts,
    ).data

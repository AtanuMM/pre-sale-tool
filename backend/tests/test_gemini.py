from unittest.mock import MagicMock, patch

import pytest
from google.genai.errors import ClientError
from pydantic import BaseModel

from app.llm import gemini
from app.llm.gemini import (
    LLMError,
    LLMRateLimitError,
    LLMValidationError,
    generate_structured,
    reset_client_for_tests,
)


class SampleSchema(BaseModel):
    answer: str


def _mock_response(text: str, prompt_tokens: int = 10, candidate_tokens: int = 5):
    response = MagicMock()
    response.text = text
    usage = MagicMock()
    usage.prompt_token_count = prompt_tokens
    usage.candidates_token_count = candidate_tokens
    response.usage_metadata = usage
    return response


@pytest.fixture(autouse=True)
def _clear_client_cache() -> None:
    reset_client_for_tests()
    gemini._client = None
    yield
    reset_client_for_tests()
    gemini._client = None


@pytest.fixture
def mock_generate_content():
    with patch.object(gemini, "_get_client") as get_client:
        client = MagicMock()
        get_client.return_value = client
        yield client.models.generate_content


def test_success_path(mock_generate_content: MagicMock) -> None:
    mock_generate_content.return_value = _mock_response('{"answer": "ok"}')

    with patch("app.llm.gemini.get_settings") as settings:
        settings.return_value.GEMINI_MODEL = "test-model"
        result = generate_structured("prompt", SampleSchema)

    assert result.answer == "ok"
    assert mock_generate_content.call_count == 1


def test_429_then_success(mock_generate_content: MagicMock) -> None:
    mock_generate_content.side_effect = [
        ClientError(429, {"error": {"message": "rate limit"}}),
        _mock_response('{"answer": "ok"}'),
    ]

    with (
        patch("app.llm.gemini.get_settings") as settings,
        patch("app.llm.gemini.time.sleep") as sleep,
    ):
        settings.return_value.GEMINI_MODEL = "test-model"
        result = generate_structured("prompt", SampleSchema)

    assert result.answer == "ok"
    assert mock_generate_content.call_count == 2
    sleep.assert_called_once()


def test_repeated_429_raises_rate_limit_error(mock_generate_content: MagicMock) -> None:
    mock_generate_content.side_effect = ClientError(
        429, {"error": {"message": "rate limit"}}
    )

    with (
        patch("app.llm.gemini.get_settings") as settings,
        patch("app.llm.gemini.time.sleep"),
        pytest.raises(LLMRateLimitError),
    ):
        settings.return_value.GEMINI_MODEL = "test-model"
        generate_structured("prompt", SampleSchema)

    assert mock_generate_content.call_count == gemini.MAX_API_ATTEMPTS


def test_validation_failure_then_success(mock_generate_content: MagicMock) -> None:
    mock_generate_content.side_effect = [
        _mock_response('{"answer": 123}'),
        _mock_response('{"answer": "fixed"}'),
    ]

    with patch("app.llm.gemini.get_settings") as settings:
        settings.return_value.GEMINI_MODEL = "test-model"
        result = generate_structured("prompt", SampleSchema)

    assert result.answer == "fixed"
    assert mock_generate_content.call_count == 2


def test_validation_failure_exhausted(mock_generate_content: MagicMock) -> None:
    mock_generate_content.return_value = _mock_response('{"answer": 123}')

    with (
        patch("app.llm.gemini.get_settings") as settings,
        pytest.raises(LLMValidationError),
    ):
        settings.return_value.GEMINI_MODEL = "test-model"
        generate_structured("prompt", SampleSchema, validation_max_attempts=2)

    assert mock_generate_content.call_count == 2


def test_non_retryable_client_error(mock_generate_content: MagicMock) -> None:
    mock_generate_content.side_effect = ClientError(
        400, {"error": {"message": "bad request"}}
    )

    with (
        patch("app.llm.gemini.get_settings") as settings,
        patch("app.llm.gemini.time.sleep") as sleep,
        pytest.raises(LLMError),
    ):
        settings.return_value.GEMINI_MODEL = "test-model"
        generate_structured("prompt", SampleSchema)

    assert mock_generate_content.call_count == 1
    sleep.assert_not_called()

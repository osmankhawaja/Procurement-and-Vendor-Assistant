import os

import pytest

from app.config import Settings, configure_langsmith


def test_current_gemini_models_are_default() -> None:
    settings = Settings(_env_file=None)

    assert settings.primary_model == "gemini-3.8-flash"
    assert settings.fallback_model == "gemini-3.5-flash-lite"


def test_cors_origins_accept_comma_separated_environment_value() -> None:
    settings = Settings(
        _env_file=None,
        CORS_ORIGINS="http://localhost:5173, http://127.0.0.1:5173",
    )

    assert settings.cors_origins == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


def test_langsmith_modern_environment_names(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "LANGSMITH_API_KEY",
        "LANGCHAIN_API_KEY",
        "LANGSMITH_TRACING",
        "LANGCHAIN_TRACING_V2",
        "LANGSMITH_ENDPOINT",
        "LANGCHAIN_ENDPOINT",
        "LANGSMITH_PROJECT",
        "LANGCHAIN_PROJECT",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = Settings(
        _env_file=None,
        LANGSMITH_API_KEY="test-key",
        LANGSMITH_TRACING=True,
        LANGSMITH_ENDPOINT="https://example.test",
        LANGSMITH_PROJECT="test-project",
    )

    assert configure_langsmith(settings) is True
    assert os.environ["LANGSMITH_TRACING"] == "true"
    assert os.environ["LANGSMITH_PROJECT"] == "test-project"
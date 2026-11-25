"""Model construction and primary/fallback routing for chat workloads."""

from typing import Any, TypeVar

from langchain_core.runnables import Runnable
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel

from app.config import get_settings


OutputModel = TypeVar("OutputModel", bound=BaseModel)

_MODEL_REQUEST_TIMEOUT_SECONDS = 20
_MODEL_MAX_RETRIES = 0


def _resolve_api_key(raw_key: Any) -> str:
    if raw_key is None:
        return ""
    if hasattr(raw_key, "get_secret_value") and callable(raw_key.get_secret_value):
        value = raw_key.get_secret_value()
    else:
        value = str(raw_key)
    return value.strip()


def _effective_temperature(model_name: str, temperature: float) -> float:
    normalized_name = model_name.removeprefix("models/").strip().lower()
    if normalized_name.startswith(("gemini-3", "gemini-4")):
        return 1.0
    return temperature


def _create_model(
    model_name: str,
    *,
    api_key: str,
    temperature: float,
    output_schema: type[BaseModel] | None,
) -> Runnable:
    model = ChatGoogleGenerativeAI(
        model=model_name,
        google_api_key=api_key,
        temperature=_effective_temperature(model_name, temperature),
        timeout=_MODEL_REQUEST_TIMEOUT_SECONDS,
        max_retries=_MODEL_MAX_RETRIES,
    )
    if output_schema is not None:
        return model.with_structured_output(output_schema)
    return model


def _get_model(
    *,
    temperature: float,
    output_schema: type[BaseModel] | None,
) -> Runnable:
    settings = get_settings()
    api_key = _resolve_api_key(getattr(settings, "google_api_key", None))
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY is required to use the Gemini models.")

    raw_candidates = (
        getattr(settings, "primary_model", None),
        getattr(settings, "fallback_model", None),
    )
    model_names = tuple(
        dict.fromkeys(
            name.strip()
            for name in raw_candidates
            if isinstance(name, str) and name.strip()
        )
    )
    if not model_names:
        raise ValueError("At least one Gemini model name must be configured.")

    models = [
        _create_model(
            model_name,
            api_key=api_key,
            temperature=temperature,
            output_schema=output_schema,
        )
        for model_name in model_names
    ]
    if len(models) == 1:
        return models[0]
    return models[0].with_fallbacks(models[1:])


def get_chat_model(*, temperature: float = 0.0) -> Runnable:
    """Create the configured Gemini chat model with fallback routing."""
    return _get_model(temperature=temperature, output_schema=None)


def get_structured_chat_model(
    output_schema: type[OutputModel],
    *,
    temperature: float = 0.0,
) -> Runnable:
    """Create a Gemini chat model that returns validated structured output."""
    return _get_model(temperature=temperature, output_schema=output_schema)
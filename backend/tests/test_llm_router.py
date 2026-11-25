from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from app.llm import get_chat_model, get_structured_chat_model
from app.llm import router as llm_router


class OutputSchema(BaseModel):
    answer: str


class FakeRunnable:
    def __init__(self, model: object, schema: type[BaseModel] | None = None) -> None:
        self.model = model
        self.schema = schema
        self.fallbacks: list[FakeRunnable] = []

    def with_fallbacks(self, fallbacks: list[FakeRunnable]) -> FakeRunnable:
        self.fallbacks = fallbacks
        return self


class FakeChatModel:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs

    def with_structured_output(self, schema: type[BaseModel]) -> FakeRunnable:
        return FakeRunnable(self, schema)


@pytest.fixture
def capture_chat_models(monkeypatch: pytest.MonkeyPatch) -> list[FakeChatModel]:
    instances: list[FakeChatModel] = []

    def _factory(**kwargs: object) -> FakeChatModel:
        model = FakeChatModel(**kwargs)
        instances.append(model)
        return model

    monkeypatch.setattr(llm_router, "ChatGoogleGenerativeAI", _factory)
    return instances


def test_structured_model_uses_primary_and_fallback(
    monkeypatch: pytest.MonkeyPatch,
    capture_chat_models: list[FakeChatModel],
) -> None:
    monkeypatch.setattr(
        llm_router,
        "get_settings",
        lambda: SimpleNamespace(
            google_api_key="test-key",
            primary_model="gemini-primary",
            fallback_model="gemini-fallback",
        ),
    )

    model = get_structured_chat_model(OutputSchema)

    assert isinstance(model, FakeRunnable)
    assert model.schema is OutputSchema
    assert len(capture_chat_models) == 2
    assert capture_chat_models[0].kwargs["model"] == "gemini-primary"
    assert capture_chat_models[0].kwargs["timeout"] == 20
    assert capture_chat_models[0].kwargs["max_retries"] == 0
    assert len(model.fallbacks) == 1
    assert model.fallbacks[0].schema is OutputSchema
    assert capture_chat_models[1].kwargs["model"] == "gemini-fallback"
    assert capture_chat_models[1].kwargs["timeout"] == 20
    assert capture_chat_models[1].kwargs["max_retries"] == 0


@pytest.mark.parametrize(
    "model_name",
    ["gemini-3.8-flash", "models/gemini-3.5-flash-lite"],
)
def test_gemini_3_models_use_recommended_temperature(
    monkeypatch: pytest.MonkeyPatch,
    capture_chat_models: list[FakeChatModel],
    model_name: str,
) -> None:
    monkeypatch.setattr(
        llm_router,
        "get_settings",
        lambda: SimpleNamespace(
            google_api_key="test-key",
            primary_model=model_name,
            fallback_model="",
        ),
    )

    get_chat_model()

    assert len(capture_chat_models) == 1
    assert capture_chat_models[0].kwargs["temperature"] == 1.0


def test_chat_model_requires_google_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        llm_router,
        "get_settings",
        lambda: SimpleNamespace(
            google_api_key="",
            primary_model="gemini-primary",
            fallback_model="gemini-fallback",
        ),
    )

    with pytest.raises(RuntimeError, match="GOOGLE_API_KEY"):
        get_chat_model()
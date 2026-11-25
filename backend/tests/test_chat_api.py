import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import chat as chat_api
from app.api.chat import router


class SlowGraph:
    async def ainvoke(self, input: object, config: dict[str, object]) -> object:
        await asyncio.sleep(0.2)
        return {"response": "This should not be reached."}


def test_chat_times_out_when_workflow_does_not_respond(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_api, "_WORKFLOW_TIMEOUT_SECONDS", 0.01)
    app = FastAPI()
    app.include_router(router)
    app.state.procurement_graph = SlowGraph()

    with TestClient(app) as client:
        response = client.post("/chat", json={"message": "Find a vendor"})

    assert response.status_code == 504
    assert response.json()["detail"] == (
        "The procurement workflow timed out. Please try again."
    )
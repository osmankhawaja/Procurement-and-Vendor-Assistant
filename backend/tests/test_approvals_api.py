from types import SimpleNamespace
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.approvals import router


class FakeCheckpointer:
    async def alist(self, config: object, *, limit: int | None = None) -> object:
        raise NotImplementedError


class FakeGraph:
    checkpointer = FakeCheckpointer()

    def __init__(self) -> None:
        self.resume_value: dict[str, Any] | None = None

    async def aget_state(self, config: dict[str, object]) -> SimpleNamespace:
        return SimpleNamespace(
            values={"status": "AWAITING_APPROVAL"},
            next=("hitl_gate",),
            tasks=(),
            created_at=None,
        )

    async def ainvoke(
        self,
        command: Any,
        config: dict[str, object],
    ) -> dict[str, Any]:
        resume_payload = getattr(command, "resume", None)
        assert isinstance(resume_payload, dict)
        self.resume_value = resume_payload
        return {"approval_decision": resume_payload.get("decision")}


def test_approval_route_maps_api_action_to_hitl_resume_contract() -> None:
    app = FastAPI()
    app.include_router(router)
    graph = FakeGraph()
    app.state.procurement_graph = graph

    with TestClient(app) as client:
        response = client.post(
            "/approvals/thread-1",
            json={
                "decision": "approve",
                "comment": "  Reviewed  ",
                "approver_id": " manager-1 ",
            },
        )

    assert response.status_code == 200, response.text
    assert graph.resume_value == {
        "decision": "approved",
        "notes": "Reviewed",
        "approver_id": "manager-1",
    }
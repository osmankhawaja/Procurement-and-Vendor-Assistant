from types import SimpleNamespace

import pytest
from langchain_core.messages import HumanMessage

from app.graph.nodes import procurement_agent


class FakeModel:
    def __init__(self, response: procurement_agent.ProcurementAgentResponse) -> None:
        self.response = response

    async def ainvoke(
        self, messages: list[object]
    ) -> procurement_agent.ProcurementAgentResponse:
        assert messages[0].type == "system"
        return self.response


async def _empty_policy_result(query: str) -> SimpleNamespace:
    return SimpleNamespace(context="", citations=[])


async def _lookup_context(
    query: str,
    *,
    cost_center_id: str | None = None,
) -> dict[str, object]:
    return {
        **_catalog_context(),
        "approved_vendors": [],
        "budget": None,
    }


def _catalog_context() -> dict[str, object]:
    return {
        "catalog_items": [
            {
                "approved": True,
                "product_id": "laptop-01",
                "item_name": "Business Laptop",
                "vendor_id": "vendor-01",
                "vendor_name": "Approved Computers",
                "unit_price": 400.0,
                "currency": "USD",
            }
        ]
    }


def _state() -> dict[str, object]:
    return {
        "messages": [HumanMessage(content="Draft an order for two business laptops.")],
        "procurement_context": _catalog_context(),
        "citations": [],
        "default_cost_center": "CC-IT-01",
    }


def _patch_agent_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    model_response: procurement_agent.ProcurementAgentResponse,
) -> None:
    monkeypatch.setattr(
        procurement_agent, "_build_model", lambda: FakeModel(model_response)
    )
    monkeypatch.setattr(
        procurement_agent, "retrieve_policy_context", _empty_policy_result
    )
    monkeypatch.setattr(
        procurement_agent, "lookup_procurement_context", _lookup_context
    )
    monkeypatch.setattr(
        procurement_agent,
        "get_settings",
        lambda: SimpleNamespace(hitl_approval_threshold=500),
    )


@pytest.mark.asyncio
async def test_procurement_agent_builds_grounded_order_and_flags_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    draft = procurement_agent.PurchaseOrderDraft(
        items=[
            procurement_agent.PurchaseOrderItem(
                product_id="laptop-01",
                item_name="Business Laptop",
                vendor_id="vendor-01",
                vendor_name="Approved Computers",
                quantity=2,
                unit_price=400,
                currency="USD",
            )
        ]
    )
    model_response = procurement_agent.ProcurementAgentResponse(
        response="I prepared the purchase-order draft.",
        draft_po=draft,
    )
    _patch_agent_dependencies(monkeypatch, model_response)

    result = await procurement_agent.procurement_agent_node(_state())

    assert result["draft_po"]["total_amount"] == 800
    assert result["draft_po"]["cost_center_id"] == "CC-IT-01"
    assert result["requires_approval"] is True
    assert result["status"] == "AWAITING_APPROVAL"


@pytest.mark.asyncio
async def test_procurement_agent_rejects_order_not_in_approved_catalog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    draft = procurement_agent.PurchaseOrderDraft(
        items=[
            procurement_agent.PurchaseOrderItem(
                product_id="unlisted-item",
                item_name="Business Laptop",
                vendor_id="vendor-01",
                vendor_name="Approved Computers",
                quantity=1,
                unit_price=400,
                currency="USD",
            )
        ]
    )
    model_response = procurement_agent.ProcurementAgentResponse(
        response="I prepared the purchase-order draft.",
        draft_po=draft,
    )
    _patch_agent_dependencies(monkeypatch, model_response)

    result = await procurement_agent.procurement_agent_node(_state())

    assert result["draft_po"] is None
    assert "verified against the approved procurement catalog" in result["messages"][0].content
    assert result["requires_approval"] is False
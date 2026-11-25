import sqlite3
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from app.graph import workflow
from app.graph.nodes import hitl_gate
from app.graph.state import ProcurementGraphState


def _fetch_po_row(database_path: Path, po_id: str, query: str) -> tuple[Any, ...] | None:
    with closing(sqlite3.connect(database_path)) as connection:
        return connection.execute(query, (po_id,)).fetchone()


@pytest.mark.parametrize(
    ("draft_po", "expected_route"),
    [
        (None, "output_guardrail"),
        ({"total_amount": 500.0}, "output_guardrail"),
        ({"total_amount": 500.01}, "hitl_gate"),
    ],
)
def test_route_after_agent_uses_configured_threshold(
    monkeypatch: pytest.MonkeyPatch,
    draft_po: dict[str, Any] | None,
    expected_route: str,
) -> None:
    monkeypatch.setattr(
        workflow,
        "settings",
        SimpleNamespace(hitl_approval_threshold=500.0),
    )

    assert workflow.route_after_agent({"draft_po": draft_po}) == expected_route


@pytest.mark.parametrize(
    ("decision", "expected_route"),
    [
        ("approved", "output_guardrail"),
        ("APPROVED", "output_guardrail"),
        ("rejected", "procurement_agent"),
        (None, "procurement_agent"),
    ],
)
def test_route_after_hitl_gate_uses_approval_decision(
    decision: str | None,
    expected_route: str,
) -> None:
    assert workflow.route_after_hitl_gate({"approval_decision": decision}) == expected_route


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("decision", "expected_status"),
    [
        ("approved", "APPROVED"),
        ("rejected", "REJECTED"),
    ],
)
async def test_hitl_gate_persists_pending_po_and_resumes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    decision: str,
    expected_status: str,
) -> None:
    database_path = tmp_path / "erp.sqlite"
    monkeypatch.setattr(
        hitl_gate,
        "settings",
        SimpleNamespace(
            erp_db_path=lambda: database_path,
            hitl_approval_threshold=500.0,
        ),
    )
    graph_builder = StateGraph(ProcurementGraphState)
    graph_builder.add_node("approval", hitl_gate.hitl_gate_node)
    graph_builder.add_edge(START, "approval")
    graph_builder.add_edge("approval", END)
    graph = graph_builder.compile(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": f"thread-{decision}"}}
    po_id = f"PO-{decision.upper()}"
    initial_state: ProcurementGraphState = {
        "thread_id": f"thread-{decision}",
        "user_name": "Test Requester",
        "draft_po": {
            "po_id": po_id,
            "department": "Engineering",
            "cost_center_id": "CC-ENG-402",
            "total_amount": 750.0,
            "items": [{"product_id": "ITEM-1", "quantity": 1}],
        },
        "citations": [],
    }

    interrupted = await graph.ainvoke(initial_state, config)

    assert len(interrupted["__interrupt__"]) == 1
    interrupt_value = interrupted["__interrupt__"][0].value
    assert interrupt_value["event"] == "HITL_APPROVAL_REQUIRED"
    assert interrupt_value["po_id"] == po_id
    assert interrupt_value["threshold_usd"] == 500.0

    pending = _fetch_po_row(
        database_path,
        po_id,
        "SELECT status, total_amount FROM purchase_orders WHERE po_id = ?",
    )
    assert pending == ("PENDING_APPROVAL", 750.0)

    resumed = await graph.ainvoke(
        Command(
            resume={
                "decision": decision,
                "approver_id": "MGR-1",
                "approver_name": "Department Manager",
                "notes": "Reviewed for the test.",
            }
        ),
        config,
    )

    assert resumed["approval_decision"] == decision
    assert resumed["draft_po"]["status"] == expected_status
    assert resumed["approver_id"] == "MGR-1"
    assert resumed["approver_name"] == "Department Manager"
    assert resumed["manager_notes"] == "Reviewed for the test."
    assert resumed["status"] == expected_status

    if decision == "rejected":
        rejected = _fetch_po_row(
            database_path,
            po_id,
            "SELECT status, approver_id FROM purchase_orders WHERE po_id = ?",
        )
        assert rejected == ("REJECTED", "MGR-1")
import asyncio
import math
from typing import Any, Literal, Optional

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph

from app.config import get_settings
from app.graph.nodes.hitl_gate import hitl_gate_node
from app.graph.nodes.input_guardrail import input_guardrail_node
from app.graph.nodes.output_guardrail import output_guardrail_node
from app.graph.nodes.procurement_agent import procurement_agent_node
from app.graph.state import ProcurementGraphState

settings = get_settings()

# Singleton compiled graph instance, checkpointer context, and bound event loop
_compiled_graph: Any = None
_checkpointer_cm: Any = None
_checkpointer_loop: Optional[asyncio.AbstractEventLoop] = None
_graph_lock: Optional[asyncio.Lock] = None
_lock_loop: Optional[asyncio.AbstractEventLoop] = None


def _get_lock() -> asyncio.Lock:
    global _graph_lock, _lock_loop
    loop = asyncio.get_running_loop()
    if _graph_lock is None or _lock_loop is not loop:
        _graph_lock = asyncio.Lock()
        _lock_loop = loop
    return _graph_lock


def _safe_total_amount(draft_po: Any) -> float:
    if not isinstance(draft_po, dict):
        return 0.0
    raw_amount = draft_po.get("total_amount", 0.0)
    if raw_amount is None:
        return 0.0
    try:
        amount = float(raw_amount)
    except (TypeError, ValueError):
        return 0.0
    return amount if math.isfinite(amount) else 0.0


# ==============================================================================
# CONDITIONAL ROUTING FUNCTIONS
# ==============================================================================


def route_after_input_guardrail(
    state: ProcurementGraphState,
) -> Literal["procurement_agent", "__end__"]:
    """
    If the input guardrail detected a prompt injection, out-of-scope query,
    or blacklisted vendor, short-circuit immediately to END.
    """
    if state.get("blocked", False):
        return END
    return "procurement_agent"


def route_after_agent(
    state: ProcurementGraphState,
) -> Literal["hitl_gate", "output_guardrail"]:
    """
    Checks whether a draft Purchase Requisition exists and exceeds the
    configured automated approval threshold.
    - Above threshold -> Route to `hitl_gate` (pauses via interrupt() for approval)
    - At/below threshold or no draft -> Route to `output_guardrail`
    """
    active_settings = getattr(get_settings, "__wrapped__", None) and get_settings() or settings
    threshold = getattr(active_settings, "hitl_approval_threshold", 500.0)

    draft_po = state.get("draft_po")
    total_amount = _safe_total_amount(draft_po)

    if isinstance(draft_po, dict) and draft_po and total_amount > threshold:
        return "hitl_gate"

    return "output_guardrail"


def route_after_hitl_gate(
    state: ProcurementGraphState,
) -> Literal["output_guardrail", "procurement_agent"]:
    """
    Handles the manager's HITL decision.
    - 'approved' -> Proceed to `output_guardrail` to scrub PII and commit final PO.
    - 'rejected' -> Route back to `procurement_agent` with rejection context.
    """
    decision = str(state.get("approval_decision") or "").strip().lower()
    if decision in {"approved", "approve"}:
        return "output_guardrail"
    return "procurement_agent"


# ==============================================================================
# GRAPH BUILDER & CHECKPOINTER INITIALIZATION
# ==============================================================================


def build_procurement_state_graph() -> StateGraph:
    """Constructs the LangGraph StateGraph topology."""
    workflow = StateGraph(ProcurementGraphState)

    workflow.add_node("input_guardrail", input_guardrail_node)
    workflow.add_node("procurement_agent", procurement_agent_node)
    workflow.add_node("hitl_gate", hitl_gate_node)
    workflow.add_node("output_guardrail", output_guardrail_node)

    workflow.add_edge(START, "input_guardrail")

    workflow.add_conditional_edges(
        "input_guardrail",
        route_after_input_guardrail,
        {
            "procurement_agent": "procurement_agent",
            END: END,
        },
    )

    workflow.add_conditional_edges(
        "procurement_agent",
        route_after_agent,
        {
            "hitl_gate": "hitl_gate",
            "output_guardrail": "output_guardrail",
        },
    )

    workflow.add_conditional_edges(
        "hitl_gate",
        route_after_hitl_gate,
        {
            "output_guardrail": "output_guardrail",
            "procurement_agent": "procurement_agent",
        },
    )

    workflow.add_edge("output_guardrail", END)

    return workflow


async def get_compiled_graph():
    """
    Returns a compiled LangGraph instance backed by AsyncSqliteSaver
    for multi-turn conversation memory and HITL interrupt persistence.
    """
    global _compiled_graph, _checkpointer_cm, _checkpointer_loop

    loop = asyncio.get_running_loop()
    if (
        _compiled_graph is not None
        and _checkpointer_loop is loop
        and not loop.is_closed()
    ):
        return _compiled_graph

    async with _get_lock():
        loop = asyncio.get_running_loop()
        if (
            _compiled_graph is not None
            and _checkpointer_loop is loop
            and not loop.is_closed()
        ):
            return _compiled_graph

        # If a prior graph/checkpointer was created on another loop or stale state, reset cleanly
        if _checkpointer_cm is not None:
            try:
                await _checkpointer_cm.__aexit__(None, None, None)
            except Exception:
                pass
            _checkpointer_cm = None
            _compiled_graph = None
            _checkpointer_loop = None

        active_settings = settings
        try:
            active_settings = get_settings()
        except Exception:
            pass

        db_path = active_settings.checkpoint_db_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)

        cm = AsyncSqliteSaver.from_conn_string(str(db_path))
        try:
            checkpointer = await cm.__aenter__()
            await checkpointer.setup()

            state_graph = build_procurement_state_graph()
            compiled = state_graph.compile(checkpointer=checkpointer)

            _checkpointer_cm = cm
            _compiled_graph = compiled
            _checkpointer_loop = loop
            return _compiled_graph
        except Exception:
            try:
                await cm.__aexit__(None, None, None)
            except Exception:
                pass
            raise


async def close_compiled_graph() -> None:
    """Close the checkpoint checkpointer and allow the graph to be rebuilt."""
    global _compiled_graph, _checkpointer_cm, _checkpointer_loop

    async with _get_lock():
        cm = _checkpointer_cm
        _checkpointer_cm = None
        _compiled_graph = None
        _checkpointer_loop = None
        if cm is not None:
            try:
                await cm.__aexit__(None, None, None)
            except Exception:
                pass
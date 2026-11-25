import operator
from typing import Annotated, Any, Dict, List, Optional
from typing_extensions import TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class ProcurementGraphState(TypedDict, total=False):
    """
    Shared state schema passed between all nodes in the LangGraph procurement pipeline.
    Persisted across conversational turns and HITL interrupts via AsyncSqliteSaver.
    """

    # 1. Conversation History (Multi-Turn Memory)
    # `add_messages` automatically appends new HumanMessage / AIMessage / ToolMessage objects.
    messages: Annotated[List[BaseMessage], add_messages]

    # 2. Session & User Metadata
    thread_id: str
    user_id: str
    user_name: str
    default_cost_center: Optional[str]

    # 3. Safety & Guardrail Flags
    blocked: bool
    block_reason: Optional[str]

    # 4. Structured Purchase Requisition & Citations
    draft_po: Optional[Dict[str, Any]]
    final_po_id: Optional[str]
    citations: List[Dict[str, Any]]
    procurement_context: Dict[str, Any]

    # 5. Human-in-the-Loop (HITL) Approval State
    requires_approval: bool
    approval_decision: Optional[str]  # "approved" | "rejected" | None
    approver_id: Optional[str]
    approver_name: Optional[str]
    manager_notes: Optional[str]

    # 6. Graph Execution Tracking
    # Tracks workflow status: "RUNNING" | "BLOCKED" | "AWAITING_APPROVAL" | "COMPLETED" | "REJECTED"
    status: str
    visited_nodes: Annotated[List[str], operator.add]
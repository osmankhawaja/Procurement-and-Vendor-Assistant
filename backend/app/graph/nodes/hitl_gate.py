from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Dict

from app.config import get_settings
from app.graph.state import ProcurementGraphState
from langchain_core.messages import SystemMessage
from langgraph.types import interrupt


def _connect_erp_db() -> sqlite3.Connection:
  db_path = Path(get_settings().erp_db_path())
  db_path.parent.mkdir(parents=True, exist_ok=True)
  return sqlite3.connect(str(db_path))


def _default_po_id(thread_id: str) -> str:
  digest = hashlib.sha256(thread_id.encode("utf-8")).hexdigest()
  return f"PO-2026-{int(digest[:8], 16) % 900 + 100}"


def _upsert_pending_po_in_erp(
    state: ProcurementGraphState,
    requisition: Dict[str, Any],
) -> str:
  """
    Ensures the requisition is persisted in the SQLite ERP `purchase_orders`
    table with status='PENDING_APPROVAL' so the React Manager Dashboard can display it.
    """
  thread_id = str(state.get("thread_id") or "unknown-thread")
  po_id = str(requisition.get("po_id") or _default_po_id(thread_id))

  conn = _connect_erp_db()
  try:
    cursor = conn.cursor()
    cursor.execute(
        """
            CREATE TABLE IF NOT EXISTS purchase_orders (
                po_id TEXT PRIMARY KEY,
                thread_id TEXT,
                requester_name TEXT,
                department TEXT,
                cost_center_id TEXT,
                total_amount REAL,
                items_json TEXT,
                citations_json TEXT,
                status TEXT,
                approver_id TEXT,
                created_at TEXT,
                updated_at TEXT
            )
            """
    )

    now_iso = datetime.now(timezone.utc).isoformat()
    cursor.execute(
        """
            INSERT INTO purchase_orders (
                po_id, thread_id, requester_name, department, cost_center_id,
                total_amount, items_json, citations_json, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PENDING_APPROVAL', ?, ?)
            ON CONFLICT(po_id) DO UPDATE SET
                total_amount = excluded.total_amount,
                items_json = excluded.items_json,
                citations_json = excluded.citations_json,
                status = 'PENDING_APPROVAL',
                updated_at = excluded.updated_at
            """,
        (
            po_id,
            thread_id,
            state.get("user_name", "Engineering Lead"),
            requisition.get("department", "Engineering"),
            requisition.get("cost_center_id", "CC-ENG-402"),
            float(requisition.get("total_amount", 0.0)),
            json.dumps(requisition.get("items", [])),
            json.dumps(state.get("citations", [])),
            now_iso,
            now_iso,
        ),
    )
    conn.commit()
    return po_id
  finally:
    conn.close()


def _mark_po_rejected_in_erp(po_id: str, approver_id: str) -> None:
  """Updates the ERP record to REJECTED if the manager declines the requisition."""
  conn = _connect_erp_db()
  try:
    cursor = conn.cursor()
    cursor.execute(
        """
            UPDATE purchase_orders
            SET status = 'REJECTED',
                approver_id = ?,
                updated_at = ?
            WHERE po_id = ?
            """,
        (approver_id, datetime.now(timezone.utc).isoformat(), po_id),
    )
    conn.commit()
  finally:
    conn.close()


async def hitl_gate_node(state: ProcurementGraphState) -> Dict[str, Any]:
  """
    Human-in-the-Loop (HITL) Approval Gate.
    Triggered whenever `total_amount > threshold`.

    1. Writes/updates the `PENDING_APPROVAL` requisition in SQLite for the UI.
    2. Invokes LangGraph `interrupt()` to halt execution until `Command(resume=...)` is sent
       from `POST /approvals/{thread_id}` without creating a `DRAFT` PO beforehand.
    3. Only creates `draft_po` when approved, or routes back with `draft_po=None` if rejected.
    """
  threshold = float(get_settings().hitl_approval_threshold)
  requisition: Dict[str, Any] = dict(
      state.get("pending_approval_request") or state.get("draft_po") or {}
  )
  po_id = _upsert_pending_po_in_erp(state, requisition)
  requisition["po_id"] = po_id
  requisition["status"] = "PENDING_APPROVAL"

  raw_response: Any = interrupt({
      "event": "HITL_APPROVAL_REQUIRED",
      "po_id": po_id,
      "thread_id": state.get("thread_id"),
      "requester_name": state.get("user_name", "Engineering Lead"),
      "cost_center_id": requisition.get("cost_center_id", "CC-ENG-402"),
      "total_amount": requisition.get("total_amount", 0.0),
      "threshold_usd": threshold,
      "items": requisition.get("items", []),
      "citations": state.get("citations", []),
      "message": (
          f"Requisition {po_id}"
          f" (${float(requisition.get('total_amount', 0)):,.2f}) exceeds the"
          f" ${threshold:,.2f} automated threshold and requires Department"
          " Manager sign-off before a purchase draft can be created."
      ),
  })

  if isinstance(raw_response, dict):
    manager_response = raw_response
  elif isinstance(raw_response, str):
    manager_response = {"decision": raw_response}
  else:
    manager_response = {}

  decision = str(manager_response.get("decision") or "rejected").strip().lower()
  approver_id = str(manager_response.get("approver_id") or "MGR-TANVIR-01")
  approver_name = str(manager_response.get("approver_name") or "Tanvir Ahmed")
  notes = str(manager_response.get("notes") or "").strip()

  if decision in {"approved", "approve"}:
    approved_draft: Dict[str, Any] = {
        **requisition,
        "po_id": po_id,
        "status": "DRAFT",
        "approved_by": approver_id,
        "approver_name": approver_name,
    }
    return {
        "draft_po": approved_draft,
        "pending_approval_request": None,
        "requires_approval": False,
        "approval_decision": "approved",
        "approver_id": approver_id,
        "approver_name": approver_name,
        "manager_notes": notes,
        "status": "APPROVED",
        "visited_nodes": ["hitl_gate"],
    }

  _mark_po_rejected_in_erp(po_id, approver_id)

  rejection_context = (
      "[HITL MANAGER DECISION: REJECTED] Department Manager"
      f" {approver_name} ({approver_id}) rejected Purchase Requisition"
      f" {po_id} (${float(requisition.get('total_amount', 0)):,.2f}). Manager"
      f" Notes: '{notes or 'No specific notes provided.'}'. No purchase draft"
      " was created. Inform the user politely about the rejection, include the"
      " manager's notes, and ask if they would like to modify the"
      " quantities/specifications or cancel the request."
  )

  return {
      "draft_po": None,
      "pending_approval_request": None,
      "requires_approval": False,
      "approval_decision": "rejected",
      "approver_id": approver_id,
      "approver_name": approver_name,
      "manager_notes": notes,
      "status": "REJECTED",
      "messages": [SystemMessage(content=rejection_context)],
      "visited_nodes": ["hitl_gate"],
  }
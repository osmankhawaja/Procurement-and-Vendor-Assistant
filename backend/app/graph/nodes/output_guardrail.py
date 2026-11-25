import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.messages import AIMessage

from app.config import get_settings
from app.graph.state import ProcurementGraphState

settings = get_settings()

# ==============================================================================
# OUTPUT PII & FINANCIAL IDENTIFIER REDACTION RULES
# ==============================================================================

REDACTION_PATTERNS: List[Tuple[str, str]] = [
    # Corporate EIN / Tax IDs (e.g., 12-3456789)
    (r"\b\d{2}-\d{7}\b", "[REDACTED-CORPORATE-EIN]"),
    # International Bank Account Numbers (IBAN)
    (r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b", "[REDACTED-VENDOR-IBAN]"),
    # Bank Routing / SWIFT / Account references
    (
        r"(?i)(routing|account|swift)\s*(number|no|#|:)?\s*[:#]?\s*\d{6,17}",
        "[REDACTED-BANK-DETAIL]",
    ),
    # SSNs
    (r"\b\d{3}-\d{2}-\d{4}\b", "[REDACTED-SSN]"),
    # API Keys / Bearer Tokens
    (r"\b(AIza[0-9A-Za-z\-_]{35}|sk-[a-zA-Z0-9]{20,})\b", "[REDACTED-API-KEY]"),
]


def _connect_erp_db() -> sqlite3.Connection:
    db_path = Path(settings.erp_db_path())
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(str(db_path))


def _default_po_id(thread_id: str) -> str:
    digest = hashlib.sha256(thread_id.encode("utf-8")).hexdigest()
    return f"PO-2026-{int(digest[:8], 16) % 900 + 100}"


def _redact_sensitive_text(text: str) -> str:
    """Scrubs sensitive tax, banking, and credential strings from outputs."""
    scrubbed = text
    for pattern, replacement in REDACTION_PATTERNS:
        scrubbed = re.sub(pattern, replacement, scrubbed)
    return scrubbed


def _commit_final_po_to_erp(
    state: ProcurementGraphState,
    draft_po: Dict[str, Any],
) -> Optional[str]:
    """
    Commits an approved (or auto-approved) Purchase Order to the SQLite ERP
    `purchase_orders` ledger and deducts the total from `department_budgets`.
    """
    total_amount = float(draft_po.get("total_amount", 0.0))
    items = draft_po.get("items", [])

    if not items or total_amount <= 0:
        return None

    thread_id = str(state.get("thread_id") or "unknown-thread")
    po_id = str(draft_po.get("po_id") or _default_po_id(thread_id))
    cost_center_id = draft_po.get("cost_center_id", "CC-ENG-402")
    approver_id = state.get("approver_id") or "AUTO-POLICY"
    now_iso = datetime.now(timezone.utc).isoformat()

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

        cursor.execute(
            "SELECT status FROM purchase_orders WHERE po_id = ?",
            (po_id,),
        )
        existing = cursor.fetchone()
        already_committed = existing is not None and existing[0] == "COMMITTED"

        cursor.execute(
            """
            INSERT INTO purchase_orders (
                po_id, thread_id, requester_name, department, cost_center_id,
                total_amount, items_json, citations_json, status, approver_id,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'COMMITTED', ?, ?, ?)
            ON CONFLICT(po_id) DO UPDATE SET
                total_amount = excluded.total_amount,
                items_json = excluded.items_json,
                citations_json = excluded.citations_json,
                status = 'COMMITTED',
                approver_id = excluded.approver_id,
                updated_at = excluded.updated_at
            """,
            (
                po_id,
                thread_id,
                state.get("user_name", "Engineering Lead"),
                draft_po.get("department", "Engineering"),
                cost_center_id,
                total_amount,
                json.dumps(items),
                json.dumps(state.get("citations", [])),
                approver_id,
                now_iso,
                now_iso,
            ),
        )

        if not already_committed:
            cursor.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='department_budgets'
                """
            )
            if cursor.fetchone():
                cursor.execute(
                    """
                    UPDATE department_budgets
                    SET remaining_budget = MAX(0, remaining_budget - ?),
                        spent_budget = spent_budget + ?
                    WHERE cost_center_id = ?
                    """,
                    (total_amount, total_amount, cost_center_id),
                )

        conn.commit()
        return po_id
    finally:
        conn.close()


async def output_guardrail_node(state: ProcurementGraphState) -> Dict[str, Any]:
    """
    Output Guardrail & Final PO Commit Node:
    1. Commits approved/auto-approved requisitions to SQLite ERP and updates budgets.
    2. Redacts sensitive identifiers or credentials from responses.
    3. Emits a final confirmation receipt when resuming from approval.
    """
    draft_po = dict(state.get("draft_po") or {})
    approval_decision = str(state.get("approval_decision") or "").lower()
    is_rejected = approval_decision == "rejected" or draft_po.get("status") == "REJECTED"
    final_po_id: Optional[str] = state.get("final_po_id")

    if not is_rejected and draft_po and draft_po.get("items"):
        committed_id = _commit_final_po_to_erp(state, draft_po)
        if committed_id:
            final_po_id = committed_id
            draft_po["po_id"] = committed_id
            draft_po["status"] = "COMMITTED"

    messages = state.get("messages", [])
    latest_text = ""
    if messages and hasattr(messages[-1], "content"):
        raw = messages[-1].content
        if isinstance(raw, list):
            latest_text = "\n".join(
                b.get("text", "") if isinstance(b, dict) else str(b) for b in raw
            )
        else:
            latest_text = str(raw)

    next_status = "REJECTED" if is_rejected else "COMPLETED"

    if approval_decision == "approved" and final_po_id:
        approver_name = state.get("approver_name", "Tanvir Ahmed")
        notes = state.get("manager_notes", "")
        note_line = f"\n* **Manager Notes:** {notes}" if notes else ""

        receipt_msg = (
            f"**Purchase Order `{final_po_id}` Approved & Committed!**\n\n"
            f"* **Approved By:** {approver_name}\n"
            f"* **Cost Center:** `{draft_po.get('cost_center_id', 'CC-ENG-402')}`\n"
            f"* **Total Committed Amount:** **${float(draft_po.get('total_amount', 0)):,.2f}**"
            f"{note_line}\n\n"
            "The requisition has been recorded in the ERP ledger and deducted from the department budget."
        )
        scrubbed_reply = _redact_sensitive_text(receipt_msg)
        return {
            "draft_po": draft_po,
            "final_po_id": final_po_id,
            "status": next_status,
            "messages": [AIMessage(content=scrubbed_reply)],
            "visited_nodes": ["output_guardrail"],
        }

    scrubbed_reply = _redact_sensitive_text(latest_text)
    updated_messages = []
    if scrubbed_reply and scrubbed_reply != latest_text:
        updated_messages = [AIMessage(content=scrubbed_reply)]

    return {
        "draft_po": draft_po if draft_po else None,
        "final_po_id": final_po_id,
        "status": next_status,
        "messages": updated_messages,
        "visited_nodes": ["output_guardrail"],
    }
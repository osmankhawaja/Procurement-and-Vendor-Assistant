import re
from typing import Any, Dict, List, Tuple

from langchain_core.messages import AIMessage

from app.graph.state import ProcurementGraphState

# ==============================================================================
# GUARDRAIL RULES & DEFINITIONS
# ==============================================================================

# 1. Adversarial prompt-injection & budget-bypass patterns
INJECTION_PATTERNS: List[Tuple[str, str]] = [
    (
        r"ignore\s+(all\s+)?(previous\s+|prior\s+|budget\s+|policy\s+)?(instructions|rules|limits|guidelines)",
        "Prompt injection / policy override attempt detected.",
    ),
    (
        r"system\s*override|developer\s*mode|jailbreak|bypass\s+(approval|hitl|budget|limit)",
        "Unauthorized system override or HITL approval bypass attempt detected.",
    ),
    (
        r"approve\s+.*as\s+\$?\d+\s*(office\s+supplies|misc)",
        "Attempt to misclassify high-value spend to evade the approval threshold.",
    ),
    (
        r"(reveal|print|dump|show)\s+(your\s+)?(system\s+prompt|hidden\s+instructions|api\s*key)",
        "Attempt to extract confidential system instructions or credentials.",
    ),
]

# 2. Explicitly Blacklisted / Sanctioned Vendors (Hard Block before LLM runs)
BLACKLISTED_VENDORS: Dict[str, str] = {
    "shadowsupply": "Sanctioned for counterfeit hardware components (Compliance Bulletin 2025-09).",
    "rogueit": "Blacklisted due to data-breach non-compliance (Security Manual Sec 6.1).",
    "apex grey market": "Prohibited grey-market reseller without OEM warranty.",
    "quickcash electronics": "Flagged for anti-fraud blacklist violation.",
}

# 3. Out-of-scope keywords (HR salaries, personal finance, unrelated tasks)
OUT_OF_SCOPE_PATTERNS: List[str] = [
    r"\b(salary|salaries|payroll|bonus|compensation\s+band)\b",
    r"\b(stock\s+market|crypto|bitcoin|personal\s+investment|tax\s+return)\b",
    r"\b(write\s+me\s+a\s+poem|tell\s+me\s+a\s+joke|recipe\s+for)\b",
]


def _extract_latest_user_text(state: ProcurementGraphState) -> str:
    """Extracts the plain text content of the most recent user message."""
    messages = state.get("messages", [])
    if not messages:
        return ""
    last_msg = messages[-1]
    content = getattr(last_msg, "content", "")
    if isinstance(content, list):
        return " ".join(
            block.get("text", "") if isinstance(block, dict) else str(block)
            for block in content
        ).strip()
    return str(content).strip()


def _check_input_safety(text: str) -> Tuple[bool, str, List[Dict[str, Any]]]:
    """
    Evaluates incoming text against injection, blacklist, and scope rules.
    Returns: (is_blocked, refusal_message, citations)
    """
    lowered = text.lower()

    for pattern, reason in INJECTION_PATTERNS:
        if re.search(pattern, lowered):
            refusal = (
                "**Request Blocked by Security Guardrail**\n\n"
                f"I cannot process this request because a policy-override or prompt-injection "
                f"pattern was detected (*{reason}*).\n\n"
                "All purchase requisitions must follow corporate procurement policy and undergo "
                "standard budget and approval checks."
            )
            citations = [
                {
                    "doc_title": "Corporate_Procurement_Policy_v2.4.pdf",
                    "section": "Section 1.4 - System Integrity & Audit Controls",
                    "page": 3,
                    "snippet": "Attempts to circumvent spending thresholds, cost-center validations, or approval workflows are strictly prohibited and logged.",
                }
            ]
            return True, refusal, citations

    for vendor_key, ban_reason in BLACKLISTED_VENDORS.items():
        if vendor_key in lowered:
            refusal = (
                f"**Blacklisted Vendor Refusal**\n\n"
                f"Transactions with **{vendor_key.title()}** are prohibited. "
                f"Reason: *{ban_reason}*\n\n"
                "Please specify an approved vendor from the catalog or ask me to search approved suppliers."
            )
            citations = [
                {
                    "doc_title": "Approved_Vendor_Security_Manual.pdf",
                    "section": "Section 6.1 - Sanctioned & Blacklisted Suppliers",
                    "page": 10,
                    "snippet": "Requisitions referencing entities on the Corporate Anti-Fraud & Security Blacklist must be rejected immediately prior to catalog lookup.",
                }
            ]
            return True, refusal, citations

    for pattern in OUT_OF_SCOPE_PATTERNS:
        if re.search(pattern, lowered):
            refusal = (
                "**Out-of-Scope Request**\n\n"
                "I am the **Procurement & Vendor Management Assistant**. I can assist with "
                "hardware, cloud, or software requisitions, approved vendor lookups, budget checks, "
                "and procurement policies."
            )
            return True, refusal, []

    return False, "", []


async def input_guardrail_node(state: ProcurementGraphState) -> Dict[str, Any]:
    """
    Pre-execution Input Guardrail Node.
    Runs before the main procurement agent to block prompt injections, blacklisted vendors,
    and out-of-scope requests early.
    """
    user_text = _extract_latest_user_text(state)
    is_blocked, refusal_message, citations = _check_input_safety(user_text)

    if is_blocked:
        return {
            "blocked": True,
            "block_reason": refusal_message,
            "status": "BLOCKED",
            "citations": citations,
            "messages": [AIMessage(content=refusal_message)],
            "visited_nodes": ["input_guardrail"],
        }

    return {
        "blocked": False,
        "block_reason": None,
        "status": "RUNNING",
        "visited_nodes": ["input_guardrail"],
    }
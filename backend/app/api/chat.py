"""Chat endpoint for procurement requests."""

import asyncio
import logging
import time
from typing import Any, Protocol, cast
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from langchain_core.messages import AIMessage, HumanMessage

from app.config import get_settings, settings
from app.schemas.api_models import ChatRequest, ChatResponse

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger(__name__)

_PENDING_STATUSES = {
    "awaiting_approval",
    "approval_pending",
    "pending",
    "requires_approval",
    "waiting_for_approval",
}
_WORKFLOW_TIMEOUT_SECONDS = 120


class ProcurementGraph(Protocol):
    async def ainvoke(self, input: Any, config: dict[str, Any]) -> Any: ...


def _get_graph(request: Request) -> ProcurementGraph:
    graph = getattr(request.app.state, "procurement_graph", None)
    if graph is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The procurement workflow is not initialized.",
        )
    if not callable(getattr(graph, "ainvoke", None)):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The configured procurement workflow cannot process chat requests.",
        )
    return cast(ProcurementGraph, graph)


def _get_recursion_limit() -> int:
    try:
        active_settings = get_settings()
    except Exception:
        active_settings = settings
    return int(getattr(active_settings, "recursion_limit", 8) or 8)


def _message_text(content: Any) -> str | None:
    if isinstance(content, str):
        return content.strip() or None
    if isinstance(content, list):
        text_parts = [
            item["text"]
            for item in content
            if isinstance(item, dict) and isinstance(item.get("text"), str)
        ]
        combined = "\n".join(text_parts).strip()
        return combined or None
    return None


def _assistant_response(result: Any) -> str | None:
    if not isinstance(result, dict):
        return None

    for key in ("response", "answer"):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    messages = result.get("messages")
    if isinstance(messages, (list, tuple)):
        for message in reversed(messages):
            if isinstance(message, AIMessage):
                text = _message_text(message.content)
                if text is not None:
                    return text
            elif isinstance(message, dict):
                role = message.get("role", message.get("type"))
                if role in {"assistant", "ai"}:
                    text = _message_text(message.get("content"))
                    if text is not None:
                        return text
    return None


def _is_waiting_for_approval(result: Any) -> bool:
    if not isinstance(result, dict):
        return False
    if result.get("__interrupt__"):
        return True
    if result.get("approval_required") is True or result.get("requires_approval") is True:
        return True
    state_status = result.get("approval_status", result.get("status", ""))
    return str(state_status).strip().lower() in _PENDING_STATUSES


@router.post(
    "",
    response_model=ChatResponse,
    summary="Send a procurement message",
)
async def chat(request: Request, payload: ChatRequest) -> ChatResponse:
    """Run a user message through the procurement workflow."""
    graph = _get_graph(request)
    thread_id = payload.thread_id or str(uuid4())
    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": _get_recursion_limit(),
        "tags": ["procurement-chat"],
        "metadata": {
            "thread_id": thread_id,
            "workflow": "procurement",
        },
        "run_name": "procurement_chat",
    }
    started_at = time.perf_counter()
    try:
        result = await asyncio.wait_for(
            graph.ainvoke(
                {"messages": [HumanMessage(content=payload.message)]},
                config=config,
            ),
            timeout=_WORKFLOW_TIMEOUT_SECONDS,
        )
    except TimeoutError as exc:
        elapsed = time.perf_counter() - started_at
        logger.error(
            "Procurement workflow timed out after %.2fs (limit=%ss) for thread %s",
            elapsed,
            _WORKFLOW_TIMEOUT_SECONDS,
            thread_id,
        )
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="The procurement workflow timed out. Please try again.",
        ) from exc
    except asyncio.CancelledError:
        elapsed = time.perf_counter() - started_at
        logger.warning(
            "Procurement workflow task cancelled after %.2fs for thread %s",
            elapsed,
            thread_id,
        )
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="The procurement workflow timed out. Please try again.",
        ) from None
    except (RuntimeError, ValueError, TypeError) as exc:
        logger.exception("Procurement workflow failed for thread %s", thread_id)
        detail = str(exc).strip()
        if "GOOGLE_API_KEY" in detail:
            detail = "GOOGLE_API_KEY is not configured for the backend."
        else:
            detail = (
                "The procurement workflow could not complete. "
                "Check backend logs and service configuration."
            )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=detail,
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected procurement workflow failure for thread %s", thread_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "The procurement workflow or an external AI service is unavailable. "
                "Please try again."
            ),
        ) from exc

    if not isinstance(result, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The procurement workflow returned an invalid response.",
        )

    waiting_for_approval = _is_waiting_for_approval(result)
    response_text = _assistant_response(result)
    if response_text is None and not waiting_for_approval:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The procurement workflow completed without an assistant response.",
        )

    citations = result.get("citations", [])
    if citations is None:
        citations = []
    if not isinstance(citations, list):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The procurement workflow returned citations in an invalid format.",
        )

    purchase_order = result.get(
        "purchase_order",
        result.get("po_draft", result.get("draft_po")),
    )
    if purchase_order is not None and not isinstance(purchase_order, dict):
        purchase_order = jsonable_encoder(purchase_order)
        if not isinstance(purchase_order, dict):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="The procurement workflow returned a purchase order in an invalid format.",
            )

    return ChatResponse(
        thread_id=thread_id,
        response=response_text or "Approval is required before completing this request.",
        status="waiting_for_approval" if waiting_for_approval else "completed",
        citations=jsonable_encoder(citations),
        purchase_order=jsonable_encoder(purchase_order),
    )
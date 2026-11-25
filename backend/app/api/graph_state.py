"""Endpoints for inspecting procurement workflow graphs and checkpoints."""

import asyncio
from collections.abc import Mapping
from datetime import datetime
from typing import Any, Protocol, cast

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder

from app.schemas.api_models import GraphDefinitionResponse, GraphStateResponse


router = APIRouter(prefix="/graph", tags=["graph"])


class StateSnapshot(Protocol):
    """LangGraph snapshot properties exposed by the inspector API."""

    values: Mapping[str, Any]
    next: tuple[str, ...]
    tasks: tuple[Any, ...]
    metadata: Mapping[str, Any]
    created_at: datetime | None
    config: Mapping[str, Any]


class ProcurementGraph(Protocol):
    async def aget_state(self, config: dict[str, Any]) -> StateSnapshot: ...

    def get_graph(self) -> Any: ...


def _get_graph(request: Request) -> ProcurementGraph:
    graph = getattr(request.app.state, "procurement_graph", None)
    if graph is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The procurement workflow is not initialized.",
        )
    if not callable(getattr(graph, "aget_state", None)):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The configured procurement workflow cannot expose state snapshots.",
        )
    return cast(ProcurementGraph, graph)


def _task_details(task: Any) -> dict[str, Any]:
    details: dict[str, Any] = {}
    for attribute in ("id", "name", "path", "result"):
        value = getattr(task, attribute, None)
        if value is not None:
            details[attribute] = jsonable_encoder(value)

    error = getattr(task, "error", None)
    if error is not None:
        details["error"] = str(error)

    interrupts = getattr(task, "interrupts", ())
    if interrupts:
        details["interrupts"] = jsonable_encoder(interrupts)
    return details


def _has_checkpoint(snapshot: StateSnapshot) -> bool:
    if snapshot.created_at is not None or snapshot.values or snapshot.next:
        return True
    configurable = snapshot.config.get("configurable")
    return isinstance(configurable, Mapping) and bool(configurable.get("checkpoint_id"))


@router.get(
    "/definition",
    response_model=GraphDefinitionResponse,
    summary="Get the procurement workflow diagram",
)
async def graph_definition(request: Request) -> GraphDefinitionResponse:
    """Return a Mermaid diagram for the compiled procurement workflow."""
    graph = _get_graph(request)
    get_graph = getattr(graph, "get_graph", None)
    if not callable(get_graph):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The configured procurement workflow cannot provide a graph diagram.",
        )
    compiled_graph = get_graph()
    diagram = await asyncio.to_thread(compiled_graph.draw_mermaid)
    return GraphDefinitionResponse(mermaid=diagram)


@router.get(
    "/{thread_id}",
    response_model=GraphStateResponse,
    summary="Get a conversation's workflow state",
)
async def get_graph_state(
    thread_id: str,
    request: Request,
) -> GraphStateResponse:
    """Return the latest checkpointed state for a workflow thread."""
    graph = _get_graph(request)
    snapshot = await graph.aget_state(
        {"configurable": {"thread_id": thread_id}}
    )
    if not _has_checkpoint(snapshot):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No workflow state was found for thread '{thread_id}'.",
        )

    return GraphStateResponse(
        thread_id=thread_id,
        values=jsonable_encoder(dict(snapshot.values)),
        next=list(snapshot.next),
        tasks=[_task_details(task) for task in snapshot.tasks],
        metadata=jsonable_encoder(dict(snapshot.metadata)),
        created_at=snapshot.created_at,
    )
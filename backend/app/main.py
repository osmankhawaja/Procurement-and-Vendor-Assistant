"""FastAPI application entry point."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api import router as api_router
from app.config import configure_langsmith, get_settings, settings
from app.graph import close_compiled_graph, get_compiled_graph


def _resolve_settings():
    try:
        return get_settings()
    except Exception:
        return settings


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    """Initialize application resources and release them during shutdown."""
    active_settings = _resolve_settings()
    application.state.settings = active_settings
    application.state.procurement_graph = None

    configure_langsmith(active_settings)

    try:
        application.state.procurement_graph = await get_compiled_graph()
        yield
    finally:
        application.state.procurement_graph = None
        await close_compiled_graph()


initial_settings = _resolve_settings()

app = FastAPI(
    title="AI-Powered Procurement and Vendor Assistant",
    description="Policy-aware procurement workflows with LangGraph, RAG, MCP, and human approval.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=initial_settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/", tags=["system"])
async def root() -> dict[str, str]:
    """Return basic service metadata."""
    return {
        "name": "AI-Powered Procurement and Vendor Assistant",
        "status": "running",
    }


@app.get("/health", tags=["system"])
async def health(request: Request) -> dict[str, Any]:
    """Report whether the API process and workflow graph are healthy."""
    graph_ready = getattr(request.app.state, "procurement_graph", None) is not None
    return {
        "status": "ok" if graph_ready else "degraded",
        "graph_ready": graph_ready,
    }
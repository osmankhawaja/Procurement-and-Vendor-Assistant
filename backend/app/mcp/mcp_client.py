"""Async in-process MCP client for ERP procurement tools."""

import asyncio
import json
from typing import Any

from fastmcp import Client

from app.mcp.erp_mcp_server import _database_path, initialize_erp_database, mcp


_EMPTY_TOOL_RESULTS = {
    "search_catalog_items": [],
    "search_approved_vendors": [],
    "get_department_budget": None,
}


def _decode_tool_result(contents: Any, tool_name: str) -> Any:
    if hasattr(contents, "data") and contents.data is not None:
        return contents.data

    if hasattr(contents, "content"):
        blocks = contents.content
    elif isinstance(contents, list):
        blocks = contents
    else:
        blocks = []

    if not blocks and tool_name in _EMPTY_TOOL_RESULTS:
        return _EMPTY_TOOL_RESULTS[tool_name]

    if len(blocks) != 1 or not isinstance(getattr(blocks[0], "text", None), str):
        raise RuntimeError(
            f"ERP MCP tool '{tool_name}' returned an unsupported result."
        )
    try:
        return json.loads(blocks[0].text)
    except json.JSONDecodeError as error:
        raise RuntimeError(
            f"ERP MCP tool '{tool_name}' returned invalid JSON."
        ) from error


async def _call_tool(client: Client, name: str, arguments: dict[str, Any]) -> Any:
    result = await client.call_tool(name, arguments)
    return _decode_tool_result(result, name)


async def lookup_procurement_context(
    query: str,
    *,
    cost_center_id: str | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """Fetch approved catalog, vendor, and optional budget facts via MCP."""
    normalized_query = query.strip()
    if not normalized_query:
        raise ValueError("query must not be blank")

    initialize_erp_database(_database_path())
    async with Client(mcp) as client:
        catalog_task = _call_tool(
            client,
            "search_catalog_items",
            {"query": normalized_query, "limit": limit},
        )
        vendors_task = _call_tool(
            client,
            "search_approved_vendors",
            {"query": normalized_query, "limit": limit},
        )

        if cost_center_id is not None and cost_center_id.strip():
            budget_task = _call_tool(
                client,
                "get_department_budget",
                {"cost_center_id": cost_center_id.strip()},
            )
            catalog_items, approved_vendors, budget = await asyncio.gather(
                catalog_task,
                vendors_task,
                budget_task,
            )
        else:
            catalog_items, approved_vendors = await asyncio.gather(
                catalog_task,
                vendors_task,
            )
            budget = None

    if not isinstance(catalog_items, list) or not isinstance(approved_vendors, list):
        raise RuntimeError("ERP MCP search tools returned an invalid result shape.")
    if budget is not None and not isinstance(budget, dict):
        raise RuntimeError("ERP MCP budget tool returned an invalid result shape.")

    return {
        "catalog_items": catalog_items,
        "approved_vendors": approved_vendors,
        "budget": budget,
    }
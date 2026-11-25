import sqlite3
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.mcp import erp_mcp_server
from app.mcp.mcp_client import lookup_procurement_context


@pytest.mark.asyncio
async def test_mcp_lookup_returns_only_approved_catalog_and_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "erp.sqlite"
    monkeypatch.setattr(
        erp_mcp_server,
        "get_settings",
        lambda: SimpleNamespace(erp_db_path=lambda: database_path),
    )
    erp_mcp_server.initialize_erp_database()
    with closing(sqlite3.connect(database_path)) as connection:
        with connection:
            connection.execute(
                "INSERT INTO vendors (vendor_id, name, status, categories) VALUES (?, ?, ?, ?)",
                ("vendor-1", "Approved Computing", "APPROVED", "laptops"),
            )
            connection.execute(
                """
                INSERT INTO products
                    (product_id, item_name, description, vendor_id, unit_price, currency, approved)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                ("product-1", "Business Laptop", "Enterprise notebook", "vendor-1", 750, "USD", 1),
            )
            connection.execute(
                "INSERT INTO vendors (vendor_id, name, status) VALUES (?, ?, ?)",
                ("vendor-2", "Pending Supplier", "PENDING"),
            )
            connection.execute(
                """
                INSERT INTO products
                    (product_id, item_name, vendor_id, unit_price, currency, approved)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                ("product-2", "Budget Laptop", "vendor-2", 200, "USD", 1),
            )
            connection.execute(
                """
                INSERT INTO department_budgets
                    (cost_center_id, department, total_budget, spent_budget, remaining_budget)
                VALUES (?, ?, ?, ?, ?)
                """,
                ("CC-IT", "IT", 10000, 2500, 7500),
            )

    context = await lookup_procurement_context(
        "laptop",
        cost_center_id="CC-IT",
    )

    assert len(context["catalog_items"]) == 1
    assert context["catalog_items"][0]["product_id"] == "product-1"
    assert context["catalog_items"][0]["approved"] is True
    assert len(context["approved_vendors"]) == 1
    assert context["budget"]["remaining_budget"] == 7500


@pytest.mark.asyncio
async def test_mcp_lookup_handles_empty_searches_and_missing_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "erp.sqlite"
    monkeypatch.setattr(
        erp_mcp_server,
        "get_settings",
        lambda: SimpleNamespace(erp_db_path=lambda: database_path),
    )

    context = await lookup_procurement_context(
        "unmatched procurement request",
        cost_center_id="CC-MISSING",
    )

    assert context == {
        "catalog_items": [],
        "approved_vendors": [],
        "budget": None,
    }


@pytest.mark.asyncio
async def test_mcp_client_rejects_empty_search_query() -> None:
    with pytest.raises(ValueError, match="blank"):
        await lookup_procurement_context("   ")
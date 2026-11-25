from contextlib import closing
from pathlib import Path
import sqlite3
from types import SimpleNamespace

from app.graph.nodes import output_guardrail
from app.mcp import erp_mcp_server
from data.seed_erp import seed_erp_database
import pytest


def test_seed_erp_initializes_and_idempotently_seeds_demo_records(
    tmp_path: Path,
) -> None:
  database_path = tmp_path / "erp.sqlite"

  first_run = seed_erp_database(database_path)
  with closing(sqlite3.connect(database_path)) as connection:
    with connection:
      connection.execute(
          """
                UPDATE department_budgets
                SET remaining_budget = 20000
                WHERE cost_center_id = 'CC-ENG-402'
                """
      )
  second_run = seed_erp_database(database_path)

  assert first_run.vendors_inserted == 4
  assert first_run.products_inserted == 5
  assert first_run.budgets_inserted == 3
  assert second_run.vendors_inserted == 0
  assert second_run.products_inserted == 0
  assert second_run.budgets_inserted == 0

  with closing(sqlite3.connect(database_path)) as connection:
    counts = tuple(
        connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in ("vendors", "products", "department_budgets")
    )
    budget_row = connection.execute(
        """
            SELECT remaining_budget
            FROM department_budgets
            WHERE cost_center_id = 'CC-ENG-402'
            """
    ).fetchone()

  assert counts == (4, 5, 3)
  assert budget_row is not None
  assert budget_row[0] == 20000


def test_seeded_database_supports_approved_only_lookups(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
  database_path = tmp_path / "erp.sqlite"
  seed_erp_database(database_path)
  monkeypatch.setattr(
      erp_mcp_server,
      "get_settings",
      lambda: SimpleNamespace(erp_db_path=lambda: database_path),
  )

  vendors = erp_mcp_server.search_approved_vendors("laptop")
  products = erp_mcp_server.search_catalog_items("laptop")
  budget = erp_mcp_server.get_department_budget("CC-ENG-402")

  assert {vendor["name"] for vendor in vendors} == {
      "Apple Enterprise Partner",
      "Dell Corporate",
  }
  assert [product["product_id"] for product in products] == [
      "DELL-BUSINESS-LAPTOP-001",
      "APPLE-MACBOOK-AIR-001",
  ]
  assert budget is not None
  assert budget["remaining_budget"] == 37500


def test_committing_same_purchase_order_does_not_deduct_budget_twice(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
  database_path = tmp_path / "erp.sqlite"
  seed_erp_database(database_path)
  monkeypatch.setattr(
      output_guardrail,
      "settings",
      SimpleNamespace(erp_db_path=lambda: database_path),
  )
  monkeypatch.setattr(
      output_guardrail,
      "get_settings",
      lambda: SimpleNamespace(erp_db_path=lambda: database_path),
      raising=False,
  )
  state = {"thread_id": "thread-1", "citations": []}
  draft = {
      "po_id": "PO-TEST-1",
      "items": [{"product_id": "DELL-USB-C-DOCK-001", "quantity": 1}],
      "total_amount": 199,
      "cost_center_id": "CC-ENG-402",
      "department": "Engineering",
  }

  output_guardrail._commit_final_po_to_erp(state, draft)
  output_guardrail._commit_final_po_to_erp(state, draft)

  with closing(sqlite3.connect(database_path)) as connection:
    budget_row = connection.execute(
        """
            SELECT spent_budget, remaining_budget
            FROM department_budgets
            WHERE cost_center_id = 'CC-ENG-402'
            """
    ).fetchone()

  assert budget_row is not None
  spent_budget, remaining_budget = budget_row
  assert spent_budget == 12699
  assert remaining_budget == 37301
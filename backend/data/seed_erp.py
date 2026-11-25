"""Initialize and populate a local ERP SQLite database with demo records."""

from __future__ import annotations

import argparse
from contextlib import closing
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import sqlite3
import sys

if __package__ in (None, ""):
  sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings
from app.mcp.erp_mcp_server import initialize_erp_database

_VENDORS: tuple[tuple[str, str, str, str, str | None], ...] = (
    (
        "VEND-APPLE-ENT",
        "Apple Enterprise Partner",
        "APPROVED",
        "computers, laptops, tablets",
        None,
    ),
    (
        "VEND-DELL-CORP",
        "Dell Corporate",
        "APPROVED",
        "computers, laptops, monitors, accessories",
        None,
    ),
    (
        "VEND-GLOBAL-IT",
        "Global IT Solutions",
        "APPROVED",
        "software, cloud, managed services",
        None,
    ),
    (
        "VEND-PENDING-DEMO",
        "Example Pending Supplier",
        "PENDING",
        "peripherals",
        None,
    ),
)

_PRODUCTS: tuple[tuple[str, str, str, str, float, str, int], ...] = (
    (
        "DELL-BUSINESS-LAPTOP-001",
        "Business Laptop",
        "Business-class laptop for corporate users; sample catalog record.",
        "VEND-DELL-CORP",
        1299.00,
        "USD",
        1,
    ),
    (
        "APPLE-MACBOOK-AIR-001",
        "MacBook Air 13-inch",
        "Lightweight laptop for engineering and general corporate workflows.",
        "VEND-APPLE-ENT",
        1199.00,
        "USD",
        1,
    ),
    (
        "DELL-USB-C-DOCK-001",
        "USB-C Docking Station",
        "USB-C docking station; sample catalog record.",
        "VEND-DELL-CORP",
        199.00,
        "USD",
        1,
    ),
    (
        "GIT-CLOUD-SEAT-001",
        "Cloud DevOps Seat License",
        "Annual cloud workspace and deployment seat license.",
        "VEND-GLOBAL-IT",
        240.00,
        "USD",
        1,
    ),
    (
        "PENDING-USB-HUB-001",
        "Example USB-C Hub",
        "Sample item from a supplier that is not approved.",
        "VEND-PENDING-DEMO",
        39.00,
        "USD",
        0,
    ),
)

_DEPARTMENT_BUDGETS: tuple[tuple[str, str, float, float, float], ...] = (
    ("CC-ENG-402", "Engineering", 50000.00, 12500.00, 37500.00),
    ("CC-IT-210", "Information Technology", 100000.00, 25000.00, 75000.00),
    ("CC-FIN-110", "Finance", 30000.00, 8000.00, 22000.00),
)


@dataclass(frozen=True)
class SeedSummary:
  """Counts of demo records newly inserted by a seed run."""

  database_path: str
  vendors_inserted: int
  products_inserted: int
  budgets_inserted: int


def _insert_missing_rows(
    connection: sqlite3.Connection,
    statement: str,
    rows: tuple[tuple[object, ...], ...],
) -> int:
  inserted = 0
  for row in rows:
    cursor = connection.execute(statement, row)
    inserted += max(cursor.rowcount, 0)
  return inserted


def seed_erp_database(database_path: str | Path | None = None) -> SeedSummary:
  """Create the ERP schema and insert missing, non-production demo records.

    Existing records are left unchanged, so repeated runs are safe and do not
    overwrite locally maintained catalog or budget data.
    """
  raw_path = (
      database_path if database_path is not None else get_settings().erp_db_path()
  )
  path = Path(raw_path).resolve()
  initialize_erp_database(path)

  with closing(sqlite3.connect(str(path), timeout=10)) as connection:
    connection.execute("PRAGMA foreign_keys = ON")
    with connection:
      vendors_inserted = _insert_missing_rows(
          connection,
          """
                INSERT INTO vendors (vendor_id, name, status, categories, website)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(vendor_id) DO NOTHING
                """,
          _VENDORS,
      )
      products_inserted = _insert_missing_rows(
          connection,
          """
                INSERT INTO products (
                    product_id, item_name, description, vendor_id,
                    unit_price, currency, approved
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(product_id) DO NOTHING
                """,
          _PRODUCTS,
      )
      budgets_inserted = _insert_missing_rows(
          connection,
          """
                INSERT INTO department_budgets (
                    cost_center_id, department, total_budget,
                    spent_budget, remaining_budget
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(cost_center_id) DO NOTHING
                """,
          _DEPARTMENT_BUDGETS,
      )

  return SeedSummary(
      database_path=str(path),
      vendors_inserted=vendors_inserted,
      products_inserted=products_inserted,
      budgets_inserted=budgets_inserted,
  )


def main() -> None:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument(
      "--database-path",
      type=Path,
      help="SQLite file to initialize (defaults to ERP_DATABASE_PATH).",
  )
  args = parser.parse_args()
  summary = seed_erp_database(args.database_path)
  print(json.dumps(asdict(summary), indent=2))


if __name__ == "__main__":
  main()
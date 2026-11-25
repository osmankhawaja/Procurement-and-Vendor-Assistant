"""Read-only ERP catalog and budget tools exposed through FastMCP."""

import re
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

from app.config import get_settings


mcp = FastMCP(
    name="procurement-erp",
    instructions=(
        "Read-only access to approved vendors, catalog items, and department budgets. "
        "Purchase-order writes are handled by the procurement workflow."
    ),
)

_SEARCH_STOP_WORDS = {
    "a",
    "an",
    "and",
    "approved",
    "buy",
    "can",
    "find",
    "for",
    "get",
    "i",
    "me",
    "need",
    "of",
    "order",
    "please",
    "purchase",
    "show",
    "the",
    "to",
    "vendor",
    "vendors",
    "with",
    "you",
}

_INITIALIZED_DATABASES: set[Path] = set()


def _database_path() -> Path:
    return Path(get_settings().erp_db_path()).resolve()


def _connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(str(path), timeout=10)
    connection.execute("PRAGMA busy_timeout = 10000")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def initialize_erp_database(
    database_path: str | Path | None = None,
    *,
    force: bool = False,
) -> None:
    """Create the local ERP tables required by the read-only tools."""
    path = (
        Path(database_path).resolve()
        if database_path is not None
        else _database_path()
    )
    if not force and path in _INITIALIZED_DATABASES and path.exists():
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(_connect(path)) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS vendors (
                vendor_id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL,
                categories TEXT NOT NULL DEFAULT '',
                website TEXT
            );

            CREATE TABLE IF NOT EXISTS products (
                product_id TEXT PRIMARY KEY,
                item_name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                vendor_id TEXT NOT NULL REFERENCES vendors(vendor_id),
                unit_price REAL NOT NULL CHECK (unit_price >= 0),
                currency TEXT NOT NULL DEFAULT 'USD',
                approved INTEGER NOT NULL DEFAULT 0 CHECK (approved IN (0, 1))
            );

            CREATE TABLE IF NOT EXISTS department_budgets (
                cost_center_id TEXT PRIMARY KEY,
                department TEXT NOT NULL,
                total_budget REAL NOT NULL CHECK (total_budget >= 0),
                spent_budget REAL NOT NULL DEFAULT 0 CHECK (spent_budget >= 0),
                remaining_budget REAL NOT NULL CHECK (remaining_budget >= 0)
            );

            CREATE TABLE IF NOT EXISTS purchase_orders (
                po_id TEXT PRIMARY KEY,
                thread_id TEXT,
                requester_name TEXT,
                department TEXT,
                cost_center_id TEXT,
                total_amount REAL NOT NULL DEFAULT 0,
                items_json TEXT NOT NULL DEFAULT '[]',
                citations_json TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL,
                approver_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_products_vendor_id
                ON products(vendor_id);
            CREATE INDEX IF NOT EXISTS idx_products_approved
                ON products(approved);
            """
        )
        connection.commit()

    _INITIALIZED_DATABASES.add(path)


def _escaped_like_pattern(query: str) -> str:
    escaped = (
        query.strip()
        .replace("!", "!!")
        .replace("%", "!%")
        .replace("_", "!_")
    )
    return f"%{escaped}%"


def _search_patterns(query: str) -> list[str]:
    terms = [
        term
        for term in re.findall(r"[a-z0-9]+", query.casefold())
        if term not in _SEARCH_STOP_WORDS and len(term) > 1
    ]
    if not terms:
        terms = [query.strip()]

    patterns = [_escaped_like_pattern(query)]
    for term in terms[:12]:
        candidates = [term]
        if term.endswith("ies") and len(term) > 4:
            candidates.append(f"{term[:-3]}y")
        elif term.endswith("s") and len(term) > 4 and not term.endswith("ss"):
            candidates.append(term[:-1])
        elif len(term) > 4:
            candidates.append(f"{term}s")
        for candidate in candidates:
            pattern = _escaped_like_pattern(candidate)
            if pattern not in patterns:
                patterns.append(pattern)
    return patterns


def _any_column_match(columns: tuple[str, ...], pattern_count: int) -> str:
    return " OR ".join(
        f"{column} LIKE ? ESCAPE '!'"
        for _ in range(pattern_count)
        for column in columns
    )


def _validated_limit(limit: int) -> int:
    if not 1 <= limit <= 50:
        raise ValueError("limit must be between 1 and 50")
    return limit


@mcp.tool(
    name="search_approved_vendors",
    description="Search approved ERP vendors by name or category.",
)
def search_approved_vendors(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Return approved vendors matching a name or category query."""
    normalized_query = query.strip()
    if not normalized_query:
        raise ValueError("query must not be blank")
    row_limit = _validated_limit(limit)
    patterns = _search_patterns(normalized_query)
    db_path = _database_path()
    initialize_erp_database(db_path)

    with closing(_connect(db_path)) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            f"""
            SELECT vendor_id, name, categories, website
            FROM vendors
            WHERE UPPER(status) = 'APPROVED'
              AND ({_any_column_match(("name", "categories"), len(patterns))})
            ORDER BY name
            LIMIT ?
            """,
            (*[pattern for pattern in patterns for _ in ("name", "categories")], row_limit),
        ).fetchall()
    return [dict(row) for row in rows]


@mcp.tool(
    name="search_catalog_items",
    description="Search approved products from approved ERP vendors.",
)
def search_catalog_items(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Return approved catalog items with verified vendor and price data."""
    normalized_query = query.strip()
    if not normalized_query:
        raise ValueError("query must not be blank")
    row_limit = _validated_limit(limit)
    patterns = _search_patterns(normalized_query)
    db_path = _database_path()
    initialize_erp_database(db_path)

    with closing(_connect(db_path)) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            f"""
            SELECT
                products.product_id,
                products.item_name,
                products.description,
                products.vendor_id,
                vendors.name AS vendor_name,
                products.unit_price,
                products.currency
            FROM products
            JOIN vendors ON vendors.vendor_id = products.vendor_id
            WHERE products.approved = 1
              AND UPPER(vendors.status) = 'APPROVED'
              AND (
                  {_any_column_match(("products.item_name", "products.description"), len(patterns))}
              )
            ORDER BY products.item_name
            LIMIT ?
            """,
            (*[pattern for pattern in patterns for _ in ("name", "description")], row_limit),
        ).fetchall()

    return [
        {
            **dict(row),
            "approved": True,
        }
        for row in rows
    ]


@mcp.tool(
    name="get_department_budget",
    description="Look up total, spent, and remaining budget for a cost center.",
)
def get_department_budget(cost_center_id: str) -> dict[str, Any] | None:
    """Return budget details for a cost center, or None if it is not configured."""
    normalized_id = cost_center_id.strip()
    if not normalized_id:
        raise ValueError("cost_center_id must not be blank")
    db_path = _database_path()
    initialize_erp_database(db_path)

    with closing(_connect(db_path)) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """
            SELECT cost_center_id, department, total_budget,
                   spent_budget, remaining_budget
            FROM department_budgets
            WHERE cost_center_id = ?
            """,
            (normalized_id,),
        ).fetchone()
    return dict(row) if row is not None else None


if __name__ == "__main__":
    mcp.run()
"""CRUD operations for locally persisted department preferences."""

import json
import sqlite3
from collections.abc import Mapping
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Any, Iterator


BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MEMORY_DATABASE_PATH = BACKEND_ROOT / "data" / "department_preferences.sqlite"

_INITIALIZED_MEMORY_DBS: set[Path] = set()


def _resolve_memory_database_path(
    database_path: str | Path | None = None,
) -> Path:
    path = Path(database_path) if database_path is not None else DEFAULT_MEMORY_DATABASE_PATH
    if not path.is_absolute():
        path = BACKEND_ROOT / path
    return path.resolve()


def _connect_memory_db(
    path: Path,
    *,
    isolation_level: str | None = "",
) -> sqlite3.Connection:
    connection = sqlite3.connect(
        str(path),
        timeout=10,
        isolation_level=isolation_level,
    )
    connection.execute("PRAGMA busy_timeout = 10000")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def initialize_memory_database(
    database_path: str | Path | None = None,
    *,
    force: bool = False,
) -> Path:
    """Create the memory database and its preferences table if they do not exist."""
    path = _resolve_memory_database_path(database_path)
    if not force and path in _INITIALIZED_MEMORY_DBS and path.exists():
        return path

    path.parent.mkdir(parents=True, exist_ok=True)

    with closing(_connect_memory_db(path, isolation_level="")) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS department_preferences (
                department TEXT PRIMARY KEY NOT NULL,
                preferences_json TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.commit()

    _INITIALIZED_MEMORY_DBS.add(path)
    return path


@contextmanager
def _memory_connection(
    database_path: str | Path | None = None,
    *,
    autocommit_transactions: bool = True,
) -> Iterator[sqlite3.Connection]:
    path = initialize_memory_database(database_path)
    isolation_level = "" if autocommit_transactions else None
    with closing(_connect_memory_db(path, isolation_level=isolation_level)) as connection:
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            if autocommit_transactions:
                connection.commit()
        except Exception:
            if autocommit_transactions:
                try:
                    connection.rollback()
                except Exception:
                    pass
            raise


def _validate_department(department: str) -> str:
    if not isinstance(department, str):
        raise TypeError("department must be a string.")
    normalized = department.strip()
    if not normalized or len(normalized) > 200:
        raise ValueError("department must contain between 1 and 200 characters.")
    return normalized


def _serialize_preferences(preferences: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    if not isinstance(preferences, Mapping):
        raise TypeError("preferences must be a mapping.")
    if any(not isinstance(key, str) or not key.strip() for key in preferences):
        raise ValueError("preference keys must be non-empty strings.")
    try:
        serialized = json.dumps(dict(preferences), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("preferences must contain only JSON-serializable values.") from exc
    normalized = json.loads(serialized)
    return serialized, normalized


def _decode_preferences(department: str, value: str) -> dict[str, Any]:
    try:
        preferences = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Stored preferences for department {department!r} are invalid JSON."
        ) from exc
    if not isinstance(preferences, dict):
        raise ValueError(
            f"Stored preferences for department {department!r} must be a JSON object."
        )
    return preferences


def get_department_preferences(
    department: str,
    *,
    database_path: str | Path | None = None,
) -> dict[str, Any]:
    """Return a department's preferences, or an empty mapping when none are stored."""
    normalized_department = _validate_department(department)
    with _memory_connection(database_path) as connection:
        row = connection.execute(
            """
            SELECT preferences_json
            FROM department_preferences
            WHERE department = ?
            """,
            (normalized_department,),
        ).fetchone()

    if row is None:
        return {}
    return _decode_preferences(normalized_department, row["preferences_json"])


def save_department_preferences(
    department: str,
    preferences: Mapping[str, Any],
    *,
    database_path: str | Path | None = None,
) -> dict[str, Any]:
    """Replace all stored preferences for a department and return the saved values."""
    normalized_department = _validate_department(department)
    serialized, normalized_preferences = _serialize_preferences(preferences)
    with _memory_connection(database_path) as connection:
        connection.execute(
            """
            INSERT INTO department_preferences (department, preferences_json)
            VALUES (?, ?)
            ON CONFLICT(department) DO UPDATE SET
                preferences_json = excluded.preferences_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (normalized_department, serialized),
        )
    return normalized_preferences


def update_department_preferences(
    department: str,
    updates: Mapping[str, Any],
    *,
    database_path: str | Path | None = None,
) -> dict[str, Any]:
    """Merge preference keys into the department's existing values."""
    normalized_department = _validate_department(department)
    _, normalized_updates = _serialize_preferences(updates)
    with _memory_connection(database_path, autocommit_transactions=False) as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            row = connection.execute(
                """
                SELECT preferences_json
                FROM department_preferences
                WHERE department = ?
                """,
                (normalized_department,),
            ).fetchone()
            current = (
                _decode_preferences(normalized_department, row["preferences_json"])
                if row is not None
                else {}
            )
            current.update(normalized_updates)
            serialized, saved_preferences = _serialize_preferences(current)
            connection.execute(
                """
                INSERT INTO department_preferences (department, preferences_json)
                VALUES (?, ?)
                ON CONFLICT(department) DO UPDATE SET
                    preferences_json = excluded.preferences_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (normalized_department, serialized),
            )
            connection.execute("COMMIT")
        except Exception:
            try:
                connection.execute("ROLLBACK")
            except Exception:
                pass
            raise
    return saved_preferences


def delete_department_preferences(
    department: str,
    *,
    database_path: str | Path | None = None,
) -> bool:
    """Delete a department's stored preferences and report whether a row existed."""
    normalized_department = _validate_department(department)
    with _memory_connection(database_path) as connection:
        cursor = connection.execute(
            "DELETE FROM department_preferences WHERE department = ?",
            (normalized_department,),
        )
    return cursor.rowcount > 0
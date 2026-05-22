"""Database connection management for Novel Factory.

v6.6.9: Migration detection now uses the declarative registry in
migration_registry.py instead of an if/elif chain. The old
_is_migration_applied_by_schema() is retained as a thin wrapper
for backward compatibility.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from .migration_registry import (
    is_migration_applied_by_registry,
    get_migration_sql_files,
    check_migration_health,
    check_table_integrity,
    MigrationHealthStatus,
    TableIntegrityCheck,
)


DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "novel_factory.db"


def _ensure_migration_tracking(conn: sqlite3.Connection) -> None:
    """Create the _migrations_applied table if it does not exist."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS _migrations_applied ("
        "name TEXT PRIMARY KEY, applied_at DATETIME DEFAULT (datetime('now','+8 hours'))"
        ")"
    )
    conn.commit()


def _is_migration_applied_by_tracking(conn: sqlite3.Connection, name: str) -> bool:
    """Check if a migration is recorded in the _migrations_applied table."""
    row = conn.execute(
        "SELECT 1 FROM _migrations_applied WHERE name=?", (name,)
    ).fetchone()
    return row is not None


def _is_migration_applied_by_schema(conn: sqlite3.Connection, name: str) -> bool:
    """Check if a migration's effects are already present in the schema.

    v6.6.9: Delegates to the declarative migration registry.
    Falls back to False for unknown migration IDs, meaning
    the tracking table is the sole authority for those.
    """
    return is_migration_applied_by_registry(conn, name)


def _record_migration(conn: sqlite3.Connection, name: str) -> None:
    """Record a migration as applied using INSERT OR IGNORE for idempotency."""
    conn.execute(
        "INSERT OR IGNORE INTO _migrations_applied (name) VALUES (?)", (name,)
    )


def get_connection(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Get a SQLite connection with row factory enabled.

    Args:
        db_path: Path to the database file. Defaults to novel_factory.db
                 in the project root.
    """
    path = Path(db_path) if db_path else DEFAULT_DB_PATH
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    """Convert a sqlite3.Row to a plain dict."""
    return dict(row) if row else None


def init_db(db_path: str | Path | None = None) -> None:
    """Initialize the database with all required tables.

    Idempotent: safe to call multiple times on the same database.
    Migrations are tracked in _migrations_applied and will not be re-run.
    For databases created before tracking was added, schema detection
    is used to identify already-applied migrations.
    """
    conn = get_connection(db_path)
    schema_dir = Path(__file__).resolve().parent / "schema"

    # Ensure migration tracking table exists before any schema operations
    _ensure_migration_tracking(conn)

    # Run base schema if not already applied
    # The base schema uses CREATE TABLE IF NOT EXISTS, so it's safe to re-run,
    # but we skip it for efficiency and to avoid any edge cases.
    base_sql = schema_dir / "000_base_schema.sql"
    base_applied = _is_migration_applied_by_tracking(conn, "000_base_schema") or \
                   _is_migration_applied_by_schema(conn, "000_base_schema")

    if not base_applied:
        if base_sql.exists():
            conn.executescript(base_sql.read_text(encoding="utf-8"))
        else:
            # Fallback: try openclaw-agents path for dev environment
            alt_sql = (
                Path(__file__).resolve().parent.parent.parent
                / "openclaw-agents" / "shared" / "data" / "init_db.sql"
            )
            if alt_sql.exists():
                conn.executescript(alt_sql.read_text(encoding="utf-8"))

    # Always ensure base schema is tracked (handles pre-tracking databases)
    _record_migration(conn, "000_base_schema")

    # Run all migration files in order, skipping already-applied ones
    for sql_file in get_migration_sql_files():
        migration_name = sql_file.stem

        # Check tracking table first
        if _is_migration_applied_by_tracking(conn, migration_name):
            continue

        # Also check schema for migrations applied before tracking existed
        if _is_migration_applied_by_schema(conn, migration_name):
            _record_migration(conn, migration_name)
            continue

        # Execute the migration
        conn.executescript(sql_file.read_text(encoding="utf-8"))
        _record_migration(conn, migration_name)

    conn.commit()
    conn.close()

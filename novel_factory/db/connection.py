"""Database connection management for Novel Factory."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


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

    This handles databases that ran migrations before _migrations_applied
    tracking was introduced.  Returns True if the migration's effects are
    detectable in the current schema.
    """
    if name == "000_base_schema":
        # Base schema creates the projects table
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='projects'"
        )
        return cursor.fetchone() is not None

    if name == "001_add_workflow_tables":
        # 001 adds workflow_runs table
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='workflow_runs'"
        )
        return cursor.fetchone() is not None

    if name == "002_v1_1_stability":
        # 002 adds content_hash column to chapter_versions
        cursor = conn.execute("PRAGMA table_info(chapter_versions)")
        columns = [row[1] for row in cursor.fetchall()]
        return "content_hash" in columns

    if name == "003_v1_2_quality":
        # 003 adds issue_categories column to reviews
        cursor = conn.execute("PRAGMA table_info(reviews)")
        columns = [row[1] for row in cursor.fetchall()]
        return "issue_categories" in columns

    if name == "004_v1_4_runtime":
        # 004 adds revision_target column to reviews
        cursor = conn.execute("PRAGMA table_info(reviews)")
        columns = [row[1] for row in cursor.fetchall()]
        return "revision_target" in columns

    if name == "005_v2_sidecar_agents":
        # 005 adds 4 tables: scout_reports, reports, continuity_reports, architecture_proposals
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN "
            "('scout_reports', 'reports', 'continuity_reports', 'architecture_proposals')"
        )
        tables = {row[0] for row in cursor.fetchall()}
        required = {"scout_reports", "reports", "continuity_reports", "architecture_proposals"}
        return required.issubset(tables)

    if name == "006_v2_1_qualityhub_skill":
        # 006 adds quality_reports table
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='quality_reports'"
        )
        return cursor.fetchone() is not None

    if name == "007_v3_0_batch_production":
        # 007 adds 3 tables: production_runs, production_run_items, human_review_sessions
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN "
            "('production_runs', 'production_run_items', 'human_review_sessions')"
        )
        tables = {row[0] for row in cursor.fetchall()}
        required = {"production_runs", "production_run_items", "human_review_sessions"}
        return required.issubset(tables)

    if name == "008_v3_2_batch_revision":
        # 008 adds 3 tables: batch_revision_runs, batch_revision_items, chapter_review_notes
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN "
            "('batch_revision_runs', 'batch_revision_items', 'chapter_review_notes')"
        )
        tables = {row[0] for row in cursor.fetchall()}
        required = {"batch_revision_runs", "batch_revision_items", "chapter_review_notes"}
        return required.issubset(tables)

    if name == "009_v3_3_batch_continuity_gate":
        # 009 adds batch_continuity_gates table
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='batch_continuity_gates'"
        )
        return cursor.fetchone() is not None

    if name == "010_v3_4_production_queue":
        # 010 adds 2 tables: production_queue, production_queue_events
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN "
            "('production_queue', 'production_queue_events')"
        )
        tables = {row[0] for row in cursor.fetchall()}
        required = {"production_queue", "production_queue_events"}
        return required.issubset(tables)

    if name == "011_v3_6_serial_plan":
        # 011 adds 2 tables: serial_plans, serial_plan_events
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN "
            "('serial_plans', 'serial_plan_events')"
        )
        tables = {row[0] for row in cursor.fetchall()}
        required = {"serial_plans", "serial_plan_events"}
        return required.issubset(tables)

    if name == "012_v4_0_style_bible":
        # 012 adds style_bibles table
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='style_bibles'"
        )
        return cursor.fetchone() is not None

    if name == "013_v4_1_style_gate_evolution":
        # 013 adds style_bible_versions and style_evolution_proposals tables
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN "
            "('style_bible_versions', 'style_evolution_proposals')"
        )
        tables = {row[0] for row in cursor.fetchall()}
        required = {"style_bible_versions", "style_evolution_proposals"}
        return required.issubset(tables)

    if name == "014_v4_2_style_sample_analyzer":
        # 014 adds style_samples table
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='style_samples'"
        )
        return cursor.fetchone() is not None

    if name == "020_v5_2_character_traits":
        # 020 adds traits column to characters table
        cursor = conn.execute("PRAGMA table_info(characters)")
        columns = [row[1] for row in cursor.fetchall()]
        return "traits" in columns

    if name == "021_v5_2_token_tracking":
        # 021 adds token tracking columns to workflow_runs table
        cursor = conn.execute("PRAGMA table_info(workflow_runs)")
        columns = [row[1] for row in cursor.fetchall()]
        required = {"prompt_tokens", "completion_tokens", "total_tokens", "duration_ms"}
        return required.issubset(set(columns))

    if name == "022_v5_3_2_genesis_memory":
        # 022 adds genesis_memories table
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='genesis_memories'"
        )
        return cursor.fetchone() is not None

    if name == "023_v5_3_artifact_run_id":
        # 023 adds workflow_run_id column to agent_artifacts
        cursor = conn.execute("PRAGMA table_info(agent_artifacts)")
        columns = [row[1] for row in cursor.fetchall()]
        return "workflow_run_id" in columns

    if name == "024_v5_3_5_memory_item_error":
        # 024 adds error_message column to memory_update_items
        cursor = conn.execute("PRAGMA table_info(memory_update_items)")
        columns = [row[1] for row in cursor.fetchall()]
        return "error_message" in columns

    return False


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
    migrations_dir = Path(__file__).resolve().parent / "migrations"

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
    for sql_file in sorted(migrations_dir.glob("*.sql")):
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

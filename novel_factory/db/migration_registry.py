"""Declarative migration registry for Novelos (v6.6.9).

Replaces the if/elif chain in connection.py's _is_migration_applied_by_schema()
with a data-driven registry. Each migration entry declares what schema artifacts
it produces (tables, columns, indexes), and the detection logic is generic.

Design goals:
- Zero if/elif per migration — all detection is data-driven
- Each entry is independently testable
- Easy to add new migrations (just append to MIGRATION_REGISTRY)
- Backward compatible with all existing databases
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


# ── Data structures ─────────────────────────────────────────────────


@dataclass(frozen=True)
class SchemaRequirement:
    """A single schema artifact that a migration produces.

    kinds:
      - "table":  the migration creates this table
      - "column": the migration adds this column to a table
      - "index":  the migration creates this index
    """

    kind: str  # "table" | "column" | "index"
    name: str  # table name, or index name
    column: str = ""  # only for kind="column": the column name


@dataclass(frozen=True)
class MigrationEntry:
    """A single migration's declarative registration."""

    migration_id: str  # e.g. "001_add_workflow_tables"
    sql_filename: str  # e.g. "001_add_workflow_tables.sql"
    description: str  # human-readable summary
    requirements: tuple[SchemaRequirement, ...] = ()
    custom_detector: Callable[[sqlite3.Connection], bool] | None = None

    def is_applied(self, conn: sqlite3.Connection) -> bool:
        """Check if this migration's effects are detectable in the schema.

        If a custom_detector is provided, use it exclusively.
        Otherwise, check all declared requirements.
        """
        if self.custom_detector is not None:
            return self.custom_detector(conn)
        return _check_requirements(conn, self.requirements)


# ── Generic requirement checker ─────────────────────────────────────


def _check_requirements(
    conn: sqlite3.Connection,
    requirements: tuple[SchemaRequirement, ...],
) -> bool:
    """Return True if all requirements are present in the schema."""
    if not requirements:
        return False  # no requirements declared → cannot detect → must rely on tracking table

    for req in requirements:
        if req.kind == "table":
            if not _table_exists(conn, req.name):
                return False
        elif req.kind == "column":
            if not _column_exists(conn, req.name, req.column):
                return False
        elif req.kind == "index":
            if not _index_exists(conn, req.name):
                return False
        else:
            return False  # unknown kind
    return True


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def _column_exists(conn: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    try:
        cursor = conn.execute(f"PRAGMA table_info({table_name})")
        columns = {row[1] for row in cursor.fetchall()}
        return column_name in columns
    except Exception:
        return False


def _index_exists(conn: sqlite3.Connection, index_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?",
        (index_name,),
    ).fetchone()
    return row is not None


# ── Registry ────────────────────────────────────────────────────────

# Helper shortcuts
_T = lambda name: SchemaRequirement(kind="table", name=name)
_C = lambda table, col: SchemaRequirement(kind="column", name=table, column=col)
_I = lambda name: SchemaRequirement(kind="index", name=name)

MIGRATION_REGISTRY: list[MigrationEntry] = [
    # ── 000_base_schema (not a file migration, applied from schema/) ──
    MigrationEntry(
        migration_id="000_base_schema",
        sql_filename="000_base_schema.sql",
        description="Base schema — projects, chapters, reviews, etc.",
        requirements=(
            _T("projects"),
            _T("world_settings"),
            _T("characters"),
            _T("factions"),
            _T("chapters"),
            _T("instructions"),
            _T("plot_holes"),
            _T("chapter_plots"),
            _T("reviews"),
            _T("task_status"),
            _T("market_reports"),
            _T("chapter_state"),
            _T("outlines"),
            _T("chapter_versions"),
            _T("state_history"),
            _T("agent_messages"),
            _T("learned_patterns"),
            _T("best_practices"),
            _T("anti_patterns"),
            _T("context_rules"),
        ),
    ),

    # ── 001 ──
    MigrationEntry(
        migration_id="001_add_workflow_tables",
        sql_filename="001_add_workflow_tables.sql",
        description="Workflow tables — scene_beats, polish_reports, workflow_runs, agent_artifacts",
        requirements=(
            _T("scene_beats"),
            _T("polish_reports"),
            _T("workflow_runs"),
            _T("agent_artifacts"),
        ),
    ),

    # ── 002 ──
    MigrationEntry(
        migration_id="002_v1_1_stability",
        sql_filename="002_v1_1_stability.sql",
        description="Stability — content_hash on chapter_versions",
        requirements=(_C("chapter_versions", "content_hash"),),
    ),

    # ── 003 ──
    MigrationEntry(
        migration_id="003_v1_2_quality",
        sql_filename="003_v1_2_quality.sql",
        description="Quality — issue_categories on reviews",
        requirements=(_C("reviews", "issue_categories"),),
    ),

    # ── 004 ──
    MigrationEntry(
        migration_id="004_v1_4_runtime",
        sql_filename="004_v1_4_runtime.sql",
        description="Runtime — revision_target on reviews",
        requirements=(_C("reviews", "revision_target"),),
    ),

    # ── 005 ──
    MigrationEntry(
        migration_id="005_v2_sidecar_agents",
        sql_filename="005_v2_sidecar_agents.sql",
        description="Sidecar agents — scout_reports, reports, continuity_reports, architecture_proposals",
        requirements=(
            _T("scout_reports"),
            _T("reports"),
            _T("continuity_reports"),
            _T("architecture_proposals"),
        ),
    ),

    # ── 006 ──
    MigrationEntry(
        migration_id="006_v2_1_qualityhub_skill",
        sql_filename="006_v2_1_qualityhub_skill.sql",
        description="QualityHub — quality_reports table",
        requirements=(
            _T("quality_reports"),
            _T("skill_runs"),
        ),
    ),

    # ── 007 ──
    MigrationEntry(
        migration_id="007_v3_0_batch_production",
        sql_filename="007_v3_0_batch_production.sql",
        description="Batch production — production_runs, production_run_items, human_review_sessions",
        requirements=(
            _T("production_runs"),
            _T("production_run_items"),
            _T("human_review_sessions"),
        ),
    ),

    # ── 008 ──
    MigrationEntry(
        migration_id="008_v3_2_batch_revision",
        sql_filename="008_v3_2_batch_revision.sql",
        description="Batch revision — batch_revision_runs, batch_revision_items, chapter_review_notes",
        requirements=(
            _T("batch_revision_runs"),
            _T("batch_revision_items"),
            _T("chapter_review_notes"),
        ),
    ),

    # ── 009 ──
    MigrationEntry(
        migration_id="009_v3_3_batch_continuity_gate",
        sql_filename="009_v3_3_batch_continuity_gate.sql",
        description="Continuity gate — batch_continuity_gates",
        requirements=(_T("batch_continuity_gates"),),
    ),

    # ── 010 ──
    MigrationEntry(
        migration_id="010_v3_4_production_queue",
        sql_filename="010_v3_4_production_queue.sql",
        description="Production queue — production_queue, production_queue_events",
        requirements=(
            _T("production_queue"),
            _T("production_queue_events"),
        ),
    ),

    # ── 011 ──
    MigrationEntry(
        migration_id="011_v3_6_serial_plan",
        sql_filename="011_v3_6_serial_plan.sql",
        description="Serial plan — serial_plans, serial_plan_events",
        requirements=(
            _T("serial_plans"),
            _T("serial_plan_events"),
        ),
    ),

    # ── 012 ──
    MigrationEntry(
        migration_id="012_v4_0_style_bible",
        sql_filename="012_v4_0_style_bible.sql",
        description="Style bible — style_bibles table",
        requirements=(_T("style_bibles"),),
    ),

    # ── 013 ──
    MigrationEntry(
        migration_id="013_v4_1_style_gate_evolution",
        sql_filename="013_v4_1_style_gate_evolution.sql",
        description="Style evolution — style_bible_versions, style_evolution_proposals",
        requirements=(
            _T("style_bible_versions"),
            _T("style_evolution_proposals"),
        ),
    ),

    # ── 014 ──
    MigrationEntry(
        migration_id="014_v4_2_style_sample_analyzer",
        sql_filename="014_v4_2_style_sample_analyzer.sql",
        description="Style samples — style_samples table",
        requirements=(_T("style_samples"),),
    ),

    # ── 020 ──
    MigrationEntry(
        migration_id="020_v5_2_character_traits",
        sql_filename="020_v5_2_character_traits.sql",
        description="Character traits — traits column on characters",
        requirements=(_C("characters", "traits"),),
    ),

    # ── 021 ──
    MigrationEntry(
        migration_id="021_v5_2_token_tracking",
        sql_filename="021_v5_2_token_tracking.sql",
        description="Token tracking — prompt_tokens, completion_tokens, total_tokens, duration_ms on workflow_runs",
        requirements=(
            _C("workflow_runs", "prompt_tokens"),
            _C("workflow_runs", "completion_tokens"),
            _C("workflow_runs", "total_tokens"),
            _C("workflow_runs", "duration_ms"),
        ),
    ),

    # ── 022 ──
    MigrationEntry(
        migration_id="022_v5_3_2_genesis_memory",
        sql_filename="022_v5_3_2_genesis_memory.sql",
        description="Genesis & memory — genesis_runs, memory_update_batches, memory_update_items, story_facts, story_fact_events",
        requirements=(
            _T("genesis_runs"),
            _T("memory_update_batches"),
            _T("memory_update_items"),
            _T("story_facts"),
            _T("story_fact_events"),
        ),
        # Note: original detector checked genesis_memories, but the SQL creates genesis_runs.
        # Using genesis_runs as the true indicator.
    ),

    # ── 023 ──
    MigrationEntry(
        migration_id="023_v5_3_artifact_run_id",
        sql_filename="023_v5_3_artifact_run_id.sql",
        description="Artifact run ID — workflow_run_id on agent_artifacts",
        requirements=(_C("agent_artifacts", "workflow_run_id"),),
    ),

    # ── 024 ──
    MigrationEntry(
        migration_id="024_v5_3_5_memory_item_error",
        sql_filename="024_v5_3_5_memory_item_error.sql",
        description="Memory item error — error_message on memory_update_items",
        requirements=(_C("memory_update_items", "error_message"),),
    ),

    # ── 025 ──
    MigrationEntry(
        migration_id="025_v5_3_6_task_status_run_id",
        sql_filename="025_v5_3_6_task_status_run_id.sql",
        description="Task status run ID — workflow_run_id on task_status",
        requirements=(_C("task_status", "workflow_run_id"),),
    ),

    # ── 026 ──
    MigrationEntry(
        migration_id="026_v5_4_13_project_skill_overrides",
        sql_filename="026_v5_4_13_project_skill_overrides.sql",
        description="Skill overrides — project_skill_overrides table",
        requirements=(_T("project_skill_overrides"),),
    ),

    # ── 027 ──
    MigrationEntry(
        migration_id="027_v5_5_8_auto_run_sessions",
        sql_filename="027_v5_5_8_auto_run_sessions.sql",
        description="Auto-run — auto_run_sessions table",
        requirements=(
            _T("auto_run_sessions"),
            _T("auto_run_steps"),
        ),
    ),

    # ── 028 ──
    MigrationEntry(
        migration_id="028_v5_5_9_auto_run_resilience",
        sql_filename="028_v5_5_9_auto_run_resilience.sql",
        description="Auto-run resilience — last_event on auto_run_sessions",
        requirements=(_C("auto_run_sessions", "last_event"),),
    ),

    # ── 029 ──
    MigrationEntry(
        migration_id="029_v5_7_chapter_version_fields",
        sql_filename="029_v5_7_chapter_version_fields.sql",
        description="Chapter version fields — source, base_version_id, summary, metadata on chapter_versions",
        requirements=(
            _C("chapter_versions", "source"),
            _C("chapter_versions", "base_version_id"),
            _C("chapter_versions", "summary"),
            _C("chapter_versions", "metadata"),
        ),
    ),

    # ── 030 ──
    MigrationEntry(
        migration_id="030_v5_8_workflow_node_events",
        sql_filename="030_v5_8_workflow_node_events.sql",
        description="Workflow node events — workflow_node_events table",
        requirements=(_T("workflow_node_events"),),
    ),

    # ── 031 ──
    MigrationEntry(
        migration_id="031_v6_0_agent_memory_and_trace",
        sql_filename="031_v6_0_agent_memory_and_trace.sql",
        description="Agent memory & trace — agent_memories, agent_decision_traces",
        requirements=(
            _T("agent_memories"),
            _T("agent_decision_traces"),
        ),
    ),

    # ── 032 ──
    MigrationEntry(
        migration_id="032_v6_1_workflow_execution_events",
        sql_filename="032_v6_1_workflow_execution_events.sql",
        description="Execution events — workflow_execution_events table",
        requirements=(_T("workflow_execution_events"),),
    ),

    # ── 033 ──
    MigrationEntry(
        migration_id="033_v6_6_19_memory_curator_locks",
        sql_filename="033_v6_6_19_memory_curator_locks.sql",
        description="MemoryCurator locks — one active extraction per project/chapter",
        requirements=(_T("memory_curator_locks"),),
    ),
]


# ── Registry lookup helpers ─────────────────────────────────────────


def _build_registry_index() -> dict[str, MigrationEntry]:
    """Build a lookup dict from migration_id to MigrationEntry."""
    return {entry.migration_id: entry for entry in MIGRATION_REGISTRY}


_REGISTRY_INDEX: dict[str, MigrationEntry] | None = None


def get_registry_index() -> dict[str, MigrationEntry]:
    """Return the migration_id → MigrationEntry index (cached)."""
    global _REGISTRY_INDEX
    if _REGISTRY_INDEX is None:
        _REGISTRY_INDEX = _build_registry_index()
    return _REGISTRY_INDEX


def get_migration_entry(migration_id: str) -> MigrationEntry | None:
    """Look up a migration entry by ID."""
    return get_registry_index().get(migration_id)


def is_migration_applied_by_registry(
    conn: sqlite3.Connection,
    migration_id: str,
) -> bool:
    """Check if a migration is applied using the registry.

    Returns False if the migration_id is not in the registry
    (falls back to tracking table only).
    """
    entry = get_migration_entry(migration_id)
    if entry is None:
        return False
    return entry.is_applied(conn)


def get_migration_sql_files() -> list[Path]:
    """Return sorted list of migration SQL files in the migrations directory."""
    migrations_dir = Path(__file__).resolve().parent / "migrations"
    return sorted(migrations_dir.glob("*.sql"))


# ── Migration health / integrity ────────────────────────────────────


@dataclass
class MigrationHealthStatus:
    """Migration health diagnostic output."""

    total_migrations: int
    applied_migrations: list[str]
    pending_migrations: list[str]
    suspicious_findings: list[str]
    registry_coverage: float  # ratio of SQL files covered by registry


@dataclass
class TableIntegrityCheck:
    """Result of checking a critical table's integrity."""

    table_name: str
    exists: bool
    missing_columns: list[str] = field(default_factory=list)
    row_count: int = -1  # -1 means table doesn't exist or query failed


# Critical tables and their required columns for integrity checks
CRITICAL_TABLE_COLUMNS: dict[str, list[str]] = {
    "projects": ["project_id", "name", "status"],
    "chapters": ["project_id", "chapter_number", "title", "status"],
    "workflow_runs": ["id", "project_id", "status"],
    "agent_artifacts": ["id", "project_id", "agent_id", "artifact_type"],
    "memory_update_batches": ["id", "project_id", "status"],
    "memory_curator_locks": ["project_id", "chapter_number", "status"],
    "story_facts": ["id", "project_id", "fact_key", "fact_type"],
}


def check_migration_health(conn: sqlite3.Connection) -> MigrationHealthStatus:
    """Return migration health status for the given database connection.

    Read-only: does not modify the database.
    Does not expose user content, API keys, or tokens.
    """
    # Ensure tracking table exists (read-only check)
    tracking_exists = _table_exists(conn, "_migrations_applied")

    # Get applied migrations from tracking table
    applied_from_tracking: set[str] = set()
    if tracking_exists:
        rows = conn.execute("SELECT name FROM _migrations_applied").fetchall()
        applied_from_tracking = {row[0] for row in rows}

    # Check each registry entry
    applied: list[str] = []
    pending: list[str] = []
    suspicious: list[str] = []

    for entry in MIGRATION_REGISTRY:
        in_tracking = entry.migration_id in applied_from_tracking
        in_schema = entry.is_applied(conn)

        if in_tracking and in_schema:
            applied.append(entry.migration_id)
        elif in_tracking and not in_schema:
            # Tracked as applied but schema evidence missing
            suspicious.append(
                f"{entry.migration_id}: tracked as applied but schema evidence missing"
            )
            applied.append(entry.migration_id)  # still count as applied (tracking is truth)
        elif not in_tracking and in_schema:
            # Schema evidence exists but not tracked — should be recorded
            suspicious.append(
                f"{entry.migration_id}: schema evidence present but not tracked"
            )
            applied.append(entry.migration_id)  # count as applied (schema is truth)
        else:
            pending.append(entry.migration_id)

    # Check registry coverage against actual SQL files
    sql_files = get_migration_sql_files()
    sql_stems = {f.stem for f in sql_files}
    registry_ids = {e.migration_id for e in MIGRATION_REGISTRY if e.migration_id != "000_base_schema"}
    uncovered = sql_stems - registry_ids
    if uncovered:
        suspicious.append(f"SQL files not in registry: {sorted(uncovered)}")

    coverage = len(registry_ids & sql_stems) / len(sql_stems) if sql_stems else 1.0

    return MigrationHealthStatus(
        total_migrations=len(MIGRATION_REGISTRY),
        applied_migrations=applied,
        pending_migrations=pending,
        suspicious_findings=suspicious,
        registry_coverage=coverage,
    )


def check_table_integrity(conn: sqlite3.Connection) -> list[TableIntegrityCheck]:
    """Check integrity of critical tables.

    Read-only: does not modify data.
    Returns clear diagnostics for missing tables or columns.
    """
    results: list[TableIntegrityCheck] = []

    for table_name, required_cols in CRITICAL_TABLE_COLUMNS.items():
        if not _table_exists(conn, table_name):
            results.append(TableIntegrityCheck(
                table_name=table_name,
                exists=False,
                missing_columns=required_cols,
                row_count=-1,
            ))
            continue

        # Check columns
        cursor = conn.execute(f"PRAGMA table_info({table_name})")
        existing_cols = {row[1] for row in cursor.fetchall()}
        missing = [col for col in required_cols if col not in existing_cols]

        # Get row count
        try:
            count = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
        except Exception:
            count = -1

        results.append(TableIntegrityCheck(
            table_name=table_name,
            exists=True,
            missing_columns=missing,
            row_count=count,
        ))

    return results

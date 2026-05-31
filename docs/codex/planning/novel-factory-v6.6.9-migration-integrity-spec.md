# v6.6.9 Database Migration & Persistence Integrity Closure — Spec

## Problem

The migration detection system in `novel_factory/db/connection.py` relies on a long `if/elif` chain in `_is_migration_applied_by_schema()`. As of v6.6.8, this function contains 30+ hardcoded branches, each with inline SQL queries. This creates several risks:

1. **Fragile**: Adding a new migration requires modifying `connection.py` and adding another `if` branch — easy to forget or get wrong.
2. **Untestable in isolation**: Individual migration detectors cannot be unit-tested independently.
3. **Silent failures**: If a migration SQL file exists but has no corresponding `if` branch, `init_db` on a pre-tracking database will re-execute it, potentially causing `ALTER TABLE` errors.
4. **No health visibility**: There is no way to inspect migration status — whether migrations are tracked, whether schema and tracking agree, whether any critical tables are missing columns.
5. **Bug in 022 detection**: The original detector checked `genesis_memories` (from migration 031) instead of `genesis_runs` (the actual table created by migration 022).

## Goals

1. **Declarative migration registry** — replace the `if/elif` chain with a data-driven registry where each migration declares its schema requirements.
2. **Backward compatibility** — all existing databases continue to work; `init_db` remains idempotent.
3. **Migration health / integrity output** — provide read-only diagnostic functions.
4. **Table integrity checks** — lightweight self-checks for critical tables.
5. **Comprehensive test coverage** — every registry entry and health function is tested.

## Design

### Migration Registry (`novel_factory/db/migration_registry.py`)

New module with:

- `SchemaRequirement` — a single schema artifact (table, column, or index)
- `MigrationEntry` — a migration's ID, SQL filename, description, and requirements
- `MIGRATION_REGISTRY` — the authoritative list of all migrations
- `is_migration_applied_by_registry()` — generic detection using declared requirements
- `check_migration_health()` — returns `MigrationHealthStatus`
- `check_table_integrity()` — returns `list[TableIntegrityCheck]`

Each `MigrationEntry` declares what it creates:

```python
MigrationEntry(
    migration_id="001_add_workflow_tables",
    sql_filename="001_add_workflow_tables.sql",
    description="Workflow tables — scene_beats, polish_reports, workflow_runs, agent_artifacts",
    requirements=(_T("workflow_runs"),),
)
```

Detection is generic: check if all declared requirements exist in the schema. No migration-specific `if/elif` needed.

### Refactored `connection.py`

- `_is_migration_applied_by_schema()` now delegates to `is_migration_applied_by_registry()`
- `init_db()` uses `get_migration_sql_files()` from registry
- Exports `check_migration_health`, `check_table_integrity`, `MigrationHealthStatus`, `TableIntegrityCheck` for API/CLI integration

### Health Output

`MigrationHealthStatus`:
- `total_migrations: int`
- `applied_migrations: list[str]`
- `pending_migrations: list[str]`
- `suspicious_findings: list[str]` — tracking/schema mismatches, uncovered SQL files
- `registry_coverage: float` — ratio of SQL files covered by registry

`TableIntegrityCheck`:
- `table_name: str`
- `exists: bool`
- `missing_columns: list[str]`
- `row_count: int` — -1 if table doesn't exist

### Critical Tables

| Table | Required Columns |
|-------|-----------------|
| `projects` | `project_id`, `name`, `status` |
| `chapters` | `project_id`, `chapter_number`, `title`, `status` |
| `workflow_runs` | `id`, `project_id`, `status` |
| `agent_artifacts` | `id`, `project_id`, `agent_id`, `artifact_type` |
| `memory_update_batches` | `id`, `project_id`, `status` |
| `story_facts` | `id`, `project_id`, `fact_key`, `fact_type` |

## Bug Fix

Migration 022's detector was checking `genesis_memories` (a table from migration 031) instead of `genesis_runs` (the actual table it creates). This meant:
- On a database where only 022 was applied (not 031), the schema check would fail, causing re-execution.
- On a database where 031 was applied but 022 wasn't, the schema check would incorrectly report 022 as applied.

The registry now correctly requires `genesis_runs`.

## Constraints

- No LangGraph topology changes
- No Agent business semantics changes
- No Repository rewrites
- No new database frameworks
- No destructive migrations
- All new checks are read-only or idempotent
- Python 3.9 compatible

## Verification

- `python3 -m pytest tests/test_v669_migration_integrity.py -q` — 73 tests
- `python3 -m pytest -q` — 2433 passed
- `cd frontend && npm run typecheck && npm run lint && npm run build` — all pass
- `git diff --check` — clean

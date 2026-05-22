# v6.6.9 Database Migration & Persistence Integrity Closure — Completion Report

## Summary

Replaced the 30+ branch `if/elif` migration detection chain in `connection.py` with a declarative migration registry. Added migration health and table integrity diagnostic functions. Fixed a detection bug in migration 022.

## Changes

### New Files

- **`novel_factory/db/migration_registry.py`** — Declarative migration registry with:
  - `SchemaRequirement` / `MigrationEntry` dataclasses
  - `MIGRATION_REGISTRY` — 28 entries covering all migrations (000–032)
  - `is_migration_applied_by_registry()` — generic schema detection
  - `check_migration_health()` — returns `MigrationHealthStatus`
  - `check_table_integrity()` — returns `list[TableIntegrityCheck]`
  - `CRITICAL_TABLE_COLUMNS` — 6 tables with required column definitions

- **`tests/test_v669_migration_integrity.py`** — 73 tests covering:
  - Empty DB init_db → all migrations applied
  - Old schema detection accuracy
  - Missing column/table detection
  - Registry coverage of all SQL files
  - init_db idempotency
  - Migration health output structure and safety
  - Table integrity checks
  - No if/elif branches in connection.py
  - Backward compatibility
  - Specific migration detection accuracy (parametrized)
  - Partial migration health
  - Connection module exports

### Modified Files

- **`novel_factory/db/connection.py`** — Refactored:
  - `_is_migration_applied_by_schema()` now delegates to registry
  - `init_db()` uses `get_migration_sql_files()` from registry
  - Exports health/integrity functions and dataclasses
  - Removed 30+ `if name ==` branches

- **`novel_factory/version.py`** — `6.6.8` → `6.6.9`
- **`frontend/package.json`** — version synced to `6.6.9`
- **`AGENTS.md`** — Updated baseline, test count, architecture description
- **`docs/codex/README.md`** — Added v6.6.9 baseline entry, updated test count

### Bug Fix

Migration 022 (`022_v5_3_2_genesis_memory`) was checking for `genesis_memories` table (created by migration 031) instead of `genesis_runs` (the actual table it creates). The registry now correctly requires `genesis_runs`.

## Migration Detection: Before vs After

### Before (connection.py)
```python
def _is_migration_applied_by_schema(conn, name):
    if name == "000_base_schema":
        cursor = conn.execute("SELECT name FROM sqlite_master ...")
        return cursor.fetchone() is not None
    if name == "001_add_workflow_tables":
        cursor = conn.execute("SELECT name FROM sqlite_master ...")
        return cursor.fetchone() is not None
    # ... 28 more if/elif branches
    return False
```

### After (migration_registry.py + connection.py)
```python
# In migration_registry.py:
MIGRATION_REGISTRY = [
    MigrationEntry(
        migration_id="001_add_workflow_tables",
        requirements=(_T("workflow_runs"),),
    ),
    # ...
]

# In connection.py:
def _is_migration_applied_by_schema(conn, name):
    return is_migration_applied_by_registry(conn, name)
```

Adding a new migration: append one `MigrationEntry` to `MIGRATION_REGISTRY`. No changes to `connection.py`.

## Integrity Health Output

### MigrationHealthStatus
```python
MigrationHealthStatus(
    total_migrations=28,
    applied_migrations=["000_base_schema", "001_add_workflow_tables", ...],
    pending_migrations=[],
    suspicious_findings=[],
    registry_coverage=1.0,
)
```

### TableIntegrityCheck
```python
TableIntegrityCheck(
    table_name="projects",
    exists=True,
    missing_columns=[],
    row_count=0,
)
```

## Verification Results

| Check | Result |
|-------|--------|
| `test_v669_migration_integrity.py` | **73 passed** |
| `test_v666/667/668` (adjacent versions) | **86 passed** |
| `test_init_db_idempotency.py` | **14 passed** |
| Backend full suite | **2433 passed** |
| Frontend typecheck | ✅ |
| Frontend lint | ✅ |
| Frontend build | ✅ |
| `git diff --check` | ✅ |

## Old Database Compatibility

- **Pre-tracking databases**: Schema detection via registry correctly identifies applied migrations and records them in `_migrations_applied`
- **Empty databases**: `init_db` creates all tables from scratch
- **Partially migrated databases**: Pending migrations are correctly identified and applied
- **Idempotent**: `init_db` can be called any number of times safely

## Unresolved Risks

None identified. The refactoring is backward compatible and all existing tests pass.

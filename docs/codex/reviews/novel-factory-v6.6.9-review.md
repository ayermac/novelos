# v6.6.9 Database Migration & Persistence Integrity Closure — Review

## Scope

- Refactor `_is_migration_applied_by_schema()` from 30+ `if/elif` branches to declarative registry
- Add migration health and table integrity diagnostic functions
- Fix migration 022 detection bug
- Add comprehensive test coverage

## Findings

### P0 — None

### P1 — None

### P2 — Fixed During Review

1. **Migration 022 detection bug** — The original `_is_migration_applied_by_schema()` checked for `genesis_memories` table (created by migration 031) instead of `genesis_runs` (the actual table created by migration 022). This could cause false negatives (re-executing migration 022 on pre-tracking databases) or false positives (skipping migration 022 if 031 was applied). **Fixed**: Registry entry now requires `genesis_runs`.

2. **Sensitive pattern false positive in test** — Initial test for "no sensitive data in health output" used `token` as a sensitive pattern, which matched the migration ID `021_v5_2_token_tracking`. **Fixed**: Replaced with more specific patterns (`sk-`, `password=`, `secret=`, `OPENAI_API_KEY`, `Bearer `) that indicate actual leaked secrets.

### Advisory

1. **Registry coverage metric** — The `registry_coverage` field in `MigrationHealthStatus` measures how many SQL files in `migrations/` have a corresponding registry entry. This is a good safety net for catching forgotten registrations when adding new migrations.

2. **Custom detector support** — `MigrationEntry` supports a `custom_detector` field for migrations that need detection logic beyond simple table/column/index checks. Currently unused, but available for future complex migrations.

3. **Health API integration** — The health and integrity functions are importable from `connection.py` and can be wired into the existing `/health` endpoint or CLI without further refactoring.

## Verification

- All 73 new tests pass
- All 2433 backend tests pass
- Frontend typecheck/lint/build pass
- `git diff --check` clean
- Existing `test_init_db_idempotency.py` still passes (14 tests)

## Decision

**PASS** — Ready for commit.

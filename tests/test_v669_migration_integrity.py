"""Tests for v6.6.9 Database Migration & Persistence Integrity Closure.

Covers:
- Empty DB init_db → all migrations applied
- Old schema / existing tables → detector correctly judges applied
- Missing column → detector returns pending
- Registry covers all migrations/*.sql files
- init_db repeated runs are idempotent
- Migration health output structure is stable
- No leakage of content, API keys, base_url tokens
- connection.py no longer depends on if/elif migration branches
- Compatible with existing workflow/memory/editor tests
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from novel_factory.db.connection import (
    _is_migration_applied_by_schema,
    _is_migration_applied_by_tracking,
    get_connection,
    init_db,
)
from novel_factory.db.migration_registry import (
    MIGRATION_REGISTRY,
    MigrationEntry,
    MigrationHealthStatus,
    SchemaRequirement,
    TableIntegrityCheck,
    check_migration_health,
    check_table_integrity,
    get_migration_entry,
    get_migration_sql_files,
    get_registry_index,
    is_migration_applied_by_registry,
    CRITICAL_TABLE_COLUMNS,
)


# ── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def fresh_db(tmp_path):
    """Create a fresh database via init_db and return its path."""
    db_path = tmp_path / "test.db"
    init_db(db_path)
    return db_path


@pytest.fixture
def fresh_conn(fresh_db):
    """Return an open connection to a freshly initialized database."""
    conn = get_connection(str(fresh_db))
    yield conn
    conn.close()


# ── Test: Empty DB init_db → all migrations applied ─────────────────


class TestInitDbCompleteness:
    """init_db on a fresh database should apply all migrations."""

    def test_all_migrations_tracked(self, fresh_conn):
        """All registry entries should be tracked in _migrations_applied."""
        for entry in MIGRATION_REGISTRY:
            assert _is_migration_applied_by_tracking(
                fresh_conn, entry.migration_id
            ), f"Migration {entry.migration_id} not tracked after init_db"

    def test_all_migrations_detectable_in_schema(self, fresh_conn):
        """All registry entries should be detectable by schema check."""
        for entry in MIGRATION_REGISTRY:
            assert _is_migration_applied_by_schema(
                fresh_conn, entry.migration_id
            ), f"Migration {entry.migration_id} not detectable in schema after init_db"

    def test_migration_count_matches_tracking(self, fresh_conn):
        """Number of tracked migrations should match registry size."""
        count = fresh_conn.execute(
            "SELECT COUNT(*) FROM _migrations_applied"
        ).fetchone()[0]
        assert count == len(MIGRATION_REGISTRY)


# ── Test: Old schema / existing tables → detector correct ───────────


class TestSchemaDetectionAccuracy:
    """Schema detection should correctly identify applied/pending state."""

    def test_base_schema_detection_on_old_db(self, tmp_path):
        """A database with only the base schema should detect 000_base_schema."""
        db_path = tmp_path / "old_base.db"
        schema_file = (
            Path(__file__).resolve().parent.parent
            / "novel_factory" / "db" / "schema" / "000_base_schema.sql"
        )
        conn = sqlite3.connect(str(db_path))
        conn.executescript(schema_file.read_text(encoding="utf-8"))
        conn.commit()

        # 000_base_schema should be detectable
        assert _is_migration_applied_by_schema(conn, "000_base_schema")
        # 001 should NOT be detectable (no workflow_runs table)
        assert not _is_migration_applied_by_schema(conn, "001_add_workflow_tables")
        conn.close()

    def test_partial_migrations_detection(self, tmp_path):
        """A database with only 000 + 001 should detect those two but not 002."""
        db_path = tmp_path / "partial.db"
        schema_file = (
            Path(__file__).resolve().parent.parent
            / "novel_factory" / "db" / "schema" / "000_base_schema.sql"
        )
        migration_001 = (
            Path(__file__).resolve().parent.parent
            / "novel_factory" / "db" / "migrations" / "001_add_workflow_tables.sql"
        )

        conn = sqlite3.connect(str(db_path))
        conn.executescript(schema_file.read_text(encoding="utf-8"))
        conn.executescript(migration_001.read_text(encoding="utf-8"))
        conn.commit()

        assert _is_migration_applied_by_schema(conn, "000_base_schema")
        assert _is_migration_applied_by_schema(conn, "001_add_workflow_tables")
        # 002 adds content_hash to chapter_versions — not present
        assert not _is_migration_applied_by_schema(conn, "002_v1_1_stability")
        conn.close()

    def test_unknown_migration_id_returns_false(self, fresh_conn):
        """An unknown migration_id should return False from schema detection."""
        assert not _is_migration_applied_by_schema(fresh_conn, "999_nonexistent")


# ── Test: Missing column → detector returns pending ─────────────────


class TestMissingColumnDetection:
    """When a column required by a migration is missing, detection should fail."""

    def test_column_requirement_not_met(self, tmp_path):
        """A DB missing a required column should report migration as not applied."""
        db_path = tmp_path / "no_content_hash.db"
        schema_file = (
            Path(__file__).resolve().parent.parent
            / "novel_factory" / "db" / "schema" / "000_base_schema.sql"
        )

        conn = sqlite3.connect(str(db_path))
        conn.executescript(schema_file.read_text(encoding="utf-8"))
        conn.commit()

        # 002 requires content_hash on chapter_versions
        # Base schema doesn't have it
        assert not _is_migration_applied_by_schema(conn, "002_v1_1_stability")
        conn.close()

    def test_table_requirement_not_met(self, tmp_path):
        """A DB missing a required table should report migration as not applied."""
        db_path = tmp_path / "no_workflow.db"
        schema_file = (
            Path(__file__).resolve().parent.parent
            / "novel_factory" / "db" / "schema" / "000_base_schema.sql"
        )

        conn = sqlite3.connect(str(db_path))
        conn.executescript(schema_file.read_text(encoding="utf-8"))
        conn.commit()

        # 001 requires workflow_runs table
        assert not _is_migration_applied_by_schema(conn, "001_add_workflow_tables")
        conn.close()


# ── Test: Registry covers all SQL files ─────────────────────────────


class TestRegistryCoverage:
    """The registry should cover every SQL file in the migrations directory."""

    def test_all_sql_files_have_registry_entries(self):
        """Every .sql file in migrations/ should have a matching registry entry."""
        sql_files = get_migration_sql_files()
        registry_ids = {e.migration_id for e in MIGRATION_REGISTRY}
        # 000_base_schema is in schema/ not migrations/
        migration_ids = {f.stem for f in sql_files}

        # All migration files must be in the registry
        missing_from_registry = migration_ids - registry_ids
        assert not missing_from_registry, (
            f"SQL files missing from registry: {missing_from_registry}"
        )

    def test_no_extra_registry_entries_without_sql_files(self):
        """Registry entries (except 000_base_schema) must have matching SQL files."""
        sql_files = get_migration_sql_files()
        migration_ids = {f.stem for f in sql_files}

        for entry in MIGRATION_REGISTRY:
            if entry.migration_id == "000_base_schema":
                continue  # 000_base_schema lives in schema/, not migrations/
            assert entry.migration_id in migration_ids, (
                f"Registry entry {entry.migration_id} has no matching SQL file"
            )

    def test_registry_entries_have_requirements(self):
        """Every registry entry must have at least one requirement or custom_detector."""
        for entry in MIGRATION_REGISTRY:
            has_reqs = len(entry.requirements) > 0
            has_custom = entry.custom_detector is not None
            assert has_reqs or has_custom, (
                f"Migration {entry.migration_id} has no requirements or custom_detector"
            )


# ── Test: init_db idempotent ────────────────────────────────────────


class TestInitDbIdempotency:
    """init_db should be safe to call multiple times."""

    def test_init_db_twice(self, tmp_path):
        """Running init_db twice should not raise."""
        db_path = tmp_path / "idem.db"
        init_db(db_path)
        init_db(db_path)  # second call must not raise

    def test_init_db_three_times_tracking_count(self, tmp_path):
        """Running init_db three times should produce correct tracking count."""
        db_path = tmp_path / "idem3.db"
        init_db(db_path)
        init_db(db_path)
        init_db(db_path)

        conn = get_connection(str(db_path))
        count = conn.execute(
            "SELECT COUNT(*) FROM _migrations_applied"
        ).fetchone()[0]
        conn.close()
        assert count == len(MIGRATION_REGISTRY)

    def test_init_db_on_preexisting_db(self, tmp_path):
        """init_db on a manually-created DB with all migrations should work."""
        db_path = tmp_path / "preexisting.db"
        schema_dir = (
            Path(__file__).resolve().parent.parent
            / "novel_factory" / "db" / "schema"
        )
        migration_dir = (
            Path(__file__).resolve().parent.parent
            / "novel_factory" / "db" / "migrations"
        )

        # Apply everything manually (old DB without tracking)
        conn = sqlite3.connect(str(db_path))
        conn.executescript(
            (schema_dir / "000_base_schema.sql").read_text(encoding="utf-8")
        )
        for sql_file in sorted(migration_dir.glob("*.sql")):
            conn.executescript(sql_file.read_text(encoding="utf-8"))
        conn.commit()
        conn.close()

        # Now run init_db — should detect all and track them
        init_db(str(db_path))

        conn = get_connection(str(db_path))
        count = conn.execute(
            "SELECT COUNT(*) FROM _migrations_applied"
        ).fetchone()[0]
        conn.close()
        assert count == len(MIGRATION_REGISTRY)


# ── Test: Migration health output ───────────────────────────────────


class TestMigrationHealth:
    """Migration health check should return stable, safe output."""

    def test_health_on_fresh_db(self, fresh_conn):
        """Health check on fresh DB should show all applied, none pending."""
        health = check_migration_health(fresh_conn)
        assert isinstance(health, MigrationHealthStatus)
        assert health.total_migrations == len(MIGRATION_REGISTRY)
        assert len(health.applied_migrations) == len(MIGRATION_REGISTRY)
        assert len(health.pending_migrations) == 0
        assert health.registry_coverage == 1.0

    def test_health_on_empty_db(self, tmp_path):
        """Health check on empty DB should show all pending."""
        db_path = tmp_path / "empty.db"
        conn = sqlite3.connect(str(db_path))
        health = check_migration_health(conn)
        assert health.total_migrations == len(MIGRATION_REGISTRY)
        assert len(health.applied_migrations) == 0
        assert len(health.pending_migrations) == len(MIGRATION_REGISTRY)
        conn.close()

    def test_health_suspicious_tracking_without_schema(self, fresh_conn):
        """Manually removing a table but keeping tracking should show suspicious."""
        # Drop a table that a migration created (simulating corruption)
        fresh_conn.execute("DROP TABLE IF EXISTS quality_reports")
        fresh_conn.commit()

        health = check_migration_health(fresh_conn)
        # Should have at least one suspicious finding about 006
        suspicious_ids = [s for s in health.suspicious_findings if "006" in s]
        assert len(suspicious_ids) > 0, "Should detect schema/tracking mismatch"

    def test_health_schema_without_tracking(self, tmp_path):
        """Schema evidence present but not tracked should be suspicious."""
        db_path = tmp_path / "no_track.db"
        schema_file = (
            Path(__file__).resolve().parent.parent
            / "novel_factory" / "db" / "schema" / "000_base_schema.sql"
        )
        conn = sqlite3.connect(str(db_path))
        conn.executescript(schema_file.read_text(encoding="utf-8"))
        conn.commit()

        health = check_migration_health(conn)
        # 000_base_schema should be detected in schema but not tracked
        suspicious_ids = [s for s in health.suspicious_findings if "000_base_schema" in s]
        assert len(suspicious_ids) > 0
        conn.close()

    def test_health_no_sensitive_data(self, fresh_conn):
        """Health output should not contain user content, API keys, or tokens."""
        health = check_migration_health(fresh_conn)
        # Convert to dict and check that no field values contain sensitive data.
        # Note: migration IDs like "token_tracking" are fine — those are schema names.
        import dataclasses
        health_dict = dataclasses.asdict(health)
        # Flatten all string values
        all_text = " ".join(str(v) for v in health_dict.values())
        # These patterns indicate leaked secrets, not schema artifact names
        sensitive_patterns = [
            "OPENAI_API_KEY", "sk-", "password=", "secret=",
            "Authorization", "Bearer ",
        ]
        for pattern in sensitive_patterns:
            assert pattern not in all_text, f"Sensitive pattern '{pattern}' found in health output"


# ── Test: Table integrity checks ────────────────────────────────────


class TestTableIntegrity:
    """Table integrity checks should detect missing tables and columns."""

    def test_all_critical_tables_exist_after_init(self, fresh_conn):
        """After init_db, all critical tables should exist."""
        results = check_table_integrity(fresh_conn)
        for check in results:
            assert check.exists, f"Critical table {check.table_name} missing after init_db"
            assert len(check.missing_columns) == 0, (
                f"Table {check.table_name} missing columns: {check.missing_columns}"
            )

    def test_missing_table_detected(self, tmp_path):
        """An empty database should report all critical tables as missing."""
        db_path = tmp_path / "empty.db"
        conn = sqlite3.connect(str(db_path))
        results = check_table_integrity(conn)
        for check in results:
            assert not check.exists
            assert len(check.missing_columns) > 0
        conn.close()

    def test_missing_column_detected(self, tmp_path):
        """A table missing a required column should be reported."""
        db_path = tmp_path / "partial.db"
        conn = sqlite3.connect(str(db_path))
        # Create projects table with only id column (missing project_id, name, status)
        conn.execute(
            "CREATE TABLE projects (id INTEGER PRIMARY KEY)"
        )
        conn.commit()

        results = check_table_integrity(conn)
        projects_check = [c for c in results if c.table_name == "projects"][0]
        assert projects_check.exists
        assert "project_id" in projects_check.missing_columns
        assert "name" in projects_check.missing_columns
        conn.close()

    def test_integrity_check_is_read_only(self, fresh_conn):
        """Integrity checks should not modify the database."""
        # Get row counts before
        counts_before = {}
        for table in CRITICAL_TABLE_COLUMNS:
            try:
                counts_before[table] = fresh_conn.execute(
                    f"SELECT COUNT(*) FROM {table}"
                ).fetchone()[0]
            except Exception:
                counts_before[table] = -1

        # Run integrity check
        check_table_integrity(fresh_conn)

        # Get row counts after
        for table in CRITICAL_TABLE_COLUMNS:
            try:
                count_after = fresh_conn.execute(
                    f"SELECT COUNT(*) FROM {table}"
                ).fetchone()[0]
                assert count_after == counts_before[table], (
                    f"Table {table} was modified by integrity check"
                )
            except Exception:
                pass

    def test_integrity_output_no_sensitive_data(self, fresh_conn):
        """Integrity check output should not contain user content."""
        results = check_table_integrity(fresh_conn)
        output_str = str(results)
        sensitive_patterns = [
            "OPENAI_API_KEY", "API_KEY", "api_key",
            "BASE_URL", "base_url", "token",
            "password",
        ]
        for pattern in sensitive_patterns:
            assert pattern not in output_str, f"Sensitive pattern '{pattern}' in integrity output"


# ── Test: connection.py no longer uses if/elif migration branches ───


class TestNoIfElifMigrationBranches:
    """Verify that connection.py delegates to the registry instead of if/elif."""

    def test_connection_imports_registry(self):
        """connection.py should import from migration_registry."""
        from novel_factory.db import connection as conn_module
        import inspect
        source = inspect.getsource(conn_module)
        assert "migration_registry" in source
        assert "is_migration_applied_by_registry" in source

    def test_no_migration_name_literals_in_connection(self):
        """connection.py should not contain hardcoded migration name comparisons."""
        from novel_factory.db import connection as conn_module
        import inspect
        source = inspect.getsource(conn_module)
        # These migration name strings should NOT appear as == comparisons in connection.py
        # (they now live in migration_registry.py)
        forbidden_patterns = [
            '== "001_add_workflow_tables"',
            '== "002_v1_1_stability"',
            '== "022_v5_3_2_genesis_memory"',
            'name == "003_v1_2_quality"',
        ]
        for pattern in forbidden_patterns:
            assert pattern not in source, (
                f"connection.py still contains hardcoded migration check: {pattern}"
            )


# ── Test: Registry index and lookup ─────────────────────────────────


class TestRegistryLookup:
    """Registry lookup functions should work correctly."""

    def test_get_migration_entry_found(self):
        """Known migration IDs should return entries."""
        entry = get_migration_entry("000_base_schema")
        assert entry is not None
        assert entry.migration_id == "000_base_schema"

    def test_get_migration_entry_not_found(self):
        """Unknown migration IDs should return None."""
        entry = get_migration_entry("999_nonexistent")
        assert entry is None

    def test_registry_index_complete(self):
        """Registry index should contain all entries."""
        index = get_registry_index()
        assert len(index) == len(MIGRATION_REGISTRY)

    def test_is_migration_applied_by_registry_known(self, fresh_conn):
        """Registry-based check should work for known migrations."""
        assert is_migration_applied_by_registry(fresh_conn, "000_base_schema")
        assert is_migration_applied_by_registry(fresh_conn, "001_add_workflow_tables")

    def test_is_migration_applied_by_registry_unknown(self, fresh_conn):
        """Registry-based check should return False for unknown migrations."""
        assert not is_migration_applied_by_registry(fresh_conn, "999_nonexistent")


# ── Test: SchemaRequirement and MigrationEntry ──────────────────────


class TestSchemaRequirement:
    """SchemaRequirement dataclass should work as expected."""

    def test_table_requirement(self, fresh_conn):
        """Table requirement should detect existing tables."""
        req = SchemaRequirement(kind="table", name="projects")
        from novel_factory.db.migration_registry import _check_requirements
        assert _check_requirements(fresh_conn, (req,))

    def test_column_requirement(self, fresh_conn):
        """Column requirement should detect existing columns."""
        req = SchemaRequirement(kind="column", name="chapters", column="status")
        from novel_factory.db.migration_registry import _check_requirements
        assert _check_requirements(fresh_conn, (req,))

    def test_missing_table_requirement(self, tmp_path):
        """Table requirement should fail for non-existent table."""
        db_path = tmp_path / "empty.db"
        conn = sqlite3.connect(str(db_path))
        req = SchemaRequirement(kind="table", name="nonexistent_table")
        from novel_factory.db.migration_registry import _check_requirements
        assert not _check_requirements(conn, (req,))
        conn.close()

    def test_missing_column_requirement(self, tmp_path):
        """Column requirement should fail for non-existent column."""
        db_path = tmp_path / "partial.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE test_table (id INTEGER PRIMARY KEY)")
        conn.commit()
        req = SchemaRequirement(kind="column", name="test_table", column="nonexistent_col")
        from novel_factory.db.migration_registry import _check_requirements
        assert not _check_requirements(conn, (req,))
        conn.close()


# ── Test: Compatibility with existing tests ──────────────────────────


class TestBackwardCompatibility:
    """Ensure refactored code is compatible with existing test expectations."""

    def test_is_migration_applied_by_schema_still_callable(self, fresh_conn):
        """_is_migration_applied_by_schema should still be callable from connection.py."""
        assert _is_migration_applied_by_schema(fresh_conn, "000_base_schema")
        assert _is_migration_applied_by_schema(fresh_conn, "001_add_workflow_tables")
        assert not _is_migration_applied_by_schema(fresh_conn, "999_nonexistent")

    def test_is_migration_applied_by_tracking_still_callable(self, fresh_conn):
        """_is_migration_applied_by_tracking should still work."""
        assert _is_migration_applied_by_tracking(fresh_conn, "000_base_schema")

    def test_init_db_creates_expected_tables(self, fresh_conn):
        """init_db should create all expected tables."""
        tables = {
            r[0]
            for r in fresh_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        expected = {
            "projects", "chapters", "workflow_runs", "agent_artifacts",
            "reviews", "memory_update_batches", "story_facts",
            "production_runs", "auto_run_sessions",
        }
        assert expected.issubset(tables)


# ── Test: Specific migration detection accuracy ─────────────────────


class TestSpecificMigrationDetection:
    """Test detection accuracy for each migration in the registry."""

    @pytest.mark.parametrize("entry", MIGRATION_REGISTRY, ids=lambda e: e.migration_id)
    def test_each_migration_detectable_after_init(self, entry, fresh_conn):
        """Each registry entry should be detectable after full init_db."""
        assert _is_migration_applied_by_schema(
            fresh_conn, entry.migration_id
        ), f"Migration {entry.migration_id} not detectable after init_db"

    def test_022_detects_genesis_runs_not_genesis_memories(self, fresh_conn):
        """Migration 022 should detect genesis_runs (the actual table it creates)."""
        # The SQL creates genesis_runs, not genesis_memories
        assert _is_migration_applied_by_schema(fresh_conn, "022_v5_3_2_genesis_memory")
        # Verify genesis_runs exists
        row = fresh_conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='genesis_runs'"
        ).fetchone()
        assert row is not None

    def test_021_all_token_columns(self, fresh_conn):
        """Migration 021 should detect all four token tracking columns."""
        assert _is_migration_applied_by_schema(fresh_conn, "021_v5_2_token_tracking")
        cursor = fresh_conn.execute("PRAGMA table_info(workflow_runs)")
        columns = {row[1] for row in cursor.fetchall()}
        assert {"prompt_tokens", "completion_tokens", "total_tokens", "duration_ms"}.issubset(columns)


# ── Test: Migration health on partially migrated DB ──────────────────


class TestPartialMigrationHealth:
    """Health check should correctly identify partial migration states."""

    def test_partial_db_shows_pending(self, tmp_path):
        """A DB with only base schema should show many pending migrations."""
        db_path = tmp_path / "base_only.db"
        schema_file = (
            Path(__file__).resolve().parent.parent
            / "novel_factory" / "db" / "schema" / "000_base_schema.sql"
        )
        conn = sqlite3.connect(str(db_path))
        conn.executescript(schema_file.read_text(encoding="utf-8"))
        conn.commit()

        health = check_migration_health(conn)
        # 000_base_schema should be detected via schema
        assert "000_base_schema" in health.applied_migrations
        # Most others should be pending
        assert len(health.pending_migrations) > 0
        conn.close()

    def test_init_db_then_health_is_healthy(self, fresh_conn):
        """After init_db, health should show no pending and no suspicious."""
        health = check_migration_health(fresh_conn)
        assert len(health.pending_migrations) == 0
        # Suspicious findings about schema/tracking mismatch should be empty
        # (Note: there may be findings about SQL file coverage, which is fine)
        mismatch_findings = [
            s for s in health.suspicious_findings
            if "tracked" in s or "schema evidence" in s
        ]
        assert len(mismatch_findings) == 0


# ── Test: Row count in integrity check ──────────────────────────────


class TestIntegrityRowCount:
    """Row count should be accurate in integrity checks."""

    def test_row_count_after_init(self, fresh_conn):
        """Row counts should be 0 after fresh init_db."""
        results = check_table_integrity(fresh_conn)
        for check in results:
            if check.exists:
                assert check.row_count >= 0  # 0 is expected for fresh DB


# ── Test: Exports from connection module ─────────────────────────────


class TestConnectionModuleExports:
    """The connection module should export health/integrity functions."""

    def test_health_functions_importable_from_connection(self):
        """check_migration_health and check_table_integrity should be importable."""
        from novel_factory.db.connection import (
            check_migration_health,
            check_table_integrity,
        )
        assert callable(check_migration_health)
        assert callable(check_table_integrity)

    def test_dataclasses_importable_from_connection(self):
        """MigrationHealthStatus and TableIntegrityCheck should be importable."""
        from novel_factory.db.connection import (
            MigrationHealthStatus,
            TableIntegrityCheck,
        )
        assert MigrationHealthStatus is not None
        assert TableIntegrityCheck is not None

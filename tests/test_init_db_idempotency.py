"""Tests for init_db() idempotency.

Ensures that init_db() can be called multiple times on the same database
without raising errors, and that real CLI command chains work correctly
after multiple init_db() invocations.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

from novel_factory.db.connection import (
    _is_migration_applied_by_schema,
    _is_migration_applied_by_tracking,
    get_connection,
    init_db,
)


def _get_expected_migration_count() -> int:
    """Dynamically compute expected migration count.

    Returns: 1 (000_base_schema) + number of migration files in db/migrations/
    """
    migration_dir = (
        Path(__file__).resolve().parent.parent
        / "novel_factory" / "db" / "migrations"
    )
    migration_count = len(list(migration_dir.glob("*.sql")))
    return 1 + migration_count  # base_schema + migrations


class TestInitDbIdempotency:
    """Test that init_db() is idempotent and can be called multiple times."""

    def test_init_db_twice_on_fresh_db(self, tmp_path):
        """init_db() on the same fresh database twice should not raise."""
        db_path = tmp_path / "test.db"
        init_db(db_path)
        # Second call must not raise
        init_db(db_path)
        # Verify all tables exist
        conn = get_connection(str(db_path))
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        ]
        conn.close()
        assert "projects" in tables
        assert "chapters" in tables
        assert "workflow_runs" in tables
        assert "production_runs" in tables

    def test_init_db_three_times(self, tmp_path):
        """init_db() called three times should not raise."""
        db_path = tmp_path / "test.db"
        init_db(db_path)
        init_db(db_path)
        init_db(db_path)
        # Verify migrations are tracked correctly
        conn = get_connection(str(db_path))
        count = conn.execute(
            "SELECT COUNT(*) FROM _migrations_applied"
        ).fetchone()[0]
        conn.close()
        expected = _get_expected_migration_count()
        assert count == expected, f"Expected {expected} migration records, got {count}"

    def test_init_db_on_empty_sqlite_file(self, tmp_path):
        """init_db() on an empty sqlite file should not raise."""
        db_path = tmp_path / "empty.db"
        # Create an empty file (just touch)
        db_path.touch()
        init_db(db_path)
        # Verify it's properly initialized
        conn = get_connection(str(db_path))
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        ]
        conn.close()
        assert len(tables) > 0

    def test_init_db_on_db_with_base_schema_no_tracking(self, tmp_path):
        """init_db() on a DB with base schema but no tracking should not raise."""
        db_path = tmp_path / "base_only.db"
        # Apply base schema manually (simulating old DB)
        conn = sqlite3.connect(str(db_path))
        schema_file = (
            Path(__file__).resolve().parent.parent
            / "novel_factory" / "db" / "schema" / "000_base_schema.sql"
        )
        conn.executescript(schema_file.read_text(encoding="utf-8"))
        conn.commit()
        conn.close()

        # init_db should detect existing schema and not fail
        init_db(str(db_path))

        # Verify all migrations are tracked
        conn = get_connection(str(db_path))
        count = conn.execute(
            "SELECT COUNT(*) FROM _migrations_applied"
        ).fetchone()[0]
        conn.close()
        expected = _get_expected_migration_count()
        assert count == expected, f"Expected {expected} migration records, got {count}"

    def test_init_db_on_db_with_all_migrations_no_tracking(self, tmp_path):
        """init_db() on a DB with all migrations but no tracking should not raise."""
        db_path = tmp_path / "all_migrations.db"
        migration_dir = (
            Path(__file__).resolve().parent.parent
            / "novel_factory" / "db" / "migrations"
        )

        # Apply all migrations manually (simulating old DB)
        conn = sqlite3.connect(str(db_path))
        schema_file = (
            Path(__file__).resolve().parent.parent
            / "novel_factory" / "db" / "schema" / "000_base_schema.sql"
        )
        conn.executescript(schema_file.read_text(encoding="utf-8"))
        for sql_file in sorted(migration_dir.glob("*.sql")):
            conn.executescript(sql_file.read_text(encoding="utf-8"))
        conn.commit()
        conn.close()

        # init_db should detect existing schema and not fail
        init_db(str(db_path))

        # Verify all migrations are tracked
        conn = get_connection(str(db_path))
        count = conn.execute(
            "SELECT COUNT(*) FROM _migrations_applied"
        ).fetchone()[0]
        conn.close()
        expected = _get_expected_migration_count()
        assert count == expected, f"Expected {expected} migration records, got {count}"

    def test_init_db_duplicate_tracking_record_no_error(self, tmp_path):
        """INSERT OR IGNORE should prevent unique constraint errors."""
        db_path = tmp_path / "duplicate.db"
        init_db(db_path)

        # Manually try to insert a duplicate tracking record
        conn = get_connection(str(db_path))
        # This should NOT raise IntegrityError
        conn.execute(
            "INSERT OR IGNORE INTO _migrations_applied (name) VALUES (?)",
            ("002_v1_1_stability",),
        )
        conn.commit()
        conn.close()

        # And init_db again should still work
        init_db(str(db_path))


class TestSchemaDetection:
    """Test that _is_migration_applied_by_schema correctly detects applied migrations."""

    def test_detects_base_schema(self, tmp_path):
        """Schema detection should detect the base schema."""
        db_path = tmp_path / "test.db"
        init_db(str(db_path))
        conn = get_connection(str(db_path))
        assert _is_migration_applied_by_schema(conn, "000_base_schema")
        conn.close()

    def test_detects_001_workflow_tables(self, tmp_path):
        """Schema detection should detect workflow tables migration."""
        db_path = tmp_path / "test.db"
        init_db(str(db_path))
        conn = get_connection(str(db_path))
        assert _is_migration_applied_by_schema(conn, "001_add_workflow_tables")
        conn.close()

    def test_detects_002_content_hash(self, tmp_path):
        """Schema detection should detect content_hash column."""
        db_path = tmp_path / "test.db"
        init_db(str(db_path))
        conn = get_connection(str(db_path))
        assert _is_migration_applied_by_schema(conn, "002_v1_1_stability")
        conn.close()

    def test_detects_006_qualityhub(self, tmp_path):
        """Schema detection should detect quality_reports table."""
        db_path = tmp_path / "test.db"
        init_db(str(db_path))
        conn = get_connection(str(db_path))
        assert _is_migration_applied_by_schema(conn, "006_v2_1_qualityhub_skill")
        conn.close()

    def test_detects_007_batch(self, tmp_path):
        """Schema detection should detect batch production tables."""
        db_path = tmp_path / "test.db"
        init_db(str(db_path))
        conn = get_connection(str(db_path))
        assert _is_migration_applied_by_schema(conn, "007_v3_0_batch_production")
        conn.close()


class TestCLIChainIdempotency:
    """Test that real CLI command chains work after repeated init_db() calls."""

    def _run_cli(self, args: list[str]) -> tuple[int, str, str]:
        """Run CLI command and return exit code, stdout, stderr."""
        cmd = [sys.executable, "-m", "novel_factory.cli"] + args
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.returncode, result.stdout, result.stderr

    def test_seed_demo_then_run_chapter_no_traceback(self, tmp_path):
        """seed-demo then run-chapter should not traceback on migration."""
        db_path = tmp_path / "chain.db"

        # Step 1: seed-demo
        code, stdout, stderr = self._run_cli([
            "--db-path", str(db_path),
            "seed-demo", "--project-id", "demo", "--json",
        ])
        assert code == 0, f"seed-demo failed: {stdout}{stderr}"

        # Step 2: run-chapter (stub mode to avoid LLM errors)
        code, stdout, stderr = self._run_cli([
            "--db-path", str(db_path),
            "--llm-mode", "stub",
            "run-chapter", "--project-id", "demo", "--chapter", "1",
            "--max-steps", "1", "--json",
        ])
        # Should not traceback
        assert "Traceback" not in stdout, f"stdout contains traceback: {stdout[:500]}"
        assert "Traceback" not in stderr, f"stderr contains traceback: {stderr[:500]}"

        # Should return valid JSON
        result = json.loads(stdout)
        assert "ok" in result

    def test_seed_demo_on_empty_file_no_unique_error(self, tmp_path):
        """seed-demo on empty sqlite file should not raise _migrations_applied unique error."""
        db_path = tmp_path / "empty.db"
        db_path.touch()  # Create empty file

        code, stdout, stderr = self._run_cli([
            "--db-path", str(db_path),
            "seed-demo", "--project-id", "demo", "--json",
        ])

        assert code == 0, f"seed-demo on empty file failed: {stdout}{stderr}"
        assert "UNIQUE constraint" not in stdout
        assert "UNIQUE constraint" not in stderr
        assert "Traceback" not in stdout
        assert "Traceback" not in stderr

    def test_seed_demo_then_run_chapter_real_mode_json_envelope(self, tmp_path):
        """seed-demo then run-chapter --llm-mode real --json should return JSON envelope."""
        db_path = tmp_path / "real_chain.db"
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            "llm:\n"
            "  provider: openai_compatible\n"
            "  base_url_env: MISSING_BASE_URL\n"
            "  api_key_env: MISSING_API_KEY\n"
            "  model: gpt-4o-mini\n"
        )

        # Step 1: seed-demo
        code, stdout, stderr = self._run_cli([
            "--db-path", str(db_path),
            "seed-demo", "--project-id", "demo", "--json",
        ])
        assert code == 0, f"seed-demo failed: {stdout}{stderr}"

        # Step 2: run-chapter with real mode (will fail due to missing env)
        code, stdout, stderr = self._run_cli([
            "--db-path", str(db_path),
            "--config", str(config_path),
            "--llm-mode", "real",
            "run-chapter", "--project-id", "demo", "--chapter", "1", "--json",
        ])

        # Should not traceback
        assert "Traceback" not in stdout, f"stdout contains traceback: {stdout[:500]}"

        # Should return valid JSON envelope
        result = json.loads(stdout)
        assert "ok" in result
        assert "error" in result
        assert "data" in result

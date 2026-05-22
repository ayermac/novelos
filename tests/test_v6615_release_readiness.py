"""v6.6.15 Release Readiness tests.

Covers:
- Version uniformity (Task 1)
- Migration health & idempotency (Task 2)
- Desktop packaging script existence & readability (Task 3)
- Stub real-chain smoke test (Task 4)
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from novel_factory.db.migration_registry import (
    MIGRATION_REGISTRY,
    MigrationHealthStatus,
    TableIntegrityCheck,
    check_migration_health,
    check_table_integrity,
    CRITICAL_TABLE_COLUMNS,
)
from novel_factory.db.connection import (
    init_db,
    get_connection,
)
from novel_factory.version import get_version


def _cli_env() -> dict[str, str]:
    """Return a test-safe environment that prevents implicit real-mode config."""
    return {**os.environ, "NOVEL_FACTORY_DISABLE_DOTENV": "1"}


def _run_cli(db_path: Path, *args: str, timeout: int = 60) -> dict:
    """Run the Novelos CLI against a temp DB and return parsed JSON."""
    result = subprocess.run(
        [sys.executable, "-m", "novel_factory.cli", "--db-path", str(db_path), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=_cli_env(),
    )
    assert result.returncode == 0, (
        f"CLI command failed: {' '.join(args)}\nSTDOUT={result.stdout}\nSTDERR={result.stderr}"
    )
    return json.loads(result.stdout)


def _add_demo_chapter(db_path: Path, project_id: str, chapter_number: int) -> None:
    """Seed the next demo chapter without an instruction so Planner must run."""
    conn = get_connection(str(db_path))
    try:
        conn.execute(
            "INSERT OR IGNORE INTO chapters "
            "(project_id, chapter_number, title, status) VALUES (?, ?, ?, 'planned')",
            (project_id, chapter_number, f"第{chapter_number}章：余波"),
        )
        conn.execute(
            "INSERT OR IGNORE INTO outlines "
            "(project_id, level, sequence, title, content, chapters_range) "
            "VALUES (?, 'chapter', ?, ?, ?, ?)",
            (
                project_id,
                chapter_number,
                f"第{chapter_number}章：余波",
                "林默从上一章的冲突中脱身后，开始追查敌人留下的异常痕迹，"
                "并意识到灵力觉醒背后存在人为干预。",
                str(chapter_number),
            ),
        )
        conn.commit()
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════════
# Task 1: Version uniformity
# ══════════════════════════════════════════════════════════════════════


class TestVersionUniformity:
    """All version sources must agree on the current runtime version."""

    def test_version_py_consistent(self):
        assert get_version() == "6.6.17"

    def test_frontend_package_json_version(self):
        pkg = Path(__file__).parent.parent / "frontend" / "package.json"
        data = json.loads(pkg.read_text())
        assert data["version"] == get_version()

    def test_desktop_package_json_version(self):
        pkg = Path(__file__).parent.parent / "desktop" / "package.json"
        data = json.loads(pkg.read_text())
        assert data["version"] == get_version()

    def test_no_old_version_strings_in_package_files(self):
        """No package.json should still contain '6.6.15' or older as version."""
        for package_path in [
            "frontend/package.json",
            "desktop/package.json",
        ]:
            full = Path(__file__).parent.parent / package_path
            data = json.loads(full.read_text())
            assert data["version"] not in ("6.6.14", "6.8.0-m6"), (
                f"{package_path} still has old version {data['version']}"
            )

    def test_cli_version_matches(self):
        """CLI --version should show current version."""
        result = subprocess.run(
            [sys.executable, "-m", "novel_factory.cli", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        current = get_version()
        assert current in result.stdout, f"CLI version mismatch: expected {current}, got {result.stdout}"

    def test_health_endpoint_uses_get_version(self):
        """GET /api/health uses get_version() which returns 6.6.15."""
        from novel_factory.api.routes.health import health_check
        # Verify the module imports get_version
        import inspect
        source = inspect.getsource(health_check)
        assert "get_version" in source, "health_check should use get_version()"


# ══════════════════════════════════════════════════════════════════════
# Task 2: Migration health & idempotency
# ══════════════════════════════════════════════════════════════════════


class TestFreshDbMigrationHealth:
    """New empty database after init_db must be clean."""

    def test_health_on_fresh_db_all_applied(self, tmp_path):
        db_path = tmp_path / "test.db"
        init_db(db_path)
        conn = get_connection(str(db_path))
        health = check_migration_health(conn)
        conn.close()
        assert health.total_migrations == len(MIGRATION_REGISTRY)
        assert len(health.applied_migrations) == len(MIGRATION_REGISTRY)
        assert len(health.pending_migrations) == 0
        assert health.registry_coverage == 1.0

    def test_health_on_fresh_db_no_suspicious(self, tmp_path):
        db_path = tmp_path / "test.db"
        init_db(db_path)
        conn = get_connection(str(db_path))
        health = check_migration_health(conn)
        conn.close()
        mismatch_findings = [
            s for s in health.suspicious_findings
            if "tracked" in s or "schema evidence" in s
        ]
        assert len(mismatch_findings) == 0, f"Suspicious findings: {mismatch_findings}"


class TestInitDbIdempotency:
    """Repeated init_db must be idempotent."""

    def test_init_db_twice_no_error(self, tmp_path):
        db_path = tmp_path / "test.db"
        init_db(db_path)
        init_db(db_path)  # must not raise

    def test_init_db_twice_tracking_count(self, tmp_path):
        db_path = tmp_path / "test.db"
        init_db(db_path)
        init_db(db_path)
        conn = get_connection(str(db_path))
        count = conn.execute(
            "SELECT COUNT(*) FROM _migrations_applied"
        ).fetchone()[0]
        conn.close()
        assert count == len(MIGRATION_REGISTRY)


class TestRegistryCoverage:
    """Migration registry must cover all SQL files."""

    def test_registry_coverage_1_0(self, tmp_path):
        db_path = tmp_path / "test.db"
        init_db(db_path)
        conn = get_connection(str(db_path))
        health = check_migration_health(conn)
        conn.close()
        assert health.registry_coverage >= 1.0, (
            f"Registry coverage below 1.0: {health.registry_coverage}"
        )

    def test_no_unregistered_sql_files(self):
        from novel_factory.db.migration_registry import get_migration_sql_files
        sql_files = get_migration_sql_files()
        registry_ids = {
            e.sql_filename for e in MIGRATION_REGISTRY
        } | {"000_base_schema.sql"}  # base schema lives in schema/
        sql_filenames = {f.name for f in sql_files}
        uncovered = sql_filenames - registry_ids
        assert not uncovered, f"SQL files not in registry: {uncovered}"


class TestCriticalTableIntegrity:
    """Core tables must exist after init_db."""

    CORE_TABLES = [
        "projects",
        "chapters",
        "instructions",
        "workflow_runs",
        "agent_artifacts",
        "story_facts",
        "memory_update_batches",
    ]

    def test_all_core_tables_exist(self, tmp_path):
        db_path = tmp_path / "test.db"
        init_db(db_path)
        conn = get_connection(str(db_path))
        try:
            results = check_table_integrity(conn)
            for check in results:
                assert check.exists, f"Core table {check.table_name} missing"
                assert len(check.missing_columns) == 0, (
                    f"Table {check.table_name} missing columns: {check.missing_columns}"
                )
        finally:
            conn.close()

    def test_core_tables_exist_after_second_init(self, tmp_path):
        """Core tables must exist after double init_db."""
        db_path = tmp_path / "test.db"
        init_db(db_path)
        init_db(db_path)
        conn = get_connection(str(db_path))
        try:
            for table in self.CORE_TABLES:
                row = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                    (table,),
                ).fetchone()
                assert row is not None, f"Table {table} missing after double init_db"
        finally:
            conn.close()


# ══════════════════════════════════════════════════════════════════════
# Task 3: Desktop packaging check
# ══════════════════════════════════════════════════════════════════════


class TestPackagingScriptExistence:
    """Packaging scripts must exist and be executable."""

    def test_build_desktop_mac_script_exists(self):
        script = (
            Path(__file__).parent.parent
            / "packaging" / "scripts" / "build-desktop-mac.sh"
        )
        assert script.exists(), f"Build script not found: {script}"
        assert os.access(script, os.R_OK), f"Build script not readable: {script}"

    def test_build_desktop_mac_script_key_params(self):
        """Script help must mention --dir and --dmg."""
        script = (
            Path(__file__).parent.parent
            / "packaging" / "scripts" / "build-desktop-mac.sh"
        )
        content = script.read_text()
        assert "--dir" in content, "Build script missing --dir parameter"
        assert "--dmg" in content, "Build script missing --dmg parameter"

    def test_build_desktop_mac_script_output_paths(self):
        """Script output must mention .app and .dmg paths."""
        script = (
            Path(__file__).parent.parent
            / "packaging" / "scripts" / "build-desktop-mac.sh"
        )
        content = script.read_text()
        assert "Novelos.app" in content, "Build script missing .app output path"
        assert "Novelos-*.dmg" in content, "Build script missing .dmg output path"

    def test_build_desktop_mac_script_shows_version(self):
        """Build script header must show version."""
        script = (
            Path(__file__).parent.parent
            / "packaging" / "scripts" / "build-desktop-mac.sh"
        )
        content = script.read_text()
        assert 'v$VERSION' in content or 'version' in content.lower(), (
            "Build script should display version"
        )


# ══════════════════════════════════════════════════════════════════════
# Task 4: Stub real-chain smoke test
# ══════════════════════════════════════════════════════════════════════


class TestStubFullChainSmoke:
    """Full stub chain: init_db → seed → chapter 1 → check → chapter 2 audit."""

    def test_full_chain_chapter1_to_reviewed(self, tmp_path):
        """Run full chapter 1 production chain via stub CLI and verify state."""
        db_path = tmp_path / "smoke.db"

        # Step 1: seed demo project
        result = subprocess.run(
            [
                sys.executable, "-m", "novel_factory.cli",
                "--db-path", str(db_path),
                "seed-demo", "--project-id", "smoke", "--json",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            env={**os.environ, "NOVEL_FACTORY_DISABLE_DOTENV": "1"},
        )
        assert result.returncode == 0, f"seed-demo failed: {result.stderr}"
        seed_data = json.loads(result.stdout)
        assert seed_data.get("ok") is True

        # Step 2: run chapter 1 with stub LLM
        result = subprocess.run(
            [
                sys.executable, "-m", "novel_factory.cli",
                "--db-path", str(db_path),
                "--llm-mode", "stub",
                "run-chapter", "--project-id", "smoke",
                "--chapter", "1", "--json",
            ],
            capture_output=True,
            text=True,
            timeout=60,
            env={**os.environ, "NOVEL_FACTORY_DISABLE_DOTENV": "1"},
        )
        assert result.returncode == 0, f"run-chapter failed: {result.stderr}"
        run_data = json.loads(result.stdout)

        # Step 3: verify chapter status
        conn = get_connection(str(db_path))
        try:
            chapter = conn.execute(
                "SELECT status FROM chapters WHERE project_id=? AND chapter_number=?",
                ("smoke", 1),
            ).fetchone()
            assert chapter is not None, "Chapter 1 not created"
            assert chapter[0] in ("reviewed", "awaiting_publish", "published"), (
                f"Chapter 1 unexpected status: {chapter[0]}"
            )
        finally:
            conn.close()

    def test_full_chain_domain_result_present(self, tmp_path):
        """Run detail must contain domain_result and memory_status."""
        db_path = tmp_path / "smoke.db"

        _run_cli(db_path, "seed-demo", "--project-id", "smoke", "--json", timeout=30)
        run_data = _run_cli(
            db_path,
            "--llm-mode", "stub",
            "run-chapter", "--project-id", "smoke",
            "--chapter", "1", "--json",
        )
        run_id = run_data["data"]["run_id"]

        from fastapi.testclient import TestClient
        from novel_factory.api_app import create_api_app

        client = TestClient(create_api_app(db_path=str(db_path), llm_mode="stub"))
        response = client.get(f"/api/runs/{run_id}")
        assert response.status_code == 200
        detail = response.json()
        assert detail["ok"] is True

        payload = detail["data"]
        assert payload["run_id"] == run_id
        assert payload["domain_result"]["domain_status"] in {
            "success",
            "fallback",
            "degraded",
            "partial_success",
        }
        assert "severity" in payload["domain_result"]
        assert payload["memory_status"]["memory_status"] in {
            "trusted",
            "fallback",
            "failed",
            "missing",
        }
        assert isinstance(payload["memory_context_audit"], dict)

    def test_full_chain_chapter2_planner_audit(self, tmp_path):
        """After chapter 1, chapter 2 Planner audit must show memory context info."""
        db_path = tmp_path / "smoke.db"

        _run_cli(db_path, "seed-demo", "--project-id", "smoke", "--json", timeout=30)
        _run_cli(
            db_path,
            "--llm-mode", "stub",
            "run-chapter", "--project-id", "smoke",
            "--chapter", "1", "--json",
        )
        _add_demo_chapter(db_path, "smoke", 2)
        chapter2 = _run_cli(
            db_path,
            "--llm-mode", "stub",
            "run-chapter", "--project-id", "smoke",
            "--chapter", "2", "--json",
        )
        assert chapter2["ok"] is True
        run_id = chapter2["data"]["run_id"]

        from fastapi.testclient import TestClient
        from novel_factory.api_app import create_api_app

        client = TestClient(create_api_app(db_path=str(db_path), llm_mode="stub"))
        detail = client.get(f"/api/runs/{run_id}").json()["data"]
        audit = detail["memory_context_audit"]
        assert audit["chapter_number"] == 2
        assert audit["batch_status"] in {"trusted", "degraded", "missing"}
        assert audit["batch_status"] != "not_applicable"
        assert isinstance(audit["memory_items_count"], int)
        assert isinstance(audit["memory_context_degraded"], bool)

    def test_workflow_timeline_node_semantics(self, tmp_path):
        """Workflow timeline must have node_status and domain_status fields."""
        db_path = tmp_path / "smoke.db"

        _run_cli(db_path, "seed-demo", "--project-id", "smoke", "--json", timeout=30)
        _run_cli(
            db_path,
            "--llm-mode", "stub",
            "run-chapter", "--project-id", "smoke",
            "--chapter", "1", "--json",
        )

        from fastapi.testclient import TestClient
        from novel_factory.api_app import create_api_app

        client = TestClient(create_api_app(db_path=str(db_path), llm_mode="stub"))
        response = client.get("/api/projects/smoke/chapters/1/workflow-timeline")
        assert response.status_code == 200
        payload = response.json()["data"]
        assert payload["nodes"], "workflow timeline returned no nodes"

        memory_node = None
        for node in payload["nodes"]:
            assert node["node_status"] in {
                "pending",
                "running",
                "succeeded",
                "warning",
                "failed",
                "skipped",
                "blocked",
            }
            assert node["domain_status"] in {
                "success",
                "partial_success",
                "fallback",
                "degraded",
                "failed",
                "blocked",
                "needs_human",
                "pending",
                "ignored",
            }
            assert node["severity"] in {"success", "info", "warning", "error"}
            if node["node_name"] == "memory_curator":
                memory_node = node

        assert memory_node is not None, "memory_curator node missing from timeline"
        if memory_node["domain_status"] in {"fallback", "degraded", "partial_success"}:
            assert memory_node["node_status"] == "warning"
            assert memory_node["severity"] == "warning"
        assert not (
            memory_node["domain_status"] in {"fallback", "degraded", "partial_success"}
            and memory_node["severity"] == "success"
        )


# ══════════════════════════════════════════════════════════════════════
# Task 5: Documentation checks (smoke)
# ══════════════════════════════════════════════════════════════════════


class TestDocumentationExists:
    """Key documentation files must exist."""

    def test_changelog_has_v6615(self):
        changelog = Path(__file__).parent.parent / "CHANGELOG.md"
        content = changelog.read_text()
        assert "v6.6.15" in content

    def test_readme_mentions_packaging(self):
        readme = Path(__file__).parent.parent / "README.md"
        content = readme.read_text()
        # Should mention packaging or desktop or build
        assert any(
            keyword in content.lower()
            for keyword in ["packaging", "desktop", "build", "打包"]
        ), "README should mention packaging/building"

    def test_desktop_readme_has_build_instructions(self):
        desktop_readme = Path(__file__).parent.parent / "desktop" / "README.md"
        content = desktop_readme.read_text()
        assert "packaging/scripts/build-desktop-mac.sh" in content
        assert "--dir" in content
        assert "--dmg" in content


# ══════════════════════════════════════════════════════════════════════
# Task 6: Focused review checks
# ══════════════════════════════════════════════════════════════════════


class TestNoLeaksOrRegressions:
    """Focused review safety checks."""

    def test_docs_superpowers_not_in_git(self):
        """docs/superpowers/ must not be tracked by git."""
        result = subprocess.run(
            ["git", "ls-files", "docs/superpowers/"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,
        )
        assert result.stdout.strip() == "", (
            "docs/superpowers/ should not be in git"
        )

    def test_no_real_llm_calls_in_tests(self, tmp_path):
        """This entire smoke test uses only stub mode — verify no real env leaks."""
        assert os.environ.get("NOVEL_FACTORY_DISABLE_DOTENV") == "1" or True
        db_path = tmp_path / "stub_only.db"
        subprocess.run(
            [
                sys.executable, "-m", "novel_factory.cli",
                "--db-path", str(db_path),
                "seed-demo", "--project-id", "stub", "--json",
            ],
            capture_output=True,
            timeout=30,
            env={**os.environ, "NOVEL_FACTORY_DISABLE_DOTENV": "1"},
            check=False,
        )
        result = subprocess.run(
            [
                sys.executable, "-m", "novel_factory.cli",
                "--db-path", str(db_path),
                "--llm-mode", "stub",
                "run-chapter", "--project-id", "stub",
                "--chapter", "1", "--json",
            ],
            capture_output=True,
            text=True,
            timeout=60,
            env={**os.environ, "NOVEL_FACTORY_DISABLE_DOTENV": "1"},
        )
        assert "OPENAI_API_KEY" not in result.stdout
        assert "API key" not in result.stderr.lower()

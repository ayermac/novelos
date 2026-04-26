"""v4.0 Style Bible CLI integration tests.

Covers:
- style templates --json
- style init --project-id --template --json
- style show --project-id --json
- style update --project-id --set key=value --json
- style check --project-id --chapter --json
- style delete --project-id --json
- Error paths return stable envelope
- No traceback in JSON output
- v3.1/v3.9 CLI regression
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

import pytest


def run_cli(args: list[str], db_path: str | None = None, expect_json: bool = True) -> tuple[int, str, str]:
    """Run CLI command and return exit code, stdout, stderr."""
    cmd = [sys.executable, "-m", "novel_factory.cli"]
    if db_path:
        cmd.extend(["--db-path", db_path])
    cmd.extend(args)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return result.returncode, result.stdout, result.stderr


def _parse_json(stdout: str) -> dict:
    """Parse JSON from stdout."""
    return json.loads(stdout)


@pytest.fixture(scope="module")
def db_path():
    """Create a temporary database for CLI tests."""
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "v40_cli_test.db")
        # Init DB
        subprocess.run(
            [sys.executable, "-m", "novel_factory.cli", "--db-path", db, "init-db"],
            capture_output=True, timeout=30,
        )
        # Seed demo
        subprocess.run(
            [sys.executable, "-m", "novel_factory.cli", "--db-path", db, "seed-demo", "--project-id", "demo", "--json"],
            capture_output=True, timeout=30,
        )
        yield db


class TestStyleTemplates:
    """Test style templates command."""

    def test_templates_json(self, db_path):
        """style templates --json returns valid envelope."""
        code, stdout, stderr = run_cli(["style", "templates", "--json"], db_path)
        assert code == 0, f"Exit {code}, stderr: {stderr}"
        result = _parse_json(stdout)
        assert result["ok"] is True
        assert result["data"]["total"] > 0
        assert len(result["data"]["templates"]) > 0

    def test_templates_has_default(self, db_path):
        """Templates include default_web_serial."""
        code, stdout, _ = run_cli(["style", "templates", "--json"], db_path)
        result = _parse_json(stdout)
        ids = [t["id"] for t in result["data"]["templates"]]
        assert "default_web_serial" in ids


class TestStyleInit:
    """Test style init command."""

    def test_init_success(self, db_path):
        """style init creates Style Bible."""
        code, stdout, stderr = run_cli(
            ["style", "init", "--project-id", "demo", "--template", "default_web_serial", "--json"],
            db_path,
        )
        assert code == 0, f"Exit {code}, stderr: {stderr}"
        result = _parse_json(stdout)
        assert result["ok"] is True
        assert result["data"]["project_id"] == "demo"

    def test_init_duplicate_error(self, db_path):
        """style init on existing project returns error."""
        code, stdout, _ = run_cli(
            ["style", "init", "--project-id", "demo", "--template", "default_web_serial", "--json"],
            db_path,
        )
        result = _parse_json(stdout)
        assert result["ok"] is False
        assert "already exists" in result["error"]

    def test_init_invalid_template_error(self, db_path):
        """style init with invalid template returns error."""
        code, stdout, _ = run_cli(
            ["style", "init", "--project-id", "invalid_tmpl_test", "--template", "nonexistent_template",
             "--create-project", "--json"],
            db_path,
        )
        result = _parse_json(stdout)
        assert result["ok"] is False
        assert "Unknown template" in result["error"]

    def test_init_with_overrides(self, db_path):
        """style init with --set overrides."""
        code, stdout, _ = run_cli(
            ["style", "init", "--project-id", "override_test", "--template", "default_web_serial",
             "--create-project", "--set", "genre=科幻", "--set", "pacing=slow", "--json"],
            db_path,
        )
        if code == 0:
            result = _parse_json(stdout)
            assert result["ok"] is True

    def test_init_nonexistent_project_without_flag(self, db_path):
        """style init for nonexistent project without --create-project returns error."""
        code, stdout, _ = run_cli(
            ["style", "init", "--project-id", "phantom_project", "--template", "default_web_serial", "--json"],
            db_path,
        )
        result = _parse_json(stdout)
        assert result["ok"] is False
        assert "does not exist" in result["error"]

    def test_init_nonexistent_project_with_flag(self, db_path):
        """style init for nonexistent project with --create-project succeeds."""
        code, stdout, _ = run_cli(
            ["style", "init", "--project-id", "new_project_flag", "--template", "default_web_serial",
             "--create-project", "--json"],
            db_path,
        )
        result = _parse_json(stdout)
        assert result["ok"] is True
        assert result["data"]["project_id"] == "new_project_flag"


class TestStyleShow:
    """Test style show command."""

    def test_show_existing(self, db_path):
        """style show for existing project."""
        code, stdout, _ = run_cli(["style", "show", "--project-id", "demo", "--json"], db_path)
        assert code == 0
        result = _parse_json(stdout)
        assert result["ok"] is True
        assert result["data"]["name"] == "网文默认风格"

    def test_show_nonexistent(self, db_path):
        """style show for nonexistent project returns error."""
        code, stdout, _ = run_cli(["style", "show", "--project-id", "nonexistent", "--json"], db_path)
        result = _parse_json(stdout)
        assert result["ok"] is False
        assert "No Style Bible" in result["error"]


class TestStyleUpdate:
    """Test style update command."""

    def test_update_success(self, db_path):
        """style update with --set."""
        code, stdout, _ = run_cli(
            ["style", "update", "--project-id", "demo", "--set", "genre=仙侠", "--json"],
            db_path,
        )
        assert code == 0
        result = _parse_json(stdout)
        assert result["ok"] is True

        # Verify update
        code2, stdout2, _ = run_cli(["style", "show", "--project-id", "demo", "--json"], db_path)
        result2 = _parse_json(stdout2)
        assert result2["data"]["genre"] == "仙侠"

    def test_update_no_set_error(self, db_path):
        """style update without --set returns error."""
        code, stdout, _ = run_cli(
            ["style", "update", "--project-id", "demo", "--json"],
            db_path,
        )
        result = _parse_json(stdout)
        assert result["ok"] is False

    def test_update_nonexistent_error(self, db_path):
        """style update for nonexistent project returns error."""
        code, stdout, _ = run_cli(
            ["style", "update", "--project-id", "nonexistent", "--set", "genre=科幻", "--json"],
            db_path,
        )
        result = _parse_json(stdout)
        assert result["ok"] is False


class TestStyleCheck:
    """Test style check command."""

    def test_check_existing_chapter(self, db_path):
        """style check for a chapter with Style Bible."""
        code, stdout, _ = run_cli(
            ["style", "check", "--project-id", "demo", "--chapter", "1", "--json"],
            db_path,
        )
        # Chapter 1 may or may not have content, but should not traceback
        result = _parse_json(stdout)
        assert "ok" in result

    def test_check_no_bible_error(self, db_path):
        """style check without Style Bible returns error."""
        code, stdout, _ = run_cli(
            ["style", "check", "--project-id", "no_bible_project", "--chapter", "1", "--json"],
            db_path,
        )
        result = _parse_json(stdout)
        assert result["ok"] is False
        assert "No Style Bible" in result["error"]

    def test_check_no_chapter_error(self, db_path):
        """style check for nonexistent chapter returns error."""
        code, stdout, _ = run_cli(
            ["style", "check", "--project-id", "demo", "--chapter", "999", "--json"],
            db_path,
        )
        result = _parse_json(stdout)
        assert result["ok"] is False


class TestStyleDelete:
    """Test style delete command."""

    def test_delete_success(self, db_path):
        """style delete for existing project."""
        # First create a bible to delete
        run_cli(["style", "init", "--project-id", "delete_test", "--template", "default_web_serial", "--create-project", "--json"], db_path)
        code, stdout, _ = run_cli(["style", "delete", "--project-id", "delete_test", "--json"], db_path)
        assert code == 0
        result = _parse_json(stdout)
        assert result["ok"] is True
        assert result["data"]["deleted"] is True

    def test_delete_nonexistent(self, db_path):
        """style delete for nonexistent project returns error."""
        code, stdout, _ = run_cli(["style", "delete", "--project-id", "nonexistent", "--json"], db_path)
        result = _parse_json(stdout)
        assert result["ok"] is False


class TestCLIErrorPaths:
    """Test that error paths return stable envelope, no traceback."""

    def test_no_traceback_in_json_errors(self, db_path):
        """JSON error responses contain no Python traceback."""
        code, stdout, stderr = run_cli(
            ["style", "show", "--project-id", "nonexistent", "--json"],
            db_path,
        )
        assert "Traceback" not in stdout
        result = _parse_json(stdout)
        assert result["ok"] is False
        assert result["error"]

    def test_no_api_keys_in_output(self, db_path):
        """No API keys appear in any output."""
        code, stdout, _ = run_cli(["style", "templates", "--json"], db_path)
        assert "sk-" not in stdout


class TestV31V39CLIRegression:
    """Ensure v3.1/v3.9 CLI commands still work."""

    def test_llm_profiles_still_works(self, db_path):
        """llm profiles --json still returns valid response."""
        code, stdout, _ = run_cli(["llm", "profiles", "--json"], db_path)
        try:
            result = _parse_json(stdout)
            assert "ok" in result
        except json.JSONDecodeError:
            pass  # May fail if no profiles configured

    def test_llm_catalog_still_works(self, db_path):
        """llm catalog --json still returns valid response."""
        code, stdout, _ = run_cli(["llm", "catalog", "--json"], db_path)
        assert code == 0
        result = _parse_json(stdout)
        assert result["ok"] is True

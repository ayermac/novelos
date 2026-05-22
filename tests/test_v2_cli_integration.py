"""Integration tests for retained diagnostic CLI commands using subprocess.

These tests verify that active CLI commands can run in stub mode.
"""

import json
import subprocess
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    yield db_path
    # Cleanup
    Path(db_path).unlink(missing_ok=True)


def run_cli(db_path: str, args: list[str]) -> tuple[int, str, str]:
    """Run CLI command and return exit code, stdout, stderr."""
    cmd = ["python3", "-m", "novel_factory.cli", "--db-path", db_path] + args
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    return result.returncode, result.stdout, result.stderr


class TestV2CLIIntegration:
    """Integration tests for v2 CLI commands."""

    def test_seed_demo(self, temp_db):
        """seed-demo should create a demo project."""
        code, stdout, stderr = run_cli(temp_db, ["seed-demo", "--project-id", "demo", "--json"])
        
        assert code == 0, f"seed-demo failed: {stderr}"
        data = json.loads(stdout)
        assert data["ok"] is True
        assert "project_id" in data["data"]

    def test_continuity_check_stub_mode(self, temp_db):
        """continuity-check command should work in stub mode."""
        # First seed demo
        run_cli(temp_db, ["seed-demo", "--project-id", "demo", "--json"])
        
        # Run continuity-check
        code, stdout, stderr = run_cli(
            temp_db,
            ["continuity-check", "--project-id", "demo", "--from-chapter", "1", "--to-chapter", "5", "--llm-mode", "stub", "--json"]
        )
        
        assert code == 0, f"continuity-check failed: {stderr}\nstdout: {stdout}"
        data = json.loads(stdout)
        assert data["ok"] is True
        assert "report_id" in data["data"]

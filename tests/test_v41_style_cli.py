"""v4.1 Style Gate & Evolution CLI tests.

Covers:
- style gate --project-id --json
- style gate-set --project-id --mode block --threshold --json
- style versions --project-id --json
- style version-show --version-id --json
- style propose --project-id --json
- style proposals --project-id --json
- style proposal-show --proposal-id --json
- style proposal-decide --proposal-id --decision --json
- Error paths: stable envelope, no traceback
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

import pytest


def run_cli(args: list[str], db_path: str | None = None) -> tuple[int, str, str]:
    cmd = [sys.executable, "-m", "novel_factory.cli"]
    if db_path:
        cmd.extend(["--db-path", db_path])
    cmd.extend(args)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return result.returncode, result.stdout, result.stderr


def _parse_json(stdout: str) -> dict:
    return json.loads(stdout)


@pytest.fixture(scope="module")
def db_path():
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "v41_cli_test.db")
        # Init DB + seed demo + style init
        subprocess.run(
            [sys.executable, "-m", "novel_factory.cli", "--db-path", db, "init-db"],
            capture_output=True, timeout=30,
        )
        subprocess.run(
            [sys.executable, "-m", "novel_factory.cli", "--db-path", db,
             "seed-demo", "--project-id", "demo", "--json"],
            capture_output=True, timeout=30,
        )
        subprocess.run(
            [sys.executable, "-m", "novel_factory.cli", "--db-path", db,
             "style", "init", "--project-id", "demo",
             "--template", "default_web_serial", "--json"],
            capture_output=True, timeout=30,
        )
        yield db


class TestStyleGateCLI:
    def test_gate_show(self, db_path):
        code, stdout, _ = run_cli(["style", "gate", "--project-id", "demo", "--json"], db_path)
        assert code == 0
        result = _parse_json(stdout)
        assert result["ok"] is True

    def test_gate_set_mode_block(self, db_path):
        code, stdout, _ = run_cli(
            ["style", "gate-set", "--project-id", "demo",
             "--mode", "block", "--threshold", "75", "--json"],
            db_path,
        )
        assert code == 0
        result = _parse_json(stdout)
        assert result["ok"] is True
        assert result["data"]["mode"] == "block"
        assert result["data"]["blocking_threshold"] == 75

    def test_gate_set_mode_warn(self, db_path):
        code, stdout, _ = run_cli(
            ["style", "gate-set", "--project-id", "demo",
             "--mode", "warn", "--json"],
            db_path,
        )
        result = _parse_json(stdout)
        assert result["ok"] is True
        assert result["data"]["mode"] == "warn"

    def test_gate_no_bible_error(self, db_path):
        code, stdout, _ = run_cli(
            ["style", "gate", "--project-id", "nonexistent", "--json"], db_path
        )
        result = _parse_json(stdout)
        assert result["ok"] is False

    def test_gate_set_invalid_mode(self, db_path):
        code, stdout, _ = run_cli(
            ["style", "gate-set", "--project-id", "demo",
             "--mode", "invalid", "--json"],
            db_path,
        )
        # argparse should reject invalid choice
        assert code != 0


class TestStyleVersionsCLI:
    def test_versions_list(self, db_path):
        code, stdout, _ = run_cli(
            ["style", "versions", "--project-id", "demo", "--json"], db_path
        )
        assert code == 0
        result = _parse_json(stdout)
        assert result["ok"] is True

    def test_version_show_nonexistent(self, db_path):
        code, stdout, _ = run_cli(
            ["style", "version-show", "--version-id", "nonexistent", "--json"], db_path
        )
        result = _parse_json(stdout)
        assert result["ok"] is False


class TestStyleProposeCLI:
    def test_propose(self, db_path):
        code, stdout, _ = run_cli(
            ["style", "propose", "--project-id", "demo", "--json"], db_path
        )
        assert code == 0
        result = _parse_json(stdout)
        assert result["ok"] is True

    def test_propose_no_bible(self, db_path):
        code, stdout, _ = run_cli(
            ["style", "propose", "--project-id", "nonexistent", "--json"], db_path
        )
        result = _parse_json(stdout)
        assert result["ok"] is False


class TestStyleProposalsCLI:
    def test_proposals_list(self, db_path):
        code, stdout, _ = run_cli(
            ["style", "proposals", "--project-id", "demo", "--json"], db_path
        )
        assert code == 0
        result = _parse_json(stdout)
        assert result["ok"] is True

    def test_proposal_decide_approve(self, db_path):
        # Create a pending proposal directly via Repository so the test
        # is deterministic and does not depend on `style propose` output.
        from novel_factory.db.repository import Repository
        repo = Repository(db_path)
        pid = repo.create_style_evolution_proposal(
            "demo",
            "add_forbidden_expression",
            {"pattern": "冷笑", "severity": "blocking"},
            "Test proposal for decide CLI",
        )

        code, stdout, _ = run_cli(
            ["style", "proposal-decide", "--proposal-id", pid,
             "--decision", "approve", "--notes", "Test approve", "--json"],
            db_path,
        )
        result = _parse_json(stdout)
        assert result["ok"] is True
        assert result["data"]["decision"] == "approved"

    def test_proposal_show_nonexistent(self, db_path):
        code, stdout, _ = run_cli(
            ["style", "proposal-show", "--proposal-id", "nonexistent", "--json"], db_path
        )
        result = _parse_json(stdout)
        assert result["ok"] is False

    def test_proposal_decide_invalid_decision(self, db_path):
        code, stdout, _ = run_cli(
            ["style", "proposal-decide", "--proposal-id", "any",
             "--decision", "invalid", "--json"],
            db_path,
        )
        # argparse rejects invalid choice
        assert code != 0


class TestCLIErrorPaths:
    def test_no_traceback_in_errors(self, db_path):
        code, stdout, _ = run_cli(
            ["style", "gate", "--project-id", "nonexistent", "--json"], db_path
        )
        assert "Traceback" not in stdout
        result = _parse_json(stdout)
        assert result["ok"] is False

    def test_no_author_imitation_fields(self, db_path):
        """CLI output never contains author imitation fields."""
        code, stdout, _ = run_cli(
            ["style", "gate", "--project-id", "demo", "--json"], db_path
        )
        assert "author" not in stdout.lower() or "revision_target" in stdout
        # Specifically check for prohibited patterns
        assert "模仿" not in stdout
        assert "imitate" not in stdout.lower()

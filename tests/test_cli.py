"""CLI tests — covers D1 novelos entry, D4 query, D5 human-resume."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from novel_factory.cli import build_parser, main
from novel_factory.db.connection import init_db
from novel_factory.db.repository import Repository


@pytest.fixture
def tmp_db(tmp_path):
    db_path = tmp_path / "test_cli.db"
    init_db(db_path)
    return str(db_path)


@pytest.fixture
def repo(tmp_db):
    return Repository(tmp_db)


def _seed_project_chapter(repo, status="planned", content=None):
    conn = repo._conn()
    conn.execute(
        "INSERT INTO projects (project_id, name, genre, is_current) VALUES (?, ?, ?, 1)",
        ("cli_proj", "CLI Novel", "urban"),
    )
    if content:
        conn.execute(
            "INSERT INTO chapters (project_id, chapter_number, title, status, content) "
            "VALUES (?, ?, ?, ?, ?)",
            ("cli_proj", 1, "第一章", status, content),
        )
    else:
        conn.execute(
            "INSERT INTO chapters (project_id, chapter_number, title, status) "
            "VALUES (?, ?, ?, ?)",
            ("cli_proj", 1, "第一章", status),
        )
    conn.execute(
        "INSERT INTO instructions (project_id, chapter_number, objective, key_events, "
        "plots_to_plant, plots_to_resolve, ending_hook, word_target, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active')",
        ("cli_proj", 1, "推进剧情", '["事件1"]', '[]', '[]', "悬念", 2500),
    )
    conn.commit()
    conn.close()


# ── Help and basic commands ────────────────────────────────────

class TestCLIHelp:
    def test_novelos_help(self):
        """novelos --help should not error."""
        parser = build_parser()
        # Parsing --help raises SystemExit(0)
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["--help"])
        assert exc_info.value.code == 0

    def test_init_db_help(self):
        parser = build_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["init-db", "--help"])
        assert exc_info.value.code == 0

    def test_run_chapter_help(self):
        parser = build_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["run-chapter", "--help"])
        assert exc_info.value.code == 0


class TestCLIInitDb:
    def test_init_db_creates_database(self, tmp_path):
        db_path = tmp_path / "new_cli.db"
        assert not db_path.exists()
        args = build_parser().parse_args(["--db-path", str(db_path), "init-db"])
        args.func(args)
        assert db_path.exists()

    def test_init_db_custom_path(self, tmp_path):
        db_path = tmp_path / "custom" / "novel.db"
        args = build_parser().parse_args(["--db-path", str(db_path), "init-db"])
        args.func(args)
        assert db_path.exists()


# ── Status command ─────────────────────────────────────────────

class TestCLIStatus:
    def test_status_shows_chapter(self, repo, tmp_db, capsys):
        _seed_project_chapter(repo, status="planned")
        args = build_parser().parse_args([
            "--db-path", tmp_db, "status",
            "--project-id", "cli_proj", "--chapter", "1",
        ])
        args.func(args)
        output = capsys.readouterr().out
        assert "planned" in output

    def test_status_json_output(self, repo, tmp_db, capsys):
        _seed_project_chapter(repo, status="drafted")
        args = build_parser().parse_args([
            "--db-path", tmp_db, "status",
            "--project-id", "cli_proj", "--chapter", "1", "--json",
        ])
        args.func(args)
        output = capsys.readouterr().out
        data = json.loads(output)
        assert data["status"] == "drafted"
        assert data["project_id"] == "cli_proj"

    def test_status_missing_chapter_exits_1(self, tmp_db):
        args = build_parser().parse_args([
            "--db-path", tmp_db, "status",
            "--project-id", "nonexistent", "--chapter", "1",
        ])
        with pytest.raises(SystemExit) as exc_info:
            args.func(args)
        assert exc_info.value.code == 1

    def test_status_latest_run_filtered_by_chapter(self, repo, tmp_db, capsys):
        """[P2] status for chapter N should not show runs from chapter M."""
        _seed_project_chapter(repo, status="planned")
        # Add a second chapter and create a workflow run for it
        conn = repo._conn()
        conn.execute(
            "INSERT INTO chapters (project_id, chapter_number, title, status) "
            "VALUES (?, ?, ?, ?)",
            ("cli_proj", 2, "第二章", "drafted"),
        )
        conn.commit()
        conn.close()
        # Create run for chapter 2 (not chapter 1)
        repo.create_workflow_run("cli_proj", 2)

        args = build_parser().parse_args([
            "--db-path", tmp_db, "status",
            "--project-id", "cli_proj", "--chapter", "1", "--json",
        ])
        args.func(args)
        output = capsys.readouterr().out
        data = json.loads(output)
        # latest_run should be None since we only created a run for chapter 2
        assert data.get("latest_run") is None


# ── Runs command ───────────────────────────────────────────────

class TestCLIRuns:
    def test_runs_empty_project(self, repo, tmp_db, capsys):
        _seed_project_chapter(repo, status="planned")
        args = build_parser().parse_args([
            "--db-path", tmp_db, "runs",
            "--project-id", "cli_proj",
        ])
        args.func(args)
        output = capsys.readouterr().out
        # Should not crash, may say "No workflow runs"
        assert isinstance(output, str)

    def test_runs_json_output(self, repo, tmp_db, capsys):
        _seed_project_chapter(repo, status="planned")
        # Create a workflow run
        repo.create_workflow_run("cli_proj", 1)
        args = build_parser().parse_args([
            "--db-path", tmp_db, "runs",
            "--project-id", "cli_proj", "--json",
        ])
        args.func(args)
        output = capsys.readouterr().out
        data = json.loads(output)
        assert isinstance(data, list)
        assert len(data) >= 1


# ── Artifacts command ──────────────────────────────────────────

class TestCLIArtifacts:
    def test_artifacts_empty(self, repo, tmp_db, capsys):
        _seed_project_chapter(repo, status="planned")
        args = build_parser().parse_args([
            "--db-path", tmp_db, "artifacts",
            "--project-id", "cli_proj", "--chapter", "1",
        ])
        args.func(args)
        output = capsys.readouterr().out
        assert "No artifacts" in output

    def test_artifacts_json_output(self, repo, tmp_db, capsys):
        _seed_project_chapter(repo, status="drafted", content="内容" * 20)
        repo.save_artifact("cli_proj", 1, "author", "draft", {"content": "test"})
        args = build_parser().parse_args([
            "--db-path", tmp_db, "artifacts",
            "--project-id", "cli_proj", "--chapter", "1", "--json",
        ])
        args.func(args)
        output = capsys.readouterr().out
        data = json.loads(output)
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]["agent_id"] == "author"


# ── Human-resume command ───────────────────────────────────────

class TestCLIHumanResume:
    def test_resume_to_drafted(self, repo, tmp_db, capsys):
        _seed_project_chapter(repo, status="blocking")
        args = build_parser().parse_args([
            "--db-path", tmp_db, "human-resume",
            "--project-id", "cli_proj", "--chapter", "1", "--status", "drafted",
        ])
        args.func(args)
        output = capsys.readouterr().out
        assert "drafted" in output

    def test_resume_to_published_forbidden(self, repo, tmp_db):
        _seed_project_chapter(repo, status="blocking")
        args = build_parser().parse_args([
            "--db-path", tmp_db, "human-resume",
            "--project-id", "cli_proj", "--chapter", "1", "--status", "published",
        ])
        with pytest.raises(SystemExit) as exc_info:
            args.func(args)
        assert exc_info.value.code == 1


# ── Legacy compatibility ───────────────────────────────────────

class TestCLILegacy:
    def test_python_m_cli_help(self):
        """python -m novel_factory.cli --help should work."""
        result = subprocess.run(
            [sys.executable, "-m", "novel_factory.cli", "--help"],
            capture_output=True, text=True,
            cwd="/Users/chenchao/Workspace/AI-Project/claw-novel",
        )
        assert result.returncode == 0
        assert "novelos" in result.stdout or "novel-factory" in result.stdout


# ── v1.3 Rework regression tests ────────────────────────────────

class TestBundledSchemaLocatable:
    """[P1] init_db must work from packaged install (schema in novel_factory/db/schema/)."""

    def test_base_schema_file_exists(self):
        """The bundled base schema must exist in the package."""
        from pathlib import Path
        schema_path = Path(__file__).resolve().parent.parent / "novel_factory" / "db" / "schema" / "000_base_schema.sql"
        assert schema_path.exists(), f"Base schema not found at {schema_path}"

    def test_init_db_uses_bundled_schema(self, tmp_path):
        """init_db should work using only the bundled schema, not openclaw-agents."""
        from novel_factory.db.connection import init_db
        db_path = tmp_path / "bundled_test.db"
        init_db(db_path)
        # Verify core tables exist
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        tables = [row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        conn.close()
        # Must have the essential tables
        assert "projects" in tables
        assert "chapters" in tables
        assert "instructions" in tables
        assert "reviews" in tables

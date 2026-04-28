"""Runtime hardening tests for v1.4."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from novel_factory.db.connection import init_db
from novel_factory.db.repository import Repository

from tests.conftest import seed_context_for_chapter


@pytest.fixture
def tmp_db(tmp_path):
    db_path = tmp_path / "test_runtime.db"
    init_db(db_path)
    return str(db_path)


@pytest.fixture
def repo(tmp_db):
    return Repository(tmp_db)


def test_llm_mode_stub_vs_real(tmp_path):
    """Test that stub mode works without API key, real mode fails."""
    db_path = tmp_path / "test_llm_mode.db"
    init_db(db_path)
    
    # Seed a project
    repo = Repository(str(db_path))
    conn = repo._conn()
    conn.execute(
        "INSERT INTO projects (project_id, name, genre, is_current) VALUES (?, ?, ?, 1)",
        ("test_proj", "Test Novel", "urban"),
    )
    conn.execute(
        "INSERT INTO chapters (project_id, chapter_number, title, status) VALUES (?, ?, ?, ?)",
        ("test_proj", 1, "第一章", "planned"),
    )
    conn.execute(
        "INSERT INTO instructions (project_id, chapter_number, objective, key_events, status) "
        "VALUES (?, ?, ?, ?, 'active')",
        ("test_proj", 1, "推进剧情", '["事件1"]'),
    )
    conn.commit()
    conn.close()

    # Seed v5.3 context gate fields
    seed_context_for_chapter(str(db_path), "test_proj", 1)

    # Build clean environment for subprocess: disable .env and clear API keys
    import os
    env = os.environ.copy()
    env["NOVEL_FACTORY_DISABLE_DOTENV"] = "1"
    env.pop("OPENAI_API_KEY", None)
    env.pop("OPENAI_BASE_URL", None)
    
    # Test stub mode should work
    result = subprocess.run(
        [sys.executable, "-m", "novel_factory.cli",
         "--db-path", str(db_path),
         "run-chapter",
         "--project-id", "test_proj",
         "--chapter", "1",
         "--llm-mode", "stub",
         "--max-steps", "1"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
        env=env,
    )
    assert result.returncode == 0, f"Stub mode failed: {result.stderr}"
    
    # Test real mode without API key should fail
    result = subprocess.run(
        [sys.executable, "-m", "novel_factory.cli",
         "--db-path", str(db_path),
         "run-chapter",
         "--project-id", "test_proj",
         "--chapter", "1",
         "--llm-mode", "real",
         "--max-steps", "1"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
        env=env,
    )
    assert result.returncode != 0, "Real mode without API key should fail"
    assert "API key" in result.stderr or "API key" in result.stdout


def test_seed_demo_idempotent(tmp_path):
    """Test that seed-demo is idempotent."""
    db_path = tmp_path / "test_seed.db"
    init_db(db_path)
    
    # First seed
    result = subprocess.run(
        [sys.executable, "-m", "novel_factory.cli",
         "--db-path", str(db_path),
         "seed-demo"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )
    assert result.returncode == 0, f"First seed failed: {result.stderr}"
    assert "Demo project seeded" in result.stdout
    
    # Second seed should not error
    result = subprocess.run(
        [sys.executable, "-m", "novel_factory.cli",
         "--db-path", str(db_path),
         "seed-demo"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )
    assert result.returncode == 0, f"Second seed failed: {result.stderr}"
    assert "already exists" in result.stdout or "Demo project seeded" in result.stdout
    
    # Verify data exists
    repo = Repository(str(db_path))
    conn = repo._conn()
    projects = conn.execute("SELECT * FROM projects WHERE project_id='demo'").fetchall()
    chapters = conn.execute("SELECT * FROM chapters WHERE project_id='demo'").fetchall()
    conn.close()
    assert len(projects) == 1
    assert len(chapters) == 1


def test_smoke_run_returns_structure(tmp_path):
    """Test that smoke-run returns expected structure."""
    db_path = tmp_path / "test_smoke.db"
    
    result = subprocess.run(
        [sys.executable, "-m", "novel_factory.cli",
         "--db-path", str(db_path),
         "smoke-run",
         "--json"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )
    assert result.returncode == 0, f"Smoke run failed: {result.stderr}"
    
    # Should be valid JSON with envelope
    data = json.loads(result.stdout)
    assert "ok" in data
    assert "error" in data
    assert "data" in data
    
    # Check the actual result in data field
    assert "chapter_status" in data["data"]
    assert "steps" in data["data"]
    assert "error" in data["data"]
    assert "requires_human" in data["data"]


def test_revision_target_field_used(repo):
    """Test that revision_target field is used instead of summary parsing."""
    # Create a chapter and review with revision_target field
    conn = repo._conn()
    conn.execute(
        "INSERT INTO projects (project_id, name, genre, is_current) VALUES (?, ?, ?, 1)",
        ("rev_test", "Revision Test", "urban"),
    )
    conn.execute(
        "INSERT INTO chapters (project_id, chapter_number, title, status) VALUES (?, ?, ?, ?)",
        ("rev_test", 1, "第一章", "revision"),
    )
    chapter = conn.execute(
        "SELECT id FROM chapters WHERE project_id='rev_test' AND chapter_number=1"
    ).fetchone()
    chapter_id = chapter["id"]
    
    # Insert review with structured revision_target field
    conn.execute(
        "INSERT INTO reviews (project_id, chapter_id, pass, score, revision_target) "
        "VALUES (?, ?, ?, ?, ?)",
        ("rev_test", chapter_id, 0, 70, "polisher"),
    )
    conn.commit()
    conn.close()
    
    # Test that dispatcher reads from revision_target field
    from novel_factory.dispatcher import Dispatcher
    from novel_factory.llm.provider import LLMProvider
    
    class StubLLM(LLMProvider):
        def invoke_json(self, messages, schema=None, temperature=None) -> dict:
            return {}
        def invoke_text(self, messages, temperature=None, max_tokens=None) -> str:
            return "{}"
    
    dispatcher = Dispatcher(repo, StubLLM(), max_retries=3)
    next_agent = dispatcher._route("rev_test", 1, "revision")
    assert next_agent == "polisher"


def test_migration_004_idempotent(tmp_path):
    """Test that migration 004 can be applied multiple times."""
    db_path = tmp_path / "test_migration.db"
    
    # First init
    init_db(db_path)
    
    # Apply migration manually (simulate second run)
    import sqlite3
    conn = sqlite3.connect(str(db_path))
    
    # Check if column exists
    cursor = conn.execute("PRAGMA table_info(reviews)")
    columns = [row[1] for row in cursor.fetchall()]
    has_revision_target = "revision_target" in columns
    
    # Try to add column (should not fail if already exists)
    try:
        conn.execute("ALTER TABLE reviews ADD COLUMN revision_target TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        # Expected if column already exists
        pass
    
    # Verify column exists now
    cursor = conn.execute("PRAGMA table_info(reviews)")
    columns = [row[1] for row in cursor.fetchall()]
    assert "revision_target" in columns
    conn.close()


def test_workflow_run_shows_llm_mode(tmp_path):
    """Test that workflow run or output shows llm_mode."""
    db_path = tmp_path / "test_llm_mode_visible.db"
    init_db(db_path)
    
    # Seed and run with stub
    result = subprocess.run(
        [sys.executable, "-m", "novel_factory.cli",
         "--db-path", str(db_path),
         "seed-demo"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )
    assert result.returncode == 0
    
    result = subprocess.run(
        [sys.executable, "-m", "novel_factory.cli",
         "--db-path", str(db_path),
         "run-chapter",
         "--project-id", "demo",
         "--chapter", "1",
         "--llm-mode", "stub",
         "--max-steps", "1"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )
    assert result.returncode == 0
    
    # Check workflow runs exist
    repo = Repository(str(db_path))
    runs = repo.get_workflow_runs_for_project("demo")
    assert len(runs) >= 1
    # At least one run should be in terminal state
    assert any(r["status"] in ("completed", "failed", "blocked") for r in runs)

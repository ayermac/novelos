"""Tests for v3.6 Semi-Auto Serial Mode.

Covers:
- Migration 011 idempotency
- Serial plan creation
- Serial plan status
- enqueue-next behavior
- advance decisions
- pause/resume/cancel
- State transitions
- CLI JSON envelope
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from novel_factory.db.connection import get_connection, init_db
from novel_factory.db.repository import Repository
from novel_factory.dispatcher import Dispatcher
from novel_factory.llm.provider import LLMProvider


class StubLLM(LLMProvider):
    """Stub LLM that returns valid outputs for each agent type."""

    def __init__(self, responses: list[dict] | None = None):
        self.responses = responses or []
        self._call_count = 0

    def invoke_json(self, messages, schema=None, temperature=None) -> dict:
        if self._call_count < len(self.responses):
            resp = self.responses[self._call_count]
            self._call_count += 1
            return resp
        # Default responses based on schema
        schema_name = getattr(schema, "__name__", "") if schema else ""
        if "Planner" in schema_name:
            return {
                "chapter_brief": {
                    "objective": "推进剧情", "required_events": ["事件1"],
                    "plots_to_plant": [], "plots_to_resolve": [],
                    "ending_hook": "悬念", "constraints": [],
                }
            }
        if "Screenwriter" in schema_name:
            return {"scene_beats": [{"sequence": 1, "scene_goal": "场景目标", "conflict": "冲突", "hook": "钩子"}]}
        if "Author" in schema_name:
            content = "测试章节内容..."
            return {
                "title": "测试章", "content": content,
                "word_count": len(content), "implemented_events": ["事件1"], "used_plot_refs": [],
            }
        if "Polisher" in schema_name:
            return {
                "content": "润色后内容", "fact_change_risk": "none",
                "changed_scope": ["sentence", "rhythm"], "summary": "微调表达",
            }
        if "Editor" in schema_name:
            return {
                "pass": True, "score": 92,
                "scores": {"setting": 20, "logic": 20, "poison": 18, "text": 17, "pacing": 17},
                "issues": [], "suggestions": [], "revision_target": None, "state_card": {},
            }
        return {}

    def invoke_text(self, messages, temperature=None, max_tokens=None) -> str:
        return "{}"


# ── Test fixtures ───────────────────────────────────────────────────────


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    """Create a temporary database with migrations."""
    db_path = tmp_path / "test.db"
    init_db(str(db_path))
    return db_path


@pytest.fixture
def repo(tmp_db: Path) -> Repository:
    """Create a repository instance."""
    return Repository(str(tmp_db))


@pytest.fixture
def dispatcher(repo: Repository) -> Dispatcher:
    """Create a dispatcher instance with stub LLM."""
    stub_llm = StubLLM()
    return Dispatcher(repo, llm=stub_llm, max_retries=3)


def _seed_project(repo: Repository, project_id: str = "test_project"):
    """Seed a test project."""
    conn = repo._conn()
    conn.execute(
        "INSERT INTO projects (project_id, name, genre, is_current) VALUES (?, ?, ?, 1)",
        (project_id, "Test Novel", "fantasy"),
    )
    conn.commit()
    conn.close()


def _create_serial_plan(dispatcher: Dispatcher, **kwargs):
    """Helper to create a serial plan with defaults."""
    return dispatcher.create_serial_plan(
        project_id=kwargs.get("project_id", "test_project"),
        name=kwargs.get("name", "Test Serial Plan"),
        start_chapter=kwargs.get("start_chapter", 1),
        target_chapter=kwargs.get("target_chapter", 10),
        batch_size=kwargs.get("batch_size", 3),
    )


# ── Test 1: Migration 011 idempotency ────────────────────────────────────


def test_migration_011_idempotent(tmp_db: Path):
    """Test that migration 011 can be run multiple times without error."""
    # Run init_db again (should be idempotent)
    init_db(str(tmp_db))

    # Verify tables exist
    conn = get_connection(str(tmp_db))
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('serial_plans', 'serial_plan_events')"
    )
    tables = {row[0] for row in cursor.fetchall()}
    conn.close()

    assert "serial_plans" in tables
    assert "serial_plan_events" in tables


# ── Test 2: Serial create success ────────────────────────────────────────


def test_serial_create_success(dispatcher: Dispatcher, repo: Repository):
    """Test that serial plan can be created successfully."""
    _seed_project(repo)

    result = dispatcher.create_serial_plan(
        project_id="test_project",
        name="第一卷连载计划",
        start_chapter=1,
        target_chapter=10,
        batch_size=3,
    )

    assert result["ok"] is True
    assert "serial_plan_id" in result["data"]
    assert result["data"]["status"] == "active"
    assert result["data"]["current_chapter"] == 1


# ── Test 3: Create rejects start_chapter > target_chapter ────────────────


def test_create_rejects_start_greater_than_target(dispatcher: Dispatcher, repo: Repository):
    """Test that create rejects start_chapter > target_chapter."""
    _seed_project(repo)

    result = dispatcher.create_serial_plan(
        project_id="test_project",
        name="Invalid Plan",
        start_chapter=10,
        target_chapter=5,
        batch_size=3,
    )

    assert result["ok"] is False
    assert "start_chapter" in result["error"]


# ── Test 4: Create rejects batch_size < 1 ────────────────────────────────


def test_create_rejects_batch_size_less_than_one(dispatcher: Dispatcher, repo: Repository):
    """Test that create rejects batch_size < 1."""
    _seed_project(repo)

    result = dispatcher.create_serial_plan(
        project_id="test_project",
        name="Invalid Plan",
        start_chapter=1,
        target_chapter=10,
        batch_size=0,
    )

    assert result["ok"] is False
    assert "batch_size" in result["error"]


# ── Test 5: Serial status returns plan and events ────────────────────────


def test_serial_status_returns_plan_and_events(dispatcher: Dispatcher, repo: Repository):
    """Test that serial status returns plan details and events."""
    _seed_project(repo)

    create_result = _create_serial_plan(dispatcher)
    serial_plan_id = create_result["data"]["serial_plan_id"]

    result = dispatcher.get_serial_status(serial_plan_id)

    assert result["ok"] is True
    assert result["data"]["serial_plan_id"] == serial_plan_id
    assert result["data"]["status"] == "active"
    assert "events" in result["data"]
    assert len(result["data"]["events"]) >= 1  # At least 'created' event


# ── Test 6: enqueue-next from active creates queue item ───────────────────


def test_enqueue_next_creates_queue_item(dispatcher: Dispatcher, repo: Repository):
    """Test that enqueue-next creates a queue item."""
    _seed_project(repo)

    create_result = _create_serial_plan(dispatcher)
    serial_plan_id = create_result["data"]["serial_plan_id"]

    result = dispatcher.enqueue_serial_next(serial_plan_id)

    assert result["ok"] is True
    assert "queue_id" in result["data"]

    # Verify queue item exists
    queue_item = repo.get_queue_item(result["data"]["queue_id"])
    assert queue_item is not None


# ── Test 7: enqueue-next range calculation correct ───────────────────────


def test_enqueue_next_range_calculation(dispatcher: Dispatcher, repo: Repository):
    """Test that enqueue-next calculates correct ranges: 1-3, 4-6, 10-10."""
    _seed_project(repo)

    # Test 1-3
    create_result = _create_serial_plan(dispatcher, start_chapter=1, target_chapter=10, batch_size=3)
    serial_plan_id = create_result["data"]["serial_plan_id"]

    result = dispatcher.enqueue_serial_next(serial_plan_id)
    assert result["ok"] is True
    assert result["data"]["from_chapter"] == 1
    assert result["data"]["to_chapter"] == 3


def test_enqueue_next_range_final_batch(dispatcher: Dispatcher, repo: Repository):
    """Test that enqueue-next handles final batch correctly (10-10)."""
    _seed_project(repo)

    # Create plan with current_chapter already at 10
    create_result = _create_serial_plan(dispatcher, start_chapter=10, target_chapter=10, batch_size=3)
    serial_plan_id = create_result["data"]["serial_plan_id"]

    result = dispatcher.enqueue_serial_next(serial_plan_id)
    assert result["ok"] is True
    assert result["data"]["from_chapter"] == 10
    assert result["data"]["to_chapter"] == 10


# ── Test 8: enqueue-next sets status to waiting_review ────────────────────


def test_enqueue_next_sets_waiting_review(dispatcher: Dispatcher, repo: Repository):
    """Test that enqueue-next sets status to waiting_review."""
    _seed_project(repo)

    create_result = _create_serial_plan(dispatcher)
    serial_plan_id = create_result["data"]["serial_plan_id"]

    result = dispatcher.enqueue_serial_next(serial_plan_id)

    assert result["ok"] is True
    assert result["data"]["status"] == "waiting_review"

    # Verify in database
    plan = repo.get_serial_plan(serial_plan_id)
    assert plan["status"] == "waiting_review"


# ── Test 9: waiting_review cannot enqueue-next again ──────────────────────


def test_waiting_review_cannot_enqueue_next(dispatcher: Dispatcher, repo: Repository):
    """Test that waiting_review status cannot enqueue-next."""
    _seed_project(repo)

    create_result = _create_serial_plan(dispatcher)
    serial_plan_id = create_result["data"]["serial_plan_id"]

    # First enqueue
    dispatcher.enqueue_serial_next(serial_plan_id)

    # Second enqueue should fail
    result = dispatcher.enqueue_serial_next(serial_plan_id)

    assert result["ok"] is False
    assert "waiting_review" in result["error"]


# ── Test 10: advance approve rejects incomplete queue ─────────────────────


def test_advance_approve_rejects_incomplete_queue(dispatcher: Dispatcher, repo: Repository):
    """Test that advance approve rejects when queue item is not completed."""
    _seed_project(repo)

    create_result = _create_serial_plan(dispatcher)
    serial_plan_id = create_result["data"]["serial_plan_id"]

    dispatcher.enqueue_serial_next(serial_plan_id)

    result = dispatcher.advance_serial_plan(serial_plan_id, decision="approve")

    assert result["ok"] is False
    assert "not completed" in result["error"]


# ── Test 11: advance approve rejects missing production_run_id ────────────


def test_advance_approve_rejects_missing_production_run_id(dispatcher: Dispatcher, repo: Repository):
    """Test that advance approve rejects when production_run_id is missing."""
    _seed_project(repo)

    create_result = _create_serial_plan(dispatcher)
    serial_plan_id = create_result["data"]["serial_plan_id"]

    dispatcher.enqueue_serial_next(serial_plan_id)

    # Manually set queue to completed without production_run_id
    plan = repo.get_serial_plan(serial_plan_id)
    conn = repo._conn()
    conn.execute(
        "UPDATE production_queue SET status = 'completed' WHERE id = ?",
        (plan["current_queue_id"],),
    )
    conn.commit()
    conn.close()

    result = dispatcher.advance_serial_plan(serial_plan_id, decision="approve")

    assert result["ok"] is False
    assert "production_run_id" in result["error"]


# ── Test 12: advance approve rejects continuity gate failed ───────────────


def test_advance_approve_rejects_continuity_gate_failed(dispatcher: Dispatcher, repo: Repository):
    """Test that advance approve rejects when continuity gate is failed."""
    _seed_project(repo)

    create_result = _create_serial_plan(dispatcher)
    serial_plan_id = create_result["data"]["serial_plan_id"]

    dispatcher.enqueue_serial_next(serial_plan_id)

    # Setup: queue completed with production_run_id
    plan = repo.get_serial_plan(serial_plan_id)
    queue_id = plan["current_queue_id"]

    # Create production run
    run_id = "batch_test123"
    conn = repo._conn()
    conn.execute(
        "INSERT INTO production_runs (id, project_id, from_chapter, to_chapter, status, total_chapters, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (run_id, "test_project", 1, 3, "awaiting_review", 3, datetime.now().isoformat(), datetime.now().isoformat()),
    )
    conn.execute(
        "UPDATE production_queue SET status = 'completed', production_run_id = ? WHERE id = ?",
        (run_id, queue_id),
    )
    # Create failed continuity gate
    conn.execute(
        "INSERT INTO batch_continuity_gates (id, run_id, project_id, from_chapter, to_chapter, status, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("gate_test", run_id, "test_project", 1, 3, "failed", datetime.now().isoformat(), datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()

    result = dispatcher.advance_serial_plan(serial_plan_id, decision="approve")

    assert result["ok"] is False
    assert "continuity" in result["error"].lower()


# ── Test 13: advance approve allows continuity gate warning/passed ─────────


def test_advance_approve_allows_continuity_gate_passed(dispatcher: Dispatcher, repo: Repository):
    """Test that advance approve allows continuity gate passed."""
    _seed_project(repo)

    create_result = _create_serial_plan(dispatcher)
    serial_plan_id = create_result["data"]["serial_plan_id"]

    dispatcher.enqueue_serial_next(serial_plan_id)

    plan = repo.get_serial_plan(serial_plan_id)
    queue_id = plan["current_queue_id"]

    run_id = "batch_test123"
    conn = repo._conn()
    conn.execute(
        "INSERT INTO production_runs (id, project_id, from_chapter, to_chapter, status, total_chapters, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (run_id, "test_project", 1, 3, "awaiting_review", 3, datetime.now().isoformat(), datetime.now().isoformat()),
    )
    conn.execute(
        "UPDATE production_queue SET status = 'completed', production_run_id = ? WHERE id = ?",
        (run_id, queue_id),
    )
    # Create passed continuity gate
    conn.execute(
        "INSERT INTO batch_continuity_gates (id, run_id, project_id, from_chapter, to_chapter, status, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("gate_test", run_id, "test_project", 1, 3, "passed", datetime.now().isoformat(), datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()

    result = dispatcher.advance_serial_plan(serial_plan_id, decision="approve")

    assert result["ok"] is True


# ── Test 14: advance approve moves current_chapter forward ────────────────


def test_advance_approve_moves_current_chapter(dispatcher: Dispatcher, repo: Repository):
    """Test that approve moves current_chapter forward."""
    _seed_project(repo)

    create_result = _create_serial_plan(dispatcher, start_chapter=1, target_chapter=10, batch_size=3)
    serial_plan_id = create_result["data"]["serial_plan_id"]

    dispatcher.enqueue_serial_next(serial_plan_id)

    plan = repo.get_serial_plan(serial_plan_id)
    queue_id = plan["current_queue_id"]

    run_id = "batch_test123"
    conn = repo._conn()
    conn.execute(
        "INSERT INTO production_runs (id, project_id, from_chapter, to_chapter, status, total_chapters, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (run_id, "test_project", 1, 3, "awaiting_review", 3, datetime.now().isoformat(), datetime.now().isoformat()),
    )
    conn.execute(
        "UPDATE production_queue SET status = 'completed', production_run_id = ? WHERE id = ?",
        (run_id, queue_id),
    )
    # R1: Multi-chapter batch requires continuity gate
    conn.execute(
        "INSERT INTO batch_continuity_gates (id, run_id, project_id, from_chapter, to_chapter, status, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("gate_test", run_id, "test_project", 1, 3, "passed", datetime.now().isoformat(), datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()

    result = dispatcher.advance_serial_plan(serial_plan_id, decision="approve")

    assert result["ok"] is True
    assert result["data"]["current_chapter"] == 4  # 1 + 3
    assert result["data"]["status"] == "active"


# ── Test 15: advance approve final batch sets completed ───────────────────


def test_advance_approve_final_batch_sets_completed(dispatcher: Dispatcher, repo: Repository):
    """Test that approve on final batch sets status to completed."""
    _seed_project(repo)

    create_result = _create_serial_plan(dispatcher, start_chapter=10, target_chapter=10, batch_size=3)
    serial_plan_id = create_result["data"]["serial_plan_id"]

    dispatcher.enqueue_serial_next(serial_plan_id)

    plan = repo.get_serial_plan(serial_plan_id)
    queue_id = plan["current_queue_id"]

    run_id = "batch_test123"
    conn = repo._conn()
    conn.execute(
        "INSERT INTO production_runs (id, project_id, from_chapter, to_chapter, status, total_chapters, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (run_id, "test_project", 10, 10, "awaiting_review", 1, datetime.now().isoformat(), datetime.now().isoformat()),
    )
    conn.execute(
        "UPDATE production_queue SET status = 'completed', production_run_id = ? WHERE id = ?",
        (run_id, queue_id),
    )
    conn.commit()
    conn.close()

    result = dispatcher.advance_serial_plan(serial_plan_id, decision="approve")

    assert result["ok"] is True
    assert result["data"]["status"] == "completed"


# ── Test 16: request_changes keeps waiting_review ─────────────────────────


def test_request_changes_keeps_waiting_review(dispatcher: Dispatcher, repo: Repository):
    """Test that request_changes keeps status as waiting_review."""
    _seed_project(repo)

    create_result = _create_serial_plan(dispatcher)
    serial_plan_id = create_result["data"]["serial_plan_id"]

    dispatcher.enqueue_serial_next(serial_plan_id)

    result = dispatcher.advance_serial_plan(serial_plan_id, decision="request_changes", notes="需要修改")

    assert result["ok"] is True
    assert result["data"]["status"] == "waiting_review"

    # Verify no automatic revision plan created
    plan = repo.get_serial_plan(serial_plan_id)
    assert plan["status"] == "waiting_review"


# ── Test 17: pause active succeeds ───────────────────────────────────────


def test_pause_active_succeeds(dispatcher: Dispatcher, repo: Repository):
    """Test that pause works on active status."""
    _seed_project(repo)

    create_result = _create_serial_plan(dispatcher)
    serial_plan_id = create_result["data"]["serial_plan_id"]

    result = dispatcher.pause_serial_plan(serial_plan_id)

    assert result["ok"] is True
    assert result["data"]["status"] == "paused"


# ── Test 18: resume paused succeeds ──────────────────────────────────────


def test_resume_paused_succeeds(dispatcher: Dispatcher, repo: Repository):
    """Test that resume works on paused status."""
    _seed_project(repo)

    create_result = _create_serial_plan(dispatcher)
    serial_plan_id = create_result["data"]["serial_plan_id"]

    dispatcher.pause_serial_plan(serial_plan_id)

    result = dispatcher.resume_serial_plan(serial_plan_id)

    assert result["ok"] is True
    assert result["data"]["status"] == "active"


# ── Test 19: cancel active/waiting_review succeeds ────────────────────────


def test_cancel_active_succeeds(dispatcher: Dispatcher, repo: Repository):
    """Test that cancel works on active status."""
    _seed_project(repo)

    create_result = _create_serial_plan(dispatcher)
    serial_plan_id = create_result["data"]["serial_plan_id"]

    result = dispatcher.cancel_serial_plan(serial_plan_id, reason="manual stop")

    assert result["ok"] is True
    assert result["data"]["status"] == "cancelled"


def test_cancel_waiting_review_succeeds(dispatcher: Dispatcher, repo: Repository):
    """Test that cancel works on waiting_review status."""
    _seed_project(repo)

    create_result = _create_serial_plan(dispatcher)
    serial_plan_id = create_result["data"]["serial_plan_id"]

    dispatcher.enqueue_serial_next(serial_plan_id)

    result = dispatcher.cancel_serial_plan(serial_plan_id, reason="manual stop")

    assert result["ok"] is True
    assert result["data"]["status"] == "cancelled"


# ── Test 20: completed/cancelled cannot advance/enqueue-next ──────────────


def test_completed_cannot_enqueue_next(dispatcher: Dispatcher, repo: Repository):
    """Test that completed status cannot enqueue-next."""
    _seed_project(repo)

    create_result = _create_serial_plan(dispatcher, start_chapter=10, target_chapter=10, batch_size=3)
    serial_plan_id = create_result["data"]["serial_plan_id"]

    dispatcher.enqueue_serial_next(serial_plan_id)

    plan = repo.get_serial_plan(serial_plan_id)
    queue_id = plan["current_queue_id"]

    run_id = "batch_test123"
    conn = repo._conn()
    conn.execute(
        "INSERT INTO production_runs (id, project_id, from_chapter, to_chapter, status, total_chapters, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (run_id, "test_project", 10, 10, "awaiting_review", 1, datetime.now().isoformat(), datetime.now().isoformat()),
    )
    conn.execute(
        "UPDATE production_queue SET status = 'completed', production_run_id = ? WHERE id = ?",
        (run_id, queue_id),
    )
    conn.commit()
    conn.close()

    dispatcher.advance_serial_plan(serial_plan_id, decision="approve")

    # Try to enqueue-next again
    result = dispatcher.enqueue_serial_next(serial_plan_id)

    assert result["ok"] is False


def test_cancelled_cannot_advance(dispatcher: Dispatcher, repo: Repository):
    """Test that cancelled status cannot advance."""
    _seed_project(repo)

    create_result = _create_serial_plan(dispatcher)
    serial_plan_id = create_result["data"]["serial_plan_id"]

    dispatcher.cancel_serial_plan(serial_plan_id)

    result = dispatcher.advance_serial_plan(serial_plan_id, decision="approve")

    assert result["ok"] is False


# ── Test 21: CLI JSON envelope for all commands ───────────────────────────


def test_cli_serial_create_json(tmp_db: Path):
    """Test serial create CLI with --json."""
    repo = Repository(str(tmp_db))
    _seed_project(repo)

    result = subprocess.run(
        [sys.executable, "-m", "novel_factory.cli", "--db-path", str(tmp_db),
         "serial", "create",
         "--project-id", "test_project",
         "--name", "Test Plan",
         "--start-chapter", "1",
         "--target-chapter", "10",
         "--batch-size", "3",
         "--json"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["ok"] is True
    assert "serial_plan_id" in output["data"]


def test_cli_serial_status_json(tmp_db: Path):
    """Test serial status CLI with --json."""
    repo = Repository(str(tmp_db))
    _seed_project(repo)

    # Create plan first
    dispatcher = Dispatcher(repo, llm=StubLLM())
    create_result = dispatcher.create_serial_plan(
        project_id="test_project",
        name="Test Plan",
        start_chapter=1,
        target_chapter=10,
        batch_size=3,
    )
    serial_plan_id = create_result["data"]["serial_plan_id"]

    result = subprocess.run(
        [sys.executable, "-m", "novel_factory.cli", "--db-path", str(tmp_db),
         "serial", "status",
         "--serial-plan-id", serial_plan_id,
         "--json"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["ok"] is True
    assert output["data"]["serial_plan_id"] == serial_plan_id


def test_cli_serial_enqueue_next_json(tmp_db: Path):
    """Test serial enqueue-next CLI with --json."""
    repo = Repository(str(tmp_db))
    _seed_project(repo)

    dispatcher = Dispatcher(repo, llm=StubLLM())
    create_result = dispatcher.create_serial_plan(
        project_id="test_project",
        name="Test Plan",
        start_chapter=1,
        target_chapter=10,
        batch_size=3,
    )
    serial_plan_id = create_result["data"]["serial_plan_id"]

    result = subprocess.run(
        [sys.executable, "-m", "novel_factory.cli", "--db-path", str(tmp_db),
         "serial", "enqueue-next",
         "--serial-plan-id", serial_plan_id,
         "--json"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["ok"] is True
    assert "queue_id" in output["data"]


def test_cli_serial_advance_json(tmp_db: Path):
    """Test serial advance CLI with --json."""
    repo = Repository(str(tmp_db))
    _seed_project(repo)

    dispatcher = Dispatcher(repo, llm=StubLLM())
    create_result = dispatcher.create_serial_plan(
        project_id="test_project",
        name="Test Plan",
        start_chapter=1,
        target_chapter=10,
        batch_size=3,
    )
    serial_plan_id = create_result["data"]["serial_plan_id"]

    dispatcher.enqueue_serial_next(serial_plan_id)

    result = subprocess.run(
        [sys.executable, "-m", "novel_factory.cli", "--db-path", str(tmp_db),
         "serial", "advance",
         "--serial-plan-id", serial_plan_id,
         "--decision", "request_changes",
         "--json"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["ok"] is True


def test_cli_serial_pause_json(tmp_db: Path):
    """Test serial pause CLI with --json."""
    repo = Repository(str(tmp_db))
    _seed_project(repo)

    dispatcher = Dispatcher(repo, llm=StubLLM())
    create_result = dispatcher.create_serial_plan(
        project_id="test_project",
        name="Test Plan",
        start_chapter=1,
        target_chapter=10,
        batch_size=3,
    )
    serial_plan_id = create_result["data"]["serial_plan_id"]

    result = subprocess.run(
        [sys.executable, "-m", "novel_factory.cli", "--db-path", str(tmp_db),
         "serial", "pause",
         "--serial-plan-id", serial_plan_id,
         "--json"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["ok"] is True


def test_cli_serial_resume_json(tmp_db: Path):
    """Test serial resume CLI with --json."""
    repo = Repository(str(tmp_db))
    _seed_project(repo)

    dispatcher = Dispatcher(repo, llm=StubLLM())
    create_result = dispatcher.create_serial_plan(
        project_id="test_project",
        name="Test Plan",
        start_chapter=1,
        target_chapter=10,
        batch_size=3,
    )
    serial_plan_id = create_result["data"]["serial_plan_id"]

    dispatcher.pause_serial_plan(serial_plan_id)

    result = subprocess.run(
        [sys.executable, "-m", "novel_factory.cli", "--db-path", str(tmp_db),
         "serial", "resume",
         "--serial-plan-id", serial_plan_id,
         "--json"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["ok"] is True


def test_cli_serial_cancel_json(tmp_db: Path):
    """Test serial cancel CLI with --json."""
    repo = Repository(str(tmp_db))
    _seed_project(repo)

    dispatcher = Dispatcher(repo, llm=StubLLM())
    create_result = dispatcher.create_serial_plan(
        project_id="test_project",
        name="Test Plan",
        start_chapter=1,
        target_chapter=10,
        batch_size=3,
    )
    serial_plan_id = create_result["data"]["serial_plan_id"]

    result = subprocess.run(
        [sys.executable, "-m", "novel_factory.cli", "--db-path", str(tmp_db),
         "serial", "cancel",
         "--serial-plan-id", serial_plan_id,
         "--reason", "manual stop",
         "--json"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["ok"] is True


# ── Test 22: argparse missing param JSON envelope ────────────────────────


def test_cli_serial_create_missing_param_json(tmp_db: Path):
    """Test serial create CLI with missing --project-id returns JSON error."""
    result = subprocess.run(
        [sys.executable, "-m", "novel_factory.cli", "--db-path", str(tmp_db),
         "serial", "create",
         "--name", "Test Plan",
         "--start-chapter", "1",
         "--target-chapter", "10",
         "--batch-size", "3",
         "--json"],
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    output = json.loads(result.stdout)
    assert output["ok"] is False
    assert "required" in output["error"].lower()


# ── R1/R2/R3 Rework Tests ────────────────────────────────────────────────


def test_r1_multi_chapter_approve_requires_continuity_gate(dispatcher: Dispatcher, repo: Repository):
    """R1: Multi-chapter batch approve MUST require continuity gate."""
    _seed_project(repo)

    create_result = _create_serial_plan(dispatcher, start_chapter=1, target_chapter=10, batch_size=3)
    serial_plan_id = create_result["data"]["serial_plan_id"]

    dispatcher.enqueue_serial_next(serial_plan_id)

    plan = repo.get_serial_plan(serial_plan_id)
    queue_id = plan["current_queue_id"]

    run_id = "batch_test123"
    conn = repo._conn()
    conn.execute(
        "INSERT INTO production_runs (id, project_id, from_chapter, to_chapter, status, total_chapters, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (run_id, "test_project", 1, 3, "awaiting_review", 3, datetime.now().isoformat(), datetime.now().isoformat()),
    )
    conn.execute(
        "UPDATE production_queue SET status = 'completed', production_run_id = ? WHERE id = ?",
        (run_id, queue_id),
    )
    conn.commit()
    conn.close()

    # Try to approve WITHOUT continuity gate - should fail
    result = dispatcher.advance_serial_plan(serial_plan_id, decision="approve")

    assert result["ok"] is False
    assert "continuity gate" in result["error"].lower()


def test_r2_event_write_failure_in_create_serial_plan(dispatcher: Dispatcher, repo: Repository):
    """R2: create_serial_plan must rollback if event write fails."""
    _seed_project(repo)

    # Mock record_serial_plan_event to return None (failure)
    with patch.object(repo, 'record_serial_plan_event', return_value=None):
        result = dispatcher.create_serial_plan(
            project_id="test_project",
            name="Test Plan",
            start_chapter=1,
            target_chapter=10,
            batch_size=3,
        )

        assert result["ok"] is False
        assert "event" in result["error"].lower()

        # Verify serial plan was rolled back (cancelled)
        plans = repo.list_serial_plans(project_id="test_project")
        # Plan should exist but be cancelled
        assert len(plans) == 1
        assert plans[0]["status"] == "cancelled"


def test_r2_event_write_failure_in_enqueue_serial_next(dispatcher: Dispatcher, repo: Repository):
    """R2: enqueue_serial_next must rollback and cancel queue item if event write fails."""
    _seed_project(repo)

    create_result = _create_serial_plan(dispatcher)
    serial_plan_id = create_result["data"]["serial_plan_id"]

    # Mock record_serial_plan_event to return None (failure) for enqueue event
    # We need to mock on the dispatcher's repo instance
    with patch.object(dispatcher.repo, 'record_serial_plan_event', return_value=None):
        result = dispatcher.enqueue_serial_next(serial_plan_id)

        assert result["ok"] is False
        assert "event" in result["error"].lower()

        # Verify serial plan status reverted to active
        plan = repo.get_serial_plan(serial_plan_id)
        assert plan["status"] == "active"
        assert plan["current_queue_id"] is None


def test_r3_enqueue_next_update_failure_compensates_queue_item(dispatcher: Dispatcher, repo: Repository):
    """R3: enqueue_serial_next must cancel queue item if serial plan update fails."""
    _seed_project(repo)

    create_result = _create_serial_plan(dispatcher)
    serial_plan_id = create_result["data"]["serial_plan_id"]

    # Mock update_serial_plan to return False (failure) for enqueue update
    # We need to mock on the dispatcher's repo instance
    with patch.object(dispatcher.repo, 'update_serial_plan', return_value=False):
        result = dispatcher.enqueue_serial_next(serial_plan_id)

        assert result["ok"] is False
        assert "update" in result["error"].lower()

        # Verify queue item was cancelled - use list_queue_items to find it
        queue_items = repo.list_queue_items(project_id="test_project")
        assert len(queue_items) > 0
        # The most recent queue item should be cancelled
        queue_item = queue_items[0]
        assert queue_item["status"] == "cancelled"


def test_r2_event_write_failure_in_advance_approve(dispatcher: Dispatcher, repo: Repository):
    """R2: advance_serial_plan approve must rollback if event write fails."""
    _seed_project(repo)

    create_result = _create_serial_plan(dispatcher, start_chapter=1, target_chapter=10, batch_size=3)
    serial_plan_id = create_result["data"]["serial_plan_id"]

    dispatcher.enqueue_serial_next(serial_plan_id)

    plan = repo.get_serial_plan(serial_plan_id)
    queue_id = plan["current_queue_id"]

    run_id = "batch_test123"
    conn = repo._conn()
    conn.execute(
        "INSERT INTO production_runs (id, project_id, from_chapter, to_chapter, status, total_chapters, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (run_id, "test_project", 1, 3, "awaiting_review", 3, datetime.now().isoformat(), datetime.now().isoformat()),
    )
    conn.execute(
        "UPDATE production_queue SET status = 'completed', production_run_id = ? WHERE id = ?",
        (run_id, queue_id),
    )
    # Add continuity gate
    conn.execute(
        "INSERT INTO batch_continuity_gates (id, run_id, project_id, from_chapter, to_chapter, status, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("gate_test", run_id, "test_project", 1, 3, "passed", datetime.now().isoformat(), datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()

    # Mock record_serial_plan_event to return None (failure)
    with patch.object(repo, 'record_serial_plan_event', return_value=None):
        result = dispatcher.advance_serial_plan(serial_plan_id, decision="approve")

        assert result["ok"] is False
        assert "event" in result["error"].lower()

        # Verify serial plan status reverted to waiting_review
        plan = repo.get_serial_plan(serial_plan_id)
        assert plan["status"] == "waiting_review"
        assert plan["current_chapter"] == 1  # Original value
        assert plan["completed_chapters"] == 0  # Original value


def test_r2_event_write_failure_in_pause_serial_plan(dispatcher: Dispatcher, repo: Repository):
    """R2: pause_serial_plan must rollback if event write fails."""
    _seed_project(repo)

    create_result = _create_serial_plan(dispatcher)
    serial_plan_id = create_result["data"]["serial_plan_id"]

    # Mock record_serial_plan_event to return None (failure)
    with patch.object(repo, 'record_serial_plan_event', return_value=None):
        result = dispatcher.pause_serial_plan(serial_plan_id)

        assert result["ok"] is False
        assert "event" in result["error"].lower()

        # Verify serial plan status reverted to active
        plan = repo.get_serial_plan(serial_plan_id)
        assert plan["status"] == "active"


def test_r2_event_write_failure_in_resume_serial_plan(dispatcher: Dispatcher, repo: Repository):
    """R2: resume_serial_plan must rollback if event write fails."""
    _seed_project(repo)

    create_result = _create_serial_plan(dispatcher)
    serial_plan_id = create_result["data"]["serial_plan_id"]

    # First pause successfully
    dispatcher.pause_serial_plan(serial_plan_id)

    # Mock record_serial_plan_event to return None (failure) for resume
    with patch.object(repo, 'record_serial_plan_event', return_value=None):
        result = dispatcher.resume_serial_plan(serial_plan_id)

        assert result["ok"] is False
        assert "event" in result["error"].lower()

        # Verify serial plan status reverted to paused
        plan = repo.get_serial_plan(serial_plan_id)
        assert plan["status"] == "paused"


def test_r2_event_write_failure_in_cancel_serial_plan(dispatcher: Dispatcher, repo: Repository):
    """R2: cancel_serial_plan must rollback if event write fails."""
    _seed_project(repo)

    create_result = _create_serial_plan(dispatcher)
    serial_plan_id = create_result["data"]["serial_plan_id"]

    # Mock record_serial_plan_event to return None (failure)
    with patch.object(repo, 'record_serial_plan_event', return_value=None):
        result = dispatcher.cancel_serial_plan(serial_plan_id, reason="test")

        assert result["ok"] is False
        assert "event" in result["error"].lower()

        # Verify serial plan status reverted to active
        plan = repo.get_serial_plan(serial_plan_id)
        assert plan["status"] == "active"


# ── Compensation Failure Tests ─────────────────────────────────────────


def test_compensation_queue_cancel_fails(dispatcher: Dispatcher, repo: Repository):
    """Test that queue compensation failure is reported when update_serial_plan fails."""
    _seed_project(repo)

    create_result = _create_serial_plan(dispatcher)
    serial_plan_id = create_result["data"]["serial_plan_id"]

    # Mock both update_serial_plan and update_queue_item to fail
    with patch.object(dispatcher.repo, 'update_serial_plan', return_value=False):
        with patch.object(dispatcher.repo, 'update_queue_item', return_value=False):
            result = dispatcher.enqueue_serial_next(serial_plan_id)

            assert result["ok"] is False
            assert "compensation failed" in result["error"].lower()
            assert result["data"].get("compensation_failed") is True


def test_compensation_queue_event_fails(dispatcher: Dispatcher, repo: Repository):
    """Test that queue event compensation failure is reported."""
    _seed_project(repo)

    create_result = _create_serial_plan(dispatcher)
    serial_plan_id = create_result["data"]["serial_plan_id"]

    # Mock update_serial_plan to fail, but update_queue_item succeeds, record_queue_event fails
    # We need to allow the first record_queue_event call (from enqueue_batch) to succeed
    original_record = repo.record_queue_event
    record_call_count = [0]
    
    def mock_record(*args, **kwargs):
        record_call_count[0] += 1
        # First call is from enqueue_batch (should succeed)
        # Second call is the compensation event (should fail)
        if record_call_count[0] == 1:
            return original_record(*args, **kwargs)
        return None  # Compensation event fails
    
    with patch.object(dispatcher.repo, 'update_serial_plan', return_value=False):
        with patch.object(dispatcher.repo, 'record_queue_event', side_effect=mock_record):
            result = dispatcher.enqueue_serial_next(serial_plan_id)

            assert result["ok"] is False
            assert "compensation event failed" in result["error"].lower()
            assert result["data"].get("compensation_failed") is True


def test_compensation_rollback_fails_in_approve(dispatcher: Dispatcher, repo: Repository):
    """Test that rollback failure is reported when approve event fails."""
    _seed_project(repo)

    create_result = _create_serial_plan(dispatcher, start_chapter=1, target_chapter=10, batch_size=3)
    serial_plan_id = create_result["data"]["serial_plan_id"]

    dispatcher.enqueue_serial_next(serial_plan_id)

    plan = repo.get_serial_plan(serial_plan_id)
    queue_id = plan["current_queue_id"]

    run_id = "batch_test123"
    conn = repo._conn()
    conn.execute(
        "INSERT INTO production_runs (id, project_id, from_chapter, to_chapter, status, total_chapters, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (run_id, "test_project", 1, 3, "awaiting_review", 3, datetime.now().isoformat(), datetime.now().isoformat()),
    )
    conn.execute(
        "UPDATE production_queue SET status = 'completed', production_run_id = ? WHERE id = ?",
        (run_id, queue_id),
    )
    conn.execute(
        "INSERT INTO batch_continuity_gates (id, run_id, project_id, from_chapter, to_chapter, status, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("gate_test", run_id, "test_project", 1, 3, "passed", datetime.now().isoformat(), datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()

    # First mock record_serial_plan_event to fail for approve event
    # Then mock update_serial_plan to fail for rollback
    original_update = repo.update_serial_plan
    update_call_count = [0]
    
    def mock_update(*args, **kwargs):
        update_call_count[0] += 1
        # First call is the approve update (should succeed)
        # Second call is the rollback (should fail)
        if update_call_count[0] == 1:
            return original_update(*args, **kwargs)
        return False  # Rollback fails
    
    with patch.object(repo, 'record_serial_plan_event', return_value=None):
        with patch.object(repo, 'update_serial_plan', side_effect=mock_update):
            result = dispatcher.advance_serial_plan(serial_plan_id, decision="approve")

            assert result["ok"] is False
            assert "rollback failed" in result["error"].lower()
            assert result["data"].get("compensation_failed") is True


def test_compensation_rollback_fails_in_pause(dispatcher: Dispatcher, repo: Repository):
    """Test that rollback failure is reported when pause event fails."""
    _seed_project(repo)

    create_result = _create_serial_plan(dispatcher)
    serial_plan_id = create_result["data"]["serial_plan_id"]

    # First mock record_serial_plan_event to fail for pause event
    # Then mock update_serial_plan to fail for rollback
    original_update = repo.update_serial_plan
    update_call_count = [0]
    
    def mock_update(*args, **kwargs):
        update_call_count[0] += 1
        # First call is the pause update (should succeed)
        # Second call is the rollback (should fail)
        if update_call_count[0] == 1:
            return original_update(*args, **kwargs)
        return False  # Rollback fails
    
    with patch.object(repo, 'record_serial_plan_event', return_value=None):
        with patch.object(repo, 'update_serial_plan', side_effect=mock_update):
            result = dispatcher.pause_serial_plan(serial_plan_id)

            assert result["ok"] is False
            assert "rollback failed" in result["error"].lower()
            assert result["data"].get("compensation_failed") is True


def test_compensation_rollback_fails_in_enqueue_event(dispatcher: Dispatcher, repo: Repository):
    """Test that rollback failure is reported when enqueue event fails."""
    _seed_project(repo)

    create_result = _create_serial_plan(dispatcher)
    serial_plan_id = create_result["data"]["serial_plan_id"]

    # First mock record_serial_plan_event to fail for enqueue event
    # Then mock update_serial_plan to fail for rollback
    original_update = repo.update_serial_plan
    update_call_count = [0]
    
    def mock_update(*args, **kwargs):
        update_call_count[0] += 1
        # First call is the enqueue update (should succeed)
        # Second call is the rollback (should fail)
        if update_call_count[0] == 1:
            return original_update(*args, **kwargs)
        return False  # Rollback fails
    
    with patch.object(repo, 'record_serial_plan_event', return_value=None):
        with patch.object(repo, 'update_serial_plan', side_effect=mock_update):
            result = dispatcher.enqueue_serial_next(serial_plan_id)

            assert result["ok"] is False
            assert "rollback failed" in result["error"].lower()
            assert result["data"].get("compensation_failed") is True


def test_compensation_rollback_fails_in_create(dispatcher: Dispatcher, repo: Repository):
    """Test that rollback failure is reported when create event fails."""
    _seed_project(repo)

    # Mock both record_serial_plan_event and update_serial_plan (rollback) to fail
    with patch.object(repo, 'record_serial_plan_event', return_value=None):
        with patch.object(repo, 'update_serial_plan', return_value=False):
            result = dispatcher.create_serial_plan(
                project_id="test_project",
                name="Test Plan",
                start_chapter=1,
                target_chapter=10,
                batch_size=3,
            )

            assert result["ok"] is False
            assert "cancellation failed" in result["error"].lower()
            assert result["data"].get("compensation_failed") is True

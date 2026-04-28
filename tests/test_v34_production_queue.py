"""Tests for v3.4 Production Queue functionality.

Covers:
- Migration 010 idempotency
- enqueue success and max_chapters guard
- queue-status
- queue-run idle, success, failure
- pause/resume/retry
- timeout event writing
- Event write failure handling
- production_run_id write failure handling
- CLI JSON envelope
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from novel_factory.db.connection import get_connection, init_db
from novel_factory.db.repository import Repository
from novel_factory.dispatcher import Dispatcher
from novel_factory.llm.provider import LLMProvider

from tests.conftest import LONG_CHAPTER_CONTENT  # noqa: F401


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
            # v5.3.0: Must be >= word_target * 0.85 (word_target defaults to 2500)
            return {
                "title": "测试章", "content": LONG_CHAPTER_CONTENT,
                "word_count": len(LONG_CHAPTER_CONTENT), "implemented_events": ["事件1"], "used_plot_refs": [],
            }
        if "Polisher" in schema_name:
            # v5.3.0: Must be >= word_target * 0.85
            return {
                "content": LONG_CHAPTER_CONTENT,
                "fact_change_risk": "none", "changed_scope": ["sentence"], "summary": "微调",
            }
        if "Editor" in schema_name:
            return {
                "pass": True, "score": 92,
                "scores": {"setting": 20, "logic": 20, "poison": 18, "text": 17, "pacing": 17},
                "issues": [], "suggestions": [],
                "revision_target": None, "state_card": {},
            }
        return {}

    def invoke_text(self, messages, temperature=None, max_tokens=None) -> str:
        return "{}"


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary database for testing."""
    db_path = tmp_path / "test.db"
    init_db(db_path)
    return db_path


@pytest.fixture
def repo(tmp_db):
    """Create a Repository instance."""
    return Repository(tmp_db)


@pytest.fixture
def dispatcher(repo):
    """Create a Dispatcher instance with stub LLM."""
    return Dispatcher(repo, StubLLM(), max_retries=3)


def _seed_project(repo, project_id="test-project"):
    """Seed a project directly via SQL."""
    conn = repo._conn()
    conn.execute(
        "INSERT INTO projects (project_id, name, genre, is_current) VALUES (?, ?, ?, 1)",
        (project_id, "Test Novel", "fantasy"),
    )
    conn.commit()
    conn.close()


def _seed_chapter(repo, project_id="test-project", chapter_number=1, status="planned"):
    """Seed a chapter directly via SQL."""
    conn = repo._conn()
    conn.execute(
        "INSERT INTO chapters (project_id, chapter_number, title, status) "
        "VALUES (?, ?, ?, ?)",
        (project_id, chapter_number, f"第{chapter_number}章", status),
    )
    conn.execute(
        "INSERT INTO instructions (project_id, chapter_number, objective, key_events, "
        "plots_to_plant, plots_to_resolve, ending_hook, word_target, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active')",
        (project_id, chapter_number, "推进剧情", '["事件1"]', '[]', '[]', "悬念", 2500),
    )
    conn.commit()
    conn.close()


class TestMigration010Idempotency:
    """Test that migration 010 can be applied multiple times."""

    def test_production_queue_table_exists(self, tmp_db):
        """Verify production_queue table exists after init_db."""
        conn = get_connection(tmp_db)
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        ]
        conn.close()
        assert "production_queue" in tables

    def test_production_queue_events_table_exists(self, tmp_db):
        """Verify production_queue_events table exists after init_db."""
        conn = get_connection(tmp_db)
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        ]
        conn.close()
        assert "production_queue_events" in tables

    def test_init_db_twice_no_error(self, tmp_db):
        """init_db called twice should not raise."""
        # Second call
        init_db(tmp_db)
        # Verify tables still exist
        conn = get_connection(tmp_db)
        count = conn.execute(
            "SELECT COUNT(*) FROM production_queue"
        ).fetchone()[0]
        conn.close()
        assert count == 0


class TestEnqueue:
    """Test enqueue functionality."""

    def test_enqueue_success(self, repo, dispatcher):
        """Test successful enqueue."""
        # Create a project first
        _seed_project(repo)

        result = dispatcher.enqueue_batch(
            project_id="test-project",
            from_chapter=1,
            to_chapter=5,
            priority=100,
            max_attempts=3,
            timeout_minutes=120,
            max_chapters=50,
        )

        assert result["ok"] is True
        assert "queue_id" in result["data"]
        assert result["data"]["status"] == "pending"

        # Verify event was recorded
        events = repo.get_queue_events(result["data"]["queue_id"])
        assert len(events) == 1
        assert events[0]["event_type"] == "enqueued"

    def test_enqueue_max_chapters_guard(self, repo, dispatcher):
        """Test that enqueue rejects batches exceeding max_chapters."""
        _seed_project(repo)

        result = dispatcher.enqueue_batch(
            project_id="test-project",
            from_chapter=1,
            to_chapter=100,  # 100 chapters > default max_chapters=50
            priority=100,
            max_attempts=3,
            timeout_minutes=120,
            max_chapters=50,
        )

        assert result["ok"] is False
        assert "exceeds max_chapters" in result["error"]

    def test_enqueue_event_failure_returns_error(self, repo, dispatcher):
        """Test that event write failure returns ok=false."""
        _seed_project(repo)

        # Mock record_queue_event to return None
        with patch.object(repo, 'record_queue_event', return_value=None):
            result = dispatcher.enqueue_batch(
                project_id="test-project",
                from_chapter=1,
                to_chapter=5,
                priority=100,
                max_attempts=3,
                timeout_minutes=120,
                max_chapters=50,
            )

        assert result["ok"] is False
        assert "failed to record 'enqueued' event" in result["error"]


class TestQueueStatus:
    """Test queue-status functionality."""

    def test_queue_status_empty(self, dispatcher):
        """Test queue status when empty."""
        result = dispatcher.get_queue_status()
        assert result["ok"] is True
        assert result["data"]["items"] == []

    def test_queue_status_with_items(self, repo, dispatcher):
        """Test queue status with items."""
        _seed_project(repo)

        # Enqueue an item
        enqueue_result = dispatcher.enqueue_batch(
            project_id="test-project",
            from_chapter=1,
            to_chapter=5,
        )
        queue_id = enqueue_result["data"]["queue_id"]

        result = dispatcher.get_queue_status()
        assert result["ok"] is True
        assert len(result["data"]["items"]) == 1
        assert result["data"]["items"][0]["queue_id"] == queue_id

    def test_queue_status_filter_by_status(self, repo, dispatcher):
        """Test queue status filtering by status."""
        _seed_project(repo)

        # Enqueue and then pause
        enqueue_result = dispatcher.enqueue_batch(
            project_id="test-project",
            from_chapter=1,
            to_chapter=5,
        )
        queue_id = enqueue_result["data"]["queue_id"]
        dispatcher.pause_queue_item(queue_id)

        # Filter by paused
        result = dispatcher.get_queue_status(status="paused")
        assert result["ok"] is True
        assert len(result["data"]["items"]) == 1

        # Filter by pending (should be empty)
        result = dispatcher.get_queue_status(status="pending")
        assert result["ok"] is True
        assert len(result["data"]["items"]) == 0


class TestQueueRun:
    """Test queue-run functionality."""

    def test_queue_run_idle(self, dispatcher):
        """Test queue-run when no pending items."""
        result = dispatcher.run_queue_once()
        assert result["ok"] is True
        assert result["data"]["status"] == "idle"

    def test_queue_run_success_and_production_run_id(self, repo, dispatcher):
        """Test successful queue-run with production_run_id association."""
        _seed_project(repo)
        _seed_chapter(repo, chapter_number=1)

        # Enqueue
        enqueue_result = dispatcher.enqueue_batch(
            project_id="test-project",
            from_chapter=1,
            to_chapter=1,
        )
        queue_id = enqueue_result["data"]["queue_id"]

        # Run
        result = dispatcher.run_queue_once()
        assert result["ok"] is True
        assert result["data"]["status"] == "completed"
        assert "production_run_id" in result["data"]

        # Verify queue item has production_run_id
        item = repo.get_queue_item(queue_id)
        assert item["production_run_id"] is not None
        assert item["production_run_id"] == result["data"]["production_run_id"]

    def test_queue_run_failure(self, repo, dispatcher):
        """Test queue-run when batch fails."""
        _seed_project(repo)
        # Don't seed chapter - will fail

        # Enqueue
        enqueue_result = dispatcher.enqueue_batch(
            project_id="test-project",
            from_chapter=1,
            to_chapter=1,
        )
        queue_id = enqueue_result["data"]["queue_id"]

        # Run - should fail because chapter doesn't exist
        result = dispatcher.run_queue_once()
        assert result["ok"] is False
        assert result["data"]["status"] == "failed"

        # Verify event
        events = repo.get_queue_events(queue_id)
        event_types = [e["event_type"] for e in events]
        assert "started" in event_types
        assert "failed" in event_types

    def test_queue_run_started_event_failure_rollback(self, repo, dispatcher):
        """Test that started event failure rolls back status."""
        _seed_project(repo)
        _seed_chapter(repo, chapter_number=1)  # Seed chapter so batch can succeed

        # Enqueue
        enqueue_result = dispatcher.enqueue_batch(
            project_id="test-project",
            from_chapter=1,
            to_chapter=1,
        )
        queue_id = enqueue_result["data"]["queue_id"]

        # Mock record_queue_event to fail only for 'started' event
        original_record = repo.record_queue_event

        def mock_record(*args, **kwargs):
            event_type = kwargs.get('event_type', args[1] if len(args) > 1 else None)
            if event_type == "started":
                return None
            return original_record(*args, **kwargs)

        with patch.object(repo, 'record_queue_event', side_effect=mock_record):
            result = dispatcher.run_queue_once()

        assert result["ok"] is False
        assert "failed to record 'started' event" in result["error"].lower()

        # Verify item was rolled back to pending
        item = repo.get_queue_item(queue_id)
        assert item["status"] == "pending"
        assert item["locked_at"] is None


class TestPauseResume:
    """Test pause/resume functionality."""

    def test_pause_pending(self, repo, dispatcher):
        """Test pausing a pending item."""
        _seed_project(repo)

        enqueue_result = dispatcher.enqueue_batch(
            project_id="test-project",
            from_chapter=1,
            to_chapter=5,
        )
        queue_id = enqueue_result["data"]["queue_id"]

        result = dispatcher.pause_queue_item(queue_id)
        assert result["ok"] is True
        assert result["data"]["status"] == "paused"

        # Verify event
        events = repo.get_queue_events(queue_id)
        event_types = [e["event_type"] for e in events]
        assert "paused" in event_types

    def test_resume_paused(self, repo, dispatcher):
        """Test resuming a paused item."""
        _seed_project(repo)

        enqueue_result = dispatcher.enqueue_batch(
            project_id="test-project",
            from_chapter=1,
            to_chapter=5,
        )
        queue_id = enqueue_result["data"]["queue_id"]

        dispatcher.pause_queue_item(queue_id)
        result = dispatcher.resume_queue_item(queue_id)

        assert result["ok"] is True
        assert result["data"]["status"] == "pending"

        # Verify events
        events = repo.get_queue_events(queue_id)
        event_types = [e["event_type"] for e in events]
        assert "resumed" in event_types

    def test_pause_event_failure_returns_error(self, repo, dispatcher):
        """Test that pause event failure returns ok=false."""
        _seed_project(repo)

        enqueue_result = dispatcher.enqueue_batch(
            project_id="test-project",
            from_chapter=1,
            to_chapter=5,
        )
        queue_id = enqueue_result["data"]["queue_id"]

        with patch.object(repo, 'record_queue_event', return_value=None):
            result = dispatcher.pause_queue_item(queue_id)

        assert result["ok"] is False
        assert "failed to record 'paused' event" in result["error"]


class TestRetry:
    """Test retry functionality."""

    def test_retry_failed(self, repo, dispatcher):
        """Test retrying a failed item."""
        _seed_project(repo)

        enqueue_result = dispatcher.enqueue_batch(
            project_id="test-project",
            from_chapter=1,
            to_chapter=1,
        )
        queue_id = enqueue_result["data"]["queue_id"]

        # Manually set to failed
        repo.update_queue_item(queue_id, status="failed", last_error="Test error")

        result = dispatcher.retry_queue_item(queue_id)
        assert result["ok"] is True
        assert result["data"]["status"] == "pending"
        assert result["data"]["attempt_count"] == 1

    def test_retry_timeout(self, repo, dispatcher):
        """Test retrying a timed-out item."""
        _seed_project(repo)

        enqueue_result = dispatcher.enqueue_batch(
            project_id="test-project",
            from_chapter=1,
            to_chapter=1,
        )
        queue_id = enqueue_result["data"]["queue_id"]

        # Manually set to timeout
        repo.update_queue_item(queue_id, status="timeout", last_error="Timed out")

        result = dispatcher.retry_queue_item(queue_id)
        assert result["ok"] is True
        assert result["data"]["status"] == "pending"

    def test_retry_completed_rejected(self, repo, dispatcher):
        """Test that retrying a completed item is rejected."""
        _seed_project(repo)

        enqueue_result = dispatcher.enqueue_batch(
            project_id="test-project",
            from_chapter=1,
            to_chapter=1,
        )
        queue_id = enqueue_result["data"]["queue_id"]

        # Manually set to completed
        repo.update_queue_item(queue_id, status="completed")

        result = dispatcher.retry_queue_item(queue_id)
        assert result["ok"] is False
        assert "Cannot retry" in result["error"]

    def test_retry_clears_locked_at_started_at_completed_at(self, repo, dispatcher):
        """Test that retry clears locked_at, started_at, completed_at."""
        _seed_project(repo)

        enqueue_result = dispatcher.enqueue_batch(
            project_id="test-project",
            from_chapter=1,
            to_chapter=1,
        )
        queue_id = enqueue_result["data"]["queue_id"]

        # Set to failed with timestamps
        now = datetime.now().isoformat()
        repo.update_queue_item(
            queue_id,
            status="failed",
            last_error="Test error",
            locked_at=now,
            started_at=now,
            completed_at=now,
        )

        # Verify timestamps are set
        item = repo.get_queue_item(queue_id)
        assert item["locked_at"] is not None
        assert item["started_at"] is not None
        assert item["completed_at"] is not None

        # Retry
        result = dispatcher.retry_queue_item(queue_id)
        assert result["ok"] is True

        # Verify timestamps are cleared
        item = repo.get_queue_item(queue_id)
        assert item["locked_at"] is None
        assert item["started_at"] is None
        assert item["completed_at"] is None


class TestTimeout:
    """Test timeout functionality."""

    def test_timeout_writes_queue_event(self, repo, dispatcher):
        """Test that mark_queue_timeouts writes events."""
        _seed_project(repo)

        enqueue_result = dispatcher.enqueue_batch(
            project_id="test-project",
            from_chapter=1,
            to_chapter=1,
            timeout_minutes=1,  # 1 minute timeout
        )
        queue_id = enqueue_result["data"]["queue_id"]

        # Manually set to running with old locked_at
        old_time = (datetime.now() - timedelta(minutes=10)).isoformat()
        repo.update_queue_item(queue_id, status="running", locked_at=old_time)

        # Mark timeouts
        result = dispatcher.mark_queue_timeouts()
        assert result["ok"] is True
        assert result["data"]["timed_out_count"] == 1

        # Verify event
        events = repo.get_queue_events(queue_id)
        timeout_events = [e for e in events if e["event_type"] == "timeout"]
        assert len(timeout_events) == 1
        assert timeout_events[0]["from_status"] == "running"
        assert timeout_events[0]["to_status"] == "timeout"

    def test_timeout_event_failure_returns_error(self, repo, dispatcher):
        """Test that timeout event failure returns ok=false."""
        _seed_project(repo)

        enqueue_result = dispatcher.enqueue_batch(
            project_id="test-project",
            from_chapter=1,
            to_chapter=1,
            timeout_minutes=1,
        )
        queue_id = enqueue_result["data"]["queue_id"]

        # Set to running with old locked_at
        old_time = (datetime.now() - timedelta(minutes=10)).isoformat()
        repo.update_queue_item(queue_id, status="running", locked_at=old_time)

        # Mock record_queue_event to fail
        with patch.object(repo, 'record_queue_event', return_value=None):
            result = dispatcher.mark_queue_timeouts()

        assert result["ok"] is False
        assert "failed to write timeout events" in result["error"].lower()


class TestProductionRunIdWriteFailure:
    """Test production_run_id write failure handling."""

    def test_production_run_id_write_failure_returns_error(self, repo, dispatcher):
        """Test that production_run_id write failure returns ok=false."""
        _seed_project(repo)
        _seed_chapter(repo, chapter_number=1)

        enqueue_result = dispatcher.enqueue_batch(
            project_id="test-project",
            from_chapter=1,
            to_chapter=1,
        )
        queue_id = enqueue_result["data"]["queue_id"]

        # Mock update_queue_item to fail for production_run_id update
        original_update = repo.update_queue_item
        call_count = [0]

        def mock_update(*args, **kwargs):
            call_count[0] += 1
            if 'production_run_id' in kwargs:
                return False
            return original_update(*args, **kwargs)

        with patch.object(repo, 'update_queue_item', side_effect=mock_update):
            result = dispatcher.run_queue_once()

        assert result["ok"] is False
        assert "failed to save production_run_id" in result["error"].lower()


class TestCLIJsonEnvelope:
    """Test CLI JSON envelope and argparse error envelope."""

    def _run_cli(self, args: list[str]) -> tuple[int, str, str]:
        """Run CLI command and return exit code, stdout, stderr."""
        cmd = [sys.executable, "-m", "novel_factory.cli"] + args
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.returncode, result.stdout, result.stderr

    def test_enqueue_json_envelope(self, tmp_path):
        """Test enqueue --json returns valid JSON envelope."""
        db_path = tmp_path / "test.db"
        config_path = tmp_path / "config.yaml"
        config_path.write_text("llm:\n  provider: stub\n")

        # Seed project first
        code, stdout, stderr = self._run_cli([
            "--db-path", str(db_path),
            "seed-demo", "--project-id", "test-cli", "--json",
        ])
        assert code == 0

        # Enqueue
        code, stdout, stderr = self._run_cli([
            "--db-path", str(db_path),
            "batch", "enqueue",
            "--project-id", "test-cli",
            "--from-chapter", "1",
            "--to-chapter", "5",
            "--json",
        ])

        assert code == 0
        result = json.loads(stdout)
        assert "ok" in result
        assert "error" in result
        assert "data" in result
        assert result["ok"] is True

    def test_queue_status_json_envelope(self, tmp_path):
        """Test queue-status --json returns valid JSON envelope."""
        db_path = tmp_path / "test.db"

        code, stdout, stderr = self._run_cli([
            "--db-path", str(db_path),
            "batch", "queue-status",
            "--json",
        ])

        assert code == 0
        result = json.loads(stdout)
        assert "ok" in result
        assert "error" in result
        assert "data" in result

    def test_argparse_error_json_envelope(self, tmp_path):
        """Test argparse error returns JSON envelope when --json is present."""
        db_path = tmp_path / "test.db"

        # Missing required --project-id
        code, stdout, stderr = self._run_cli([
            "--db-path", str(db_path),
            "batch", "enqueue",
            "--from-chapter", "1",
            "--to-chapter", "5",
            "--json",
        ])

        assert code == 2
        result = json.loads(stdout)
        assert result["ok"] is False
        assert "error" in result
        assert "required" in result["error"].lower()

    def test_queue_run_idle_json_envelope(self, tmp_path):
        """Test queue-run idle returns valid JSON envelope."""
        db_path = tmp_path / "test.db"

        code, stdout, stderr = self._run_cli([
            "--db-path", str(db_path),
            "batch", "queue-run",
            "--llm-mode", "stub",
            "--json",
        ])

        assert code == 0
        result = json.loads(stdout)
        assert result["ok"] is True
        assert result["data"]["status"] == "idle"


class TestQueueRunTimeoutAudit:
    """Test R1: queue-run 前置 timeout 扫描必须写 timeout event."""

    def test_queue_run_timeout_scan_writes_events(self, repo, dispatcher):
        """Test that run_queue_once writes timeout events for timed-out items."""
        _seed_project(repo)

        # Enqueue
        enqueue_result = dispatcher.enqueue_batch(
            project_id="test-project",
            from_chapter=1,
            to_chapter=1,
            timeout_minutes=1,
        )
        queue_id = enqueue_result["data"]["queue_id"]

        # Manually set to running with old locked_at
        old_time = (datetime.now() - timedelta(minutes=10)).isoformat()
        repo.update_queue_item(queue_id, status="running", locked_at=old_time)

        # Run queue_once - should detect timeout and write event
        result = dispatcher.run_queue_once()

        # The timed-out item should have a timeout event
        events = repo.get_queue_events(queue_id)
        timeout_events = [e for e in events if e["event_type"] == "timeout"]
        assert len(timeout_events) == 1
        assert timeout_events[0]["from_status"] == "running"
        assert timeout_events[0]["to_status"] == "timeout"

    def test_queue_run_timeout_scan_failure_returns_error(self, repo, dispatcher):
        """Test that timeout scan failure returns ok=false."""
        _seed_project(repo)

        # Enqueue and set to running with old locked_at
        enqueue_result = dispatcher.enqueue_batch(
            project_id="test-project",
            from_chapter=1,
            to_chapter=1,
            timeout_minutes=1,
        )
        queue_id = enqueue_result["data"]["queue_id"]
        old_time = (datetime.now() - timedelta(minutes=10)).isoformat()
        repo.update_queue_item(queue_id, status="running", locked_at=old_time)

        # Mock record_queue_event to fail for timeout event
        def mock_record(*args, **kwargs):
            event_type = kwargs.get('event_type', args[1] if len(args) > 1 else None)
            if event_type == "timeout":
                return None
            return repo.record_queue_event(*args, **kwargs)

        with patch.object(repo, 'record_queue_event', side_effect=mock_record):
            result = dispatcher.run_queue_once()

        assert result["ok"] is False
        assert "failed to mark queue timeouts" in result["error"].lower()


class TestStartedEventRollback:
    """Test R2: started event 失败回滚必须清理 started_at."""

    def test_started_event_failure_clears_started_at(self, repo, dispatcher):
        """Test that started event failure clears both locked_at and started_at."""
        _seed_project(repo)
        _seed_chapter(repo, chapter_number=1)

        # Enqueue
        enqueue_result = dispatcher.enqueue_batch(
            project_id="test-project",
            from_chapter=1,
            to_chapter=1,
        )
        queue_id = enqueue_result["data"]["queue_id"]

        # Mock record_queue_event to fail only for 'started' event
        original_record = repo.record_queue_event

        def mock_record(*args, **kwargs):
            event_type = kwargs.get('event_type', args[1] if len(args) > 1 else None)
            if event_type == "started":
                return None
            return original_record(*args, **kwargs)

        with patch.object(repo, 'record_queue_event', side_effect=mock_record):
            result = dispatcher.run_queue_once()

        assert result["ok"] is False
        assert "failed to record 'started' event" in result["error"].lower()

        # Verify item was rolled back to pending with cleared timestamps
        item = repo.get_queue_item(queue_id)
        assert item["status"] == "pending"
        assert item["locked_at"] is None
        assert item["started_at"] is None


class TestProductionRunIdFailureAudit:
    """Test R3: production_run_id 回写失败后的 failed 标记必须检查并审计."""

    def test_production_run_id_write_failure_marks_failed_with_event(self, repo, dispatcher):
        """Test that production_run_id write failure marks failed and writes event."""
        _seed_project(repo)
        _seed_chapter(repo, chapter_number=1)

        enqueue_result = dispatcher.enqueue_batch(
            project_id="test-project",
            from_chapter=1,
            to_chapter=1,
        )
        queue_id = enqueue_result["data"]["queue_id"]

        # Mock update_queue_item to fail for production_run_id update
        original_update = repo.update_queue_item

        def mock_update(*args, **kwargs):
            if 'production_run_id' in kwargs:
                return False
            return original_update(*args, **kwargs)

        with patch.object(repo, 'update_queue_item', side_effect=mock_update):
            result = dispatcher.run_queue_once()

        assert result["ok"] is False
        assert "failed to save production_run_id" in result["error"].lower()

        # Verify item is marked as failed
        item = repo.get_queue_item(queue_id)
        assert item["status"] == "failed"

        # Verify failed event was written
        events = repo.get_queue_events(queue_id)
        failed_events = [e for e in events if e["event_type"] == "failed"]
        assert len(failed_events) == 1

    def test_production_run_id_failure_then_failed_mark_failure(self, repo, dispatcher):
        """Test that failed mark failure returns explicit error."""
        _seed_project(repo)
        _seed_chapter(repo, chapter_number=1)

        enqueue_result = dispatcher.enqueue_batch(
            project_id="test-project",
            from_chapter=1,
            to_chapter=1,
        )
        queue_id = enqueue_result["data"]["queue_id"]

        # Mock update_queue_item to fail for both production_run_id and status=failed
        original_update = repo.update_queue_item
        call_count = [0]

        def mock_update(*args, **kwargs):
            call_count[0] += 1
            if 'production_run_id' in kwargs:
                return False
            if kwargs.get('status') == 'failed':
                return False
            return original_update(*args, **kwargs)

        with patch.object(repo, 'update_queue_item', side_effect=mock_update):
            result = dispatcher.run_queue_once()

        assert result["ok"] is False
        assert "failed to save production_run_id and failed to mark" in result["error"].lower()

    def test_production_run_id_failure_then_failed_event_failure(self, repo, dispatcher):
        """Test that failed event write failure returns explicit error."""
        _seed_project(repo)
        _seed_chapter(repo, chapter_number=1)

        enqueue_result = dispatcher.enqueue_batch(
            project_id="test-project",
            from_chapter=1,
            to_chapter=1,
        )
        queue_id = enqueue_result["data"]["queue_id"]

        # Mock update_queue_item to fail for production_run_id
        original_update = repo.update_queue_item
        original_record = repo.record_queue_event

        def mock_update(*args, **kwargs):
            if 'production_run_id' in kwargs:
                return False
            return original_update(*args, **kwargs)

        def mock_record(*args, **kwargs):
            event_type = kwargs.get('event_type', args[1] if len(args) > 1 else None)
            # Fail for the failed event after production_run_id failure
            if event_type == "failed":
                # Only fail if we're in the production_run_id failure path
                # Check if this is the first failed event (not from normal batch failure)
                events = repo.get_queue_events(queue_id)
                started_events = [e for e in events if e["event_type"] == "started"]
                if started_events:
                    return None
            return original_record(*args, **kwargs)

        with patch.object(repo, 'update_queue_item', side_effect=mock_update):
            with patch.object(repo, 'record_queue_event', side_effect=mock_record):
                result = dispatcher.run_queue_once()

        assert result["ok"] is False
        assert "failed to record 'failed' event" in result["error"].lower()

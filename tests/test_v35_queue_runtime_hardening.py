"""Tests for v3.5 Queue Runtime Hardening.

Covers:
- queue-events: view audit events
- queue-cancel: cancel items
- queue-recover: recover stuck items
- queue-doctor: diagnostics
- queue-run --limit: multiple execution
- Queue state matrix enforcement
- JSON envelope for all commands
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
            content = """林默推开房门，屋内弥漫着淡淡的茶香。他缓步走到窗前，凝望着外面的雨幕。
"你来了。"身后传来一个低沉的声音。林默转身，看到一个黑衣男子站在阴影中。
"你是谁？"林默警觉地问道，手已经摸向腰间的短剑。
"我是谁不重要，"黑衣男子缓缓走近，"重要的是，你正在寻找的东西，也在寻找你。"
林默心中一凛。这件事他从未告诉过任何人，这个人是怎么知道的？
"别紧张，"黑衣男子停下脚步，"我是来帮你的。但你必须做出选择。"
"什么选择？"林默紧盯着对方，随时准备出手。
"是继续寻找真相，还是保全你现在的平静生活。"黑衣男子的目光变得复杂。
林默沉默了片刻。窗外的雨越下越大，雷声隐隐传来。
"我已经没有退路了，"他终于说道，"不管前面是什么，我都必须走下去。"
黑衣男子点了点头。"很好。那么，从现在开始，你要小心身边的每一个人。"
说完，他的身影渐渐消失在阴影中，仿佛从未出现过。
林默站在原地，心中涌起一股不安。窗外的雨声似乎变得更加急促，仿佛在预示着什么。
他走到书桌前，翻开那本泛黄的笔记本。纸页上密密麻麻的字迹记录着这些年来的调查。
他拿起笔，在空白处写下今天的日期，然后停住了。笔尖悬在纸面上，迟迟没有落下。
最后，他只写了一句话：今天，一切都将改变。
就在这时，门外传来急促的敲门声。林默迅速合上笔记本，藏好短剑，然后走去开门。
门外站着一个陌生的年轻人，浑身湿透，目光中带着惊恐。
"救救我，"年轻人喘着气说，"他们...他们要杀我。"
林默还没来得及反应，远处就传来了脚步声。不止一个人，而且正在快速接近。
他一把将年轻人拉进屋内，关上门，然后吹灭了桌上的蜡烛。
黑暗中，他听到了自己的心跳声。这一刻，他知道，平静的日子已经结束了。"""
            return {
                "title": "测试章", "content": content,
                "word_count": len(content), "implemented_events": ["事件1"], "used_plot_refs": [],
            }
        if "Polisher" in schema_name:
            content = """林默推开房门，屋内弥漫着淡淡的茶香。他缓步走到窗前，凝望着外面的雨幕。
"你来了。"身后传来一个低沉的声音。林默转身，看到一个黑衣男子站在阴影中。
"你是谁？"林默警觉地问道，手已经摸向腰间的短剑。
"我是谁不重要，"黑衣男子缓缓走近，"重要的是，你正在寻找的东西，也在寻找你。"
林默心中一凛。这件事他从未告诉过任何人，这个人是怎么知道的？
"别紧张，"黑衣男子停下脚步，"我是来帮你的。但你必须做出选择。"
"什么选择？"林默紧盯着对方，随时准备出手。
"是继续寻找真相，还是保全你现在的平静生活。"黑衣男子的目光变得复杂。
林默沉默了片刻。窗外的雨越下越大，雷声隐隐传来。
"我已经没有退路了，"他终于说道，"不管前面是什么，我都必须走下去。"
黑衣男子点了点头。"很好。那么，从现在开始，你要小心身边的每一个人。"
说完，他的身影渐渐消失在阴影中，仿佛从未出现过。
林默站在原地，心中涌起一股不安。窗外的雨声似乎变得更加急促，仿佛在预示着什么。
他走到书桌前，翻开那本泛黄的笔记本。纸页上密密麻麻的字迹记录着这些年来的调查。
他拿起笔，在空白处写下今天的日期，然后停住了。笔尖悬在纸面上，迟迟没有落下。
最后，他只写了一句话：今天，一切都将改变。
就在这时，门外传来急促的敲门声。林默迅速合上笔记本，藏好短剑，然后走去开门。
门外站着一个陌生的年轻人，浑身湿透，目光中带着惊恐。
"救救我，"年轻人喘着气说，"他们...他们要杀我。"
林默还没来得及反应，远处就传来了脚步声。不止一个人，而且正在快速接近。
他一把将年轻人拉进屋内，关上门，然后吹灭了桌上的蜡烛。
黑暗中，他听到了自己的心跳声。这一刻，他知道，平静的日子已经结束了。"""
            return {
                "content": content, "fact_change_risk": "none",
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
    conn.execute(
        "INSERT INTO chapters (project_id, chapter_number, title, status) VALUES (?, ?, ?, ?)",
        (project_id, 1, "Chapter 1", "planned"),
    )
    conn.commit()
    conn.close()


def _create_queue_item(repo: Repository, project_id: str = "test_project", status: str = "pending", **kwargs):
    """Create a queue item with specified status."""
    queue_id = repo.create_queue_item(
        project_id=project_id,
        from_chapter=kwargs.get("from_chapter", 1),
        to_chapter=kwargs.get("to_chapter", 1),
        priority=kwargs.get("priority", 100),
        max_attempts=kwargs.get("max_attempts", 3),
        timeout_minutes=kwargs.get("timeout_minutes", 120),
    )

    # Record enqueued event
    repo.record_queue_event(
        queue_id=queue_id,
        event_type="enqueued",
        to_status="pending",
        message="Batch enqueued",
    )

    if status != "pending":
        conn = repo._conn()
        updates = ["status = ?"]
        params = [status]

        if status == "running":
            locked_at = kwargs.get("locked_at", datetime.now(timezone.utc).isoformat())
            updates.append("locked_at = ?")
            params.append(locked_at)
            started_at = kwargs.get("started_at", datetime.now(timezone.utc).isoformat())
            updates.append("started_at = ?")
            params.append(started_at)

        params.append(queue_id)
        conn.execute(
            f"UPDATE production_queue SET {', '.join(updates)} WHERE id = ?",
            params,
        )
        conn.commit()
        conn.close()

        # Record status change event
        repo.record_queue_event(
            queue_id=queue_id,
            event_type=status,
            from_status="pending",
            to_status=status,
            message=f"Status changed to {status}",
        )

    return queue_id


# ── Test 1: queue-events returns event list ───────────────────────────────


def test_queue_events_returns_events(dispatcher: Dispatcher, repo: Repository):
    """Test that queue-events returns a list of events."""
    _seed_project(repo)
    queue_id = _create_queue_item(repo)

    result = dispatcher.get_queue_events(queue_id)

    assert result["ok"] is True
    assert result["data"]["queue_id"] == queue_id
    assert len(result["data"]["events"]) >= 1
    assert result["data"]["events"][0]["event_type"] == "enqueued"


# ── Test 2: queue-events returns ok=false for non-existent queue_id ─────────


def test_queue_events_not_found(dispatcher: Dispatcher):
    """Test that queue-events returns ok=false for non-existent queue_id."""
    result = dispatcher.get_queue_events("nonexistent_queue")

    assert result["ok"] is False
    assert "not found" in result["error"]


# ── Test 3: pending item can be cancelled ───────────────────────────────────


def test_cancel_pending_item(dispatcher: Dispatcher, repo: Repository):
    """Test that pending item can be cancelled."""
    _seed_project(repo)
    queue_id = _create_queue_item(repo, status="pending")

    result = dispatcher.cancel_queue_item(queue_id, reason="manual stop")

    assert result["ok"] is True
    assert result["data"]["status"] == "cancelled"

    # Verify event was written
    events = repo.get_queue_events(queue_id)
    assert any(e["event_type"] == "cancelled" for e in events)


# ── Test 4: paused item can be cancelled ─────────────────────────────────────


def test_cancel_paused_item(dispatcher: Dispatcher, repo: Repository):
    """Test that paused item can be cancelled."""
    _seed_project(repo)
    queue_id = _create_queue_item(repo, status="paused")

    result = dispatcher.cancel_queue_item(queue_id)

    assert result["ok"] is True
    assert result["data"]["status"] == "cancelled"


# ── Test 5: running item can be cancelled ────────────────────────────────────


def test_cancel_running_item(dispatcher: Dispatcher, repo: Repository):
    """Test that running item can be cancelled."""
    _seed_project(repo)
    queue_id = _create_queue_item(repo, status="running")

    result = dispatcher.cancel_queue_item(queue_id, reason="manual stop")

    assert result["ok"] is True
    assert result["data"]["status"] == "cancelled"

    # Verify event was written
    events = repo.get_queue_events(queue_id)
    assert any(e["event_type"] == "cancelled" for e in events)


# ── Test 6: completed item cannot be cancelled ───────────────────────────────


def test_cancel_completed_item_fails(dispatcher: Dispatcher, repo: Repository):
    """Test that completed item cannot be cancelled."""
    _seed_project(repo)
    queue_id = _create_queue_item(repo, status="completed")

    result = dispatcher.cancel_queue_item(queue_id)

    assert result["ok"] is False
    assert "Cannot cancel" in result["error"]


# ── Test 7: cancelled item cannot be retried/resumed/run ─────────────────────


def test_cancelled_item_cannot_retry(dispatcher: Dispatcher, repo: Repository):
    """Test that cancelled item cannot be retried."""
    _seed_project(repo)
    queue_id = _create_queue_item(repo, status="cancelled")

    result = dispatcher.retry_queue_item(queue_id)

    assert result["ok"] is False
    assert "Cannot retry" in result["error"]


def test_cancelled_item_cannot_resume(dispatcher: Dispatcher, repo: Repository):
    """Test that cancelled item cannot be resumed."""
    _seed_project(repo)
    queue_id = _create_queue_item(repo, status="cancelled")

    result = dispatcher.resume_queue_item(queue_id)

    assert result["ok"] is False
    assert "Cannot resume" in result["error"]


# ── Test 8: running stuck item can be recovered ──────────────────────────────


def test_recover_stuck_running_item(dispatcher: Dispatcher, repo: Repository):
    """Test that running item with locked_at exceeding timeout can be recovered."""
    _seed_project(repo)
    # Create a stuck item (locked_at is 3 hours ago, timeout is 2 hours)
    stuck_time = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    queue_id = _create_queue_item(repo, status="running", locked_at=stuck_time, timeout_minutes=120)

    result = dispatcher.recover_queue_item(queue_id)

    assert result["ok"] is True
    assert result["data"]["status"] == "pending"

    # Verify event was written
    events = repo.get_queue_events(queue_id)
    assert any(e["event_type"] == "recovered" for e in events)


# ── Test 9: running non-stuck item cannot be recovered ───────────────────────


def test_recover_non_stuck_running_item_fails(dispatcher: Dispatcher, repo: Repository):
    """Test that running item not exceeding timeout cannot be recovered."""
    _seed_project(repo)
    # Create a non-stuck item (locked_at is 30 minutes ago, timeout is 2 hours)
    recent_time = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
    queue_id = _create_queue_item(repo, status="running", locked_at=recent_time, timeout_minutes=120)

    result = dispatcher.recover_queue_item(queue_id)

    assert result["ok"] is False
    assert "not stuck" in result["error"]


# ── Test 10: recover --force can recover non-stuck item ───────────────────────


def test_recover_force_non_stuck_item(dispatcher: Dispatcher, repo: Repository):
    """Test that --force can recover non-stuck running item."""
    _seed_project(repo)
    # Create a non-stuck item
    recent_time = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
    queue_id = _create_queue_item(repo, status="running", locked_at=recent_time, timeout_minutes=120)

    result = dispatcher.recover_queue_item(queue_id, force=True)

    assert result["ok"] is True
    assert result["data"]["status"] == "pending"

    # Verify event was written with forced flag
    events = repo.get_queue_events(queue_id)
    recovered_event = next(e for e in events if e["event_type"] == "recovered")
    assert "forced" in recovered_event["message"]


# ── Test 11: recover clears timestamps ───────────────────────────────────────


def test_recover_clears_timestamps(dispatcher: Dispatcher, repo: Repository):
    """Test that recover clears locked_at, started_at, completed_at."""
    _seed_project(repo)
    stuck_time = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    queue_id = _create_queue_item(repo, status="running", locked_at=stuck_time, started_at=stuck_time)

    result = dispatcher.recover_queue_item(queue_id)

    assert result["ok"] is True

    # Verify timestamps are cleared
    item = repo.get_queue_item(queue_id)
    assert item.get("locked_at") is None
    assert item.get("started_at") is None
    assert item.get("completed_at") is None


# ── Test 12: recover writes event ─────────────────────────────────────────────


def test_recover_writes_event(dispatcher: Dispatcher, repo: Repository):
    """Test that recover writes event."""
    _seed_project(repo)
    stuck_time = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    queue_id = _create_queue_item(repo, status="running", locked_at=stuck_time)

    result = dispatcher.recover_queue_item(queue_id)

    assert result["ok"] is True

    events = repo.get_queue_events(queue_id)
    assert any(e["event_type"] == "recovered" for e in events)


# ── Test 13: queue-doctor returns checks ─────────────────────────────────────


def test_queue_doctor_returns_checks(dispatcher: Dispatcher, repo: Repository):
    """Test that queue-doctor returns checks."""
    _seed_project(repo)
    queue_id = _create_queue_item(repo)

    result = dispatcher.doctor_queue_item(queue_id)

    assert result["ok"] is True
    assert "checks" in result["data"]
    assert len(result["data"]["checks"]) > 0

    # Verify all check names
    check_names = [c["name"] for c in result["data"]["checks"]]
    assert "queue_item_exists" in check_names
    assert "has_events" in check_names


# ── Test 14: doctor reports failed check for completed without production_run ─


def test_doctor_completed_without_production_run(dispatcher: Dispatcher, repo: Repository):
    """Test that doctor reports failed check for completed item without production_run_id."""
    _seed_project(repo)
    queue_id = _create_queue_item(repo, status="completed")

    result = dispatcher.doctor_queue_item(queue_id)

    assert result["ok"] is True

    # Find the completed_has_production_run check
    check = next(c for c in result["data"]["checks"] if c["name"] == "completed_has_production_run")
    assert check["pass"] is False


# ── Test 15: queue-run --limit 1 equals once ─────────────────────────────────


def test_queue_run_limit_1_equals_once(dispatcher: Dispatcher, repo: Repository):
    """Test that --limit 1 is equivalent to --once."""
    _seed_project(repo)
    queue_id = _create_queue_item(repo)

    result = dispatcher.run_queue(limit=1)

    assert result["ok"] is True
    assert result["data"]["limit"] == 1
    assert result["data"]["executed"] == 1


# ── Test 16: queue-run --limit 3 executes multiple items ─────────────────────


def test_queue_run_limit_3_executes_multiple(dispatcher: Dispatcher, repo: Repository):
    """Test that --limit 3 can execute multiple pending items."""
    _seed_project(repo)
    # Create 3 chapters for the project
    conn = repo._conn()
    for i in range(2, 4):
        conn.execute(
            "INSERT INTO chapters (project_id, chapter_number, title, status) VALUES (?, ?, ?, ?)",
            ("test_project", i, f"Chapter {i}", "planned"),
        )
    conn.commit()
    conn.close()

    # Create 3 pending items with different chapter ranges
    for i in range(3):
        _create_queue_item(repo, from_chapter=i+1, to_chapter=i+1)

    result = dispatcher.run_queue(limit=3)

    assert result["ok"] is True
    assert result["data"]["executed"] == 3


# ── Test 17: queue-run --limit stops on idle ─────────────────────────────────


def test_queue_run_limit_stops_on_idle(dispatcher: Dispatcher, repo: Repository):
    """Test that --limit stops early when encountering idle."""
    _seed_project(repo)
    # Create only 1 pending item
    _create_queue_item(repo)

    result = dispatcher.run_queue(limit=5)

    assert result["ok"] is True
    assert result["data"]["executed"] == 1
    assert result["data"]["stopped_reason"] == "idle"


# ── Test 18: queue-run --limit stops on failure ──────────────────────────────


def test_queue_run_limit_stops_on_failure(dispatcher: Dispatcher, repo: Repository):
    """Test that --limit stops early when encountering failure."""
    _seed_project(repo)
    # Create 2 pending items
    _create_queue_item(repo, from_chapter=1, to_chapter=1)
    _create_queue_item(repo, from_chapter=2, to_chapter=2)

    # Mock run_queue_once to fail on second call
    call_count = 0
    original_run = dispatcher.run_queue_once

    def mock_run():
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            return {"ok": False, "error": "Simulated failure", "data": {}}
        return original_run()

    with patch.object(dispatcher, "run_queue_once", mock_run):
        result = dispatcher.run_queue(limit=5)

    assert result["ok"] is True
    assert result["data"]["stopped_reason"] == "failure"


# ── Test 19: CLI JSON envelope for all new commands ──────────────────────────


def test_cli_queue_events_json(tmp_db: Path):
    """Test queue-events CLI with --json."""
    repo = Repository(str(tmp_db))
    _seed_project(repo)
    queue_id = _create_queue_item(repo)

    result = subprocess.run(
        [sys.executable, "-m", "novel_factory.cli", "--db-path", str(tmp_db),
         "batch", "queue-events", "--queue-id", queue_id, "--json"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["ok"] is True
    assert "events" in output["data"]


def test_cli_queue_cancel_json(tmp_db: Path):
    """Test queue-cancel CLI with --json."""
    repo = Repository(str(tmp_db))
    _seed_project(repo)
    queue_id = _create_queue_item(repo, status="pending")

    result = subprocess.run(
        [sys.executable, "-m", "novel_factory.cli", "--db-path", str(tmp_db),
         "batch", "queue-cancel", "--queue-id", queue_id, "--reason", "test", "--json"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["ok"] is True
    assert output["data"]["status"] == "cancelled"


def test_cli_queue_recover_json(tmp_db: Path):
    """Test queue-recover CLI with --json."""
    repo = Repository(str(tmp_db))
    _seed_project(repo)
    stuck_time = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    queue_id = _create_queue_item(repo, status="running", locked_at=stuck_time, timeout_minutes=120)

    result = subprocess.run(
        [sys.executable, "-m", "novel_factory.cli", "--db-path", str(tmp_db),
         "batch", "queue-recover", "--queue-id", queue_id, "--json"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["ok"] is True
    assert output["data"]["status"] == "pending"


def test_cli_queue_doctor_json(tmp_db: Path):
    """Test queue-doctor CLI with --json."""
    repo = Repository(str(tmp_db))
    _seed_project(repo)
    queue_id = _create_queue_item(repo)

    result = subprocess.run(
        [sys.executable, "-m", "novel_factory.cli", "--db-path", str(tmp_db),
         "batch", "queue-doctor", "--queue-id", queue_id, "--json"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["ok"] is True
    assert "checks" in output["data"]


def test_cli_queue_run_limit_json(tmp_db: Path):
    """Test queue-run --limit CLI with --json."""
    repo = Repository(str(tmp_db))
    _seed_project(repo)
    _create_queue_item(repo)

    result = subprocess.run(
        [sys.executable, "-m", "novel_factory.cli", "--db-path", str(tmp_db),
         "batch", "queue-run", "--limit", "1", "--llm-mode", "stub", "--json"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["ok"] is True
    assert output["data"]["limit"] == 1


# ── Test 20: argparse missing param JSON envelope ────────────────────────────


def test_cli_queue_events_missing_queue_id_json(tmp_db: Path):
    """Test queue-events CLI with missing --queue-id returns JSON error."""
    result = subprocess.run(
        [sys.executable, "-m", "novel_factory.cli", "--db-path", str(tmp_db),
         "batch", "queue-events", "--json"],
        capture_output=True,
        text=True,
    )

    # Should exit with error code
    assert result.returncode != 0
    # Should output JSON error
    output = json.loads(result.stdout)
    assert output["ok"] is False
    assert "required" in output["error"].lower()


# ── Test 21: State matrix enforcement ────────────────────────────────────────


def test_state_matrix_pending_to_cancelled(dispatcher: Dispatcher, repo: Repository):
    """Test state matrix: pending → cancelled is allowed."""
    _seed_project(repo)
    queue_id = _create_queue_item(repo, status="pending")

    result = dispatcher.cancel_queue_item(queue_id)

    assert result["ok"] is True


def test_state_matrix_running_to_pending_via_recover(dispatcher: Dispatcher, repo: Repository):
    """Test state matrix: running → pending via recover is allowed."""
    _seed_project(repo)
    stuck_time = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    queue_id = _create_queue_item(repo, status="running", locked_at=stuck_time, timeout_minutes=120)

    result = dispatcher.recover_queue_item(queue_id)

    assert result["ok"] is True


def test_state_matrix_completed_to_cancelled_denied(dispatcher: Dispatcher, repo: Repository):
    """Test state matrix: completed → cancelled is denied."""
    _seed_project(repo)
    queue_id = _create_queue_item(repo, status="completed")

    result = dispatcher.cancel_queue_item(queue_id)

    assert result["ok"] is False


def test_state_matrix_cancelled_to_retry_denied(dispatcher: Dispatcher, repo: Repository):
    """Test state matrix: cancelled → pending via retry is denied."""
    _seed_project(repo)
    queue_id = _create_queue_item(repo, status="cancelled")

    result = dispatcher.retry_queue_item(queue_id)

    assert result["ok"] is False


# ── Test 22: recover only for running status ─────────────────────────────────


def test_recover_non_running_denied(dispatcher: Dispatcher, repo: Repository):
    """Test that recover is denied for non-running status."""
    _seed_project(repo)
    queue_id = _create_queue_item(repo, status="pending")

    result = dispatcher.recover_queue_item(queue_id)

    assert result["ok"] is False
    assert "Only 'running'" in result["error"]


# ── R1: Non-JSON queue-run idle path must not traceback ────────────────────


def test_cli_queue_run_idle_no_json_no_traceback(tmp_db: Path):
    """Test that queue-run with no pending items does not traceback in non-JSON mode."""
    result = subprocess.run(
        [sys.executable, "-m", "novel_factory.cli", "--db-path", str(tmp_db),
         "batch", "queue-run", "--limit", "1", "--llm-mode", "stub"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "No pending queue items" in result.stdout
    assert "Traceback" not in result.stderr
    assert "KeyError" not in result.stderr


# ── R2: recover_queue_item handles naive/aware locked_at ───────────────────


def test_recover_naive_locked_at(dispatcher: Dispatcher, repo: Repository):
    """Test that recover works with naive (no timezone) locked_at timestamps."""
    _seed_project(repo)
    # Create a stuck item with naive locked_at (common in v3.4 data)
    naive_stuck_time = (datetime.now() - timedelta(hours=3)).isoformat()
    queue_id = _create_queue_item(repo, status="running", locked_at=naive_stuck_time, timeout_minutes=120)

    result = dispatcher.recover_queue_item(queue_id)

    assert result["ok"] is True
    assert result["data"]["status"] == "pending"


def test_recover_invalid_locked_at_returns_error(dispatcher: Dispatcher, repo: Repository):
    """Test that recover returns ok=false for unparseable locked_at, no traceback."""
    _seed_project(repo)
    queue_id = _create_queue_item(repo, status="running")

    # Manually set an invalid locked_at
    conn = repo._conn()
    conn.execute(
        "UPDATE production_queue SET locked_at = ? WHERE id = ?",
        ("not-a-valid-timestamp", queue_id),
    )
    conn.commit()
    conn.close()

    result = dispatcher.recover_queue_item(queue_id)

    assert result["ok"] is False
    assert "parse" in result["error"].lower()


def test_recover_aware_locked_at_with_z_suffix(dispatcher: Dispatcher, repo: Repository):
    """Test that recover works with Z-suffix aware locked_at timestamps."""
    _seed_project(repo)
    # Create a stuck item with Z-suffix timestamp
    stuck_time = (datetime.now(timezone.utc) - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    queue_id = _create_queue_item(repo, status="running", locked_at=stuck_time, timeout_minutes=120)

    result = dispatcher.recover_queue_item(queue_id)

    assert result["ok"] is True
    assert result["data"]["status"] == "pending"


# ── R3: recover --force must write metadata_json ───────────────────────────


def test_recover_force_writes_metadata_json(dispatcher: Dispatcher, repo: Repository):
    """Test that force recover writes metadata_json with {"force": true}."""
    _seed_project(repo)
    recent_time = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
    queue_id = _create_queue_item(repo, status="running", locked_at=recent_time, timeout_minutes=120)

    result = dispatcher.recover_queue_item(queue_id, force=True)

    assert result["ok"] is True

    # Verify metadata_json contains {"force": true}
    events = repo.get_queue_events(queue_id)
    recovered_event = next(e for e in events if e["event_type"] == "recovered")
    metadata = json.loads(recovered_event["metadata_json"])
    assert metadata.get("force") is True


def test_recover_non_force_writes_metadata_json(dispatcher: Dispatcher, repo: Repository):
    """Test that non-force recover writes metadata_json with {"force": false}."""
    _seed_project(repo)
    stuck_time = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    queue_id = _create_queue_item(repo, status="running", locked_at=stuck_time, timeout_minutes=120)

    result = dispatcher.recover_queue_item(queue_id, force=False)

    assert result["ok"] is True

    # Verify metadata_json contains {"force": false}
    events = repo.get_queue_events(queue_id)
    recovered_event = next(e for e in events if e["event_type"] == "recovered")
    metadata = json.loads(recovered_event["metadata_json"])
    assert metadata.get("force") is False

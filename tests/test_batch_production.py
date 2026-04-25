"""Batch production tests — covers v3.0 batch operations."""

from __future__ import annotations

import pytest

from novel_factory.db.connection import init_db
from novel_factory.db.repository import Repository
from novel_factory.dispatcher import Dispatcher
from novel_factory.llm.provider import LLMProvider


# ── Fixtures ────────────────────────────────────────────────────

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
            # Generate content with conflict, dialogue, and hook to pass final_gate
            # Must be >= 500 characters, avoid death penalty words
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
            # Return polished content (same as author for simplicity)
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
                "content": content,
                "fact_change_risk": "none", "changed_scope": ["sentence"], "summary": "微调",
            }
        if "Editor" in schema_name:
            return {
                "pass": True, "score": 92,
                "scores": {"setting": 20, "logic": 20, "poison": 18, "text": 17, "pacing": 17},
                "issues": [], "suggestions": [],
                "revision_target": None, "state_card": {},
            }
        if "ContinuityCheckerOutput" in schema_name:
            return {
                "report": {
                    "project_id": "batch_proj",
                    "from_chapter": 1,
                    "to_chapter": 3,
                    "issues": [],
                    "warnings": [],
                    "state_card_consistency": True,
                    "character_consistency": True,
                    "plot_consistency": True,
                    "summary": "连续性检查通过",
                },
                "agent_messages": [],
            }
        return {}

    def invoke_text(self, messages, temperature=None, max_tokens=None) -> str:
        return "{}"


@pytest.fixture
def tmp_db(tmp_path):
    db_path = tmp_path / "test_batch.db"
    init_db(db_path)
    return str(db_path)


@pytest.fixture
def repo(tmp_db):
    return Repository(tmp_db)


@pytest.fixture
def dispatcher(repo):
    return Dispatcher(repo, StubLLM(), max_retries=3)


def _seed_project_with_chapters(repo, project_id="batch_proj", num_chapters=3):
    """Seed a project with multiple chapters in planned status."""
    conn = repo._conn()
    conn.execute(
        "INSERT INTO projects (project_id, name, genre, is_current) VALUES (?, ?, ?, 1)",
        (project_id, "Batch Novel", "urban"),
    )
    for i in range(1, num_chapters + 1):
        conn.execute(
            "INSERT INTO chapters (project_id, chapter_number, title, status) "
            "VALUES (?, ?, ?, ?)",
            (project_id, i, f"第{i}章", "planned"),
        )
    conn.commit()
    conn.close()


# ── run_batch tests ──────────────────────────────────────────────

def test_run_batch_creates_production_run(repo, dispatcher):
    """Test that run_batch creates a production_run record."""
    _seed_project_with_chapters(repo, num_chapters=3)
    
    result = dispatcher.run_batch("batch_proj", 1, 3)
    
    assert result["ok"] is True
    assert result["error"] is None
    assert "run_id" in result["data"]
    assert result["data"]["project_id"] == "batch_proj"
    assert result["data"]["from_chapter"] == 1
    assert result["data"]["to_chapter"] == 3


def test_run_batch_creates_production_run_items(repo, dispatcher):
    """Test that run_batch creates production_run_item for each chapter."""
    _seed_project_with_chapters(repo, num_chapters=3)
    
    result = dispatcher.run_batch("batch_proj", 1, 3)
    run_id = result["data"]["run_id"]
    
    items = repo.get_production_run_items(run_id)
    assert len(items) == 3
    
    chapter_numbers = [item["chapter_number"] for item in items]
    assert chapter_numbers == [1, 2, 3]


def test_run_batch_success_sets_awaiting_review(repo, dispatcher):
    """Test that successful batch sets status to awaiting_review."""
    _seed_project_with_chapters(repo, num_chapters=2)
    
    result = dispatcher.run_batch("batch_proj", 1, 2)
    
    assert result["ok"] is True
    assert result["data"]["status"] == "awaiting_review"
    assert result["data"]["completed_chapters"] == 2
    assert result["data"]["blocked_chapter"] is None


def test_run_batch_invalid_range(repo, dispatcher):
    """Test that from_chapter > to_chapter returns error."""
    _seed_project_with_chapters(repo, num_chapters=3)
    
    result = dispatcher.run_batch("batch_proj", 3, 1)
    
    assert result["ok"] is False
    assert "from_chapter" in result["error"]
    assert result["data"] == {}


def test_run_batch_stops_on_blocked_chapter(repo):
    """Test that batch stops when a chapter fails (stop_on_block=True)."""
    # Create LLM that will fail on chapter 2
    class FailingLLM(StubLLM):
        def invoke_json(self, messages, schema=None, temperature=None):
            schema_name = getattr(schema, "__name__", "") if schema else ""
            # First chapter succeeds
            if self._call_count < 5:  # planner, screenwriter, author, polisher, editor
                self._call_count += 1
                return super().invoke_json(messages, schema, temperature)
            # Second chapter fails at planner
            return {
                "chapter_brief": {
                    "objective": "推进剧情", "required_events": ["事件1"],
                    "plots_to_plant": [], "plots_to_resolve": [],
                    "ending_hook": "悬念", "constraints": [],
                }
            }
    
    dispatcher = Dispatcher(repo, FailingLLM(), max_retries=3)
    _seed_project_with_chapters(repo, num_chapters=3)
    
    result = dispatcher.run_batch("batch_proj", 1, 3)
    
    # Should have stopped at chapter 2
    assert result["data"]["status"] == "blocked"
    assert result["data"]["blocked_chapter"] is not None
    
    # Check that chapter 3 was skipped
    run_id = result["data"]["run_id"]
    items = repo.get_production_run_items(run_id)
    chapter_3_item = next((item for item in items if item["chapter_number"] == 3), None)
    assert chapter_3_item is not None
    assert chapter_3_item["status"] == "skipped"


def test_run_batch_marks_items_completed(repo, dispatcher):
    """Test that successful chapters are marked as completed."""
    _seed_project_with_chapters(repo, num_chapters=2)
    
    result = dispatcher.run_batch("batch_proj", 1, 2)
    run_id = result["data"]["run_id"]
    
    items = repo.get_production_run_items(run_id)
    for item in items:
        assert item["status"] == "completed"
        assert item["chapter_status"] == "published"


# ── get_batch_status tests ───────────────────────────────────────

def test_get_batch_status_returns_run_and_items(repo, dispatcher):
    """Test that get_batch_status returns run info and items."""
    _seed_project_with_chapters(repo, num_chapters=2)
    
    run_result = dispatcher.run_batch("batch_proj", 1, 2)
    run_id = run_result["data"]["run_id"]
    
    status_result = dispatcher.get_batch_status(run_id)
    
    assert status_result["ok"] is True
    assert status_result["data"]["run_id"] == run_id
    assert status_result["data"]["project_id"] == "batch_proj"
    assert status_result["data"]["status"] == "awaiting_review"
    assert len(status_result["data"]["items"]) == 2


def test_get_batch_status_not_found(repo, dispatcher):
    """Test that get_batch_status returns error for non-existent run."""
    result = dispatcher.get_batch_status("nonexistent_run")
    
    assert result["ok"] is False
    assert "not found" in result["error"]
    assert result["data"] == {}


def test_get_batch_status_includes_quality_pass(repo, dispatcher):
    """Test that get_batch_status includes quality_pass info."""
    _seed_project_with_chapters(repo, num_chapters=1)
    
    run_result = dispatcher.run_batch("batch_proj", 1, 1)
    run_id = run_result["data"]["run_id"]
    
    status_result = dispatcher.get_batch_status(run_id)
    
    assert status_result["ok"] is True
    items = status_result["data"]["items"]
    assert len(items) == 1
    # quality_pass should be present (may be True or None)
    assert "quality_pass" in items[0]


# ── review_batch tests ───────────────────────────────────────────

def test_review_batch_approve(repo, dispatcher):
    """Test that review_batch with approve decision works."""
    _seed_project_with_chapters(repo, num_chapters=2)
    
    run_result = dispatcher.run_batch("batch_proj", 1, 2)
    run_id = run_result["data"]["run_id"]
    
    # v3.3: Run continuity gate before approve
    gate_result = dispatcher.run_batch_continuity_gate(run_id)
    assert gate_result["ok"]
    
    review_result = dispatcher.review_batch(run_id, "approve")
    
    assert review_result["ok"] is True
    assert review_result["data"]["run_id"] == run_id
    assert review_result["data"]["decision"] == "approve"
    
    # Check that production run status was updated
    run = repo.get_production_run(run_id)
    assert run["status"] == "approved"
    
    # Check that human review session was created
    sessions = repo.get_human_review_sessions(run_id)
    assert len(sessions) == 1
    assert sessions[0]["decision"] == "approve"


def test_review_batch_request_changes_with_notes(repo, dispatcher):
    """Test that review_batch with request_changes and notes works."""
    _seed_project_with_chapters(repo, num_chapters=2)
    
    run_result = dispatcher.run_batch("batch_proj", 1, 2)
    run_id = run_result["data"]["run_id"]
    
    review_result = dispatcher.review_batch(
        run_id, "request_changes", notes="第 3 章节奏太快"
    )
    
    assert review_result["ok"] is True
    
    # Check that production run status was updated
    run = repo.get_production_run(run_id)
    assert run["status"] == "request_changes"
    
    # Check that notes were saved
    sessions = repo.get_human_review_sessions(run_id)
    assert len(sessions) == 1
    assert sessions[0]["decision"] == "request_changes"
    assert sessions[0]["notes"] == "第 3 章节奏太快"


def test_review_batch_reject(repo, dispatcher):
    """Test that review_batch with reject decision works."""
    _seed_project_with_chapters(repo, num_chapters=2)
    
    run_result = dispatcher.run_batch("batch_proj", 1, 2)
    run_id = run_result["data"]["run_id"]
    
    review_result = dispatcher.review_batch(run_id, "reject")
    
    assert review_result["ok"] is True
    
    # Check that production run status was updated
    run = repo.get_production_run(run_id)
    assert run["status"] == "rejected"


def test_review_batch_invalid_decision(repo, dispatcher):
    """Test that review_batch with invalid decision returns error."""
    _seed_project_with_chapters(repo, num_chapters=2)
    
    run_result = dispatcher.run_batch("batch_proj", 1, 2)
    run_id = run_result["data"]["run_id"]
    
    review_result = dispatcher.review_batch(run_id, "invalid_decision")
    
    assert review_result["ok"] is False
    assert "Invalid decision" in review_result["error"]


def test_review_batch_not_found(repo, dispatcher):
    """Test that review_batch returns error for non-existent run."""
    result = dispatcher.review_batch("nonexistent_run", "approve")
    
    assert result["ok"] is False
    assert "not found" in result["error"]


# ── Integration tests ────────────────────────────────────────────

def test_full_batch_workflow(repo, dispatcher):
    """Test complete batch workflow: run -> status -> review."""
    _seed_project_with_chapters(repo, num_chapters=3)
    
    # Run batch
    run_result = dispatcher.run_batch("batch_proj", 1, 3)
    assert run_result["ok"] is True
    run_id = run_result["data"]["run_id"]
    
    # Check status
    status_result = dispatcher.get_batch_status(run_id)
    assert status_result["ok"] is True
    assert status_result["data"]["status"] == "awaiting_review"
    assert len(status_result["data"]["items"]) == 3
    
    # v3.3: Run continuity gate before approve
    gate_result = dispatcher.run_batch_continuity_gate(run_id)
    assert gate_result["ok"]
    
    # Review batch
    review_result = dispatcher.review_batch(run_id, "approve", notes="质量不错")
    assert review_result["ok"] is True
    
    # Verify final status
    final_status = dispatcher.get_batch_status(run_id)
    assert final_status["data"]["status"] == "approved"


def test_batch_reuses_run_chapter(repo, dispatcher):
    """Test that run_batch reuses run_chapter for each chapter."""
    _seed_project_with_chapters(repo, num_chapters=2)
    
    result = dispatcher.run_batch("batch_proj", 1, 2)
    run_id = result["data"]["run_id"]
    
    # Check that each chapter has a workflow_run_id
    items = repo.get_production_run_items(run_id)
    for item in items:
        assert item["workflow_run_id"] is not None
        assert item["chapter_status"] == "published"


def test_batch_envelope_format(repo, dispatcher):
    """Test that all batch methods return {ok, error, data} envelope."""
    _seed_project_with_chapters(repo, num_chapters=2)
    
    # Test run_batch envelope
    run_result = dispatcher.run_batch("batch_proj", 1, 2)
    assert "ok" in run_result
    assert "error" in run_result
    assert "data" in run_result
    
    run_id = run_result["data"]["run_id"]
    
    # Test get_batch_status envelope
    status_result = dispatcher.get_batch_status(run_id)
    assert "ok" in status_result
    assert "error" in status_result
    assert "data" in status_result
    
    # v3.3: Run continuity gate before approve
    gate_result = dispatcher.run_batch_continuity_gate(run_id)
    assert gate_result["ok"]
    
    # Test review_batch envelope
    review_result = dispatcher.review_batch(run_id, "approve")
    assert "ok" in review_result
    assert "error" in review_result
    assert "data" in review_result


def test_batch_error_envelope_format(repo, dispatcher):
    """Test that error cases also return {ok, error, data} envelope."""
    # Test invalid range
    _seed_project_with_chapters(repo, num_chapters=3)
    result = dispatcher.run_batch("batch_proj", 3, 1)
    assert "ok" in result
    assert result["ok"] is False
    assert "error" in result
    assert "data" in result
    
    # Test not found
    result = dispatcher.get_batch_status("nonexistent")
    assert "ok" in result
    assert result["ok"] is False
    assert "error" in result
    assert "data" in result
    
    # Test invalid decision
    run_result = dispatcher.run_batch("batch_proj", 1, 2)
    run_id = run_result["data"]["run_id"]
    result = dispatcher.review_batch(run_id, "bad_decision")
    assert "ok" in result
    assert result["ok"] is False
    assert "error" in result
    assert "data" in result


# ── R2: Repository rowcount + Dispatcher write-check tests ───────

class TestRepositoryUpdateRowcount:
    """Verify that update methods return False when no row is matched."""

    def test_update_production_run_missing_returns_false(self, repo):
        """update_production_run("missing", ...) returns False."""
        ok = repo.update_production_run("nonexistent-id", status="failed")
        assert ok is False

    def test_update_production_run_item_missing_returns_false(self, repo):
        """update_production_run_item("missing", ...) returns False."""
        ok = repo.update_production_run_item("nonexistent-id", status="running")
        assert ok is False


class TestDispatcherWriteChecks:
    """Verify that run_batch / review_batch fail loudly on write errors.

    Uses monkeypatch to simulate update failures on the repo.
    """

    def _seed_and_create_run(self, repo, dispatcher):
        """Helper: create a project and a production run with 2 chapters."""
        _seed_project_with_chapters(repo, num_chapters=2)
        run_result = dispatcher.run_batch("batch_proj", 1, 2)
        assert run_result["ok"] is True
        return run_result["data"]["run_id"]

    def test_run_batch_item_running_update_fails(self, repo, dispatcher):
        """If marking item as running fails, run_batch returns ok=false."""
        _seed_project_with_chapters(repo, num_chapters=2)

        original = repo.update_production_run_item

        call_count = 0

        def patched_update_item(item_id, **kwargs):
            nonlocal call_count
            call_count += 1
            # Fail the first update_production_run_item (marking running)
            if kwargs.get("status") == "running" and call_count == 1:
                return False
            return original(item_id, **kwargs)

        repo.update_production_run_item = patched_update_item

        result = dispatcher.run_batch("batch_proj", 1, 2)
        assert result["ok"] is False
        assert "running" in result["error"]

    def test_run_batch_item_completed_update_fails(self, repo, dispatcher):
        """If marking item as completed fails, run_batch returns ok=false."""
        _seed_project_with_chapters(repo, num_chapters=1)

        original = repo.update_production_run_item

        def patched_update_item(item_id, **kwargs):
            if kwargs.get("status") == "completed":
                return False
            return original(item_id, **kwargs)

        repo.update_production_run_item = patched_update_item

        result = dispatcher.run_batch("batch_proj", 1, 1)
        assert result["ok"] is False
        assert "completed" in result["error"]

    def test_run_batch_run_awaiting_review_update_fails(self, repo, dispatcher):
        """If marking run as awaiting_review fails, run_batch returns ok=false."""
        _seed_project_with_chapters(repo, num_chapters=1)

        original = repo.update_production_run

        def patched_update_run(run_id, **kwargs):
            if kwargs.get("status") == "awaiting_review":
                return False
            return original(run_id, **kwargs)

        repo.update_production_run = patched_update_run

        result = dispatcher.run_batch("batch_proj", 1, 1)
        assert result["ok"] is False
        assert "awaiting_review" in result["error"]

    def test_review_batch_run_status_update_fails(self, repo, dispatcher):
        """If run status update fails in review_batch, returns ok=false and no session created."""
        run_id = self._seed_and_create_run(repo, dispatcher)

        # v3.3: Run continuity gate before approve
        gate_result = dispatcher.run_batch_continuity_gate(run_id)
        assert gate_result["ok"]

        original = repo.update_production_run

        def patched_update_run(rid, **kwargs):
            # Fail when trying to update status to approved/rejected/request_changes
            if kwargs.get("status") in ("approved", "rejected", "request_changes"):
                return False
            return original(rid, **kwargs)

        repo.update_production_run = patched_update_run

        # Count sessions before
        sessions_before = repo.get_human_review_sessions(run_id)

        result = dispatcher.review_batch(run_id, "approve")
        assert result["ok"] is False
        assert "update" in result["error"].lower() or "status" in result["error"].lower()

        # Verify no new session was created (status update happens first)
        sessions_after = repo.get_human_review_sessions(run_id)
        assert len(sessions_after) == len(sessions_before)

    def test_review_batch_session_save_fails_compensates_status(self, repo, dispatcher):
        """If save_human_review_session fails, run status is reverted to original."""
        run_id = self._seed_and_create_run(repo, dispatcher)

        # v3.3: Run continuity gate before approve
        gate_result = dispatcher.run_batch_continuity_gate(run_id)
        assert gate_result["ok"]

        # Get original status
        run_before = repo.get_production_run(run_id)
        original_status = run_before["status"]

        original_save = repo.save_human_review_session

        def patched_save_session(*args, **kwargs):
            # Simulate failure
            return None

        repo.save_human_review_session = patched_save_session

        result = dispatcher.review_batch(run_id, "approve")
        assert result["ok"] is False
        assert "session" in result["error"].lower()

        # Verify status was compensated back to original
        run_after = repo.get_production_run(run_id)
        assert run_after["status"] == original_status

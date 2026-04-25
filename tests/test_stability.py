"""v1.1 Stability tests — S1 through S7.

Covers:
- S1: workflow_runs lifecycle (create, update node, finalize completed/blocked/failed)
- S2: artifact idempotency (same content → same id, different content → new id, hash key-order stable)
- S3: chapter_versions idempotency (same content → no new version, different → increment)
- S4: Repository write methods return false on missing target
- S5: expected_status prevents stale overwrites
- S6: task timeout marking
- S7: compile_graph with custom checkpointer / checkpoint=False
"""

from __future__ import annotations

import json
import time

import pytest

from novel_factory.db.connection import init_db
from novel_factory.db.repository import Repository
from novel_factory.llm.provider import LLMProvider
from novel_factory.models.state import ChapterStatus, FactoryState
from novel_factory.utils.hash import stable_json_hash
from novel_factory.validators.chapter_checker import count_words


class StubLLMProvider(LLMProvider):
    def __init__(self, responses: list[dict] | None = None):
        self.responses = responses or []
        self._call_count = 0

    def invoke_json(self, messages, schema=None, temperature=None) -> dict:
        if self._call_count < len(self.responses):
            resp = self.responses[self._call_count]
            self._call_count += 1
            return resp
        return {}

    def invoke_text(self, messages, temperature=None, max_tokens=None) -> str:
        return json.dumps(self.invoke_json(messages))


# ── Fixtures ────────────────────────────────────────────────────

@pytest.fixture
def tmp_db(tmp_path):
    db_path = tmp_path / "test_stability.db"
    init_db(db_path)
    return str(db_path)


@pytest.fixture
def repo(tmp_db):
    return Repository(tmp_db)


def _seed_project_chapter(repo, status="planned"):
    conn = repo._conn()
    conn.execute(
        "INSERT INTO projects (project_id, name, genre, is_current) VALUES (?, ?, ?, 1)",
        ("stab_proj", "Stability Novel", "urban"),
    )
    conn.execute(
        "INSERT INTO chapters (project_id, chapter_number, title, status) "
        "VALUES (?, ?, ?, ?)",
        ("stab_proj", 1, "第一章", status),
    )
    conn.execute(
        "INSERT INTO instructions (project_id, chapter_number, objective, key_events, "
        "plots_to_plant, plots_to_resolve, ending_hook, word_target, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active')",
        ("stab_proj", 1, "目标", '["事件1"]', '["P001"]', '[]', "悬念", 2500),
    )
    conn.commit()
    conn.close()


def _make_state(**overrides) -> FactoryState:
    base: FactoryState = {
        "project_id": "stab_proj",
        "chapter_number": 1,
        "chapter_status": "planned",
        "retry_count": 0,
        "max_retries": 3,
        "requires_human": False,
        "error": None,
    }
    base.update(overrides)
    return base


# ── S1: workflow_runs lifecycle ─────────────────────────────────

class TestS1WorkflowRuns:
    def test_workflow_run_created_on_entry(self, repo):
        """health_check_node creates a workflow_run if none exists."""
        from novel_factory.workflow.nodes import health_check_node

        _seed_project_chapter(repo)
        state = _make_state()
        result = health_check_node(state, repo)

        assert "workflow_run_id" in result
        run_id = result["workflow_run_id"]

        # Verify in DB
        conn = repo._conn()
        row = conn.execute("SELECT * FROM workflow_runs WHERE id=?", (run_id,)).fetchone()
        conn.close()
        assert row is not None
        assert row["status"] == "running"

    def test_workflow_run_completed_on_archive(self, repo):
        """archive_node marks workflow_run as completed."""
        from novel_factory.workflow.nodes import archive_node

        _seed_project_chapter(repo)
        run_id = repo.create_workflow_run("stab_proj", 1)
        state = _make_state(workflow_run_id=run_id, chapter_status="published")

        archive_node(state, repo)

        conn = repo._conn()
        row = conn.execute("SELECT status FROM workflow_runs WHERE id=?", (run_id,)).fetchone()
        conn.close()
        assert row["status"] == "completed"

    def test_workflow_run_blocked_on_human_review(self, repo):
        """human_review_node marks workflow_run as blocked."""
        from novel_factory.workflow.nodes import human_review_node

        _seed_project_chapter(repo)
        run_id = repo.create_workflow_run("stab_proj", 1)
        state = _make_state(workflow_run_id=run_id, chapter_status="blocking")

        human_review_node(state, repo)

        conn = repo._conn()
        row = conn.execute("SELECT status FROM workflow_runs WHERE id=?", (run_id,)).fetchone()
        conn.close()
        assert row["status"] == "blocked"

    def test_workflow_run_failed_on_agent_error(self, repo):
        """Agent error finalizes workflow_run as failed."""
        from novel_factory.workflow.nodes import author_node

        _seed_project_chapter(repo, status="planned")  # wrong status for author
        run_id = repo.create_workflow_run("stab_proj", 1)
        state = _make_state(workflow_run_id=run_id, chapter_status="scripted")

        stub = StubLLMProvider([])
        result = author_node(state, repo, stub)

        # Author should fail precondition
        assert "error" in result
        conn = repo._conn()
        row = conn.execute("SELECT status, error_message FROM workflow_runs WHERE id=?", (run_id,)).fetchone()
        conn.close()
        assert row["status"] == "failed"

    def test_workflow_run_current_node_updated(self, repo):
        """Nodes update current_node in workflow_runs."""
        from novel_factory.workflow.nodes import task_discovery_node

        _seed_project_chapter(repo, status="planned")
        run_id = repo.create_workflow_run("stab_proj", 1)
        state = _make_state(workflow_run_id=run_id, chapter_status="planned")

        task_discovery_node(state, repo)

        conn = repo._conn()
        row = conn.execute("SELECT current_node FROM workflow_runs WHERE id=?", (run_id,)).fetchone()
        conn.close()
        assert row["current_node"] == "task_discovery"


# ── S2: Artifact idempotency ───────────────────────────────────

class TestS2ArtifactIdempotency:
    def test_same_artifact_saves_once(self, repo):
        """Saving the same artifact twice only produces one record."""
        _seed_project_chapter(repo)

        content = {"title": "第一章", "content": "测试内容"}
        id1 = repo.save_artifact("stab_proj", 1, "author", "draft", content_json=content)
        id2 = repo.save_artifact("stab_proj", 1, "author", "draft", content_json=content)

        assert id1 == id2

        conn = repo._conn()
        count = conn.execute(
            "SELECT COUNT(*) as cnt FROM agent_artifacts "
            "WHERE project_id=? AND chapter_number=? AND agent_id=? AND artifact_type=?",
            ("stab_proj", 1, "author", "draft"),
        ).fetchone()["cnt"]
        conn.close()
        assert count == 1

    def test_different_content_creates_new_artifact(self, repo):
        """Different content creates a new artifact."""
        _seed_project_chapter(repo)

        content_v1 = {"title": "第一章", "content": "版本一"}
        content_v2 = {"title": "第一章", "content": "版本二"}

        id1 = repo.save_artifact("stab_proj", 1, "author", "draft", content_json=content_v1)
        id2 = repo.save_artifact("stab_proj", 1, "author", "draft", content_json=content_v2)

        assert id1 != id2

    def test_hash_key_order_stable(self, repo):
        """Hash is insensitive to JSON key order."""
        h1 = stable_json_hash({"a": 1, "b": 2})
        h2 = stable_json_hash({"b": 2, "a": 1})
        assert h1 == h2

    def test_artifact_has_content_hash(self, repo):
        """Saved artifact has content_hash populated."""
        _seed_project_chapter(repo)

        content = {"title": "第一章"}
        repo.save_artifact("stab_proj", 1, "author", "draft", content_json=content)

        conn = repo._conn()
        row = conn.execute(
            "SELECT content_hash FROM agent_artifacts "
            "WHERE project_id=? AND agent_id=?",
            ("stab_proj", "author"),
        ).fetchone()
        conn.close()
        assert row["content_hash"] == stable_json_hash(content)


# ── S3: Chapter versions idempotency ────────────────────────────

class TestS3ChapterVersionsIdempotency:
    def test_same_content_no_duplicate_version(self, repo):
        """Saving same content twice does not increase version count."""
        _seed_project_chapter(repo)

        content = "这是测试内容" * 50
        vid1 = repo.save_version("stab_proj", 1, content, created_by="author")
        vid2 = repo.save_version("stab_proj", 1, content, created_by="author")

        assert vid1 == vid2

        conn = repo._conn()
        count = conn.execute(
            "SELECT COUNT(*) as cnt FROM chapter_versions "
            "WHERE project_id=? AND chapter=? AND created_by=?",
            ("stab_proj", 1, "author"),
        ).fetchone()["cnt"]
        conn.close()
        assert count == 1

    def test_different_content_increments_version(self, repo):
        """Different content creates a new version with incremented number."""
        _seed_project_chapter(repo)

        content_v1 = "版本一内容" * 50
        content_v2 = "版本二内容" * 50

        vid1 = repo.save_version("stab_proj", 1, content_v1, created_by="author")
        vid2 = repo.save_version("stab_proj", 1, content_v2, created_by="author")

        assert vid1 != vid2

        conn = repo._conn()
        rows = conn.execute(
            "SELECT version FROM chapter_versions "
            "WHERE project_id=? AND chapter=? ORDER BY version",
            ("stab_proj", 1),
        ).fetchall()
        conn.close()
        assert len(rows) == 2
        assert rows[0]["version"] == 1
        assert rows[1]["version"] == 2

    def test_different_created_by_allows_separate_versions(self, repo):
        """Same content but different created_by creates separate records."""
        _seed_project_chapter(repo)

        content = "相同内容" * 50
        vid1 = repo.save_version("stab_proj", 1, content, created_by="author")
        vid2 = repo.save_version("stab_proj", 1, content, created_by="polisher")

        assert vid1 != vid2


# ── S4: Repository write failure detection ──────────────────────

class TestS4WriteFailureDetection:
    def test_save_chapter_content_missing_chapter_returns_false(self, repo):
        """Saving content for non-existent chapter returns False."""
        ok = repo.save_chapter_content("nonexistent", 999, "content")
        assert ok is False

    def test_publish_missing_chapter_returns_false(self, repo):
        """Publishing non-existent chapter returns False."""
        ok = repo.publish_chapter("nonexistent", 999)
        assert ok is False

    def test_update_workflow_run_nonexistent_returns_false(self, repo):
        """Updating non-existent workflow run returns False."""
        ok = repo.update_workflow_run("nonexistent-id", status="completed")
        assert ok is False

    def test_complete_task_nonexistent_returns_false(self, repo):
        """Completing non-existent task returns False."""
        ok = repo.complete_task(99999, success=True)
        assert ok is False


# ── S5: expected_status prevents stale overwrites ───────────────

class TestS5ExpectedStatus:
    def test_author_cannot_overwrite_if_db_changed(self, repo):
        """Author writes content but DB status was changed to 'review' — status not advanced."""
        _seed_project_chapter(repo, status="review")  # DB is already past scripted

        # Author tries to write with expected_status=scripted
        ok = repo.update_chapter_status(
            "stab_proj", 1, ChapterStatus.DRAFTED.value,
            expected_status=ChapterStatus.SCRIPTED.value,
        )
        assert ok is False
        # Status should remain review
        assert repo.get_chapter_status("stab_proj", 1) == "review"

    def test_polisher_cannot_overwrite_if_db_changed(self, repo):
        """Polisher tries to advance but DB status was changed to 'review'."""
        _seed_project_chapter(repo, status="review")

        ok = repo.update_chapter_status(
            "stab_proj", 1, ChapterStatus.POLISHED.value,
            expected_status=ChapterStatus.DRAFTED.value,
        )
        assert ok is False

    def test_publisher_only_publishes_reviewed(self, repo):
        """Publisher can only publish chapters in 'reviewed' status."""
        _seed_project_chapter(repo, status="polished")

        ok = repo.publish_chapter("stab_proj", 1)
        assert ok is False
        assert repo.get_chapter_status("stab_proj", 1) == "polished"

    def test_publisher_publishes_reviewed(self, repo):
        """Publisher succeeds when chapter is 'reviewed'."""
        _seed_project_chapter(repo, status="reviewed")

        ok = repo.publish_chapter("stab_proj", 1)
        assert ok is True
        assert repo.get_chapter_status("stab_proj", 1) == "published"


# ── S6: Task timeout marking ────────────────────────────────────

class TestS6TaskTimeout:
    def test_timed_out_running_task_marked(self, repo):
        """Running task older than timeout is marked as timeout."""
        _seed_project_chapter(repo)

        # Insert a running task with old started_at
        conn = repo._conn()
        conn.execute(
            "INSERT INTO task_status "
            "(project_id, chapter_number, task_type, agent_id, status, started_at) "
            "VALUES (?, ?, 'write', 'author', 'running', '2020-01-01 00:00:00')",
            ("stab_proj", 1),
        )
        conn.commit()
        conn.close()

        marked = repo.mark_timed_out_tasks("stab_proj", timeout_minutes=60)
        assert marked == 1

        # Verify status changed
        conn = repo._conn()
        row = conn.execute(
            "SELECT status FROM task_status WHERE project_id=? AND task_type='write'",
            ("stab_proj",),
        ).fetchone()
        conn.close()
        assert row["status"] == "timeout"

    def test_recent_running_task_not_marked(self, repo):
        """Running task within timeout is not marked."""
        _seed_project_chapter(repo)

        conn = repo._conn()
        conn.execute(
            "INSERT INTO task_status "
            "(project_id, chapter_number, task_type, agent_id, status, started_at) "
            "VALUES (?, ?, 'write', 'author', 'running', datetime('now','+8 hours'))",
            ("stab_proj", 1),
        )
        conn.commit()
        conn.close()

        marked = repo.mark_timed_out_tasks("stab_proj", timeout_minutes=60)
        assert marked == 0

    def test_completed_task_not_marked(self, repo):
        """Completed tasks are not affected by timeout scan."""
        _seed_project_chapter(repo)

        conn = repo._conn()
        conn.execute(
            "INSERT INTO task_status "
            "(project_id, chapter_number, task_type, agent_id, status, started_at) "
            "VALUES (?, ?, 'write', 'author', 'completed', '2020-01-01 00:00:00')",
            ("stab_proj", 1),
        )
        conn.commit()
        conn.close()

        marked = repo.mark_timed_out_tasks("stab_proj", timeout_minutes=60)
        assert marked == 0

        conn = repo._conn()
        row = conn.execute(
            "SELECT status FROM task_status WHERE project_id=? AND task_type='write'",
            ("stab_proj",),
        ).fetchone()
        conn.close()
        assert row["status"] == "completed"


# ── S7: Checkpoint recovery basics ─────────────────────────────

class TestS7Checkpoint:
    def test_compile_with_custom_checkpointer(self):
        """compile_graph accepts a custom checkpointer."""
        from langgraph.checkpoint.memory import MemorySaver
        from novel_factory.workflow.graph import compile_graph

        custom_cp = MemorySaver()
        graph = compile_graph(checkpointer=custom_cp)
        assert graph is not None

    def test_compile_without_checkpoint(self):
        """compile_graph with checkpoint=False has no checkpointer."""
        from novel_factory.workflow.graph import compile_graph

        graph = compile_graph(checkpoint=False)
        assert graph is not None

    def test_compile_default_uses_memory_saver(self):
        """compile_graph with default args uses MemorySaver."""
        from novel_factory.workflow.graph import compile_graph

        graph = compile_graph(checkpoint=True)
        assert graph is not None


# ── v1.1 Rework: Agent status-advance guard ────────────────────

class TestAgentStatusAdvanceGuard:
    """When update_chapter_status returns False (stale state), agents must
    return error and must NOT save artifacts or return a success status."""

    def _seed_and_spoof(self, repo, db_status, state_status):
        """Seed project/chapter, then set DB status to db_status while
        providing state_status in FactoryState — simulating a stale state."""
        _seed_project_chapter(repo, status=db_status)
        return _make_state(chapter_status=state_status)

    # -- Screenwriter --

    def test_screenwriter_stale_state_returns_error(self, repo):
        """Screenwriter: stale planned→scripted returns error, no scene beats saved."""
        from novel_factory.agents.screenwriter import ScreenwriterAgent

        # DB is already scripted (past planned), but state thinks it's planned
        state = self._seed_and_spoof(repo, db_status="scripted", state_status="planned")

        stub = StubLLMProvider([{
            "scene_beats": [
                {"sequence": 1, "scene_goal": "开场", "conflict": "冲突", "turn": "转折", "plot_refs": [], "hook": "钩子"},
            ]
        }])
        agent = ScreenwriterAgent(repo, stub)
        result = agent.run(state)

        assert "error" in result
        assert result["chapter_status"] != "scripted"
        # No scene beats should have been saved
        beats = repo.get_scene_beats("stab_proj", 1)
        assert len(beats) == 0

    # -- Author --

    def test_author_stale_state_returns_error(self, repo):
        """Author: stale scripted→drafted returns error, no content/artifact saved."""
        from novel_factory.agents.author import AuthorAgent

        state = self._seed_and_spoof(repo, db_status="drafted", state_status="scripted")
        # Add scene beats so author has context
        repo.save_scene_beats("stab_proj", 1, [{"sequence": 1, "scene_goal": "开场", "conflict": "冲突"}])
        # Re-set DB status since save_scene_beats doesn't change it
        repo.update_chapter_status("stab_proj", 1, "drafted")

        stub = StubLLMProvider([{
            "title": "第一章",
            "content": "测试正文" * 100,
            "word_count": 400,
            "implemented_events": [],
            "used_plot_refs": [],
        }])
        agent = AuthorAgent(repo, stub)
        result = agent.run(state)

        assert "error" in result
        assert result["chapter_status"] != "drafted"
        # No artifact should have been saved
        conn = repo._conn()
        count = conn.execute(
            "SELECT COUNT(*) as cnt FROM agent_artifacts WHERE agent_id='author'"
        ).fetchone()["cnt"]
        conn.close()
        assert count == 0

    # -- Polisher --

    def test_polisher_stale_state_returns_error(self, repo):
        """Polisher: stale drafted→polished returns error, no artifact saved."""
        from novel_factory.agents.polisher import PolisherAgent

        state = self._seed_and_spoof(repo, db_status="polished", state_status="drafted")
        repo.save_chapter_content("stab_proj", 1, "草稿内容" * 20, "第一章")
        repo.update_chapter_status("stab_proj", 1, "polished")

        stub = StubLLMProvider([{
            "content": "润色后的内容" * 20,
            "fact_change_risk": "none",
            "changed_scope": ["sentence"],
            "summary": "润色完成",
        }])
        agent = PolisherAgent(repo, stub)
        result = agent.run(state)

        assert "error" in result
        assert result["chapter_status"] != "polished"
        # No artifact should have been saved
        conn = repo._conn()
        count = conn.execute(
            "SELECT COUNT(*) as cnt FROM agent_artifacts WHERE agent_id='polisher'"
        ).fetchone()["cnt"]
        conn.close()
        assert count == 0

    # -- Editor --

    def test_editor_stale_state_pass_returns_error(self, repo):
        """Editor: stale polished→reviewed (pass) returns error, no artifact saved."""
        from novel_factory.agents.editor import EditorAgent

        state = self._seed_and_spoof(repo, db_status="reviewed", state_status="polished")
        repo.save_chapter_content("stab_proj", 1, "正文内容" * 20, "第一章")
        repo.update_chapter_status("stab_proj", 1, "reviewed")

        stub = StubLLMProvider([{
            "pass": True,
            "score": 92,
            "scores": {"setting": 23, "logic": 20, "poison": 18, "text": 16, "pacing": 15},
            "issues": [],
            "suggestions": [],
            "revision_target": None,
            "state_card": {"assets": {"credits": 100}},
        }])
        agent = EditorAgent(repo, stub)
        result = agent.run(state)

        assert "error" in result
        assert result["chapter_status"] != "reviewed"
        # No artifact should have been saved
        conn = repo._conn()
        count = conn.execute(
            "SELECT COUNT(*) as cnt FROM agent_artifacts WHERE agent_id='editor'"
        ).fetchone()["cnt"]
        conn.close()
        assert count == 0

    def test_editor_stale_state_revision_returns_error(self, repo):
        """Editor: stale polished→revision (fail) returns error."""
        from novel_factory.agents.editor import EditorAgent

        state = self._seed_and_spoof(repo, db_status="reviewed", state_status="polished")
        repo.save_chapter_content("stab_proj", 1, "正文内容" * 20, "第一章")
        repo.update_chapter_status("stab_proj", 1, "reviewed")

        stub = StubLLMProvider([{
            "pass": False,
            "score": 65,
            "scores": {"setting": 15, "logic": 12, "poison": 13, "text": 12, "pacing": 13},
            "issues": ["逻辑漏洞"],
            "suggestions": ["修复"],
            "revision_target": "author",
            "state_card": {},
        }])
        agent = EditorAgent(repo, stub)
        result = agent.run(state)

        assert "error" in result
        assert result["chapter_status"] != "revision"


# ── v1.1 Rework: Migration idempotency ────────────────────────

class TestMigrationIdempotency:
    def test_init_db_idempotent(self, tmp_path):
        """init_db can be called twice on the same DB without error."""
        from novel_factory.db.connection import init_db

        db_path = tmp_path / "idempotent.db"
        init_db(db_path)  # First run
        init_db(db_path)  # Second run — must not raise

        # Verify DB is still functional
        repo = Repository(str(db_path))
        # Should be able to insert without error
        conn = repo._conn()
        conn.execute(
            "INSERT INTO projects (project_id, name, genre, is_current) VALUES (?, ?, ?, 1)",
            ("mig_test", "Migration Test", "urban"),
        )
        conn.commit()
        conn.close()

    def test_migrations_tracked(self, tmp_path):
        """Migration tracking table records applied migrations."""
        from novel_factory.db.connection import init_db

        db_path = tmp_path / "tracked.db"
        init_db(db_path)

        import sqlite3
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT name FROM _migrations_applied ORDER BY name").fetchall()
        conn.close()

        names = [r["name"] for r in rows]
        assert "001_add_workflow_tables" in names
        assert "002_v1_1_stability" in names

    def test_init_db_second_run_skips_applied(self, tmp_path):
        """Second init_db skips already-applied migrations (no duplicate column error)."""
        from novel_factory.db.connection import init_db

        db_path = tmp_path / "skip.db"
        init_db(db_path)
        init_db(db_path)

        # Verify content_hash column exists and is functional
        repo = Repository(str(db_path))
        conn = repo._conn()
        conn.execute(
            "INSERT INTO projects (project_id, name, genre, is_current) VALUES (?, ?, ?, 1)",
            ("skip_test", "Skip Test", "urban"),
        )
        conn.execute(
            "INSERT INTO chapters (project_id, chapter_number, title, status) "
            "VALUES (?, ?, ?, 'planned')",
            ("skip_test", 1, "第一章"),
        )
        conn.commit()
        conn.close()

        # save_version uses content_hash — should work after double init
        vid = repo.save_version("skip_test", 1, "测试内容" * 20, created_by="author")
        assert vid > 0


# ── v1.1 Rework 2: Write failure compensation ─────────────────

class TestAgentWriteFailureCompensation:
    """When a product write fails after status advance, agents must
    compensate (roll back) the status and return error — never leave
    the DB in a 'status advanced but products missing' half-state."""

    def _seed_at_status(self, repo, status):
        """Seed project/chapter at a given status."""
        _seed_project_chapter(repo, status=status)
        return _make_state(chapter_status=status)

    # -- Screenwriter: save_scene_beats raises exception --

    def test_screenwriter_write_failure_compensates(self, repo):
        """Screenwriter: save_scene_beats fails → status rolled back to planned."""
        from unittest.mock import patch
        from novel_factory.agents.screenwriter import ScreenwriterAgent

        state = self._seed_at_status(repo, "planned")

        stub = StubLLMProvider([{
            "scene_beats": [
                {"sequence": 1, "scene_goal": "开场", "conflict": "冲突", "turn": "转折", "plot_refs": [], "hook": "钩子"},
            ]
        }])
        agent = ScreenwriterAgent(repo, stub)

        with patch.object(repo, "save_scene_beats", side_effect=RuntimeError("DB write error")):
            result = agent.run(state)

        assert "error" in result
        assert result["chapter_status"] == "planned"
        # DB status must be back to planned
        assert repo.get_chapter_status("stab_proj", 1) == "planned"

    # -- Author: save_chapter_content returns False --

    def test_author_save_content_fails_compensates(self, repo):
        """Author: save_chapter_content returns False → status rolled back to scripted."""
        from unittest.mock import patch
        from novel_factory.agents.author import AuthorAgent

        _seed_project_chapter(repo, status="scripted")
        repo.save_scene_beats("stab_proj", 1, [{"sequence": 1, "scene_goal": "开场", "conflict": "冲突"}])
        state = _make_state(chapter_status="scripted")

        stub = StubLLMProvider([{
            "title": "第一章",
            "content": "测试正文" * 100,
            "word_count": 400,
            "implemented_events": [],
            "used_plot_refs": [],
        }])
        agent = AuthorAgent(repo, stub)

        with patch.object(repo, "save_chapter_content", return_value=False):
            result = agent.run(state)

        assert "error" in result
        assert result["chapter_status"] == "scripted"
        assert repo.get_chapter_status("stab_proj", 1) == "scripted"

    # -- Author: save_version raises exception --

    def test_author_save_version_fails_compensates(self, repo):
        """Author: save_version raises → status rolled back, no artifact saved."""
        from unittest.mock import patch
        from novel_factory.agents.author import AuthorAgent

        _seed_project_chapter(repo, status="scripted")
        repo.save_scene_beats("stab_proj", 1, [{"sequence": 1, "scene_goal": "开场", "conflict": "冲突"}])
        state = _make_state(chapter_status="scripted")

        stub = StubLLMProvider([{
            "title": "第一章",
            "content": "测试正文" * 100,
            "word_count": 400,
            "implemented_events": [],
            "used_plot_refs": [],
        }])
        agent = AuthorAgent(repo, stub)

        with patch.object(repo, "save_version", side_effect=RuntimeError("version write error")):
            result = agent.run(state)

        assert "error" in result
        assert result["chapter_status"] == "scripted"
        assert repo.get_chapter_status("stab_proj", 1) == "scripted"

    # -- Polisher: save_chapter_content returns False --

    def test_polisher_save_content_fails_compensates(self, repo):
        """Polisher: save_chapter_content returns False → status rolled back to drafted."""
        from unittest.mock import patch
        from novel_factory.agents.polisher import PolisherAgent

        _seed_project_chapter(repo, status="drafted")
        repo.save_chapter_content("stab_proj", 1, "草稿内容" * 20, "第一章")
        repo.update_chapter_status("stab_proj", 1, "drafted")
        state = _make_state(chapter_status="drafted")

        stub = StubLLMProvider([{
            "content": "润色后的内容" * 20,
            "fact_change_risk": "none",
            "changed_scope": ["sentence"],
            "summary": "润色完成",
        }])
        agent = PolisherAgent(repo, stub)

        with patch.object(repo, "save_chapter_content", return_value=False):
            result = agent.run(state)

        assert "error" in result
        assert result["chapter_status"] == "drafted"
        assert repo.get_chapter_status("stab_proj", 1) == "drafted"

    # -- Polisher: save_polish_report raises exception --

    def test_polisher_save_report_fails_compensates(self, repo):
        """Polisher: save_polish_report raises → status rolled back to drafted."""
        from unittest.mock import patch
        from novel_factory.agents.polisher import PolisherAgent

        _seed_project_chapter(repo, status="drafted")
        repo.save_chapter_content("stab_proj", 1, "草稿内容" * 20, "第一章")
        repo.update_chapter_status("stab_proj", 1, "drafted")
        state = _make_state(chapter_status="drafted")

        stub = StubLLMProvider([{
            "content": "润色后的内容" * 20,
            "fact_change_risk": "none",
            "changed_scope": ["sentence"],
            "summary": "润色完成",
        }])
        agent = PolisherAgent(repo, stub)

        with patch.object(repo, "save_polish_report", side_effect=RuntimeError("report write error")):
            result = agent.run(state)

        assert "error" in result
        assert result["chapter_status"] == "drafted"
        assert repo.get_chapter_status("stab_proj", 1) == "drafted"

    # -- Editor: save_chapter_state returns False (pass branch) --

    def test_editor_save_state_fails_compensates(self, repo):
        """Editor: save_chapter_state fails → status rolled back to polished."""
        from unittest.mock import patch
        from novel_factory.agents.editor import EditorAgent

        _seed_project_chapter(repo, status="polished")
        repo.save_chapter_content("stab_proj", 1, "正文内容" * 20, "第一章")
        repo.update_chapter_status("stab_proj", 1, "polished")
        state = _make_state(chapter_status="polished")

        stub = StubLLMProvider([{
            "pass": True,
            "score": 92,
            "scores": {"setting": 23, "logic": 20, "poison": 18, "text": 16, "pacing": 15},
            "issues": [],
            "suggestions": [],
            "revision_target": None,
            "state_card": {"assets": {"credits": 100}},
        }])
        agent = EditorAgent(repo, stub)

        with patch.object(repo, "save_chapter_state", return_value=False):
            result = agent.run(state)

        assert "error" in result
        assert result["chapter_status"] == "polished"
        assert repo.get_chapter_status("stab_proj", 1) == "polished"

    # -- Editor: save_artifact raises exception (pass branch) --

    def test_editor_save_artifact_fails_compensates(self, repo):
        """Editor: save_artifact raises → status rolled back to polished."""
        from unittest.mock import patch
        from novel_factory.agents.editor import EditorAgent

        _seed_project_chapter(repo, status="polished")
        repo.save_chapter_content("stab_proj", 1, "正文内容" * 20, "第一章")
        repo.update_chapter_status("stab_proj", 1, "polished")
        state = _make_state(chapter_status="polished")

        stub = StubLLMProvider([{
            "pass": True,
            "score": 92,
            "scores": {"setting": 23, "logic": 20, "poison": 18, "text": 16, "pacing": 15},
            "issues": [],
            "suggestions": [],
            "revision_target": None,
            "state_card": {},
        }])
        agent = EditorAgent(repo, stub)

        with patch.object(repo, "save_artifact", side_effect=RuntimeError("artifact write error")):
            result = agent.run(state)

        assert "error" in result
        assert result["chapter_status"] == "polished"
        assert repo.get_chapter_status("stab_proj", 1) == "polished"

    # -- Editor: send_message raises (blocking branch) --

    def test_editor_blocking_send_message_fails_compensates(self, repo):
        """Editor: send_message raises in blocking branch → status rolled back."""
        from unittest.mock import patch
        from novel_factory.agents.editor import EditorAgent

        _seed_project_chapter(repo, status="polished")
        repo.save_chapter_content("stab_proj", 1, "正文内容" * 20, "第一章")
        repo.update_chapter_status("stab_proj", 1, "polished")
        # Simulate max retries reached
        conn = repo._conn()
        for _ in range(3):
            conn.execute(
                "INSERT INTO task_status (project_id, chapter_number, task_type, agent_id, status, started_at) "
                "VALUES (?, ?, 'revise', 'author', 'completed', datetime('now','+8 hours'))",
                ("stab_proj", 1),
            )
        conn.commit()
        conn.close()
        state = _make_state(chapter_status="polished", max_retries=3)

        stub = StubLLMProvider([{
            "pass": False,
            "score": 55,
            "scores": {"setting": 10, "logic": 10, "poison": 12, "text": 10, "pacing": 13},
            "issues": ["严重问题"],
            "suggestions": ["重写"],
            "revision_target": "author",
            "state_card": {},
        }])
        agent = EditorAgent(repo, stub)

        with patch.object(repo, "send_message", side_effect=RuntimeError("msg send error")):
            result = agent.run(state)

        assert "error" in result
        assert result["chapter_status"] == "polished"
        assert repo.get_chapter_status("stab_proj", 1) == "polished"

    # -- Editor: send_message raises (revision branch) --

    def test_editor_revision_send_message_fails_compensates(self, repo):
        """Editor: send_message raises in revision branch → status rolled back."""
        from unittest.mock import patch
        from novel_factory.agents.editor import EditorAgent

        _seed_project_chapter(repo, status="polished")
        repo.save_chapter_content("stab_proj", 1, "正文内容" * 20, "第一章")
        repo.update_chapter_status("stab_proj", 1, "polished")
        state = _make_state(chapter_status="polished")

        # Use AI-style text issues so classifier routes to polisher → triggers send_message
        stub = StubLLMProvider([{
            "pass": False,
            "score": 65,
            "scores": {"setting": 15, "logic": 12, "poison": 13, "text": 12, "pacing": 13},
            "issues": ["AI味句式问题严重"],
            "suggestions": ["修复"],
            "revision_target": "polisher",  # text issues → polisher → triggers send_message
            "state_card": {},
        }])
        agent = EditorAgent(repo, stub)

        with patch.object(repo, "send_message", side_effect=RuntimeError("msg send error")):
            result = agent.run(state)

        assert "error" in result
        assert result["chapter_status"] == "polished"
        assert repo.get_chapter_status("stab_proj", 1) == "polished"


# ── v1.1 Rework 2: Migration compatibility with pre-tracking DBs ──

class TestMigrationPreTrackingCompat:
    def test_init_db_on_db_with_content_hash_but_no_tracking(self, tmp_path):
        """Database that already has content_hash (from pre-tracking era)
        should not fail when init_db runs — schema check detects it."""
        from novel_factory.db.connection import init_db

        db_path = tmp_path / "legacy.db"

        # Simulate a pre-tracking DB by running init_db once
        init_db(db_path)

        # Remove tracking records to simulate a pre-tracking DB
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        conn.execute("DELETE FROM _migrations_applied WHERE name='002_v1_1_stability'")
        conn.commit()
        conn.close()

        # Running init_db again should NOT raise "duplicate column name"
        init_db(db_path)

        # 002 should now be recorded in tracking
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT 1 FROM _migrations_applied WHERE name='002_v1_1_stability'"
        ).fetchone()
        conn.close()
        assert row is not None

    def test_init_db_on_db_with_all_migrations_but_no_tracking(self, tmp_path):
        """Database with all migration effects applied but no tracking table
        at all — init_db should detect and record them all."""
        from novel_factory.db.connection import init_db

        db_path = tmp_path / "full_legacy.db"

        # Simulate by running init_db once
        init_db(db_path)

        # Drop the entire tracking table
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        conn.execute("DROP TABLE _migrations_applied")
        conn.commit()
        conn.close()

        # Running init_db again should NOT raise any errors
        init_db(db_path)

        # All migrations should now be tracked
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT name FROM _migrations_applied").fetchall()
        conn.close()
        names = [r["name"] for r in rows]
        assert "001_add_workflow_tables" in names
        assert "002_v1_1_stability" in names

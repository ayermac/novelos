"""Runtime tests — covers Dispatcher + Repository integration for v1.3.

These tests verify the runtime behavior of the full pipeline when driven
by the Dispatcher, ensuring DB state consistency, workflow tracking,
and artifact recording.
"""

from __future__ import annotations

import json

import pytest

from novel_factory.db.connection import init_db
from novel_factory.db.repository import Repository
from novel_factory.dispatcher import Dispatcher
from novel_factory.llm.provider import LLMProvider
from tests.conftest import LONG_CHAPTER_CONTENT


# ── Fixtures ────────────────────────────────────────────────────

class StubLLM(LLMProvider):
    """Stub LLM with configurable responses for multi-step runs."""

    def __init__(self, editor_pass: bool = True):
        self.editor_pass = editor_pass

    def invoke_json(self, messages, schema=None, temperature=None) -> dict:
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
            # v5.3.0: Content must meet 85% threshold (2125 chars for 2500 target)
            content = (
                "林默走进房间，环顾四周。房间很安静，只有窗外的雨声。"
                "他走到窗前，看着雨幕中的城市。突然，他注意到对面楼顶有一个黑影。"
                "\"谁在那里？\"他低声问道，但没有回应。"
                "黑影消失了，但林默知道，这只是一个开始。他必须做好准备，迎接即将到来的挑战。"
                "然而，他不知道的是，更大的危机正在逼近。"
            ) * 25  # ~2200 chars to pass quality gate
            return {
                "title": "测试章", "content": content,
                "word_count": len(content), "implemented_events": ["事件1"], "used_plot_refs": [],
            }
        if "Polisher" in schema_name:
            # v5.3.0: Content must meet 85% threshold (2125 chars for 2500 target)
            content = (
                "林默走入房间，环顾四周。房间很安静，只有窗外的雨声。"
                "他走到窗前，看着雨幕中的城市。突然，他注意到对面楼顶有一个黑影。"
                "\"谁在那里？\"他低声问道，但没有回应。"
                "黑影消失了，但林默知道，这只是一个开始。他必须做好准备，迎接即将到来的挑战。"
                "然而，他不知道的是，更大的危机正在逼近。"
            ) * 25  # ~2200 chars to pass quality gate
            return {
                "content": content,
                "fact_change_risk": "none", "changed_scope": ["sentence"], "summary": "微调",
            }
        if "Editor" in schema_name:
            if self.editor_pass:
                return {
                    "pass": True, "score": 92,
                    "scores": {"setting": 20, "logic": 20, "poison": 18, "text": 17, "pacing": 17},
                    "issues": [], "suggestions": [],
                    "revision_target": None, "state_card": {},
                }
            else:
                return {
                    "pass": False, "score": 65,
                    "scores": {"setting": 12, "logic": 12, "poison": 13, "text": 14, "pacing": 14},
                    "issues": ["AI味句式问题"], "suggestions": ["修改句式"],
                    "revision_target": "polisher", "state_card": {},
                }
        return {}

    def invoke_text(self, messages, temperature=None, max_tokens=None) -> str:
        return "{}"


@pytest.fixture
def tmp_db(tmp_path):
    db_path = tmp_path / "test_runtime.db"
    init_db(db_path)
    return str(db_path)


@pytest.fixture
def repo(tmp_db):
    return Repository(tmp_db)


def _seed_full_project(repo, status="planned", content=None):
    conn = repo._conn()
    conn.execute(
        "INSERT INTO projects (project_id, name, genre, is_current) VALUES (?, ?, ?, 1)",
        ("rt_proj", "Runtime Novel", "urban"),
    )
    if content:
        conn.execute(
            "INSERT INTO chapters (project_id, chapter_number, title, status, content) "
            "VALUES (?, ?, ?, ?, ?)",
            ("rt_proj", 1, "第一章", status, content),
        )
    else:
        conn.execute(
            "INSERT INTO chapters (project_id, chapter_number, title, status) "
            "VALUES (?, ?, ?, ?)",
            ("rt_proj", 1, "第一章", status),
        )
    conn.execute(
        "INSERT INTO instructions (project_id, chapter_number, objective, key_events, "
        "plots_to_plant, plots_to_resolve, ending_hook, word_target, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active')",
        ("rt_proj", 1, "推进剧情", '["事件1"]', '["P001"]', '[]', "悬念", 2500),
    )
    conn.execute(
        "INSERT INTO characters (project_id, name, role, description, status) "
        "VALUES (?, ?, ?, ?, 'active')",
        ("rt_proj", "林默", "protagonist", "主角"),
    )
    conn.execute(
        "INSERT INTO plot_holes (project_id, code, title, status, planted_chapter, planned_resolve_chapter) "
        "VALUES (?, ?, ?, 'planted', 1, 5)",
        ("rt_proj", "P001", "神秘信件"),
    )
    conn.commit()
    conn.close()


# ── Pipeline end-to-end ────────────────────────────────────────

class TestRuntimePipeline:
    def test_planned_to_reviewed_full_run(self, repo):
        """Full pipeline from planned to reviewed (editor passes)."""
        _seed_full_project(repo, status="planned")
        d = Dispatcher(repo, StubLLM(editor_pass=True), max_retries=3)
        result = d.run_chapter("rt_proj", 1)

        # Should have completed multiple steps
        assert len(result["steps"]) >= 3
        # Final status should be reviewed or published
        assert result["chapter_status"] in ("reviewed", "published")
        assert not result.get("error")

    def test_editor_rejection_creates_revision(self, repo):
        """When editor rejects, status should become revision."""
        _seed_full_project(repo, status="polished", content=LONG_CHAPTER_CONTENT)
        d = Dispatcher(repo, StubLLM(editor_pass=False), max_retries=3)
        result = d.run_chapter("rt_proj", 1)

        # Editor should be called
        assert any(s["agent"] == "editor" for s in result["steps"])
        # Should end in revision or blocking (if max retries hit)
        assert result["chapter_status"] in ("revision", "blocking")

    def test_workflow_runs_track_steps(self, repo):
        """Each run_chapter should create workflow_runs entries."""
        _seed_full_project(repo, status="planned")
        d = Dispatcher(repo, StubLLM(editor_pass=True), max_retries=3)
        d.run_chapter("rt_proj", 1)

        runs = repo.get_workflow_runs_for_project("rt_proj")
        assert len(runs) >= 1
        # At least one run should have a current_node
        assert any(r.get("current_node") for r in runs)

    def test_artifacts_recorded(self, repo):
        """Running the pipeline should create artifacts."""
        _seed_full_project(repo, status="planned")
        d = Dispatcher(repo, StubLLM(editor_pass=True), max_retries=3)
        d.run_chapter("rt_proj", 1)

        artifacts = repo.get_artifacts_for_chapter("rt_proj", 1)
        assert len(artifacts) >= 1

    def test_db_status_always_trusted(self, repo):
        """Dispatcher should use DB status, not passed-in state."""
        _seed_full_project(repo, status="polished", content="正文" * 30)
        d = Dispatcher(repo, StubLLM(editor_pass=True), max_retries=3)
        result = d.run_chapter("rt_proj", 1)
        # First step should be editor (based on DB status=polished)
        assert result["steps"][0]["agent"] == "editor"

    def test_resume_then_run(self, repo):
        """After human-resume, run_chapter should continue from new status."""
        _seed_full_project(repo, status="blocking")
        d = Dispatcher(repo, StubLLM(editor_pass=True), max_retries=3)

        # Resume to drafted
        resume_result = d.resume_blocked("rt_proj", 1, "drafted")
        assert resume_result["ok"] is True

        # Save content so polisher can run
        repo.save_chapter_content("rt_proj", 1, "草稿内容" * 30)

        # Now run — should start from drafted
        result = d.run_chapter("rt_proj", 1)
        assert any(s["agent"] == "polisher" for s in result["steps"])

"""Dispatcher tests — covers D2/D3 routing, run_chapter, discover_next, resume_blocked."""

from __future__ import annotations

import json

import pytest

from novel_factory.db.connection import init_db
from novel_factory.db.repository import Repository
from novel_factory.dispatcher import Dispatcher, STATUS_ROUTE, REVISION_ROUTE, LEGAL_RESUME_STATUSES
from novel_factory.llm.provider import LLMProvider
from novel_factory.models.state import ChapterStatus


# ── Fixtures ────────────────────────────────────────────────────

# Quality-pass content for seed data — must pass final_gate checks
# (>= 500 chars, dialogue, conflict, hook, no death penalty words)
_QUALITY_PASS_CONTENT = (
    "林默推开房门，屋内弥漫着淡淡的茶香。他缓步走到窗前，凝望着外面的雨幕。"
    "\"你来了。\"身后传来一个低沉的声音。林默转身，看到一个黑衣男子站在阴影中。"
    "\"你是谁？\"林默警觉地问道，手已经摸向腰间的短剑。"
    "\"我是谁不重要，\"黑衣男子缓缓走近，\"重要的是，你正在寻找的东西，也在寻找你。\""
    "林默心中一凛。这件事他从未告诉过任何人，这个人是怎么知道的？"
    "\"别紧张，\"黑衣男子停下脚步，\"我是来帮你的。但你必须做出选择。\""
    "\"什么选择？\"林默紧盯着对方，随时准备出手。"
    "\"是继续寻找真相，还是保全你现在的平静生活。\"黑衣男子的目光变得复杂。"
    "林默沉默了片刻。窗外的雨越下越大，雷声隐隐传来。"
    "\"我已经没有退路了，\"他终于说道，\"不管前面是什么，我都必须走下去。\""
    "黑衣男子点了点头。\"很好。那么，从现在开始，你要小心身边的每一个人。\""
    "说完，他的身影渐渐消失在阴影中，仿佛从未出现过。"
    "林默站在原地，心中涌起一股不安。窗外的雨声似乎变得更加急促，仿佛在预示着什么。"
    "他走到书桌前，翻开那本泛黄的笔记本。纸页上密密麻麻的字迹记录着这些年来的调查。"
    "他拿起笔，在空白处写下今天的日期，然后停住了。笔尖悬在纸面上，迟迟没有落下。"
    "最后，他只写了一句话：今天，一切都将改变。"
    "就在这时，门外传来急促的敲门声。林默迅速合上笔记本，藏好短剑，然后走去开门。"
    "门外站着一个陌生的年轻人，浑身湿透，目光中带着惊恐。"
    "\"救救我，\"年轻人喘着气说，\"他们...他们要杀我。\""
    "林默还没来得及反应，远处就传来了脚步声。不止一个人，而且正在快速接近。"
    "他一把将年轻人拉进屋内，关上门，然后吹灭了桌上的蜡烛。"
    "黑暗中，他听到了自己的心跳声。这一刻，他知道，平静的日子已经结束了。"
)

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
            # Content with conflict, dialogue, and hook to pass final_gate
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
        return {}

    def invoke_text(self, messages, temperature=None, max_tokens=None) -> str:
        return "{}"


@pytest.fixture
def tmp_db(tmp_path):
    db_path = tmp_path / "test_dispatcher.db"
    init_db(db_path)
    return str(db_path)


@pytest.fixture
def repo(tmp_db):
    return Repository(tmp_db)


@pytest.fixture
def dispatcher(repo):
    return Dispatcher(repo, StubLLM(), max_retries=3)


def _seed_project_chapter(repo, status="planned", content=None):
    """Seed a project with a chapter in the given status."""
    conn = repo._conn()
    conn.execute(
        "INSERT INTO projects (project_id, name, genre, is_current) VALUES (?, ?, ?, 1)",
        ("disp_proj", "Dispatcher Novel", "urban"),
    )
    if content:
        conn.execute(
            "INSERT INTO chapters (project_id, chapter_number, title, status, content) "
            "VALUES (?, ?, ?, ?, ?)",
            ("disp_proj", 1, "第一章", status, content),
        )
    else:
        conn.execute(
            "INSERT INTO chapters (project_id, chapter_number, title, status) "
            "VALUES (?, ?, ?, ?)",
            ("disp_proj", 1, "第一章", status),
        )
    conn.execute(
        "INSERT INTO instructions (project_id, chapter_number, objective, key_events, "
        "plots_to_plant, plots_to_resolve, ending_hook, word_target, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active')",
        ("disp_proj", 1, "推进剧情", '["事件1"]', '["P001"]', '[]', "悬念", 2500),
    )
    conn.execute(
        "INSERT INTO characters (project_id, name, role, description, status) "
        "VALUES (?, ?, ?, ?, 'active')",
        ("disp_proj", "林默", "protagonist", "主角"),
    )
    conn.commit()
    conn.close()


# ── Routing table tests ────────────────────────────────────────

class TestRoutingTable:
    def test_planned_routes_to_screenwriter(self):
        assert STATUS_ROUTE["planned"] == "screenwriter"

    def test_scripted_routes_to_author(self):
        assert STATUS_ROUTE["scripted"] == "author"

    def test_drafted_routes_to_polisher(self):
        assert STATUS_ROUTE["drafted"] == "polisher"

    def test_polished_routes_to_editor(self):
        assert STATUS_ROUTE["polished"] == "editor"

    def test_reviewed_routes_to_publisher(self):
        assert STATUS_ROUTE["reviewed"] == "publisher"

    def test_published_routes_to_end(self):
        assert STATUS_ROUTE["published"] == "__end__"

    def test_blocking_routes_to_stop(self):
        assert STATUS_ROUTE["blocking"] == "__stop__"

    def test_revision_author_routes_to_author(self):
        assert REVISION_ROUTE["author"] == "author"

    def test_revision_polisher_routes_to_polisher(self):
        assert REVISION_ROUTE["polisher"] == "polisher"

    def test_revision_planner_routes_to_stop(self):
        assert REVISION_ROUTE["planner"] == "__stop__"


# ── Dispatcher run_chapter tests ───────────────────────────────

class TestDispatcherRunChapter:
    def test_missing_chapter_returns_error(self, dispatcher, repo):
        result = dispatcher.run_chapter("nonexistent", 1)
        assert result["error"] == "Chapter not found in DB"
        assert result["requires_human"] is True

    def test_planned_to_scripted(self, dispatcher, repo):
        _seed_project_chapter(repo, status="planned")
        result = dispatcher.run_chapter("disp_proj", 1)
        # Should have advanced past planned
        assert len(result["steps"]) >= 1
        assert result["steps"][0]["agent"] == "screenwriter"

    def test_scripted_to_drafted(self, dispatcher, repo):
        _seed_project_chapter(repo, status="scripted")
        result = dispatcher.run_chapter("disp_proj", 1)
        assert len(result["steps"]) >= 1
        assert result["steps"][0]["agent"] == "author"

    def test_drafted_to_polished(self, dispatcher, repo):
        _seed_project_chapter(repo, status="drafted", content=_QUALITY_PASS_CONTENT)
        result = dispatcher.run_chapter("disp_proj", 1)
        assert len(result["steps"]) >= 1
        assert result["steps"][0]["agent"] == "polisher"

    def test_polished_to_reviewed_or_revision(self, dispatcher, repo):
        _seed_project_chapter(repo, status="polished", content=_QUALITY_PASS_CONTENT)
        result = dispatcher.run_chapter("disp_proj", 1)
        assert len(result["steps"]) >= 1
        assert result["steps"][0]["agent"] == "editor"
        # Status should be reviewed, revision, blocking, or published (if auto-published)
        final_status = result["chapter_status"]
        assert final_status in ("reviewed", "revision", "blocking", "published")

    def test_blocking_stops_scheduling(self, dispatcher, repo):
        _seed_project_chapter(repo, status="blocking")
        result = dispatcher.run_chapter("disp_proj", 1)
        # Should stop immediately
        assert len(result["steps"]) == 1
        assert result["steps"][0]["action"] == "stop"

    def test_published_stops_immediately(self, dispatcher, repo):
        _seed_project_chapter(repo, status="published")
        result = dispatcher.run_chapter("disp_proj", 1)
        assert len(result["steps"]) == 0

    def test_max_steps_prevents_infinite_loop(self, repo):
        """When max_steps=1, only one step is executed."""
        _seed_project_chapter(repo, status="planned")
        d = Dispatcher(repo, StubLLM(), max_retries=3)
        result = d.run_chapter("disp_proj", 1, max_steps=1)
        # Should have exactly 1 step (or 0 if first step stops)
        assert len(result["steps"]) <= 1

    def test_workflow_runs_recorded(self, dispatcher, repo):
        _seed_project_chapter(repo, status="planned")
        dispatcher.run_chapter("disp_proj", 1)
        runs = repo.get_workflow_runs_for_project("disp_proj")
        assert len(runs) >= 1


# ── Revision routing ───────────────────────────────────────────

class TestDispatcherRevision:
    def test_revision_with_author_target(self, repo):
        _seed_project_chapter(repo, status="revision", content=_QUALITY_PASS_CONTENT)
        # Set up a review with revision_target=author
        conn = repo._conn()
        ch = repo.get_chapter("disp_proj", 1)
        conn.execute(
            "INSERT INTO reviews (project_id, chapter_id, pass, score, summary) "
            "VALUES (?, ?, 0, 70, 'revision_target=author')",
            ("disp_proj", ch["id"]),
        )
        conn.commit()
        conn.close()

        d = Dispatcher(repo, StubLLM(), max_retries=3)
        result = d.run_chapter("disp_proj", 1)
        # Should route to author
        assert any(s["agent"] == "author" for s in result["steps"])

    def test_revision_with_polisher_target(self, repo):
        _seed_project_chapter(repo, status="revision", content=_QUALITY_PASS_CONTENT)
        conn = repo._conn()
        ch = repo.get_chapter("disp_proj", 1)
        conn.execute(
            "INSERT INTO reviews (project_id, chapter_id, pass, score, summary) "
            "VALUES (?, ?, 0, 70, 'revision_target=polisher')",
            ("disp_proj", ch["id"]),
        )
        conn.commit()
        conn.close()

        d = Dispatcher(repo, StubLLM(), max_retries=3)
        result = d.run_chapter("disp_proj", 1)
        assert any(s["agent"] == "polisher" for s in result["steps"])


# ── Discover next ──────────────────────────────────────────────

class TestDispatcherDiscover:
    def test_discover_finds_actionable_chapters(self, dispatcher, repo):
        _seed_project_chapter(repo, status="planned")
        results = dispatcher.discover_next("disp_proj")
        assert len(results) >= 1
        assert results[0]["next_agent"] == "screenwriter"

    def test_discover_skips_completed(self, dispatcher, repo):
        _seed_project_chapter(repo, status="published")
        results = dispatcher.discover_next("disp_proj")
        assert len(results) == 0

    def test_discover_skips_blocking(self, dispatcher, repo):
        _seed_project_chapter(repo, status="blocking")
        results = dispatcher.discover_next("disp_proj")
        assert len(results) == 0


# ── Human resume ───────────────────────────────────────────────

class TestDispatcherHumanResume:
    def test_resume_to_drafted(self, dispatcher, repo):
        _seed_project_chapter(repo, status="blocking")
        result = dispatcher.resume_blocked("disp_proj", 1, "drafted")
        assert result["ok"] is True
        assert result["data"]["new_status"] == "drafted"
        # Verify DB status updated
        assert repo.get_chapter_status("disp_proj", 1) == "drafted"

    def test_resume_to_polished(self, dispatcher, repo):
        _seed_project_chapter(repo, status="blocking")
        result = dispatcher.resume_blocked("disp_proj", 1, "polished")
        assert result["ok"] is True
        assert result["data"]["new_status"] == "polished"

    def test_resume_to_revision(self, dispatcher, repo):
        _seed_project_chapter(repo, status="blocking")
        result = dispatcher.resume_blocked("disp_proj", 1, "revision")
        assert result["ok"] is True

    def test_resume_to_published_forbidden(self, dispatcher, repo):
        _seed_project_chapter(repo, status="blocking")
        result = dispatcher.resume_blocked("disp_proj", 1, "published")
        assert result["ok"] is False
        assert "published" in result["error"]

    def test_resume_to_invalid_status_forbidden(self, dispatcher, repo):
        _seed_project_chapter(repo, status="blocking")
        result = dispatcher.resume_blocked("disp_proj", 1, "reviewed")
        assert result["ok"] is False

    def test_resume_missing_chapter_fails(self, dispatcher, repo):
        result = dispatcher.resume_blocked("nonexistent", 1, "drafted")
        assert result["ok"] is False
        assert "not found" in result["error"].lower()

    def test_resume_creates_workflow_run(self, dispatcher, repo):
        _seed_project_chapter(repo, status="blocking")
        dispatcher.resume_blocked("disp_proj", 1, "drafted")
        runs = repo.get_workflow_runs_for_project("disp_proj")
        assert len(runs) >= 1
        # Should have a human_resume node
        assert any(r.get("current_node") == "human_resume" for r in runs)

    def test_legal_resume_statuses(self):
        """Verify the legal resume statuses match spec."""
        assert "drafted" in LEGAL_RESUME_STATUSES
        assert "polished" in LEGAL_RESUME_STATUSES
        assert "planned" in LEGAL_RESUME_STATUSES
        assert "scripted" in LEGAL_RESUME_STATUSES
        assert "revision" in LEGAL_RESUME_STATUSES
        assert "published" not in LEGAL_RESUME_STATUSES
        assert "reviewed" not in LEGAL_RESUME_STATUSES
        assert "blocking" not in LEGAL_RESUME_STATUSES


# ── v1.3 Rework regression tests ──────────────────────────────────

class TestDispatcherErrorPropagation:
    """[P1] Agent error must propagate to run_chapter return value."""

    def test_agent_error_propagates_to_result(self, repo):
        """When an agent returns error, run_chapter must return that error."""
        _seed_project_chapter(repo, status="planned")

        class ErrorLLM(LLMProvider):
            def invoke_json(self, messages, schema=None, temperature=None) -> dict:
                return {}  # Empty response will cause validation error
            def invoke_text(self, messages, temperature=None, max_tokens=None) -> str:
                return "{}"

        d = Dispatcher(repo, ErrorLLM(), max_retries=3)
        result = d.run_chapter("disp_proj", 1)

        # Error must be present in return value (not None)
        assert result["error"] is not None
        assert result["requires_human"] is True

    def test_agent_requires_human_propagates(self, repo):
        """When an agent returns requires_human, it should propagate."""
        _seed_project_chapter(repo, status="planned")

        class RequiresHumanLLM(LLMProvider):
            def invoke_json(self, messages, schema=None, temperature=None) -> dict:
                schema_name = getattr(schema, "__name__", "") if schema else ""
                if "Screenwriter" in schema_name:
                    return {"scene_beats": [{"sequence": 1, "scene_goal": "场景", "conflict": "冲突", "hook": "钩子"}]}
                # Author returns requires_human
                if "Author" in schema_name:
                    content = "林默走进房间安静地坐下" * 80
                    return {
                        "title": "测试章", "content": content,
                        "word_count": len(content), "implemented_events": ["事件1"], "used_plot_refs": [],
                    }
                if "Polisher" in schema_name:
                    return {
                        "content": "林默走入房间悄然落座" * 40,
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

        d = Dispatcher(repo, RequiresHumanLLM(), max_retries=3)
        # Even with good LLM, max_steps=1 should cause requires_human
        result = d.run_chapter("disp_proj", 1, max_steps=1)
        assert result["requires_human"] is True
        assert result["error"] is not None  # max_steps exceeded error


class TestWorkflowRunNoLeakingRunning:
    """[P2] workflow_runs must not stay 'running' after successful steps."""

    def test_successful_run_marks_completed(self, repo):
        """A full successful pipeline should have completed workflow_runs."""
        _seed_project_chapter(repo, status="planned")
        d = Dispatcher(repo, StubLLM(), max_retries=3)
        d.run_chapter("disp_proj", 1)

        runs = repo.get_workflow_runs_for_project("disp_proj")
        assert len(runs) >= 1
        # No run should be stuck in 'running'
        running_runs = [r for r in runs if r.get("status") == "running"]
        assert len(running_runs) == 0, f"Found {len(running_runs)} runs stuck in 'running'"

    def test_single_step_run_marks_completed(self, repo):
        """Even a single-step successful run should be marked completed."""
        _seed_project_chapter(repo, status="planned")
        d = Dispatcher(repo, StubLLM(), max_retries=3)
        result = d.run_chapter("disp_proj", 1, max_steps=1)

        runs = repo.get_workflow_runs_for_project("disp_proj")
        # All runs should be in terminal state
        for run in runs:
            assert run["status"] in ("completed", "failed", "blocked"), \
                f"Run {run['id'][:8]} is in status '{run['status']}'"

    def test_failed_run_marks_failed(self, repo):
        """A run that encounters an error should be marked failed, not running."""

        class ErrorLLM(LLMProvider):
            def invoke_json(self, messages, schema=None, temperature=None) -> dict:
                return {}  # Will cause error
            def invoke_text(self, messages, temperature=None, max_tokens=None) -> str:
                return "{}"

        _seed_project_chapter(repo, status="planned")
        d = Dispatcher(repo, ErrorLLM(), max_retries=3)
        d.run_chapter("disp_proj", 1)

        runs = repo.get_workflow_runs_for_project("disp_proj")
        assert len(runs) >= 1
        # No run should be 'running'
        running_runs = [r for r in runs if r.get("status") == "running"]
        assert len(running_runs) == 0

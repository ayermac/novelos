"""v1 Review R1-R5 fix verification tests.

Tests specified in novel-factory-v1-review-fix-spec.md:
- test_base_agent_has_single_run_method          (R1)
- test_task_discovery_uses_db_status_over_state   (R2)
- test_task_discovery_missing_chapter_requires_human  (R2)
- test_update_chapter_status_expected_status_success   (R3)
- test_update_chapter_status_expected_status_failure   (R3)
- test_author_rejects_when_state_stale_against_db     (R4)
- test_polisher_rejects_when_state_stale_against_db   (R4)
- test_count_words_is_shared_for_chapter_content      (R5)
"""

from __future__ import annotations

import inspect
import json

import pytest

from novel_factory.db.connection import init_db
from novel_factory.db.repository import Repository
from novel_factory.llm.provider import LLMProvider
from novel_factory.models.state import ChapterStatus, FactoryState
from novel_factory.validators.chapter_checker import count_words


class StubLLMProvider(LLMProvider):
    """Stub LLM that returns predetermined JSON responses."""

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
    db_path = tmp_path / "test_review.db"
    init_db(db_path)
    return str(db_path)


@pytest.fixture
def repo(tmp_db):
    return Repository(tmp_db)


def _seed_project_chapter(repo, status="planned"):
    """Seed a project and chapter with given status."""
    conn = repo._conn()
    conn.execute(
        "INSERT INTO projects (project_id, name, genre, is_current) VALUES (?, ?, ?, 1)",
        ("rev_proj", "Review Novel", "urban"),
    )
    conn.execute(
        "INSERT INTO chapters (project_id, chapter_number, title, status) "
        "VALUES (?, ?, ?, ?)",
        ("rev_proj", 1, "第一章", status),
    )
    conn.execute(
        "INSERT INTO instructions (project_id, chapter_number, objective, key_events, "
        "plots_to_plant, plots_to_resolve, ending_hook, word_target, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active')",
        ("rev_proj", 1, "测试目标", '["事件1"]', '["P001"]', '[]', "悬念", 2500),
    )
    conn.commit()
    conn.close()


def _make_state(**overrides) -> FactoryState:
    base: FactoryState = {
        "project_id": "rev_proj",
        "chapter_number": 1,
        "chapter_status": "planned",
        "retry_count": 0,
        "max_retries": 3,
        "requires_human": False,
        "error": None,
    }
    base.update(overrides)
    return base


# ── R1: BaseAgent has single run method ────────────────────────

class TestR1SingleRunMethod:
    def test_base_agent_has_single_run_method(self):
        """BaseAgent must have exactly one 'run' method definition."""
        from novel_factory.agents.base import BaseAgent
        run_methods = [
            name for name, _ in inspect.getmembers(BaseAgent, predicate=inspect.isfunction)
            if name == "run"
        ]
        # There should be exactly one 'run' in the class dict
        assert "run" in BaseAgent.__dict__
        # And no duplicate definitions (Python would use the last one)
        # Verify by checking source has only one 'def run('
        source = inspect.getsource(BaseAgent)
        count = source.count("def run(")
        assert count == 1, f"Expected 1 'def run(' in BaseAgent, found {count}"


# ── R2: task_discovery_node uses DB status ─────────────────────

class TestR2TaskDiscoveryDBStatus:
    def test_task_discovery_uses_db_status_over_state_status(self, repo):
        """When DB status differs from state, task_discovery returns DB status."""
        from novel_factory.workflow.nodes import task_discovery_node

        _seed_project_chapter(repo, status="scripted")

        state = _make_state(chapter_status="planned")
        result = task_discovery_node(state, repo)

        assert result["chapter_status"] == "scripted"

    def test_task_discovery_missing_chapter_requires_human(self, repo):
        """When chapter does not exist in DB, return error and requires_human."""
        from novel_factory.workflow.nodes import task_discovery_node

        # Seed project but no chapter
        conn = repo._conn()
        conn.execute(
            "INSERT INTO projects (project_id, name, genre, is_current) VALUES (?, ?, ?, 1)",
            ("rev_proj", "Review Novel", "urban"),
        )
        conn.commit()
        conn.close()

        state = _make_state(chapter_status="planned")
        result = task_discovery_node(state, repo)

        assert "error" in result
        assert result.get("requires_human") is True


# ── R3: update_chapter_status expected_status protection ────────

class TestR3ExpectedStatus:
    def test_update_chapter_status_expected_status_success(self, repo):
        """When expected_status matches DB, update succeeds."""
        _seed_project_chapter(repo, status="planned")

        ok = repo.update_chapter_status(
            "rev_proj", 1, "scripted", expected_status="planned"
        )
        assert ok is True
        assert repo.get_chapter_status("rev_proj", 1) == "scripted"

    def test_update_chapter_status_expected_status_failure(self, repo):
        """When expected_status does not match DB, update fails and status unchanged."""
        _seed_project_chapter(repo, status="planned")

        ok = repo.update_chapter_status(
            "rev_proj", 1, "scripted", expected_status="drafted"
        )
        assert ok is False
        # Status should remain unchanged
        assert repo.get_chapter_status("rev_proj", 1) == "planned"


# ── R4: Agent precondition checks DB status ─────────────────────

class TestR4AgentPreconditionDBCheck:
    def test_author_rejects_when_state_stale_against_db(self, repo):
        """Author must reject when state says 'scripted' but DB says 'planned'."""
        from novel_factory.agents.author import AuthorAgent

        _seed_project_chapter(repo, status="planned")
        repo.save_scene_beats("rev_proj", 1, [
            {"sequence": 1, "scene_goal": "开场", "conflict": "冲突"},
        ])

        stub = StubLLMProvider([{
            "title": "第一章",
            "content": "内容" * 200,
            "word_count": 400,
            "implemented_events": [],
            "used_plot_refs": [],
        }])

        agent = AuthorAgent(repo, stub)
        # State says scripted, but DB says planned — should reject
        result = agent.run(_make_state(chapter_status="scripted"))

        assert "error" in result
        assert "Stale state" in result["error"]
        # DB should not be written
        chapter = repo.get_chapter("rev_proj", 1)
        assert chapter.get("content") is None or chapter.get("content") == ""

    def test_polisher_rejects_when_state_stale_against_db(self, repo):
        """Polisher must reject when state says 'drafted' but DB says 'review'."""
        from novel_factory.agents.polisher import PolisherAgent

        _seed_project_chapter(repo, status="review")
        repo.save_chapter_content("rev_proj", 1, "已有内容。", "第一章")

        stub = StubLLMProvider([{
            "content": "润色后内容",
            "fact_change_risk": "none",
            "changed_scope": ["sentence"],
            "summary": "润色完成",
        }])

        agent = PolisherAgent(repo, stub)
        # State says drafted, but DB says review — should reject
        result = agent.run(_make_state(chapter_status="drafted"))

        assert "error" in result
        assert "Stale state" in result["error"]


# ── R5: Unified count_words function ────────────────────────────

class TestR5CountWordsShared:
    def test_count_words_is_shared_for_chapter_content(self):
        """count_words is the single canonical function used everywhere."""
        # 1. Function exists and works
        assert count_words("Hello") == 5
        assert count_words("你好世界") == 4
        assert count_words("") == 0

        # 2. Verify repository uses count_words
        from novel_factory.db import repository as repo_module
        assert hasattr(repo_module, 'count_words')
        # The import is there
        import novel_factory.db.repository as r
        assert count_words is r.count_words

    def test_count_words_chinese_text(self):
        """Chinese character count is correct via count_words."""
        text = "这是一段中文测试文本"
        assert count_words(text) == 10

    def test_repository_save_chapter_uses_count_words(self, repo):
        """save_chapter_content must use count_words for word_count."""
        _seed_project_chapter(repo, status="planned")

        content = "测试内容" * 100  # 400 chars
        repo.save_chapter_content("rev_proj", 1, content, "第一章")

        chapter = repo.get_chapter("rev_proj", 1)
        assert chapter["word_count"] == count_words(content)
        assert chapter["word_count"] == 400

    def test_repository_save_version_uses_count_words(self, repo):
        """save_version must use count_words for word_count."""
        _seed_project_chapter(repo, status="planned")

        content = "版本内容" * 50  # 200 chars
        repo.save_version("rev_proj", 1, content, created_by="author")

        conn = repo._conn()
        row = conn.execute(
            "SELECT word_count FROM chapter_versions WHERE project_id=? AND chapter=?",
            ("rev_proj", 1),
        ).fetchone()
        conn.close()

        assert row["word_count"] == count_words(content)
        assert row["word_count"] == 200


# ── R2 补充: Graph/router 层路由安全测试 ────────────────────────

class TestR2RouterSafety:
    def test_missing_chapter_routes_to_human_review_not_agent(self, repo):
        """When chapter is missing from DB, task_discovery + route must go to human_review.

        This tests the full node→router path, not just task_discovery_node in isolation.
        Input state has chapter_status='planned', but DB has no chapter.
        After task_discovery_node, the merged state must route to human_review,
        NOT to screenwriter.
        """
        from novel_factory.workflow.nodes import task_discovery_node
        from novel_factory.workflow.conditions import route_by_chapter_status

        # Seed project but NO chapter
        conn = repo._conn()
        conn.execute(
            "INSERT INTO projects (project_id, name, genre, is_current) VALUES (?, ?, ?, 1)",
            ("rev_proj", "Review Novel", "urban"),
        )
        conn.commit()
        conn.close()

        # Input state says planned — would normally route to screenwriter
        state = _make_state(chapter_status="planned")

        # Step 1: task_discovery_node processes state
        updates = task_discovery_node(state, repo)

        # Step 2: merge updates into state (simulating LangGraph state merge)
        merged = {**state, **updates}

        # Step 3: route_by_chapter_status must return human_review, not screenwriter
        route = route_by_chapter_status(merged)
        assert route == "human_review", (
            f"Expected route 'human_review' for missing chapter, got '{route}'"
        )

    def test_error_flag_routes_to_human_review(self):
        """Any error flag in state must route to human_review."""
        from novel_factory.workflow.conditions import route_by_chapter_status

        state = _make_state(chapter_status="scripted", error="Something went wrong")
        assert route_by_chapter_status(state) == "human_review"

    def test_requires_human_routes_to_human_review(self):
        """requires_human flag must route to human_review even with valid status."""
        from novel_factory.workflow.conditions import route_by_chapter_status

        state = _make_state(chapter_status="drafted", requires_human=True)
        assert route_by_chapter_status(state) == "human_review"

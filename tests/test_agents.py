"""Tests for agents/ — stub LLM agent integration tests.

These tests use a StubLLMProvider to avoid real API calls.
They verify that agents correctly call the LLM, validate output,
and update the database.
"""

from __future__ import annotations

import json
import tempfile
from typing import Any

import pytest

from novel_factory.db.connection import init_db
from novel_factory.db.repository import Repository
from novel_factory.llm.provider import LLMProvider
from novel_factory.models.state import ChapterStatus, FactoryState


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


@pytest.fixture
def tmp_db(tmp_path):
    db_path = tmp_path / "test_agent.db"
    init_db(db_path)
    return str(db_path)


@pytest.fixture
def repo(tmp_db):
    return Repository(tmp_db)


@pytest.fixture
def seeded_repo(repo):
    """Seed a project and chapter in 'planned' status."""
    conn = repo._conn()
    conn.execute(
        "INSERT INTO projects (project_id, name, genre, is_current) VALUES (?, ?, ?, 1)",
        ("test_proj", "Test Novel", "urban"),
    )
    conn.execute(
        "INSERT INTO chapters (project_id, chapter_number, title, status) "
        "VALUES (?, ?, ?, ?)",
        ("test_proj", 1, "第一章 测试", "planned"),
    )
    conn.execute(
        "INSERT INTO instructions (project_id, chapter_number, objective, key_events, "
        "plots_to_plant, plots_to_resolve, ending_hook, word_target, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active')",
        ("test_proj", 1, "测试目标", '["事件1"]', '["P001"]', '[]', "悬念", 2500),
    )
    # Add a character
    conn.execute(
        "INSERT INTO characters (project_id, name, role, description, status) "
        "VALUES (?, ?, ?, ?, 'active')",
        ("test_proj", "林默", "protagonist", "主角"),
    )
    conn.commit()
    conn.close()
    return repo


class TestPlannerAgent:
    def test_planner_creates_instruction(self, seeded_repo):
        from novel_factory.agents.planner import PlannerAgent

        stub = StubLLMProvider([{
            "chapter_brief": {
                "objective": "林默Lv1，本章目标：突破困境",
                "required_events": ["事件1"],
                "plots_to_plant": ["P001"],
                "plots_to_resolve": [],
                "ending_hook": "悬念",
                "constraints": ["禁止冷笑"],
            }
        }])

        agent = PlannerAgent(seeded_repo, stub)
        state: FactoryState = {
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "planned",
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
        }

        result = agent.run(state)
        assert result["chapter_status"] == ChapterStatus.PLANNED.value

        # Verify instruction was saved
        instr = seeded_repo.get_instruction("test_proj", 1)
        assert instr is not None


class TestScreenwriterAgent:
    def test_screenwriter_creates_beats(self, seeded_repo):
        from novel_factory.agents.screenwriter import ScreenwriterAgent

        stub = StubLLMProvider([{
            "scene_beats": [
                {"sequence": 1, "scene_goal": "开场", "conflict": "冲突", "turn": "转折", "plot_refs": ["P001"], "hook": "钩子"},
            ]
        }])

        agent = ScreenwriterAgent(seeded_repo, stub)
        # Set chapter to planned status for screenwriter
        seeded_repo.update_chapter_status("test_proj", 1, "planned")
        state: FactoryState = {
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "planned",
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
        }

        result = agent.run(state)
        assert result["chapter_status"] == ChapterStatus.SCRIPTED.value

        beats = seeded_repo.get_scene_beats("test_proj", 1)
        assert len(beats) == 1


class TestAuthorAgent:
    def test_author_writes_content(self, seeded_repo):
        from novel_factory.agents.author import AuthorAgent

        # v5.3.0: Content must meet word count threshold (85% of 2500 = 2125)
        # Base content is 51 chars, need 43x to get 2193 chars > 2125
        base_content = "这是一段测试正文内容，用于验证 Author Agent 的基本功能。每次修改都需要确保内容充实完整。"
        long_content = (base_content * 44)  # 2244 chars

        stub = StubLLMProvider([{
            "title": "第一章 测试",
            "content": long_content,
            "word_count": 2244,
            "implemented_events": ["事件1"],
            "used_plot_refs": ["P001"],
        }])

        agent = AuthorAgent(seeded_repo, stub)
        seeded_repo.update_chapter_status("test_proj", 1, "scripted")
        # Add scene beats
        seeded_repo.save_scene_beats("test_proj", 1, [
            {"sequence": 1, "scene_goal": "开场", "conflict": "冲突"},
        ])

        state: FactoryState = {
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "scripted",
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
        }

        result = agent.run(state)
        assert result["chapter_status"] == ChapterStatus.DRAFTED.value

        chapter = seeded_repo.get_chapter("test_proj", 1)
        assert chapter["content"] is not None

    def test_author_recomputes_llm_declared_word_count(self, seeded_repo):
        """LLM word_count guesses should not block otherwise valid content."""
        from novel_factory.agents.author import AuthorAgent
        from novel_factory.validators.chapter_checker import count_words

        base_content = "这是一段测试正文内容，用于验证 Author Agent 的基本功能。每次修改都需要确保内容充实完整。"
        long_content = base_content * 44

        stub = StubLLMProvider([{
            "title": "第一章 测试",
            "content": long_content,
            "word_count": 3000,
            "implemented_events": ["事件1"],
            "used_plot_refs": ["P001"],
        }])

        agent = AuthorAgent(seeded_repo, stub)
        seeded_repo.update_chapter_status("test_proj", 1, "scripted")
        seeded_repo.save_scene_beats("test_proj", 1, [
            {"sequence": 1, "scene_goal": "开场", "conflict": "冲突"},
        ])

        state: FactoryState = {
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "scripted",
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
        }

        result = agent.run(state)

        assert "word_count 不匹配" not in result.get("error", "")
        assert result["chapter_status"] == ChapterStatus.DRAFTED.value

        chapter = seeded_repo.get_chapter("test_proj", 1)
        assert chapter["word_count"] == count_words(long_content)

    def test_author_real_mode_expands_short_valid_draft_once(self, seeded_repo):
        from novel_factory.agents.author import AuthorAgent

        short_content = "短正文" * 200  # 600 chars: valid payload, too short for gate.
        long_content = "扩写后的正文内容" * 300  # 2400 chars: passes 2500 * 85%.

        stub = StubLLMProvider([
            {
                "title": "第一章 测试",
                "content": short_content,
                "word_count": 3000,
                "implemented_events": ["事件1"],
                "used_plot_refs": ["P001"],
            },
            {
                "title": "第一章 测试",
                "content": long_content,
                "word_count": 3000,
                "implemented_events": ["事件1"],
                "used_plot_refs": ["P001"],
            },
        ])

        agent = AuthorAgent(seeded_repo, stub)
        seeded_repo.update_chapter_status("test_proj", 1, "scripted")
        seeded_repo.save_scene_beats("test_proj", 1, [
            {"sequence": 1, "scene_goal": "开场", "conflict": "冲突"},
        ])

        state: FactoryState = {
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "scripted",
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
            "llm_mode": "real",
        }

        result = agent.run(state)

        assert result["chapter_status"] == ChapterStatus.DRAFTED.value
        assert stub._call_count == 2
        chapter = seeded_repo.get_chapter("test_proj", 1)
        assert chapter["content"] == long_content


class TestPolisherAgent:
    def test_polisher_polishes_content(self, seeded_repo):
        from novel_factory.agents.polisher import PolisherAgent

        # v5.3.0: Content must meet word count threshold (85% of 2500 = 2125)
        # Base content is 51 chars, need 44x to get 2244 chars > 2125
        base_content = "这是一段测试正文内容，用于验证 Polisher Agent 的基本功能。每次修改都需要确保内容充实完整。"
        long_content = (base_content * 44)  # 2244 chars

        # Setup: chapter with content in 'drafted' status
        seeded_repo.save_chapter_content("test_proj", 1, long_content, "第一章 测试")
        seeded_repo.update_chapter_status("test_proj", 1, "drafted")

        stub = StubLLMProvider([{
            "content": long_content + "润色后。",
            "fact_change_risk": "none",
            "changed_scope": ["sentence"],
            "summary": "润色完成",
        }])

        agent = PolisherAgent(seeded_repo, stub)
        state: FactoryState = {
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "drafted",
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
        }

        result = agent.run(state)
        assert result["chapter_status"] == ChapterStatus.POLISHED.value

    def test_polisher_rejects_fact_change(self, seeded_repo):
        from novel_factory.agents.polisher import PolisherAgent

        # v5.3.0: Content must meet word count threshold
        base_content = "这是一段测试正文内容，用于验证 Polisher Agent 的基本功能。每次修改都需要确保内容充实完整。"
        long_content = (base_content * 35)  # ~2200 words

        seeded_repo.save_chapter_content("test_proj", 1, long_content, "第一章 测试")
        seeded_repo.update_chapter_status("test_proj", 1, "drafted")

        stub = StubLLMProvider([{
            "content": "改变了事实的内容",
            "fact_change_risk": "high",
            "changed_scope": ["plot"],
            "summary": "改变了剧情",
        }])

        agent = PolisherAgent(seeded_repo, stub)
        state: FactoryState = {
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "drafted",
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
        }

        result = agent.run(state)
        assert "error" in result
        assert "fact_change_risk" in result["error"]


class TestEditorAgent:
    def test_editor_pass(self, seeded_repo):
        from novel_factory.agents.editor import EditorAgent

        # v5.3.0: Content must meet word count threshold (90% of 2500 = 2250)
        # Base content is 51 chars, need 45x to get 2295 chars > 2250
        base_content = "这是一段测试正文内容，用于验证 Editor Agent 的基本功能。每次修改都需要确保内容充实完整。"
        long_content = (base_content * 45)  # 2295 chars

        # Setup: chapter with content in 'polished' status
        seeded_repo.save_chapter_content("test_proj", 1, long_content, "第一章 测试")
        seeded_repo.update_chapter_status("test_proj", 1, "polished")

        stub = StubLLMProvider([{
            "pass": True,
            "score": 92,
            "scores": {"setting": 23, "logic": 20, "poison": 18, "text": 16, "pacing": 15},
            "issues": [],
            "suggestions": [],
            "revision_target": None,
            "state_card": {"assets": {"credits": 100}},
        }])

        agent = EditorAgent(seeded_repo, stub)
        state: FactoryState = {
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "polished",
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
        }

        result = agent.run(state)
        assert result["chapter_status"] == ChapterStatus.REVIEWED.value
        assert result["quality_gate"]["pass"] is True

    def test_editor_fail_routes_to_revision(self, seeded_repo):
        from novel_factory.agents.editor import EditorAgent

        # v5.3.0: Content must meet word count threshold
        base_content = "这是一段测试正文内容，用于验证 Editor Agent 的基本功能。每次修改都需要确保内容充实完整。"
        long_content = (base_content * 36)  # ~2300 words

        seeded_repo.save_chapter_content("test_proj", 1, long_content, "第一章 测试")
        seeded_repo.update_chapter_status("test_proj", 1, "polished")

        stub = StubLLMProvider([{
            "pass": False,
            "score": 65,
            "scores": {"setting": 15, "logic": 12, "poison": 13, "text": 12, "pacing": 13},
            "issues": ["逻辑漏洞"],
            "suggestions": ["修复逻辑"],
            "revision_target": "author",
            "state_card": {},
        }])

        agent = EditorAgent(seeded_repo, stub)
        state: FactoryState = {
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "polished",
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
        }

        result = agent.run(state)
        assert result["chapter_status"] == ChapterStatus.REVISION.value
        assert result["quality_gate"]["pass"] is False

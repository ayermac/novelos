"""v1 MVP acceptance tests per the spec's 验收测试 section.

These tests verify:
1. planned -> published full happy path
2. Editor rejects to Author (revision_target=author)
3. Editor rejects to Polisher (revision_target=polisher)
4. Consecutive rejections trigger blocking
5. Invalid Agent output schema does NOT write to DB
6. Status precondition mismatch rejects writes
"""

from __future__ import annotations

import json
import tempfile

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


# ── Fixtures ────────────────────────────────────────────────────

@pytest.fixture
def tmp_db(tmp_path):
    db_path = tmp_path / "test_acceptance.db"
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
        ("acc_proj", "Acceptance Novel", "urban"),
    )
    conn.execute(
        "INSERT INTO chapters (project_id, chapter_number, title, status) "
        "VALUES (?, ?, ?, ?)",
        ("acc_proj", 1, "第一章 验收", status),
    )
    conn.execute(
        "INSERT INTO instructions (project_id, chapter_number, objective, key_events, "
        "plots_to_plant, plots_to_resolve, ending_hook, word_target, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active')",
        ("acc_proj", 1, "验收目标", '["事件1"]', '["P001"]', '[]', "悬念", 2500),
    )
    conn.execute(
        "INSERT INTO characters (project_id, name, role, description, status) "
        "VALUES (?, ?, ?, ?, 'active')",
        ("acc_proj", "林默", "protagonist", "主角"),
    )
    conn.commit()
    conn.close()


def _make_state(**overrides) -> FactoryState:
    base: FactoryState = {
        "project_id": "acc_proj",
        "chapter_number": 1,
        "chapter_status": "planned",
        "retry_count": 0,
        "max_retries": 3,
        "requires_human": False,
        "error": None,
    }
    base.update(overrides)
    return base


# Helper: long enough content to pass word count validation
# v5.3.0: Author/Polisher need 85% of word_target, Editor needs 90%
# With Planner preserving word_target from seed (2500), thresholds are:
# Author needs 2500*0.85=2125, Editor needs 2500*0.9=2250
# Base content is 44 chars, 59x for 2596 (>2125), 62x for 2728 (>2250)
_BASE_CONTENT = "这是一段验收测试用的正文内容，用于模拟 Agent 的输出。每次都需要确保内容充实完整。"
_LONG_CONTENT = _BASE_CONTENT * 59   # 2596 chars
_POLISHED_CONTENT = _BASE_CONTENT * 62  # 2728 chars


# ── Test 1: Full happy path planned -> published ────────────────

class TestFullHappyPath:
    def test_planned_to_published(self, repo):
        """Verify a chapter can flow from planned all the way to published."""
        from novel_factory.agents.planner import PlannerAgent
        from novel_factory.agents.screenwriter import ScreenwriterAgent
        from novel_factory.agents.author import AuthorAgent
        from novel_factory.agents.polisher import PolisherAgent
        from novel_factory.agents.editor import EditorAgent

        _seed_project_chapter(repo, status="planned")

        # Step 1: Planner
        planner_llm = StubLLMProvider([{
            "chapter_brief": {
                "objective": "验收测试目标",
                "required_events": ["事件1"],
                "plots_to_plant": ["P001"],
                "plots_to_resolve": [],
                "ending_hook": "悬念",
                "constraints": ["禁止冷笑"],
            }
        }])
        planner = PlannerAgent(repo, planner_llm)
        result = planner.run(_make_state(chapter_status="planned"))
        assert result["chapter_status"] == ChapterStatus.PLANNED.value

        # Step 2: Screenwriter
        sw_llm = StubLLMProvider([{
            "scene_beats": [
                {"sequence": 1, "scene_goal": "开场", "conflict": "冲突", "turn": "转折", "plot_refs": ["P001"], "hook": "钩子"},
            ]
        }])
        sw = ScreenwriterAgent(repo, sw_llm)
        result = sw.run(_make_state(chapter_status="planned"))
        assert result["chapter_status"] == ChapterStatus.SCRIPTED.value

        # Step 3: Author
        author_llm = StubLLMProvider([{
            "title": "第一章 验收",
            "content": _LONG_CONTENT,
            "word_count": len(_LONG_CONTENT),
            "implemented_events": ["事件1"],
            "used_plot_refs": ["P001"],
        }])
        author = AuthorAgent(repo, author_llm)
        result = author.run(_make_state(chapter_status="scripted"))
        assert result["chapter_status"] == ChapterStatus.DRAFTED.value

        # Step 4: Polisher
        polisher_llm = StubLLMProvider([{
            "content": _POLISHED_CONTENT,
            "fact_change_risk": "none",
            "changed_scope": ["sentence"],
            "summary": "润色完成",
        }])
        polisher = PolisherAgent(repo, polisher_llm)
        result = polisher.run(_make_state(chapter_status="drafted"))
        assert result["chapter_status"] == ChapterStatus.POLISHED.value

        # Step 5: Editor (pass)
        editor_llm = StubLLMProvider([{
            "pass": True,
            "score": 92,
            "scores": {"setting": 23, "logic": 20, "poison": 18, "text": 16, "pacing": 15},
            "issues": [],
            "suggestions": [],
            "revision_target": None,
            "state_card": {"assets": {"credits": 100}},
        }])
        editor = EditorAgent(repo, editor_llm)
        result = editor.run(_make_state(chapter_status="polished"))
        assert result["chapter_status"] == ChapterStatus.REVIEWED.value

        # Step 6: Publish
        repo.publish_chapter("acc_proj", 1)
        status = repo.get_chapter_status("acc_proj", 1)
        assert status == ChapterStatus.PUBLISHED.value


# ── Test 2 & 3: Editor rejects to Author / Polisher ─────────────

class TestEditorRevisionRouting:
    def test_editor_rejects_to_author(self, repo):
        """Editor fails, revision_target=author -> chapter goes to revision."""
        from novel_factory.agents.editor import EditorAgent

        _seed_project_chapter(repo, status="polished")
        repo.save_chapter_content("acc_proj", 1, _POLISHED_CONTENT, "第一章 验收")

        editor_llm = StubLLMProvider([{
            "pass": False,
            "score": 65,
            "scores": {"setting": 15, "logic": 12, "poison": 13, "text": 12, "pacing": 13},
            "issues": ["逻辑漏洞"],
            "suggestions": ["修复逻辑"],
            "revision_target": "author",
            "state_card": {},
        }])
        editor = EditorAgent(repo, editor_llm)
        result = editor.run(_make_state(chapter_status="polished"))
        assert result["chapter_status"] == ChapterStatus.REVISION.value
        assert result["quality_gate"]["revision_target"] == "author"

    def test_editor_rejects_to_polisher(self, repo):
        """Editor fails, revision_target=polisher -> chapter goes to revision."""
        from novel_factory.agents.editor import EditorAgent

        _seed_project_chapter(repo, status="polished")
        repo.save_chapter_content("acc_proj", 1, _POLISHED_CONTENT, "第一章 验收")

        editor_llm = StubLLMProvider([{
            "pass": False,
            "score": 75,
            "scores": {"setting": 20, "logic": 18, "poison": 15, "text": 10, "pacing": 12},
            "issues": ["AI味太重"],
            "suggestions": ["去除AI烂词"],
            "revision_target": "polisher",
            "state_card": {},
        }])
        editor = EditorAgent(repo, editor_llm)
        result = editor.run(_make_state(chapter_status="polished"))
        assert result["chapter_status"] == ChapterStatus.REVISION.value
        assert result["quality_gate"]["revision_target"] == "polisher"


# ── Test 4: Consecutive rejections trigger blocking ─────────────

class TestCircuitBreaker:
    def test_max_retries_triggers_blocking(self, repo):
        """When retry_count >= max_retries, Editor sends to blocking."""
        from novel_factory.agents.editor import EditorAgent

        _seed_project_chapter(repo, status="polished")
        repo.save_chapter_content("acc_proj", 1, _POLISHED_CONTENT, "第一章 验收")

        # Simulate 3 prior revision tasks
        for _ in range(3):
            conn = repo._conn()
            conn.execute(
                "INSERT INTO task_status (project_id, chapter_number, task_type, agent_id, status) "
                "VALUES (?, ?, 'revise', 'editor', 'completed')",
                ("acc_proj", 1),
            )
            conn.commit()
            conn.close()

        editor_llm = StubLLMProvider([{
            "pass": False,
            "score": 55,
            "scores": {"setting": 12, "logic": 10, "poison": 11, "text": 10, "pacing": 12},
            "issues": ["严重问题"],
            "suggestions": ["需要人工介入"],
            "revision_target": "author",
            "state_card": {},
        }])
        editor = EditorAgent(repo, editor_llm)
        result = editor.run(_make_state(chapter_status="polished", retry_count=3, max_retries=3))
        assert result["chapter_status"] == ChapterStatus.BLOCKING.value
        assert result["current_stage"] == "blocking"

        # Verify chapter status in DB
        status = repo.get_chapter_status("acc_proj", 1)
        assert status == ChapterStatus.BLOCKING.value


# ── Test 5: Invalid output schema does NOT write to DB ──────────

class TestInvalidSchemaNoWrite:
    def test_invalid_author_output_does_not_write(self, repo):
        """When Author output schema is invalid, no content is written to DB."""
        from novel_factory.agents.author import AuthorAgent

        _seed_project_chapter(repo, status="scripted")
        # Add scene beats
        repo.save_scene_beats("acc_proj", 1, [
            {"sequence": 1, "scene_goal": "开场", "conflict": "冲突"},
        ])

        # LLM returns invalid schema (missing required 'content' field)
        bad_llm = StubLLMProvider([{
            "title": "第一章",
            # "content" is missing — schema validation will fail
            "word_count": 500,
        }])
        author = AuthorAgent(repo, bad_llm)
        result = author.run(_make_state(chapter_status="scripted"))

        # Agent should return an error, not change status
        assert "error" in result
        assert result["chapter_status"] == "scripted"  # status unchanged

        # Verify DB was NOT written
        chapter = repo.get_chapter("acc_proj", 1)
        assert chapter.get("content") is None or chapter.get("content") == ""


# ── Test 6: Status precondition mismatch rejects writes ─────────

class TestStatusPrecondition:
    def test_author_rejects_when_status_is_planned(self, repo):
        """Author cannot write when chapter status is 'planned'."""
        from novel_factory.agents.author import AuthorAgent

        _seed_project_chapter(repo, status="planned")

        author_llm = StubLLMProvider([{
            "title": "第一章",
            "content": _LONG_CONTENT,
            "word_count": len(_LONG_CONTENT),
            "implemented_events": [],
            "used_plot_refs": [],
        }])
        author = AuthorAgent(repo, author_llm)
        result = author.run(_make_state(chapter_status="planned"))

        # Should fail with precondition error
        assert "error" in result

        # DB should not have been written
        chapter = repo.get_chapter("acc_proj", 1)
        assert chapter.get("content") is None or chapter.get("content") == ""

    def test_polisher_rejects_when_status_is_scripted(self, repo):
        """Polisher cannot write when chapter status is 'scripted'."""
        from novel_factory.agents.polisher import PolisherAgent

        _seed_project_chapter(repo, status="scripted")

        polisher_llm = StubLLMProvider([{
            "content": _POLISHED_CONTENT,
            "fact_change_risk": "none",
            "changed_scope": ["sentence"],
            "summary": "润色",
        }])
        polisher = PolisherAgent(repo, polisher_llm)
        result = polisher.run(_make_state(chapter_status="scripted"))

        # Should fail with precondition error
        assert "error" in result


# ── Test 7: Death penalty detection ─────────────────────────────

class TestDeathPenaltyValidation:
    def test_author_rejects_death_penalty_words(self, repo):
        """Author output with death penalty words should be rejected."""
        from novel_factory.agents.author import AuthorAgent

        _seed_project_chapter(repo, status="scripted")
        repo.save_scene_beats("acc_proj", 1, [
            {"sequence": 1, "scene_goal": "开场", "conflict": "冲突"},
        ])

        content_with_death_penalty = ("林默冷笑一声，倒吸一口凉气。" + "正常内容填充" * 50)
        author_llm = StubLLMProvider([{
            "title": "第一章",
            "content": content_with_death_penalty,
            "word_count": len(content_with_death_penalty),
            "implemented_events": [],
            "used_plot_refs": [],
        }])
        author = AuthorAgent(repo, author_llm)
        result = author.run(_make_state(chapter_status="scripted"))

        # Should fail validation
        assert "error" in result
        # DB should not be written with death penalty content
        chapter = repo.get_chapter("acc_proj", 1)
        # Content should remain None or unchanged

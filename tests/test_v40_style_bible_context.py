"""v4.0 Style Bible Context integration tests — REAL production paths.

Covers:
- novel_factory.context.builder.ContextBuilder injects Style Bible for all 4 agents
- Author/Planner/Editor Agent.build_context() includes Style Bible
- Polisher (via ContextBuilder) gets Style Bible
- Loader functions work correctly
- Backward compatibility: no Style Bible → no crash, no empty fragment pollution
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from novel_factory.db.connection import init_db, get_connection
from novel_factory.db.repository import Repository
from novel_factory.models.style_bible import (
    StyleBible,
    ForbiddenExpression,
    PreferredExpression,
    AITraceAvoidance,
    StyleRule,
)


# ── Helpers ────────────────────────────────────────────────────


def _ensure_project(db_path: str, project_id: str, name: str = "Test Project") -> None:
    """Insert a project row so FK constraint on style_bibles is satisfied."""
    conn = get_connection(db_path)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO projects (project_id, name) VALUES (?, ?)",
            (project_id, name),
        )
        conn.commit()
    finally:
        conn.close()


def _ensure_chapter(db_path: str, project_id: str, chapter_number: int = 1) -> None:
    """Insert a minimal chapter row for testing."""
    conn = get_connection(db_path)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO chapters (project_id, chapter_number, status) "
            "VALUES (?, ?, 'scripted')",
            (project_id, chapter_number),
        )
        conn.commit()
    finally:
        conn.close()


def _make_bible(project_id: str = "ctx_test") -> StyleBible:
    """Create a StyleBible with distinctive content for assertion."""
    return StyleBible(
        project_id=project_id,
        name="Context Test Bible",
        genre="玄幻",
        prose_style="紧凑",
        dialogue_style="犀利",
        pacing="fast",
        pov="third_person_limited",
        tone_keywords=["热血", "爽快"],
        target_platform="起点",
        target_audience="男性向",
        forbidden_expressions=[
            ForbiddenExpression(pattern="冷笑", reason="AI味", severity="blocking"),
            ForbiddenExpression(pattern="嘴角微扬", reason="模板化", severity="warning"),
        ],
        preferred_expressions=[
            PreferredExpression(pattern="目光一凝", context="战斗前"),
        ],
        ai_trace_avoidance=AITraceAvoidance(
            avoid_patterns=["不禁", "竟然"],
            prefer_patterns=["猛然", "陡然"],
        ),
    )


# ── Fixtures ───────────────────────────────────────────────────


@pytest.fixture
def db_path(tmp_path):
    """Create a temporary database with schema."""
    db = str(tmp_path / "test_v40_context.db")
    init_db(db)
    return db


@pytest.fixture
def repo(db_path):
    return Repository(db_path)


@pytest.fixture
def bible_dict():
    return _make_bible().to_storage_dict()


# ══════════════════════════════════════════════════════════════
# 1. Loader functions
# ══════════════════════════════════════════════════════════════


class TestStyleBibleLoader:
    """Test style_bible.loader functions."""

    def test_load_existing_bible(self, db_path, repo, bible_dict):
        from novel_factory.style_bible.loader import load_style_bible_for_project

        _ensure_project(db_path, "ctx_test")
        repo.save_style_bible("ctx_test", bible_dict)
        bible = load_style_bible_for_project("ctx_test", repo)
        assert bible is not None
        assert bible.name == "Context Test Bible"
        assert bible.genre == "玄幻"

    def test_load_nonexistent_bible(self, db_path, repo):
        from novel_factory.style_bible.loader import load_style_bible_for_project

        bible = load_style_bible_for_project("nonexistent", repo)
        assert bible is None

    def test_get_style_context_for_author(self, db_path, repo, bible_dict):
        from novel_factory.style_bible.loader import get_style_context_for_agent

        _ensure_project(db_path, "ctx_test")
        repo.save_style_bible("ctx_test", bible_dict)
        ctx = get_style_context_for_agent("ctx_test", "author", repo)
        assert "紧凑" in ctx
        assert "写作指引" in ctx

    def test_get_style_context_for_planner(self, db_path, repo, bible_dict):
        from novel_factory.style_bible.loader import get_style_context_for_agent

        _ensure_project(db_path, "ctx_test")
        repo.save_style_bible("ctx_test", bible_dict)
        ctx = get_style_context_for_agent("ctx_test", "planner", repo)
        assert "策划摘要" in ctx
        assert "热血" in ctx

    def test_get_style_context_for_editor(self, db_path, repo, bible_dict):
        from novel_factory.style_bible.loader import get_style_context_for_agent

        _ensure_project(db_path, "ctx_test")
        repo.save_style_bible("ctx_test", bible_dict)
        ctx = get_style_context_for_agent("ctx_test", "editor", repo)
        assert "审校规则" in ctx
        assert "冷笑" in ctx

    def test_get_style_context_no_bible(self, db_path, repo):
        from novel_factory.style_bible.loader import get_style_context_for_agent

        ctx = get_style_context_for_agent("nonexistent", "author", repo)
        assert ctx == ""

    def test_get_style_bible_summary(self, db_path, repo, bible_dict):
        from novel_factory.style_bible.loader import get_style_bible_summary

        _ensure_project(db_path, "ctx_test")
        repo.save_style_bible("ctx_test", bible_dict)
        summary = get_style_bible_summary("ctx_test", repo)
        assert "Context Test Bible" in summary


# ══════════════════════════════════════════════════════════════
# 2. novel_factory.context.builder.ContextBuilder — REAL PATH
# ══════════════════════════════════════════════════════════════


class TestContextBuilderStyleBible:
    """Test novel_factory.context.builder.ContextBuilder with Style Bible.

    This is the REAL production path used by PolisherAgent and any
    future agents that delegate to ContextBuilder.
    """

    def test_builder_author_without_style_bible(self, db_path, repo):
        """ContextBuilder.build_for_author works without Style Bible."""
        from novel_factory.context.builder import ContextBuilder

        builder = ContextBuilder(repo)
        ctx = builder.build_for_author("nonexistent_project", 1)
        assert isinstance(ctx, str)
        # Should NOT contain style_bible fragments
        assert "风格规范" not in ctx

    def test_builder_author_with_style_bible(self, db_path, repo, bible_dict):
        """ContextBuilder.build_for_author injects Style Bible."""
        from novel_factory.context.builder import ContextBuilder

        _ensure_project(db_path, "ctx_test")
        repo.save_style_bible("ctx_test", bible_dict)
        builder = ContextBuilder(repo)
        ctx = builder.build_for_author("ctx_test", 1)
        assert "风格规范" in ctx
        assert "紧凑" in ctx

    def test_builder_polisher_without_style_bible(self, db_path, repo):
        """ContextBuilder.build_for_polisher works without Style Bible."""
        from novel_factory.context.builder import ContextBuilder

        builder = ContextBuilder(repo)
        ctx = builder.build_for_polisher("nonexistent_project", 1)
        assert isinstance(ctx, str)
        assert "风格规范" not in ctx

    def test_builder_polisher_with_style_bible(self, db_path, repo, bible_dict):
        """ContextBuilder.build_for_polisher injects Style Bible."""
        from novel_factory.context.builder import ContextBuilder

        _ensure_project(db_path, "ctx_test")
        repo.save_style_bible("ctx_test", bible_dict)
        builder = ContextBuilder(repo)
        ctx = builder.build_for_polisher("ctx_test", 1)
        assert "风格规范" in ctx
        assert "审校规则" in ctx

    def test_builder_editor_without_style_bible(self, db_path, repo):
        """ContextBuilder.build_for_editor works without Style Bible."""
        from novel_factory.context.builder import ContextBuilder

        builder = ContextBuilder(repo)
        ctx = builder.build_for_editor("nonexistent_project", 1)
        assert isinstance(ctx, str)
        assert "风格规范" not in ctx

    def test_builder_editor_with_style_bible(self, db_path, repo, bible_dict):
        """ContextBuilder.build_for_editor injects Style Bible."""
        from novel_factory.context.builder import ContextBuilder

        _ensure_project(db_path, "ctx_test")
        repo.save_style_bible("ctx_test", bible_dict)
        builder = ContextBuilder(repo)
        ctx = builder.build_for_editor("ctx_test", 1)
        assert "风格规范" in ctx
        assert "审校规则" in ctx

    def test_builder_planner_without_style_bible(self, db_path, repo):
        """ContextBuilder.build_for_planner works without Style Bible."""
        from novel_factory.context.builder import ContextBuilder

        builder = ContextBuilder(repo)
        ctx = builder.build_for_planner("nonexistent_project", 1)
        assert isinstance(ctx, str)
        assert "风格规范" not in ctx

    def test_builder_planner_with_style_bible(self, db_path, repo, bible_dict):
        """ContextBuilder.build_for_planner injects Style Bible."""
        from novel_factory.context.builder import ContextBuilder

        _ensure_project(db_path, "ctx_test")
        repo.save_style_bible("ctx_test", bible_dict)
        builder = ContextBuilder(repo)
        ctx = builder.build_for_planner("ctx_test", 1)
        assert "风格规范" in ctx
        assert "策划摘要" in ctx


# ══════════════════════════════════════════════════════════════
# 3. Agent.build_context() — REAL production path
# ══════════════════════════════════════════════════════════════


class TestAgentBuildContext:
    """Test that Author/Planner/Editor/Polisher Agent.build_context()
    includes Style Bible when available.

    These are the actual code paths called during chapter production.
    """

    def _make_state(self, project_id: str = "ctx_test", chapter_number: int = 1):
        return {
            "project_id": project_id,
            "chapter_number": chapter_number,
            "chapter_status": "scripted",
        }

    def test_author_without_style_bible(self, db_path, repo):
        """Author.build_context() works without Style Bible."""
        from novel_factory.agents.author import AuthorAgent

        _ensure_project(db_path, "ctx_test")
        agent = AuthorAgent(repo, MagicMock())
        ctx = agent.build_context(self._make_state())
        assert isinstance(ctx, str)
        assert "风格规范" not in ctx

    def test_author_with_style_bible(self, db_path, repo, bible_dict):
        """Author.build_context() includes Style Bible when available."""
        from novel_factory.agents.author import AuthorAgent

        _ensure_project(db_path, "ctx_test")
        repo.save_style_bible("ctx_test", bible_dict)
        agent = AuthorAgent(repo, MagicMock())
        ctx = agent.build_context(self._make_state())
        assert "风格规范" in ctx
        assert "写作指引" in ctx
        assert "紧凑" in ctx

    def test_planner_without_style_bible(self, db_path, repo):
        """Planner.build_context() works without Style Bible."""
        from novel_factory.agents.planner import PlannerAgent

        _ensure_project(db_path, "ctx_test")
        agent = PlannerAgent(repo, MagicMock())
        ctx = agent.build_context(self._make_state())
        assert isinstance(ctx, str)
        assert "风格规范" not in ctx

    def test_planner_with_style_bible(self, db_path, repo, bible_dict):
        """Planner.build_context() includes Style Bible when available."""
        from novel_factory.agents.planner import PlannerAgent

        _ensure_project(db_path, "ctx_test")
        repo.save_style_bible("ctx_test", bible_dict)
        agent = PlannerAgent(repo, MagicMock())
        ctx = agent.build_context(self._make_state())
        assert "风格规范" in ctx
        assert "策划摘要" in ctx
        assert "热血" in ctx

    def test_editor_without_style_bible(self, db_path, repo):
        """Editor.build_context() works without Style Bible."""
        from novel_factory.agents.editor import EditorAgent

        _ensure_project(db_path, "ctx_test")
        agent = EditorAgent(repo, MagicMock())
        ctx = agent.build_context(self._make_state())
        assert isinstance(ctx, str)
        assert "风格规范" not in ctx

    def test_editor_with_style_bible(self, db_path, repo, bible_dict):
        """Editor.build_context() includes Style Bible when available."""
        from novel_factory.agents.editor import EditorAgent

        _ensure_project(db_path, "ctx_test")
        repo.save_style_bible("ctx_test", bible_dict)
        agent = EditorAgent(repo, MagicMock())
        ctx = agent.build_context(self._make_state())
        assert "风格规范" in ctx
        assert "审校规则" in ctx
        assert "冷笑" in ctx

    def test_polisher_without_style_bible(self, db_path, repo):
        """Polisher.build_context() (via ContextBuilder) works without Style Bible."""
        from novel_factory.agents.polisher import PolisherAgent

        _ensure_project(db_path, "ctx_test")
        agent = PolisherAgent(repo, MagicMock())
        ctx = agent.build_context(self._make_state())
        assert isinstance(ctx, str)
        assert "风格规范" not in ctx

    def test_polisher_with_style_bible(self, db_path, repo, bible_dict):
        """Polisher.build_context() (via ContextBuilder) includes Style Bible."""
        from novel_factory.agents.polisher import PolisherAgent

        _ensure_project(db_path, "ctx_test")
        repo.save_style_bible("ctx_test", bible_dict)
        agent = PolisherAgent(repo, MagicMock())
        ctx = agent.build_context(self._make_state())
        assert "风格规范" in ctx
        assert "审校规则" in ctx


# ══════════════════════════════════════════════════════════════
# 4. Agent-specific style rules content verification
# ══════════════════════════════════════════════════════════════


class TestAgentStyleContentDetails:
    """Verify that each agent gets the RIGHT style rules for its role.

    This catches cases where agents might get generic instead of
    role-specific style guidance.
    """

    def _make_rich_bible(self, project_id: str = "ctx_test") -> StyleBible:
        """Bible with rules that differ across agent roles."""
        return StyleBible(
            project_id=project_id,
            name="Rich Test Bible",
            genre="玄幻",
            prose_style="干练",
            dialogue_style="简洁",
            pacing="fast",
            tone_keywords=["爽", "燃"],
            target_platform="起点",
            forbidden_expressions=[
                ForbiddenExpression(pattern="不禁", reason="AI味", severity="blocking"),
                ForbiddenExpression(pattern="竟然", reason="廉价惊讶", severity="warning"),
            ],
            preferred_expressions=[
                PreferredExpression(pattern="目光一沉", context="危机"),
            ],
            sentence_rules=[StyleRule(description="单句不超过80字", severity="warning")],
            paragraph_rules=[StyleRule(description="段落不超过500字", severity="warning")],
            chapter_opening_rules=[StyleRule(description="开篇必须有动作", severity="blocking")],
            chapter_ending_rules=[StyleRule(description="结尾必须有钩子", severity="blocking")],
            ai_trace_avoidance=AITraceAvoidance(
                avoid_patterns=["心中暗想"],
                prefer_patterns=["眉头一皱"],
            ),
        )

    def _make_state(self, project_id: str = "ctx_test"):
        return {
            "project_id": project_id,
            "chapter_number": 1,
            "chapter_status": "scripted",
        }

    def test_author_gets_writing_guidance(self, db_path, repo):
        """Author gets prose/dialogue/sentence rules, NOT planner rules."""
        from novel_factory.agents.author import AuthorAgent

        bible = self._make_rich_bible()
        _ensure_project(db_path, "ctx_test")
        repo.save_style_bible("ctx_test", bible.to_storage_dict())
        agent = AuthorAgent(repo, MagicMock())
        ctx = agent.build_context(self._make_state())

        # Author-specific
        assert "写作指引" in ctx
        assert "干练" in ctx
        assert "简洁" in ctx
        # Author should NOT get planner-specific heading
        assert "策划摘要" not in ctx

    def test_planner_gets_structure_guidance(self, db_path, repo):
        """Planner gets tone/pacing/chapter structure rules."""
        from novel_factory.agents.planner import PlannerAgent

        bible = self._make_rich_bible()
        _ensure_project(db_path, "ctx_test")
        repo.save_style_bible("ctx_test", bible.to_storage_dict())
        agent = PlannerAgent(repo, MagicMock())
        ctx = agent.build_context(self._make_state())

        # Planner-specific
        assert "策划摘要" in ctx
        assert "开篇规则" in ctx
        assert "结尾规则" in ctx
        # Planner should NOT get author-specific heading
        assert "写作指引" not in ctx

    def test_editor_gets_review_rules(self, db_path, repo):
        """Editor gets forbidden/ai-trace/paragraph rules."""
        from novel_factory.agents.editor import EditorAgent

        bible = self._make_rich_bible()
        _ensure_project(db_path, "ctx_test")
        repo.save_style_bible("ctx_test", bible.to_storage_dict())
        agent = EditorAgent(repo, MagicMock())
        ctx = agent.build_context(self._make_state())

        # Editor/Polisher-specific
        assert "审校规则" in ctx
        assert "不禁" in ctx
        assert "段落规则" in ctx
        # Editor should NOT get author/planner headings
        assert "写作指引" not in ctx
        assert "策划摘要" not in ctx

    def test_polisher_gets_review_rules(self, db_path, repo):
        """Polisher (via ContextBuilder) gets forbidden/ai-trace rules."""
        from novel_factory.agents.polisher import PolisherAgent

        bible = self._make_rich_bible()
        _ensure_project(db_path, "ctx_test")
        repo.save_style_bible("ctx_test", bible.to_storage_dict())
        agent = PolisherAgent(repo, MagicMock())
        ctx = agent.build_context(self._make_state())

        # Editor/Polisher share the same style rules
        assert "审校规则" in ctx
        assert "不禁" in ctx

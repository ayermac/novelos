"""Tests for v6.10.13 internal repair prompt compaction.

These tests verify that Author and Polisher distinguish internal quality-gate
repairs from real Editor revisions and use compact prompts for internal repairs.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from novel_factory.agents.author import AuthorAgent
from novel_factory.agents.polisher import PolisherAgent
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
    db_path = tmp_path / "test_internal_repair.db"
    init_db(db_path)
    return str(db_path)


@pytest.fixture
def repo(tmp_db):
    return Repository(tmp_db)


class TestInternalRepairDetection:
    """Verify BaseAgent helpers distinguish internal repair from Editor revision."""

    def test_internal_repair_flag_detected(self, repo):
        agent = AuthorAgent(repo, StubLLMProvider())
        state: FactoryState = {
            "project_id": "test",
            "chapter_number": 1,
            "chapter_status": ChapterStatus.REVISION.value,
            "quality_gate": {
                "pass": False,
                "internal_repair": True,
                "repair_scope": "internal_word_count_compression",
            },
        }
        assert agent._is_internal_repair(state) is True
        assert agent._is_editor_revision(state) is False

    def test_quality_gate_without_internal_repair_is_editor_revision(self, repo):
        agent = AuthorAgent(repo, StubLLMProvider())
        state: FactoryState = {
            "project_id": "test",
            "chapter_number": 1,
            "chapter_status": ChapterStatus.REVISION.value,
            "quality_gate": {
                "pass": False,
                "blocking_issues": ["章间衔接断裂"],
            },
        }
        # v6.10.13-fix: Narrow quality-gate failures (continuity, word-count,
        # death-penalty, etc.) are deterministic repairs and should use compact
        # prompts, not full Editor revision context.  Only real Editor revisions
        # (with review_id or score) should load the full Editor feedback.
        assert agent._is_internal_repair(state) is True
        assert agent._is_editor_revision(state) is False

    def test_quality_gate_with_review_id_is_editor_revision(self, repo):
        agent = AuthorAgent(repo, StubLLMProvider())
        state: FactoryState = {
            "project_id": "test",
            "chapter_number": 1,
            "chapter_status": ChapterStatus.REVISION.value,
            "quality_gate": {
                "pass": False,
                "review_id": 123,
                "score": 60,
                "blocking_issues": ["章间衔接断裂"],
            },
        }
        assert agent._is_internal_repair(state) is False
        assert agent._is_editor_revision(state) is True

    def test_revision_review_in_state_is_editor_revision(self, repo):
        agent = AuthorAgent(repo, StubLLMProvider())
        state: FactoryState = {
            "project_id": "test",
            "chapter_number": 1,
            "chapter_status": ChapterStatus.REVISION.value,
            "_revision_review": {
                "review_id": "rev-1",
                "score": 70,
                "revision_target": "author",
                "issues": ["issue"],
                "suggestions": ["suggestion"],
            },
        }
        assert agent._is_internal_repair(state) is False
        assert agent._is_editor_revision(state) is True

    def test_internal_repair_instruction_for_word_count_compression(self, repo):
        agent = AuthorAgent(repo, StubLLMProvider())
        state: FactoryState = {
            "project_id": "test",
            "chapter_number": 1,
            "chapter_status": ChapterStatus.REVISION.value,
            "quality_gate": {
                "pass": False,
                "internal_repair": True,
                "repair_scope": "internal_word_count_compression",
                "word_target": 5000,
            },
        }
        instruction = agent._build_internal_repair_instruction(state)
        assert "字数压缩" in instruction
        assert "5000" in instruction

    def test_internal_repair_instruction_for_expansion_drift(self, repo):
        agent = AuthorAgent(repo, StubLLMProvider())
        state: FactoryState = {
            "project_id": "test",
            "chapter_number": 1,
            "chapter_status": ChapterStatus.REVISION.value,
            "quality_gate": {
                "pass": False,
                "internal_repair": True,
                "repair_scope": "internal_polisher_expansion_drift",
                "original_word_count": 3759,
                "polished_word_count": 4588,
                "word_count_delta": 829,
            },
        }
        instruction = agent._build_internal_repair_instruction(state)
        assert "扩写漂移" in instruction
        assert "3759" in instruction
        assert "4588" in instruction

    def test_context_limit_reduced_for_internal_repair(self, repo):
        agent = AuthorAgent(repo, StubLLMProvider())
        agent.context_char_limit = 12000
        internal_state: FactoryState = {
            "project_id": "test",
            "chapter_number": 1,
            "chapter_status": ChapterStatus.REVISION.value,
            "quality_gate": {
                "pass": False,
                "internal_repair": True,
                "repair_scope": "internal_word_count_compression",
            },
        }
        normal_state: FactoryState = {
            "project_id": "test",
            "chapter_number": 1,
            "chapter_status": "scripted",
        }
        assert agent._get_context_char_limit(internal_state) < 7000
        assert agent._get_context_char_limit(normal_state) == 12000


class TestInternalRepairPromptCompaction:
    """Verify Author/Polisher build_context compacts internal repair prompts."""

    def test_author_internal_repair_skips_editor_feedback(self, repo):
        agent = AuthorAgent(repo, StubLLMProvider())
        internal_state: FactoryState = {
            "project_id": "test",
            "chapter_number": 1,
            "chapter_status": ChapterStatus.REVISION.value,
            "_revision_review": {
                "review_id": "rev-1",
                "score": 50,
                "revision_target": "author",
                "issues": ["editor issue 1", "editor issue 2"],
                "suggestions": ["editor suggestion 1"],
            },
            "quality_gate": {
                "pass": False,
                "internal_repair": True,
                "repair_scope": "internal_word_count_compression",
                "word_target": 5000,
            },
        }
        context = agent.build_context(internal_state)
        # Should not load the full Editor feedback block
        assert "editor issue 1" not in context
        assert "editor suggestion 1" not in context
        # Should contain the compact repair instruction
        assert "内部修复" in context
        assert "字数压缩" in context

    def test_author_nested_word_count_repair_preserves_editor_feedback(self, repo):
        agent = AuthorAgent(repo, StubLLMProvider())
        internal_state: FactoryState = {
            "project_id": "test",
            "chapter_number": 1,
            "chapter_status": ChapterStatus.REVISION.value,
            "_revision_review": {
                "review_id": "rev-keep",
                "score": 44,
                "revision_target": "author",
                "issues": ["时间线倒退，必须修正 00:00:29 的来源"],
                "suggestions": ["保留已修正文段，只补足场景细节"],
            },
            "quality_gate": {
                "pass": False,
                "word_count_fail": True,
                "internal_repair": True,
                "consume_revision_retry": False,
                "repair_scope": "internal_word_count_expansion",
                "actual_word_count": 1660,
                "word_target": 3000,
                "preserve_revision_feedback": True,
                "revision_source_review_id": "rev-keep",
            },
        }

        context = agent.build_context(internal_state)

        assert "内部修复：字数扩写" in context
        assert "时间线倒退" in context
        assert "只补足场景细节" in context

    def test_author_editor_revision_includes_feedback(self, repo):
        agent = AuthorAgent(repo, StubLLMProvider())
        editor_state: FactoryState = {
            "project_id": "test",
            "chapter_number": 1,
            "chapter_status": ChapterStatus.REVISION.value,
            "_revision_review": {
                "review_id": "rev-1",
                "score": 50,
                "revision_target": "author",
                "issues": ["editor issue 1"],
                "suggestions": ["editor suggestion 1"],
            },
        }
        context = agent.build_context(editor_state)
        assert "editor issue 1" in context
        assert "editor suggestion 1" in context

    def test_polisher_internal_repair_skips_editor_feedback(self, repo):
        agent = PolisherAgent(repo, StubLLMProvider())
        internal_state: FactoryState = {
            "project_id": "test",
            "chapter_number": 1,
            "chapter_status": ChapterStatus.REVISION.value,
            "_revision_review": {
                "review_id": "rev-1",
                "score": 50,
                "revision_target": "polisher",
                "issues": ["polisher issue 1"],
                "suggestions": ["polisher suggestion 1"],
            },
            "quality_gate": {
                "pass": False,
                "internal_repair": True,
                "repair_scope": "internal_polisher_expansion_drift",
                "original_word_count": 3759,
                "polished_word_count": 4588,
                "word_count_delta": 829,
            },
        }
        context = agent.build_context(internal_state)
        assert "polisher issue 1" not in context
        assert "polisher suggestion 1" not in context
        assert "内部修复" in context
        assert "扩写漂移" in context

    def test_polisher_editor_revision_includes_feedback(self, repo):
        agent = PolisherAgent(repo, StubLLMProvider())
        editor_state: FactoryState = {
            "project_id": "test",
            "chapter_number": 1,
            "chapter_status": ChapterStatus.REVISION.value,
            "_revision_review": {
                "review_id": "rev-1",
                "score": 50,
                "revision_target": "polisher",
                "issues": ["polisher issue 1"],
                "suggestions": ["polisher suggestion 1"],
            },
        }
        context = agent.build_context(editor_state)
        assert "polisher issue 1" in context
        assert "polisher suggestion 1" in context

"""v6.8.5: Quality Gate 独立节点测试

测试覆盖：
- quality_gate_node() 独立测试
- route_by_quality_gate() 路由测试
- 边界条件测试
"""

from __future__ import annotations

import json
import os
import tempfile

import pytest

from novel_factory.models.state import ChapterStatus, FactoryState
from novel_factory.db.connection import init_db
from novel_factory.db.repository import Repository


# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def tmp_repo(tmp_path):
    """Create a temporary repository for testing."""
    db_path = str(tmp_path / "test.db")
    repo = Repository(db_path)
    init_db(db_path)
    return repo


@pytest.fixture
def seeded_repo(tmp_repo):
    """Seed a repository with test project and chapter."""
    conn = tmp_repo._conn()
    try:
        conn.execute(
            "INSERT INTO projects (project_id, name, genre, total_chapters_planned, description, target_words) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("test-proj", "Test Project", "fantasy", 10, "测试简介", 100000),
        )
        conn.execute(
            "INSERT INTO chapters (project_id, chapter_number, title, status, content, word_count) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("test-proj", 1, "第一章 测试", "polished", "测试内容" * 1000, 5000),
        )
        conn.execute(
            "INSERT INTO instructions (project_id, chapter_number, objective, key_events, "
            "plots_to_plant, plots_to_resolve, ending_hook, word_target, status) "
            "VALUES (?, ?, '测试目标', '[]', '[]', '[]', '悬念', 2500, 'active')",
            ("test-proj", 1),
        )
        conn.commit()
    finally:
        conn.close()
    return tmp_repo


# ── quality_gate_node 测试 ────────────────────────────────────────


class TestQualityGateNode:
    """Test quality_gate_node independent quality checks."""

    def test_quality_gate_passes_with_valid_content(self, seeded_repo):
        """quality_gate_node should pass with valid content meeting all checks."""
        from novel_factory.workflow.nodes import quality_gate_node

        state: FactoryState = {
            "project_id": "test-proj",
            "chapter_number": 1,
            "chapter_status": "polished",
            "llm_mode": "stub",
        }

        result = quality_gate_node(state, seeded_repo)

        assert "quality_gate" in result
        assert result["quality_gate"]["passed"] is True
        assert result["quality_gate"]["pass"] is True
        assert result["quality_gate"]["score"] >= 80
        assert len(result["quality_gate"]["blocking_issues"]) == 0
        assert result["quality_gate"]["revision_target"] is None

    def test_quality_gate_fails_with_empty_content(self, tmp_repo):
        """quality_gate_node should fail when chapter content is empty."""
        from novel_factory.workflow.nodes import quality_gate_node

        conn = tmp_repo._conn()
        try:
            conn.execute(
                "INSERT INTO projects (project_id, name, genre, total_chapters_planned, description, target_words) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("test-proj", "Test Project", "fantasy", 10, "测试简介", 100000),
            )
            conn.execute(
                "INSERT INTO chapters (project_id, chapter_number, title, status, content, word_count) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("test-proj", 1, "第一章 测试", "polished", "", 0),
            )
            conn.commit()
        finally:
            conn.close()

        state: FactoryState = {
            "project_id": "test-proj",
            "chapter_number": 1,
            "chapter_status": "polished",
            "llm_mode": "stub",
        }

        result = quality_gate_node(state, tmp_repo)

        assert "error" in result
        assert result["requires_human"] is True

    def test_quality_gate_fails_with_missing_chapter(self, tmp_repo):
        """quality_gate_node should fail when chapter does not exist."""
        from novel_factory.workflow.nodes import quality_gate_node

        conn = tmp_repo._conn()
        try:
            conn.execute(
                "INSERT INTO projects (project_id, name, genre, total_chapters_planned, description, target_words) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("test-proj", "Test Project", "fantasy", 10, "测试简介", 100000),
            )
            conn.commit()
        finally:
            conn.close()

        state: FactoryState = {
            "project_id": "test-proj",
            "chapter_number": 999,
            "chapter_status": "polished",
            "llm_mode": "stub",
        }

        result = quality_gate_node(state, tmp_repo)

        assert "error" in result
        assert result["requires_human"] is True

    def test_quality_gate_fails_with_word_count_below_target(self, tmp_repo):
        """quality_gate_node should fail when word count is below target."""
        from novel_factory.workflow.nodes import quality_gate_node

        conn = tmp_repo._conn()
        try:
            conn.execute(
                "INSERT INTO projects (project_id, name, genre, total_chapters_planned, description, target_words) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("test-proj", "Test Project", "fantasy", 10, "测试简介", 100000),
            )
            conn.execute(
                "INSERT INTO chapters (project_id, chapter_number, title, status, content, word_count) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("test-proj", 1, "第一章 测试", "polished", "短内容", 3),
            )
            conn.execute(
                "INSERT INTO instructions (project_id, chapter_number, objective, key_events, "
                "plots_to_plant, plots_to_resolve, ending_hook, word_target, status) "
                "VALUES (?, ?, '测试目标', '[]', '[]', '[]', '悬念', 2500, 'active')",
                ("test-proj", 1),
            )
            conn.commit()
        finally:
            conn.close()

        state: FactoryState = {
            "project_id": "test-proj",
            "chapter_number": 1,
            "chapter_status": "polished",
            "llm_mode": "stub",
        }

        result = quality_gate_node(state, tmp_repo)

        assert result["quality_gate"]["passed"] is False
        assert result["quality_gate"]["revision_target"] == "polisher"
        assert any("字数" in i for i in result["quality_gate"]["blocking_issues"])

    def test_quality_gate_fails_with_death_penalty(self, tmp_repo):
        """quality_gate_node should fail with death penalty violations."""
        from novel_factory.workflow.nodes import quality_gate_node

        conn = tmp_repo._conn()
        try:
            conn.execute(
                "INSERT INTO projects (project_id, name, genre, total_chapters_planned, description, target_words) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("test-proj", "Test Project", "fantasy", 10, "测试简介", 100000),
            )
            conn.execute(
                "INSERT INTO chapters (project_id, chapter_number, title, status, content, word_count) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("test-proj", 1, "第一章 测试", "polished",
                 "他冷笑一声，嘴角微微上扬。" * 100, 1000),
            )
            conn.execute(
                "INSERT INTO instructions (project_id, chapter_number, objective, key_events, "
                "plots_to_plant, plots_to_resolve, ending_hook, word_target, status) "
                "VALUES (?, ?, '测试目标', '[]', '[]', '[]', '悬念', 500, 'active')",
                ("test-proj", 1),
            )
            conn.commit()
        finally:
            conn.close()

        state: FactoryState = {
            "project_id": "test-proj",
            "chapter_number": 1,
            "chapter_status": "polished",
            "llm_mode": "stub",
        }

        result = quality_gate_node(state, tmp_repo)

        assert result["quality_gate"]["passed"] is False
        assert result["quality_gate"]["score"] <= 50
        assert result["quality_gate"]["revision_target"] == "author"

    def test_quality_gate_returns_diagnostics(self, seeded_repo):
        """quality_gate_node should return detailed diagnostics."""
        from novel_factory.workflow.nodes import quality_gate_node

        state: FactoryState = {
            "project_id": "test-proj",
            "chapter_number": 1,
            "chapter_status": "polished",
            "llm_mode": "stub",
        }

        result = quality_gate_node(state, seeded_repo)

        diagnostics = result["quality_gate"]["diagnostics"]
        assert "death_penalty" in diagnostics
        assert "word_count_gate" in diagnostics
        assert "chapter_seam" in diagnostics
        assert "continuity_gate" in diagnostics

    def test_quality_gate_returns_checks_run(self, seeded_repo):
        """quality_gate_node should return list of checks run."""
        from novel_factory.workflow.nodes import quality_gate_node

        state: FactoryState = {
            "project_id": "test-proj",
            "chapter_number": 1,
            "chapter_status": "polished",
            "llm_mode": "stub",
        }

        result = quality_gate_node(state, seeded_repo)

        checks_run = result["quality_gate"]["checks_run"]
        assert "death_penalty" in checks_run
        assert "word_count_gate" in checks_run
        assert "chapter_seam" in checks_run
        assert "continuity_gate" in checks_run

    def test_quality_gate_handles_blocking_db_status(self, tmp_repo):
        """quality_gate_node should guard against blocking DB status."""
        from novel_factory.workflow.nodes import quality_gate_node

        conn = tmp_repo._conn()
        try:
            conn.execute(
                "INSERT INTO projects (project_id, name, genre, total_chapters_planned, description, target_words) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("test-proj", "Test Project", "fantasy", 10, "测试简介", 100000),
            )
            conn.execute(
                "INSERT INTO chapters (project_id, chapter_number, title, status, content, word_count) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("test-proj", 1, "第一章 测试", "blocking", "测试内容", 100),
            )
            conn.commit()
        finally:
            conn.close()

        state: FactoryState = {
            "project_id": "test-proj",
            "chapter_number": 1,
            "chapter_status": "blocking",
            "llm_mode": "stub",
        }

        result = quality_gate_node(state, tmp_repo)

        # Should return blocking guard result
        assert "error" in result or result.get("requires_human") is True


# ── route_by_quality_gate 测试 ────────────────────────────────────


class TestRouteByQualityGate:
    """Test route_by_quality_gate routing logic."""

    def test_routes_to_editor_when_passed(self):
        """Should route to editor when quality gate passes."""
        from novel_factory.workflow.conditions import route_by_quality_gate

        state: FactoryState = {
            "quality_gate": {"passed": True, "pass": True},
        }

        result = route_by_quality_gate(state)

        assert result == "editor"

    def test_routes_to_revision_router_when_failed(self):
        """Should route to revision_router when quality gate fails."""
        from novel_factory.workflow.conditions import route_by_quality_gate

        state: FactoryState = {
            "quality_gate": {"passed": False, "pass": False},
            "retry_count": 0,
            "max_retries": 3,
        }

        result = route_by_quality_gate(state)

        assert result == "revision_router"

    def test_routes_to_human_review_when_max_retries_exceeded(self):
        """Should route to human_review when max retries exceeded."""
        from novel_factory.workflow.conditions import route_by_quality_gate

        state: FactoryState = {
            "quality_gate": {"passed": False, "pass": False},
            "retry_count": 3,
            "max_retries": 3,
        }

        result = route_by_quality_gate(state)

        assert result == "human_review"

    def test_routes_to_human_review_on_error(self):
        """Should route to human_review when error is set."""
        from novel_factory.workflow.conditions import route_by_quality_gate

        state: FactoryState = {
            "quality_gate": {"passed": True, "pass": True},
            "error": "some error",
        }

        result = route_by_quality_gate(state)

        assert result == "human_review"

    def test_routes_to_human_review_when_requires_human(self):
        """Should route to human_review when requires_human is set."""
        from novel_factory.workflow.conditions import route_by_quality_gate

        state: FactoryState = {
            "quality_gate": {"passed": True, "pass": True},
            "requires_human": True,
        }

        result = route_by_quality_gate(state)

        assert result == "human_review"

    def test_handles_missing_quality_gate(self):
        """Should handle missing quality_gate gracefully."""
        from novel_factory.workflow.conditions import route_by_quality_gate

        state: FactoryState = {}

        result = route_by_quality_gate(state)

        # Missing quality_gate defaults to failed
        assert result == "revision_router"

    def test_handles_empty_quality_gate(self):
        """Should handle empty quality_gate gracefully."""
        from novel_factory.workflow.conditions import route_by_quality_gate

        state: FactoryState = {"quality_gate": {}}

        result = route_by_quality_gate(state)

        # Empty quality_gate defaults to failed
        assert result == "revision_router"


# ── 边界条件测试 ──────────────────────────────────────────────────


class TestQualityGateEdgeCases:
    """Test edge cases for quality gate."""

    def test_quality_gate_with_no_skill_registry(self, seeded_repo):
        """quality_gate_node should work without skill_registry."""
        from novel_factory.workflow.nodes import quality_gate_node

        state: FactoryState = {
            "project_id": "test-proj",
            "chapter_number": 1,
            "chapter_status": "polished",
            "llm_mode": "stub",
        }

        # Pass None as skill_registry
        result = quality_gate_node(state, seeded_repo, skill_registry=None)

        assert "quality_gate" in result
        assert result["quality_gate"]["passed"] is True
        # quality_diagnosis should not be in checks_run without skill_registry
        assert "quality_diagnosis" not in result["quality_gate"]["checks_run"]

    def test_quality_gate_preserves_existing_state(self, seeded_repo):
        """quality_gate_node should not modify unrelated state fields."""
        from novel_factory.workflow.nodes import quality_gate_node

        state: FactoryState = {
            "project_id": "test-proj",
            "chapter_number": 1,
            "chapter_status": "polished",
            "llm_mode": "stub",
            "retry_count": 2,
            "max_retries": 3,
        }

        result = quality_gate_node(state, seeded_repo)

        # Should only return quality_gate field
        assert "quality_gate" in result
        assert "retry_count" not in result
        assert "max_retries" not in result

    def test_quality_gate_score_range(self, seeded_repo):
        """quality_gate_node score should be in valid range."""
        from novel_factory.workflow.nodes import quality_gate_node

        state: FactoryState = {
            "project_id": "test-proj",
            "chapter_number": 1,
            "chapter_status": "polished",
            "llm_mode": "stub",
        }

        result = quality_gate_node(state, seeded_repo)

        score = result["quality_gate"]["score"]
        assert 0 <= score <= 100

    def test_quality_gate_timestamp_format(self, seeded_repo):
        """quality_gate_node should return valid ISO timestamp."""
        from novel_factory.workflow.nodes import quality_gate_node

        state: FactoryState = {
            "project_id": "test-proj",
            "chapter_number": 1,
            "chapter_status": "polished",
            "llm_mode": "stub",
        }

        result = quality_gate_node(state, seeded_repo)

        timestamp = result["quality_gate"]["timestamp"]
        # Should be valid ISO format
        assert "T" in timestamp
        assert "+" in timestamp or "Z" in timestamp

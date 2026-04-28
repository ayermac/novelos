"""Tests for v5.3.0 Trusted Generation Chain.

Tests cover:
1. Context Readiness Gate
2. Planner 必经 routing
3. 字数硬质量门
4. 禁止真实模式自动发布
5. Manual publish API
6. API integration: run_chapter awaiting_publish, publish chapter, error cases
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from novel_factory.validators.context_readiness import (
    check_context_readiness,
    ContextReadinessResult,
    format_readiness_error,
    _outline_covers_chapter,
)
from novel_factory.validators.chapter_checker import (
    check_word_count_quality_gate,
    derive_word_target,
    count_words,
    QUALITY_GATE_AUTHOR_THRESHOLD,
    QUALITY_GATE_EDITOR_THRESHOLD,
)
from novel_factory.workflow.conditions import route_by_chapter_status, route_by_review_result
from novel_factory.models.state import ChapterStatus, FactoryState


# ── 1. Context Readiness Gate Tests ─────────────────────────────────────────────

class TestContextReadinessGate:
    """Tests for context readiness validation."""

    def test_complete_context_is_ready(self):
        """A project with all required context should be ready."""
        project = {
            "description": "一部玄幻小说",
            "target_words": 1500000,
            "total_chapters_planned": 500,
        }
        world_settings = [{"category": "world", "title": "世界观", "content": "修仙世界"}]
        characters = [{"name": "张三", "role": "protagonist", "description": "主角"}]
        outlines = [{"level": "chapter", "chapters_range": "1-10", "title": "第一卷"}]
        instruction = {"objective": "测试指令", "word_target": 3000}

        result = check_context_readiness(
            project=project,
            world_settings=world_settings,
            characters=characters,
            outlines=outlines,
            instruction=instruction,
            chapter_number=1,
            chapter_status="planned",
        )

        assert result.ready is True
        assert len(result.missing) == 0

    def test_missing_description_fails(self):
        """Missing project description should fail readiness check."""
        project = {
            "description": "",  # Empty description
            "target_words": 1500000,
            "total_chapters_planned": 500,
        }
        world_settings = [{"category": "world", "title": "世界观", "content": "修仙世界"}]
        characters = [{"name": "张三", "role": "protagonist", "description": "主角"}]
        outlines = [{"level": "chapter", "chapters_range": "1-10", "title": "第一卷"}]
        instruction = {"objective": "测试指令", "word_target": 3000}

        result = check_context_readiness(
            project=project,
            world_settings=world_settings,
            characters=characters,
            outlines=outlines,
            instruction=instruction,
            chapter_number=1,
            chapter_status="planned",
        )

        assert result.ready is False
        assert "项目简介" in result.missing
        assert any("项目设置中填写项目简介" in a for a in result.actions)

    def test_missing_world_settings_fails(self):
        """Missing world settings should fail readiness check."""
        project = {
            "description": "一部玄幻小说",
            "target_words": 1500000,
            "total_chapters_planned": 500,
        }
        world_settings = []  # Empty world settings
        characters = [{"name": "张三", "role": "protagonist", "description": "主角"}]
        outlines = [{"level": "chapter", "chapters_range": "1-10", "title": "第一卷"}]
        instruction = {"objective": "测试指令", "word_target": 3000}

        result = check_context_readiness(
            project=project,
            world_settings=world_settings,
            characters=characters,
            outlines=outlines,
            instruction=instruction,
            chapter_number=1,
            chapter_status="planned",
        )

        assert result.ready is False
        assert "世界观设定" in result.missing

    def test_missing_protagonist_fails(self):
        """Missing protagonist should fail readiness check."""
        project = {
            "description": "一部玄幻小说",
            "target_words": 1500000,
            "total_chapters_planned": 500,
        }
        world_settings = [{"category": "world", "title": "世界观", "content": "修仙世界"}]
        characters = [{"name": "李四", "role": "antagonist", "description": "反派"}]  # No protagonist
        outlines = [{"level": "chapter", "chapters_range": "1-10", "title": "第一卷"}]
        instruction = {"objective": "测试指令", "word_target": 3000}

        result = check_context_readiness(
            project=project,
            world_settings=world_settings,
            characters=characters,
            outlines=outlines,
            instruction=instruction,
            chapter_number=1,
            chapter_status="planned",
        )

        assert result.ready is False
        assert "主角角色" in result.missing

    def test_missing_outline_coverage_fails(self):
        """Missing outline coverage for chapter should fail readiness check."""
        project = {
            "description": "一部玄幻小说",
            "target_words": 1500000,
            "total_chapters_planned": 500,
        }
        world_settings = [{"category": "world", "title": "世界观", "content": "修仙世界"}]
        characters = [{"name": "张三", "role": "protagonist", "description": "主角"}]
        outlines = [{"level": "chapter", "chapters_range": "1-10", "title": "第一卷"}]
        instruction = {"objective": "测试指令", "word_target": 3000}

        # Requesting chapter 20 which is not covered
        result = check_context_readiness(
            project=project,
            world_settings=world_settings,
            characters=characters,
            outlines=outlines,
            instruction=instruction,
            chapter_number=20,
            chapter_status="planned",
        )

        assert result.ready is False
        assert "第20章大纲" in result.missing

    def test_volume_outline_covering_chapter_is_ready(self):
        """A volume/arc outline covering the chapter should satisfy readiness."""
        project = {
            "description": "一部玄幻小说",
            "target_words": 1500000,
            "total_chapters_planned": 500,
        }
        world_settings = [{"category": "world", "title": "世界观", "content": "修仙世界"}]
        characters = [{"name": "张三", "role": "protagonist", "description": "主角"}]
        outlines = [{"level": "volume", "chapters_range": "1-10", "title": "第一卷"}]
        instruction = None

        result = check_context_readiness(
            project=project,
            world_settings=world_settings,
            characters=characters,
            outlines=outlines,
            instruction=instruction,
            chapter_number=1,
            chapter_status="planned",
        )

        assert result.ready is True
        assert result.details["has_outline_coverage"] is True

    def test_no_instruction_but_can_enter_planner(self):
        """No instruction but status allows planner entry should pass."""
        project = {
            "description": "一部玄幻小说",
            "target_words": 1500000,
            "total_chapters_planned": 500,
        }
        world_settings = [{"category": "world", "title": "世界观", "content": "修仙世界"}]
        characters = [{"name": "张三", "role": "protagonist", "description": "主角"}]
        outlines = [{"level": "chapter", "chapters_range": "1-10", "title": "第一卷"}]
        instruction = None  # No instruction

        # Status 'idea' can enter planner
        result = check_context_readiness(
            project=project,
            world_settings=world_settings,
            characters=characters,
            outlines=outlines,
            instruction=instruction,
            chapter_number=1,
            chapter_status="idea",
        )

        assert result.ready is True

    def test_format_readiness_error(self):
        """Test error formatting for API response."""
        result = ContextReadinessResult(
            ready=False,
            missing=["项目简介", "主角角色"],
            actions=["请填写项目简介", "请添加主角"],
            details={"has_description": False, "protagonist_count": 0},
        )

        error = format_readiness_error(result)

        assert error["error_code"] == "PROJECT_CONTEXT_INCOMPLETE"
        assert error["message"] == "项目资料不完整，无法生成章节"
        assert "项目简介" in error["missing"]
        assert "主角角色" in error["missing"]


class TestOutlineCoversChapter:
    """Tests for outline chapter coverage checking."""

    def test_single_chapter_match(self):
        """Single chapter number should match exactly."""
        assert _outline_covers_chapter("5", 5) is True
        assert _outline_covers_chapter("5", 6) is False

    def test_range_coverage(self):
        """Range should cover chapters within it."""
        assert _outline_covers_chapter("1-10", 1) is True
        assert _outline_covers_chapter("1-10", 5) is True
        assert _outline_covers_chapter("1-10", 10) is True
        assert _outline_covers_chapter("1-10", 11) is False

    def test_empty_range(self):
        """Empty range should return False."""
        assert _outline_covers_chapter("", 1) is False
        assert _outline_covers_chapter(None, 1) is False


# ── 2. Planner 必经 Routing Tests ─────────────────────────────────────────────

class TestPlannerRouting:
    """Tests for Planner 必经 routing logic."""

    def test_planned_without_instruction_routes_to_planner(self):
        """Planned status without instruction should route to planner."""
        state: FactoryState = {
            "project_id": "test",
            "chapter_number": 1,
            "chapter_status": ChapterStatus.PLANNED.value,
            "has_instruction": False,
        }

        result = route_by_chapter_status(state)
        assert result == "planner"

    def test_planned_with_instruction_routes_to_screenwriter(self):
        """Planned status with instruction should route to screenwriter."""
        state: FactoryState = {
            "project_id": "test",
            "chapter_number": 1,
            "chapter_status": ChapterStatus.PLANNED.value,
            "has_instruction": True,
        }

        result = route_by_chapter_status(state)
        assert result == "screenwriter"

    def test_idea_always_routes_to_planner(self):
        """Idea status should always route to planner."""
        state: FactoryState = {
            "project_id": "test",
            "chapter_number": 1,
            "chapter_status": ChapterStatus.IDEA.value,
            "has_instruction": False,
        }

        result = route_by_chapter_status(state)
        assert result == "planner"

    def test_error_routes_to_human_review(self):
        """Error state should route to human review."""
        state: FactoryState = {
            "project_id": "test",
            "chapter_number": 1,
            "chapter_status": ChapterStatus.PLANNED.value,
            "has_instruction": True,
            "error": "Something went wrong",
        }

        result = route_by_chapter_status(state)
        assert result == "human_review"


# ── 3. 字数硬质量门 Tests ─────────────────────────────────────────────────────

class TestWordCountQualityGate:
    """Tests for word count quality gate."""

    def test_author_passes_threshold(self):
        """Author output meeting 85% threshold should pass."""
        content = "x" * 2500  # 2500 words
        word_target = 3000
        # 85% of 3000 = 2550, but we check against threshold
        # Actually 2500 / 3000 = 83.3%, which is < 85%, so this should fail
        passed, message = check_word_count_quality_gate(content, word_target, "author")
        assert passed is False

    def test_author_meets_threshold(self):
        """Author output meeting exactly 85% threshold should pass."""
        content = "x" * 2600  # 2600 words
        word_target = 3000
        # 85% of 3000 = 2550, 2600 > 2550, should pass
        passed, message = check_word_count_quality_gate(content, word_target, "author")
        assert passed is True

    def test_editor_stricter_threshold(self):
        """Editor has stricter 90% threshold."""
        content = "x" * 2600  # 2600 words
        word_target = 3000
        # 90% of 3000 = 2700, 2600 < 2700, should fail for editor
        passed, message = check_word_count_quality_gate(content, word_target, "editor")
        assert passed is False

    def test_editor_passes_stricter_threshold(self):
        """Editor output meeting 90% threshold should pass."""
        content = "x" * 2750  # 2750 words
        word_target = 3000
        # 90% of 3000 = 2700, 2750 > 2700, should pass
        passed, message = check_word_count_quality_gate(content, word_target, "editor")
        assert passed is True

    def test_empty_content_fails(self):
        """Empty content should always fail."""
        passed, message = check_word_count_quality_gate("", 3000, "author")
        assert passed is False
        assert "空" in message


class TestDeriveWordTarget:
    """Tests for word target derivation."""

    def test_instruction_word_target_takes_precedence(self):
        """Instruction word_target should take precedence."""
        instruction = {"word_target": 5000}
        project = {"target_words": 1500000, "total_chapters_planned": 500}

        result = derive_word_target(instruction, project)
        assert result == 5000

    def test_derive_from_project_settings(self):
        """Should derive from project settings if no instruction word_target."""
        instruction = {"objective": "test"}  # No word_target
        project = {"target_words": 1500000, "total_chapters_planned": 500}

        result = derive_word_target(instruction, project)
        assert result == 3000  # 1500000 / 500 = 3000

    def test_minimum_2000(self):
        """Should enforce minimum of 2000."""
        instruction = {"word_target": 1000}  # Below minimum
        project = {"target_words": 1500000, "total_chapters_planned": 500}

        result = derive_word_target(instruction, project)
        assert result == 2000

    def test_default_fallback(self):
        """Should return default when no data available."""
        instruction = None
        project = {}

        result = derive_word_target(instruction, project)
        assert result == 2500


# ── 4. 禁止真实模式自动发布 Tests ─────────────────────────────────────────────

class TestRealModeAutoPublishBlocking:
    """Tests for blocking auto-publish in real mode."""

    def test_stub_mode_auto_publish(self):
        """Stub mode should route to publisher after pass."""
        state: FactoryState = {
            "project_id": "test",
            "chapter_number": 1,
            "chapter_status": ChapterStatus.REVIEWED.value,
            "llm_mode": "stub",
            "quality_gate": {"pass": True},
        }

        result = route_by_review_result(state)
        assert result == "publish"

    def test_real_mode_no_auto_publish(self):
        """Real mode should route to awaiting_publish, not publish."""
        state: FactoryState = {
            "project_id": "test",
            "chapter_number": 1,
            "chapter_status": ChapterStatus.REVIEWED.value,
            "llm_mode": "real",
            "quality_gate": {"pass": True},
        }

        result = route_by_review_result(state)
        assert result == "awaiting_publish"

    def test_failed_review_routes_to_revise(self):
        """Failed review should route to revise regardless of mode."""
        state_stub: FactoryState = {
            "project_id": "test",
            "chapter_number": 1,
            "chapter_status": ChapterStatus.POLISHED.value,
            "llm_mode": "stub",
            "quality_gate": {"pass": False},
            "retry_count": 0,
            "max_retries": 3,
        }

        state_real: FactoryState = {
            "project_id": "test",
            "chapter_number": 1,
            "chapter_status": ChapterStatus.POLISHED.value,
            "llm_mode": "real",
            "quality_gate": {"pass": False},
            "retry_count": 0,
            "max_retries": 3,
        }

        assert route_by_review_result(state_stub) == "revise"
        assert route_by_review_result(state_real) == "revise"

    def test_max_retries_routes_to_human_review(self):
        """Max retries exceeded should route to human review."""
        state: FactoryState = {
            "project_id": "test",
            "chapter_number": 1,
            "chapter_status": ChapterStatus.POLISHED.value,
            "llm_mode": "real",
            "quality_gate": {"pass": False},
            "retry_count": 3,
            "max_retries": 3,
        }

        result = route_by_review_result(state)
        assert result == "human_review"


# ── Integration Tests ─────────────────────────────────────────────────────────

class TestIntegration:
    """Integration tests for v5.3.0 features."""

    def test_full_workflow_stub_mode(self):
        """Test that stub mode workflow still auto-publishes."""
        # This is a conceptual test - actual integration test would need DB
        state: FactoryState = {
            "project_id": "test",
            "chapter_number": 1,
            "chapter_status": ChapterStatus.PLANNED.value,
            "has_instruction": True,
            "llm_mode": "stub",
            "quality_gate": {},
            "retry_count": 0,
            "max_retries": 3,
        }

        # Should route to screenwriter (has instruction)
        assert route_by_chapter_status(state) == "screenwriter"

        # After pass, should route to publish
        state["quality_gate"] = {"pass": True}
        assert route_by_review_result(state) == "publish"

    def test_full_workflow_real_mode(self):
        """Test that real mode workflow stops at reviewed."""
        state: FactoryState = {
            "project_id": "test",
            "chapter_number": 1,
            "chapter_status": ChapterStatus.PLANNED.value,
            "has_instruction": True,
            "llm_mode": "real",
            "quality_gate": {},
            "retry_count": 0,
            "max_retries": 3,
        }

        # Should route to screenwriter (has instruction)
        assert route_by_chapter_status(state) == "screenwriter"

        # After pass, should route to awaiting_publish (NOT publish)
        state["quality_gate"] = {"pass": True}
        assert route_by_review_result(state) == "awaiting_publish"


# ── 6. API Integration Tests ──────────────────────────────────────────────────

class TestAPIPublishIntegration:
    """v5.3.0 API integration tests for publish workflow."""

    @pytest.fixture
    def api_client(self):
        """Create test client with temporary database."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            from novel_factory.db.connection import init_db
            init_db(db_path)

            from novel_factory.api_app import create_api_app
            from fastapi.testclient import TestClient

            # Use stub mode by default (safe for tests)
            app = create_api_app(db_path=db_path, llm_mode="stub")
            client = TestClient(app)
            yield client, db_path
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)
            # Also clean up checkpoint DB if created
            cp_path = Path(db_path).with_suffix(".checkpoints.db")
            if cp_path.exists():
                os.unlink(str(cp_path))

    @pytest.fixture
    def real_mode_client(self):
        """Create test client with real mode LLM but stub provider (no API keys needed).

        Monkeypatches _validate_llm_config so that the workflow can run
        through the real-mode routing path without actual LLM API keys.
        """
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            from novel_factory.db.connection import init_db
            init_db(db_path)

            from novel_factory.api_app import create_api_app
            from fastapi.testclient import TestClient

            app = create_api_app(db_path=db_path, llm_mode="real")
            client = TestClient(app)
            yield client, db_path
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)
            cp_path = Path(db_path).with_suffix(".checkpoints.db")
            if cp_path.exists():
                os.unlink(str(cp_path))

    def _seed_project(self, client, db_path, project_id="test_publish_001"):
        """Create a project and seed context for readiness gate."""
        client.post(
            "/api/onboarding/projects",
            json={
                "project_id": project_id,
                "name": "测试发布小说",
                "genre": "玄幻",
                "target_words": 100000,
                "initial_chapter_count": 3,
            },
        )
        from conftest import seed_context_for_chapter
        seed_context_for_chapter(db_path, project_id, 1)

    def test_real_mode_run_returns_awaiting_publish(self, real_mode_client, monkeypatch):
        """Real mode run should return awaiting_publish=true after editor pass.

        Uses monkeypatch to bypass LLM config validation and inject stub LLM
        router so the workflow can complete without real API keys, while still
        exercising the real-mode routing path (route_by_review_result → awaiting_publish).
        """
        client, db_path = real_mode_client
        self._seed_project(client, db_path)

        # Bypass LLM config validation + force stub router so real-mode
        # routing logic (awaiting_publish) is exercised without real API keys.
        # The key: llm_mode="real" is preserved in the workflow state so
        # route_by_review_result returns "awaiting_publish", but the actual
        # LLM calls use the stub provider.
        from novel_factory.workflow import runner as runner_mod
        monkeypatch.setattr(runner_mod, "_validate_llm_config", lambda *a, **kw: None)
        original_build = runner_mod._build_llm_router

        def _force_stub_router(settings, llm_mode="stub"):
            # Always build stub router regardless of llm_mode argument
            return original_build(settings, llm_mode="stub")

        monkeypatch.setattr(runner_mod, "_build_llm_router", _force_stub_router)

        resp = client.post(
            "/api/run/chapter",
            json={"project_id": "test_publish_001", "chapter": 1},
        )
        assert resp.status_code == 200
        data = resp.json()

        # Strong assertions: real mode must complete and await manual publish
        assert data["ok"] is True, f"Expected ok=True, got: {data}"
        result = data["data"]
        assert result["workflow_status"] == "completed", (
            f"Expected workflow_status='completed', got: {result.get('workflow_status')}"
        )
        assert result["chapter_status"] == "reviewed", (
            f"Expected chapter_status='reviewed', got: {result.get('chapter_status')}"
        )
        assert result["awaiting_publish"] is True, (
            f"Expected awaiting_publish=True, got: {result.get('awaiting_publish')}"
        )
        assert result["requires_human"] is True, (
            f"Expected requires_human=True, got: {result.get('requires_human')}"
        )
        # Message should indicate awaiting manual publish
        assert "人工" in result.get("message", "") or "待人工" in result.get("message", ""), (
            f"Expected message to mention manual publish, got: {result.get('message')}"
        )

    def test_publish_reviewed_chapter(self, api_client):
        """POST /run/publish/chapter should publish a reviewed chapter."""
        client, db_path = api_client
        self._seed_project(client, db_path)

        # First set chapter to reviewed status
        from novel_factory.db.repository import Repository
        repo = Repository(db_path)
        repo.update_chapter_status("test_publish_001", 1, "reviewed")

        resp = client.post(
            "/api/publish/chapter",
            json={"project_id": "test_publish_001", "chapter": 1},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["data"]["chapter_status"] == "published"

    def test_publish_non_reviewed_returns_invalid_status(self, api_client):
        """Publishing a non-reviewed chapter should return INVALID_STATUS."""
        client, db_path = api_client
        self._seed_project(client, db_path)

        # Chapter is in 'planned' status by default
        resp = client.post(
            "/api/publish/chapter",
            json={"project_id": "test_publish_001", "chapter": 1},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert data["error"]["code"] == "INVALID_STATUS"

    def test_publish_nonexistent_project(self, api_client):
        """Publishing a chapter in non-existent project returns PROJECT_NOT_FOUND."""
        client, db_path = api_client

        resp = client.post(
            "/api/publish/chapter",
            json={"project_id": "nonexistent_project", "chapter": 1},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert data["error"]["code"] == "PROJECT_NOT_FOUND"

    def test_publish_nonexistent_chapter(self, api_client):
        """Publishing a non-existent chapter returns CHAPTER_NOT_FOUND."""
        client, db_path = api_client
        self._seed_project(client, db_path)

        resp = client.post(
            "/api/publish/chapter",
            json={"project_id": "test_publish_001", "chapter": 999},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert data["error"]["code"] == "CHAPTER_NOT_FOUND"

    def test_run_chapter_returns_awaiting_publish_field(self, api_client):
        """Run chapter response should include awaiting_publish field."""
        client, db_path = api_client
        self._seed_project(client, db_path)

        resp = client.post(
            "/api/run/chapter",
            json={"project_id": "test_publish_001", "chapter": 1},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        # awaiting_publish should be present in response (false for stub mode)
        assert "awaiting_publish" in data["data"]
        assert data["data"]["awaiting_publish"] is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

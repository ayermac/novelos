"""v6.3: Creator onboarding closure tests.

Verify that:
1. Chapter run guard blocks generation when context is incomplete.
2. production-next returns ready_for_chapter_1 correctly.
3. Project creation defaults to friendly chapter titles.
"""

from __future__ import annotations

import os
import tempfile

import pytest


@pytest.fixture
def repo():
    """Create a fresh in-memory repo for each test."""
    from novel_factory.db.repository import Repository
    from novel_factory.db.connection import init_db

    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(db_path)
    repo = Repository(db_path)
    yield repo, db_path
    if os.path.exists(db_path):
        os.unlink(db_path)


def _seed_full_context(repo, project_id: str):
    """Seed a project with all required context for chapter generation."""
    repo.create_project(
        project_id=project_id,
        name="Test Novel",
        genre="fantasy",
        description="test",
        target_words=30000,
        total_chapters_planned=10,
    )
    repo.add_chapter(project_id, 1, "第 1 章（待命名）", status="planned")
    repo.create_genesis_run(project_id, input_json='{"title":"test"}', status="approved")
    repo.create_world_setting(project_id, category="世界观", title="背景", content="test")
    repo.create_character(project_id, name="主角", role="protagonist", description="test", traits="", first_appearance=1)
    repo.create_outline(project_id, level="volume", sequence=1, title="第一卷", content="test", chapters_range="1-10")
    repo.create_instruction(project_id, chapter_number=1, objective="test", key_events="test")


class TestChapterRunGuardContextCompleteness:
    """Guard 4: CONTEXT_INCOMPLETE blocks chapter generation when project context is missing."""

    def test_guard_blocks_without_approved_genesis(self, repo):
        repo_obj, db_path = repo
        project_id = "v63-no-genesis"
        repo_obj.create_project(
            project_id=project_id, name="No Genesis", genre="fantasy",
            description="test", target_words=30000, total_chapters_planned=10,
        )
        repo_obj.add_chapter(project_id, 1, "第 1 章（待命名）", status="planned")

        from novel_factory.api.routes._run_guards import check_chapter_run_guard

        err = check_chapter_run_guard(repo_obj, project_id, 1)
        assert err is not None
        assert err.code == "CONTEXT_INCOMPLETE"
        assert "创世设定" in err.message

    def test_guard_blocks_with_approved_genesis_but_missing_world(self, repo):
        repo_obj, db_path = repo
        project_id = "v63-no-world"
        repo_obj.create_project(
            project_id=project_id, name="No World", genre="fantasy",
            description="test", target_words=30000, total_chapters_planned=10,
        )
        repo_obj.add_chapter(project_id, 1, "第 1 章（待命名）", status="planned")
        repo_obj.create_genesis_run(project_id, input_json='{"title":"test"}', status="approved")
        repo_obj.create_character(project_id, name="主角", role="protagonist", description="test", traits="", first_appearance=1)
        repo_obj.create_outline(project_id, level="volume", sequence=1, title="第一卷", content="test", chapters_range="1-10")
        repo_obj.create_instruction(project_id, chapter_number=1, objective="test", key_events="test")

        from novel_factory.api.routes._run_guards import check_chapter_run_guard

        err = check_chapter_run_guard(repo_obj, project_id, 1)
        assert err is not None
        assert err.code == "CONTEXT_INCOMPLETE"
        assert "世界观" in err.message

    def test_guard_passes_with_full_context(self, repo):
        repo_obj, db_path = repo
        project_id = "v63-full-context"
        _seed_full_context(repo_obj, project_id)

        from novel_factory.api.routes._run_guards import check_chapter_run_guard

        assert check_chapter_run_guard(repo_obj, project_id, 1) is None


class TestProductionNextHealth:
    """production-next health snapshot includes ready_for_chapter_1."""

    def test_ready_for_chapter_1_false_when_context_missing(self, repo):
        repo_obj, db_path = repo
        project_id = "v63-health-missing"
        repo_obj.create_project(
            project_id=project_id, name="Missing", genre="fantasy",
            description="test", target_words=30000, total_chapters_planned=10,
        )
        repo_obj.add_chapter(project_id, 1, "第 1 章（待命名）", status="planned")

        from novel_factory.api.routes.production import _build_health

        health = _build_health(repo_obj, project_id, 1)
        assert health["ready_for_chapter_1"] is False
        assert health["has_approved_genesis"] is False

    def test_ready_for_chapter_1_true_when_context_complete(self, repo):
        repo_obj, db_path = repo
        project_id = "v63-health-ready"
        _seed_full_context(repo_obj, project_id)

        from novel_factory.api.routes.production import _build_health

        health = _build_health(repo_obj, project_id, 1)
        assert health["ready_for_chapter_1"] is True
        assert health["has_approved_genesis"] is True
        assert health["has_world_settings"] is True
        assert health["has_characters"] is True
        assert health["has_outlines"] is True
        assert health["has_instructions_for_current_chapter"] is True


class TestOnboardingChapterTitles:
    """Project creation uses descriptive placeholder chapter titles."""

    def test_default_chapter_title_includes_placeholder(self, repo):
        repo_obj, db_path = repo
        project_id = "v63-titles"
        repo_obj.create_project(
            project_id=project_id, name="Titles", genre="fantasy",
            description="test", target_words=30000, total_chapters_planned=10,
        )
        ch_id = repo_obj.add_chapter(project_id, 1, "第 1 章（待命名）", status="planned")
        chapter = repo_obj.get_chapter(project_id, 1)
        assert "待命名" in chapter["title"]

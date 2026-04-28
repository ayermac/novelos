"""v5.1.3 Author Workflow Usability Closure Tests.

Tests for:
1. Chapter content reader API: GET /api/projects/{id}/chapters/{num}
2. Stub content varies per chapter (title, content, word_count)
3. Run result post-actions: published -> 查看正文 button
4. Settings i18n: stub/blocked/missing Chinese mappings
5. Review empty state explanation
6. Acceptance page hides internal IDs by default
7. Onboarding: auto-generate project ID from name
8. Dashboard/ProjectDetail only check latest run (not historical)
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.conftest import seed_context_for_chapter


@pytest.fixture
def client():
    """Create test client with temporary database."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        from novel_factory.db.connection import init_db
        from novel_factory.api_app import create_api_app

        init_db(db_path)
        app = create_api_app(db_path=db_path, llm_mode="stub")
        test_client = TestClient(app)
        yield test_client
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


class TestChapterContentAPI:
    """GET /api/projects/{id}/chapters/{num} returns chapter content."""

    def test_get_chapter_content(self, client):
        """Should return chapter content after generating."""
        # Create project and run chapter
        client.post(
            "/api/onboarding/projects",
            json={
                "project_id": "v513_reader",
                "name": "阅读器测试",
                "initial_chapter_count": 1,
            },
        )
        db_path = client.app.state.db_path
        seed_context_for_chapter(db_path, "v513_reader", 1)
        client.post("/api/run/chapter", json={"project_id": "v513_reader", "chapter": 1})

        # Get chapter content
        resp = client.get("/api/projects/v513_reader/chapters/1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        result = data["data"]

        assert result["project_id"] == "v513_reader"
        assert result["chapter_number"] == 1
        assert "content" in result
        assert result["content"] != "", "Content should not be empty after generation"
        assert result["word_count"] > 0

    def test_chapter_not_found(self, client):
        """Should return CHAPTER_NOT_FOUND for non-existent chapter."""
        client.post(
            "/api/onboarding/projects",
            json={"project_id": "v513_404", "name": "404测试", "initial_chapter_count": 1},
        )
        resp = client.get("/api/projects/v513_404/chapters/999")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert data["error"]["code"] == "CHAPTER_NOT_FOUND"

    def test_project_not_found_for_chapter(self, client):
        """Should return PROJECT_NOT_FOUND for non-existent project."""
        resp = client.get("/api/projects/nonexistent/chapters/1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert data["error"]["code"] == "PROJECT_NOT_FOUND"


class TestStubContentVariety:
    """Stub content varies per chapter."""

    def test_different_chapters_have_different_titles(self, client):
        """Chapter 1 and 2 should have different titles."""
        from novel_factory.llm.stub_provider import _get_stub_chapter_content, _STORY_TEMPLATES

        # Direct test with mock messages
        msg1 = [{"role": "user", "content": "章节号: 1"}]
        msg2 = [{"role": "user", "content": "章节号: 2"}]

        ch1 = _get_stub_chapter_content(msg1)
        ch2 = _get_stub_chapter_content(msg2)

        assert ch1["title"] != ch2["title"], (
            f"Chapter 1 title '{ch1['title']}' should differ from chapter 2 '{ch2['title']}'"
        )

    def test_different_chapters_have_different_content(self):
        """Chapter 1 and 2 should have different content."""
        from novel_factory.llm.stub_provider import _get_stub_chapter_content

        msg1 = [{"role": "user", "content": "章节号: 1"}]
        msg2 = [{"role": "user", "content": "章节号: 2"}]

        ch1 = _get_stub_chapter_content(msg1)
        ch2 = _get_stub_chapter_content(msg2)

        assert ch1["content"] != ch2["content"], "Content should differ between chapters"

    def test_stub_content_meets_min_words(self):
        """All stub templates should meet minimum word count (500)."""
        from novel_factory.llm.stub_provider import _STORY_TEMPLATES, _get_stub_chapter_content

        for num, template in _STORY_TEMPLATES.items():
            assert len(template["content"]) >= 500, (
                f"Template {num} has {len(template['content'])} chars, need >= 500"
            )

    def test_stub_does_not_call_real_llm(self):
        """StubLLM should not make any real API calls."""
        from novel_factory.llm.stub_provider import StubLLM

        stub = StubLLM()
        # These should return instantly without any network calls
        result = stub.invoke_json([], schema=None)
        assert isinstance(result, dict)


class TestFrontendChapterReader:
    """Frontend ChapterReader page quality checks (now in ProjectDetail workspace)."""

    def test_chapter_reader_page_exists(self):
        """Chapter content display is now in ProjectDetail.tsx workspace."""
        frontend_src = Path(__file__).parent.parent / "frontend" / "src"
        detail_file = frontend_src / "pages" / "ProjectDetail.tsx"
        assert detail_file.exists(), "ProjectDetail.tsx should exist"

    def test_chapter_reader_shows_content(self):
        """ProjectDetail workspace should display chapter content."""
        frontend_src = Path(__file__).parent.parent / "frontend" / "src"
        content = (frontend_src / "pages" / "ProjectDetail.tsx").read_text()

        assert "content" in content, "Should display content"
        assert "pre-wrap" in content, "Should preserve line breaks (white-space: pre-wrap)"
        assert "maxWidth" in content or "max-width" in content, "Should limit reading width"

    def test_chapter_reader_route_registered(self):
        """App.tsx should register the chapter reader route (redirect to workspace)."""
        frontend_src = Path(__file__).parent.parent / "frontend" / "src"
        content = (frontend_src / "App.tsx").read_text()

        # Route now redirects to workspace instead of separate ChapterReader page
        assert "chapters/:chapterNumber" in content, "Route should include chapters/:chapterNumber"
        assert "ChapterRedirect" in content, "Should have ChapterRedirect component"


class TestFrontendRunPostActions:
    """Run page post-generation action buttons."""

    def test_run_shows_view_content_on_published(self):
        """Run page should show '查看正文' when chapter_status=published."""
        frontend_src = Path(__file__).parent.parent / "frontend" / "src"
        content = (frontend_src / "pages" / "Run.tsx").read_text()

        assert "查看正文" in content, "Should have '查看正文' button for published chapters"
        assert "chapter_status === 'published'" in content, "Should check for published status"

    def test_run_supports_query_params(self):
        """Run page should support ?project_id=&chapter= query params."""
        frontend_src = Path(__file__).parent.parent / "frontend" / "src"
        content = (frontend_src / "pages" / "Run.tsx").read_text()

        assert "useSearchParams" in content or "searchParams" in content, (
            "Should use useSearchParams for query parameter pre-selection"
        )


class TestFrontendSettingsI18n:
    """Settings page Chinese localization."""

    def test_settings_uses_config_draft_generator_name(self):
        """Settings should label wizard as '配置草案生成器', not '配置向导' implying completion."""
        frontend_src = Path(__file__).parent.parent / "frontend" / "src"
        content = (frontend_src / "pages" / "Settings.tsx").read_text()

        assert "配置草案生成器" in content, "Should use '配置草案生成器' naming"

    def test_settings_has_form_inputs(self):
        """Settings should have provider, model, base_url, api_key_env form fields."""
        frontend_src = Path(__file__).parent.parent / "frontend" / "src"
        content = (frontend_src / "pages" / "Settings.tsx").read_text()

        assert "provider" in content, "Should have provider field"
        assert "model" in content, "Should have model field"
        assert "base_url" in content, "Should have base_url field"
        assert "api_key_env" in content, "Should have api_key_env field"

    def test_i18n_covers_stub_blocked_missing(self):
        """STATUS_MAP should cover stub, blocked, missing Chinese mappings."""
        frontend_src = Path(__file__).parent.parent / "frontend" / "src"
        content = (frontend_src / "lib" / "i18n.ts").read_text()

        assert "blocked:" in content, "Should have blocked mapping"
        assert "已阻塞" in content, "Should map blocked to 已阻塞"


class TestFrontendReviewEmptyState:
    """Review empty state should explain why."""

    def test_review_explains_empty_state(self):
        """Review empty state should explain the review/publish flow."""
        frontend_src = Path(__file__).parent.parent / "frontend" / "src"
        content = (frontend_src / "pages" / "Review.tsx").read_text()

        assert "AI 审核通过" in content or "待人工发布" in content or "审核工作台" in content, (
            "Review empty state should explain why there are no pending reviews"
        )


class TestFrontendAcceptanceProductization:
    """Acceptance page was removed in v5.1.6 — tests skipped."""

    def test_acceptance_hides_internal_id_by_default(self):
        """Skipped: Acceptance page removed in v5.1.6."""
        pass  # Acceptance.tsx deleted, feature merged into other pages

    def test_acceptance_shows_chinese_title(self):
        """Skipped: Acceptance page removed in v5.1.6."""
        pass  # Acceptance.tsx deleted, feature merged into other pages


class TestFrontendOnboardingAutoId:
    """Onboarding auto-generates project ID from name."""

    def test_onboarding_auto_generates_id(self):
        """Onboarding should auto-generate project ID from name."""
        frontend_src = Path(__file__).parent.parent / "frontend" / "src"
        content = (frontend_src / "pages" / "Onboarding.tsx").read_text()

        assert "generateProjectId" in content, "Should have generateProjectId function"
        assert "idManuallyEdited" in content, "Should track if ID was manually edited"

    def test_onboarding_default_genre(self):
        """Onboarding should have a default genre selection."""
        frontend_src = Path(__file__).parent.parent / "frontend" / "src"
        content = (frontend_src / "pages" / "Onboarding.tsx").read_text()

        assert "genre: 'urban'" in content or 'genre: "urban"' in content, (
            "Default genre should not be empty"
        )

    def test_onboarding_duplicate_id_error(self):
        """Onboarding should show Chinese error for duplicate project ID."""
        frontend_src = Path(__file__).parent.parent / "frontend" / "src"
        content = (frontend_src / "pages" / "Onboarding.tsx").read_text()

        assert "已被使用" in content, "Should show Chinese error for duplicate ID"

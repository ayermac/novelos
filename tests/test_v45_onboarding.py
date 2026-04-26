"""Tests for v4.5 Personal Novel Project Onboarding.

Focus on testing real business state changes, not HTML content.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from novel_factory.db.connection import get_connection, init_db
from novel_factory.db.repository import Repository
from novel_factory.web.app import create_app


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".db", delete=False) as f:
        db_path = f.name
    
    # Initialize database
    init_db(db_path)
    
    yield db_path
    
    # Cleanup
    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def client(temp_db):
    """Create a test client."""
    app = create_app(db_path=temp_db, config_path=None, llm_mode="stub")
    return TestClient(app)


class TestOnboardingForm:
    """Test onboarding form display."""

    def test_onboarding_page_loads(self, client):
        """GET /onboarding returns 200 with form."""
        response = client.get("/onboarding")
        assert response.status_code == 200
        assert b"project_id" in response.content
        assert b"name" in response.content
        assert b"style_template" in response.content

    def test_onboarding_shows_v40_style_templates(self, client):
        """Onboarding form shows v4.0 Style Bible templates."""
        response = client.get("/onboarding")
        assert response.status_code == 200
        # Should show templates from config/style_bible_templates.yaml
        assert b"default_web_serial" in response.content
        assert b"urban_fantasy_fast" in response.content
        assert b"xianxia_progression" in response.content


class TestProjectCreation:
    """Test project creation via onboarding."""

    def test_create_minimal_project(self, client, temp_db):
        """Create project with minimal required fields."""
        response = client.post(
            "/onboarding/project",
            data={
                "project_id": "test_novel_001",
                "name": "Test Novel",
                "genre": "",
                "description": "",
                "total_chapters_planned": 500,
                "target_words": 1500000,
                "start_chapter": 1,
                "initial_chapter_count": 10,
                "style_template": "default_web_serial",
                "opening_objective": "",
                "world_setting": "",
                "main_character_name": "",
                "main_character_role": "protagonist",
                "main_character_description": "",
                "create_serial_plan": "",
                "serial_batch_size": 5,
            },
        )
        assert response.status_code == 200
        assert b"success" in response.content.lower() or b"Success" in response.content

        # Verify project created in DB
        repo = Repository(temp_db)
        project = repo.get_project("test_novel_001")
        assert project is not None
        assert project["name"] == "Test Novel"

    def test_create_project_with_all_fields(self, client, temp_db):
        """Create project with all optional fields."""
        response = client.post(
            "/onboarding/project",
            data={
                "project_id": "test_novel_002",
                "name": "Full Novel",
                "genre": "玄幻",
                "description": "A fantasy novel for testing",
                "total_chapters_planned": 1000,
                "target_words": 3000000,
                "start_chapter": 1,
                "initial_chapter_count": 20,
                "style_template": "xianxia_progression",
                "opening_objective": "Introduce protagonist and world",
                "world_setting": "A magical world with ancient powers",
                "main_character_name": "张三",
                "main_character_role": "protagonist",
                "main_character_description": "Young hero with hidden powers",
                "create_serial_plan": "on",
                "serial_batch_size": 10,
            },
        )
        assert response.status_code == 200

        # Verify all entities created in DB
        repo = Repository(temp_db)
        
        # Check project
        project = repo.get_project("test_novel_002")
        assert project is not None
        assert project["name"] == "Full Novel"
        assert project["genre"] == "玄幻"
        assert project["description"] == "A fantasy novel for testing"
        assert project["total_chapters_planned"] == 1000
        assert project["target_words"] == 3000000

        # Check chapters
        chapters = repo.list_chapters("test_novel_002")
        assert len(chapters) == 20
        for i, ch in enumerate(chapters, start=1):
            assert ch["chapter_number"] == i
            assert ch["status"] == "planned"

        # Check instruction
        instruction = repo.get_instruction("test_novel_002", 1)
        assert instruction is not None
        assert instruction["objective"] == "Introduce protagonist and world"

        # Check world setting
        world_settings = repo.get_world_settings("test_novel_002")
        assert len(world_settings) == 1
        assert world_settings[0]["content"] == "A magical world with ancient powers"

        # Check character
        characters = repo.get_characters("test_novel_002")
        assert len(characters) == 1
        assert characters[0]["name"] == "张三"
        assert characters[0]["role"] == "protagonist"

        # Check Style Bible
        style_bible = repo.get_style_bible("test_novel_002")
        assert style_bible is not None
        assert style_bible["genre"] == "玄幻"
        # Verify it's using v4.0 template
        bible = style_bible.get("bible", {})
        assert "tone_keywords" in bible  # v4.0 template field

        # Check Serial Plan
        serial_plans = repo.list_serial_plans(project_id="test_novel_002")
        assert len(serial_plans) == 1
        assert serial_plans[0]["batch_size"] == 10

    def test_create_project_with_custom_start_chapter(self, client, temp_db):
        """Create project starting from chapter 10."""
        response = client.post(
            "/onboarding/project",
            data={
                "project_id": "test_novel_003",
                "name": "Late Start Novel",
                "genre": "都市",
                "description": "",
                "total_chapters_planned": 500,
                "target_words": 1500000,
                "start_chapter": 10,
                "initial_chapter_count": 5,
                "style_template": "urban_fantasy_fast",
                "opening_objective": "Continue the story",
                "world_setting": "",
                "main_character_name": "",
                "main_character_role": "protagonist",
                "main_character_description": "",
                "create_serial_plan": "",
                "serial_batch_size": 5,
            },
        )
        assert response.status_code == 200

        # Verify chapters start from 10
        repo = Repository(temp_db)
        chapters = repo.list_chapters("test_novel_003")
        assert len(chapters) == 5
        assert chapters[0]["chapter_number"] == 10
        assert chapters[-1]["chapter_number"] == 14

    def test_duplicate_project_id_rejected(self, client, temp_db):
        """Creating project with duplicate ID shows error."""
        # Create first project
        client.post(
            "/onboarding/project",
            data={
                "project_id": "duplicate_test",
                "name": "First Project",
                "genre": "",
                "description": "",
                "total_chapters_planned": 500,
                "target_words": 1500000,
                "start_chapter": 1,
                "initial_chapter_count": 10,
                "style_template": "default_web_serial",
                "opening_objective": "",
                "world_setting": "",
                "main_character_name": "",
                "main_character_role": "protagonist",
                "main_character_description": "",
                "create_serial_plan": "",
                "serial_batch_size": 5,
            },
        )

        # Try to create duplicate
        response = client.post(
            "/onboarding/project",
            data={
                "project_id": "duplicate_test",
                "name": "Second Project",
                "genre": "",
                "description": "",
                "total_chapters_planned": 500,
                "target_words": 1500000,
                "start_chapter": 1,
                "initial_chapter_count": 10,
                "style_template": "default_web_serial",
                "opening_objective": "",
                "world_setting": "",
                "main_character_name": "",
                "main_character_role": "protagonist",
                "main_character_description": "",
                "create_serial_plan": "",
                "serial_batch_size": 5,
            },
        )
        assert response.status_code == 400
        assert "已存在" in response.text or "already exists" in response.text.lower()

    def test_invalid_chapter_count_rejected(self, client):
        """Creating project with 0 chapters shows error."""
        response = client.post(
            "/onboarding/project",
            data={
                "project_id": "invalid_chapters",
                "name": "Invalid Novel",
                "genre": "",
                "description": "",
                "total_chapters_planned": 500,
                "target_words": 1500000,
                "start_chapter": 1,
                "initial_chapter_count": 0,
                "style_template": "modern_urban",
                "opening_objective": "",
                "world_setting": "",
                "main_character_name": "",
                "main_character_role": "protagonist",
                "main_character_description": "",
                "create_serial_plan": "",
                "serial_batch_size": 5,
            },
        )
        assert response.status_code == 400
        assert "至少为 1" in response.text or "at least 1" in response.text.lower()

    def test_invalid_style_template_rejected(self, client):
        """Creating project with invalid template shows error."""
        response = client.post(
            "/onboarding/project",
            data={
                "project_id": "invalid_template",
                "name": "Invalid Template Novel",
                "genre": "",
                "description": "",
                "total_chapters_planned": 500,
                "target_words": 1500000,
                "start_chapter": 1,
                "initial_chapter_count": 10,
                "style_template": "nonexistent_template",
                "opening_objective": "",
                "world_setting": "",
                "main_character_name": "",
                "main_character_role": "protagonist",
                "main_character_description": "",
                "create_serial_plan": "",
                "serial_batch_size": 5,
            },
        )
        assert response.status_code == 400
        assert "无效的风格模板" in response.text or "invalid" in response.text.lower()

    def test_total_chapters_less_than_initial_count_rejected(self, client, temp_db):
        """Creating project with total_chapters < initial_chapter_count shows error."""
        response = client.post(
            "/onboarding/project",
            data={
                "project_id": "invalid_chapters_range",
                "name": "Invalid Chapters Range",
                "genre": "",
                "description": "",
                "total_chapters_planned": 5,
                "target_words": 1500000,
                "start_chapter": 1,
                "initial_chapter_count": 10,  # More than total_chapters_planned
                "style_template": "default_web_serial",
                "opening_objective": "",
                "world_setting": "",
                "main_character_name": "",
                "main_character_role": "protagonist",
                "main_character_description": "",
                "create_serial_plan": "",
                "serial_batch_size": 5,
            },
        )
        assert response.status_code == 400
        assert "计划总章节数" in response.text or "total_chapters" in response.text.lower()
        
        # Verify no project created
        repo = Repository(temp_db)
        project = repo.get_project("invalid_chapters_range")
        assert project is None


class TestNavigationIntegration:
    """Test navigation integration."""

    def test_dashboard_has_onboarding_link(self, client):
        """Dashboard shows link to onboarding."""
        response = client.get("/")
        assert response.status_code == 200
        assert b"/onboarding" in response.content

    def test_projects_page_has_onboarding_link(self, client, temp_db):
        """Projects page shows link to onboarding."""
        # Create a project first so page loads
        repo = Repository(temp_db)
        conn = get_connection(temp_db)
        try:
            conn.execute(
                "INSERT INTO projects (project_id, name, genre, total_chapters_planned) "
                "VALUES (?, ?, ?, ?)",
                ("nav_test", "Nav Test", "fantasy", 100),
            )
            conn.commit()
        finally:
            conn.close()

        response = client.get("/projects")
        assert response.status_code == 200
        assert b"/onboarding" in response.content


class TestRepositoryMethods:
    """Test new Repository methods."""

    def test_create_project_method(self, temp_db):
        """Repository.create_project() creates project record."""
        repo = Repository(temp_db)
        repo.create_project(
            project_id="repo_test_001",
            name="Repo Test Novel",
            genre="科幻",
            description="Testing repository method",
            total_chapters_planned=200,
            target_words=600000,
        )

        project = repo.get_project("repo_test_001")
        assert project is not None
        assert project["name"] == "Repo Test Novel"
        assert project["genre"] == "科幻"
        assert project["total_chapters_planned"] == 200

    def test_add_world_setting_method(self, temp_db):
        """Repository.add_world_setting() creates world setting."""
        repo = Repository(temp_db)
        
        # Create project first
        repo.create_project(project_id="world_test", name="World Test")
        
        # Add world setting
        setting_id = repo.add_world_setting(
            project_id="world_test",
            category="地理",
            title="大陆设定",
            content="三大大陆，五大洋",
        )

        assert setting_id > 0

        settings = repo.get_world_settings("world_test")
        assert len(settings) == 1
        assert settings[0]["category"] == "地理"
        assert settings[0]["title"] == "大陆设定"

    def test_add_character_method(self, temp_db):
        """Repository.add_character() creates character."""
        repo = Repository(temp_db)
        
        # Create project first
        repo.create_project(project_id="char_test", name="Character Test")
        
        # Add character
        char_id = repo.add_character(
            project_id="char_test",
            name="李四",
            role="antagonist",
            description="反派角色",
            alias="暗影",
            first_appearance=5,
        )

        assert char_id > 0

        characters = repo.get_characters("char_test")
        assert len(characters) == 1
        assert characters[0]["name"] == "李四"
        assert characters[0]["role"] == "antagonist"
        assert characters[0]["alias"] == "暗影"


class TestStyleBibleInitialization:
    """Test Style Bible initialization."""

    def test_style_bible_created_with_v40_template(self, client, temp_db):
        """Style Bible is created with v4.0 template."""
        response = client.post(
            "/onboarding/project",
            data={
                "project_id": "style_test",
                "name": "Style Test Novel",
                "genre": "言情",
                "description": "",
                "total_chapters_planned": 500,
                "target_words": 1500000,
                "start_chapter": 1,
                "initial_chapter_count": 10,
                "style_template": "romance_emotional",
                "opening_objective": "",
                "world_setting": "",
                "main_character_name": "",
                "main_character_role": "protagonist",
                "main_character_description": "",
                "create_serial_plan": "",
                "serial_batch_size": 5,
            },
        )
        assert response.status_code == 200

        # Verify Style Bible created with v4.0 romance template
        repo = Repository(temp_db)
        style_bible = repo.get_style_bible("style_test")
        assert style_bible is not None
        assert style_bible["genre"] == "言情"
        # Check that v4.0 template fields are present
        bible = style_bible.get("bible", {})
        assert "tone_keywords" in bible
        assert "pacing" in bible
        assert "ai_trace_avoidance" in bible

    def test_style_bible_uses_project_genre(self, client, temp_db):
        """Style Bible uses project genre instead of template genre."""
        response = client.post(
            "/onboarding/project",
            data={
                "project_id": "genre_override_test",
                "name": "Genre Override Test",
                "genre": "悬疑",
                "description": "",
                "total_chapters_planned": 500,
                "target_words": 1500000,
                "start_chapter": 1,
                "initial_chapter_count": 10,
                "style_template": "mystery_suspense",
                "opening_objective": "",
                "world_setting": "",
                "main_character_name": "",
                "main_character_role": "protagonist",
                "main_character_description": "",
                "create_serial_plan": "",
                "serial_batch_size": 5,
            },
        )
        assert response.status_code == 200

        # Verify Style Bible uses project genre
        repo = Repository(temp_db)
        style_bible = repo.get_style_bible("genre_override_test")
        assert style_bible is not None
        assert style_bible["genre"] == "悬疑"


class TestTransactionalIntegrity:
    """Test transactional integrity - no partial state on failure."""

    def test_failed_style_bible_leaves_no_partial_project(self, client, temp_db):
        """If Style Bible creation fails, no project should be left in DB."""
        bad_template = {
            "name": "Broken Template",
            "genre": "测试",
            "target_platform": {"not": "a string"},
            "target_audience": "测试读者",
        }

        with patch(
            "novel_factory.web.routes.onboarding.load_style_bible_template",
            return_value=bad_template,
        ):
            response = client.post(
                "/onboarding/project",
                data={
                    "project_id": "rollback_style_failure",
                    "name": "Rollback Style Failure",
                    "genre": "",
                    "description": "",
                    "total_chapters_planned": 20,
                    "target_words": 100000,
                    "start_chapter": 1,
                    "initial_chapter_count": 3,
                    "style_template": "default_web_serial",
                    "opening_objective": "Should roll back",
                    "world_setting": "Should not remain",
                    "main_character_name": "ShouldNotRemain",
                    "main_character_role": "protagonist",
                    "main_character_description": "Should not remain",
                    "create_serial_plan": "on",
                    "serial_batch_size": 3,
                },
            )

        assert response.status_code == 500

        repo = Repository(temp_db)
        assert repo.get_project("rollback_style_failure") is None
        assert repo.list_chapters("rollback_style_failure") == []
        assert repo.get_instruction("rollback_style_failure", 1) is None
        assert repo.get_world_settings("rollback_style_failure") == []
        assert repo.get_characters("rollback_style_failure") == []
        assert repo.get_style_bible("rollback_style_failure") is None
        assert repo.list_serial_plans(project_id="rollback_style_failure") == []


class TestSuccessPageActions:
    """Test success page action buttons."""

    def test_success_page_shows_run_chapter_link(self, client, temp_db):
        """Success page shows Run Chapter link."""
        response = client.post(
            "/onboarding/project",
            data={
                "project_id": "success_test",
                "name": "Success Test",
                "genre": "",
                "description": "",
                "total_chapters_planned": 500,
                "target_words": 1500000,
                "start_chapter": 1,
                "initial_chapter_count": 10,
                "style_template": "default_web_serial",
                "opening_objective": "",
                "world_setting": "",
                "main_character_name": "",
                "main_character_role": "protagonist",
                "main_character_description": "",
                "create_serial_plan": "",
                "serial_batch_size": 5,
            },
        )
        assert response.status_code == 200
        # Check for Run Chapter link
        assert b"Run Chapter" in response.content or b"run" in response.content.lower()

    def test_success_page_shows_serial_plan_link_when_created(self, client, temp_db):
        """Success page shows Serial Plan link when serial plan is created."""
        response = client.post(
            "/onboarding/project",
            data={
                "project_id": "serial_success_test",
                "name": "Serial Success Test",
                "genre": "",
                "description": "",
                "total_chapters_planned": 500,
                "target_words": 1500000,
                "start_chapter": 1,
                "initial_chapter_count": 10,
                "style_template": "default_web_serial",
                "opening_objective": "",
                "world_setting": "",
                "main_character_name": "",
                "main_character_role": "protagonist",
                "main_character_description": "",
                "create_serial_plan": "on",
                "serial_batch_size": 5,
            },
        )
        assert response.status_code == 200
        # Check for Serial Plan link
        assert b"Serial Plan" in response.content or b"serial" in response.content.lower()


class TestSerialPlanCreation:
    """Test Serial Plan creation."""

    def test_serial_plan_created_when_checked(self, client, temp_db):
        """Serial Plan is created when checkbox is checked."""
        response = client.post(
            "/onboarding/project",
            data={
                "project_id": "serial_test",
                "name": "Serial Test Novel",
                "genre": "",
                "description": "",
                "total_chapters_planned": 500,
                "target_words": 1500000,
                "start_chapter": 1,
                "initial_chapter_count": 20,
                "style_template": "default_web_serial",
                "opening_objective": "",
                "world_setting": "",
                "main_character_name": "",
                "main_character_role": "protagonist",
                "main_character_description": "",
                "create_serial_plan": "on",
                "serial_batch_size": 5,
            },
        )
        assert response.status_code == 200

        # Verify Serial Plan created
        repo = Repository(temp_db)
        serial_plans = repo.list_serial_plans(project_id="serial_test")
        assert len(serial_plans) == 1
        assert serial_plans[0]["start_chapter"] == 1
        assert serial_plans[0]["target_chapter"] == 20
        assert serial_plans[0]["batch_size"] == 5

    def test_no_serial_plan_when_unchecked(self, client, temp_db):
        """Serial Plan is not created when checkbox is unchecked."""
        response = client.post(
            "/onboarding/project",
            data={
                "project_id": "no_serial_test",
                "name": "No Serial Test Novel",
                "genre": "",
                "description": "",
                "total_chapters_planned": 500,
                "target_words": 1500000,
                "start_chapter": 1,
                "initial_chapter_count": 10,
                "style_template": "default_web_serial",
                "opening_objective": "",
                "world_setting": "",
                "main_character_name": "",
                "main_character_role": "protagonist",
                "main_character_description": "",
                "create_serial_plan": "",
                "serial_batch_size": 5,
            },
        )
        assert response.status_code == 200

        # Verify no Serial Plan created
        repo = Repository(temp_db)
        serial_plans = repo.list_serial_plans(project_id="no_serial_test")
        assert len(serial_plans) == 0

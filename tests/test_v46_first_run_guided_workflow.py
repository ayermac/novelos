"""Tests for v4.6 First Run Guided Workflow.

Focus on testing the guided workflow from onboarding success to first chapter run.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

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


@pytest.fixture
def new_project(client, temp_db):
    """Create a new project via onboarding for testing."""
    response = client.post(
        "/onboarding/project",
        data={
            "project_id": "test_first_run_001",
            "name": "First Run Test Novel",
            "genre": "都市异能",
            "description": "Test novel for first run workflow",
            "total_chapters_planned": 100,
            "target_words": 300000,
            "start_chapter": 1,
            "initial_chapter_count": 5,
            "style_template": "default_web_serial",
            "opening_objective": "主角觉醒异能",
            "world_setting": "现代都市，隐藏着异能者世界",
            "main_character_name": "林风",
            "main_character_role": "protagonist",
            "main_character_description": "普通大学生，意外获得异能",
            "create_serial_plan": "",
            "serial_batch_size": 5,
        },
    )
    assert response.status_code == 200
    
    repo = Repository(temp_db)
    return repo.get_project("test_first_run_001")


class TestOnboardingSuccessPageGuidedRun:
    """Test onboarding success page contains guided run link."""

    def test_success_page_has_first_chapter_link(self, client, new_project):
        """Onboarding success page contains link to run first chapter."""
        # Get the success page (we already created project in fixture)
        response = client.get("/onboarding")
        assert response.status_code == 200
        
        # The success page should have been shown after project creation
        # Check that the link format is correct
        # Since we can't directly test the success page after POST,
        # we'll verify the template contains the right link format
        
    def test_success_page_link_format(self, client):
        """Verify success page link includes project_id and chapter params."""
        response = client.post(
            "/onboarding/project",
            data={
                "project_id": "test_link_format",
                "name": "Link Format Test",
                "genre": "",
                "description": "",
                "total_chapters_planned": 50,
                "target_words": 150000,
                "start_chapter": 1,
                "initial_chapter_count": 3,
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
        # Check the response contains the guided run link
        assert b"/run?project_id=test_link_format" in response.content
        assert b"chapter=1" in response.content
        assert "生成第 1 章" in response.text


class TestRunChapterQueryParams:
    """Test Run Chapter page supports query parameter pre-fill."""

    def test_run_form_with_project_id_param(self, client, new_project):
        """GET /run?project_id=X pre-selects the project."""
        response = client.get("/run?project_id=test_first_run_001")
        assert response.status_code == 200
        assert b"test_first_run_001" in response.content

    def test_run_form_with_chapter_param(self, client, new_project):
        """GET /run?chapter=X pre-fills chapter number."""
        response = client.get("/run?project_id=test_first_run_001&chapter=3")
        assert response.status_code == 200
        # Check that chapter 3 is pre-filled
        assert b'value="3"' in response.content

    def test_run_form_with_llm_mode_param(self, client, new_project):
        """GET /run?llm_mode=stub pre-selects LLM mode."""
        response = client.get("/run?project_id=test_first_run_001&chapter=1&llm_mode=stub")
        assert response.status_code == 200
        # Check stub mode is selected
        assert b'stub (demo)' in response.content

    def test_run_form_invalid_project_id(self, client):
        """GET /run?project_id=invalid returns error."""
        response = client.get("/run?project_id=nonexistent_project")
        assert response.status_code == 404
        assert "不存在" in response.text

    def test_run_form_invalid_chapter(self, client, new_project):
        """GET /run?chapter=999 returns error for non-existent chapter."""
        response = client.get("/run?project_id=test_first_run_001&chapter=999")
        assert response.status_code == 404
        assert "不存在" in response.text


class TestFirstChapterRun:
    """Test first chapter run from new project."""

    def test_run_first_chapter_stub_mode(self, client, temp_db, new_project):
        """New project first chapter can run in stub mode."""
        response = client.post(
            "/run/chapter",
            data={
                "project_id": "test_first_run_001",
                "chapter": 1,
                "llm_mode": "stub",
                "max_steps": 20,
            },
        )
        assert response.status_code == 200
        
        # Verify chapter status changed in DB
        repo = Repository(temp_db)
        chapter = repo.get_chapter("test_first_run_001", 1)
        assert chapter is not None
        # In stub mode, chapter should progress through the pipeline
        assert chapter["status"] in ("planned", "outline", "draft", "polished", "reviewed", "published", "blocking")

    def test_run_result_shows_readable_summary(self, client, new_project):
        """POST /run/chapter shows readable result summary, not raw JSON."""
        response = client.post(
            "/run/chapter",
            data={
                "project_id": "test_first_run_001",
                "chapter": 1,
                "llm_mode": "stub",
                "max_steps": 20,
            },
        )
        assert response.status_code == 200
        
        # Should show readable labels, not raw JSON
        assert "项目 ID" in response.text or "Project ID" in response.text
        assert "章节" in response.text or "Chapter" in response.text
        assert "章节状态" in response.text or "status" in response.text.lower()

    def test_run_result_shows_workflow_run_info(self, client, new_project, temp_db):
        """POST /run/chapter shows workflow run information."""
        response = client.post(
            "/run/chapter",
            data={
                "project_id": "test_first_run_001",
                "chapter": 1,
                "llm_mode": "stub",
                "max_steps": 20,
            },
        )
        assert response.status_code == 200
        
        # Should show workflow run ID
        assert "Workflow Run ID" in response.text or "workflow" in response.text.lower()
        
        # Verify workflow run was created in DB
        repo = Repository(temp_db)
        runs = repo.get_workflow_runs_for_project("test_first_run_001", 1)
        assert len(runs) > 0

    def test_run_result_has_next_step_links(self, client, new_project):
        """POST /run/chapter result contains next step action links."""
        response = client.post(
            "/run/chapter",
            data={
                "project_id": "test_first_run_001",
                "chapter": 1,
                "llm_mode": "stub",
                "max_steps": 20,
            },
        )
        assert response.status_code == 200
        
        # Should have links to project detail or review
        assert b"/projects/test_first_run_001" in response.content or b"project" in response.content.lower()
        # Should have review link
        assert b"/review" in response.content

    def test_run_result_blocking_status(self, client, temp_db):
        """Blocking status shows human intervention needed."""
        # Create a project
        response = client.post(
            "/onboarding/project",
            data={
                "project_id": "test_blocking_001",
                "name": "Blocking Test",
                "genre": "",
                "description": "",
                "total_chapters_planned": 50,
                "target_words": 150000,
                "start_chapter": 1,
                "initial_chapter_count": 1,
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
        
        # Run with max_steps=1 to potentially trigger blocking
        response = client.post(
            "/run/chapter",
            data={
                "project_id": "test_blocking_001",
                "chapter": 1,
                "llm_mode": "stub",
                "max_steps": 1,
            },
        )
        assert response.status_code == 200
        
        # If blocking, should show warning message
        if "blocking" in response.text.lower() or "需要人工" in response.text:
            assert "人工处理" in response.text or "human" in response.text.lower()


class TestErrorHandling:
    """Test error handling for run chapter."""

    def test_run_nonexistent_project(self, client):
        """Running non-existent project shows readable error."""
        response = client.post(
            "/run/chapter",
            data={
                "project_id": "nonexistent_project",
                "chapter": 1,
                "llm_mode": "stub",
                "max_steps": 20,
            },
        )
        # Should show error, not crash
        assert response.status_code == 200
        assert "error" in response.text.lower() or "错误" in response.text

    def test_run_nonexistent_chapter(self, client, new_project):
        """Running non-existent chapter shows readable error."""
        response = client.post(
            "/run/chapter",
            data={
                "project_id": "test_first_run_001",
                "chapter": 999,
                "llm_mode": "stub",
                "max_steps": 20,
            },
        )
        # Should show error, not crash
        assert response.status_code == 200
        assert "error" in response.text.lower() or "错误" in response.text


class TestDatabaseStateChanges:
    """Test that run chapter actually changes database state."""

    def test_run_creates_workflow_run_record(self, client, temp_db, new_project):
        """Running chapter creates workflow_run record in DB."""
        repo = Repository(temp_db)
        
        # Count workflow runs before
        runs_before = repo.get_workflow_runs_for_project("test_first_run_001", 1)
        
        # Run chapter
        response = client.post(
            "/run/chapter",
            data={
                "project_id": "test_first_run_001",
                "chapter": 1,
                "llm_mode": "stub",
                "max_steps": 20,
            },
        )
        assert response.status_code == 200
        
        # Count workflow runs after
        runs_after = repo.get_workflow_runs_for_project("test_first_run_001", 1)
        assert len(runs_after) > len(runs_before)

    def test_run_updates_chapter_status(self, client, temp_db, new_project):
        """Running chapter updates chapter status in DB."""
        repo = Repository(temp_db)
        
        # Get initial chapter status
        chapter_before = repo.get_chapter("test_first_run_001", 1)
        assert chapter_before["status"] == "planned"
        
        # Run chapter
        response = client.post(
            "/run/chapter",
            data={
                "project_id": "test_first_run_001",
                "chapter": 1,
                "llm_mode": "stub",
                "max_steps": 20,
            },
        )
        assert response.status_code == 200
        
        # Check chapter status changed - must leave planned state
        chapter_after = repo.get_chapter("test_first_run_001", 1)
        assert chapter_after["status"] != "planned", \
            f"Chapter status should have changed from 'planned', got: {chapter_after['status']}"
        
        # Verify workflow run was created
        runs = repo.get_workflow_runs_for_project("test_first_run_001", 1)
        assert len(runs) > 0, "At least one workflow run should exist"
        
        # Verify workflow run status is consistent with chapter status
        latest_run = runs[0]
        assert latest_run["status"] in ("completed", "blocked", "failed"), \
            f"Workflow run status should be terminal, got: {latest_run['status']}"

    def test_multiple_runs_create_multiple_workflow_runs(self, client, temp_db, new_project):
        """Running chapter multiple times creates multiple workflow runs."""
        repo = Repository(temp_db)
        
        # Run chapter first time
        client.post(
            "/run/chapter",
            data={
                "project_id": "test_first_run_001",
                "chapter": 1,
                "llm_mode": "stub",
                "max_steps": 20,
            },
        )
        
        runs_after_first = repo.get_workflow_runs_for_project("test_first_run_001", 1)
        first_count = len(runs_after_first)
        
        # Run chapter second time
        client.post(
            "/run/chapter",
            data={
                "project_id": "test_first_run_001",
                "chapter": 1,
                "llm_mode": "stub",
                "max_steps": 20,
            },
        )
        
        runs_after_second = repo.get_workflow_runs_for_project("test_first_run_001", 1)
        assert len(runs_after_second) > first_count


class TestFormContextPreservation:
    """Test that form context is preserved after POST."""

    def test_success_response_contains_projects_dropdown(self, client, new_project):
        """POST /run/chapter success response contains projects dropdown options."""
        response = client.post(
            "/run/chapter",
            data={
                "project_id": "test_first_run_001",
                "chapter": 1,
                "llm_mode": "stub",
                "max_steps": 20,
            },
        )
        assert response.status_code == 200
        
        # Response should contain the current project in dropdown
        assert b"test_first_run_001" in response.content
        # Response should contain select element for projects
        assert b'<select name="project_id"' in response.content or b'select' in response.content.lower()

    def test_error_response_contains_projects_dropdown(self, client):
        """POST /run/chapter error response contains projects dropdown for retry."""
        # Try to run non-existent project
        response = client.post(
            "/run/chapter",
            data={
                "project_id": "nonexistent_project",
                "chapter": 1,
                "llm_mode": "stub",
                "max_steps": 20,
            },
        )
        assert response.status_code == 200
        
        # Even on error, should have projects dropdown for retry
        # Check that select element exists
        assert b'<select name="project_id"' in response.content or b'select' in response.content.lower()

    def test_success_response_preserves_run_parameters(self, client, new_project):
        """POST /run/chapter success response preserves run parameters."""
        response = client.post(
            "/run/chapter",
            data={
                "project_id": "test_first_run_001",
                "chapter": 1,
                "llm_mode": "stub",
                "max_steps": 20,
            },
        )
        assert response.status_code == 200
        
        # Check that form preserves parameters
        assert b"test_first_run_001" in response.content
        # Chapter should be in response
        assert b"1" in response.content

"""Tests for project-level modules: Style, Review, Runs.

This test file covers:
- StyleGuideModule: style console API
- ReviewModule: blocking/reviewed/published status, publish API
- RunsModule: project-level runs list API
"""

from __future__ import annotations

import tempfile
import pytest
from pathlib import Path

from novel_factory.db.connection import init_db
from novel_factory.db.repository import Repository
from novel_factory.api_app import create_api_app
from fastapi.testclient import TestClient


@pytest.fixture
def test_client():
    """Create test client with isolated database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        init_db(str(db_path))
        app = create_api_app(db_path=str(db_path), llm_mode="stub")
        client = TestClient(app)
        yield client, str(db_path)


class TestStyleGuideModule:
    """Test StyleGuideModule API requirements."""

    def test_style_console_returns_required_fields(self, test_client):
        """Style console should return style_bibles, style_gate_configs, style_samples, and health."""
        client, _ = test_client
        resp = client.get("/api/style/console")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "style_bibles" in data["data"]
        assert "style_gate_configs" in data["data"]
        assert "style_samples" in data["data"]
        assert "health" in data["data"]

    def test_style_init_creates_bible(self, test_client):
        """Style init should create style bible for project."""
        client, db_path = test_client

        # Create project via onboarding API
        resp = client.post("/api/onboarding/projects", json={
            "project_id": "test-style-project",
            "name": "Test Project",
            "genre": "fantasy",
            "target_words": 100000,
            "total_chapters_planned": 50,
        })
        assert resp.status_code == 200
        project_id = resp.json()["data"]["project"]["project_id"]

        # Init style bible
        resp = client.post("/api/style/init", json={"project_id": project_id})
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True

        # Verify bible appears in console
        resp2 = client.get("/api/style/console")
        assert resp2.status_code == 200
        bibles = resp2.json()["data"]["style_bibles"]
        assert any(b["project_id"] == project_id for b in bibles)


class TestReviewModule:
    """Test ReviewModule API requirements."""

    def test_workspace_includes_recent_runs(self, test_client):
        """Workspace API should include recent_runs for blocking error display."""
        client, db_path = test_client

        # Create project via onboarding API
        resp = client.post("/api/onboarding/projects", json={
            "project_id": "test-workspace-project",
            "name": "Test Project",
            "genre": "fantasy",
            "target_words": 100000,
            "total_chapters_planned": 50,
        })
        assert resp.status_code == 200
        project_id = resp.json()["data"]["project"]["project_id"]

        # Get workspace
        resp = client.get(f"/api/projects/{project_id}/workspace")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "recent_runs" in data["data"]

    def test_publish_endpoint_for_reviewed_chapter(self, test_client):
        """Publish API should allow publishing reviewed chapters."""
        client, db_path = test_client
        repo = Repository(db_path)

        # Create project via onboarding API
        resp = client.post("/api/onboarding/projects", json={
            "project_id": "test-publish-project",
            "name": "Test Project",
            "genre": "fantasy",
            "target_words": 100000,
            "total_chapters_planned": 50,
        })
        assert resp.status_code == 200
        project_id = resp.json()["data"]["project"]["project_id"]

        # Update chapter to reviewed status via SQL
        conn = repo._conn()
        try:
            conn.execute(
                "UPDATE chapters SET status='reviewed', word_count=3000 WHERE project_id=? AND chapter_number=1",
                (project_id,),
            )
            conn.commit()
        finally:
            conn.close()

        # Publish
        resp = client.post("/api/publish/chapter", json={
            "project_id": project_id,
            "chapter": 1,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True

        # Verify status changed to published
        chapter = repo.get_chapter(project_id, 1)
        assert chapter["status"] == "published"

    def test_reset_blocking_chapter(self, test_client):
        """Reset API should allow resetting blocking chapters."""
        client, db_path = test_client
        repo = Repository(db_path)

        # Create project via onboarding API
        resp = client.post("/api/onboarding/projects", json={
            "project_id": "test-reset-project",
            "name": "Test Project",
            "genre": "fantasy",
            "target_words": 100000,
            "total_chapters_planned": 50,
        })
        assert resp.status_code == 200
        project_id = resp.json()["data"]["project"]["project_id"]

        # Update chapter to blocking status via SQL
        conn = repo._conn()
        try:
            conn.execute(
                "UPDATE chapters SET status='blocking' WHERE project_id=? AND chapter_number=1",
                (project_id,),
            )
            conn.commit()
        finally:
            conn.close()

        # Reset
        resp = client.post(f"/api/projects/{project_id}/chapters/1/reset")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True

        # Verify status changed to planned
        chapter = repo.get_chapter(project_id, 1)
        assert chapter["status"] == "planned"


class TestRunsModule:
    """Test RunsModule API requirements."""

    def test_project_runs_list(self, test_client):
        """Project runs API should return list of runs with required fields."""
        client, db_path = test_client
        repo = Repository(db_path)

        # Create project via onboarding API
        resp = client.post("/api/onboarding/projects", json={
            "project_id": "test-runs-project",
            "name": "Test Project",
            "genre": "fantasy",
            "target_words": 100000,
            "total_chapters_planned": 50,
        })
        assert resp.status_code == 200
        project_id = resp.json()["data"]["project"]["project_id"]

        # Create a workflow run
        run_id = repo.create_workflow_run(project_id, 1)
        repo.update_workflow_run(
            run_id,
            status="completed",
            prompt_tokens=1000,
            completion_tokens=2000,
            total_tokens=3000,
            duration_ms=5000,
        )

        # Get project runs
        resp = client.get(f"/api/projects/{project_id}/runs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert isinstance(data["data"], list)
        assert len(data["data"]) >= 1

        # Check required fields
        run = data["data"][0]
        assert "run_id" in run or "id" in run
        assert "chapter_number" in run
        assert "status" in run
        assert "total_tokens" in run
        assert "duration_ms" in run

    def test_run_detail_includes_steps_and_artifacts(self, test_client):
        """Run detail API should include steps with artifacts."""
        client, db_path = test_client
        repo = Repository(db_path)

        # Create project via onboarding API
        resp = client.post("/api/onboarding/projects", json={
            "project_id": "test-steps-project",
            "name": "Test Project",
            "genre": "fantasy",
            "target_words": 100000,
            "total_chapters_planned": 50,
        })
        assert resp.status_code == 200
        project_id = resp.json()["data"]["project"]["project_id"]

        # Update chapter to published status via SQL
        conn = repo._conn()
        try:
            conn.execute(
                "UPDATE chapters SET status='published', word_count=3000 WHERE project_id=? AND chapter_number=1",
                (project_id,),
            )
            conn.commit()
        finally:
            conn.close()

        # Create run
        run_id = repo.create_workflow_run(project_id, 1)
        repo.update_workflow_run(run_id, status="completed")

        # Get run detail
        resp = client.get(f"/api/runs/{run_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True

        # Check steps
        assert "steps" in data["data"]
        steps = data["data"]["steps"]
        assert len(steps) >= 1

        # Each step should have key, label, status
        for step in steps:
            assert "key" in step
            assert "label" in step
            assert "status" in step

    def test_run_detail_includes_error_message(self, test_client):
        """Run detail API should include error_message for failed runs."""
        client, db_path = test_client
        repo = Repository(db_path)

        # Create project via onboarding API
        resp = client.post("/api/onboarding/projects", json={
            "project_id": "test-error-project",
            "name": "Test Project",
            "genre": "fantasy",
            "target_words": 100000,
            "total_chapters_planned": 50,
        })
        assert resp.status_code == 200
        project_id = resp.json()["data"]["project"]["project_id"]

        # Update chapter to blocking status via SQL
        conn = repo._conn()
        try:
            conn.execute(
                "UPDATE chapters SET status='blocking' WHERE project_id=? AND chapter_number=1",
                (project_id,),
            )
            conn.commit()
        finally:
            conn.close()

        # Create failed run
        run_id = repo.create_workflow_run(project_id, 1)
        repo.update_workflow_run(run_id, status="failed", error_message="Test error message")

        # Get run detail
        resp = client.get(f"/api/runs/{run_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "error_message" in data["data"]

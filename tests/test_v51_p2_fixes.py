"""v5.1 P2 fixes verification tests.

Tests for:
- Dashboard API works with projects
- Style API works with projects
- API command available in CLI
- Frontend build succeeds
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="function")
def client():
    """Create test client with initialized database."""
    from novel_factory.api_app import create_api_app
    from novel_factory.db.connection import init_db

    # Create temporary database file
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    # Initialize database
    init_db(db_path)

    # Create app with the same database
    app = create_api_app(db_path=db_path, llm_mode="stub")

    test_client = TestClient(app)

    yield test_client

    # Cleanup
    if os.path.exists(db_path):
        os.unlink(db_path)


class TestDashboardWithProjects:
    """Dashboard API works correctly when projects exist."""

    def test_dashboard_after_project_creation(self, client):
        """Dashboard returns data after creating a project."""
        # Create a project first
        response = client.post(
            "/api/onboarding/projects",
            json={
                "project_id": "test_dashboard",
                "name": "测试项目",
                "initial_chapter_count": 3,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True

        # Now get dashboard
        response = client.get("/api/dashboard")
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["data"]["project_count"] == 1
        assert len(data["data"]["recent_runs"]) == 0  # No runs yet

    def test_dashboard_after_run_chapter(self, client):
        """Dashboard shows recent runs after running a chapter."""
        # Create project
        client.post(
            "/api/onboarding/projects",
            json={
                "project_id": "test_dashboard_run",
                "name": "测试项目",
                "initial_chapter_count": 1,
            },
        )

        # Run chapter
        response = client.post(
            "/api/run/chapter",
            json={
                "project_id": "test_dashboard_run",
                "chapter": 1,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True

        # Get dashboard
        response = client.get("/api/dashboard")
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["data"]["project_count"] == 1
        # Should have at least one run now
        assert len(data["data"]["recent_runs"]) >= 1


class TestStyleWithProjects:
    """Style API works correctly when projects exist."""

    def test_style_console_with_projects(self, client):
        """Style console returns data with projects."""
        # Create a project
        client.post(
            "/api/onboarding/projects",
            json={
                "project_id": "test_style",
                "name": "风格测试",
                "initial_chapter_count": 1,
            },
        )

        # Get style console
        response = client.get("/api/style/console")
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "style_bibles" in data["data"]
        assert "style_gate_configs" in data["data"]
        assert "style_samples" in data["data"]
        assert "health" in data["data"]


class TestAPICommand:
    """API command is available in CLI."""

    def test_api_command_exists(self):
        """API command is registered in CLI."""
        result = subprocess.run(
            [sys.executable, "-m", "novel_factory.cli", "api", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "api" in result.stdout
        assert "--host" in result.stdout
        assert "--port" in result.stdout
        assert "--llm-mode" in result.stdout


class TestFrontendBuild:
    """Frontend build succeeds."""

    def test_frontend_build_succeeds(self):
        """Frontend npm run build succeeds."""
        frontend_dir = Path(__file__).parent.parent / "frontend"
        if not frontend_dir.exists():
            pytest.skip("Frontend directory not found")

        # Run build
        result = subprocess.run(
            ["npm", "run", "build"],
            cwd=str(frontend_dir),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Build failed: {result.stderr}"

        # Check dist directory exists
        dist_dir = frontend_dir / "dist"
        assert dist_dir.exists(), "dist directory not created"

        # Check index.html exists
        index_html = dist_dir / "index.html"
        assert index_html.exists(), "index.html not created"

    def test_frontend_typecheck_succeeds(self):
        """Frontend TypeScript type checking succeeds."""
        frontend_dir = Path(__file__).parent.parent / "frontend"
        if not frontend_dir.exists():
            pytest.skip("Frontend directory not found")

        # Run typecheck
        result = subprocess.run(
            ["npm", "run", "typecheck"],
            cwd=str(frontend_dir),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Typecheck failed: {result.stderr}"


class TestAcceptanceMatrix:
    """Acceptance matrix is properly populated."""

    def test_acceptance_matrix_has_capabilities(self, client):
        """Acceptance matrix returns capabilities."""
        response = client.get("/api/acceptance")
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "capabilities" in data["data"]
        assert len(data["data"]["capabilities"]) > 0

        # Check that v5.1 capabilities are present
        capability_ids = [c["capability_id"] for c in data["data"]["capabilities"]]
        assert "v51_api_backend" in capability_ids
        assert "v51_frontend" in capability_ids

    def test_acceptance_matrix_summary(self, client):
        """Acceptance matrix summary is accurate."""
        response = client.get("/api/acceptance")
        data = response.json()
        summary = data["data"]["summary"]

        assert summary["total"] > 0
        assert summary["passed"] >= 2  # At least v5.1 capabilities
        assert summary["failed"] >= 0

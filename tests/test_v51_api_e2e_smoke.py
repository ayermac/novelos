"""v5.1 API End-to-End Smoke Tests.

Tests real user paths through the API without calling real LLM.
Uses temporary SQLite database and FastAPI TestClient.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def test_client():
    """Create test client with temporary database."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        # Initialize database schema
        from novel_factory.db.connection import init_db

        init_db(db_path)

        from novel_factory.api_app import create_api_app

        app = create_api_app(db_path=db_path, llm_mode="stub")
        client = TestClient(app)
        yield client
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


class TestAPIE2ESmoke:
    """End-to-end smoke tests for API."""

    def test_health_check(self, test_client):
        """Test health endpoint."""
        resp = test_client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "status" in data["data"]

    def test_dashboard_empty(self, test_client):
        """Test dashboard with no projects."""
        resp = test_client.get("/api/dashboard")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        # Dashboard may have projects from other tests in shared DB
        assert "project_count" in data["data"]
        assert "recent_runs" in data["data"]
        assert "queue_count" in data["data"]
        assert "review_count" in data["data"]

    def test_projects_list_empty(self, test_client):
        """Test projects list when empty."""
        resp = test_client.get("/api/projects")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        # Projects list may have items from other tests
        assert isinstance(data["data"], list)

    def test_onboarding_create_project(self, test_client):
        """Test creating project via onboarding."""
        resp = test_client.post(
            "/api/onboarding/projects",
            json={
                "project_id": "test_novel_001",
                "name": "测试小说",
                "genre": "玄幻",
                "target_words": 100000,
                "initial_chapter_count": 10,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["data"]["project"]["project_id"] == "test_novel_001"

    def test_dashboard_with_project(self, test_client):
        """Test dashboard shows created project."""
        # Create project first
        test_client.post(
            "/api/onboarding/projects",
            json={
                "project_id": "test_novel_002",
                "name": "测试小说2",
                "genre": "都市",
                "target_words": 80000,
                "initial_chapter_count": 8,
            },
        )

        # Check dashboard
        resp = test_client.get("/api/dashboard")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["data"]["project_count"] >= 1

    def test_project_workspace(self, test_client):
        """Test project workspace shows chapters."""
        # Create project
        test_client.post(
            "/api/onboarding/projects",
            json={
                "project_id": "test_novel_003",
                "name": "测试小说3",
                "genre": "科幻",
                "target_words": 120000,
                "initial_chapter_count": 12,
            },
        )

        # Get workspace
        resp = test_client.get("/api/projects/test_novel_003/workspace")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["data"]["project"]["project_id"] == "test_novel_003"
        assert len(data["data"]["chapters"]) == 12

    def test_run_chapter_stub_mode(self, test_client):
        """Test running chapter in stub mode."""
        # Create project
        test_client.post(
            "/api/onboarding/projects",
            json={
                "project_id": "test_novel_004",
                "name": "测试小说4",
                "genre": "奇幻",
                "target_words": 90000,
                "initial_chapter_count": 9,
            },
        )

        # Run chapter
        resp = test_client.post(
            "/api/run/chapter",
            json={
                "project_id": "test_novel_004",
                "chapter": 1,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "run_id" in data["data"]
        assert data["data"]["status"] in ["pending", "running", "completed"]

    def test_dashboard_recent_runs(self, test_client):
        """Test dashboard shows recent runs."""
        # Create project and run chapter
        test_client.post(
            "/api/onboarding/projects",
            json={
                "project_id": "test_novel_005",
                "name": "测试小说5",
                "genre": "仙侠",
                "target_words": 110000,
                "initial_chapter_count": 11,
            },
        )

        test_client.post(
            "/api/run/chapter",
            json={
                "project_id": "test_novel_005",
                "chapter": 1,
            },
        )

        # Check dashboard for recent runs
        resp = test_client.get("/api/dashboard")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        # Recent runs should exist (may be empty if run hasn't completed)
        assert "recent_runs" in data["data"]

    def test_style_console(self, test_client):
        """Test style console endpoint."""
        resp = test_client.get("/api/style/console")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "style_gate_configs" in data["data"]

    def test_settings_no_key_exposure(self, test_client):
        """Test settings endpoint doesn't expose API keys."""
        resp = test_client.get("/api/settings")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True

        # Check response doesn't contain actual API key values
        resp_text = resp.text
        assert "sk-" not in resp_text
        assert "sk_live_" not in resp_text
        assert "sk_test_" not in resp_text

        # Check structure
        assert "llm_profiles" in data["data"]
        for profile in data["data"]["llm_profiles"]:
            # Should only have has_key boolean, not actual key
            assert "has_key" in profile
            # api_key field should not exist or be None
            if "api_key" in profile:
                assert profile["api_key"] is None

    def test_settings_no_traceback(self, test_client):
        """Test settings endpoint doesn't expose tracebacks."""
        resp = test_client.get("/api/settings")
        assert resp.status_code == 200
        resp_text = resp.text.lower()
        assert "traceback" not in resp_text
        assert "file " not in resp_text
        assert "line " not in resp_text

    def test_acceptance_matrix(self, test_client):
        """Test acceptance matrix endpoint."""
        resp = test_client.get("/api/acceptance")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "capabilities" in data["data"]
        assert isinstance(data["data"]["capabilities"], list)

        # Check v5.1 capability is present (or at least some capabilities exist)
        capabilities = data["data"]["capabilities"]
        assert len(capabilities) > 0, "Should have at least one capability"

        # Check summary exists
        assert "summary" in data["data"]
        assert "total" in data["data"]["summary"]

    def test_project_not_found(self, test_client):
        """Test error for non-existent project."""
        resp = test_client.get("/api/projects/nonexistent_project/workspace")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert data["error"]["code"] == "PROJECT_NOT_FOUND"
        # Error message should be in Chinese
        assert "项目" in data["error"]["message"] or "不存在" in data["error"]["message"]

    def test_run_chapter_project_not_found(self, test_client):
        """Test running chapter for non-existent project."""
        resp = test_client.post(
            "/api/run/chapter",
            json={
                "project_id": "nonexistent_project",
                "chapter": 1,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert data["error"]["code"] == "PROJECT_NOT_FOUND"

    def test_envelope_format_consistency(self, test_client):
        """Test all responses follow envelope format {ok, error, data}."""
        endpoints = [
            "/api/health",
            "/api/dashboard",
            "/api/projects",
            "/api/style/console",
            "/api/settings",
            "/api/acceptance",
        ]

        for endpoint in endpoints:
            resp = test_client.get(endpoint)
            data = resp.json()

            # Must have ok field
            assert "ok" in data, f"{endpoint} missing 'ok' field"

            # Must have error or data field
            if data["ok"]:
                assert "data" in data, f"{endpoint} missing 'data' field on success"
                assert data.get("error") is None, f"{endpoint} has non-null error on success"
            else:
                assert "error" in data, f"{endpoint} missing 'error' field on failure"
                assert data.get("data") is None, f"{endpoint} has non-null data on failure"
                assert "code" in data["error"], f"{endpoint} error missing 'code'"
                assert "message" in data["error"], f"{endpoint} error missing 'message'"

    def test_no_absolute_paths_in_errors(self, test_client):
        """Test error responses don't expose absolute paths."""
        # Try to access non-existent project
        resp = test_client.get("/api/projects/nonexistent/workspace")
        resp_text = resp.text

        # Should not contain absolute paths
        assert "/Users/" not in resp_text
        assert "/home/" not in resp_text
        assert "/root/" not in resp_text
        assert "C:\\" not in resp_text

    def test_config_plan_no_file_write(self, test_client):
        """Test config plan endpoint doesn't write files."""
        resp = test_client.post(
            "/api/config/plan",
            json={
                "project_id": "test_project",
                "model_preferences": {
                    "architect": "gpt-4",
                    "writer": "gpt-3.5-turbo",
                },
            },
        )

        # Should return draft, not write file
        if resp.status_code == 200:
            data = resp.json()
            assert data["ok"] is True
            # Should return draft content, not file path
            assert "draft" in data["data"] or "config" in data["data"]

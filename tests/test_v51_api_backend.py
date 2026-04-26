"""Tests for v5.1 API Backend.

Covers:
- API envelope format
- Error handling without traceback
- API safety (no secrets)
- Project not found
- Run chapter stub mode
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from novel_factory.db.connection import init_db
from novel_factory.api_app import create_api_app


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".db", delete=False) as f:
        db_path = f.name
    init_db(db_path)
    yield db_path
    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def client(temp_db):
    """Create a test client with stub mode."""
    app = create_api_app(db_path=temp_db, config_path=None, llm_mode="stub")
    return TestClient(app)


# ── Section 1: API Envelope Format ───────────────────────────────

class TestAPIEnvelope:
    """All API responses follow {ok, error, data} envelope."""

    def test_health_envelope_format(self, client):
        """Health endpoint returns proper envelope."""
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert "ok" in data
        assert data["ok"] is True
        assert "error" in data
        assert data["error"] is None
        assert "data" in data
        assert data["data"]["status"] == "ok"

    def test_dashboard_envelope_format(self, client):
        """Dashboard endpoint returns proper envelope."""
        response = client.get("/api/dashboard")
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "data" in data
        assert "project_count" in data["data"]

    def test_projects_envelope_format(self, client):
        """Projects endpoint returns proper envelope."""
        response = client.get("/api/projects")
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "data" in data
        assert isinstance(data["data"], list)


# ── Section 2: Error Handling ────────────────────────────────────

class TestErrorHandling:
    """API errors are safe and structured."""

    def test_project_not_found_returns_error_envelope(self, client):
        """Non-existent project returns error envelope."""
        response = client.get("/api/projects/nonexistent_project")
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is False
        assert data["error"] is not None
        assert data["error"]["code"] == "PROJECT_NOT_FOUND"
        assert "不存在" in data["error"]["message"]

    def test_error_no_traceback(self, client):
        """Error responses never include traceback."""
        response = client.get("/api/projects/nonexistent")
        content = response.text
        assert "Traceback" not in content
        assert "File " not in content
        assert "line " not in content


# ── Section 3: API Safety ─────────────────────────────────────────

class TestAPISafety:
    """API never exposes secrets or sensitive data."""

    def test_settings_no_api_key_values(self, client):
        """Settings endpoint never returns API key values."""
        response = client.get("/api/settings")
        assert response.status_code == 200
        content = response.text
        assert "sk-" not in content
        assert "api_key" not in content.lower() or "has_key" in content.lower()

    def test_health_no_secrets(self, client):
        """Health endpoint has no secrets."""
        response = client.get("/api/health")
        data = response.json()
        assert "db_path" not in str(data)
        assert "config_path" not in str(data)

    def test_stub_mode_is_safe(self, client):
        """Stub mode is indicated in responses."""
        response = client.get("/api/health")
        data = response.json()
        assert data["data"]["llm_mode"] == "stub"


# ── Section 4: Run Chapter Stub Mode ─────────────────────────────

class TestRunChapterStubMode:
    """Run chapter works in stub mode without real LLM."""

    def test_run_chapter_creates_project(self, client):
        """Create project via onboarding API."""
        response = client.post(
            "/api/onboarding/projects",
            json={
                "project_id": "test_run_chapter",
                "name": "测试项目",
                "initial_chapter_count": 1,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["data"]["project"]["project_id"] == "test_run_chapter"

    def test_run_chapter_stub_mode(self, client):
        """Run chapter in stub mode returns mock result."""
        # Create project first
        client.post(
            "/api/onboarding/projects",
            json={
                "project_id": "test_run_stub",
                "name": "测试项目",
                "initial_chapter_count": 1,
            },
        )

        # Run chapter
        response = client.post(
            "/api/run/chapter",
            json={
                "project_id": "test_run_stub",
                "chapter": 1,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "run_id" in data["data"]
        assert data["data"]["llm_mode"] == "stub"


# ── Section 5: CRUD Operations ───────────────────────────────────

class TestCRUDOperations:
    """Basic CRUD operations work correctly."""

    def test_create_project(self, client):
        """Create project via API."""
        response = client.post(
            "/api/onboarding/projects",
            json={
                "project_id": "test_crud",
                "name": "CRUD 测试项目",
                "genre": "玄幻",
                "initial_chapter_count": 5,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["data"]["project"]["name"] == "CRUD 测试项目"
        assert len(data["data"]["chapters"]) == 5

    def test_list_projects(self, client):
        """List projects via API."""
        # Create a project first
        client.post(
            "/api/onboarding/projects",
            json={
                "project_id": "test_list",
                "name": "列表测试",
                "initial_chapter_count": 1,
            },
        )

        # List projects
        response = client.get("/api/projects")
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert any(p["project_id"] == "test_list" for p in data["data"])

    def test_get_project_workspace(self, client):
        """Get project workspace via API."""
        # Create project first
        client.post(
            "/api/onboarding/projects",
            json={
                "project_id": "test_workspace",
                "name": "工作台测试",
                "initial_chapter_count": 3,
            },
        )

        # Get workspace
        response = client.get("/api/projects/test_workspace/workspace")
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["data"]["project"]["project_id"] == "test_workspace"
        assert len(data["data"]["chapters"]) == 3
        assert "stats" in data["data"]


# ── Section 6: Config Plan ───────────────────────────────────────

class TestConfigPlan:
    """Config plan generation works correctly."""

    def test_config_plan_generates_draft(self, client):
        """Config plan endpoint generates YAML draft."""
        response = client.post(
            "/api/config/plan",
            json={
                "provider": "openai",
                "model": "gpt-4",
                "api_key_env": "OPENAI_API_KEY",
                "default_llm": "default",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "draft" in data["data"]
        assert "llm_profiles:" in data["data"]["draft"]
        assert "api_key_env:" in data["data"]["draft"]
        assert "OPENAI_API_KEY" in data["data"]["draft"]

    def test_config_plan_no_real_key(self, client):
        """Config plan does not include real API key."""
        response = client.post(
            "/api/config/plan",
            json={
                "provider": "openai",
                "model": "gpt-4",
                "api_key_env": "MY_API_KEY",
            },
        )
        data = response.json()
        # Should have api_key_env field, not actual key value
        draft = data["data"]["draft"]
        assert "sk-" not in draft
        assert "MY_API_KEY" in draft

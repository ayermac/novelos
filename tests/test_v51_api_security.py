"""v5.1 API Security and Consistency Tests.

Tests for API security and consistency:
- All routes return {ok, error, data} envelope
- Error responses don't expose tracebacks
- Error responses don't expose absolute paths
- Error responses don't expose API keys
- Error messages are in Chinese
- Settings/config plan don't write files
- Run chapter in stub mode doesn't call real LLM
"""

from __future__ import annotations

import os
import tempfile

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def test_client():
    """Create test client with temporary database."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        from novel_factory.db.connection import init_db
        from novel_factory.api_app import create_api_app

        init_db(db_path)
        app = create_api_app(db_path=db_path, llm_mode="stub")
        client = TestClient(app)
        yield client
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


class TestAPISecurity:
    """API security tests."""

    def test_no_traceback_in_errors(self, test_client):
        """Test error responses don't expose tracebacks."""
        # Try to access non-existent project
        resp = test_client.get("/api/projects/nonexistent_project/workspace")
        resp_text = resp.text.lower()

        # Should not contain traceback indicators
        assert "traceback" not in resp_text
        assert "file \"" not in resp_text or "file " not in resp_text
        assert "line " not in resp_text or "line 1" not in resp_text

    def test_no_absolute_paths_in_errors(self, test_client):
        """Test error responses don't expose absolute paths."""
        resp = test_client.get("/api/projects/nonexistent_project/workspace")
        resp_text = resp.text

        # Should not contain absolute paths
        assert "/Users/" not in resp_text
        assert "/home/" not in resp_text
        assert "/root/" not in resp_text
        assert "C:\\" not in resp_text

    def test_no_api_key_in_settings(self, test_client):
        """Test settings endpoint doesn't expose API keys."""
        resp = test_client.get("/api/settings")
        resp_text = resp.text

        # Should not contain API key patterns
        assert "sk-" not in resp_text
        assert "sk_live_" not in resp_text
        assert "sk_test_" not in resp_text
        assert "api_key_value" not in resp_text

        # Check JSON structure
        data = resp.json()
        if data["ok"] and "llm_profiles" in data["data"]:
            for profile in data["data"]["llm_profiles"]:
                # Should only have has_key boolean
                assert "has_key" in profile
                # Should not have actual API key value
                if "api_key" in profile:
                    assert profile["api_key"] is None

    def test_error_messages_in_chinese(self, test_client):
        """Test error messages are in Chinese."""
        # Try to access non-existent project
        resp = test_client.get("/api/projects/nonexistent_project/workspace")
        data = resp.json()

        assert data["ok"] is False
        assert "error" in data
        assert "message" in data["error"]

        # Error message should contain Chinese characters
        message = data["error"]["message"]
        has_chinese = any("\u4e00" <= char <= "\u9fff" for char in message)
        assert has_chinese, f"Error message should be in Chinese: {message}"

    def test_config_plan_no_file_write(self, test_client):
        """Test config plan endpoint doesn't write files."""
        import tempfile
        from pathlib import Path

        # Create temp directory
        with tempfile.TemporaryDirectory() as tmpdir:
            # Change to temp directory
            old_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)

                # Call config plan
                resp = test_client.post(
                    "/api/config/plan",
                    json={
                        "project_id": "test_project",
                        "provider": "openai",
                        "model": "gpt-4",
                        "api_key_env": "OPENAI_API_KEY",
                    },
                )

                # Check no files were created
                files = list(Path(tmpdir).glob("*"))
                yaml_files = [f for f in files if f.suffix in [".yaml", ".yml"]]

                assert len(yaml_files) == 0, "Config plan should not write files"

                # Response should contain draft
                data = resp.json()
                if data["ok"]:
                    assert "draft" in data["data"] or "config" in data["data"]

            finally:
                os.chdir(old_cwd)

    def test_run_chapter_stub_no_real_llm(self, test_client):
        """Test run chapter in stub mode doesn't call real LLM."""
        # Create project
        test_client.post(
            "/api/onboarding/projects",
            json={
                "project_id": "stub_test_project",
                "name": "Stub Test",
                "genre": "玄幻",
                "initial_chapter_count": 1,
            },
        )

        # Run chapter in stub mode
        resp = test_client.post(
            "/api/run/chapter",
            json={
                "project_id": "stub_test_project",
                "chapter": 1,
            },
        )

        data = resp.json()
        assert data["ok"] is True

        # Should indicate stub mode
        assert data["data"]["llm_mode"] == "stub"

        # Should complete quickly (no real LLM call)
        assert data["data"]["status"] in ["completed", "pending", "running"]

    def test_all_routes_return_envelope(self, test_client):
        """Test all API routes return {ok, error, data} envelope."""
        routes = [
            ("GET", "/api/health"),
            ("GET", "/api/dashboard"),
            ("GET", "/api/projects"),
            ("GET", "/api/style/console"),
            ("GET", "/api/settings"),
            ("GET", "/api/acceptance"),
        ]

        for method, route in routes:
            if method == "GET":
                resp = test_client.get(route)
            else:
                continue

            data = resp.json()

            # Must have ok field
            assert "ok" in data, f"{route} missing 'ok' field"

            # Must have error or data field
            if data["ok"]:
                assert "data" in data, f"{route} missing 'data' on success"
                assert data.get("error") is None
            else:
                assert "error" in data, f"{route} missing 'error' on failure"
                assert data.get("data") is None
                assert "code" in data["error"]
                assert "message" in data["error"]

    def test_no_secrets_in_response_headers(self, test_client):
        """Test API responses don't leak secrets in headers."""
        resp = test_client.get("/api/settings")

        # Check headers don't contain secrets
        headers_str = str(resp.headers).lower()

        assert "api-key" not in headers_str
        assert "authorization" not in headers_str or "bearer" not in headers_str
        assert "sk-" not in headers_str

    def test_error_response_consistency(self, test_client):
        """Test error responses are consistent."""
        # Test multiple error scenarios
        error_responses = []

        # Non-existent project
        resp1 = test_client.get("/api/projects/nonexistent1/workspace")
        error_responses.append(resp1.json())

        # Non-existent project for run
        resp2 = test_client.post(
            "/api/run/chapter",
            json={"project_id": "nonexistent2", "chapter": 1},
        )
        error_responses.append(resp2.json())

        # Check all error responses have consistent structure
        for error_resp in error_responses:
            if not error_resp["ok"]:
                assert "error" in error_resp
                assert "code" in error_resp["error"]
                assert "message" in error_resp["error"]
                assert isinstance(error_resp["error"]["code"], str)
                assert isinstance(error_resp["error"]["message"], str)

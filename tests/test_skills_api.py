"""Tests for v5.3.3 Skill Visibility API.

Covers:
- GET /api/skills
- GET /api/skills/{skill_id}
- GET /api/skills/mounts
- POST /api/skills/validate
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from novel_factory.api_app import create_api_app
from novel_factory.db.connection import init_db


@pytest.fixture
def test_client():
    """Create test client with isolated database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        init_db(str(db_path))
        app = create_api_app(db_path=str(db_path), llm_mode="stub")
        client = TestClient(app)
        yield client


class TestListSkills:
    """Test GET /api/skills."""

    def test_returns_envelope(self, test_client):
        resp = test_client.get("/api/skills")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "data" in data
        assert "skills" in data["data"]

    def test_returns_four_skills(self, test_client):
        resp = test_client.get("/api/skills")
        data = resp.json()
        skills = data["data"]["skills"]
        skill_ids = {s["id"] for s in skills}
        expected = {"humanizer-zh", "ai-style-detector", "narrative-quality", "style-bible-checker"}
        assert skill_ids == expected

    def test_each_skill_has_required_fields(self, test_client):
        resp = test_client.get("/api/skills")
        data = resp.json()
        skills = data["data"]["skills"]
        for skill in skills:
            assert "id" in skill
            assert "enabled" in skill
            assert "mounted_to" in skill
            assert "is_mounted" in skill

    def test_style_bible_checker_is_enabled_but_unmounted(self, test_client):
        resp = test_client.get("/api/skills")
        data = resp.json()
        skills = data["data"]["skills"]
        sbc = next((s for s in skills if s["id"] == "style-bible-checker"), None)
        assert sbc is not None
        assert sbc["enabled"] is True
        assert sbc["is_mounted"] is False
        assert sbc["mounted_to"] == []


class TestGetSkillDetail:
    """Test GET /api/skills/{skill_id}."""

    def test_existing_skill_returns_envelope(self, test_client):
        resp = test_client.get("/api/skills/humanizer-zh")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "data" in data

    def test_existing_skill_has_detail_fields(self, test_client):
        resp = test_client.get("/api/skills/humanizer-zh")
        data = resp.json()["data"]
        assert data["id"] == "humanizer-zh"
        assert "name" in data
        assert "kind" in data
        assert "version" in data
        assert "class_name" in data
        assert "description" in data
        assert "mounted_to" in data
        assert "is_mounted" in data

    def test_not_found_returns_error(self, test_client):
        resp = test_client.get("/api/skills/not-found")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert data["error"] is not None
        assert data["error"]["code"] == "RESOURCE_NOT_FOUND"


class TestGetSkillMounts:
    """Test GET /api/skills/mounts."""

    def test_returns_envelope(self, test_client):
        resp = test_client.get("/api/skills/mounts")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "data" in data

    def test_returns_polisher_and_editor_mounts(self, test_client):
        resp = test_client.get("/api/skills/mounts")
        data = resp.json()["data"]
        assert "polisher" in data
        assert "editor" in data
        assert "after_llm" in data["polisher"]
        assert "before_save" in data["polisher"]
        assert "before_review" in data["editor"]
        assert "humanizer-zh" in data["polisher"]["after_llm"]
        assert "ai-style-detector" in data["polisher"]["before_save"]
        assert "ai-style-detector" in data["editor"]["before_review"]
        assert "narrative-quality" in data["editor"]["before_review"]


class TestValidateSkills:
    """Test POST /api/skills/validate."""

    def test_returns_envelope(self, test_client):
        resp = test_client.post("/api/skills/validate")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "data" in data

    def test_returns_ok_errors_warnings(self, test_client):
        resp = test_client.post("/api/skills/validate")
        data = resp.json()["data"]
        assert "ok" in data
        assert "errors" in data
        assert "warnings" in data
        assert isinstance(data["errors"], list)
        assert isinstance(data["warnings"], list)


class TestTestSkills:
    """Test POST /api/skills/test."""

    def test_all_returns_envelope_and_results(self, test_client):
        resp = test_client.post("/api/skills/test", json={"all": True})
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "data" in data
        result = data["data"]
        assert "total" in result
        assert "passed" in result
        assert "failed" in result
        assert "skipped" in result
        assert "skipped_ids" in result
        assert "results" in result

    def test_single_skill_returns_ok(self, test_client):
        resp = test_client.post("/api/skills/test", json={"skill_id": "humanizer-zh"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "data" in data
        result = data["data"]
        assert result["skill_id"] == "humanizer-zh"
        assert "result" in result

    def test_empty_request_returns_validation_error(self, test_client):
        resp = test_client.post("/api/skills/test", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert data["error"]["code"] == "VALIDATION_ERROR"


class TestRunSkill:
    """Test POST /api/skills/run."""

    def test_run_humanizer_zh_with_text(self, test_client):
        resp = test_client.post("/api/skills/run", json={
            "skill_id": "humanizer-zh",
            "text": "这是一个测试文本。",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "data" in data
        result = data["data"]
        assert result["skill_id"] == "humanizer-zh"
        assert "result" in result

    def test_run_unknown_skill(self, test_client):
        resp = test_client.post("/api/skills/run", json={
            "skill_id": "unknown-skill",
            "text": "test",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert data["error"]["code"] == "RESOURCE_NOT_FOUND"

    def test_run_without_text_or_payload(self, test_client):
        resp = test_client.post("/api/skills/run", json={
            "skill_id": "humanizer-zh",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert data["error"]["code"] == "VALIDATION_ERROR"

    def test_run_empty_string_text(self, test_client):
        resp = test_client.post("/api/skills/run", json={
            "skill_id": "humanizer-zh",
            "text": "",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert data["error"]["code"] == "VALIDATION_ERROR"

    def test_run_whitespace_text(self, test_client):
        resp = test_client.post("/api/skills/run", json={
            "skill_id": "humanizer-zh",
            "text": "   ",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert data["error"]["code"] == "VALIDATION_ERROR"

    def test_run_empty_payload(self, test_client):
        resp = test_client.post("/api/skills/run", json={
            "skill_id": "humanizer-zh",
            "payload": {},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert data["error"]["code"] == "VALIDATION_ERROR"

    def test_run_text_and_payload_merged(self, test_client):
        resp = test_client.post("/api/skills/run", json={
            "skill_id": "humanizer-zh",
            "text": "合并测试",
            "payload": {"extra": "value"},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        result = data["data"]
        assert result["skill_id"] == "humanizer-zh"
        assert "result" in result

    def test_run_all_skips_non_package_skills(self, test_client):
        resp = test_client.post("/api/skills/test", json={"all": True})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "skipped" in data
        assert "skipped_ids" in data
        assert "style-bible-checker" in data["skipped_ids"]

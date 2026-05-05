"""Tests for v5.3.3 Skill Visibility API and v5.4.6 Mount Configuration API.

Covers:
- GET /api/skills
- GET /api/skills/config
- GET /api/skills/{skill_id}
- GET /api/skills/mounts
- POST /api/skills/mount
- DELETE /api/skills/mount
- POST /api/skills/reorder
- POST /api/skills/validate
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from novel_factory.api_app import create_api_app
from novel_factory.db.connection import init_db


DEFAULT_SKILLS_PATH = Path(__file__).parent.parent / "novel_factory" / "config" / "skills.yaml"


@pytest.fixture
def test_client():
    """Create test client with isolated database and skills config."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        init_db(str(db_path))

        # Copy default skills.yaml to temp dir for safe writes
        skills_path = Path(tmpdir) / "skills.yaml"
        shutil.copy(str(DEFAULT_SKILLS_PATH), str(skills_path))

        app = create_api_app(
            db_path=str(db_path),
            llm_mode="stub",
            skills_config_path=str(skills_path),
        )
        client = TestClient(app)
        yield client


def _write_openclaw_skill(root: Path, agent: str, skill: str, body: str) -> Path:
    """Write a minimal OpenClaw-style SKILL.md for tests."""
    skill_dir = root / agent / "workspace" / "skills" / skill
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(
        f"""---
name: {skill}
description: Test {skill}
---

{body}
""",
        encoding="utf-8",
    )
    return skill_dir


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

    def test_style_bible_checker_is_enabled_and_mounted_to_editor(self, test_client):
        resp = test_client.get("/api/skills")
        data = resp.json()
        skills = data["data"]["skills"]
        sbc = next((s for s in skills if s["id"] == "style-bible-checker"), None)
        assert sbc is not None
        assert sbc["enabled"] is True
        assert sbc["is_mounted"] is True
        assert {"agent": "editor", "stage": "before_review"} in sbc["mounted_to"]


class TestGetSkillConfig:
    """Test GET /api/skills/config."""

    def test_returns_envelope(self, test_client):
        resp = test_client.get("/api/skills/config")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "data" in data

    def test_has_required_fields(self, test_client):
        resp = test_client.get("/api/skills/config")
        data = resp.json()["data"]
        assert "agents" in data
        assert "stages" in data
        assert "agent_skills" in data
        assert "available_skills" in data
        assert "missing_skills" in data
        assert "disabled_skills" in data
        assert "config_path" in data
        assert "total_skills" in data
        assert "total_mounted" in data

    def test_available_skills_match_registry(self, test_client):
        resp = test_client.get("/api/skills/config")
        data = resp.json()["data"]
        available_ids = {s["id"] for s in data["available_skills"]}
        assert available_ids == {"humanizer-zh", "ai-style-detector", "narrative-quality", "style-bible-checker"}

    def test_config_path_is_skills_yaml(self, test_client):
        resp = test_client.get("/api/skills/config")
        data = resp.json()["data"]
        assert "skills.yaml" in data["config_path"]


class TestOpenClawReadiness:
    """Test GET /api/skills/openclaw-readiness."""

    def test_openclaw_readiness_classifies_candidates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "openclaw-agents"
            _write_openclaw_skill(root, "planner", "worldbuilding", "Instruction-only skill.")
            _write_openclaw_skill(root, "author", "novel-writing", "Run python3 tools/db.py build_context")
            _write_openclaw_skill(root, "secretary", "daily-report", "Daily reporting helper.")

            db_path = Path(tmpdir) / "test.db"
            init_db(str(db_path))
            skills_path = Path(tmpdir) / "skills.yaml"
            shutil.copy(str(DEFAULT_SKILLS_PATH), str(skills_path))

            app = create_api_app(
                db_path=str(db_path),
                llm_mode="stub",
                skills_config_path=str(skills_path),
                openclaw_root_path=str(root),
            )
            client = TestClient(app)

            resp = client.get("/api/skills/openclaw-readiness")
            assert resp.status_code == 200
            envelope = resp.json()
            assert envelope["ok"] is True
            data = envelope["data"]
            assert data["root_exists"] is True
            assert data["total"] == 3
            assert data["summary"]["import_ready"] == 1
            assert data["summary"]["needs_adapter"] == 1
            assert data["summary"]["manual_ready"] == 1

            by_name = {candidate["name"]: candidate for candidate in data["candidates"]}
            assert by_name["worldbuilding"]["target_agent"] == "planner"
            assert by_name["worldbuilding"]["status"] == "import_ready"
            assert by_name["novel-writing"]["status"] == "needs_adapter"
            assert by_name["daily-report"]["status"] == "manual_ready"

    def test_openclaw_readiness_missing_root_is_non_blocking(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            init_db(str(db_path))
            skills_path = Path(tmpdir) / "skills.yaml"
            shutil.copy(str(DEFAULT_SKILLS_PATH), str(skills_path))

            app = create_api_app(
                db_path=str(db_path),
                llm_mode="stub",
                skills_config_path=str(skills_path),
                openclaw_root_path=str(Path(tmpdir) / "missing-openclaw"),
            )
            client = TestClient(app)

            resp = client.get("/api/skills/openclaw-readiness")
            data = resp.json()["data"]
            assert data["root_exists"] is False
            assert data["total"] == 0
            assert data["warnings"] == ["OpenClaw legacy workspace not found"]

    def test_universal_import_readiness_treats_unmapped_skills_as_manual_ready(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "openclaw-agents"
            _write_openclaw_skill(root, "planner", "worldbuilding", "Instruction-only skill.")
            _write_openclaw_skill(root, "secretary", "daily-report", "Daily reporting helper.")

            db_path = Path(tmpdir) / "test.db"
            init_db(str(db_path))
            skills_path = Path(tmpdir) / "skills.yaml"
            shutil.copy(str(DEFAULT_SKILLS_PATH), str(skills_path))

            app = create_api_app(
                db_path=str(db_path),
                llm_mode="stub",
                skills_config_path=str(skills_path),
                openclaw_root_path=str(root),
            )
            client = TestClient(app)

            resp = client.get("/api/skills/import-readiness")
            assert resp.status_code == 200
            data = resp.json()["data"]
            by_name = {candidate["name"]: candidate for candidate in data["candidates"]}
            assert by_name["worldbuilding"]["status"] == "import_ready"
            assert by_name["daily-report"]["status"] == "manual_ready"
            assert by_name["daily-report"]["target_agent"] is None
            assert by_name["daily-report"]["source_type"] == "openclaw"

    def test_openclaw_import_plan_preview_is_read_only(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "openclaw-agents"
            _write_openclaw_skill(root, "planner", "worldbuilding", "Instruction-only skill.")

            db_path = Path(tmpdir) / "test.db"
            init_db(str(db_path))
            skills_path = Path(tmpdir) / "skills.yaml"
            shutil.copy(str(DEFAULT_SKILLS_PATH), str(skills_path))

            before = skills_path.read_text(encoding="utf-8")
            app = create_api_app(
                db_path=str(db_path),
                llm_mode="stub",
                skills_config_path=str(skills_path),
                openclaw_root_path=str(root),
            )
            client = TestClient(app)

            resp = client.post("/api/skills/openclaw-import-plan", json={
                "source_path": "planner/workspace/skills/worldbuilding",
            })
            assert resp.status_code == 200
            envelope = resp.json()
            assert envelope["ok"] is True
            data = envelope["data"]
            assert data["target"]["skill_id"] == "imported-worldbuilding"
            assert data["target"]["kind"] == "imported_instruction"
            assert data["read_only"] is True
            assert skills_path.read_text(encoding="utf-8") == before

    def test_universal_import_plan_preview_is_read_only(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "openclaw-agents"
            _write_openclaw_skill(root, "planner", "worldbuilding", "Instruction-only skill.")

            db_path = Path(tmpdir) / "test.db"
            init_db(str(db_path))
            skills_path = Path(tmpdir) / "skills.yaml"
            shutil.copy(str(DEFAULT_SKILLS_PATH), str(skills_path))

            before = skills_path.read_text(encoding="utf-8")
            app = create_api_app(
                db_path=str(db_path),
                llm_mode="stub",
                skills_config_path=str(skills_path),
                openclaw_root_path=str(root),
            )
            client = TestClient(app)

            resp = client.post("/api/skills/import-plan", json={
                "source_type": "openclaw",
                "source_path": "planner/workspace/skills/worldbuilding",
            })
            envelope = resp.json()
            assert envelope["ok"] is True
            data = envelope["data"]
            assert data["source_type"] == "openclaw"
            assert data["source_label"] == "OpenClaw legacy workspace"
            assert data["target"]["skill_id"] == "imported-worldbuilding"
            assert data["read_only"] is True
            assert skills_path.read_text(encoding="utf-8") == before

    def test_openclaw_import_plan_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "openclaw-agents"
            root.mkdir()
            db_path = Path(tmpdir) / "test.db"
            init_db(str(db_path))
            skills_path = Path(tmpdir) / "skills.yaml"
            shutil.copy(str(DEFAULT_SKILLS_PATH), str(skills_path))

            app = create_api_app(
                db_path=str(db_path),
                llm_mode="stub",
                skills_config_path=str(skills_path),
                openclaw_root_path=str(root),
            )
            client = TestClient(app)

            resp = client.post("/api/skills/openclaw-import-plan", json={
                "source_path": "../outside",
            })
            data = resp.json()
            assert data["ok"] is False
            assert data["error"]["code"] == "VALIDATION_ERROR"

    def test_universal_import_plan_rejects_unknown_source_type(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            init_db(str(db_path))
            skills_path = Path(tmpdir) / "skills.yaml"
            shutil.copy(str(DEFAULT_SKILLS_PATH), str(skills_path))

            app = create_api_app(
                db_path=str(db_path),
                llm_mode="stub",
                skills_config_path=str(skills_path),
                openclaw_root_path=str(Path(tmpdir) / "missing-openclaw"),
            )
            client = TestClient(app)

            resp = client.post("/api/skills/import-plan", json={
                "source_type": "unknown",
                "source_path": "anything",
            })
            data = resp.json()
            assert data["ok"] is False
            assert data["error"]["code"] == "VALIDATION_ERROR"


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
        assert "style-bible-checker" in data["editor"]["before_review"]


class TestMountSkill:
    """Test POST /api/skills/mount."""

    def test_mount_skill_success(self, test_client):
        resp = test_client.post("/api/skills/mount", json={
            "agent": "polisher",
            "stage": "after_llm",
            "skill_id": "narrative-quality",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["data"]["agent"] == "polisher"
        assert data["data"]["skill_id"] == "narrative-quality"

    def test_mount_duplicate_skill_rejected(self, test_client):
        # style-bible-checker is already mounted to editor/before_review
        resp = test_client.post("/api/skills/mount", json={
            "agent": "editor",
            "stage": "before_review",
            "skill_id": "style-bible-checker",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert data["error"]["code"] == "VALIDATION_ERROR"

    def test_mount_unknown_skill_rejected(self, test_client):
        resp = test_client.post("/api/skills/mount", json={
            "agent": "polisher",
            "stage": "after_llm",
            "skill_id": "unknown-skill",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert data["error"]["code"] == "VALIDATION_ERROR"

    def test_mount_unknown_agent_rejected(self, test_client):
        resp = test_client.post("/api/skills/mount", json={
            "agent": "nonexistent-agent",
            "stage": "after_llm",
            "skill_id": "humanizer-zh",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert data["error"]["code"] == "VALIDATION_ERROR"

    def test_mount_unknown_stage_rejected(self, test_client):
        resp = test_client.post("/api/skills/mount", json={
            "agent": "editor",
            "stage": "before_reveiw",
            "skill_id": "humanizer-zh",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert data["error"]["code"] == "VALIDATION_ERROR"
        assert "before_review" in data["error"]["message"]

    def test_mount_refreshes_agent_matrix(self, test_client):
        # Mount narrative-quality to polisher/after_llm
        test_client.post("/api/skills/mount", json={
            "agent": "polisher",
            "stage": "after_llm",
            "skill_id": "narrative-quality",
        })
        resp = test_client.get("/api/skills/agent-matrix")
        data = resp.json()["data"]
        polisher = next(a for a in data["agents"] if a["agent"] == "polisher")
        after_llm = next(s for s in polisher["stages"] if s["stage"] == "after_llm")
        skill_ids = [s["id"] for s in after_llm["skills"]]
        assert "narrative-quality" in skill_ids


class TestUnmountSkill:
    """Test DELETE /api/skills/mount."""

    def test_unmount_skill_success(self, test_client):
        resp = test_client.request("DELETE", "/api/skills/mount", json={
            "agent": "editor",
            "stage": "before_review",
            "skill_id": "style-bible-checker",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["data"]["skill_id"] == "style-bible-checker"

    def test_unmount_missing_skill_behavior(self, test_client):
        # narrative-quality is not mounted to polisher/after_llm initially
        resp = test_client.request("DELETE", "/api/skills/mount", json={
            "agent": "polisher",
            "stage": "after_llm",
            "skill_id": "narrative-quality",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert data["error"]["code"] == "VALIDATION_ERROR"


class TestReorderSkills:
    """Test POST /api/skills/reorder."""

    def test_reorder_skill_success(self, test_client):
        resp = test_client.post("/api/skills/reorder", json={
            "agent": "editor",
            "stage": "before_review",
            "skill_ids": ["style-bible-checker", "narrative-quality", "ai-style-detector"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["data"]["skill_ids"] == [
            "style-bible-checker", "narrative-quality", "ai-style-detector"
        ]

    def test_reorder_rejects_missing_or_extra_ids(self, test_client):
        # Missing style-bible-checker
        resp = test_client.post("/api/skills/reorder", json={
            "agent": "editor",
            "stage": "before_review",
            "skill_ids": ["narrative-quality", "ai-style-detector"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert data["error"]["code"] == "VALIDATION_ERROR"

        # Extra unknown skill
        resp2 = test_client.post("/api/skills/reorder", json={
            "agent": "editor",
            "stage": "before_review",
            "skill_ids": ["style-bible-checker", "narrative-quality", "ai-style-detector", "unknown"],
        })
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["ok"] is False
        assert data2["error"]["code"] == "VALIDATION_ERROR"


class TestGetAgentSkillMatrix:
    """Test GET /api/skills/agent-matrix."""

    def test_returns_agent_matrix_envelope(self, test_client):
        resp = test_client.get("/api/skills/agent-matrix")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "agents" in data["data"]
        assert "warnings" in data["data"]
        assert "unmounted_enabled_skills" in data["data"]

    def test_includes_editor_style_bible_mount(self, test_client):
        resp = test_client.get("/api/skills/agent-matrix")
        matrix = resp.json()["data"]
        editor = next(a for a in matrix["agents"] if a["agent"] == "editor")
        before_review = next(s for s in editor["stages"] if s["stage"] == "before_review")
        skill_ids = [s["id"] for s in before_review["skills"]]
        assert "ai-style-detector" in skill_ids
        assert "narrative-quality" in skill_ids
        assert "style-bible-checker" in skill_ids

    def test_style_bible_checker_marked_legacy(self, test_client):
        resp = test_client.get("/api/skills/agent-matrix")
        matrix = resp.json()["data"]
        editor = next(a for a in matrix["agents"] if a["agent"] == "editor")
        before_review = next(s for s in editor["stages"] if s["stage"] == "before_review")
        style_bible = next(s for s in before_review["skills"] if s["id"] == "style-bible-checker")
        assert style_bible["legacy"] is True
        assert style_bible["package"] is None


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


class TestSaveConfig:
    """Test SkillRegistry.save_config preserves top-level keys."""

    def test_save_config_preserves_top_level_keys(self):
        import tempfile
        import yaml
        from novel_factory.skills.registry import SkillRegistry

        with tempfile.TemporaryDirectory() as tmpdir:
            skills_path = Path(tmpdir) / "skills.yaml"
            # Write a file with extra top-level metadata
            original = {
                "_schema_version": "1.0",
                "skills": {
                    "humanizer-zh": {
                        "enabled": True,
                        "class": "HumanizerZhSkill",
                        "description": "Humanizer",
                    }
                },
                "agent_skills": {},
            }
            with open(skills_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(original, f, allow_unicode=True, sort_keys=False)

            registry = SkillRegistry(config_path=str(skills_path))
            registry.mount_skill("editor", "before_review", "humanizer-zh")
            registry.save_config()

            with open(skills_path, "r", encoding="utf-8") as f:
                saved = yaml.safe_load(f)

            assert saved.get("_schema_version") == "1.0"
            assert "skills" in saved
            assert "agent_skills" in saved
            assert saved["agent_skills"]["editor"]["before_review"] == ["humanizer-zh"]

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

    def test_returns_core_agent_skill_set(self, test_client):
        resp = test_client.get("/api/skills")
        data = resp.json()
        skills = data["data"]["skills"]
        skill_ids = {s["id"] for s in skills}
        expected = {
            "humanizer-zh",
            "ai-style-detector",
            "narrative-quality",
            "style-bible-checker",
            "chapter-objective-checker",
            "scene-conflict-checker",
            "event-coverage-checker",
            "memory-patch-validator",
        }
        assert expected.issubset(skill_ids)
        assert len(skill_ids) >= 8

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

    def test_available_skills_include_mountable_targets(self, test_client):
        resp = test_client.get("/api/skills/config")
        data = resp.json()["data"]
        by_id = {skill["id"]: skill for skill in data["available_skills"]}
        assert {"agent": "polisher", "stage": "after_llm"} in by_id["humanizer-zh"]["mountable_targets"]
        assert {"agent": "editor", "stage": "before_review"} in by_id["narrative-quality"]["mountable_targets"]

    def test_available_skills_match_registry(self, test_client):
        resp = test_client.get("/api/skills/config")
        data = resp.json()["data"]
        available_ids = {s["id"] for s in data["available_skills"]}
        assert {
            "humanizer-zh",
            "ai-style-detector",
            "narrative-quality",
            "style-bible-checker",
            "chapter-objective-checker",
            "scene-conflict-checker",
            "event-coverage-checker",
            "memory-patch-validator",
        }.issubset(available_ids)

    def test_core_agent_default_mounts_are_present(self, test_client):
        resp = test_client.get("/api/skills/config")
        data = resp.json()["data"]
        agent_skills = data["agent_skills"]
        assert "chapter-objective-checker" in agent_skills["planner"]["after_llm"]
        assert "foreshadowing-debt" in agent_skills["planner"]["after_llm"]
        assert agent_skills["screenwriter"]["after_llm"] == ["scene-conflict-checker"]
        assert "event-coverage-checker" in agent_skills["author"]["after_llm"]
        assert "opening-hook-checker" in agent_skills["author"]["after_llm"]
        assert agent_skills["memory_curator"]["after_extract"] == ["memory-patch-validator"]

    def test_new_agent_skills_have_manifest_and_are_not_legacy(self, test_client):
        resp = test_client.get("/api/skills/config")
        data = resp.json()["data"]
        by_id = {skill["id"]: skill for skill in data["available_skills"]}
        for skill_id in (
            "chapter-objective-checker",
            "scene-conflict-checker",
            "event-coverage-checker",
            "memory-patch-validator",
        ):
            assert by_id[skill_id]["legacy"] is False

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
            _write_openclaw_skill(root, "researcher", "daily-report", "Daily reporting helper.")

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
            _write_openclaw_skill(root, "researcher", "daily-report", "Daily reporting helper.")

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

    def test_universal_import_apply_registers_disabled_unmounted_skill(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "openclaw-agents"
            _write_openclaw_skill(root, "planner", "worldbuilding", "Instruction-only skill.")

            db_path = Path(tmpdir) / "test.db"
            init_db(str(db_path))
            config_dir = Path(tmpdir) / "config"
            config_dir.mkdir()
            skills_path = config_dir / "skills.yaml"
            shutil.copy(str(DEFAULT_SKILLS_PATH), str(skills_path))

            app = create_api_app(
                db_path=str(db_path),
                llm_mode="stub",
                skills_config_path=str(skills_path),
                openclaw_root_path=str(root),
            )
            client = TestClient(app)

            resp = client.post("/api/skills/import-apply", json={
                "source_type": "openclaw",
                "source_path": "planner/workspace/skills/worldbuilding",
            })
            assert resp.status_code == 200
            envelope = resp.json()
            assert envelope["ok"] is True
            data = envelope["data"]
            assert data["skill_id"] == "imported-worldbuilding"
            assert data["registered"] is True
            assert data["enabled"] is False
            assert data["mounted"] is False
            assert data["package"] == "skill_packages/imported_worldbuilding"
            assert (Path(tmpdir) / "skill_packages" / "imported_worldbuilding" / "manifest.yaml").exists()

            config_resp = client.get("/api/skills/config")
            config = config_resp.json()["data"]
            imported = next(s for s in config["available_skills"] if s["id"] == "imported-worldbuilding")
            assert imported["enabled"] is False
            assert {"agent": "manual", "stage": "manual"} in imported["allowed_targets"]
            assert {"agent": "manual", "stage": "manual"} in imported["mountable_targets"]
            assert "imported-worldbuilding" not in config["agent_skills"].get("planner", {}).get("before_llm", [])

    def test_universal_import_apply_duplicate_rejected_without_force(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "openclaw-agents"
            _write_openclaw_skill(root, "planner", "worldbuilding", "Instruction-only skill.")

            db_path = Path(tmpdir) / "test.db"
            init_db(str(db_path))
            config_dir = Path(tmpdir) / "config"
            config_dir.mkdir()
            skills_path = config_dir / "skills.yaml"
            shutil.copy(str(DEFAULT_SKILLS_PATH), str(skills_path))

            app = create_api_app(
                db_path=str(db_path),
                llm_mode="stub",
                skills_config_path=str(skills_path),
                openclaw_root_path=str(root),
            )
            client = TestClient(app)

            body = {
                "source_type": "openclaw",
                "source_path": "planner/workspace/skills/worldbuilding",
            }
            assert client.post("/api/skills/import-apply", json=body).json()["ok"] is True
            second = client.post("/api/skills/import-apply", json=body).json()
            assert second["ok"] is False
            assert second["error"]["code"] == "VALIDATION_ERROR"

    def test_universal_import_apply_rejects_unknown_source_type(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            init_db(str(db_path))
            config_dir = Path(tmpdir) / "config"
            config_dir.mkdir()
            skills_path = config_dir / "skills.yaml"
            shutil.copy(str(DEFAULT_SKILLS_PATH), str(skills_path))

            app = create_api_app(
                db_path=str(db_path),
                llm_mode="stub",
                skills_config_path=str(skills_path),
            )
            client = TestClient(app)

            resp = client.post("/api/skills/import-apply", json={
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
        test_client.request("DELETE", "/api/skills/mount", json={
            "agent": "editor",
            "stage": "before_review",
            "skill_id": "narrative-quality",
        })
        resp = test_client.post("/api/skills/mount", json={
            "agent": "editor",
            "stage": "before_review",
            "skill_id": "narrative-quality",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["data"]["agent"] == "editor"
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

    def test_mount_disabled_skill_rejected_by_safety_guard(self, test_client):
        test_client.post("/api/skills/enabled", json={
            "skill_id": "humanizer-zh",
            "enabled": False,
        })
        resp = test_client.post("/api/skills/mount", json={
            "agent": "polisher",
            "stage": "after_llm",
            "skill_id": "humanizer-zh",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert data["error"]["code"] == "VALIDATION_ERROR"
        assert data["error"]["details"]["review"]["verdict"] == "block"
        assert any(
            finding["code"] == "SKILL_DISABLED"
            for finding in data["error"]["details"]["review"]["findings"]
        )

    def test_mount_manual_only_imported_skill_rejected_by_safety_guard(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "openclaw-agents"
            _write_openclaw_skill(root, "planner", "worldbuilding", "Instruction-only skill.")

            db_path = Path(tmpdir) / "test.db"
            init_db(str(db_path))
            config_dir = Path(tmpdir) / "config"
            config_dir.mkdir()
            skills_path = config_dir / "skills.yaml"
            shutil.copy(str(DEFAULT_SKILLS_PATH), str(skills_path))

            app = create_api_app(
                db_path=str(db_path),
                llm_mode="stub",
                skills_config_path=str(skills_path),
                openclaw_root_path=str(root),
            )
            client = TestClient(app)

            assert client.post("/api/skills/import-apply", json={
                "source_type": "openclaw",
                "source_path": "planner/workspace/skills/worldbuilding",
            }).json()["ok"] is True
            assert client.post("/api/skills/enabled", json={
                "skill_id": "imported-worldbuilding",
                "enabled": True,
            }).json()["ok"] is True

            resp = client.post("/api/skills/mount", json={
                "agent": "planner",
                "stage": "before_llm",
                "skill_id": "imported-worldbuilding",
            })
            data = resp.json()
            assert data["ok"] is False
            assert data["error"]["code"] == "VALIDATION_ERROR"
            review = data["error"]["details"]["review"]
            assert review["verdict"] == "block"
            assert any(f["code"] == "AGENT_STAGE_NOT_ALLOWED" for f in review["findings"])

    def test_mount_refreshes_agent_matrix(self, test_client):
        # Re-mount narrative-quality to its allowed editor/before_review target
        test_client.request("DELETE", "/api/skills/mount", json={
            "agent": "editor",
            "stage": "before_review",
            "skill_id": "narrative-quality",
        })
        test_client.post("/api/skills/mount", json={
            "agent": "editor",
            "stage": "before_review",
            "skill_id": "narrative-quality",
        })
        resp = test_client.get("/api/skills/agent-matrix")
        data = resp.json()["data"]
        editor = next(a for a in data["agents"] if a["agent"] == "editor")
        before_review = next(s for s in editor["stages"] if s["stage"] == "before_review")
        skill_ids = [s["id"] for s in before_review["skills"]]
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
            "skill_ids": [
                "ai-style-detector",
                "narrative-quality",
                "style-bible-checker",
                "show-dont-tell",
                "info-dump-detector",
                "scene-texture",
                "dialogue-naturalness",
                "continuity-gate",
                "chapter-seam",
                "death-penalty",
                "word-count-gate",
                "foreshadowing-debt",
                "opening-hook-checker",
                "excitement-density-checker",
            ],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["data"]["skill_ids"] == [
            "ai-style-detector",
            "narrative-quality",
            "style-bible-checker",
            "show-dont-tell",
            "info-dump-detector",
            "scene-texture",
            "dialogue-naturalness",
            "continuity-gate",
            "chapter-seam",
            "death-penalty",
            "word-count-gate",
            "foreshadowing-debt",
            "opening-hook-checker",
            "excitement-density-checker",
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


class TestSkillEnabled:
    """Test POST /api/skills/enabled."""

    def test_disable_and_enable_skill_success(self, test_client):
        disable = test_client.post("/api/skills/enabled", json={
            "skill_id": "humanizer-zh",
            "enabled": False,
        })
        assert disable.status_code == 200
        disable_data = disable.json()
        assert disable_data["ok"] is True
        assert disable_data["data"]["skill_id"] == "humanizer-zh"
        assert disable_data["data"]["enabled"] is False

        config = test_client.get("/api/skills/config").json()["data"]
        humanizer = next(s for s in config["available_skills"] if s["id"] == "humanizer-zh")
        assert humanizer["enabled"] is False
        assert any(s["id"] == "humanizer-zh" for s in config["disabled_skills"])

        enable = test_client.post("/api/skills/enabled", json={
            "skill_id": "humanizer-zh",
            "enabled": True,
        })
        assert enable.status_code == 200
        assert enable.json()["ok"] is True

        refreshed = test_client.get("/api/skills/config").json()["data"]
        humanizer = next(s for s in refreshed["available_skills"] if s["id"] == "humanizer-zh")
        assert humanizer["enabled"] is True

    def test_set_enabled_unknown_skill_rejected(self, test_client):
        resp = test_client.post("/api/skills/enabled", json={
            "skill_id": "unknown-skill",
            "enabled": True,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert data["error"]["code"] == "VALIDATION_ERROR"

    def test_disabling_mounted_skill_preserves_mount_and_matrix_warning(self, test_client):
        resp = test_client.post("/api/skills/enabled", json={
            "skill_id": "style-bible-checker",
            "enabled": False,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["data"]["is_mounted"] is True
        assert {"agent": "editor", "stage": "before_review"} in data["data"]["mounted_to"]

        mounts = test_client.get("/api/skills/mounts").json()["data"]
        assert "style-bible-checker" in mounts["editor"]["before_review"]

        matrix = test_client.get("/api/skills/agent-matrix").json()["data"]
        warning_codes = [warning["code"] for warning in matrix["warnings"]]
        assert "MOUNTED_DISABLED_SKILL" in warning_codes


class TestSkillReview:
    """Test POST /api/skills/review."""

    def test_review_allowed_skill_for_target_passes(self, test_client):
        resp = test_client.post("/api/skills/review", json={
            "skill_id": "humanizer-zh",
            "agent": "polisher",
            "stage": "after_llm",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["data"]["verdict"] == "pass"
        assert data["data"]["findings"] == []
        assert {"agent": "polisher", "stage": "after_llm"} in data["data"]["allowed_targets"]
        assert {"agent": "polisher", "stage": "after_llm"} in data["data"]["mountable_targets"]

    def test_review_disabled_skill_warns_without_target(self, test_client):
        test_client.post("/api/skills/enabled", json={
            "skill_id": "humanizer-zh",
            "enabled": False,
        })
        resp = test_client.post("/api/skills/review", json={
            "skill_id": "humanizer-zh",
        })
        data = resp.json()
        assert data["ok"] is True
        assert data["data"]["verdict"] == "warn"
        assert any(f["code"] == "SKILL_DISABLED" for f in data["data"]["findings"])
        assert data["data"]["mountable_targets"] == [{"agent": "manual", "stage": "manual"}]

    def test_review_rejects_partial_target(self, test_client):
        resp = test_client.post("/api/skills/review", json={
            "skill_id": "humanizer-zh",
            "agent": "polisher",
        })
        data = resp.json()
        assert data["ok"] is False
        assert data["error"]["code"] == "VALIDATION_ERROR"

    def test_review_unknown_skill_blocks(self, test_client):
        resp = test_client.post("/api/skills/review", json={
            "skill_id": "unknown-skill",
        })
        data = resp.json()
        assert data["ok"] is True
        assert data["data"]["verdict"] == "block"
        assert data["data"]["findings"][0]["code"] == "SKILL_NOT_FOUND"


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
        assert "show-dont-tell" in skill_ids
        assert "info-dump-detector" in skill_ids
        assert "scene-texture" in skill_ids
        assert "dialogue-naturalness" in skill_ids

    def test_antiai_skills_are_mounted_without_unmounted_warning(self, test_client):
        resp = test_client.get("/api/skills/agent-matrix")
        matrix = resp.json()["data"]
        unmounted_ids = {s["id"] for s in matrix["unmounted_enabled_skills"]}
        warning_ids = {
            w.get("skill_id")
            for w in matrix["warnings"]
            if w.get("code") == "ENABLED_UNMOUNTED_SKILL"
        }

        for skill_id in (
            "show-dont-tell",
            "info-dump-detector",
            "scene-texture",
            "dialogue-naturalness",
        ):
            assert skill_id not in unmounted_ids
            assert skill_id not in warning_ids

    def test_editor_quality_manifest_skills_are_not_legacy(self, test_client):
        resp = test_client.get("/api/skills/agent-matrix")
        matrix = resp.json()["data"]
        editor = next(a for a in matrix["agents"] if a["agent"] == "editor")
        before_review = next(s for s in editor["stages"] if s["stage"] == "before_review")
        by_id = {s["id"]: s for s in before_review["skills"]}

        for skill_id in (
            "style-bible-checker",
            "show-dont-tell",
            "info-dump-detector",
            "scene-texture",
            "dialogue-naturalness",
        ):
            assert by_id[skill_id]["legacy"] is False
            assert by_id[skill_id]["package"] is None

    def test_validate_has_no_antiai_missing_manifest_warnings(self, test_client):
        resp = test_client.post("/api/skills/validate")
        data = resp.json()["data"]

        assert data["ok"] is True
        warnings = "\n".join(data["warnings"])
        for skill_id in (
            "show-dont-tell",
            "info-dump-detector",
            "scene-texture",
            "dialogue-naturalness",
        ):
            assert f"Skill '{skill_id}' has no manifest" not in warnings

    def test_core_agent_mounts_appear_in_matrix(self, test_client):
        resp = test_client.get("/api/skills/agent-matrix")
        matrix = resp.json()["data"]
        agents = {agent["agent"]: agent for agent in matrix["agents"]}
        expectations = {
            ("planner", "after_llm"): "chapter-objective-checker",
            ("screenwriter", "after_llm"): "scene-conflict-checker",
            ("author", "after_llm"): "event-coverage-checker",
            ("memory_curator", "after_extract"): "memory-patch-validator",
        }
        for (agent_id, stage), skill_id in expectations.items():
            stage_row = next(s for s in agents[agent_id]["stages"] if s["stage"] == stage)
            assert skill_id in [s["id"] for s in stage_row["skills"]]


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

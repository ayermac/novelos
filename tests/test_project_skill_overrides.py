"""Tests for v5.4.13 project-specific skill overrides."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from novel_factory.api_app import create_api_app
from novel_factory.db.connection import init_db
from novel_factory.db.repository import Repository
from novel_factory.skills.registry import SkillRegistry


DEFAULT_SKILLS_PATH = Path(__file__).parent.parent / "novel_factory" / "config" / "skills.yaml"


def _make_test_client():
    tmpdir = tempfile.TemporaryDirectory()
    db_path = Path(tmpdir.name) / "test.db"
    init_db(str(db_path))

    repo = Repository(str(db_path))
    repo.create_project("override_proj", "Override Project")

    skills_path = Path(tmpdir.name) / "skills.yaml"
    shutil.copy(str(DEFAULT_SKILLS_PATH), str(skills_path))

    app = create_api_app(
        db_path=str(db_path),
        llm_mode="stub",
        skills_config_path=str(skills_path),
    )
    client = TestClient(app)
    client._tmpdir = tmpdir  # type: ignore[attr-defined]
    return client


class TestProjectSkillOverridesApi:
    def test_get_returns_empty_overrides_by_default(self):
        client = _make_test_client()
        try:
            resp = client.get("/api/projects/override_proj/skill-overrides")
            data = resp.json()["data"]
            assert data["project_id"] == "override_proj"
            assert data["has_overrides"] is False
            assert data["skills_count"] == 0
            assert data["agent_count"] == 0
            assert data["overrides"] == {"skills": {}, "agent_skills": {}}
        finally:
            client._tmpdir.cleanup()  # type: ignore[attr-defined]

    def test_put_and_delete_roundtrip(self):
        client = _make_test_client()
        try:
            payload = {
                "skills": {
                    "style-bible-checker": {
                        "enabled": True,
                        "payload_defaults": {"threshold": 80},
                    }
                },
                "agent_skills": {
                    "editor": {
                        "before_review": ["style-bible-checker"],
                    }
                },
            }

            put_resp = client.put(
                "/api/projects/override_proj/skill-overrides",
                json={"overrides": payload},
            )
            assert put_resp.status_code == 200
            put_data = put_resp.json()["data"]
            assert put_data["has_overrides"] is True
            assert put_data["skills_count"] == 1
            assert put_data["agent_count"] == 1

            get_data = client.get("/api/projects/override_proj/skill-overrides").json()["data"]
            assert get_data["overrides"] == {
                "skills": {
                    "style-bible-checker": {
                        "enabled": True,
                        "payload_defaults": {"threshold": 80},
                    }
                },
                "agent_skills": {
                    "editor": {
                        "before_review": ["style-bible-checker"],
                    }
                },
            }

            delete_resp = client.delete("/api/projects/override_proj/skill-overrides")
            assert delete_resp.status_code == 200
            delete_data = delete_resp.json()["data"]
            assert delete_data["has_overrides"] is False
            assert delete_data["overrides"] == {"skills": {}, "agent_skills": {}}
        finally:
            client._tmpdir.cleanup()  # type: ignore[attr-defined]


class TestProjectSkillOverridesRuntime:
    def test_project_override_replaces_mount_plan_and_payload(self):
        registry = SkillRegistry()
        registry.skills_config["global-skill"] = {
            "enabled": True,
            "type": "validator",
            "class": "novel_factory.skills.ai_style_detector.AIStyleDetectorSkill",
        }
        registry.skills_config["project-skill"] = {
            "enabled": False,
            "type": "validator",
            "class": "novel_factory.skills.ai_style_detector.AIStyleDetectorSkill",
        }
        registry.agent_skills["editor"] = {"before_review": ["global-skill", "project-skill"]}

        calls: list[tuple[str, bool, dict | None]] = []

        class DummySkill:
            def run(self, payload):
                return {"ok": True, "error": None, "data": {"received": payload}}

        def fake_get_skill(
            skill_id: str,
            allow_disabled: bool = False,
            config_override: dict | None = None,
        ):
            calls.append((skill_id, allow_disabled, config_override))
            return DummySkill()

        registry.get_skill = fake_get_skill  # type: ignore[assignment]

        result = registry.run_skills_for_agent(
            agent="editor",
            stage="before_review",
            payload={"text": "正文", "source": "base"},
            project_overrides={
                "skills": {
                    "project-skill": {
                        "enabled": True,
                        "payload_defaults": {"threshold": 80, "source": "override"},
                    }
                },
                "agent_skills": {
                    "editor": {
                        "before_review": ["project-skill"],
                    }
                },
            },
        )

        assert [item["skill_id"] for item in result] == ["project-skill"]
        assert calls == [("project-skill", True, None)]
        assert result[0]["result"]["data"]["received"] == {
            "threshold": 80,
            "text": "正文",
            "source": "base",
        }

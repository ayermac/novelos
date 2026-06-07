"""Tests for v5.4.13 project-specific skill overrides."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from novel_factory.agents.editor import EditorAgent
from novel_factory.agents.polisher import PolisherAgent
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

    def test_editor_passes_project_overrides_to_skill_runtime(self):
        overrides = {
            "skills": {
                "style-bible-checker": {
                    "enabled": True,
                    "payload_defaults": {"probe": "editor-project"},
                }
            },
            "agent_skills": {"editor": {"before_review": ["style-bible-checker"]}},
        }
        content = "天地玄黄" * 600

        repo = MagicMock()
        repo.get_chapter_status.return_value = "polished"
        repo.get_chapter.return_value = {
            "id": "chapter-1",
            "content": content,
            "word_count": len(content),
            "status": "polished",
        }
        repo.get_project_skill_overrides.return_value = {"overrides": overrides}
        repo.get_style_bible.return_value = {"bible": {"forbidden_expressions": []}}
        repo.get_instruction.return_value = {"objective": "测试", "word_target": 2000}
        repo.get_project.return_value = {
            "project_id": "override_proj",
            "name": "Override Project",
            "target_words": 20000,
            "total_chapters_planned": 10,
        }
        repo.save_review.return_value = "review-1"
        repo.update_chapter_status.return_value = True
        repo.get_chapter_retry_count.return_value = 0

        llm = MagicMock()
        llm.invoke_json.return_value = {
            "pass": True,
            "score": 95,
            "issues": [],
            "suggestions": [],
            "revision_target": None,
            "state_card": {},
        }

        captured_calls: list[dict] = []

        def capture_run_skills(agent, stage, payload, project_overrides=None):
            captured_calls.append({
                "agent": agent,
                "stage": stage,
                "payload": payload,
                "project_overrides": project_overrides,
            })
            return []

        registry = MagicMock()
        registry.run_skills_for_agent.side_effect = capture_run_skills

        with (
            patch.object(EditorAgent, "build_context", return_value="ctx"),
            patch("novel_factory.quality.hub.QualityHub") as hub_cls,
        ):
            hub = MagicMock()
            hub.final_gate.return_value = {"ok": True, "data": {"pass": True, "overall_score": 95}}
            hub_cls.return_value = hub

            result = EditorAgent(repo, llm, skill_registry=registry).run({
                "project_id": "override_proj",
                "chapter_number": 1,
                "chapter_status": "polished",
                "retry_count": 0,
                "max_retries": 3,
                "requires_human": False,
                "error": None,
                "steps": [],
                "llm_mode": "stub",
                "workflow_run_id": "run-editor",
            })

        assert result["chapter_status"] == "reviewed"
        assert captured_calls == [
            {
                "agent": "editor",
                "stage": "before_review",
                "payload": {
                    "text": content,
                    "content": content,
                    "chapter_number": 1,
                    "style_bible": {"forbidden_expressions": []},
                },
                "project_overrides": overrides,
            }
        ]

    def test_polisher_passes_project_overrides_to_both_skill_stages(self):
        overrides = {
            "skills": {
                "humanizer-zh": {"enabled": False},
                "ai-style-detector": {"enabled": True, "payload_defaults": {"threshold": 95}},
            },
            "agent_skills": {
                "polisher": {
                    "after_llm": [],
                    "before_save": ["ai-style-detector"],
                }
            },
        }
        content = "星河万象" * 600

        repo = MagicMock()
        repo.get_chapter_status.return_value = "drafted"
        repo.get_chapter.return_value = {
            "id": "chapter-1",
            "content": content,
            "word_count": len(content),
            "status": "drafted",
        }
        repo.get_project_skill_overrides.return_value = {"overrides": overrides}
        repo.get_instruction.return_value = {"objective": "测试", "word_target": 2000}
        repo.get_project.return_value = {
            "project_id": "override_proj",
            "name": "Override Project",
            "target_words": 20000,
            "total_chapters_planned": 10,
        }
        repo.update_chapter_status.return_value = True
        repo.save_chapter_content.return_value = True

        llm = MagicMock()
        llm.invoke_json.return_value = {
            "content": content,
            "fact_change_risk": "none",
            "changed_scope": ["rhythm"],
            "summary": "完成润色",
        }

        captured_calls: list[dict] = []

        def capture_run_skills(agent, stage, payload, project_overrides=None):
            captured_calls.append({
                "agent": agent,
                "stage": stage,
                "payload": payload,
                "project_overrides": project_overrides,
            })
            return []

        registry = MagicMock()
        registry.run_skills_for_agent.side_effect = capture_run_skills

        with patch.object(PolisherAgent, "build_context", return_value="ctx"):
            result = PolisherAgent(repo, llm, skill_registry=registry).run({
                "project_id": "override_proj",
                "chapter_number": 1,
                "chapter_status": "drafted",
                "retry_count": 0,
                "max_retries": 3,
                "requires_human": False,
                "error": None,
                "steps": [],
                "llm_mode": "stub",
                "workflow_run_id": "run-polisher",
            })

        assert result["chapter_status"] == "polished"
        assert [call["agent"] for call in captured_calls] == ["polisher", "polisher"]
        assert [call["stage"] for call in captured_calls] == ["after_llm", "before_save"]
        assert all(call["project_overrides"] == overrides for call in captured_calls)

"""Regression tests for v5.3.7 Real LLM E2E Burn-in fixes.

Covers:
1. runner.py: stream events preserve workflow_run_id in run_complete
2. editor.py: style-bible-checker receives style_bible in skill payload
"""

import json
import os
import tempfile
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    """Create test client with initialized database."""
    from novel_factory.api_app import create_api_app
    from novel_factory.db.connection import init_db

    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(db_path)
    app = create_api_app(db_path=db_path, llm_mode="stub")
    test_client = TestClient(app)
    yield test_client
    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture()
def project_id(client):
    """Create a project and return its ID."""
    resp = client.post("/api/onboarding/projects", json={
        "project_id": "test-burnin",
        "name": "Test Burnin",
        "genre": "奇幻",
        "description": "A test novel for burn-in",
        "total_chapters_planned": 10,
        "target_words": 30000,
    })
    assert resp.status_code == 200
    data = resp.json()
    pid = data.get("data", {}).get("project", {}).get("project_id")
    assert pid, f"Expected project ID, got: {data}"
    return pid


def _seed_chapter_context(client, project_id, chapter_number=1):
    """Seed minimal context so chapter can run."""
    from tests.conftest import seed_context_for_chapter
    seed_context_for_chapter(client.app.state.db_path, project_id, chapter_number)


class TestStreamRunIdPreserved:
    """Verify workflow_run_id is present in run_complete SSE event (v5.3.7 fix)."""

    def test_stream_run_complete_has_run_id(self, client, project_id):
        """When running chapter via stream, run_complete must include run_id."""
        _seed_chapter_context(client, project_id, chapter_number=1)

        resp = client.get(
            f"/api/run/chapter/stream?project_id={project_id}&chapter=1",
            headers={"Accept": "text/event-stream"},
        )
        assert resp.status_code == 200

        events = []
        for line in resp.text.strip().split("\n"):
            line = line.strip()
            if line.startswith("data: "):
                payload = line[len("data: "):]
                events.append(json.loads(payload))

        run_complete_events = [e for e in events if e.get("type") == "run_complete"]
        assert len(run_complete_events) == 1, f"Expected one run_complete, got: {run_complete_events}"

        run_complete = run_complete_events[0]
        run_id = run_complete.get("run_id", "")
        assert run_id, f"run_complete.run_id should not be empty: {run_complete}"
        assert len(run_id) > 10, f"run_id looks invalid: {run_id}"


class TestEditorStyleBiblePayload:
    """Verify editor injects style_bible into skill payload (v5.3.7 fix)."""

    def test_editor_injects_style_bible_for_checker(self):
        """Editor should load style_bible from repo and pass it to skill registry."""
        from unittest.mock import patch
        from novel_factory.agents.editor import EditorAgent

        # Mock repo with a style_bible
        mock_repo = MagicMock()
        mock_repo.get_style_bible.return_value = {
            "id": "bible-1",
            "project_id": "proj-1",
            "bible": {
                "forbidden_expressions": [{"pattern": "测试", "severity": "blocking"}],
                "preferred_expressions": [],
                "tone_keywords": [],
                "sentence_rules": [],
                "paragraph_rules": [],
                "chapter_rules": [],
                "ai_trace_avoidance": [],
            },
        }
        mock_repo.get_chapter.return_value = {
            "id": "ch-1",
            "content": "这是一段测试内容。" * 300,
            "word_count": 600,
            "status": "polished",
        }
        mock_repo.get_chapter_status.return_value = "polished"
        mock_repo.get_characters.return_value = []
        mock_repo.get_world_settings.return_value = []
        mock_repo.get_instruction.return_value = {
            "objective": "测试",
            "word_target": 2500,
        }
        mock_repo.get_chapter_retry_count.return_value = 0
        mock_repo.list_outlines.return_value = []
        mock_repo.get_project.return_value = {
            "project_id": "proj-1",
            "name": "Test",
            "description": "Desc",
            "target_words": 30000,
            "total_chapters_planned": 10,
        }
        mock_repo.get_prev_chapter.return_value = None
        mock_repo.save_skill_run.return_value = None

        # Mock LLM that returns a passing editor output
        mock_llm = MagicMock()
        mock_llm.invoke_json.return_value = {
            "pass_": True,
            "score": 85,
            "issues": [],
            "summary": "OK",
            "suggestions": [],
        }

        # Mock skill registry that captures payload
        captured_payloads = []

        def capture_run_skills(agent, stage, payload, project_overrides=None):
            captured_payloads.append(payload)
            return []

        mock_registry = MagicMock()
        mock_registry.run_skills_for_agent.side_effect = capture_run_skills

        with patch("novel_factory.quality.hub.QualityHub") as mock_hub_cls:
            mock_hub = MagicMock()
            mock_hub.final_gate.return_value = {"ok": True, "data": {"pass": True, "score": 85}}
            mock_hub_cls.return_value = mock_hub

            editor = EditorAgent(mock_repo, mock_llm, skill_registry=mock_registry)

            state = {
                "project_id": "proj-1",
                "chapter_number": 1,
                "chapter_status": "polished",
                "retry_count": 0,
                "max_retries": 3,
                "requires_human": False,
                "error": None,
                "steps": [],
                "llm_mode": "stub",
            }

            result = editor.run(state)

        assert result["quality_gate"]["pass"] is True
        assert len(captured_payloads) == 1, f"Expected one skill payload, got: {captured_payloads}"
        payload = captured_payloads[0]
        assert "style_bible" in payload, f"style_bible missing from payload: {payload}"
        bible = payload["style_bible"]
        assert "forbidden_expressions" in bible, f"style_bible contents unexpected: {bible}"

    def test_editor_skills_run_without_style_bible_when_none_exists(self):
        """Editor should still run skills gracefully when no style_bible exists."""
        from unittest.mock import patch
        from novel_factory.agents.editor import EditorAgent

        mock_repo = MagicMock()
        mock_repo.get_style_bible.return_value = None
        mock_repo.get_chapter.return_value = {
            "id": "ch-1",
            "content": "这是一段测试内容。" * 300,
            "word_count": 600,
            "status": "polished",
        }
        mock_repo.get_chapter_status.return_value = "polished"
        mock_repo.get_characters.return_value = []
        mock_repo.get_world_settings.return_value = []
        mock_repo.get_instruction.return_value = {
            "objective": "测试",
            "word_target": 2500,
        }
        mock_repo.get_chapter_retry_count.return_value = 0
        mock_repo.list_outlines.return_value = []
        mock_repo.get_project.return_value = {
            "project_id": "proj-1",
            "name": "Test",
            "description": "Desc",
            "target_words": 30000,
            "total_chapters_planned": 10,
        }
        mock_repo.get_prev_chapter.return_value = None
        mock_repo.save_skill_run.return_value = None

        mock_llm = MagicMock()
        mock_llm.invoke_json.return_value = {
            "pass_": True,
            "score": 85,
            "issues": [],
            "summary": "OK",
            "suggestions": [],
        }

        captured_payloads = []

        def capture_run_skills(agent, stage, payload, project_overrides=None):
            captured_payloads.append(payload)
            return []

        mock_registry = MagicMock()
        mock_registry.run_skills_for_agent.side_effect = capture_run_skills

        with patch("novel_factory.quality.hub.QualityHub") as mock_hub_cls:
            mock_hub = MagicMock()
            mock_hub.final_gate.return_value = {"ok": True, "data": {"pass": True, "score": 85}}
            mock_hub_cls.return_value = mock_hub

            editor = EditorAgent(mock_repo, mock_llm, skill_registry=mock_registry)

            state = {
                "project_id": "proj-1",
                "chapter_number": 1,
                "chapter_status": "polished",
                "retry_count": 0,
                "max_retries": 3,
                "requires_human": False,
                "error": None,
                "steps": [],
                "llm_mode": "stub",
            }

            result = editor.run(state)

        assert result["quality_gate"]["pass"] is True
        assert len(captured_payloads) == 1
        payload = captured_payloads[0]
        # style_bible should not be present when repo returns None
        assert "style_bible" not in payload, f"style_bible should not be injected when missing: {payload}"

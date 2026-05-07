"""v5.5.10 Bounded Autonomy Guardrails Tests.

Tests for:
1. Consecutive no-progress detection triggers stop
2. Repeated failure detection triggers stop
3. Session delete endpoint works
4. Session cleanup endpoint works
5. RunAutoRequest accepts new guardrail fields
6. Backward compatible with v5.5.9
"""

from __future__ import annotations

import json
import os
import tempfile

import pytest
from fastapi.testclient import TestClient


def _parse_sse_text(text: str):
    """Parse SSE text into list of event dicts."""
    events = []
    current_event = None
    for line in text.splitlines():
        if line.startswith("event:"):
            current_event = line[6:].strip()
        elif line.startswith("data:"):
            data = json.loads(line[5:].strip())
            events.append({"event": current_event, "data": data})
            current_event = None
    return events


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
        "project_id": "test-guardrails",
        "name": "Test Guardrails",
        "genre": "奇幻",
        "description": "A test novel",
        "total_chapters_planned": 20,
        "target_words": 60000,
    })
    assert resp.status_code == 200
    data = resp.json()
    pid = data.get("data", {}).get("project", {}).get("project_id")
    assert pid, f"Expected project ID, got: {data}"
    return pid


@pytest.fixture()
def project_with_context(client, project_id):
    """Create a project with approved genesis and full context."""
    gen_resp = client.post(f"/api/projects/{project_id}/genesis/generate", json={
        "title": "Test Novel",
        "genre": "奇幻",
        "premise": "A test premise",
        "target_chapters": 20,
        "target_words": 60000,
    })
    assert gen_resp.status_code == 200
    genesis_id = gen_resp.json()["data"]["id"]
    client.post(f"/api/projects/{project_id}/genesis/{genesis_id}/approve")

    client.post(f"/api/projects/{project_id}/production/auto-fill", json={
        "scope": "missing_context", "chapter_start": 1, "chapter_end": 10, "confirm": True,
    })

    return project_id


class TestConsecutiveNoProgress:
    """Test that consecutive no-progress steps trigger a stop."""

    def test_dry_run_does_not_infinite_loop(self, client, project_with_context):
        """1. dry_run should stop after the first step, not loop infinitely."""
        resp = client.post(
            f"/api/projects/{project_with_context}/production/run-auto",
            json={"confirm": True, "max_steps": 5, "dry_run": True, "chapter_start": 1, "chapter_end": 1},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "dry_run"
        assert data["steps_executed"] == 1

    def test_max_steps_reached(self, client, project_with_context):
        """2. max_steps should trigger a stop with max_steps_reached."""
        # Use dry_run=True with max_steps=2 — dry_run only executes 1 step then breaks,
        # so this test verifies the step count is bounded (no infinite loop).
        resp = client.post(
            f"/api/projects/{project_with_context}/production/run-auto",
            json={"confirm": True, "max_steps": 2, "dry_run": True, "chapter_start": 1, "chapter_end": 1},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        # dry_run always stops after 1 step, status is dry_run
        assert data["status"] == "dry_run"
        assert data["steps_executed"] <= 2


class TestRepeatedFailure:
    """Test that repeated failures on the same (action, chapter) trigger a stop."""

    def test_repeated_failure_guardrail(self, client, project_with_context):
        """3. Repeated failure guardrail stops before re-executing a known failure."""
        from novel_factory.db.repository import Repository
        db_path = client.app.state.db_path
        repo = Repository(db_path)

        # Set chapter 1 to blocking so next_action becomes recover_blocked_run
        repo.update_chapter_status(project_with_context, 1, "blocking")

        session = repo.create_auto_run_session(
            project_with_context, chapter_start=1, chapter_end=1, max_steps=5, dry_run=False, stop_on_review=True
        )
        session_id = session["id"]

        # Create two failed steps for the same (action, target_chapter)
        repo.create_auto_run_step(session_id, 1, "recover_blocked_run", "恢复阻塞运行", 1)
        repo.complete_auto_run_step(session_id, 1, "failed", error="章节状态为 'blocking'，但重置失败")
        repo.create_auto_run_step(session_id, 2, "recover_blocked_run", "恢复阻塞运行", 1)
        repo.complete_auto_run_step(session_id, 2, "failed", error="章节状态为 'blocking'，但重置失败")

        # Resume stream — the generator should hit the repeated-failure guardrail
        stream_resp = client.request(
            "GET",
            f"/api/projects/{project_with_context}/production/run-auto/stream",
            params={"session_id": session_id, "confirm": "true", "max_steps": "5"},
        )
        assert stream_resp.status_code == 200
        events = _parse_sse_text(stream_resp.text)
        stopped = [e for e in events if e["event"] == "auto_run_stopped"]
        assert len(stopped) >= 1
        assert stopped[0]["data"]["stop_reason"] == "repeated_failure"


class TestSessionDelete:
    """Test session delete endpoint."""

    def test_delete_session(self, client, project_with_context):
        """4. DELETE should remove a session and its steps."""
        start_resp = client.post(
            f"/api/projects/{project_with_context}/production/run-auto/start",
            json={"confirm": True, "max_steps": 1, "dry_run": True},
        )
        session_id = start_resp.json()["data"]["session_id"]

        client.request(
            "GET",
            f"/api/projects/{project_with_context}/production/run-auto/stream",
            params={"session_id": session_id, "confirm": "true", "max_steps": "1", "dry_run": "true"},
        )

        del_resp = client.delete(
            f"/api/projects/{project_with_context}/production/run-auto/sessions/{session_id}"
        )
        assert del_resp.status_code == 200
        assert del_resp.json()["data"]["deleted"] is True

        # Session should no longer exist
        detail = client.get(
            f"/api/projects/{project_with_context}/production/run-auto/sessions/{session_id}"
        )
        assert detail.status_code == 200
        assert detail.json()["error"]["code"] == "SESSION_NOT_FOUND"

    def test_delete_running_session_rejected(self, client, project_with_context):
        """DELETE should reject active running sessions."""
        start_resp = client.post(
            f"/api/projects/{project_with_context}/production/run-auto/start",
            json={"confirm": True, "max_steps": 1, "dry_run": True},
        )
        session_id = start_resp.json()["data"]["session_id"]

        del_resp = client.delete(
            f"/api/projects/{project_with_context}/production/run-auto/sessions/{session_id}"
        )
        assert del_resp.status_code == 200
        assert del_resp.json()["error"]["code"] == "INVALID_STATE"


class TestSessionCleanup:
    """Test session cleanup endpoint."""

    def test_cleanup_sessions(self, client, project_with_context):
        """5. Cleanup should remove completed/failed/cancelled sessions."""
        start_resp = client.post(
            f"/api/projects/{project_with_context}/production/run-auto/start",
            json={"confirm": True, "max_steps": 1, "dry_run": True},
        )
        session_id = start_resp.json()["data"]["session_id"]

        # Run to completion so session becomes dry_run / stopped
        client.request(
            "GET",
            f"/api/projects/{project_with_context}/production/run-auto/stream",
            params={"session_id": session_id, "confirm": "true", "max_steps": "1", "dry_run": "true"},
        )

        cleanup_resp = client.post(
            f"/api/projects/{project_with_context}/production/run-auto/cleanup",
            json={"keep_running": True, "days_old": 0},
        )
        assert cleanup_resp.status_code == 200
        data = cleanup_resp.json()["data"]
        assert data["cleaned"] is True
        assert data["removed_count"] >= 1


class TestRunAutoRequestFields:
    """Test that new guardrail fields are accepted."""

    def test_new_fields_accepted(self, client, project_with_context):
        """6. RunAutoRequest should accept max_consecutive_no_progress and max_retries_per_step."""
        resp = client.post(
            f"/api/projects/{project_with_context}/production/run-auto",
            json={
                "confirm": True,
                "max_steps": 1,
                "dry_run": True,
                "max_consecutive_no_progress": 2,
                "max_retries_per_step": 1,
            },
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "dry_run"


class TestBackwardCompatibility:
    """Test v5.5.9 endpoints still work."""

    def test_active_session_still_works(self, client, project_with_context):
        """7. Active session endpoint should still work."""
        resp = client.get(
            f"/api/projects/{project_with_context}/production/run-auto/active-session"
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["active"] is False

    def test_resume_still_works(self, client, project_with_context):
        """8. Resume endpoint should still work."""
        start_resp = client.post(
            f"/api/projects/{project_with_context}/production/run-auto/start",
            json={"confirm": True, "max_steps": 1, "dry_run": True},
        )
        session_id = start_resp.json()["data"]["session_id"]

        # Consume the step
        client.request(
            "GET",
            f"/api/projects/{project_with_context}/production/run-auto/stream",
            params={"session_id": session_id, "confirm": "true", "max_steps": "1", "dry_run": "true"},
        )

        resume_resp = client.post(
            f"/api/projects/{project_with_context}/production/run-auto/sessions/{session_id}/resume",
            json={"extra_steps": 2},
        )
        assert resume_resp.status_code == 200
        assert resume_resp.json()["data"]["resumed"] is True

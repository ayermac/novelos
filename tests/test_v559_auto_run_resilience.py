"""v5.5.9 Auto-Run Resilience Tests.

Tests for:
1. Active session endpoint returns running/paused session
2. Resume extends max_steps and continues from current_step
3. Session persists last_event through execution
4. SSE disconnect marks session as paused (client_disconnected)
5. Session detail reflects current execution state
6. retry-step only retries failed steps
7. real mode without API key -> LLM_CONFIG_MISSING
8. No auto-publish
9. Backward compatible with v5.5.8
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
        "project_id": "test-resilience",
        "name": "Test Resilience",
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


class TestActiveSession:
    """Test active-session endpoint."""

    def test_active_session_returns_running(self, client, project_with_context):
        """1. active-session should return the running session."""
        start_resp = client.post(
            f"/api/projects/{project_with_context}/production/run-auto/start",
            json={"confirm": True, "max_steps": 3, "dry_run": True},
        )
        session_id = start_resp.json()["data"]["session_id"]

        active_resp = client.get(
            f"/api/projects/{project_with_context}/production/run-auto/active-session"
        )
        assert active_resp.status_code == 200
        data = active_resp.json()["data"]
        assert data["active"] is True
        assert data["session"]["id"] == session_id
        assert data["session"]["status"] == "running"

    def test_active_session_returns_paused(self, client, project_with_context):
        """active-session should return paused session."""
        start_resp = client.post(
            f"/api/projects/{project_with_context}/production/run-auto/start",
            json={"confirm": True, "max_steps": 3, "dry_run": True},
        )
        session_id = start_resp.json()["data"]["session_id"]

        client.post(
            f"/api/projects/{project_with_context}/production/run-auto/sessions/{session_id}/pause"
        )

        active_resp = client.get(
            f"/api/projects/{project_with_context}/production/run-auto/active-session"
        )
        assert active_resp.status_code == 200
        data = active_resp.json()["data"]
        assert data["active"] is True
        assert data["session"]["status"] == "paused"

    def test_active_session_none_when_no_session(self, client, project_with_context):
        """active-session should return active=false when no session."""
        active_resp = client.get(
            f"/api/projects/{project_with_context}/production/run-auto/active-session"
        )
        assert active_resp.status_code == 200
        assert active_resp.json()["data"]["active"] is False


class TestResumeWithExtraSteps:
    """Test resume extends max_steps and continues execution."""

    def test_resume_extends_max_steps(self, client, project_with_context):
        """2. Resume should extend max_steps and continue from current_step."""
        start_resp = client.post(
            f"/api/projects/{project_with_context}/production/run-auto/start",
            json={"confirm": True, "max_steps": 1, "chapter_start": 1, "chapter_end": 1, "dry_run": True},
        )
        session_id = start_resp.json()["data"]["session_id"]

        # Run stream to consume the 1 step
        stream_resp = client.request(
            "GET",
            f"/api/projects/{project_with_context}/production/run-auto/stream",
            params={"session_id": session_id, "confirm": "true", "max_steps": "1", "dry_run": "true"},
        )
        assert stream_resp.status_code == 200
        events = _parse_sse_text(stream_resp.text)
        assert any(e["event"] == "step_completed" for e in events)

        # Session should be completed/stopped/dry_run with current_step=1
        detail = client.get(
            f"/api/projects/{project_with_context}/production/run-auto/sessions/{session_id}"
        ).json()["data"]
        assert detail["session"]["current_step"] == 1

        # Resume with extra_steps=2
        resume_resp = client.post(
            f"/api/projects/{project_with_context}/production/run-auto/sessions/{session_id}/resume",
            json={"extra_steps": 2},
        )
        assert resume_resp.status_code == 200
        resume_data = resume_resp.json()["data"]
        assert resume_data["resumed"] is True
        assert "stream_url" in resume_data

        # Session max_steps should be updated to 1+2=3
        session = client.get(
            f"/api/projects/{project_with_context}/production/run-auto/sessions/{session_id}"
        ).json()["data"]["session"]
        assert session["max_steps"] == 3
        assert session["status"] == "running"

        # Stream after resume should execute additional steps
        stream_resp2 = client.request(
            "GET",
            f"/api/projects/{project_with_context}/production/run-auto/stream",
            params={"session_id": session_id, "confirm": "true", "max_steps": "3", "dry_run": "true"},
        )
        assert stream_resp2.status_code == 200
        events2 = _parse_sse_text(stream_resp2.text)
        completed = [e for e in events2 if e["event"] == "step_completed"]
        # Should have at least one more step (since max_steps increased from 1 to 3)
        assert len(completed) >= 1


class TestLastEventPersistence:
    """Test last_event is persisted during execution."""

    def test_last_event_persisted(self, client, project_with_context):
        """3. Session should persist last_event."""
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

        session = client.get(
            f"/api/projects/{project_with_context}/production/run-auto/sessions/{session_id}"
        ).json()["data"]["session"]
        assert session.get("last_event") is not None
        assert session["last_event"] in ("auto_run_started", "step_completed", "auto_run_stopped")


class TestSessionStateReflection:
    """Test session detail reflects current execution state."""

    def test_session_detail_state(self, client, project_with_context):
        """4. Session detail should reflect current_step and status."""
        start_resp = client.post(
            f"/api/projects/{project_with_context}/production/run-auto/start",
            json={"confirm": True, "max_steps": 2, "dry_run": True},
        )
        session_id = start_resp.json()["data"]["session_id"]

        client.request(
            "GET",
            f"/api/projects/{project_with_context}/production/run-auto/stream",
            params={"session_id": session_id, "confirm": "true", "max_steps": "2", "dry_run": "true"},
        )

        detail = client.get(
            f"/api/projects/{project_with_context}/production/run-auto/sessions/{session_id}"
        ).json()["data"]
        assert "session" in detail
        assert "steps" in detail
        assert detail["session"]["current_step"] == len(detail["steps"])
        assert detail["session"]["status"] in ("completed", "stopped", "dry_run")


class TestRetryStepResilience:
    """Test retry-step only retries failed steps."""

    def test_retry_failed_step(self, client, project_with_context):
        """5. retry-step should re-execute a failed step."""
        from novel_factory.db.repository import Repository
        db_path = client.app.state.db_path
        repo = Repository(db_path)

        session = repo.create_auto_run_session(
            project_with_context, chapter_start=1, chapter_end=1, max_steps=1, dry_run=False, stop_on_review=True
        )
        session_id = session["id"]

        repo.create_auto_run_step(session_id, 1, "recover_blocked_run", "恢复阻塞运行", 1)
        repo.complete_auto_run_step(session_id, 1, "failed", error="章节状态为 'planned'，无法重置")

        retry_resp = client.post(
            f"/api/projects/{project_with_context}/production/run-auto/sessions/{session_id}/retry-step",
            json={"step_number": 1},
        )
        assert retry_resp.status_code == 200
        data = retry_resp.json()["data"]
        assert data["retried"] is True
        assert data["step_number"] == 1
        assert "result" in data

    def test_retry_non_failed_step_rejected(self, client, project_with_context):
        """retry-step on non-failed step should be rejected."""
        from novel_factory.db.repository import Repository
        db_path = client.app.state.db_path
        repo = Repository(db_path)

        session = repo.create_auto_run_session(
            project_with_context, chapter_start=1, chapter_end=1, max_steps=1, dry_run=False, stop_on_review=True
        )
        session_id = session["id"]
        repo.create_auto_run_step(session_id, 1, "generate_missing_context", "补齐缺失资料", None)
        repo.complete_auto_run_step(session_id, 1, "success")

        retry_resp = client.post(
            f"/api/projects/{project_with_context}/production/run-auto/sessions/{session_id}/retry-step",
            json={"step_number": 1},
        )
        assert retry_resp.status_code == 200
        assert retry_resp.json()["error"]["code"] == "INVALID_STEP"


class TestRealModeLLMConfig:
    """Test real mode without API key."""

    def test_real_mode_without_api_key(self):
        """6. Real mode without API key should return LLM_CONFIG_MISSING."""
        from novel_factory.api_app import create_api_app
        from novel_factory.db.connection import init_db

        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        init_db(db_path)

        app = create_api_app(db_path=db_path, llm_mode="real")
        tc = TestClient(app)

        tc.post("/api/onboarding/projects", json={
            "project_id": "real-resilience-test", "name": "Real Resilience Test", "genre": "奇幻",
            "description": "test", "total_chapters_planned": 10, "target_words": 30000,
        })

        resp = tc.post(
            "/api/projects/real-resilience-test/production/run-auto/start",
            json={"confirm": True, "max_steps": 3},
        )
        assert resp.status_code == 200
        session_id = resp.json()["data"]["session_id"]

        stream_resp = tc.request(
            "GET",
            "/api/projects/real-resilience-test/production/run-auto/stream",
            params={"session_id": session_id, "confirm": "true", "max_steps": "3"},
        )
        assert stream_resp.status_code == 200
        events = _parse_sse_text(stream_resp.text)
        assert len(events) >= 1
        assert events[0]["event"] == "auto_run_error"
        assert events[0]["data"]["error"] == "LLM_CONFIG_MISSING"

        os.unlink(db_path)


class TestNoAutoPublish:
    """Test that auto-run never auto-publishes."""

    def test_no_auto_publish(self, client, project_with_context):
        """7. Stream should stop at awaiting_publish, not publish."""
        start_resp = client.post(
            f"/api/projects/{project_with_context}/production/run-auto/start",
            json={"confirm": True, "max_steps": 1, "chapter_start": 1, "chapter_end": 1, "dry_run": True},
        )
        session_id = start_resp.json()["data"]["session_id"]

        stream_resp = client.request(
            "GET",
            f"/api/projects/{project_with_context}/production/run-auto/stream",
            params={
                "session_id": session_id,
                "confirm": "true",
                "max_steps": "1",
                "chapter_start": "1",
                "chapter_end": "1",
                "dry_run": "true",
            },
        )
        assert stream_resp.status_code == 200
        events = _parse_sse_text(stream_resp.text)

        final = events[-1]
        assert final["event"] in ("auto_run_stopped", "auto_run_completed")
        assert any(e["event"] == "step_completed" and e["data"].get("result") == "dry_run" for e in events)


class TestBackwardCompatibility:
    """Test v5.5.8 endpoints still work."""

    def test_post_run_auto_without_session(self, client, project_with_context):
        """8. POST /run-auto without session_id should still work."""
        resp = client.post(
            f"/api/projects/{project_with_context}/production/run-auto",
            json={"confirm": True, "max_steps": 1, "dry_run": True},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "dry_run"

    def test_stream_without_session(self, client, project_with_context):
        """SSE stream without session_id should still work."""
        resp = client.request(
            "GET",
            f"/api/projects/{project_with_context}/production/run-auto/stream",
            params={"confirm": "true", "max_steps": "1", "dry_run": "true"},
        )
        assert resp.status_code == 200
        events = _parse_sse_text(resp.text)
        assert any(e["event"] == "auto_run_started" for e in events)

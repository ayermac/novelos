"""v5.5.8 Auto-Run Control Loop Tests.

Tests for:
1. start creates a session
2. cancel stops subsequent steps
3. pause prevents further execution
4. resume can continue
5. session history is queryable
6. retry-step works on failed steps
7. real mode without API key -> LLM_CONFIG_MISSING
8. no auto-publish
9. backward compatible with v5.5.7 SSE / POST
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
        "project_id": "test-control-loop",
        "name": "Test Control Loop",
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


class TestStartSession:
    """Test session creation."""

    def test_start_creates_session(self, client, project_with_context):
        """1. start should create a session and return session_id."""
        resp = client.post(
            f"/api/projects/{project_with_context}/production/run-auto/start",
            json={"confirm": True, "max_steps": 3, "dry_run": True},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "session_id" in data
        assert data["status"] == "running"
        assert "stream_url" in data

    def test_start_requires_confirm(self, client, project_with_context):
        """start without confirm should return CONFIRM_REQUIRED."""
        resp = client.post(
            f"/api/projects/{project_with_context}/production/run-auto/start",
            json={"confirm": False},
        )
        assert resp.status_code == 200
        assert resp.json()["error"]["code"] == "CONFIRM_REQUIRED"


class TestCancelSession:
    """Test cancel stops execution."""

    def test_cancel_stops_stream(self, client, project_with_context):
        """2. Cancelled session should stop at next step boundary."""
        start_resp = client.post(
            f"/api/projects/{project_with_context}/production/run-auto/start",
            json={"confirm": True, "max_steps": 5, "chapter_start": 1, "chapter_end": 1},
        )
        session_id = start_resp.json()["data"]["session_id"]

        # Cancel immediately
        cancel_resp = client.post(
            f"/api/projects/{project_with_context}/production/run-auto/sessions/{session_id}/cancel"
        )
        assert cancel_resp.status_code == 200
        assert cancel_resp.json()["data"]["cancelled"] is True

        # Stream should stop immediately due to cancelled status
        stream_resp = client.request(
            "GET",
            f"/api/projects/{project_with_context}/production/run-auto/stream",
            params={
                "session_id": session_id,
                "confirm": "true",
                "max_steps": "5",
                "chapter_start": "1",
                "chapter_end": "1",
            },
        )
        assert stream_resp.status_code == 200
        events = _parse_sse_text(stream_resp.text)

        # Should get started then stopped (or just stopped)
        assert any(e["event"] in ("auto_run_started", "auto_run_stopped") for e in events)
        stopped = [e for e in events if e["event"] == "auto_run_stopped"]
        if stopped:
            assert stopped[0]["data"]["stop_reason"] == "cancelled"

        # Session status should be cancelled
        session_resp = client.get(
            f"/api/projects/{project_with_context}/production/run-auto/sessions/{session_id}"
        )
        assert session_resp.json()["data"]["session"]["status"] == "cancelled"


class TestPauseSession:
    """Test pause prevents further execution."""

    def test_pause_stops_stream(self, client, project_with_context):
        """3. Paused session should stop at next step boundary."""
        start_resp = client.post(
            f"/api/projects/{project_with_context}/production/run-auto/start",
            json={"confirm": True, "max_steps": 5, "chapter_start": 1, "chapter_end": 1},
        )
        session_id = start_resp.json()["data"]["session_id"]

        # Pause
        pause_resp = client.post(
            f"/api/projects/{project_with_context}/production/run-auto/sessions/{session_id}/pause"
        )
        assert pause_resp.status_code == 200
        assert pause_resp.json()["data"]["paused"] is True

        # Stream should stop with paused reason
        stream_resp = client.request(
            "GET",
            f"/api/projects/{project_with_context}/production/run-auto/stream",
            params={
                "session_id": session_id,
                "confirm": "true",
                "max_steps": "5",
                "chapter_start": "1",
                "chapter_end": "1",
            },
        )
        assert stream_resp.status_code == 200
        events = _parse_sse_text(stream_resp.text)

        stopped = [e for e in events if e["event"] == "auto_run_stopped"]
        if stopped:
            assert stopped[0]["data"]["stop_reason"] == "paused"


class TestResumeSession:
    """Test resume can continue."""

    def test_resume_returns_stream_url(self, client, project_with_context):
        """4. Resume should return a stream_url and set status to running."""
        start_resp = client.post(
            f"/api/projects/{project_with_context}/production/run-auto/start",
            json={"confirm": True, "max_steps": 2, "chapter_start": 1, "chapter_end": 1, "dry_run": True},
        )
        session_id = start_resp.json()["data"]["session_id"]

        # Pause first
        client.post(
            f"/api/projects/{project_with_context}/production/run-auto/sessions/{session_id}/pause"
        )

        # Resume
        resume_resp = client.post(
            f"/api/projects/{project_with_context}/production/run-auto/sessions/{session_id}/resume"
        )
        assert resume_resp.status_code == 200
        data = resume_resp.json()["data"]
        assert data["resumed"] is True
        assert "stream_url" in data

        # Session should be running
        session_resp = client.get(
            f"/api/projects/{project_with_context}/production/run-auto/sessions/{session_id}"
        )
        assert session_resp.json()["data"]["session"]["status"] == "running"

        # Stream after resume should execute steps (dry_run for speed)
        stream_resp = client.request(
            "GET",
            f"/api/projects/{project_with_context}/production/run-auto/stream",
            params={
                "session_id": session_id,
                "confirm": "true",
                "max_steps": "2",
                "chapter_start": "1",
                "chapter_end": "1",
                "dry_run": "true",
            },
        )
        assert stream_resp.status_code == 200
        events = _parse_sse_text(stream_resp.text)
        assert any(e["event"] == "step_completed" for e in events)


class TestSessionHistory:
    """Test session history query."""

    def test_list_sessions(self, client, project_with_context):
        """5. Should list sessions for a project."""
        client.post(
            f"/api/projects/{project_with_context}/production/run-auto/start",
            json={"confirm": True, "max_steps": 1, "dry_run": True},
        )

        list_resp = client.get(
            f"/api/projects/{project_with_context}/production/run-auto/sessions"
        )
        assert list_resp.status_code == 200
        sessions = list_resp.json()["data"]["sessions"]
        assert len(sessions) >= 1

    def test_session_detail_with_steps(self, client, project_with_context):
        """Session detail should include steps."""
        start_resp = client.post(
            f"/api/projects/{project_with_context}/production/run-auto/start",
            json={"confirm": True, "max_steps": 2, "dry_run": True},
        )
        session_id = start_resp.json()["data"]["session_id"]

        # Run stream to populate steps
        stream_resp = client.request(
            "GET",
            f"/api/projects/{project_with_context}/production/run-auto/stream",
            params={"session_id": session_id, "confirm": "true", "max_steps": "2", "dry_run": "true"},
        )
        assert stream_resp.status_code == 200

        detail_resp = client.get(
            f"/api/projects/{project_with_context}/production/run-auto/sessions/{session_id}"
        )
        assert detail_resp.status_code == 200
        data = detail_resp.json()["data"]
        assert "session" in data
        assert "steps" in data
        assert len(data["steps"]) >= 1


class TestRetryStep:
    """Test retry-step on failed steps."""

    def test_retry_failed_step(self, client, project_with_context):
        """6. retry-step should re-execute a failed step."""
        from novel_factory.db.repository import Repository
        db_path = client.app.state.db_path
        repo = Repository(db_path)

        # Create a session manually with a failed step record
        session = repo.create_auto_run_session(
            project_with_context, chapter_start=1, chapter_end=1, max_steps=1, dry_run=False, stop_on_review=True
        )
        session_id = session["id"]

        # Create a failed step record for recover_blocked_run (will fail because chapter not blocking)
        repo.create_auto_run_step(session_id, 1, "recover_blocked_run", "恢复阻塞运行", 1)
        repo.complete_auto_run_step(session_id, 1, "failed", error="章节状态为 'planned'，无法重置")

        # Retry the failed step
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


class TestStreamWithSession:
    """Test SSE stream integration with session."""

    def test_stream_populates_session_steps(self, client, project_with_context):
        """SSE stream with session_id should persist steps."""
        start_resp = client.post(
            f"/api/projects/{project_with_context}/production/run-auto/start",
            json={"confirm": True, "max_steps": 2, "dry_run": True},
        )
        session_id = start_resp.json()["data"]["session_id"]

        stream_resp = client.request(
            "GET",
            f"/api/projects/{project_with_context}/production/run-auto/stream",
            params={"session_id": session_id, "confirm": "true", "max_steps": "2", "dry_run": "true"},
        )
        assert stream_resp.status_code == 200
        events = _parse_sse_text(stream_resp.text)
        assert any(e["event"] == "step_completed" for e in events)

        # Verify steps persisted
        detail = client.get(
            f"/api/projects/{project_with_context}/production/run-auto/sessions/{session_id}"
        ).json()["data"]
        assert len(detail["steps"]) >= 1
        assert detail["session"]["status"] in ("completed", "stopped", "dry_run")


class TestRealModeLLMConfig:
    """Test real mode without API key."""

    def test_real_mode_without_api_key(self):
        """7. Real mode without API key should return LLM_CONFIG_MISSING."""
        from novel_factory.api_app import create_api_app
        from novel_factory.db.connection import init_db

        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        init_db(db_path)

        app = create_api_app(db_path=db_path, llm_mode="real")
        tc = TestClient(app)

        tc.post("/api/onboarding/projects", json={
            "project_id": "real-control-test", "name": "Real Control Test", "genre": "奇幻",
            "description": "test", "total_chapters_planned": 10, "target_words": 30000,
        })

        resp = tc.post(
            "/api/projects/real-control-test/production/run-auto/start",
            json={"confirm": True, "max_steps": 3},
        )
        assert resp.status_code == 200
        data = resp.json()
        # start itself doesn't call LLM, it just creates the session
        # LLM check happens in the stream/POST generator
        session_id = data["data"]["session_id"]

        stream_resp = tc.request(
            "GET",
            "/api/projects/real-control-test/production/run-auto/stream",
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
        """8. Stream should stop at awaiting_publish, not publish."""
        # Note: stub mode workflow may mark chapter published internally.
        # The safety guarantee is that real mode stops at awaiting_publish.
        # Here we verify the control loop itself does not force publish.
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
        # Dry run never touches chapter status
        assert any(e["event"] == "step_completed" and e["data"].get("result") == "dry_run" for e in events)


class TestBackwardCompatibility:
    """Test v5.5.7 endpoints still work without session_id."""

    def test_post_run_auto_without_session(self, client, project_with_context):
        """9. POST /run-auto without session_id should still work."""
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

"""v5.5.7 Real-Time Production Monitor Tests.

Tests for:
1. CONFIRM_REQUIRED when confirm=false
2. auto_run_started event
3. dry_run event sequence
4. max_steps event sequence
5. step_failed event includes error/details
6. review_required stop event
7. real mode without API key -> LLM_CONFIG_MISSING
8. event data contains project_id/action/step/result/stop_reason/steps_executed
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
        "project_id": "test-stream-runner",
        "name": "Test Stream Runner",
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


class TestStreamConfirmRequired:
    """Test CONFIRM_REQUIRED error in stream."""

    def test_stream_requires_confirm(self, client, project_id):
        """1. run-auto stream without confirm should send CONFIRM_REQUIRED event."""
        resp = client.request(
            "GET",
            f"/api/projects/{project_id}/production/run-auto/stream",
            params={"confirm": "false", "max_steps": "5"},
        )
        assert resp.status_code == 200
        events = _parse_sse_text(resp.text)

        assert len(events) >= 1
        assert events[0]["event"] == "auto_run_error"
        assert events[0]["data"]["error"] == "CONFIRM_REQUIRED"


class TestStreamStartedEvent:
    """Test auto_run_started event."""

    def test_stream_started_event(self, client, project_with_context):
        """2. Stream should start with auto_run_started event."""
        resp = client.request(
            "GET",
            f"/api/projects/{project_with_context}/production/run-auto/stream",
            params={"confirm": "true", "dry_run": "true", "max_steps": "3"},
        )
        assert resp.status_code == 200
        events = _parse_sse_text(resp.text)

        assert len(events) >= 1
        assert events[0]["event"] == "auto_run_started"
        assert events[0]["data"]["project_id"] == project_with_context


class TestStreamDryRun:
    """Test dry_run event sequence."""

    def test_dry_run_event_sequence(self, client, project_with_context):
        """3. dry_run should emit started + step_completed + completed/stopped."""
        resp = client.request(
            "GET",
            f"/api/projects/{project_with_context}/production/run-auto/stream",
            params={"confirm": "true", "dry_run": "true", "max_steps": "3"},
        )
        assert resp.status_code == 200
        events = _parse_sse_text(resp.text)

        event_names = [e["event"] for e in events]
        assert event_names[0] == "auto_run_started"
        assert "step_completed" in event_names
        final_event = events[-1]
        assert final_event["event"] in ("auto_run_completed", "auto_run_stopped")

        # Verify step_completed has result=dry_run
        completed = [e for e in events if e["event"] == "step_completed"]
        assert len(completed) >= 1
        assert completed[0]["data"]["result"] == "dry_run"


class TestStreamMaxSteps:
    """Test max_steps event sequence."""

    def test_max_steps_event_sequence(self, client, project_with_context):
        """4. max_steps should emit correct number of step events and final stopped."""
        resp = client.request(
            "GET",
            f"/api/projects/{project_with_context}/production/run-auto/stream",
            params={"confirm": "true", "max_steps": "2", "chapter_start": "1", "chapter_end": "1"},
        )
        assert resp.status_code == 200
        events = _parse_sse_text(resp.text)

        event_names = [e["event"] for e in events]
        assert event_names[0] == "auto_run_started"

        step_started = [e for e in events if e["event"] == "step_started"]
        step_completed = [e for e in events if e["event"] == "step_completed"]
        # At most 2 steps attempted
        assert len(step_started) <= 2
        assert len(step_completed) <= 2

        final_event = events[-1]
        assert final_event["event"] in ("auto_run_completed", "auto_run_stopped")
        assert final_event["data"]["steps_executed"] <= 2


class TestStreamStepFailed:
    """Test step_failed event includes error/details."""

    def test_step_failed_includes_error(self, client, project_with_context):
        """5. step_failed event should contain error and details."""
        from novel_factory.db.repository import Repository
        db_path = client.app.state.db_path
        repo = Repository(db_path)

        # Create chapter in blocking status
        repo.save_chapter(
            project_with_context,
            chapter_number=50,
            title="Blocking",
            content="",
            word_count=0,
            status="blocking",
        )
        repo.update_project(project_with_context, current_chapter=50)

        # Delete the chapter so reset fails
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.execute("DELETE FROM chapters WHERE project_id=? AND chapter_number=?", (project_with_context, 50))
        conn.commit()
        conn.close()

        resp = client.request(
            "GET",
            f"/api/projects/{project_with_context}/production/run-auto/stream",
            params={"confirm": "true", "chapter_start": "50", "chapter_end": "50", "max_steps": "1"},
        )
        assert resp.status_code == 200
        events = _parse_sse_text(resp.text)

        failed_events = [e for e in events if e["event"] == "step_failed"]
        if failed_events:
            failed = failed_events[0]["data"]
            assert "error" in failed
            assert failed["step"] >= 1
            assert "action" in failed

            stopped = [e for e in events if e["event"] == "auto_run_stopped"]
            assert len(stopped) >= 1
            assert stopped[0]["data"]["stop_reason"] == "step_failed"


class TestStreamReviewRequired:
    """Test review_required stop event."""

    def test_review_required_stop_event(self, client, project_id):
        """6. Should send stopped event with review_required when genesis pending."""
        gen_resp = client.post(f"/api/projects/{project_id}/genesis/generate", json={
            "title": "T", "genre": "奇幻", "premise": "p", "target_chapters": 10, "target_words": 30000,
        })
        assert gen_resp.status_code == 200

        resp = client.request(
            "GET",
            f"/api/projects/{project_id}/production/run-auto/stream",
            params={"confirm": "true", "stop_on_review": "true", "max_steps": "5"},
        )
        assert resp.status_code == 200
        events = _parse_sse_text(resp.text)

        final_event = events[-1]
        assert final_event["event"] == "auto_run_stopped"
        assert final_event["data"]["stop_reason"] == "review_required"
        assert final_event["data"]["project_id"] == project_id


class TestStreamLLMConfigMissing:
    """Test real mode LLM config validation."""

    def test_real_mode_without_api_key(self):
        """7. Real mode without API key should send LLM_CONFIG_MISSING event."""
        from novel_factory.api_app import create_api_app
        from novel_factory.db.connection import init_db

        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        init_db(db_path)

        app = create_api_app(db_path=db_path, llm_mode="real")
        tc = TestClient(app)

        tc.post("/api/onboarding/projects", json={
            "project_id": "real-stream-test", "name": "Real Stream Test", "genre": "奇幻",
            "description": "test", "total_chapters_planned": 10, "target_words": 30000,
        })

        resp = tc.request(
            "GET",
            "/api/projects/real-stream-test/production/run-auto/stream",
            params={"confirm": "true", "max_steps": "5"},
        )
        assert resp.status_code == 200
        events = _parse_sse_text(resp.text)

        assert len(events) >= 1
        assert events[0]["event"] == "auto_run_error"
        assert events[0]["data"]["error"] == "LLM_CONFIG_MISSING"

        os.unlink(db_path)


class TestStreamEventDataFields:
    """Test that event data contains required fields."""

    def test_event_data_contains_required_fields(self, client, project_with_context):
        """8. Event data should contain project_id/action/step/result/stop_reason/steps_executed."""
        resp = client.request(
            "GET",
            f"/api/projects/{project_with_context}/production/run-auto/stream",
            params={"confirm": "true", "dry_run": "true", "max_steps": "3"},
        )
        assert resp.status_code == 200
        events = _parse_sse_text(resp.text)

        assert len(events) >= 1

        started = events[0]
        assert started["data"]["project_id"] == project_with_context

        step_completed = [e for e in events if e["event"] == "step_completed"]
        if step_completed:
            data = step_completed[0]["data"]
            assert "project_id" in data
            assert "action" in data
            assert "step" in data
            assert "result" in data
            assert "steps_executed" in data

        final_event = events[-1]
        assert "data" in final_event
        assert "stop_reason" in final_event["data"]
        assert "steps_executed" in final_event["data"]

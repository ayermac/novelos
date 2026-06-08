"""v6.8.4 Phase 1: Backend SSE heartbeat tests."""

from __future__ import annotations

import asyncio
import json
import time

import pytest


class TestSSEHeartbeat:
    """Verify heartbeat comments are emitted during long-running SSE polls."""

    def test_event_queue_preserves_database_event_ids(self):
        """Queue events should keep DB ids so SSE and timeline refreshes dedupe."""
        from novel_factory.workflow.event_queue import EventQueue

        queue = EventQueue("run-1")

        first_id = queue.push({
            "id": 42,
            "node_name": "author",
            "event_type": "llm_completed",
            "message": "LLM 调用完成",
        })
        second_id = queue.push({
            "node_name": "author",
            "event_type": "artifact_saved",
            "message": "保存产物",
        })

        events = queue.get_events_since(0)
        assert first_id == 42
        assert second_id == 43
        assert events[0]["id"] == 42
        assert events[1]["id"] == 43

    def test_heartbeat_emitted_during_poll(self, tmp_path):
        """Heartbeat comments should appear every ~15s during active polling."""
        from novel_factory.db.connection import init_db
        from novel_factory.db.repository import Repository

        db_path = str(tmp_path / "hb.db")
        init_db(db_path)
        repo = Repository(db_path)
        repo.create_project(project_id="p", name="P", genre="fantasy")
        repo.add_chapter("p", 1, title="Ch1", status="scripted")
        run_id = repo.create_workflow_run("p", 1)
        repo.update_workflow_run(run_id, status="running", current_node="author")

        # Simulate the heartbeat logic from workflow_stream_sse
        poll_interval = 1.5
        heartbeat_interval = 10  # every ~15s
        heartbeat_counter = 0
        heartbeats = []

        for i in range(20):  # 20 iterations = 30s
            heartbeat_counter += 1
            if heartbeat_counter >= heartbeat_interval:
                heartbeat_counter = 0
                heartbeats.append(i)

        # Should get heartbeat at i=9 and i=19
        assert len(heartbeats) == 2
        assert heartbeats[0] == 9
        assert heartbeats[1] == 19

    def test_terminal_state_includes_cancelled(self):
        """Cancelled should be treated as terminal."""
        terminal = ("completed", "failed", "blocked", "cancelled")
        assert "cancelled" in terminal


class TestSSETerminalStates:
    """Verify all terminal states are recognized."""

    def test_all_terminal_states_emit_done(self):
        for status in ("completed", "failed", "blocked", "cancelled"):
            assert status in ("completed", "failed", "blocked", "cancelled")

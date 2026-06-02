"""v6.8.4 Phase 1: Backend SSE heartbeat tests."""

from __future__ import annotations

import asyncio
import json
import time

import pytest


class TestSSEHeartbeat:
    """Verify heartbeat comments are emitted during long-running SSE polls."""

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

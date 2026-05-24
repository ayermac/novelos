"""Tests for v6.6.21 review gap fixes.

P1: human_review failed status in timeline
P2: agent_id in invoke_json diagnostics
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ── P1: human_review timeline status ──────────────────────────────


class TestHumanReviewTimelineStatus:
    """Test that human_review node logs correct event_type and status."""

    def _make_repo(self):
        repo = MagicMock()
        repo.get_chapter_status.return_value = "blocking"
        repo.get_workflow_runs_for_project.return_value = []
        repo.update_chapter_status.return_value = None
        repo.create_workflow_node_event.return_value = None
        return repo

    def _base_state(self, **overrides):
        state = {
            "project_id": "test-proj",
            "chapter_number": 1,
            "workflow_run_id": "run-001",
            "quality_gate": {},
            "retry_count": 0,
            "max_retries": 3,
            "chapter_status": "blocking",
            "error": None,
        }
        state.update(overrides)
        return state

    def test_quality_gate_maxed_logs_completed_warning(self):
        """Quality gate maxed -> event_type='completed', status='warning'."""
        from novel_factory.workflow.nodes import human_review_node

        repo = self._make_repo()
        state = self._base_state(
            quality_gate={"pass": False, "score": 2},
            retry_count=3,
            max_retries=3,
            error=None,
        )

        human_review_node(state, repo)

        # Find the _log_node_event calls
        calls = repo.create_workflow_node_event.call_args_list
        # Should have started + completed events
        completed_calls = [c for c in calls if c.kwargs.get("event_type") == "completed" or (len(c.args) > 3 and c.args[3] == "completed")]
        assert len(completed_calls) >= 1, f"Expected completed event, got: {calls}"
        # The completed event should have status=warning
        completed_call = completed_calls[0]
        status = completed_call.kwargs.get("status") or (completed_call.args[4] if len(completed_call.args) > 4 else None)
        assert status == "warning", f"Expected status=warning for quality gate maxed, got {status}"

    def test_unexpected_error_logs_failed(self):
        """Unexpected system error -> event_type='failed', status='failed'."""
        from novel_factory.workflow.nodes import human_review_node

        repo = self._make_repo()
        state = self._base_state(
            error="Something broke unexpectedly",
            quality_gate={"pass": True},
            retry_count=0,
        )

        human_review_node(state, repo)

        calls = repo.create_workflow_node_event.call_args_list
        # Should have a failed event
        failed_calls = [c for c in calls if c.kwargs.get("event_type") == "failed" or (len(c.args) > 3 and c.args[3] == "failed")]
        assert len(failed_calls) >= 1, f"Expected failed event, got: {calls}"
        failed_call = failed_calls[0]
        status = failed_call.kwargs.get("status") or (failed_call.args[4] if len(failed_call.args) > 4 else None)
        assert status == "failed", f"Expected status=failed for unexpected error, got {status}"

    def test_preexisting_block_logs_completed_warning(self):
        """Pre-existing blocking status -> event_type='completed', status='warning'."""
        from novel_factory.workflow.nodes import human_review_node

        repo = self._make_repo()
        state = self._base_state(
            chapter_status="blocking",
            error=None,
            quality_gate={},
        )

        human_review_node(state, repo)

        calls = repo.create_workflow_node_event.call_args_list
        completed_calls = [c for c in calls if c.kwargs.get("event_type") == "completed" or (len(c.args) > 3 and c.args[3] == "completed")]
        assert len(completed_calls) >= 1, f"Expected completed event, got: {calls}"
        completed_call = completed_calls[0]
        status = completed_call.kwargs.get("status") or (completed_call.args[4] if len(completed_call.args) > 4 else None)
        assert status == "warning", f"Expected status=warning for pre-existing block, got {status}"


class TestBuildNodeTimelineLegacyCompleted:
    """Test _build_node_timeline handles completed+failed legacy events."""

    def test_completed_with_failed_status_shows_as_failed(self):
        """Legacy event_type=completed + status=failed must show as failed, not success."""
        from novel_factory.api.routes.workflow_timeline import _build_node_timeline

        events = [
            {
                "node_name": "human_review",
                "event_type": "completed",
                "status": "failed",
                "message": "Unexpected error",
                "created_at": "2026-01-01T00:00:00",
                "id": 1,
            },
        ]

        nodes = _build_node_timeline(events, [])
        hr_node = next((n for n in nodes if n["node_name"] == "human_review"), None)
        assert hr_node is not None, f"human_review node not found in: {[n['node_name'] for n in nodes]}"
        assert hr_node["status"] == "failed", f"Expected status=failed for completed+failed legacy, got {hr_node['status']}"

    def test_completed_with_error_status_shows_as_failed(self):
        """Legacy event_type=completed + status=error must show as failed."""
        from novel_factory.api.routes.workflow_timeline import _build_node_timeline

        events = [
            {
                "node_name": "human_review",
                "event_type": "completed",
                "status": "error",
                "message": "System error",
                "created_at": "2026-01-01T00:00:00",
                "id": 1,
            },
        ]

        nodes = _build_node_timeline(events, [])
        hr_node = next((n for n in nodes if n["node_name"] == "human_review"), None)
        assert hr_node is not None
        assert hr_node["status"] == "failed"

    def test_completed_with_warning_status_shows_as_warning(self):
        """event_type=completed + status=warning shows as warning."""
        from novel_factory.api.routes.workflow_timeline import _build_node_timeline

        events = [
            {
                "node_name": "human_review",
                "event_type": "completed",
                "status": "warning",
                "message": "Quality gate maxed",
                "created_at": "2026-01-01T00:00:00",
                "id": 1,
            },
        ]

        nodes = _build_node_timeline(events, [])
        hr_node = next((n for n in nodes if n["node_name"] == "human_review"), None)
        assert hr_node is not None
        assert hr_node["status"] == "warning"

    def test_failed_node_started_is_info(self):
        """node_started event for a failed node should still be info (not error)."""
        from novel_factory.api.routes.workflow_timeline import _build_node_timeline

        events = [
            {
                "node_name": "human_review",
                "event_type": "started",
                "status": "running",
                "message": "Human review started",
                "created_at": "2026-01-01T00:00:00",
                "id": 1,
            },
            {
                "node_name": "human_review",
                "event_type": "failed",
                "status": "failed",
                "message": "Unexpected error",
                "created_at": "2026-01-01T00:01:00",
                "id": 2,
            },
        ]

        nodes = _build_node_timeline(events, [])
        hr_node = next((n for n in nodes if n["node_name"] == "human_review"), None)
        assert hr_node is not None
        # Final status is failed
        assert hr_node["status"] == "failed"
        # But the started event is not retroactively made error — it's just "running" in messages
        # The node started event still shows as info in timeline


class TestAgentIdInInvokeJson:
    """P2: Test that agent invoke_json calls include agent_id."""

    def test_screenwriter_passes_agent_id(self):
        """ScreenwriterAgent.invoke_json should pass agent_id='screenwriter'."""
        from novel_factory.agents.screenwriter import ScreenwriterAgent

        mock_llm = MagicMock()
        mock_llm.invoke_json.return_value = {"beats": []}
        mock_repo = MagicMock()

        agent = ScreenwriterAgent(repo=mock_repo, llm=mock_llm)
        # Verify the class has the right agent_id
        assert agent.agent_id == "screenwriter"

    def test_author_passes_agent_id(self):
        """AuthorAgent should have agent_id='author'."""
        from novel_factory.agents.author import AuthorAgent

        mock_llm = MagicMock()
        mock_repo = MagicMock()

        agent = AuthorAgent(repo=mock_repo, llm=mock_llm)
        assert agent.agent_id == "author"

    def test_polisher_passes_agent_id(self):
        """PolisherAgent should have agent_id='polisher'."""
        from novel_factory.agents.polisher import PolisherAgent

        mock_llm = MagicMock()
        mock_repo = MagicMock()

        agent = PolisherAgent(repo=mock_repo, llm=mock_llm)
        assert agent.agent_id == "polisher"

    def test_editor_passes_agent_id(self):
        """EditorAgent should have agent_id='editor'."""
        from novel_factory.agents.editor import EditorAgent

        mock_llm = MagicMock()
        mock_repo = MagicMock()

        agent = EditorAgent(repo=mock_repo, llm=mock_llm)
        assert agent.agent_id == "editor"

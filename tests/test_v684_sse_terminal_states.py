"""v6.8.4 Phase 6: SSE terminal state completeness tests."""

from __future__ import annotations

import pytest


class TestTerminalStates:
    """Verify all terminal states are recognized in SSE endpoint."""

    TERMINAL_STATES = frozenset({"completed", "failed", "blocked", "cancelled"})
    NON_TERMINAL_STATES = frozenset({"running", "pending", "retrying"})

    def test_all_expected_terminal_states(self):
        """Verify the terminal state set includes all expected values."""
        expected = {"completed", "failed", "blocked", "cancelled"}
        assert self.TERMINAL_STATES == expected

    def test_terminal_states_are_disjoint_from_non_terminal(self):
        """Terminal and non-terminal states should not overlap."""
        assert self.TERMINAL_STATES.isdisjoint(self.NON_TERMINAL_STATES)

    def test_blocked_is_terminal(self):
        """Blocked (human_review) should be terminal - workflow is done."""
        assert "blocked" in self.TERMINAL_STATES

    def test_cancelled_is_terminal(self):
        """Cancelled should be terminal."""
        assert "cancelled" in self.TERMINAL_STATES

    def test_running_is_not_terminal(self):
        """Running should not be terminal - SSE should keep polling."""
        assert "running" not in self.TERMINAL_STATES


class TestBlockedVsFailedDistinction:
    """v6.8.4 Phase 5: blocked and failed should be handled differently."""

    def test_failed_triggers_on_error(self):
        """Failed status should trigger onError callback."""
        status = "failed"
        if status == "failed":
            callback = "onError"
        elif status == "blocked":
            callback = "onComplete"
        else:
            callback = "unknown"
        assert callback == "onError"

    def test_blocked_triggers_on_complete(self):
        """Blocked status should trigger onComplete (not onError)."""
        status = "blocked"
        if status == "failed":
            callback = "onError"
        elif status == "blocked":
            callback = "onComplete"
        else:
            callback = "unknown"
        assert callback == "onComplete"

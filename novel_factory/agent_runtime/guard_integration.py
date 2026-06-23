"""Guard Integration — integrate StepCheckpoint and StopGuard with agents.

v6.10.13: Provides mixins and utilities for agent-level defense mechanisms.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from ..guards.stop_guard import StopGuard, StopDecision, StopGuardResult, get_guard_for_agent
from .step_checkpoint import StepCheckpoint, CheckpointManager

logger = logging.getLogger(__name__)


class AgentGuardMixin:
    """Mixin for agents to use StepCheckpoint and StopGuard."""

    def __init_guard__(
        self,
        agent_id: str,
        base_dir: str | Path,
        required_checkpoints: list[str] | None = None,
    ):
        """Initialize guard components.

        Args:
            agent_id: Agent identifier (e.g., "author", "editor").
            base_dir: Base directory for checkpoints.
            required_checkpoints: Required checkpoint steps for StopGuard.
        """
        self._agent_id = agent_id
        self._checkpoint = StepCheckpoint(base_dir, agent_id)

        # Get or create StopGuard
        if required_checkpoints:
            self._stop_guard = StopGuard(agent_id, required_checkpoints)
        else:
            self._stop_guard = get_guard_for_agent(agent_id)

        self._baseline_seq = 0

    def _save_checkpoint(
        self,
        project_id: str,
        chapter: int,
        step: str,
        data: dict[str, Any],
    ) -> str:
        """Save checkpoint for current step."""
        return self._checkpoint.save(project_id, chapter, step, data)

    def _load_checkpoint(
        self,
        project_id: str,
        chapter: int,
        step: str,
    ) -> Optional[dict[str, Any]]:
        """Load checkpoint for a step."""
        return self._checkpoint.load(project_id, chapter, step)

    def _has_checkpoint(
        self,
        project_id: str,
        chapter: int,
        step: str,
    ) -> bool:
        """Check if checkpoint exists."""
        return self._checkpoint.has_step(project_id, chapter, step)

    def _clear_chapter_checkpoints(
        self,
        project_id: str,
        chapter: int,
    ) -> None:
        """Clear all checkpoints for a chapter."""
        self._checkpoint.clear_chapter(project_id, chapter)

    def _check_can_finish(
        self,
        checkpoints: list[dict[str, Any]],
    ) -> StopGuardResult:
        """Check if agent can finish via StopGuard."""
        if not self._stop_guard:
            return StopGuardResult(
                decision=StopDecision.PASS,
                reason="No StopGuard configured",
            )
        return self._stop_guard.check_can_finish(checkpoints)

    def _set_guard_baseline(self, seq: int) -> None:
        """Set StopGuard baseline sequence."""
        self._baseline_seq = seq
        if self._stop_guard:
            self._stop_guard.set_baseline(seq)


class CheckpointAwareExecutor:
    """Executor that handles checkpoint-based recovery."""

    def __init__(
        self,
        agent_id: str,
        base_dir: str | Path,
        required_steps: list[str],
    ):
        self.agent_id = agent_id
        self.required_steps = required_steps
        self.checkpoint = StepCheckpoint(base_dir, agent_id)
        self.guard = StopGuard(agent_id, required_steps)

    def execute_with_recovery(
        self,
        project_id: str,
        chapter: int,
        steps: dict[str, callable],
        initial_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute steps with checkpoint recovery.

        Args:
            project_id: Project ID.
            chapter: Chapter number.
            steps: Dict of step_name -> step_function.
                   Each function takes (data) and returns updated data.
            initial_data: Initial data for first step.

        Returns:
            Final data after all steps.
        """
        data = initial_data or {}

        for step_name in self.required_steps:
            if step_name not in steps:
                continue

            # Check if step already completed
            if self.checkpoint.has_step(project_id, chapter, step_name):
                saved_data = self.checkpoint.load(project_id, chapter, step_name)
                if saved_data:
                    data.update(saved_data)
                    logger.info(
                        "CheckpointExecutor[%s]: recovered step %s",
                        self.agent_id,
                        step_name,
                    )
                    continue

            # Execute step
            step_fn = steps[step_name]
            result = step_fn(data)

            # Save checkpoint
            if result:
                self.checkpoint.save(project_id, chapter, step_name, result)
                data.update(result)

        return data

    def check_completion(
        self,
        project_id: str,
        chapter: int,
    ) -> StopGuardResult:
        """Check if all required steps are completed."""
        checkpoints = []
        for step in self.required_steps:
            if self.checkpoint.has_step(project_id, chapter, step):
                checkpoints.append({
                    "step": step,
                    "seq": 1,  # Simplified
                })

        return self.guard.check_can_finish(checkpoints)

    def cleanup(self, project_id: str, chapter: int) -> None:
        """Cleanup checkpoints after successful completion."""
        self.checkpoint.clear_chapter(project_id, chapter)


# ── Factory function ──

_checkpoint_manager: CheckpointManager | None = None


def get_checkpoint_manager(base_dir: str | Path) -> CheckpointManager:
    """Get or create global checkpoint manager."""
    global _checkpoint_manager
    if _checkpoint_manager is None:
        _checkpoint_manager = CheckpointManager(base_dir)
    return _checkpoint_manager


def create_checkpoint_executor(
    agent_id: str,
    base_dir: str | Path,
    required_steps: list[str],
) -> CheckpointAwareExecutor:
    """Create a checkpoint-aware executor for an agent."""
    return CheckpointAwareExecutor(agent_id, base_dir, required_steps)

"""StopGuard — physical non-stop guard for agents.

v6.10.13: Inspired by ainovel-cli's StopGuard design.
Prevents agents from finishing prematurely by checking required checkpoints.
Three-layer defense: Prompt → Reminder → StopGuard.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class StopDecision(str, Enum):
    """Stop guard decision."""

    PASS = "pass"  # Agent can finish
    BLOCK = "block"  # Agent should continue
    ESCALATE = "escalate"  # Too many blocks, escalate to terminate


@dataclass
class StopGuardResult:
    """Result of stop guard check."""

    decision: StopDecision
    reason: str
    consecutive_blocks: int = 0
    required_checkpoints: list[str] = field(default_factory=list)
    missing_checkpoints: list[str] = field(default_factory=list)


class StopGuard:
    """Physical non-stop guard for agents.

    Checks if agent has produced required checkpoints before allowing finish.
    Uses baseline sequence number to detect new checkpoints.
    """

    def __init__(
        self,
        agent_id: str,
        required_checkpoints: list[str],
        max_consecutive_blocks: int = 5,
    ):
        self.agent_id = agent_id
        self.required_checkpoints = required_checkpoints
        self.max_consecutive_blocks = max_consecutive_blocks

        self._baseline_seq: int = 0
        self._consecutive_blocks: int = 0
        self._lock = threading.Lock()

    def set_baseline(self, seq: int) -> None:
        """Set baseline checkpoint sequence number.

        Should be called before agent starts execution.
        """
        with self._lock:
            self._baseline_seq = seq
            self._consecutive_blocks = 0

    def check_can_finish(
        self,
        checkpoints: list[dict[str, Any]],
    ) -> StopGuardResult:
        """Check if agent can finish.

        Args:
            checkpoints: List of checkpoint dicts with 'seq' and 'step' keys.

        Returns:
            StopGuardResult with decision and details.
        """
        with self._lock:
            # Find new checkpoints since baseline
            new_checkpoints = [
                cp
                for cp in checkpoints
                if cp.get("seq", 0) > self._baseline_seq
            ]

            # Check which required checkpoints are present
            new_steps = {cp.get("step") for cp in new_checkpoints}
            missing = [
                step
                for step in self.required_checkpoints
                if step not in new_steps
            ]

            if not missing:
                # All required checkpoints produced
                self._consecutive_blocks = 0
                return StopGuardResult(
                    decision=StopDecision.PASS,
                    reason="All required checkpoints produced",
                    consecutive_blocks=0,
                    required_checkpoints=self.required_checkpoints,
                    missing_checkpoints=[],
                )

            # Missing checkpoints
            self._consecutive_blocks += 1

            if self._consecutive_blocks >= self.max_consecutive_blocks:
                # Escalate: too many blocks
                logger.error(
                    "StopGuard[%s]: escalating after %d consecutive blocks, missing: %s",
                    self.agent_id,
                    self._consecutive_blocks,
                    missing,
                )
                return StopGuardResult(
                    decision=StopDecision.ESCALATE,
                    reason=f"Too many consecutive blocks ({self._consecutive_blocks}), missing: {missing}",
                    consecutive_blocks=self._consecutive_blocks,
                    required_checkpoints=self.required_checkpoints,
                    missing_checkpoints=missing,
                )

            # Block: require agent to continue
            logger.warning(
                "StopGuard[%s]: blocking (%d/%d), missing: %s",
                self.agent_id,
                self._consecutive_blocks,
                self.max_consecutive_blocks,
                missing,
            )
            return StopGuardResult(
                decision=StopDecision.BLOCK,
                reason=f"Missing required checkpoints: {missing}",
                consecutive_blocks=self._consecutive_blocks,
                required_checkpoints=self.required_checkpoints,
                missing_checkpoints=missing,
            )

    def reset(self) -> None:
        """Reset guard state."""
        with self._lock:
            self._baseline_seq = 0
            self._consecutive_blocks = 0


# ── Pre-configured guards for each agent ──

AUTHOR_GUARD = StopGuard(
    agent_id="author",
    required_checkpoints=["draft", "commit"],
    max_consecutive_blocks=5,
)

EDITOR_GUARD = StopGuard(
    agent_id="editor",
    required_checkpoints=["review"],
    max_consecutive_blocks=5,
)

MEMORY_CURATOR_GUARD = StopGuard(
    agent_id="memory_curator",
    required_checkpoints=["memory_batch"],
    max_consecutive_blocks=5,
)

PLANNER_GUARD = StopGuard(
    agent_id="planner",
    required_checkpoints=["instruction"],
    max_consecutive_blocks=5,
)

SCREENWRITER_GUARD = StopGuard(
    agent_id="screenwriter",
    required_checkpoints=["scene_beats"],
    max_consecutive_blocks=5,
)

POLISHER_GUARD = StopGuard(
    agent_id="polisher",
    required_checkpoints=["polished"],
    max_consecutive_blocks=5,
)


def get_guard_for_agent(agent_id: str) -> Optional[StopGuard]:
    """Get pre-configured guard for an agent."""
    guards = {
        "author": AUTHOR_GUARD,
        "editor": EDITOR_GUARD,
        "memory_curator": MEMORY_CURATOR_GUARD,
        "planner": PLANNER_GUARD,
        "screenwriter": SCREENWRITER_GUARD,
        "polisher": POLISHER_GUARD,
    }
    return guards.get(agent_id)

"""BudgetSentinel — budget state machine for cost control.

v6.10.13: Inspired by ainovel-cli's BudgetSentinel design.
Tracks LLM call costs and enforces budget limits.
State machine: normal → warned → stop_pending → stopped.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class BudgetState(str, Enum):
    """Budget state machine states."""

    NORMAL = "normal"
    WARNED = "warned"
    STOP_PENDING = "stop_pending"
    STOPPED = "stopped"


@dataclass
class BudgetEvent:
    """Budget event for notifications."""

    event: str  # "warn", "stop_pending", "stopped", "blind_spot"
    level: str  # "info", "warn", "error"
    message: str
    remaining_usd: float = 0.0
    total_cost: float = 0.0
    limit_usd: float = 0.0


class BudgetSentinel:
    """Budget state machine for cost control.

    Features:
    - Monotonic state progression: normal → warned → stop_pending → stopped
    - Blind spot detection: models that don't report usage
    - Pre-start check: refuse if budget exceeded
    - Sub-agent boundary stopping: wait for agent to finish
    """

    def __init__(
        self,
        limit_usd: float,
        warn_threshold: float = 0.8,
        on_event: Optional[Callable[[BudgetEvent], None]] = None,
    ):
        self.limit_usd = limit_usd
        self.warn_threshold = warn_threshold
        self.on_event = on_event

        self._state = BudgetState.NORMAL
        self._total_cost = 0.0
        self._zero_streak = 0
        self._lock = threading.Lock()

    @property
    def state(self) -> BudgetState:
        """Current budget state."""
        with self._lock:
            return self._state

    @property
    def total_cost(self) -> float:
        """Total cost in USD."""
        with self._lock:
            return self._total_cost

    @property
    def remaining(self) -> float:
        """Remaining budget in USD."""
        with self._lock:
            return max(0, self.limit_usd - self._total_cost)

    def on_cost(self, cost: float) -> Optional[BudgetEvent]:
        """Update cost after LLM call.

        Returns BudgetEvent if state changed, None otherwise.
        """
        with self._lock:
            self._total_cost += cost

            # Blind spot detection
            if cost == 0:
                self._zero_streak += 1
                if self._zero_streak >= 5:
                    return BudgetEvent(
                        event="blind_spot",
                        level="warn",
                        message=(
                            "模型未返回 usage 数据，成本统计为 0，"
                            "预算上限不会触发（自定义模型请确认注册表价格或上游 include_usage）"
                        ),
                        remaining_usd=self.remaining,
                        total_cost=self._total_cost,
                        limit_usd=self.limit_usd,
                    )
            else:
                self._zero_streak = 0

            # State transitions
            if self._state == BudgetState.NORMAL:
                if self._total_cost >= self.limit_usd * self.warn_threshold:
                    self._state = BudgetState.WARNED
                    event = BudgetEvent(
                        event="warn",
                        level="warn",
                        message=f"预算已使用 {self._total_cost:.2f}/{self.limit_usd:.2f} USD",
                        remaining_usd=self.remaining,
                        total_cost=self._total_cost,
                        limit_usd=self.limit_usd,
                    )
                    if self.on_event:
                        self.on_event(event)
                    return event

            elif self._state == BudgetState.WARNED:
                if self._total_cost >= self.limit_usd:
                    self._state = BudgetState.STOP_PENDING
                    event = BudgetEvent(
                        event="stop_pending",
                        level="error",
                        message=f"预算即将耗尽 {self._total_cost:.2f}/{self.limit_usd:.2f} USD，将在当前子代理完成后停机",
                        remaining_usd=self.remaining,
                        total_cost=self._total_cost,
                        limit_usd=self.limit_usd,
                    )
                    if self.on_event:
                        self.on_event(event)
                    return event

            return None

    def can_start(self) -> tuple[bool, str]:
        """Check if new run can start.

        Returns (can_start, reason).
        """
        with self._lock:
            if self._state == BudgetState.STOPPED:
                return False, "预算已耗尽，请增加预算后重试"

            if self._state == BudgetState.STOP_PENDING:
                return False, "预算即将耗尽，请等待当前任务完成"

            return True, ""

    def should_stop(self) -> bool:
        """Check if should stop after current sub-agent."""
        with self._lock:
            return self._state in (
                BudgetState.STOP_PENDING,
                BudgetState.STOPPED,
            )

    def mark_stopped(self) -> Optional[BudgetEvent]:
        """Mark budget as stopped.

        Called after sub-agent finishes and stop_pending state.
        """
        with self._lock:
            if self._state != BudgetState.STOP_PENDING:
                return None

            self._state = BudgetState.STOPPED
            event = BudgetEvent(
                event="stopped",
                level="error",
                message=f"预算已耗尽 {self._total_cost:.2f}/{self.limit_usd:.2f} USD，创作已停止",
                remaining_usd=self.remaining,
                total_cost=self._total_cost,
                limit_usd=self.limit_usd,
            )
            if self.on_event:
                self.on_event(event)
            return event

    def reset(self) -> None:
        """Reset budget state (e.g., when budget is increased)."""
        with self._lock:
            self._state = BudgetState.NORMAL
            self._total_cost = 0.0
            self._zero_streak = 0

    def update_limit(self, new_limit: float) -> None:
        """Update budget limit.

        If new limit is higher, reset state to normal.
        """
        with self._lock:
            old_limit = self.limit_usd
            self.limit_usd = new_limit

            # If limit increased and we were stopped, reset to normal
            if new_limit > old_limit and self._state in (
                BudgetState.STOP_PENDING,
                BudgetState.STOPPED,
            ):
                self._state = BudgetState.NORMAL
                logger.info(
                    "BudgetSentinel: limit increased %.2f → %.2f, reset to normal",
                    old_limit,
                    new_limit,
                )

    def get_status(self) -> dict[str, Any]:
        """Get current budget status."""
        with self._lock:
            return {
                "state": self._state.value,
                "total_cost": self._total_cost,
                "limit_usd": self.limit_usd,
                "remaining_usd": self.remaining,
                "usage_percent": (
                    (self._total_cost / self.limit_usd * 100)
                    if self.limit_usd > 0
                    else 0
                ),
                "zero_streak": self._zero_streak,
            }

"""Bounded Autonomy decision system for v6.0 agents.

Agents may decide to continue, repair, request help, or reroute — but they
must never bypass workflow safety, publish directly, or delete data.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class AutonomyDecision(str, Enum):
    CONTINUE = "continue"
    LOCAL_REPAIR = "local_repair"
    REQUEST_CONTEXT = "request_context"
    REROUTE = "reroute"
    REFUSE = "refuse"
    ASK_HUMAN = "ask_human"


_HARD_CONSTRAINTS = {
    "cannot_bypass_publish_gate": True,
    "cannot_delete_project_data": True,
    "cannot_overwrite_versions_without_user_action": True,
    "cannot_use_external_tools_unless_enabled": True,
    "max_repair_attempts": 1,
}


@dataclass
class BoundedAutonomyDecision:
    """Structured autonomy decision with safety metadata."""

    decision: AutonomyDecision
    reason: str
    confidence: float
    risk: str  # low | medium | high
    allowed_by_policy: bool = True
    next_action: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "reason": self.reason,
            "confidence": self.confidence,
            "risk": self.risk,
            "allowed_by_policy": self.allowed_by_policy,
            "next_action": self.next_action,
            "metadata": self.metadata,
        }

    @classmethod
    def continue_(cls, reason: str = "输出通过自检", confidence: float = 1.0) -> "BoundedAutonomyDecision":
        return cls(
            decision=AutonomyDecision.CONTINUE,
            reason=reason,
            confidence=confidence,
            risk="low",
            next_action="save_and_advance",
        )

    @classmethod
    def local_repair(
        cls, reason: str, next_action: str, confidence: float = 0.8
    ) -> "BoundedAutonomyDecision":
        return cls(
            decision=AutonomyDecision.LOCAL_REPAIR,
            reason=reason,
            confidence=confidence,
            risk="medium",
            next_action=next_action,
        )

    @classmethod
    def request_context(cls, reason: str, confidence: float = 0.7) -> "BoundedAutonomyDecision":
        return cls(
            decision=AutonomyDecision.REQUEST_CONTEXT,
            reason=reason,
            confidence=confidence,
            risk="low",
            next_action="pause_for_context",
        )

    @classmethod
    def reroute(cls, reason: str, target_agent: str, confidence: float = 0.75) -> "BoundedAutonomyDecision":
        return cls(
            decision=AutonomyDecision.REROUTE,
            reason=reason,
            confidence=confidence,
            risk="medium",
            next_action=f"route_to_{target_agent}",
            metadata={"target_agent": target_agent},
        )

    @classmethod
    def refuse(cls, reason: str, confidence: float = 0.9) -> "BoundedAutonomyDecision":
        return cls(
            decision=AutonomyDecision.REFUSE,
            reason=reason,
            confidence=confidence,
            risk="high",
            next_action="block_with_reason",
        )

    @classmethod
    def ask_human(cls, reason: str, confidence: float = 0.5) -> "BoundedAutonomyDecision":
        return cls(
            decision=AutonomyDecision.ASK_HUMAN,
            reason=reason,
            confidence=confidence,
            risk="high",
            next_action="escalate_to_human",
        )


def validate_autonomy_decision(
    decision: BoundedAutonomyDecision,
    agent_id: str,
    repair_count: int = 0,
    is_real_mode: bool = False,
) -> BoundedAutonomyDecision:
    """Validate and potentially block an autonomy decision based on hard constraints.

    Returns the decision with allowed_by_policy=False if it violates constraints.
    """
    if decision.decision == AutonomyDecision.LOCAL_REPAIR:
        if repair_count >= _HARD_CONSTRAINTS["max_repair_attempts"]:
            logger.warning(
                "Agent %s: local_repair blocked — max attempts (%s) reached",
                agent_id, _HARD_CONSTRAINTS["max_repair_attempts"],
            )
            decision.allowed_by_policy = False
            decision.risk = "high"
            decision.next_action = "escalate_to_human"
            decision.decision = AutonomyDecision.ASK_HUMAN
            decision.reason = f"修复次数已达上限 ({repair_count})，需人工介入: {decision.reason}"

    if decision.decision == AutonomyDecision.CONTINUE:
        if is_real_mode and decision.metadata.get("would_publish"):
            logger.warning("Agent %s: publish blocked in real mode without human confirmation", agent_id)
            decision.allowed_by_policy = False
            decision.decision = AutonomyDecision.ASK_HUMAN
            decision.reason = "real mode 下禁止自动发布，需人工确认"
            decision.next_action = "await_human_publish"

    return decision

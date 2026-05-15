"""Self-check and local repair loop for v6.0 creative agents.

Each agent can run self-check after generation, then optionally trigger
a bounded local repair instead of failing the whole chapter.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from .autonomy import BoundedAutonomyDecision, AutonomyDecision, validate_autonomy_decision

logger = logging.getLogger(__name__)


@dataclass
class SelfCheckResult:
    """Result of an agent's self-check pass."""

    passed: bool
    issues: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    repair_needed: bool = False
    repair_target: str = ""
    repair_suggestion: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "issues": self.issues,
            "warnings": self.warnings,
            "repair_needed": self.repair_needed,
            "repair_target": self.repair_target,
            "repair_suggestion": self.repair_suggestion,
        }


@dataclass
class LocalRepairResult:
    """Result of a local repair attempt."""

    success: bool
    before_summary: str = ""
    after_summary: str = ""
    attempts: int = 0
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        metadata = {
            key: value for key, value in self.metadata.items()
            if key != "repaired_output"
        }
        return {
            "success": self.success,
            "before_summary": self.before_summary,
            "after_summary": self.after_summary,
            "attempts": self.attempts,
            "error": self.error,
            **metadata,
        }


class SelfCheckLoop:
    """Runs generate → self_check → local_repair → final_check → save."""

    def __init__(
        self,
        agent_id: str,
        max_repair_attempts: int = 1,
    ) -> None:
        self.agent_id = agent_id
        self.max_repair_attempts = max_repair_attempts
        self.repair_count = 0

    def run(
        self,
        generate_fn: Callable[[], dict[str, Any]],
        self_check_fn: Callable[[dict[str, Any]], SelfCheckResult],
        repair_fn: Callable[[dict[str, Any], SelfCheckResult], dict[str, Any] | None],
    ) -> dict[str, Any]:
        """Execute the full generate → check → repair → save loop.

        Returns the final output dict with autonomy decision and trace.
        """
        output = generate_fn()
        check = self_check_fn(output)

        trace: dict[str, Any] = {
            "self_check": check.to_dict(),
            "repair_attempts": [],
            "autonomy_decision": None,
        }

        if check.passed:
            decision = BoundedAutonomyDecision.continue_(reason="自检通过")
            trace["autonomy_decision"] = decision.to_dict()
            output["_autonomy"] = decision.to_dict()
            output["_trace"] = trace
            return output

        if not check.repair_needed:
            decision = BoundedAutonomyDecision.reroute(
                reason=f"自检未通过但不可局部修复: {check.repair_suggestion}",
                target_agent="planner",
            )
            trace["autonomy_decision"] = decision.to_dict()
            output["_autonomy"] = decision.to_dict()
            output["_trace"] = trace
            return output

        # Attempt bounded local repair
        repaired_output = None
        if self.repair_count < self.max_repair_attempts:
            repair_result = self._attempt_repair(output, check, repair_fn)
            trace["repair_attempts"].append(repair_result.to_dict())

            if repair_result.success:
                decision = BoundedAutonomyDecision.continue_(
                    reason=f"局部修复成功 ({repair_result.attempts} 次尝试)"
                )
                repaired_output = repair_result.metadata.get("repaired_output")
            else:
                decision = BoundedAutonomyDecision.ask_human(
                    reason=f"局部修复失败: {repair_result.error}"
                )
        else:
            decision = BoundedAutonomyDecision.ask_human(
                reason=f"修复次数已达上限 ({self.repair_count})"
            )

        decision = validate_autonomy_decision(
            decision, self.agent_id, repair_count=self.repair_count
        )
        trace["autonomy_decision"] = decision.to_dict()

        final_output = repaired_output if repaired_output is not None else output
        final_output["_autonomy"] = decision.to_dict()
        final_output["_trace"] = trace
        return final_output

    def _attempt_repair(
        self,
        output: dict[str, Any],
        check: SelfCheckResult,
        repair_fn: Callable[[dict[str, Any], SelfCheckResult], dict[str, Any] | None],
    ) -> LocalRepairResult:
        self.repair_count += 1
        before_summary = str(output)[:200]
        try:
            repaired = repair_fn(output, check)
            if repaired is not None:
                return LocalRepairResult(
                    success=True,
                    before_summary=before_summary,
                    after_summary=str(repaired)[:200],
                    attempts=self.repair_count,
                    metadata={"repaired_output": repaired},
                )
            return LocalRepairResult(
                success=False,
                before_summary=before_summary,
                attempts=self.repair_count,
                error="repair_fn returned None",
            )
        except Exception as e:
            logger.warning("Agent %s local repair failed: %s", self.agent_id, e)
            return LocalRepairResult(
                success=False,
                before_summary=before_summary,
                attempts=self.repair_count,
                error=str(e),
            )

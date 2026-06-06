"""DeathPenaltySkill: deterministic AI cliche / death-penalty phrase detector.

Wraps validators/death_penalty.py as a ValidatorSkill.
No LLM calls, no side effects.
"""

from __future__ import annotations

from typing import Any

from .base import ValidatorSkill


class DeathPenaltySkill(ValidatorSkill):
    """Scan text for death-penalty phrases (AI cliches) with severity levels.

    Delegates to validators.death_penalty.check_death_penalty_structured().
    """

    skill_id = "death-penalty"
    skill_type = "validator"
    version = "1.0.0"

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        from ..validators.death_penalty import check_death_penalty_structured

        text = str(payload.get("text") or payload.get("content") or "")

        if not text:
            return {
                "ok": True,
                "error": None,
                "data": {"has_critical": False, "violations": [], "score": 100, "issues": []},
            }

        try:
            result = check_death_penalty_structured(text)
            issues = [f"CRITICAL 死刑红线: {v}" for v in result.violations] if result.has_critical else []
            return {
                "ok": not result.has_critical,
                "error": "; ".join(issues) if issues else None,
                "data": {
                    "has_critical": result.has_critical,
                    "violations": result.violations,
                    "issues": issues,
                },
            }
        except Exception as e:
            return {
                "ok": False,
                "error": f"死刑红线检查异常: {e}",
                "data": {"has_critical": True, "violations": [str(e)], "issues": [str(e)]},
            }

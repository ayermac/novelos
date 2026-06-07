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
                "data": {
                    "passed": True,
                    "score": 100,
                    "findings": [],
                    "summary": "无正文内容，跳过死刑红线检查",
                },
            }

        try:
            result = check_death_penalty_structured(text)
            findings = []
            for violation in result.violations:
                findings.append({
                    "severity": "blocking",
                    "code": "DEATH_PENALTY",
                    "message": f"死刑红线: {violation}",
                    "suggestion": "请删除或重写包含AI烂词的内容",
                })
            
            passed = not result.has_critical
            score = 100 if passed else 0
            summary = f"死刑红线检查{'通过' if passed else '未通过'}，发现 {len(findings)} 个违规"
            
            return {
                "ok": passed,
                "error": "; ".join([f["message"] for f in findings]) if not passed else None,
                "data": {
                    "passed": passed,
                    "score": score,
                    "findings": findings,
                    "summary": summary,
                    "has_critical": result.has_critical,
                    "violations": result.violations,
                },
            }
        except Exception as e:
            return {
                "ok": False,
                "error": f"死刑红线检查异常: {e}",
                "data": {
                    "passed": False,
                    "score": 0,
                    "findings": [{"severity": "blocking", "code": "DEATH_PENALTY_ERROR", "message": str(e), "suggestion": "请检查文本内容"}],
                    "summary": f"死刑红线检查异常: {e}",
                },
            }

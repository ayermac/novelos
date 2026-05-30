"""ContinuityGateSkill: deterministic narrative continuity gate.

Wraps quality/continuity_gate.py as a ValidatorSkill.
No LLM calls, no side effects.
"""

from __future__ import annotations

from typing import Any

from .base import ValidatorSkill


class ContinuityGateSkill(ValidatorSkill):
    """Check chapter for narrative continuity defects.

    Delegates to quality.continuity_gate.evaluate_chapter_continuity().
    The repo object must be provided in the payload by the calling agent.
    """

    skill_id = "continuity-gate"
    skill_type = "validator"
    version = "1.0.0"

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        from ..quality.continuity_gate import evaluate_chapter_continuity

        content = str(payload.get("content") or "")
        title = str(payload.get("title") or "")
        project_id = str(payload.get("project_id") or "")
        chapter_number = int(payload.get("chapter_number") or 0)
        repo = payload.get("_repo")

        if not content:
            return {
                "ok": False,
                "error": "缺少 content 字段",
                "data": {"passed": False, "severity": "blocking", "issues": ["正文为空"], "suggestions": [], "should_block_publish": True},
            }

        if not repo or not project_id or not chapter_number:
            # Can only run title check without repo
            from ..quality.continuity_gate import _check_title
            issues, suggestions, evidence = _check_title(title, content)
            return {
                "ok": True,
                "error": None,
                "data": {
                    "passed": not issues,
                    "severity": "warning" if issues else "pass",
                    "issues": issues,
                    "suggestions": suggestions,
                    "should_block_publish": False,
                    "evidence": evidence,
                },
            }

        try:
            result = evaluate_chapter_continuity(
                repo, project_id, chapter_number, content, title=title,
            )
            return {
                "ok": result.passed,
                "error": "; ".join(result.issues) if not result.passed else None,
                "data": result.to_dict(),
            }
        except Exception as e:
            return {
                "ok": False,
                "error": f"连续性检查异常: {e}",
                "data": {"passed": False, "severity": "blocking", "issues": [str(e)], "suggestions": [], "should_block_publish": True},
            }

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
                "data": {
                    "passed": False,
                    "score": 0,
                    "findings": [{"severity": "blocking", "code": "EMPTY_CONTENT", "message": "正文为空", "suggestion": "请提供章节正文"}],
                    "summary": "正文为空，无法进行连续性检查",
                },
            }

        if not repo or not project_id or not chapter_number:
            # Can only run title check without repo
            from ..quality.continuity_gate import _check_title
            issues, suggestions, evidence = _check_title(title, content)
            findings = []
            for issue in issues:
                findings.append({"severity": "warning", "code": "TITLE_ISSUE", "message": issue, "suggestion": ""})
            for suggestion in suggestions:
                findings.append({"severity": "info", "code": "TITLE_SUGGESTION", "message": "", "suggestion": suggestion})
            return {
                "ok": True,
                "error": None,
                "data": {
                    "passed": not issues,
                    "score": 100 if not issues else 80,
                    "findings": findings,
                    "summary": f"标题检查完成，发现 {len(issues)} 个问题" if issues else "标题检查通过",
                },
            }

        try:
            result = evaluate_chapter_continuity(
                repo, project_id, chapter_number, content, title=title,
            )
            # Convert to unified schema
            findings = []
            for issue in result.issues:
                severity = "blocking" if result.severity == "blocking" else "warning"
                findings.append({"severity": severity, "code": "CONTINUITY_ISSUE", "message": issue, "suggestion": ""})
            for suggestion in result.suggestions:
                findings.append({"severity": "info", "code": "CONTINUITY_SUGGESTION", "message": "", "suggestion": suggestion})
            
            score = 100 if result.passed else (60 if result.severity == "blocking" else 80)
            summary = f"连续性检查{'通过' if result.passed else '未通过'}，发现 {len(result.issues)} 个问题"
            
            return {
                "ok": result.passed,
                "error": "; ".join(result.issues) if not result.passed else None,
                "data": {
                    "passed": result.passed,
                    "score": score,
                    "findings": findings,
                    "summary": summary,
                },
            }
        except Exception as e:
            return {
                "ok": False,
                "error": f"连续性检查异常: {e}",
                "data": {
                    "passed": False,
                    "score": 0,
                    "findings": [{"severity": "blocking", "code": "CONTINUITY_ERROR", "message": str(e), "suggestion": "请检查章节数据完整性"}],
                    "summary": f"连续性检查异常: {e}",
                },
            }

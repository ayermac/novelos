"""ChapterSeamSkill: deterministic chapter-to-chapter seam checker.

Wraps quality/chapter_seam.py as a ValidatorSkill.
No LLM calls, no side effects.
"""

from __future__ import annotations

from typing import Any

from .base import ValidatorSkill


class ChapterSeamSkill(ValidatorSkill):
    """Check for chapter-to-chapter seam breaks (time/location/hook discontinuity).

    Delegates to quality.chapter_seam.evaluate_chapter_seam().
    The repo object must be provided in the payload by the calling agent.
    """

    skill_id = "chapter-seam"
    skill_type = "validator"
    version = "1.0.0"

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        from ..quality.chapter_seam import evaluate_chapter_seam

        content = str(payload.get("content") or "")
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
                    "summary": "正文为空，无法进行章节衔接检查",
                },
            }

        if not repo or not project_id or not chapter_number:
            return {
                "ok": True,
                "error": None,
                "data": {
                    "passed": True,
                    "score": 100,
                    "findings": [],
                    "summary": "跳过章节衔接检查（缺少必要参数）",
                },
            }

        try:
            result = evaluate_chapter_seam(repo, project_id, chapter_number, content)
            # Convert to unified schema
            findings = []
            for issue in result.get("blocking_issues", []):
                findings.append({"severity": "blocking", "code": "SEAM_BLOCKING", "message": issue, "suggestion": ""})
            for issue in result.get("advisory_issues", []):
                findings.append({"severity": "warning", "code": "SEAM_ADVISORY", "message": issue, "suggestion": ""})
            for suggestion in result.get("suggestions", []):
                findings.append({"severity": "info", "code": "SEAM_SUGGESTION", "message": "", "suggestion": suggestion})
            
            passed = result.get("passed", True)
            score = 100 if passed else 70
            summary = f"章节衔接检查{'通过' if passed else '未通过'}，发现 {len(findings)} 个问题"
            
            return {
                "ok": passed,
                "error": "; ".join(result.get("blocking_issues", [])) if not passed else None,
                "data": {
                    "passed": passed,
                    "score": score,
                    "findings": findings,
                    "summary": summary,
                },
            }
        except Exception as e:
            return {
                "ok": False,
                "error": f"章节衔接检查异常: {e}",
                "data": {
                    "passed": False,
                    "score": 0,
                    "findings": [{"severity": "blocking", "code": "SEAM_ERROR", "message": str(e), "suggestion": "请检查章节数据完整性"}],
                    "summary": f"章节衔接检查异常: {e}",
                },
            }

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
                "data": {"passed": False, "issues": ["正文为空"], "suggestions": [], "blocking_count": 1},
            }

        if not repo or not project_id or not chapter_number:
            return {
                "ok": True,
                "error": None,
                "data": {"passed": True, "issues": [], "suggestions": [], "blocking_count": 0},
            }

        try:
            result = evaluate_chapter_seam(repo, project_id, chapter_number, content)
            return {
                "ok": result.get("passed", True),
                "error": "; ".join(result.get("issues", [])) if not result.get("passed", True) else None,
                "data": result,
            }
        except Exception as e:
            return {
                "ok": False,
                "error": f"章节衔接检查异常: {e}",
                "data": {"passed": False, "issues": [str(e)], "suggestions": [], "blocking_count": 1},
            }

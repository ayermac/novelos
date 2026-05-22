"""Quality diagnosis API endpoints (v6.4.0).

Provides read-only chapter quality diagnosis without triggering LLM calls.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..envelope import envelope_response, error_response, EnvelopeResponse

router = APIRouter()


@router.get("/projects/{project_id}/chapters/{chapter_number}/quality-diagnosis")
async def get_chapter_quality_diagnosis(
    request: Request,
    project_id: str,
    chapter_number: int,
) -> EnvelopeResponse:
    """Get structured quality diagnosis for a chapter.

    Aggregates death_penalty, ai_style_detector, narrative_quality_scorer,
    and baseline show-dont-tell / info-dump detection.

    Does NOT trigger LLM calls. Does NOT rewrite text.
    """
    from ..deps import get_repo
    from ...skills.registry import SkillRegistry
    from ...quality.hub import QualityHub

    try:
        repo = get_repo(request)

        project = repo.get_project(project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        chapter = repo.get_chapter(project_id, chapter_number)
        if not chapter:
            return error_response(
                "CHAPTER_NOT_FOUND",
                f"章节 {chapter_number} 不存在",
            )

        content = chapter.get("content", "")
        if not content or not content.strip():
            return error_response(
                "CHAPTER_NO_CONTENT",
                f"章节 {chapter_number} 无正文内容，无法诊断",
            )

        skill_registry = SkillRegistry()
        hub = QualityHub(repo, skill_registry=skill_registry)

        diagnosis = hub.diagnose(
            chapter_text=content,
            context={"project_id": project_id, "chapter_number": chapter_number},
        )

        return envelope_response(diagnosis)

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"质量诊断失败: {str(e)}")

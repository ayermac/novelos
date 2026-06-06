"""Editor reports API endpoints.

Returns editor review data from the legacy Editor agent (reviews table).
v6.9.0-rollout: Removed editor_lenses dependency; now surfaces the single
editor review record per chapter.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..envelope import envelope_response, error_response, EnvelopeResponse

router = APIRouter()


@router.get("/projects/{project_id}/chapters/{chapter_number}/editor-reports")
async def get_editor_reports(
    request: Request,
    project_id: str,
    chapter_number: int,
) -> EnvelopeResponse:
    """Get editor review report for a chapter.

    Returns the latest editor review (score, issues, suggestions) produced by
    the Editor agent.  This replaces the previous lens-based report structure.

    Args:
        project_id: Project identifier
        chapter_number: Chapter number
    """
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        chapter = repo.get_chapter(project_id, chapter_number)
        if not chapter:
            return envelope_response({
                "project_id": project_id,
                "chapter_number": chapter_number,
                "review": None,
            })

        review = repo.get_latest_review(project_id, chapter["id"])

        return envelope_response({
            "project_id": project_id,
            "chapter_number": chapter_number,
            "review": review,
        })

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取编辑审核报告失败: {str(e)}")


@router.get("/projects/{project_id}/editor-reports/summary")
async def get_editor_reports_summary(
    request: Request,
    project_id: str,
    limit: int = 20,
) -> EnvelopeResponse:
    """Get summary of editor reviews for a project.

    Returns review scores for recent chapters.

    Args:
        project_id: Project identifier
        limit: Number of recent chapters to include (default 20)
    """
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        chapters = repo.list_chapters(project_id)

        summaries = []
        for ch in chapters[-limit:]:
            chapter_number = ch.get("chapter_number", 0)
            chapter_id = ch.get("id")

            review = None
            if chapter_id:
                review = repo.get_latest_review(project_id, chapter_id)

            if review:
                summaries.append({
                    "chapter_number": chapter_number,
                    "status": ch.get("status", ""),
                    "passed": bool(review.get("pass", 0)),
                    "score": review.get("score", 0),
                    "issues_count": len(review.get("issues") or []),
                })

        return envelope_response({
            "project_id": project_id,
            "chapters": summaries,
            "total_chapters": len(summaries),
        })

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取编辑审核摘要失败: {str(e)}")

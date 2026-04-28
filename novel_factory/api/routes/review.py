"""Review workbench API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from ..envelope import envelope_response, error_response, EnvelopeResponse

router = APIRouter()


class ApproveRequest(BaseModel):
    """Approve chapter request (v5.2 Phase C)."""

    project_id: str
    chapter_number: int


class RejectRequest(BaseModel):
    """Reject chapter request (v5.2 Phase C)."""

    project_id: str
    chapter_number: int
    reason: str
    target: str = "author"  # Which agent to send revision to: author, polisher, or planner


@router.get("/review/workbench")
async def get_review_workbench(
    request: Request,
    project_id: str | None = None,
    status: str | None = None,
) -> EnvelopeResponse:
    """Get review workbench with queue.

    Args:
        project_id: Filter by project
        status: Filter by status (review, blocking, approved, rejected)
    """
    from ..deps import get_repo

    try:
        repo = get_repo(request)
        projects = repo.list_projects()

        # Build review queue
        review_queue = []
        for p in projects:
            if project_id and p["project_id"] != project_id:
                continue
            chapters = repo.list_chapters(p["project_id"])
            for ch in chapters:
                ch_status = ch.get("status", "")
                if status and ch_status != status:
                    continue
                if ch_status in ("review", "blocking", "approved", "rejected"):
                    review_queue.append({
                        "project_id": p["project_id"],
                        "project_name": p.get("name", ""),
                        "chapter_number": ch.get("chapter_number", 0),
                        "status": ch_status,
                        "quality_score": ch.get("quality_score"),
                        "issue_count": ch.get("issue_count", 0),
                        "last_run_id": ch.get("last_run_id", ""),
                    })

        # Count by status
        all_chapters = []
        for p in projects:
            all_chapters.extend(repo.list_chapters(p["project_id"]))

        review_count = sum(1 for c in all_chapters if c.get("status") == "review")
        blocking_count = sum(1 for c in all_chapters if c.get("status") == "blocking")
        approved_count = sum(1 for c in all_chapters if c.get("status") == "approved")
        rejected_count = sum(1 for c in all_chapters if c.get("status") == "rejected")

        return envelope_response({
            "queue": review_queue,
            "stats": {
                "review": review_count,
                "blocking": blocking_count,
                "approved": approved_count,
                "rejected": rejected_count,
            },
            "projects": projects,
        })

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取审核工作台失败: {str(e)}")


@router.get("/review/pack")
async def get_review_pack(
    request: Request,
    run_id: str | None = None,
    project_id: str | None = None,
    from_chapter: int | None = None,
    to_chapter: int | None = None,
) -> EnvelopeResponse:
    """Build a review pack."""
    from ..deps import get_dispatcher

    try:
        dispatcher = get_dispatcher(request)
        result = dispatcher.build_review_pack(
            run_id=run_id,
            project_id=project_id,
            from_chapter=from_chapter,
            to_chapter=to_chapter,
        )
        return envelope_response(result)

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"生成审核包失败: {str(e)}")


@router.get("/review/chapter")
async def get_review_chapter(
    request: Request,
    project_id: str,
    chapter: int,
) -> EnvelopeResponse:
    """Get review view for a chapter."""
    from ..deps import get_dispatcher

    try:
        dispatcher = get_dispatcher(request)
        result = dispatcher.get_review_chapter(project_id=project_id, chapter=chapter)
        return envelope_response(result)

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取章节审核视图失败: {str(e)}")


@router.get("/review/timeline")
async def get_review_timeline(
    request: Request,
    run_id: str | None = None,
    project_id: str | None = None,
    chapter: int | None = None,
) -> EnvelopeResponse:
    """Get timeline events."""
    from ..deps import get_dispatcher

    try:
        dispatcher = get_dispatcher(request)
        result = dispatcher.get_review_timeline(
            run_id=run_id,
            project_id=project_id,
            chapter=chapter,
        )
        return envelope_response(result)

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取时间线失败: {str(e)}")


@router.get("/review/diff")
async def get_review_diff(
    request: Request,
    project_id: str,
    chapter: int,
    from_version: str | None = None,
    to_version: str | None = None,
) -> EnvelopeResponse:
    """Get diff between chapter versions."""
    from ..deps import get_dispatcher

    try:
        dispatcher = get_dispatcher(request)
        result = dispatcher.get_review_diff(
            project_id=project_id,
            chapter=chapter,
            from_version=from_version,
            to_version=to_version,
        )
        return envelope_response(result)

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取差异失败: {str(e)}")


@router.post("/review/approve")
async def approve_chapter(request: Request, body: ApproveRequest) -> EnvelopeResponse:
    """Approve a chapter for publishing (v5.2 Phase C).

    Changes chapter status from 'review' to 'reviewed'.
    The chapter can then be published via the normal workflow.
    """
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        # Verify project exists
        project = repo.get_project(body.project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{body.project_id}' 不存在")

        # Verify chapter exists
        chapter = repo.get_chapter(body.project_id, body.chapter_number)
        if not chapter:
            return error_response("CHAPTER_NOT_FOUND", f"章节 {body.chapter_number} 不存在")

        # Check if chapter is in review status
        current_status = chapter.get("status", "")
        if current_status != "review":
            return error_response(
                "INVALID_STATUS",
                f"章节状态为 '{current_status}'，仅 'review' 状态可审核通过"
            )

        # Update status to reviewed
        updated = repo.update_chapter_status(
            body.project_id, body.chapter_number, "reviewed"
        )
        if not updated:
            return error_response("UPDATE_FAILED", "更新章节状态失败")

        return envelope_response({
            "approved": True,
            "project_id": body.project_id,
            "chapter_number": body.chapter_number,
            "previous_status": current_status,
            "new_status": "reviewed",
        })

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"审核通过失败: {str(e)}")


@router.post("/review/reject")
async def reject_chapter(request: Request, body: RejectRequest) -> EnvelopeResponse:
    """Reject a chapter and send it for revision (v5.2 Phase C).

    Changes chapter status from 'review' to 'revision' and records the reason.
    """
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        # Verify project exists
        project = repo.get_project(body.project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{body.project_id}' 不存在")

        # Verify chapter exists
        chapter = repo.get_chapter(body.project_id, body.chapter_number)
        if not chapter:
            return error_response("CHAPTER_NOT_FOUND", f"章节 {body.chapter_number} 不存在")

        # Check if chapter is in review status
        current_status = chapter.get("status", "")
        if current_status != "review":
            return error_response(
                "INVALID_STATUS",
                f"章节状态为 '{current_status}'，仅 'review' 状态可驳回"
            )

        # Record rejection reason
        repo.save_chapter_review_note(
            project_id=body.project_id,
            chapter_number=body.chapter_number,
            source_run_id=chapter.get("last_run_id", ""),
            revision_run_id="",  # Will be populated when revision run starts
            notes=f"[驳回] {body.reason}\n目标: {body.target}",
        )

        # Update status to revision
        updated = repo.update_chapter_status(
            body.project_id, body.chapter_number, "revision"
        )
        if not updated:
            return error_response("UPDATE_FAILED", "更新章节状态失败")

        return envelope_response({
            "rejected": True,
            "project_id": body.project_id,
            "chapter_number": body.chapter_number,
            "previous_status": current_status,
            "new_status": "revision",
            "reason": body.reason,
            "target": body.target,
        })

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"驳回失败: {str(e)}")

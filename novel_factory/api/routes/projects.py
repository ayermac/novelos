"""Projects API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

from ..envelope import envelope_response, error_response, EnvelopeResponse

router = APIRouter()


class CreateProjectRequest(BaseModel):
    """Create project request."""

    project_id: str
    name: str
    genre: str | None = None
    description: str | None = None
    total_chapters_planned: int = 500
    target_words: int = 1500000
    style_template: str = "default_web_serial"
    start_chapter: int = 1
    initial_chapter_count: int = 10


class UpdateProjectRequest(BaseModel):
    """Update project request (v5.2 Phase C)."""

    name: str | None = None
    description: str | None = None
    genre: str | None = None
    target_words: int | None = None
    total_chapters_planned: int | None = None


@router.get("/projects")
async def list_projects(request: Request) -> EnvelopeResponse:
    """List all projects."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)
        projects = repo.list_projects()

        # Add chapter counts
        result = []
        for p in projects:
            chapters = repo.list_chapters(p["project_id"])
            result.append({
                **p,
                "chapter_count": len(chapters),
            })

        return envelope_response(result)

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取项目列表失败: {str(e)}")


@router.get("/projects/{project_id}")
async def get_project(request: Request, project_id: str) -> EnvelopeResponse:
    """Get a single project by ID."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)
        project = repo.get_project(project_id)

        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        # Get chapters
        chapters = repo.list_chapters(project_id)

        return envelope_response({
            **project,
            "chapters": chapters,
            "chapter_count": len(chapters),
        })

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取项目失败: {str(e)}")


@router.put("/projects/{project_id}")
async def update_project(
    request: Request, project_id: str, body: UpdateProjectRequest
) -> EnvelopeResponse:
    """Update project settings (v5.2 Phase C).

    Allows updating name, description, genre, target_words, total_chapters_planned.
    """
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        # Verify project exists
        project = repo.get_project(project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        # Build update data (only include non-None fields)
        update_data = {}
        if body.name is not None:
            update_data["name"] = body.name
        if body.description is not None:
            update_data["description"] = body.description
        if body.genre is not None:
            update_data["genre"] = body.genre
        if body.target_words is not None:
            update_data["target_words"] = body.target_words
        if body.total_chapters_planned is not None:
            update_data["total_chapters_planned"] = body.total_chapters_planned

        if not update_data:
            return error_response("NO_UPDATES", "没有提供需要更新的字段")

        # Update project
        updated = repo.update_project(project_id, **update_data)
        if not updated:
            return error_response("UPDATE_FAILED", "更新项目失败")

        return envelope_response(updated)

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"更新项目失败: {str(e)}")


@router.get("/projects/{project_id}/chapters/{chapter_number}")
async def get_chapter_detail(
    request: Request, project_id: str, chapter_number: int
) -> EnvelopeResponse:
    """Get a single chapter's full detail including content.

    This is the author reader endpoint — content is included.
    """
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        # Verify project exists
        project = repo.get_project(project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        # Get chapter
        chapter = repo.get_chapter(project_id, chapter_number)
        if not chapter:
            return error_response("CHAPTER_NOT_FOUND", f"章节 {chapter_number} 不存在")

        # Return clean chapter data (no internal DB fields)
        return envelope_response({
            "project_id": project_id,
            "project_name": project.get("name", ""),
            "chapter_number": chapter.get("chapter_number", chapter_number),
            "title": chapter.get("title", ""),
            "status": chapter.get("status", ""),
            "word_count": chapter.get("word_count", 0),
            "quality_score": chapter.get("quality_score"),
            "content": chapter.get("content", ""),
            "created_at": chapter.get("created_at", ""),
            "updated_at": chapter.get("updated_at", ""),
        })

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取章节详情失败: {str(e)}")


@router.get("/projects/{project_id}/workspace")
async def get_project_workspace(request: Request, project_id: str) -> EnvelopeResponse:
    """Get project workspace with chapters and recent runs."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)
        project = repo.get_project(project_id)

        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        # Get chapters
        chapters = repo.list_chapters(project_id)

        # Get recent runs
        runs = repo.get_workflow_runs_for_project(project_id, limit=10)

        # Get stats
        total_words = sum(ch.get("word_count", 0) for ch in chapters)
        status_counts = {}
        for ch in chapters:
            status = ch.get("status", "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1

        return envelope_response({
            "project": project,
            "chapters": chapters,
            "recent_runs": runs,
            "stats": {
                "total_chapters": len(chapters),
                "total_words": total_words,
                "status_counts": status_counts,
            },
        })

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取项目工作台失败: {str(e)}")


@router.delete("/projects/{project_id}")
async def delete_project(request: Request, project_id: str) -> EnvelopeResponse:
    """Delete a project and all associated data."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        deleted = repo.delete_project(project_id)
        if not deleted:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        return envelope_response({"deleted": True})

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"删除项目失败: {str(e)}")


@router.post("/projects/{project_id}/chapters/{chapter_number}/reset")
async def reset_chapter(
    request: Request, project_id: str, chapter_number: int
) -> EnvelopeResponse:
    """Reset a chapter to planned status for re-processing.

    Only works for chapters in 'blocking' or 'revision' status.
    """
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        # Verify project exists
        project = repo.get_project(project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        # Verify chapter exists
        chapter = repo.get_chapter(project_id, chapter_number)
        if not chapter:
            return error_response("CHAPTER_NOT_FOUND", f"章节 {chapter_number} 不存在")

        # Check if reset is allowed
        current_status = chapter.get("status", "")
        if current_status not in ("blocking", "revision"):
            return error_response(
                "INVALID_STATUS",
                f"章节状态为 '{current_status}'，仅 'blocking' 或 'revision' 状态可重置"
            )

        # Reset the chapter
        reset = repo.reset_chapter(project_id, chapter_number)
        if not reset:
            return error_response("RESET_FAILED", "重置章节失败")

        return envelope_response({
            "reset": True,
            "previous_status": current_status,
            "new_status": "planned",
        })

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"重置章节失败: {str(e)}")


@router.delete("/projects/{project_id}/chapters/{chapter_number}")
async def delete_chapter(
    request: Request, project_id: str, chapter_number: int
) -> EnvelopeResponse:
    """Delete a chapter.

    Only allowed for chapters in 'planned' status.
    """
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        # Verify project exists
        project = repo.get_project(project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        # Verify chapter exists
        chapter = repo.get_chapter(project_id, chapter_number)
        if not chapter:
            return error_response("CHAPTER_NOT_FOUND", f"章节 {chapter_number} 不存在")

        # Check if deletion is allowed (only planned status)
        current_status = chapter.get("status", "")
        if current_status != "planned":
            return error_response(
                "INVALID_STATUS",
                f"章节状态为 '{current_status}'，仅 'planned' 状态可删除"
            )

        # Delete the chapter
        deleted = repo.delete_chapter(project_id, chapter_number)
        if not deleted:
            return error_response("DELETE_FAILED", "删除章节失败")

        return envelope_response({"deleted": True})

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"删除章节失败: {str(e)}")

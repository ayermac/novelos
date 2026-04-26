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

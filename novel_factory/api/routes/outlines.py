"""Outlines API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..envelope import envelope_response, error_response, EnvelopeResponse

router = APIRouter()


@router.get("/projects/{project_id}/outlines")
async def list_outlines(request: Request, project_id: str) -> EnvelopeResponse:
    """List all outlines for a project."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        # Verify project exists
        project = repo.get_project(project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        # Check for level query param
        level = request.query_params.get("level")

        if level:
            outlines = repo.get_outlines_by_level(project_id, level)
        else:
            outlines = repo.list_outlines(project_id)

        return envelope_response(outlines)

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取大纲列表失败: {str(e)}")


@router.get("/projects/{project_id}/outlines/{outline_id}")
async def get_outline(
    request: Request, project_id: str, outline_id: int
) -> EnvelopeResponse:
    """Get a specific outline."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        outline = repo.get_outline(project_id, outline_id)
        if not outline:
            return error_response("OUTLINE_NOT_FOUND", f"大纲 {outline_id} 不存在")

        return envelope_response(outline)

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取大纲失败: {str(e)}")


@router.post("/projects/{project_id}/outlines")
async def create_outline(request: Request, project_id: str) -> EnvelopeResponse:
    """Create a new outline."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        # Verify project exists
        project = repo.get_project(project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        # Parse request body
        body = await request.json()
        level = body.get("level", "")
        sequence = body.get("sequence", 0)
        title = body.get("title", "")
        content = body.get("content", "")
        chapters_range = body.get("chapters_range", "")

        if not level:
            return error_response("VALIDATION_ERROR", "大纲层级不能为空")
        if not title:
            return error_response("VALIDATION_ERROR", "大纲标题不能为空")

        # Validate level
        valid_levels = ("volume", "arc", "chapter")
        if level not in valid_levels:
            return error_response("VALIDATION_ERROR", f"大纲层级必须是: {', '.join(valid_levels)}")

        outline = repo.create_outline(
            project_id=project_id,
            level=level,
            sequence=sequence,
            title=title,
            content=content,
            chapters_range=chapters_range,
        )

        return envelope_response(outline)

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"创建大纲失败: {str(e)}")


@router.put("/projects/{project_id}/outlines/{outline_id}")
async def update_outline(
    request: Request, project_id: str, outline_id: int
) -> EnvelopeResponse:
    """Update an outline."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        # Verify outline exists
        existing = repo.get_outline(project_id, outline_id)
        if not existing:
            return error_response("OUTLINE_NOT_FOUND", f"大纲 {outline_id} 不存在")

        # Parse request body
        body = await request.json()
        data = {}
        for key in ("level", "sequence", "title", "content", "chapters_range"):
            if key in body:
                data[key] = body[key]

        if not data:
            return envelope_response(existing)

        # Validate level if provided
        if "level" in data:
            valid_levels = ("volume", "arc", "chapter")
            if data["level"] not in valid_levels:
                return error_response("VALIDATION_ERROR", f"大纲层级必须是: {', '.join(valid_levels)}")

        outline = repo.update_outline(project_id, outline_id, data)
        return envelope_response(outline)

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"更新大纲失败: {str(e)}")


@router.delete("/projects/{project_id}/outlines/{outline_id}")
async def delete_outline(
    request: Request, project_id: str, outline_id: int
) -> EnvelopeResponse:
    """Delete an outline."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        deleted = repo.delete_outline(project_id, outline_id)
        if not deleted:
            return error_response("OUTLINE_NOT_FOUND", f"大纲 {outline_id} 不存在")

        return envelope_response({"deleted": True})

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"删除大纲失败: {str(e)}")

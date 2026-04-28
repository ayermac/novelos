"""World Settings API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..envelope import envelope_response, error_response, EnvelopeResponse

router = APIRouter()


@router.get("/projects/{project_id}/world-settings")
async def list_world_settings(request: Request, project_id: str) -> EnvelopeResponse:
    """List all world settings for a project."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        # Verify project exists
        project = repo.get_project(project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        settings = repo.list_world_settings(project_id)
        return envelope_response(settings)

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取世界观设定失败: {str(e)}")


@router.get("/projects/{project_id}/world-settings/{ws_id}")
async def get_world_setting(
    request: Request, project_id: str, ws_id: int
) -> EnvelopeResponse:
    """Get a specific world setting."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        setting = repo.get_world_setting(project_id, ws_id)
        if not setting:
            return error_response("WORLD_SETTING_NOT_FOUND", f"世界观设定 {ws_id} 不存在")

        return envelope_response(setting)

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取世界观设定失败: {str(e)}")


@router.post("/projects/{project_id}/world-settings")
async def create_world_setting(request: Request, project_id: str) -> EnvelopeResponse:
    """Create a new world setting."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        # Verify project exists
        project = repo.get_project(project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        # Parse request body
        body = await request.json()
        category = body.get("category", "")
        title = body.get("title", "")
        content = body.get("content", "")

        if not category:
            return error_response("VALIDATION_ERROR", "分类不能为空")
        if not title:
            return error_response("VALIDATION_ERROR", "标题不能为空")

        setting = repo.create_world_setting(
            project_id=project_id,
            category=category,
            title=title,
            content=content,
        )

        return envelope_response(setting)

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"创建世界观设定失败: {str(e)}")


@router.put("/projects/{project_id}/world-settings/{ws_id}")
async def update_world_setting(
    request: Request, project_id: str, ws_id: int
) -> EnvelopeResponse:
    """Update a world setting."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        # Verify setting exists
        existing = repo.get_world_setting(project_id, ws_id)
        if not existing:
            return error_response("WORLD_SETTING_NOT_FOUND", f"世界观设定 {ws_id} 不存在")

        # Parse request body
        body = await request.json()
        data = {}
        for key in ("category", "title", "content"):
            if key in body:
                data[key] = body[key]

        if not data:
            return envelope_response(existing)

        setting = repo.update_world_setting(project_id, ws_id, data)
        return envelope_response(setting)

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"更新世界观设定失败: {str(e)}")


@router.delete("/projects/{project_id}/world-settings/{ws_id}")
async def delete_world_setting(
    request: Request, project_id: str, ws_id: int
) -> EnvelopeResponse:
    """Delete a world setting."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        deleted = repo.delete_world_setting(project_id, ws_id)
        if not deleted:
            return error_response("WORLD_SETTING_NOT_FOUND", f"世界观设定 {ws_id} 不存在")

        return envelope_response({"deleted": True})

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"删除世界观设定失败: {str(e)}")

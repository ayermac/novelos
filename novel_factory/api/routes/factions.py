"""Factions API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..envelope import envelope_response, error_response, EnvelopeResponse

router = APIRouter()


@router.get("/projects/{project_id}/factions")
async def list_factions(request: Request, project_id: str) -> EnvelopeResponse:
    """List all factions for a project."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        project = repo.get_project(project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        factions = repo.list_factions(project_id)
        return envelope_response(factions)

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取势力列表失败: {str(e)}")


@router.get("/projects/{project_id}/factions/{faction_id}")
async def get_faction(
    request: Request, project_id: str, faction_id: int
) -> EnvelopeResponse:
    """Get a specific faction."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        faction = repo.get_faction(project_id, faction_id)
        if not faction:
            return error_response("FACTION_NOT_FOUND", f"势力 {faction_id} 不存在")

        return envelope_response(faction)

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取势力详情失败: {str(e)}")


@router.post("/projects/{project_id}/factions")
async def create_faction(request: Request, project_id: str) -> EnvelopeResponse:
    """Create a new faction."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        project = repo.get_project(project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        body = await request.json()
        name = body.get("name", "")

        if not name:
            return error_response("VALIDATION_ERROR", "势力名称不能为空")

        faction = repo.create_faction(
            project_id=project_id,
            name=name,
            type=body.get("type", ""),
            description=body.get("description", ""),
            relationship_with_protagonist=body.get("relationship_with_protagonist", ""),
        )

        return envelope_response(faction)

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"创建势力失败: {str(e)}")


@router.put("/projects/{project_id}/factions/{faction_id}")
async def update_faction(
    request: Request, project_id: str, faction_id: int
) -> EnvelopeResponse:
    """Update a faction."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        existing = repo.get_faction(project_id, faction_id)
        if not existing:
            return error_response("FACTION_NOT_FOUND", f"势力 {faction_id} 不存在")

        body = await request.json()
        data = {}
        for key in ("name", "type", "description", "relationship_with_protagonist"):
            if key in body:
                data[key] = body[key]

        if not data:
            return envelope_response(existing)

        faction = repo.update_faction(project_id, faction_id, data)
        return envelope_response(faction)

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"更新势力失败: {str(e)}")


@router.delete("/projects/{project_id}/factions/{faction_id}")
async def delete_faction(
    request: Request, project_id: str, faction_id: int
) -> EnvelopeResponse:
    """Delete a faction."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        deleted = repo.delete_faction(project_id, faction_id)
        if not deleted:
            return error_response("FACTION_NOT_FOUND", f"势力 {faction_id} 不存在")

        return envelope_response({"deleted": True})

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"删除势力失败: {str(e)}")

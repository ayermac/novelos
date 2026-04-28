"""Characters API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..envelope import envelope_response, error_response, EnvelopeResponse

router = APIRouter()


@router.get("/projects/{project_id}/characters")
async def list_characters(request: Request, project_id: str) -> EnvelopeResponse:
    """List all characters for a project."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        # Verify project exists
        project = repo.get_project(project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        # Check for include_inactive query param
        include_inactive = request.query_params.get("include_inactive", "false").lower() == "true"
        characters = repo.list_characters(project_id, include_inactive=include_inactive)

        return envelope_response(characters)

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取角色列表失败: {str(e)}")


@router.get("/projects/{project_id}/characters/{char_id}")
async def get_character(
    request: Request, project_id: str, char_id: int
) -> EnvelopeResponse:
    """Get a specific character."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        character = repo.get_character(project_id, char_id)
        if not character:
            return error_response("CHARACTER_NOT_FOUND", f"角色 {char_id} 不存在")

        return envelope_response(character)

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取角色失败: {str(e)}")


@router.post("/projects/{project_id}/characters")
async def create_character(request: Request, project_id: str) -> EnvelopeResponse:
    """Create a new character."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        # Verify project exists
        project = repo.get_project(project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        # Parse request body
        body = await request.json()
        name = body.get("name", "")
        role = body.get("role", "supporting")
        description = body.get("description", "")
        alias = body.get("alias", "")
        first_appearance = body.get("first_appearance")

        if not name:
            return error_response("VALIDATION_ERROR", "角色名称不能为空")

        # Validate role
        valid_roles = ("protagonist", "antagonist", "supporting")
        if role not in valid_roles:
            return error_response("VALIDATION_ERROR", f"角色类型必须是: {', '.join(valid_roles)}")

        character = repo.create_character(
            project_id=project_id,
            name=name,
            role=role,
            description=description,
            alias=alias,
            first_appearance=first_appearance,
        )

        return envelope_response(character)

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"创建角色失败: {str(e)}")


@router.put("/projects/{project_id}/characters/{char_id}")
async def update_character(
    request: Request, project_id: str, char_id: int
) -> EnvelopeResponse:
    """Update a character."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        # Verify character exists
        existing = repo.get_character(project_id, char_id)
        if not existing:
            return error_response("CHARACTER_NOT_FOUND", f"角色 {char_id} 不存在")

        # Parse request body
        body = await request.json()
        data = {}
        for key in ("name", "alias", "role", "description", "first_appearance", "status"):
            if key in body:
                data[key] = body[key]

        if not data:
            return envelope_response(existing)

        # Validate role if provided
        if "role" in data:
            valid_roles = ("protagonist", "antagonist", "supporting")
            if data["role"] not in valid_roles:
                return error_response("VALIDATION_ERROR", f"角色类型必须是: {', '.join(valid_roles)}")

        character = repo.update_character(project_id, char_id, data)
        return envelope_response(character)

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"更新角色失败: {str(e)}")


@router.delete("/projects/{project_id}/characters/{char_id}")
async def delete_character(
    request: Request, project_id: str, char_id: int
) -> EnvelopeResponse:
    """Delete a character."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        deleted = repo.delete_character(project_id, char_id)
        if not deleted:
            return error_response("CHARACTER_NOT_FOUND", f"角色 {char_id} 不存在")

        return envelope_response({"deleted": True})

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"删除角色失败: {str(e)}")

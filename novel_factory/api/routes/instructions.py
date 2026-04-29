"""Chapter instructions API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..envelope import envelope_response, error_response, EnvelopeResponse

router = APIRouter()


@router.get("/projects/{project_id}/instructions")
async def list_instructions(request: Request, project_id: str) -> EnvelopeResponse:
    """List all instructions for a project."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        project = repo.get_project(project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        instructions = repo.list_instructions(project_id)
        return envelope_response(instructions)

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取章节指令列表失败: {str(e)}")


@router.get("/projects/{project_id}/instructions/{instruction_id}")
async def get_instruction(
    request: Request, project_id: str, instruction_id: int
) -> EnvelopeResponse:
    """Get a specific instruction."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        instruction = repo.get_instruction_by_id(project_id, instruction_id)
        if not instruction:
            return error_response("INSTRUCTION_NOT_FOUND", f"章节指令 {instruction_id} 不存在")

        return envelope_response(instruction)

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取章节指令详情失败: {str(e)}")


@router.post("/projects/{project_id}/instructions")
async def create_instruction(request: Request, project_id: str) -> EnvelopeResponse:
    """Create a new instruction."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        project = repo.get_project(project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        body = await request.json()
        chapter_number = body.get("chapter_number")

        if chapter_number is None:
            return error_response("VALIDATION_ERROR", "章节号不能为空")

        instruction_id = repo.create_instruction(
            project_id=project_id,
            chapter_number=int(chapter_number),
            objective=body.get("objective", ""),
            key_events=body.get("key_events", ""),
            plots_to_resolve=body.get("plots_to_resolve", ""),
            plots_to_plant=body.get("plots_to_plant", ""),
            emotion_tone=body.get("emotion_tone", ""),
            ending_hook=body.get("ending_hook", ""),
            word_target=body.get("word_target"),
            status=body.get("status", "pending"),
        )

        instruction = repo.get_instruction_by_id(project_id, instruction_id)
        return envelope_response(instruction)

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"创建章节指令失败: {str(e)}")


@router.put("/projects/{project_id}/instructions/{instruction_id}")
async def update_instruction(
    request: Request, project_id: str, instruction_id: int
) -> EnvelopeResponse:
    """Update an instruction."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        existing = repo.get_instruction_by_id(project_id, instruction_id)
        if not existing:
            return error_response("INSTRUCTION_NOT_FOUND", f"章节指令 {instruction_id} 不存在")

        body = await request.json()
        data = {}
        for key in ("chapter_number", "objective", "key_events", "plots_to_resolve",
                     "plots_to_plant", "emotion_tone", "ending_hook", "word_target", "status"):
            if key in body:
                data[key] = body[key]

        if not data:
            return envelope_response(existing)

        instruction = repo.update_instruction(project_id, instruction_id, data)
        return envelope_response(instruction)

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"更新章节指令失败: {str(e)}")


@router.delete("/projects/{project_id}/instructions/{instruction_id}")
async def delete_instruction(
    request: Request, project_id: str, instruction_id: int
) -> EnvelopeResponse:
    """Delete an instruction."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)

        deleted = repo.delete_instruction(project_id, instruction_id)
        if not deleted:
            return error_response("INSTRUCTION_NOT_FOUND", f"章节指令 {instruction_id} 不存在")

        return envelope_response({"deleted": True})

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"删除章节指令失败: {str(e)}")

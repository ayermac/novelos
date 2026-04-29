"""Project context status API endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..envelope import envelope_response, error_response, EnvelopeResponse

router = APIRouter()

# Map Chinese missing labels from context_readiness to frontend module paths
_MISSING_TO_MODULE = {
    "项目简介": "settings",
    "世界观设定": "worldview",
    "主角角色": "characters",
    "大纲": "outline",
    "写作指令": "instructions",
    "目标字数": "settings",
}


@router.get("/projects/{project_id}/context-status")
async def get_context_status(request: Request, project_id: str) -> EnvelopeResponse:
    """Get project context readiness status.

    Returns readiness score, missing items, and actionable suggestions.
    Uses the same logic as the Context Readiness Gate (validators/context_readiness.py).
    """
    from ..deps import get_repo
    from ...validators.context_readiness import check_context_readiness

    try:
        repo = get_repo(request)

        project = repo.get_project(project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        world_settings = repo.list_world_settings(project_id)
        characters = repo.list_characters(project_id, include_inactive=True)
        outlines = repo.list_outlines(project_id)
        instruction = repo.get_instruction_by_chapter(project_id, 1)

        result = check_context_readiness(
            project=project,
            world_settings=world_settings,
            characters=characters,
            outlines=outlines,
            instruction=instruction,
            chapter_number=1,
            chapter_status=None,
        )

        # Build actionable suggestions with frontend paths
        actions = []
        for item in result.missing:
            # Try prefix match for items like "第N章大纲"
            module = None
            for label, mod in _MISSING_TO_MODULE.items():
                if item.startswith(label) or item == label:
                    module = mod
                    break
            if module is None:
                module = "settings"

            actions.append({
                "label": item,
                "path": f"/projects/{project_id}?module={module}",
            })

        total_checks = 6
        passed = total_checks - len(result.missing)
        score = round(passed / total_checks * 100)

        return envelope_response({
            "ready": result.ready,
            "score": score,
            "missing": result.missing,
            "actions": actions,
            "details": result.details,
        })

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取上下文状态失败: {str(e)}")

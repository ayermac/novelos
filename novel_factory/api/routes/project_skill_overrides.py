"""Project-specific skill override API endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from ..envelope import envelope_response, error_response, EnvelopeResponse

router = APIRouter()


class UpdateProjectSkillOverridesRequest(BaseModel):
    """Replace a project's skill override document."""

    overrides: dict[str, Any] = Field(default_factory=dict)


def _normalize_overrides(overrides: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize override document shape for API responses and runtime use."""
    if not isinstance(overrides, dict):
        overrides = {}

    skills = overrides.get("skills", {})
    if not isinstance(skills, dict):
        skills = {}

    agent_skills = overrides.get("agent_skills", {})
    if not isinstance(agent_skills, dict):
        agent_skills = {}

    knowledge_skills = overrides.get("knowledge_skills", {})
    if not isinstance(knowledge_skills, dict):
        knowledge_skills = {}

    normalized = dict(overrides)
    normalized["skills"] = skills
    normalized["agent_skills"] = agent_skills
    normalized["knowledge_skills"] = knowledge_skills
    return normalized


@router.get("/projects/{project_id}/skill-overrides")
async def get_project_skill_overrides(
    request: Request,
    project_id: str,
) -> EnvelopeResponse:
    """Return the project-level skill override document."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)
        project = repo.get_project(project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        data = repo.get_project_skill_overrides(project_id)
        overrides = _normalize_overrides(data.get("overrides"))
        skills = overrides.get("skills", {})
        agent_skills = overrides.get("agent_skills", {})
        knowledge_skills = overrides.get("knowledge_skills", {})

        return envelope_response({
            "project_id": project_id,
            "overrides": overrides,
            "skills_count": len(skills) if isinstance(skills, dict) else 0,
            "agent_count": len(agent_skills) if isinstance(agent_skills, dict) else 0,
            "knowledge_skills_count": len(knowledge_skills) if isinstance(knowledge_skills, dict) else 0,
            "has_overrides": bool(skills or agent_skills or knowledge_skills),
            "updated_at": data.get("updated_at", ""),
        })
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取项目 Skill 覆盖失败: {str(e)}")


@router.put("/projects/{project_id}/skill-overrides")
async def update_project_skill_overrides(
    request: Request,
    project_id: str,
    body: UpdateProjectSkillOverridesRequest,
) -> EnvelopeResponse:
    """Replace the project-level skill override document."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)
        project = repo.get_project(project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        overrides = _normalize_overrides(body.overrides)
        ok = repo.save_project_skill_overrides(project_id, overrides)
        if not ok:
            return error_response("UPDATE_FAILED", "保存项目 Skill 覆盖失败")

        return envelope_response({
            "project_id": project_id,
            "overrides": overrides,
            "skills_count": len(overrides.get("skills", {})),
            "agent_count": len(overrides.get("agent_skills", {})),
            "knowledge_skills_count": len(overrides.get("knowledge_skills", {})),
            "has_overrides": bool(
                overrides.get("skills")
                or overrides.get("agent_skills")
                or overrides.get("knowledge_skills")
            ),
        })
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"保存项目 Skill 覆盖失败: {str(e)}")


@router.delete("/projects/{project_id}/skill-overrides")
async def clear_project_skill_overrides(
    request: Request,
    project_id: str,
) -> EnvelopeResponse:
    """Clear all project-level skill overrides."""
    from ..deps import get_repo

    try:
        repo = get_repo(request)
        project = repo.get_project(project_id)
        if not project:
            return error_response("PROJECT_NOT_FOUND", f"项目 '{project_id}' 不存在")

        ok = repo.save_project_skill_overrides(project_id, {})
        if not ok:
            return error_response("UPDATE_FAILED", "清空项目 Skill 覆盖失败")

        return envelope_response({
            "project_id": project_id,
            "overrides": {"skills": {}, "agent_skills": {}, "knowledge_skills": {}},
            "skills_count": 0,
            "agent_count": 0,
            "knowledge_skills_count": 0,
            "has_overrides": False,
        })
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"清空项目 Skill 覆盖失败: {str(e)}")

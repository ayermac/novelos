"""Skill visibility API endpoints.

v5.3.3: Read-only skill visibility — no config writes, no enable/disable,
no import, no run/test.
"""

from __future__ import annotations

from fastapi import APIRouter

from ..envelope import envelope_response, error_response, EnvelopeResponse

router = APIRouter()


def _get_registry():
    """Get a fresh SkillRegistry instance."""
    from ...skills.registry import SkillRegistry

    return SkillRegistry()


def _build_mounted_lookup(agent_skills: dict) -> dict[str, list[dict]]:
    """Build a lookup of skill_id -> list of mount points.

    Returns:
        Dict mapping skill_id to list of {"agent": str, "stage": str}.
    """
    mounted: dict[str, list[dict]] = {}
    for agent, stages in agent_skills.items():
        for stage, skill_ids in stages.items():
            for skill_id in skill_ids:
                mounted.setdefault(skill_id, []).append(
                    {"agent": agent, "stage": stage}
                )
    return mounted


@router.get("/skills")
async def list_skills() -> EnvelopeResponse:
    """List all configured skills with manifest and mount info."""
    try:
        registry = _get_registry()
        skills = registry.list_skills()
        mounted_lookup = _build_mounted_lookup(registry.agent_skills)

        for skill in skills:
            skill_id = skill["id"]
            skill["mounted_to"] = mounted_lookup.get(skill_id, [])
            skill["is_mounted"] = skill_id in mounted_lookup

        return envelope_response({"skills": skills})
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取 Skill 列表失败: {str(e)}")


@router.get("/skills/mounts")
async def get_skill_mounts() -> EnvelopeResponse:
    """Get structured agent/stage skill mount relationships."""
    try:
        registry = _get_registry()
        return envelope_response(registry.agent_skills)
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取挂载关系失败: {str(e)}")


@router.get("/skills/{skill_id}")
async def get_skill(skill_id: str) -> EnvelopeResponse:
    """Get single skill detail including manifest and mount info."""
    try:
        registry = _get_registry()

        if skill_id not in registry.skills_config:
            return error_response("RESOURCE_NOT_FOUND", f"Skill 不存在: {skill_id}")

        manifest = registry.get_manifest(skill_id)
        skill_config = registry.skills_config[skill_id]
        mounted_lookup = _build_mounted_lookup(registry.agent_skills)

        if manifest:
            data = {
                "id": skill_id,
                "name": manifest.name,
                "version": manifest.version,
                "kind": manifest.kind,
                "type": manifest.kind,
                "enabled": skill_config.get("enabled", True) and manifest.enabled,
                "builtin": manifest.builtin,
                "class_name": manifest.class_name,
                "class": manifest.class_name,
                "description": manifest.description,
                "allowed_agents": manifest.allowed_agents,
                "allowed_stages": manifest.allowed_stages,
                "permissions": manifest.permissions.model_dump(),
                "failure_policy": manifest.failure_policy.model_dump(),
                "input_schema": manifest.input_schema,
                "output_schema": manifest.output_schema,
                "config_schema": manifest.config_schema,
                "default_config": manifest.default_config,
                "package": skill_config.get("package"),
                "manifest": True,
                "mounted_to": mounted_lookup.get(skill_id, []),
                "is_mounted": skill_id in mounted_lookup,
            }
        else:
            # v2.1 compatibility
            data = {
                "id": skill_id,
                "name": skill_config.get("description", ""),
                "version": None,
                "kind": skill_config.get("type"),
                "type": skill_config.get("type"),
                "enabled": skill_config.get("enabled", True),
                "builtin": True,
                "class_name": skill_config.get("class"),
                "class": skill_config.get("class"),
                "description": skill_config.get("description", ""),
                "allowed_agents": [],
                "allowed_stages": [],
                "permissions": {},
                "failure_policy": {},
                "input_schema": {},
                "output_schema": {},
                "config_schema": {},
                "default_config": {},
                "package": skill_config.get("package"),
                "manifest": False,
                "mounted_to": mounted_lookup.get(skill_id, []),
                "is_mounted": skill_id in mounted_lookup,
            }

        return envelope_response(data)
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取 Skill 详情失败: {str(e)}")


@router.post("/skills/validate")
async def validate_skills() -> EnvelopeResponse:
    """Validate all skill configurations."""
    try:
        registry = _get_registry()
        result = registry.validate_all()

        return envelope_response({
            "ok": result.get("ok", False),
            "errors": result.get("errors", []),
            "warnings": result.get("warnings", []),
        })
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"验证 Skill 配置失败: {str(e)}")

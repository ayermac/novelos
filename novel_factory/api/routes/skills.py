"""Skill visibility API endpoints.

v5.3.3: Read-only skill visibility — no config writes, no enable/disable,
no import, no run/test.
v5.3.4: Add test bench endpoints for fixtures testing and manual skill runs.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from ..envelope import envelope_response, error_response, EnvelopeResponse

router = APIRouter()


class SkillTestRequest(BaseModel):
    """Skill test request."""

    skill_id: str | None = None
    all: bool = False


class SkillRunRequest(BaseModel):
    """Skill run request."""

    skill_id: str
    text: str | None = None
    payload: dict[str, Any] | None = None


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


@router.post("/skills/test")
async def test_skills(body: SkillTestRequest) -> EnvelopeResponse:
    """Run fixtures tests for skills.

    Args:
        body: SkillTestRequest with skill_id or all flag.

    Returns:
        Envelope with total/passed/failed and per-skill results.
    """
    try:
        registry = _get_registry()

        if not body.all and not body.skill_id:
            return error_response(
                "VALIDATION_ERROR",
                "请提供 skill_id 或设置 all=true",
            )

        if body.all:
            skills = registry.list_skills()
            package_skills = [s for s in skills if s.get("package")]

            all_results: dict[str, dict] = {}
            total_passed = 0
            total_failed = 0

            for skill_info in package_skills:
                sid = skill_info["id"]
                result = registry.test_skill(sid)
                all_results[sid] = result
                if result.get("ok"):
                    total_passed += 1
                else:
                    total_failed += 1

            return envelope_response({
                "total": len(package_skills),
                "passed": total_passed,
                "failed": total_failed,
                "results": all_results,
            })

        # Single skill test
        sid = body.skill_id
        if sid not in registry.skills_config:
            return error_response("RESOURCE_NOT_FOUND", f"Skill 不存在: {sid}")

        result = registry.test_skill(sid)
        return envelope_response({
            "skill_id": sid,
            "result": result,
        })

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"Skill 测试失败: {str(e)}")


@router.post("/skills/run")
async def run_skill(body: SkillRunRequest) -> EnvelopeResponse:
    """Run a skill manually with text or custom payload.

    Does NOT write to the database. Does NOT expose secrets.
    """
    try:
        registry = _get_registry()

        if body.skill_id not in registry.skills_config:
            return error_response(
                "RESOURCE_NOT_FOUND",
                f"Skill 不存在: {body.skill_id}",
            )

        payload: dict[str, Any] = {}
        if body.text is not None:
            payload["text"] = body.text
        if body.payload is not None:
            payload.update(body.payload)

        result = registry.run_skill(
            body.skill_id,
            payload,
            agent="manual",
            stage="manual",
        )

        return envelope_response({
            "skill_id": body.skill_id,
            "result": result,
        })

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"Skill 运行失败: {str(e)}")

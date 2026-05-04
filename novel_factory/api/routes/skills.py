"""Skill visibility API endpoints.

v5.3.3: Read-only skill visibility — no config writes, no enable/disable,
no import, no run/test.
v5.3.4: Add test bench endpoints for fixtures testing and manual skill runs.
v5.4.6: Add skill mount configuration console endpoints.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
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


class MountSkillRequest(BaseModel):
    """Mount skill request."""

    agent: str
    stage: str
    skill_id: str
    position: int | None = None


class UnmountSkillRequest(BaseModel):
    """Unmount skill request."""

    agent: str
    stage: str
    skill_id: str


class ReorderSkillsRequest(BaseModel):
    """Reorder skills request."""

    agent: str
    stage: str
    skill_ids: list[str]


def _get_registry(request: Request):
    """Get a fresh SkillRegistry instance.

    Uses app.state.skills_config_path if available for safe test isolation.
    """
    from ...skills.registry import SkillRegistry

    config_path = getattr(request.app.state, "skills_config_path", None)
    if config_path:
        return SkillRegistry(config_path=config_path)
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


KNOWN_AGENT_STAGES = {
    "planner": ["before_llm", "after_llm", "before_save"],
    "screenwriter": ["before_llm", "after_llm", "before_save"],
    "author": ["before_llm", "after_llm", "before_save"],
    "polisher": ["after_llm", "before_save"],
    "editor": ["before_review"],
    "memory_curator": ["before_extract", "after_extract", "before_save"],
}


def _skill_summary(skill: dict[str, Any] | None, skill_id: str) -> dict[str, Any]:
    """Return compact skill metadata for matrix cells."""
    if not skill:
        return {
            "id": skill_id,
            "name": None,
            "enabled": False,
            "missing": True,
            "package": None,
            "legacy": False,
            "kind": None,
        }

    return {
        "id": skill_id,
        "name": skill.get("name") or skill.get("description") or skill_id,
        "enabled": skill.get("enabled", True),
        "missing": False,
        "package": skill.get("package"),
        "legacy": not bool(skill.get("package")),
        "kind": skill.get("kind") or skill.get("type"),
    }


def _build_agent_matrix(registry) -> dict[str, Any]:
    """Build read-only agent/stage skill matrix with validation hints."""
    skills = registry.list_skills()
    skill_by_id = {s["id"]: s for s in skills}
    mounted_lookup = _build_mounted_lookup(registry.agent_skills)
    warnings: list[dict[str, Any]] = []
    agents: list[dict[str, Any]] = []

    configured_agents = set(registry.agent_skills.keys())
    known_agents = list(KNOWN_AGENT_STAGES.keys())
    extra_agents = sorted(configured_agents - set(known_agents))

    for agent in known_agents + extra_agents:
        configured_stages = registry.agent_skills.get(agent, {})
        known_stages = KNOWN_AGENT_STAGES.get(agent, [])
        stage_names = list(dict.fromkeys([*known_stages, *configured_stages.keys()]))
        stage_rows: list[dict[str, Any]] = []

        if agent in configured_agents and agent not in KNOWN_AGENT_STAGES:
            warnings.append({
                "code": "UNKNOWN_AGENT",
                "agent": agent,
                "message": f"未知 Agent 挂载配置: {agent}",
            })

        for stage in stage_names:
            skill_ids = configured_stages.get(stage, [])
            stage_warnings: list[dict[str, Any]] = []

            if known_stages and stage not in known_stages:
                warning = {
                    "code": "UNKNOWN_STAGE",
                    "agent": agent,
                    "stage": stage,
                    "message": f"{agent}.{stage} 不是已知 stage",
                }
                stage_warnings.append(warning)
                warnings.append(warning)

            skill_rows = []
            for skill_id in skill_ids:
                skill = skill_by_id.get(skill_id)
                summary = _skill_summary(skill, skill_id)
                skill_rows.append(summary)

                if summary["missing"]:
                    warning = {
                        "code": "MISSING_SKILL",
                        "agent": agent,
                        "stage": stage,
                        "skill_id": skill_id,
                        "message": f"{agent}.{stage} 挂载了不存在的 Skill: {skill_id}",
                    }
                    stage_warnings.append(warning)
                    warnings.append(warning)
                elif not summary["enabled"]:
                    warning = {
                        "code": "MOUNTED_DISABLED_SKILL",
                        "agent": agent,
                        "stage": stage,
                        "skill_id": skill_id,
                        "message": f"{agent}.{stage} 挂载了已禁用 Skill: {skill_id}",
                    }
                    stage_warnings.append(warning)
                    warnings.append(warning)

            stage_rows.append({
                "stage": stage,
                "skill_ids": skill_ids,
                "skills": skill_rows,
                "warnings": stage_warnings,
            })

        agents.append({
            "agent": agent,
            "stages": stage_rows,
        })

    unmounted_enabled = [
        _skill_summary(skill, skill["id"])
        for skill in skills
        if skill.get("enabled", True) and skill["id"] not in mounted_lookup
    ]
    for skill in unmounted_enabled:
        warnings.append({
            "code": "ENABLED_UNMOUNTED_SKILL",
            "skill_id": skill["id"],
            "message": f"Skill 已启用但未挂载: {skill['id']}",
        })

    return {
        "agents": agents,
        "unmounted_enabled_skills": unmounted_enabled,
        "warnings": warnings,
    }


def _build_config_view(registry) -> dict[str, Any]:
    """Build the skill configuration view for the config endpoint."""
    skills = registry.list_skills()
    skill_by_id = {s["id"]: s for s in skills}
    mounted_lookup = _build_mounted_lookup(registry.agent_skills)

    # Determine source info for each skill
    available_skills = []
    for skill in skills:
        info = {
            "id": skill["id"],
            "name": skill.get("name") or skill.get("description") or skill["id"],
            "enabled": skill.get("enabled", True),
            "kind": skill.get("kind") or skill.get("type"),
            "package": skill.get("package"),
            "legacy": not bool(skill.get("package")),
            "class_name": skill.get("class_name") or skill.get("class"),
        }
        available_skills.append(info)

    # Find missing configured skills
    missing_skills = []
    for agent, stages in registry.agent_skills.items():
        for stage, skill_ids in stages.items():
            for skill_id in skill_ids:
                if skill_id not in skill_by_id:
                    missing_skills.append({
                        "id": skill_id,
                        "agent": agent,
                        "stage": stage,
                    })

    # Find disabled skills
    disabled_skills = [
        {
            "id": skill["id"],
            "name": skill.get("name") or skill.get("description") or skill["id"],
        }
        for skill in skills
        if not skill.get("enabled", True)
    ]

    return {
        "agents": list(KNOWN_AGENT_STAGES.keys()),
        "stages": KNOWN_AGENT_STAGES,
        "agent_skills": registry.agent_skills,
        "available_skills": available_skills,
        "missing_skills": missing_skills,
        "disabled_skills": disabled_skills,
        "config_path": str(registry.config_path),
        "total_skills": len(skills),
        "total_mounted": sum(
            len(skill_ids)
            for stages in registry.agent_skills.values()
            for skill_ids in stages.values()
        ),
    }


@router.get("/skills")
async def list_skills(request: Request) -> EnvelopeResponse:
    """List all configured skills with manifest and mount info."""
    try:
        registry = _get_registry(request)
        skills = registry.list_skills()
        mounted_lookup = _build_mounted_lookup(registry.agent_skills)

        for skill in skills:
            skill_id = skill["id"]
            skill["mounted_to"] = mounted_lookup.get(skill_id, [])
            skill["is_mounted"] = skill_id in mounted_lookup

        return envelope_response({"skills": skills})
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取 Skill 列表失败: {str(e)}")


@router.get("/skills/config")
async def get_skill_config(request: Request) -> EnvelopeResponse:
    """Get current skill configuration view with mount state."""
    try:
        registry = _get_registry(request)
        return envelope_response(_build_config_view(registry))
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取 Skill 配置失败: {str(e)}")


@router.get("/skills/mounts")
async def get_skill_mounts(request: Request) -> EnvelopeResponse:
    """Get structured agent/stage skill mount relationships."""
    try:
        registry = _get_registry(request)
        return envelope_response(registry.agent_skills)
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取挂载关系失败: {str(e)}")


@router.get("/skills/agent-matrix")
async def get_agent_skill_matrix(request: Request) -> EnvelopeResponse:
    """Get read-only agent/stage skill matrix with validation hints."""
    try:
        registry = _get_registry(request)
        return envelope_response(_build_agent_matrix(registry))
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取 Agent Skill Matrix 失败: {str(e)}")


@router.get("/skills/{skill_id}")
async def get_skill(skill_id: str, request: Request) -> EnvelopeResponse:
    """Get single skill detail including manifest and mount info."""
    try:
        registry = _get_registry(request)

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


@router.post("/skills/mount")
async def mount_skill(body: MountSkillRequest, request: Request) -> EnvelopeResponse:
    """Mount a skill to an agent/stage."""
    try:
        registry = _get_registry(request)

        # Validate agent/stage existence (allow dynamic agents if configured)
        if body.agent not in KNOWN_AGENT_STAGES and body.agent not in registry.agent_skills:
            return error_response(
                "VALIDATION_ERROR",
                f"Agent '{body.agent}' 不是已知 agent，且尚未有任何挂载配置",
            )

        ok, msg = registry.mount_skill(body.agent, body.stage, body.skill_id)
        if not ok:
            return error_response("VALIDATION_ERROR", msg)

        # Handle optional position
        if body.position is not None:
            stage_skills = registry.agent_skills.get(body.agent, {}).get(body.stage, [])
            if body.skill_id in stage_skills:
                stage_skills.remove(body.skill_id)
                pos = max(0, min(body.position, len(stage_skills)))
                stage_skills.insert(pos, body.skill_id)

        registry.save_config()

        return envelope_response({
            "agent": body.agent,
            "stage": body.stage,
            "skill_id": body.skill_id,
            "source": str(registry.config_path),
        })
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"挂载 Skill 失败: {str(e)}")


@router.delete("/skills/mount")
async def unmount_skill(body: UnmountSkillRequest, request: Request) -> EnvelopeResponse:
    """Unmount a skill from an agent/stage."""
    try:
        registry = _get_registry(request)

        ok, msg = registry.unmount_skill(body.agent, body.stage, body.skill_id)
        if not ok:
            return error_response("VALIDATION_ERROR", msg)

        registry.save_config()

        return envelope_response({
            "agent": body.agent,
            "stage": body.stage,
            "skill_id": body.skill_id,
            "source": str(registry.config_path),
        })
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"卸载 Skill 失败: {str(e)}")


@router.post("/skills/reorder")
async def reorder_skills(body: ReorderSkillsRequest, request: Request) -> EnvelopeResponse:
    """Reorder skills for an agent/stage."""
    try:
        registry = _get_registry(request)

        ok, msg = registry.reorder_skills(body.agent, body.stage, body.skill_ids)
        if not ok:
            return error_response("VALIDATION_ERROR", msg)

        registry.save_config()

        return envelope_response({
            "agent": body.agent,
            "stage": body.stage,
            "skill_ids": registry.agent_skills.get(body.agent, {}).get(body.stage, []),
            "source": str(registry.config_path),
        })
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"重排 Skill 失败: {str(e)}")


@router.post("/skills/validate")
async def validate_skills(request: Request) -> EnvelopeResponse:
    """Validate all skill configurations."""
    try:
        registry = _get_registry(request)
        result = registry.validate_all()

        return envelope_response({
            "ok": result.get("ok", False),
            "errors": result.get("errors", []),
            "warnings": result.get("warnings", []),
        })
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"验证 Skill 配置失败: {str(e)}")


@router.post("/skills/test")
async def test_skills(body: SkillTestRequest, request: Request) -> EnvelopeResponse:
    """Run fixtures tests for skills.

    Args:
        body: SkillTestRequest with skill_id or all flag.

    Returns:
        Envelope with total/passed/failed and per-skill results.
    """
    try:
        registry = _get_registry(request)

        if not body.all and not body.skill_id:
            return error_response(
                "VALIDATION_ERROR",
                "请提供 skill_id 或设置 all=true",
            )

        if body.all:
            skills = registry.list_skills()
            package_skills = [s for s in skills if s.get("package")]
            skipped = [s["id"] for s in skills if not s.get("package")]

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
                "skipped": len(skipped),
                "skipped_ids": skipped,
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
async def run_skill(body: SkillRunRequest, request: Request) -> EnvelopeResponse:
    """Run a skill manually with text or custom payload.

    Does NOT write to the database. Does NOT expose secrets.
    """
    try:
        registry = _get_registry(request)

        if body.skill_id not in registry.skills_config:
            return error_response(
                "RESOURCE_NOT_FOUND",
                f"Skill 不存在: {body.skill_id}",
            )

        has_text = body.text is not None and body.text.strip()
        has_payload = body.payload is not None and bool(body.payload)

        if not has_text and not has_payload:
            return error_response(
                "VALIDATION_ERROR",
                "请提供有效的 text 或 payload",
            )

        payload: dict[str, Any] = {}
        if has_text:
            payload["text"] = body.text
        if has_payload:
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

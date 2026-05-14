"""Skill visibility API endpoints.

v5.3.3: Read-only skill visibility — no config writes, no enable/disable,
no import, no run/test.
v5.3.4: Add test bench endpoints for fixtures testing and manual skill runs.
v5.4.6: Add skill mount configuration console endpoints.
v5.4.7: Add read-only OpenClaw legacy Skill import readiness endpoint.
v5.4.8: Add universal Skill import readiness and plan preview endpoints.
v5.4.9: Add safe universal Skill import apply endpoint.
v5.4.10: Add skill enable/disable configuration endpoint.
v5.4.11: Add skill safety review and mount activation guard.
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


class SkillEnabledRequest(BaseModel):
    """Skill enabled flag update request."""

    skill_id: str
    enabled: bool


class SkillReviewRequest(BaseModel):
    """Skill safety review request."""

    skill_id: str
    agent: str | None = None
    stage: str | None = None


class SkillImportPlanRequest(BaseModel):
    """Universal skill import plan preview request."""

    source_type: str
    source_path: str


class SkillImportApplyRequest(BaseModel):
    """Universal skill import apply request."""

    source_type: str
    source_path: str
    skill_id: str | None = None
    force: bool = False


class OpenClawImportPlanRequest(BaseModel):
    """Backward-compatible OpenClaw import plan preview request."""

    source_path: str


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
        "legacy": not bool(skill.get("package") or skill.get("has_manifest")),
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

    # Determine source info for each skill
    available_skills = []
    for skill in skills:
        allowed_targets = _skill_allowed_targets(registry, skill["id"])
        info = {
            "id": skill["id"],
            "name": skill.get("name") or skill.get("description") or skill["id"],
            "enabled": skill.get("enabled", True),
            "kind": skill.get("kind") or skill.get("type"),
            "package": skill.get("package"),
            "legacy": not bool(skill.get("package") or skill.get("has_manifest")),
            "class_name": skill.get("class_name") or skill.get("class"),
            "allowed_targets": allowed_targets,
            "mountable_targets": _skill_mountable_targets(registry, skill["id"], allowed_targets),
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


def _finding(severity: str, code: str, message: str) -> dict[str, str]:
    """Build a compact skill safety finding."""
    return {
        "severity": severity,
        "code": code,
        "message": message,
    }


def _all_known_mount_targets() -> list[dict[str, str]]:
    """Return all production targets known to the WebUI mount console."""
    return [
        {"agent": agent, "stage": stage}
        for agent, stages in KNOWN_AGENT_STAGES.items()
        for stage in stages
    ]


def _skill_allowed_targets(registry, skill_id: str) -> list[dict[str, str]]:
    """Return manifest-declared allowed mount targets for a skill."""
    if skill_id not in registry.skills_config:
        return []

    manifest = registry.get_manifest(skill_id)
    if not manifest:
        # Legacy skills have no manifest constraints. Keep them available, but
        # the safety review will warn that their metadata is incomplete.
        return _all_known_mount_targets()

    targets = [
        target
        for target in _all_known_mount_targets()
        if target["agent"] in manifest.allowed_agents
        and target["stage"] in manifest.allowed_stages
    ]
    if "manual" in manifest.allowed_agents and "manual" in manifest.allowed_stages:
        targets.append({"agent": "manual", "stage": "manual"})
    return targets


def _skill_mountable_targets(
    registry,
    skill_id: str,
    allowed_targets: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    """Return currently mountable production targets after safety review."""
    targets = allowed_targets if allowed_targets is not None else _skill_allowed_targets(registry, skill_id)
    mountable = []
    for target in targets:
        if target["agent"] == "manual" and target["stage"] == "manual":
            mountable.append(target)
            continue
        review = _evaluate_skill_safety(registry, skill_id, target["agent"], target["stage"])
        if review["verdict"] != "block":
            mountable.append(target)
    return mountable


def _evaluate_skill_safety(
    registry,
    skill_id: str,
    agent: str | None = None,
    stage: str | None = None,
) -> dict[str, Any]:
    """Evaluate safety for a skill against an optional target."""
    findings: list[dict[str, str]] = []
    recommended_actions: list[str] = []

    skill_config = registry.skills_config.get(skill_id)
    if not skill_config:
        return {
            "skill_id": skill_id,
            "agent": agent,
            "stage": stage,
            "verdict": "block",
            "allowed_targets": [],
            "mountable_targets": [],
            "findings": [_finding("block", "SKILL_NOT_FOUND", f"Skill 不存在: {skill_id}")],
            "recommended_actions": ["确认 skill_id 是否正确，或先导入/register 该 Skill。"],
        }

    enabled = skill_config.get("enabled", True)
    package_path = skill_config.get("package")
    is_imported = bool(skill_config.get("_imported") or skill_config.get("class") == "ImportedInstructionSkill")
    manifest = registry.get_manifest(skill_id)
    if not enabled:
        severity = "block" if agent and stage else "warn"
        findings.append(_finding(severity, "SKILL_DISABLED", f"Skill 已禁用: {skill_id}"))
        recommended_actions.append("先启用 Skill，再挂载到工作流。")

    if package_path:
        manifest_path = registry._resolve_package_manifest_path(package_path)
        if not manifest_path:
            findings.append(_finding("block", "INVALID_PACKAGE_PATH", f"Skill package path 无效: {package_path}"))
            recommended_actions.append("修复 skills.yaml 中的 package 路径，或重新导入该 Skill。")
        else:
            package_dir = manifest_path.parent
            if not (package_dir / "handler.py").exists():
                findings.append(_finding("block", "MISSING_HANDLER", "Skill package 缺少 handler.py"))
                recommended_actions.append("重新生成 Skill package，或补齐 handler.py。")
            if not (package_dir / "tests" / "fixtures.yaml").exists():
                findings.append(_finding("warn", "MISSING_FIXTURES", "Skill package 缺少 fixtures 测试"))
                recommended_actions.append("补齐 fixtures 后再将该 Skill 用于生产工作流。")
    else:
        findings.append(_finding("warn", "LEGACY_SKILL", "Skill 未使用 package manifest，安全信息不完整"))
        recommended_actions.append("优先迁移为 package Skill，以便执行 manifest 权限和 stage 校验。")

    if not manifest:
        if package_path:
            findings.append(_finding("block", "MISSING_MANIFEST", "Skill package manifest 无法加载"))
            recommended_actions.append("修复 manifest.yaml，或重新导入该 Skill。")
    else:
        if is_imported:
            findings.append(_finding("warn", "IMPORTED_SKILL", "导入 Skill 默认只适合手动审阅/测试"))
            recommended_actions.append("如需进入生产工作流，请先审查 handler、permissions 和 allowed_agents/stages。")

        permissions = manifest.permissions
        risky_permissions = []
        if permissions.call_network:
            risky_permissions.append("call_network")
        if permissions.call_llm:
            risky_permissions.append("call_llm")
        if permissions.write_chapter_content:
            risky_permissions.append("write_chapter_content")
        if permissions.update_chapter_status:
            risky_permissions.append("update_chapter_status")
        if risky_permissions:
            findings.append(_finding("block", "RISKY_PERMISSIONS", f"Skill 声明高风险权限: {', '.join(risky_permissions)}"))
            recommended_actions.append("移除高风险权限，或为该 Skill 增加专门沙箱/审批流程。")

        if agent and stage:
            allowed, msg = registry.validate_skill_for_agent(skill_id, agent, stage)
            if not allowed:
                findings.append(_finding("block", "AGENT_STAGE_NOT_ALLOWED", msg))
                recommended_actions.append("选择 manifest 允许的 agent/stage，或先更新并审查 manifest。")

    severities = {finding["severity"] for finding in findings}
    if "block" in severities:
        verdict = "block"
    elif "warn" in severities:
        verdict = "warn"
    else:
        verdict = "pass"

    if not recommended_actions:
        recommended_actions.append("可以继续启用或挂载。")

    return {
        "skill_id": skill_id,
        "agent": agent,
        "stage": stage,
        "verdict": verdict,
        "enabled": enabled,
        "package": package_path,
        "imported": is_imported,
        "manifest": bool(manifest),
        "findings": findings,
        "recommended_actions": list(dict.fromkeys(recommended_actions)),
    }


def _skill_safety_review(
    registry,
    skill_id: str,
    agent: str | None = None,
    stage: str | None = None,
) -> dict[str, Any]:
    """Review whether a skill is safe to enable or mount."""
    review = _evaluate_skill_safety(registry, skill_id, agent, stage)
    review["allowed_targets"] = _skill_allowed_targets(registry, skill_id)
    review["mountable_targets"] = _skill_mountable_targets(
        registry,
        skill_id,
        review["allowed_targets"],
    )
    return review


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


@router.get("/skills/openclaw-readiness")
async def get_openclaw_readiness(request: Request) -> EnvelopeResponse:
    """Scan local OpenClaw legacy skills for import readiness.

    Read-only: does not import, copy, enable, mount, or execute anything.
    """
    try:
        from ...skills.openclaw_readiness import scan_openclaw_readiness

        root = getattr(request.app.state, "openclaw_root_path", None)
        return envelope_response(scan_openclaw_readiness(root))
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"扫描 OpenClaw Skill 失败: {str(e)}")


@router.get("/skills/import-readiness")
async def get_import_readiness(request: Request) -> EnvelopeResponse:
    """Scan universal local Skill sources for import readiness.

    Read-only: does not import, copy, enable, mount, or execute anything.
    """
    try:
        from ...skills.openclaw_readiness import scan_import_readiness

        root = getattr(request.app.state, "openclaw_root_path", None)
        return envelope_response(scan_import_readiness(openclaw_root=root))
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"扫描 Skill 导入候选失败: {str(e)}")


@router.post("/skills/import-plan")
async def get_import_plan(body: SkillImportPlanRequest, request: Request) -> EnvelopeResponse:
    """Build a read-only import plan preview for any local Skill candidate."""
    try:
        from ...skills.openclaw_readiness import build_import_plan_preview

        root = getattr(request.app.state, "openclaw_root_path", None)
        plan = build_import_plan_preview(body.source_type, body.source_path, openclaw_root=root)
        if not plan.get("ok"):
            return error_response("VALIDATION_ERROR", str(plan.get("error") or "生成导入计划失败"))
        return envelope_response(plan.get("data", {}))
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"生成 Skill 导入计划失败: {str(e)}")


@router.post("/skills/import-apply")
async def apply_import(body: SkillImportApplyRequest, request: Request) -> EnvelopeResponse:
    """Safely import a local Skill candidate as disabled and unmounted."""
    try:
        from pathlib import Path

        from ...skills.openclaw_readiness import apply_import_candidate, build_import_plan_preview

        registry = _get_registry(request)
        root = getattr(request.app.state, "openclaw_root_path", None)
        package_root = registry.config_path.parent.parent / "skill_packages"

        plan = build_import_plan_preview(body.source_type, body.source_path, openclaw_root=root)
        if not plan.get("ok"):
            return error_response("VALIDATION_ERROR", str(plan.get("error") or "生成导入计划失败"))

        plan_data = plan.get("data", {})
        target = plan_data.get("target", {}) if isinstance(plan_data, dict) else {}
        skill_id = body.skill_id or target.get("skill_id")
        if not skill_id:
            return error_response("VALIDATION_ERROR", "skill_id is required")

        ok, msg = registry.can_register_imported_skill(skill_id, force=body.force)
        if not ok:
            return error_response("VALIDATION_ERROR", msg)

        result = apply_import_candidate(
            source_type=body.source_type,
            source_path=body.source_path,
            skill_id=skill_id,
            force=body.force,
            openclaw_root=root,
            package_root=package_root,
        )
        if not result.get("ok"):
            return error_response("VALIDATION_ERROR", str(result.get("error") or "导入 Skill 失败"))

        data = result.get("data", {})
        package_dir = Path(data.get("package_dir", ""))
        package_path = f"skill_packages/{package_dir.name}"
        description = ""
        detected = plan_data.get("detected", {}) if isinstance(plan_data, dict) else {}
        if isinstance(detected, dict):
            description = str(detected.get("description") or "")

        ok, msg = registry.register_imported_skill(
            skill_id=skill_id,
            package_path=package_path,
            description=description,
            force=body.force,
        )
        if not ok:
            return error_response("VALIDATION_ERROR", msg)
        registry.save_config()

        data["package"] = package_path
        data["registered"] = True
        data["enabled"] = False
        data["mounted"] = False
        data["config_path"] = str(registry.config_path)
        return envelope_response(data)
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"导入 Skill 失败: {str(e)}")


@router.post("/skills/openclaw-import-plan")
async def get_openclaw_import_plan(body: OpenClawImportPlanRequest, request: Request) -> EnvelopeResponse:
    """Build a read-only import plan preview for an OpenClaw candidate."""
    try:
        from ...skills.openclaw_readiness import build_openclaw_import_plan

        root = getattr(request.app.state, "openclaw_root_path", None)
        plan = build_openclaw_import_plan(body.source_path, root)
        if not plan.get("ok"):
            return error_response("VALIDATION_ERROR", str(plan.get("error") or "生成导入计划失败"))
        return envelope_response(plan.get("data", {}))
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"生成 Skill 导入计划失败: {str(e)}")


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


@router.post("/skills/enabled")
async def set_skill_enabled(body: SkillEnabledRequest, request: Request) -> EnvelopeResponse:
    """Enable or disable a skill without changing mounts."""
    try:
        registry = _get_registry(request)

        ok, msg = registry.set_skill_enabled(body.skill_id, body.enabled)
        if not ok:
            return error_response("VALIDATION_ERROR", msg)

        registry.save_config()

        mounted_lookup = _build_mounted_lookup(registry.agent_skills)
        return envelope_response({
            "skill_id": body.skill_id,
            "enabled": body.enabled,
            "mounted_to": mounted_lookup.get(body.skill_id, []),
            "is_mounted": body.skill_id in mounted_lookup,
            "source": str(registry.config_path),
        })
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"更新 Skill 启用状态失败: {str(e)}")


@router.post("/skills/review")
async def review_skill(body: SkillReviewRequest, request: Request) -> EnvelopeResponse:
    """Review skill safety before enabling or mounting."""
    try:
        registry = _get_registry(request)

        if (body.agent and not body.stage) or (body.stage and not body.agent):
            return error_response("VALIDATION_ERROR", "agent 和 stage 必须同时提供")

        if body.agent in KNOWN_AGENT_STAGES and body.stage not in KNOWN_AGENT_STAGES[body.agent]:
            known = ", ".join(KNOWN_AGENT_STAGES[body.agent])
            return envelope_response({
                "skill_id": body.skill_id,
                "agent": body.agent,
                "stage": body.stage,
                "verdict": "block",
                "enabled": registry.is_skill_enabled(body.skill_id),
                "package": registry.skills_config.get(body.skill_id, {}).get("package"),
                "imported": bool(registry.skills_config.get(body.skill_id, {}).get("_imported")),
                "manifest": bool(registry.get_manifest(body.skill_id)) if body.skill_id in registry.skills_config else False,
                "allowed_targets": [],
                "mountable_targets": [],
                "findings": [
                    _finding(
                        "block",
                        "UNKNOWN_STAGE",
                        f"Stage '{body.stage}' 不是 agent '{body.agent}' 的已知 stage。已知: {known}",
                    )
                ],
                "recommended_actions": ["选择已知 stage，避免生成不会执行的死配置。"],
            })

        return envelope_response(_skill_safety_review(registry, body.skill_id, body.agent, body.stage))
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"审查 Skill 失败: {str(e)}")


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

        # Validate stage for known agents to prevent dead config
        if body.agent in KNOWN_AGENT_STAGES and body.stage not in KNOWN_AGENT_STAGES[body.agent]:
            known = ", ".join(KNOWN_AGENT_STAGES[body.agent])
            return error_response(
                "VALIDATION_ERROR",
                f"Stage '{body.stage}' 不是 agent '{body.agent}' 的已知 stage。已知: {known}",
            )

        review = _skill_safety_review(registry, body.skill_id, body.agent, body.stage)
        if review["verdict"] == "block":
            finding_messages = [finding["message"] for finding in review["findings"] if finding["severity"] == "block"]
            return error_response(
                "VALIDATION_ERROR",
                finding_messages[0] if finding_messages else "Skill 安全审查未通过",
                details={"review": review},
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

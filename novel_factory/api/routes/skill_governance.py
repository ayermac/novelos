"""Skill governance API endpoints (v6.10.2)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from ..envelope import EnvelopeResponse, envelope_response

router = APIRouter(prefix="/skill-governance", tags=["skill-governance"])


def _get_registry(request: Request):
    from ...skills.registry import SkillRegistry

    config_path = getattr(request.app.state, "skills_config_path", None)
    if config_path:
        return SkillRegistry(config_path=config_path)
    return SkillRegistry()


def _get_knowledge_manager(request: Request):
    km = getattr(request.app.state, "knowledge_manager", None)
    if km:
        return km

    from pathlib import Path
    from ...skills.knowledge_manager import KnowledgeManager

    knowledge_dir = str(Path(__file__).resolve().parents[2] / "skills" / "knowledge")
    return KnowledgeManager(knowledge_dir=knowledge_dir)


def _knowledge_summary(skill: Any) -> dict[str, Any]:
    return {
        "skill_id": skill.skill_id,
        "qualified_id": skill.qualified_id,
        "name": skill.name,
        "description": skill.description,
        "enabled": skill.enabled,
        "layer": skill.layer,
        "category": skill.category,
        "paired_code_skill_ids": skill.paired_code_skill_ids,
        "default_agents": skill.default_agents,
        "editable": skill.editable,
        "priority": skill.priority,
        "token_budget": skill.token_budget,
        "injection_mode": skill.injection_mode,
        "applicable_agents": skill.applicable_agents,
        "applicable_genres": skill.applicable_genres,
        "version": skill.version,
        "source": skill.source,
    }


@router.get("", response_model=EnvelopeResponse)
async def get_skill_governance(request: Request) -> EnvelopeResponse:
    """Return read-only Code/Knowledge Skill governance metadata."""
    registry = _get_registry(request)
    knowledge_manager = _get_knowledge_manager(request)

    code_skills = registry.list_skills()
    knowledge_skills = [_knowledge_summary(skill) for skill in knowledge_manager.list_all()]
    knowledge_by_id = {skill["skill_id"]: skill for skill in knowledge_skills}

    pairings: list[dict[str, Any]] = []
    for code_skill in code_skills:
        for knowledge_id in code_skill.get("knowledge_skill_ids", []) or []:
            pairings.append({
                "code_skill_id": code_skill["id"],
                "knowledge_skill_id": knowledge_id,
                "reciprocal": code_skill["id"] in knowledge_by_id.get(knowledge_id, {}).get("paired_code_skill_ids", []),
                "dedupe_group": code_skill.get("dedupe_group", ""),
                "severity_default": code_skill.get("severity_default", "blocking"),
            })

    return envelope_response({
        "code_skills": code_skills,
        "knowledge_skills": knowledge_skills,
        "pairings": pairings,
        "validation": registry.validate_all(),
        "counts": {
            "code": len(code_skills),
            "knowledge": len(knowledge_skills),
            "pairings": len(pairings),
        },
    })

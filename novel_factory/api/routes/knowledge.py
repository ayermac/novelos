"""Knowledge Skill API endpoints (v6.10.0)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..envelope import EnvelopeResponse, envelope_response

router = APIRouter(prefix="/knowledge-skills", tags=["knowledge"])


# ── Request/Response models ──────────────────────────────────


class KnowledgeSkillMeta(BaseModel):
    skill_id: str
    namespace: str = "knowledge"
    qualified_id: str = ""
    name: str
    description: str
    enabled: bool = True
    priority: int = 50
    token_budget: int = 1200
    injection_mode: str = "auto"
    tags: list[str] = Field(default_factory=list)
    applicable_agents: list[str] = Field(default_factory=list)
    applicable_genres: list[str] = Field(default_factory=list)
    version: str = "1.0"
    source: str = "builtin"


class KnowledgeSkillDetail(KnowledgeSkillMeta):
    content: str = ""


class KnowledgeSkillCreate(BaseModel):
    skill_id: str
    name: str
    description: str
    content: str
    tags: list[str] = Field(default_factory=list)
    applicable_agents: list[str] = Field(default_factory=list)
    applicable_genres: list[str] = Field(default_factory=list)
    enabled: bool = True
    priority: int = 50
    token_budget: int = 1200
    injection_mode: str = "auto"


class KnowledgeSkillUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    content: str | None = None
    tags: list[str] | None = None
    applicable_agents: list[str] | None = None
    applicable_genres: list[str] | None = None
    enabled: bool | None = None
    priority: int | None = None
    token_budget: int | None = None
    injection_mode: str | None = None


class KnowledgeSkillSelectionPreview(BaseModel):
    agent_id: str
    genre: str | None = None
    token_budget: int | None = None
    target: str = "prompt"
    quality_signals: list[str] = Field(default_factory=list)
    project_overrides: dict[str, Any] = Field(default_factory=dict)


# ── Dependency ────────────────────────────────────────────────


def _get_km(request: Request) -> Any:
    """Get KnowledgeManager from app state."""
    km = getattr(request.app.state, "knowledge_manager", None)
    if not km:
        raise HTTPException(status_code=503, detail="KnowledgeManager not initialized")
    return km


def _skill_to_dict(skill: Any, *, include_content: bool = False) -> dict[str, Any]:
    data = {
        "skill_id": skill.skill_id,
        "namespace": getattr(skill, "namespace", "knowledge"),
        "qualified_id": getattr(skill, "qualified_id", f"knowledge:{skill.skill_id}"),
        "name": skill.name,
        "description": skill.description,
        "enabled": getattr(skill, "enabled", True),
        "priority": getattr(skill, "priority", 50),
        "token_budget": getattr(skill, "token_budget", 1200),
        "injection_mode": getattr(skill, "injection_mode", "auto"),
        "tags": skill.tags,
        "applicable_agents": skill.applicable_agents,
        "applicable_genres": skill.applicable_genres,
        "version": skill.version,
        "source": skill.source,
    }
    if include_content:
        data["content"] = skill.content
    return data


# ── Endpoints ─────────────────────────────────────────────────


@router.get("", response_model=EnvelopeResponse)
async def list_knowledge_skills(request: Request) -> EnvelopeResponse:
    """List all knowledge skills."""
    km = _get_km(request)
    return envelope_response([_skill_to_dict(s) for s in km.list_all()])


@router.get("/agent/{agent_id}", response_model=EnvelopeResponse)
async def get_knowledge_skills_for_agent(
    request: Request, agent_id: str, genre: str | None = None
) -> EnvelopeResponse:
    """Get knowledge skills available for a specific agent."""
    km = _get_km(request)
    skills = km.get_for_agent(agent_id, genre=genre)
    return envelope_response([_skill_to_dict(s) for s in skills])


@router.post("/select", response_model=EnvelopeResponse)
async def preview_knowledge_selection(
    request: Request,
    body: KnowledgeSkillSelectionPreview,
) -> EnvelopeResponse:
    """Preview Knowledge Skill selection with budget and reasons."""
    km = _get_km(request)
    selection = km.select_for_agent(
        body.agent_id,
        genre=body.genre,
        project_overrides=body.project_overrides,
        token_budget=body.token_budget,
        target=body.target,
        quality_signals=body.quality_signals,
    )
    payload = selection.to_audit_payload(agent=body.agent_id, genre=body.genre)
    payload["skills"] = [_skill_to_dict(s) for s in selection.skills]
    return envelope_response(payload)


@router.get("/{skill_id}", response_model=EnvelopeResponse)
async def get_knowledge_skill(request: Request, skill_id: str) -> EnvelopeResponse:
    """Get a single knowledge skill with content."""
    km = _get_km(request)
    skill = km.get(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Knowledge skill '{skill_id}' not found")
    return envelope_response(_skill_to_dict(skill, include_content=True))


@router.post("", response_model=EnvelopeResponse, status_code=201)
async def create_knowledge_skill(request: Request, body: KnowledgeSkillCreate) -> EnvelopeResponse:
    """Create a new knowledge skill."""
    km = _get_km(request)
    existing = km.get(body.skill_id)
    if existing:
        raise HTTPException(status_code=409, detail=f"Knowledge skill '{body.skill_id}' already exists")

    skill = km.create_skill(
        skill_id=body.skill_id,
        name=body.name,
        description=body.description,
        content=body.content,
        tags=body.tags,
        applicable_agents=body.applicable_agents,
        applicable_genres=body.applicable_genres,
        enabled=body.enabled,
        priority=body.priority,
        token_budget=body.token_budget,
        injection_mode=body.injection_mode,
    )
    return envelope_response(_skill_to_dict(skill, include_content=True))


@router.put("/{skill_id}", response_model=EnvelopeResponse)
async def update_knowledge_skill(
    request: Request, skill_id: str, body: KnowledgeSkillUpdate
) -> EnvelopeResponse:
    """Update a knowledge skill."""
    km = _get_km(request)
    skill = km.update_skill(
        skill_id=skill_id,
        name=body.name,
        description=body.description,
        content=body.content,
        tags=body.tags,
        applicable_agents=body.applicable_agents,
        applicable_genres=body.applicable_genres,
        enabled=body.enabled,
        priority=body.priority,
        token_budget=body.token_budget,
        injection_mode=body.injection_mode,
    )
    if not skill:
        raise HTTPException(status_code=404, detail=f"Knowledge skill '{skill_id}' not found")
    return envelope_response(_skill_to_dict(skill, include_content=True))


@router.delete("/{skill_id}", response_model=EnvelopeResponse)
async def delete_knowledge_skill(request: Request, skill_id: str) -> EnvelopeResponse:
    """Delete a knowledge skill."""
    km = _get_km(request)
    if not km.delete_skill(skill_id):
        raise HTTPException(status_code=404, detail=f"Knowledge skill '{skill_id}' not found")
    return envelope_response({"deleted": True, "skill_id": skill_id})

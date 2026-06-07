"""Knowledge Skill API endpoints (v6.10.0)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

router = APIRouter(prefix="/knowledge-skills", tags=["knowledge"])


# ── Request/Response models ──────────────────────────────────


class KnowledgeSkillMeta(BaseModel):
    skill_id: str
    name: str
    description: str
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


class KnowledgeSkillUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    content: str | None = None
    tags: list[str] | None = None
    applicable_agents: list[str] | None = None
    applicable_genres: list[str] | None = None


# ── Dependency ────────────────────────────────────────────────


def _get_km(request: Any) -> Any:
    """Get KnowledgeManager from app state."""
    km = getattr(request.app.state, "knowledge_manager", None)
    if not km:
        raise HTTPException(status_code=503, detail="KnowledgeManager not initialized")
    return km


# ── Endpoints ─────────────────────────────────────────────────


@router.get("", response_model=list[KnowledgeSkillMeta])
async def list_knowledge_skills(request: Any) -> list[dict[str, Any]]:
    """List all knowledge skills."""
    km = _get_km(request)
    return [
        {
            "skill_id": s.skill_id,
            "name": s.name,
            "description": s.description,
            "tags": s.tags,
            "applicable_agents": s.applicable_agents,
            "applicable_genres": s.applicable_genres,
            "version": s.version,
            "source": s.source,
        }
        for s in km.list_all()
    ]


@router.get("/{skill_id}", response_model=KnowledgeSkillDetail)
async def get_knowledge_skill(request: Any, skill_id: str) -> dict[str, Any]:
    """Get a single knowledge skill with content."""
    km = _get_km(request)
    skill = km.get(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Knowledge skill '{skill_id}' not found")
    return {
        "skill_id": skill.skill_id,
        "name": skill.name,
        "description": skill.description,
        "content": skill.content,
        "tags": skill.tags,
        "applicable_agents": skill.applicable_agents,
        "applicable_genres": skill.applicable_genres,
        "version": skill.version,
        "source": skill.source,
    }


@router.post("", response_model=KnowledgeSkillDetail, status_code=201)
async def create_knowledge_skill(request: Any, body: KnowledgeSkillCreate) -> dict[str, Any]:
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
    )
    return {
        "skill_id": skill.skill_id,
        "name": skill.name,
        "description": skill.description,
        "content": skill.content,
        "tags": skill.tags,
        "applicable_agents": skill.applicable_agents,
        "applicable_genres": skill.applicable_genres,
        "version": skill.version,
        "source": skill.source,
    }


@router.put("/{skill_id}", response_model=KnowledgeSkillDetail)
async def update_knowledge_skill(
    request: Any, skill_id: str, body: KnowledgeSkillUpdate
) -> dict[str, Any]:
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
    )
    if not skill:
        raise HTTPException(status_code=404, detail=f"Knowledge skill '{skill_id}' not found")
    return {
        "skill_id": skill.skill_id,
        "name": skill.name,
        "description": skill.description,
        "content": skill.content,
        "tags": skill.tags,
        "applicable_agents": skill.applicable_agents,
        "applicable_genres": skill.applicable_genres,
        "version": skill.version,
        "source": skill.source,
    }


@router.delete("/{skill_id}")
async def delete_knowledge_skill(request: Any, skill_id: str) -> Response:
    """Delete a knowledge skill."""
    km = _get_km(request)
    if not km.delete_skill(skill_id):
        raise HTTPException(status_code=404, detail=f"Knowledge skill '{skill_id}' not found")
    return Response(status_code=204)


@router.get("/agent/{agent_id}", response_model=list[KnowledgeSkillMeta])
async def get_knowledge_skills_for_agent(
    request: Any, agent_id: str, genre: str | None = None
) -> list[dict[str, Any]]:
    """Get knowledge skills available for a specific agent."""
    km = _get_km(request)
    skills = km.get_for_agent(agent_id, genre=genre)
    return [
        {
            "skill_id": s.skill_id,
            "name": s.name,
            "description": s.description,
            "tags": s.tags,
            "applicable_agents": s.applicable_agents,
            "applicable_genres": s.applicable_genres,
            "version": s.version,
            "source": s.source,
        }
        for s in skills
    ]

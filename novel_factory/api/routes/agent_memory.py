"""API routes for Agent Memory management."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from ..deps import get_repo

router = APIRouter(prefix="/agent-memory", tags=["agent-memory"])


@router.get("/{project_id}")
def list_agent_memories(
    project_id: str,
    request: Request,
    agent_id: str | None = None,
    memory_type: str | None = None,
) -> dict[str, Any]:
    repo = get_repo(request)
    items = repo.list_agent_memories(project_id, agent_id=agent_id, memory_type=memory_type)
    return {"ok": True, "data": {"items": items, "count": len(items)}}


@router.post("/{project_id}")
def create_agent_memory(
    project_id: str,
    payload: dict[str, Any],
    request: Request,
) -> dict[str, Any]:
    repo = get_repo(request)
    try:
        item = repo.create_agent_memory(
            project_id=project_id,
            agent_id=payload["agent_id"],
            memory_type=payload["memory_type"],
            key=payload["key"],
            value=payload.get("value", {}),
            confidence=payload.get("confidence", 1.0),
            source_run_id=payload.get("source_run_id"),
            source_chapter_number=payload.get("source_chapter_number"),
        )
    except KeyError as e:
        raise HTTPException(status_code=400, detail=f"Missing field: {e.args[0]}") from e
    return {"ok": True, "data": item}


@router.patch("/{memory_id}/enable")
def enable_agent_memory(
    memory_id: int,
    request: Request,
) -> dict[str, Any]:
    repo = get_repo(request)
    ok = repo.set_agent_memory_enabled(memory_id, True)
    return {"ok": ok}


@router.patch("/{memory_id}/disable")
def disable_agent_memory(
    memory_id: int,
    request: Request,
) -> dict[str, Any]:
    repo = get_repo(request)
    ok = repo.set_agent_memory_enabled(memory_id, False)
    return {"ok": ok}


@router.delete("/{memory_id}")
def delete_agent_memory(
    memory_id: int,
    request: Request,
) -> dict[str, Any]:
    repo = get_repo(request)
    ok = repo.delete_agent_memory(memory_id)
    return {"ok": ok}

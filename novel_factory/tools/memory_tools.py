"""Internal tool handlers for agent memory and foreshadowing debt queries."""

from __future__ import annotations

from typing import Any


def handle_agent_memory_query(payload: dict[str, Any], repo: Any | None = None) -> dict[str, Any]:
    if repo is None:
        return {"error": "Repository not available"}
    project_id = payload.get("project_id", "")
    agent_id = payload.get("agent_id", "")
    try:
        items = repo.list_agent_memories(project_id, agent_id=agent_id or None, enabled_only=True)
        return {"ok": True, "count": len(items), "items": items}
    except Exception as e:
        return {"error": str(e)}


def handle_agent_memory_write(payload: dict[str, Any], repo: Any | None = None) -> dict[str, Any]:
    if repo is None:
        return {"error": "Repository not available"}
    try:
        item = repo.create_agent_memory(
            project_id=payload.get("project_id", ""),
            agent_id=payload.get("agent_id", ""),
            memory_type=payload.get("memory_type", "strategy_note"),
            key=payload.get("key", ""),
            value=payload.get("value", {}),
            confidence=payload.get("confidence", 1.0),
            source_run_id=payload.get("source_run_id"),
            source_chapter_number=payload.get("source_chapter_number"),
        )
        return {"ok": True, "item": item}
    except Exception as e:
        return {"error": str(e)}


def handle_foreshadowing_debt_report(payload: dict[str, Any], repo: Any | None = None) -> dict[str, Any]:
    if repo is None:
        return {"error": "Repository not available"}
    project_id = payload.get("project_id", "")
    try:
        pending = repo.get_pending_plots(project_id)
        total = len(pending) if pending else 0
        overdue = [p for p in (pending or []) if p.get("status") == "overdue"]
        return {
            "ok": True,
            "total_pending": total,
            "overdue_count": len(overdue),
            "overdue_plots": [{"code": p.get("code"), "title": p.get("title")} for p in overdue[:10]],
        }
    except Exception as e:
        return {"error": str(e)}

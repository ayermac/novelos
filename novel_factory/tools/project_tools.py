"""Internal tool handlers for project context queries."""

from __future__ import annotations

import json
from typing import Any


def handle_project_context_query(payload: dict[str, Any], repo: Any | None = None) -> dict[str, Any]:
    if repo is None:
        return {"error": "Repository not available"}
    project_id = payload.get("project_id", "")
    query = payload.get("query", "")

    result: dict[str, Any] = {"project_id": project_id, "query": query}

    # Characters
    try:
        chars = repo.get_characters(project_id)
        result["characters"] = [{"name": c.get("name"), "role": c.get("role")} for c in (chars or [])[:10]]
    except Exception:
        result["characters"] = []

    # World settings
    try:
        ws = repo.list_world_settings(project_id)
        result["world_settings"] = [{"title": w.get("title"), "category": w.get("category")} for w in (ws or [])[:10]]
    except Exception:
        result["world_settings"] = []

    # Pending plots
    try:
        plots = repo.get_pending_plots(project_id)
        result["pending_plots"] = [{"code": p.get("code"), "title": p.get("title")} for p in (plots or [])[:10]]
    except Exception:
        result["pending_plots"] = []

    # Story facts
    try:
        facts = repo.list_story_facts(project_id, status="active")
        result["story_facts"] = [{"key": f.get("fact_key"), "value": f.get("value_json")} for f in (facts or [])[:10]]
    except Exception:
        result["story_facts"] = []

    return result

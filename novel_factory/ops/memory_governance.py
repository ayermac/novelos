"""Project memory governance and context pressure audit."""

from __future__ import annotations

from collections import Counter
from typing import Any


DEFAULT_LIMITS = {
    "characters": 80,
    "story_facts": 160,
    "memory_items": 240,
    "context_chars": 48000,
}


def _safe_call(default: Any, fn, *args, **kwargs) -> Any:
    try:
        return fn(*args, **kwargs)
    except Exception:
        return default


def _norm(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _duplicate_values(items: list[str]) -> list[dict[str, Any]]:
    counts = Counter(item for item in items if item)
    return [
        {"value": value, "count": count}
        for value, count in sorted(counts.items())
        if count > 1
    ]


def audit_project_memory(
    repo: Any,
    project_id: str,
    *,
    limits: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Inspect project memory pressure without mutating the database."""
    limits = {**DEFAULT_LIMITS, **(limits or {})}
    characters = _safe_call([], repo.list_characters, project_id, include_inactive=True)
    story_facts = _safe_call([], repo.list_story_facts, project_id)
    memory_items = _safe_call([], repo.list_memory_items_by_project, project_id)

    character_names = [_norm(item.get("name")) for item in characters]
    fact_keys = [_norm(item.get("fact_key") or item.get("key")) for item in story_facts]
    fact_texts = [_norm(item.get("content") or item.get("value")) for item in story_facts]
    item_texts = [_norm(item.get("content") or item.get("value")) for item in memory_items]

    context_chars = sum(len(str(item)) for item in characters + story_facts + memory_items)
    duplicate_character_names = _duplicate_values(character_names)
    duplicate_fact_keys = _duplicate_values(fact_keys)
    duplicate_fact_texts = _duplicate_values(fact_texts)

    pressures = []
    if len(characters) > limits["characters"]:
        pressures.append({
            "name": "characters",
            "count": len(characters),
            "limit": limits["characters"],
            "message": "character count exceeds context planning threshold",
        })
    if len(story_facts) > limits["story_facts"]:
        pressures.append({
            "name": "story_facts",
            "count": len(story_facts),
            "limit": limits["story_facts"],
            "message": "story fact count exceeds context planning threshold",
        })
    if len(memory_items) > limits["memory_items"]:
        pressures.append({
            "name": "memory_items",
            "count": len(memory_items),
            "limit": limits["memory_items"],
            "message": "memory item count exceeds context planning threshold",
        })
    if context_chars > limits["context_chars"]:
        pressures.append({
            "name": "context_chars",
            "count": context_chars,
            "limit": limits["context_chars"],
            "message": "combined memory context is large enough to require pruning",
        })

    duplicate_groups = {
        "characters": duplicate_character_names[:20],
        "story_fact_keys": duplicate_fact_keys[:20],
        "story_fact_texts": duplicate_fact_texts[:20],
    }
    duplicate_count = sum(len(v) for v in duplicate_groups.values())
    warnings = []
    if pressures:
        warnings.append("context_pressure")
    if duplicate_count:
        warnings.append("duplicates")

    return {
        "ok": not warnings,
        "project_id": project_id,
        "counts": {
            "characters": len(characters),
            "story_facts": len(story_facts),
            "memory_items": len(memory_items),
            "context_chars": context_chars,
        },
        "limits": limits,
        "pressures": pressures,
        "duplicates": duplicate_groups,
        "duplicate_group_count": duplicate_count,
        "warnings": warnings,
        "next_actions": _next_actions(pressures, duplicate_count, item_texts),
    }


def _next_actions(pressures: list[dict[str, Any]], duplicate_count: int, item_texts: list[str]) -> list[str]:
    actions = []
    if pressures:
        actions.append("prune or summarize low-relevance memory before the next real-LLM run")
    if duplicate_count:
        actions.append("merge duplicate characters/story facts before long-form generation")
    if not any(item_texts):
        actions.append("run memory curator after terminal chapters to create trusted memory")
    return actions

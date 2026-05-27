"""Project memory governance and context pressure audit."""

from __future__ import annotations

from collections import Counter
from typing import Any


DEFAULT_LIMITS = {
    "characters": 80,
    "world_settings": 120,
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


def _duplicate_groups(
    items: list[dict[str, Any]],
    key_fn,
    table: str,
) -> list[dict[str, Any]]:
    """Build duplicate groups with ids and display values for each duplicate value.

    Args:
        items: List of dict items from repository (characters, world_settings, etc.)
        key_fn: Function to extract the comparison key from an item
        table: Table name for the group metadata

    Returns:
        List of group dicts with value, count, ids, display_values, table.
    """
    from collections import defaultdict

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        key = key_fn(item)
        if key:
            groups[key].append(item)

    result = []
    for value, group_items in sorted(groups.items()):
        if len(group_items) > 1:
            result.append({
                "value": value,
                "count": len(group_items),
                "table": table,
                "ids": [_safe_item_id(item) for item in group_items],
                "display_values": [_safe_display_value(item) for item in group_items],
            })
    return result


def _safe_item_id(item: dict[str, Any]) -> Any:
    """Safely extract id from item, returning None if unavailable."""
    return item.get("id") or item.get("character_id") or item.get("world_setting_id") or item.get("fact_id")


def _safe_display_value(item: dict[str, Any]) -> str:
    """Safely extract display value from item for human-readable reference."""
    return item.get("name") or item.get("title") or item.get("fact_key") or str(item.get("id", ""))


def audit_project_memory(
    repo: Any,
    project_id: str,
    *,
    limits: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Inspect project memory pressure without mutating the database."""
    limits = {**DEFAULT_LIMITS, **(limits or {})}
    characters = _safe_call([], repo.list_characters, project_id, include_inactive=True)
    world_settings = _safe_call([], repo.list_world_settings, project_id)
    story_facts = _safe_call([], repo.list_story_facts, project_id)
    memory_items = _safe_call([], repo.list_memory_items_by_project, project_id)

    character_names = [_norm(item.get("name")) for item in characters]
    world_titles = [_norm(item.get("title")) for item in world_settings]
    fact_keys = [_norm(item.get("fact_key") or item.get("key")) for item in story_facts]
    fact_texts = [_norm(item.get("content") or item.get("value")) for item in story_facts]
    item_texts = [_norm(item.get("content") or item.get("value")) for item in memory_items]

    context_chars = sum(len(str(item)) for item in characters + world_settings + story_facts + memory_items)
    duplicate_character_names = _duplicate_values(character_names)
    duplicate_world_titles = _duplicate_values(world_titles)
    duplicate_fact_keys = _duplicate_values(fact_keys)
    duplicate_fact_texts = _duplicate_values(fact_texts)

    # v6.7.3: Build detailed duplicate groups with ids and display values
    duplicate_character_groups = _duplicate_groups(
        characters, lambda item: _norm(item.get("name")), "characters"
    )
    duplicate_world_setting_groups = _duplicate_groups(
        world_settings, lambda item: _norm(item.get("title")), "world_settings"
    )

    pressures = []
    if len(characters) > limits["characters"]:
        pressures.append({
            "name": "characters",
            "count": len(characters),
            "limit": limits["characters"],
            "message": "character count exceeds context planning threshold",
        })
    if len(world_settings) > limits["world_settings"]:
        pressures.append({
            "name": "world_settings",
            "count": len(world_settings),
            "limit": limits["world_settings"],
            "message": "world setting count exceeds context planning threshold",
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
        "world_settings": duplicate_world_titles[:20],
        "story_fact_keys": duplicate_fact_keys[:20],
        "story_fact_texts": duplicate_fact_texts[:20],
    }
    # v6.7.3: Detailed duplicate groups with ids for UI navigation
    duplicate_groups_detailed = {
        "characters": duplicate_character_groups[:20],
        "world_settings": duplicate_world_setting_groups[:20],
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
            "world_settings": len(world_settings),
            "story_facts": len(story_facts),
            "memory_items": len(memory_items),
            "context_chars": context_chars,
        },
        "limits": limits,
        "pressures": pressures,
        "duplicates": duplicate_groups,
        "duplicate_groups": duplicate_groups_detailed,
        "duplicate_group_count": duplicate_count,
        "warnings": warnings,
        "next_actions": _next_actions(pressures, duplicate_count, item_texts),
    }


def _next_actions(pressures: list[dict[str, Any]], duplicate_count: int, item_texts: list[str]) -> list[str]:
    actions = []
    if pressures:
        actions.append("prune or summarize low-relevance memory before the next real-LLM run")
    if duplicate_count:
        actions.append("merge duplicate characters/world settings/story facts before long-form generation")
    if not any(item_texts):
        actions.append("run memory curator after terminal chapters to create trusted memory")
    return actions

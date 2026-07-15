"""Genesis draft normalization and parsing.

Handles parsing, normalizing, and deduplicating Genesis draft JSON output.
"""

from __future__ import annotations

import json
from .utils import _as_text, _merge_key_text


def _normalize_genesis_draft(value) -> dict | None:
    """Normalize provider draft output into the canonical genesis object shape."""
    if isinstance(value, dict):
        return value
    if not isinstance(value, list):
        return None

    grouped = {
        "world_settings": [],
        "characters": [],
        "factions": [],
        "outlines": [],
        "plot_holes": [],
        "instructions": [],
    }
    for item in value:
        if not isinstance(item, dict):
            continue
        keys = set(item.keys())
        if {"title", "category", "content"} <= keys:
            grouped["world_settings"].append(item)
        elif "chapter_number" in keys:
            grouped["instructions"].append(item)
        elif "chapters_range" in keys or {"level", "sequence", "content"} <= keys:
            grouped["outlines"].append(item)
        elif "code" in keys:
            grouped["plot_holes"].append(item)
        elif "relationship_with_protagonist" in keys or ("name" in keys and "type" in keys):
            grouped["factions"].append(item)
        elif "name" in keys:
            grouped["characters"].append(item)

    normalized = {key: items for key, items in grouped.items() if items}
    return normalized or None


def _world_setting_semantic_key(item: dict) -> str | None:
    """Collapse common Genesis worldbuilding duplicates into stable slots."""
    title = _as_text(item.get("title"))
    text = f"{title} {_as_text(item.get('category'))} {_as_text(item.get('content'))}"

    if "异常" in title and any(term in title for term in ("定义", "分类", "起源")):
        return "anomaly_definition"
    if "异常" in title and any(term in title for term in ("规律", "进化", "目的", "深层")):
        return "anomaly_pattern"
    if "异常处理局" in text or "国家异常事态处理局" in text:
        return "anomaly_bureau"
    if "修正系统" in text or "裁衡" in text:
        return "correction_system"
    if "同化" in title:
        return "assimilation"
    if "修正员" in title and any(term in title for term in ("等级", "能力", "体系")):
        return "corrector_capability"
    if "2056" in title or "世界" in title or "时代" in title or "社会" in title:
        return "era_background"
    return None


def _genesis_item_key(section: str, item, index: int) -> str:
    """Return a stable semantic key for a Genesis list item."""
    if not isinstance(item, dict):
        return f"raw:{index}:{_merge_key_text(item)[:80]}"

    if section == "world_settings":
        semantic_key = _world_setting_semantic_key(item)
        if semantic_key:
            return f"world:{semantic_key}"
        title = _merge_key_text(item.get("title"))
        category = _merge_key_text(item.get("category"))
        content = _merge_key_text(item.get("content"))
        return f"title:{category}:{title}" if title else f"content:{content[:100]}"

    if section in ("characters", "factions"):
        name = _merge_key_text(item.get("name"))
        return f"name:{name}" if name else f"idx:{index}"

    if section == "outlines":
        level = _merge_key_text(item.get("level", "arc"))
        sequence = item.get("sequence")
        if sequence not in (None, ""):
            return f"seq:{level}:{sequence}"
        chapters_range = _merge_key_text(item.get("chapters_range"))
        if chapters_range:
            return f"range:{chapters_range}"
        return f"title:{_merge_key_text(item.get('title'))}"

    if section == "plot_holes":
        code = _merge_key_text(item.get("code"))
        if code:
            return f"code:{code}"
        return f"title:{_merge_key_text(item.get('title'))}"

    if section == "instructions":
        chapter_number = item.get("chapter_number")
        if chapter_number not in (None, ""):
            try:
                return f"chapter:{int(chapter_number)}"
            except (TypeError, ValueError):
                return f"chapter:{_merge_key_text(chapter_number)}"
        return f"objective:{_merge_key_text(item.get('objective'))}"

    return f"idx:{index}"


def _merge_genesis_item(existing, incoming):
    """Merge duplicate Genesis items without letting empty incoming values erase data."""
    if not isinstance(existing, dict) or not isinstance(incoming, dict):
        return incoming if incoming not in (None, "", [], {}) else existing
    merged = dict(existing)
    for key, value in incoming.items():
        if value in (None, "", [], {}):
            continue
        merged[key] = value
    return merged


def _merge_unique_genesis_list(existing: list, incoming: list, section: str) -> list:
    """Merge Genesis list sections by semantic keys instead of blindly appending."""
    result: list = []
    key_to_index: dict[str, int] = {}

    for source in (existing or [], incoming or []):
        for item in source:
            key = _genesis_item_key(section, item, len(result) + 1)
            if key in key_to_index:
                idx = key_to_index[key]
                result[idx] = _merge_genesis_item(result[idx], item)
            else:
                key_to_index[key] = len(result)
                result.append(item)
    return result


def _dedupe_genesis_draft(draft: dict | None) -> dict | None:
    """Deduplicate all repeatable Genesis sections in a normalized draft."""
    if not isinstance(draft, dict):
        return draft
    deduped = dict(draft)
    for key in (
        "world_settings",
        "characters",
        "factions",
        "outlines",
        "plot_holes",
        "instructions",
    ):
        value = deduped.get(key)
        if isinstance(value, list):
            deduped[key] = _merge_unique_genesis_list([], value, key)
    return deduped


def _parse_genesis_draft_json(raw_value) -> dict | None:
    """Parse genesis draft_json into a JSON object.

    Historical/real-provider failures can leave draft_json double-encoded or
    shaped as a JSON string/list. Approval must reject those cleanly instead of
    failing later with "'str' object has no attribute 'get'" after partial work.
    """
    value = raw_value
    for _ in range(2):
        normalized = _normalize_genesis_draft(value)
        if normalized is not None:
            return _dedupe_genesis_draft(normalized)
        if isinstance(value, str):
            try:
                value = json.loads(value)
                continue
            except json.JSONDecodeError:
                return None
        return None
    return _dedupe_genesis_draft(_normalize_genesis_draft(value))
"""Genesis utility functions for type conversion and normalization."""

from __future__ import annotations

import json


def _as_text(value) -> str:
    """Normalize LLM scalar/list/dict output into DB-safe text."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _as_list(value) -> list:
    """Normalize free-form LLM list output into a list."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _as_int(value, fallback: int) -> int:
    """Normalize LLM numeric fields into an int."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _merge_key_text(value) -> str:
    """Normalize text for Genesis merge/dedup keys."""
    return " ".join(_as_text(value).split()).strip().lower()


def _short_title(text: str, fallback: str, limit: int = 24) -> str:
    """Create a compact title from free-form text."""
    clean = " ".join(_as_text(text).split())
    if not clean:
        return fallback
    return clean[:limit]
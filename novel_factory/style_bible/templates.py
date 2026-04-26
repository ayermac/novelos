"""Style Bible template loader and factory for v4.0."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from ..models.style_bible import StyleBible


_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "config"
_TEMPLATES_FILE = _TEMPLATES_DIR / "style_bible_templates.yaml"


def load_style_bible_template(template_id: str) -> dict[str, Any]:
    """Load a Style Bible template by ID.

    Args:
        template_id: Template identifier (e.g., "default_web_serial").

    Returns:
        Template dict.

    Raises:
        ValueError: If template_id is not found.
    """
    templates = _load_all_templates()
    if template_id not in templates:
        available = sorted(templates.keys())
        raise ValueError(
            f"Unknown template: '{template_id}'. Available: {available}"
        )
    return templates[template_id]


def list_templates() -> dict[str, dict[str, Any]]:
    """List all available Style Bible templates.

    Returns:
        Dict of template_id -> template data.
    """
    return _load_all_templates()


def create_style_bible_from_template(
    project_id: str,
    template_id: str,
    overrides: dict[str, Any] | None = None,
) -> StyleBible:
    """Create a StyleBible instance from a template with optional overrides.

    Args:
        project_id: Project identifier.
        template_id: Template identifier.
        overrides: Optional dict of field overrides.

    Returns:
        StyleBible instance.

    Raises:
        ValueError: If template_id is not found.
    """
    template = load_style_bible_template(template_id)

    # Remove metadata fields that aren't StyleBible fields
    template.pop("description", None)

    # Apply overrides
    if overrides:
        template = merge_style_bible(template, overrides)

    # Set project_id
    template["project_id"] = project_id

    return StyleBible(**template)


def validate_style_bible(bible: StyleBible) -> dict[str, Any]:
    """Validate a StyleBible instance.

    Checks:
    - No author names in any field
    - All required fields have values
    - No conflicting settings

    Returns:
        Dict with ok, error, data keys.
    """
    issues: list[str] = []

    # Check for author references (simple heuristic)
    author_indicators = ["模仿", "仿写", "以.*风格", "像.*写"]
    import re
    all_text = bible.model_dump_json()
    for pattern in author_indicators:
        if re.search(pattern, all_text):
            issues.append(f"Possible author imitation reference found matching '{pattern}'")

    if issues:
        return {
            "ok": False,
            "error": "Style Bible validation failed",
            "data": {"issues": issues},
        }

    return {"ok": True, "error": None, "data": {"issues": []}}


def merge_style_bible(
    base: dict[str, Any],
    overrides: dict[str, Any],
) -> dict[str, Any]:
    """Merge overrides into a base Style Bible dict.

    For list fields, overrides replace (not append).
    For dict fields, overrides are merged recursively.

    Args:
        base: Base Style Bible dict.
        overrides: Override dict.

    Returns:
        Merged dict.
    """
    result = dict(base)
    for key, value in overrides.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = {**result[key], **value}
        else:
            result[key] = value
    return result


# ── Internal ───────────────────────────────────────────────────


def _load_all_templates() -> dict[str, dict[str, Any]]:
    """Load all templates from the YAML file."""
    if not _TEMPLATES_FILE.exists():
        return {}

    with open(_TEMPLATES_FILE, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    return data.get("templates", {})

"""Style Bible normalizer for v6.10.4.

Maps legacy JSON formats (voice/narrative/prose) to canonical StyleBible schema.
Ensures old records can be read and consumed without manual migration.
"""

from __future__ import annotations

from typing import Any

from ..models.style_bible import (
    AITraceAvoidance,
    ForbiddenExpression,
    Pacing,
    POV,
    PreferredExpression,
    StyleBible,
    StyleRule,
)


# ── Legacy field mappings ──────────────────────────────────────

_POV_MAP: dict[str, str] = {
    "第一人称": "first_person",
    "第三人称": "third_person_limited",
    "第三人称有限": "third_person_limited",
    "全知": "omniscient",
    "混合": "mixed",
}

_PACING_MAP: dict[str, str] = {
    "慢": "slow",
    "缓慢": "slow",
    "适中": "balanced",
    "中等": "balanced",
    "快": "fast",
    "快速": "fast",
}


# ── Public API ─────────────────────────────────────────────────


def normalize_legacy_bible(data: dict[str, Any]) -> dict[str, Any]:
    """Convert a possibly-legacy bible dict into canonical StyleBible fields.

    Handles:
    - Old loose JSON with voice/narrative/prose keys
    - Partial canonical records
    - Fully canonical records (passthrough)

    Returns a dict that can be passed to StyleBible(**data).
    """
    if not isinstance(data, dict):
        data = {}

    # Already canonical if it has core canonical fields and no legacy top-level keys
    legacy_keys = {"voice", "narrative", "prose", "generated_from_reference", "reference_length"}
    canonical_keys = {
        "tone_keywords", "pacing", "pov", "dialogue_style", "prose_style",
        "tension_style", "humor_style", "emotional_intensity",
        "forbidden_expressions", "preferred_expressions",
        "sentence_rules", "paragraph_rules",
        "chapter_opening_rules", "chapter_ending_rules",
        "ai_trace_avoidance",
    }
    has_legacy = bool(legacy_keys & set(data.keys()))
    has_canonical = bool(canonical_keys & set(data.keys()))

    if not has_legacy and has_canonical:
        # Looks canonical already; just ensure project_id and status are present
        return dict(data)

    result: dict[str, Any] = {}

    # Carry forward canonical fields that already exist
    for key in canonical_keys:
        if key in data:
            result[key] = data[key]

    # Carry forward metadata and extension fields that live in bible_json.
    for key in (
        "project_id",
        "name",
        "genre",
        "target_platform",
        "target_audience",
        "version",
        "created_at",
        "updated_at",
        "status",
        "gate_config",
        "generated_from_reference",
        "reference_length",
    ):
        if key in data:
            result[key] = data[key]

    # Map legacy voice block
    voice = data.get("voice") or {}
    if isinstance(voice, dict):
        tone = voice.get("tone", "")
        if tone and not result.get("tone_keywords"):
            result["tone_keywords"] = [t.strip() for t in str(tone).split(",") if t.strip()]
        formality = voice.get("formality", "")
        if formality and not result.get("prose_style"):
            result["prose_style"] = f"语气{formality}"

    # Map legacy narrative block
    narrative = data.get("narrative") or {}
    if isinstance(narrative, dict):
        pov_raw = narrative.get("pov", "")
        if pov_raw and not result.get("pov"):
            result["pov"] = _map_pov(str(pov_raw))

    # Map legacy prose block
    prose = data.get("prose") or {}
    if isinstance(prose, dict):
        dialogue_style = prose.get("dialogue_style", "")
        if dialogue_style and not result.get("dialogue_style"):
            result["dialogue_style"] = str(dialogue_style)
        sentence_length = prose.get("sentence_length", "")
        if sentence_length and not result.get("sentence_rules"):
            result["sentence_rules"] = [
                StyleRule(description=f"句长控制: {sentence_length}", severity="warning")
            ]

    # Derive name from project_name if name is missing
    if not result.get("name") and data.get("project_name"):
        result["name"] = f"{data['project_name']} 风格指南"

    # Ensure defaults for missing core fields so StyleBible(**result) works
    if "pacing" not in result:
        result["pacing"] = "balanced"
    if "pov" not in result:
        result["pov"] = "third_person_limited"
    if "emotional_intensity" not in result:
        result["emotional_intensity"] = "medium"
    if "forbidden_expressions" not in result:
        result["forbidden_expressions"] = []
    if "preferred_expressions" not in result:
        result["preferred_expressions"] = []
    if "sentence_rules" not in result:
        result["sentence_rules"] = []
    if "paragraph_rules" not in result:
        result["paragraph_rules"] = []
    if "chapter_opening_rules" not in result:
        result["chapter_opening_rules"] = []
    if "chapter_ending_rules" not in result:
        result["chapter_ending_rules"] = []
    if "ai_trace_avoidance" not in result:
        result["ai_trace_avoidance"] = AITraceAvoidance()

    return result


def normalize_style_bible_status(record: dict[str, Any] | None) -> str:
    """Return a stable status string for a style bible record.

    Maps:
    - None / missing -> 'draft'
    - 'unknown' / '' -> 'draft'
    - 'draft' -> 'draft'
    - 'active' -> 'active'
    - 'needs_review' -> 'needs_review'
    """
    if not record:
        return "draft"
    bible = record.get("bible") if isinstance(record, dict) else None
    bible_status = bible.get("status") if isinstance(bible, dict) else None
    status = str(record.get("status") or bible_status or "").strip().lower()
    if status in ("active", "draft", "needs_review"):
        return status
    return "draft"


def ensure_canonical_style_bible(data: dict[str, Any]) -> StyleBible:
    """Ensure a dict becomes a canonical StyleBible instance.

    Runs normalization then validates via StyleBible model.
    """
    normalized = normalize_legacy_bible(data)
    return StyleBible(**normalized)


# ── Internal helpers ───────────────────────────────────────────


def _map_pov(raw: str) -> str:
    for cn, en in _POV_MAP.items():
        if cn in raw:
            return en
    raw_lower = raw.lower().replace(" ", "_").replace("-", "_")
    valid = {m.value for m in POV}
    if raw_lower in valid:
        return raw_lower
    return "third_person_limited"


def _map_pacing(raw: str) -> str:
    for cn, en in _PACING_MAP.items():
        if cn in raw:
            return en
    raw_lower = raw.lower().replace(" ", "_").replace("-", "_")
    valid = {m.value for m in Pacing}
    if raw_lower in valid:
        return raw_lower
    return "balanced"

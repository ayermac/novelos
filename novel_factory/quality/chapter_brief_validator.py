"""Chapter Brief Validator for v6.9.0.

Validates and fills missing fields in ChapterBrief data.

Accepts both data shapes for forward compatibility:
- **Flat**: {"chapter_goal": "...", "reader_payoff": "...", ...}
- **Nested**: {"tier1": {"chapter_goal": "...", ...}, "tier2": {...}}

The nested form matches `ChapterBrief.model_dump()` from
`novel_factory.models.chapter_contracts`. The flat form is what early
Planner stubs and some tests produce.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

from ..models.creative_contracts import GenreProfile

logger = logging.getLogger(__name__)

# Tier 1 fields are required for a valid chapter brief
TIER1_FIELDS = [
    "chapter_goal",
    "reader_payoff",
    "protagonist_agency",
    "forbidden_moves",
]

# Tier 2 fields are optional and can be filled with defaults
TIER2_FIELDS = [
    "pressure_budget",
    "payoff_budget",
    "upgrade_or_skill_use",
    "character_arc_moves",
    "mystery_actions",
    "conflict_actions",
    "ledger_debts_to_pay",
    "new_debts_allowed",
    "scene_count_target",
    "opening_hook",
    "ending_hook",
    "quality_threshold_overrides",
]


def _is_nested_shape(brief: Dict[str, Any]) -> bool:
    """Return True if brief uses the nested {tier1, tier2} structure."""
    if not isinstance(brief, dict):
        return False
    tier1 = brief.get("tier1")
    tier2 = brief.get("tier2")
    return isinstance(tier1, dict) or isinstance(tier2, dict)


def _get_tier1_view(brief: Dict[str, Any]) -> Dict[str, Any]:
    """Return tier-1 fields as a flat dict, regardless of input shape."""
    if _is_nested_shape(brief):
        return dict(brief.get("tier1") or {})
    return brief


def _get_tier2_view(brief: Dict[str, Any]) -> Dict[str, Any]:
    """Return tier-2 fields as a flat dict, regardless of input shape."""
    if _is_nested_shape(brief):
        return dict(brief.get("tier2") or {})
    return brief


def validate_chapter_brief(brief: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Validate a chapter brief dictionary.

    Args:
        brief: The chapter brief dictionary to validate. May be flat or nested.

    Returns:
        Tuple of (is_valid, missing_fields)
        - is_valid: True if all Tier 1 fields are present and non-empty
        - missing_fields: List of missing Tier 1 field names
    """
    if not brief:
        return False, TIER1_FIELDS.copy()

    tier1 = _get_tier1_view(brief)

    missing_fields = []
    for field in TIER1_FIELDS:
        value = tier1.get(field)
        # Treat None, empty string, and empty list as missing
        if value is None or value == "" or value == []:
            missing_fields.append(field)

    is_valid = len(missing_fields) == 0
    return is_valid, missing_fields


def fill_missing_tier2_fields(
    brief: Dict[str, Any],
    genre_profile: GenreProfile,
) -> Dict[str, Any]:
    """Fill missing Tier 2 fields with defaults from genre profile.

    Preserves the input data shape:
    - If input is nested, output is nested.
    - If input is flat, output is flat.

    Args:
        brief: The chapter brief dictionary (flat or nested)
        genre_profile: The genre profile to use for defaults

    Returns:
        Updated brief with missing Tier 2 fields filled
    """
    if not brief:
        brief = {}

    # Defaults for Tier 2 fields
    defaults: Dict[str, Any] = {
        "pressure_budget": "moderate",
        "payoff_budget": "balanced",
        "upgrade_or_skill_use": "minimal",
        "character_arc_moves": [],
        "mystery_actions": [],
        "conflict_actions": [],
        "ledger_debts_to_pay": [],
        "new_debts_allowed": [],
        "scene_count_target": 3,
        "opening_hook": "continue_from_previous",
        "ending_hook": "cliffhanger",
        "quality_threshold_overrides": {},
    }

    # Override defaults with genre profile specific values if available
    if hasattr(genre_profile, "chapter_rhythm_defaults") and genre_profile.chapter_rhythm_defaults:
        rhythm_defaults = genre_profile.chapter_rhythm_defaults
        if isinstance(rhythm_defaults, dict):
            for key, value in rhythm_defaults.items():
                if key in defaults:
                    defaults[key] = value

    nested = _is_nested_shape(brief)

    if nested:
        filled = {k: v for k, v in brief.items()}
        tier2 = dict(filled.get("tier2") or {})
        for field in TIER2_FIELDS:
            if field not in tier2 or tier2[field] is None:
                tier2[field] = defaults.get(field)
        filled["tier2"] = tier2
        # Ensure tier1 exists for downstream consumers
        if "tier1" not in filled or not isinstance(filled["tier1"], dict):
            filled["tier1"] = {}
        return filled

    # Flat shape
    filled_brief = brief.copy()
    for field in TIER2_FIELDS:
        if field not in filled_brief or filled_brief[field] is None:
            filled_brief[field] = defaults.get(field)
    return filled_brief


# ══════════════════════════════════════════════════════════════════
# v6.10.18: ChapterBriefValidator — single-layer with plugin checkers
# ══════════════════════════════════════════════════════════════════


class ValidationResult:
    """Result of a single validation pass."""

    def __init__(self, valid: bool = True, errors: list[str] | None = None) -> None:
        self.valid = valid
        self.errors: list[str] = errors or []


class ChapterBriefValidator:
    """Unified single-layer chapter brief validator with plugin extension.

    Replaces the multi-layer approach (schema -> Tier1 -> Tier2 -> Style -> Quality)
    with a single validation pass. Skills and external modules can register custom
    checkers via ``register_checker()``.
    """

    # Core required fields (v6.10.18: conflict is new)
    REQUIRED_FIELDS = [
        "chapter_goal",
        "conflict",
        "ending_hook",
    ]

    # Plugin checkers registry
    _checkers: list[callable] = []

    @classmethod
    def register_checker(cls, checker: callable) -> None:
        """Register a custom checker callable.

        Checker signature: ``def checker(brief: dict) -> ValidationResult``.
        Registered checkers are run during ``validate()`` in registration order.
        """
        if checker not in cls._checkers:
            cls._checkers.append(checker)

    def validate(self, brief: dict | None) -> ValidationResult:
        """Run single-pass validation: required fields + registered checkers.

        Returns:
            ValidationResult with ``valid`` and ``errors`` list.
        """
        result = ValidationResult(valid=True, errors=[])

        # 1. Required fields check
        if not brief:
            result.valid = False
            result.errors = [f"Missing required field: {f}" for f in self.REQUIRED_FIELDS]
            return result

        tier1 = brief.get("tier1") if isinstance(brief, dict) and "tier1" in brief else brief
        for field in self.REQUIRED_FIELDS:
            value = tier1.get(field) if isinstance(tier1, dict) else None
            if value is None or value == "" or value == []:
                result.valid = False
                result.errors.append(f"Missing required field: {field}")

        # 2. Contract consistency check
        if isinstance(tier1, dict):
            forbidden = tier1.get("forbidden_moves", [])
            required_beats = tier1.get("required_beats", [])
            if forbidden and required_beats:
                conflicts = self._check_conflicts(forbidden, required_beats)
                if conflicts:
                    result.valid = False
                    result.errors.extend(conflicts)

        # 3. Plugin extension: run registered checkers
        for checker in self._checkers:
            sub_result = checker(brief)
            if sub_result and sub_result.errors:
                result.valid = False
                result.errors.extend(sub_result.errors)

        return result

    @staticmethod
    def _check_conflicts(forbidden: list, required: list) -> list[str]:
        """Check for forbidden/required beat conflicts."""
        errors: list[str] = []
        forbidden_set = set(str(f).lower() for f in forbidden)
        required_set = set(str(r).lower() for r in required)
        overlap = forbidden_set & required_set
        if overlap:
            errors.append(
                f"Contract conflict: forbidden moves also in required_beats: {sorted(overlap)}"
            )
        return errors


# ══════════════════════════════════════════════════════════════════
# Legacy functions (backward-compatible)
# ══════════════════════════════════════════════════════════════════


def validate_and_fill_brief(
    brief: Dict[str, Any],
    genre_profile: GenreProfile,
) -> Tuple[bool, Dict[str, Any], List[str]]:
    """Validate and fill a chapter brief.

    Args:
        brief: The chapter brief dictionary (flat or nested)
        genre_profile: The genre profile to use for defaults

    Returns:
        Tuple of (is_valid, filled_brief, missing_tier1_fields)
        - is_valid: True if all Tier 1 fields are present
        - filled_brief: Brief with missing Tier 2 fields filled
        - missing_tier1_fields: List of missing Tier 1 field names
    """
    is_valid, missing_tier1 = validate_chapter_brief(brief)

    # Fill Tier 2 fields regardless of Tier 1 validation
    filled_brief = fill_missing_tier2_fields(brief, genre_profile)

    return is_valid, filled_brief, missing_tier1

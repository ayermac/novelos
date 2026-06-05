"""Chapter Brief Validator for v6.9.0.

Validates and fills missing fields in ChapterBrief data.
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


def validate_chapter_brief(brief: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Validate a chapter brief dictionary.
    
    Args:
        brief: The chapter brief dictionary to validate
        
    Returns:
        Tuple of (is_valid, missing_fields)
        - is_valid: True if all Tier 1 fields are present
        - missing_fields: List of missing Tier 1 field names
    """
    if not brief:
        return False, TIER1_FIELDS.copy()
    
    missing_fields = []
    for field in TIER1_FIELDS:
        if field not in brief or brief[field] is None:
            missing_fields.append(field)
    
    is_valid = len(missing_fields) == 0
    return is_valid, missing_fields


def fill_missing_tier2_fields(
    brief: Dict[str, Any],
    genre_profile: GenreProfile,
) -> Dict[str, Any]:
    """Fill missing Tier 2 fields with defaults from genre profile.
    
    Args:
        brief: The chapter brief dictionary
        genre_profile: The genre profile to use for defaults
        
    Returns:
        Updated brief with missing Tier 2 fields filled
    """
    if not brief:
        brief = {}
    
    # Create a copy to avoid modifying the original
    filled_brief = brief.copy()
    
    # Fill missing Tier 2 fields with defaults from genre profile
    # These defaults are based on the genre profile's chapter rhythm defaults
    defaults = {
        "pressure_budget": "moderate",
        "payoff_budget": "balanced",
        "upgrade_or_skill_use": "minimal",
        "character_arc_moves": "steady",
        "mystery_actions": "maintain",
        "conflict_actions": "escalate",
        "ledger_debts_to_pay": [],
        "new_debts_allowed": True,
        "scene_count_target": 3,
        "opening_hook": "continue_from_previous",
        "ending_hook": "cliffhanger",
        "quality_threshold_overrides": {},
    }
    
    # Override defaults with genre profile specific values if available
    if hasattr(genre_profile, 'chapter_rhythm_defaults') and genre_profile.chapter_rhythm_defaults:
        rhythm_defaults = genre_profile.chapter_rhythm_defaults
        if isinstance(rhythm_defaults, dict):
            for key, value in rhythm_defaults.items():
                if key in defaults:
                    defaults[key] = value
    
    # Fill missing fields
    for field in TIER2_FIELDS:
        if field not in filled_brief or filled_brief[field] is None:
            filled_brief[field] = defaults.get(field)
    
    return filled_brief


def validate_and_fill_brief(
    brief: Dict[str, Any],
    genre_profile: GenreProfile,
) -> Tuple[bool, Dict[str, Any], List[str]]:
    """Validate and fill a chapter brief.
    
    Args:
        brief: The chapter brief dictionary
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
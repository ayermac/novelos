"""Genre profile loader for v6.9.0 creative contracts.

Loads genre profile YAML configurations from config/genre_profiles/ directory.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from ..models.creative_contracts import GenreProfile


# Default config directory relative to project root
_DEFAULT_PROFILES_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "genre_profiles"

# Fallback: package data directory
_PACKAGE_PROFILES_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "genre_profiles"


def _load_yaml_file(file_path: Path) -> dict[str, Any] | None:
    """Load a single YAML file and return its contents."""
    try:
        if file_path.exists() and file_path.is_file():
            with open(file_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
    except (yaml.YAMLError, OSError):
        pass
    return None


def load_genre_profile(profile_id: str) -> GenreProfile:
    """Load a genre profile by ID.

    Args:
        profile_id: The profile identifier (e.g., 'urban_sign_in_power_fantasy')

    Returns:
        GenreProfile instance loaded from YAML config

    Raises:
        FileNotFoundError: If profile YAML file not found
        ValueError: If YAML content is invalid
    """
    # Try default config directory first
    profile_path = _DEFAULT_PROFILES_DIR / f"{profile_id}.yaml"
    data = _load_yaml_file(profile_path)

    # Fallback to package directory
    if data is None:
        profile_path = _PACKAGE_PROFILES_DIR / f"{profile_id}.yaml"
        data = _load_yaml_file(profile_path)

    if data is None:
        raise FileNotFoundError(f"Genre profile not found: {profile_id}")

    # Ensure profile_id matches filename
    data.setdefault("profile_id", profile_id)

    try:
        return GenreProfile(**data)
    except Exception as e:
        raise ValueError(f"Invalid genre profile data for {profile_id}: {e}") from e


def get_all_profile_ids() -> list[str]:
    """Get all available genre profile IDs.

    Returns:
        List of profile ID strings from config/genre_profiles/ directory
    """
    profile_ids: list[str] = []

    # Scan default config directory
    if _DEFAULT_PROFILES_DIR.exists() and _DEFAULT_PROFILES_DIR.is_dir():
        for yaml_file in _DEFAULT_PROFILES_DIR.glob("*.yaml"):
            profile_id = yaml_file.stem
            if profile_id not in profile_ids:
                profile_ids.append(profile_id)

    # Scan package directory (fallback)
    if _PACKAGE_PROFILES_DIR.exists() and _PACKAGE_PROFILES_DIR.is_dir():
        for yaml_file in _PACKAGE_PROFILES_DIR.glob("*.yaml"):
            profile_id = yaml_file.stem
            if profile_id not in profile_ids:
                profile_ids.append(profile_id)

    return sorted(profile_ids)


def get_default_genre_profile() -> GenreProfile:
    """Get a default generic genre profile for unknown genres.

    Returns:
        GenreProfile with sensible defaults for any genre
    """
    return GenreProfile(
        profile_id="generic",
        default_reader_expectations=[
            "故事逻辑自洽",
            "主角有明确目标",
            "冲突推动剧情",
            "结局满足预期",
        ],
        default_payoff_loop="遭遇困境 → 努力克服 → 获得成长 → 面临新挑战",
        opening_requirements=[
            "第一章建立主角和核心冲突",
            "前三章展示故事类型和基调",
        ],
        chapter_rhythm_defaults={
            "minor_payoff_frequency": 1,
            "visible_upgrade_frequency": 5,
            "public_reversal_frequency": 8,
            "max_consecutive_pressure": 3,
            "scene_count_target": 3,
        },
        common_poison_points=[
            "剧情逻辑漏洞",
            "角色动机不清",
            "节奏拖沓",
            "结局仓促",
        ],
        style_noise_patterns=[
            "过度心理描写",
            "对话缺乏信息量",
            "环境描写冗长",
        ],
        editor_weight_profile={
            "logic_consistency": 25,
            "character_depth": 25,
            "pacing": 20,
            "world_building": 15,
            "text_quality": 15,
        },
        profile_specific_rules={
            "must_have_tropes": [],
            "avoid_patterns": ["逻辑崩坏", "角色工具化"],
            "style_constraints": ["保持叙事节奏", "对话推动剧情"],
        },
    )

"""Dynamic skill resolver for editor agent.

v6.9.1 Phase 4: Resolves which skills should run based on:
- Genre contract (e.g., mystery genre enables mystery-integrity-check)
- Chapter position (e.g., first chapter enables opening-hook-check)
- Sampling mode (consecutive passes → run less frequently)

All decisions are deterministic — no LLM involvement.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Skills that only make sense for specific chapter positions
CHAPTER_POSITIONAL_RULES: dict[str, dict[str, Any]] = {
    "opening-hook-checker": {
        "max_chapter": 1,  # Only run for chapter 1
        "reason": "开局钩子检查仅适用于第1章",
    },
}

# Skills that are genre-specific
GENRE_SKILL_MAP: dict[str, list[str]] = {
    # genre keyword → skill_ids to enable
    "悬疑": ["mystery-integrity-check"],
    "推理": ["mystery-integrity-check"],
    "惊悚": ["mystery-integrity-check"],
    "mystery": ["mystery-integrity-check"],
    "thriller": ["mystery-integrity-check"],
    "suspense": ["mystery-integrity-check"],
}

# Default sampling intervals for skills that support sampling
DEFAULT_SAMPLING_INTERVALS: dict[str, int] = {
    "word-count-gate": 3,
    "death-penalty": 5,
    "ai-style-detector": 3,
}


def resolve_active_skills(
    project_id: str,
    chapter_number: int,
    genre_contract: dict[str, Any] | None,
    skill_ids: list[str],
    repo: Any | None = None,
) -> list[str]:
    """Determine which skills should run this chapter.

    Applies three layers of filtering:
    1. Chapter position rules (e.g., opening-hook-checker only for ch1)
    2. Genre rules (e.g., mystery-integrity-check only for mystery genre)
    3. Sampling rules (skip skills that have been consistently passing)

    Args:
        project_id: Project identifier.
        chapter_number: Current chapter number (1-based).
        genre_contract: Genre contract dict with 'genre' key, or None.
        skill_ids: Full list of skill IDs from config.
        repo: Repository for querying historical skill runs (optional).

    Returns:
        Filtered list of skill IDs to run this chapter.
    """
    active: list[str] = []
    genre = _extract_genre(genre_contract)

    for skill_id in skill_ids:
        # Rule 1: Chapter position filter
        if not _passes_chapter_position_rule(skill_id, chapter_number):
            logger.debug("Skill %s skipped: chapter position rule (ch=%d)", skill_id, chapter_number)
            continue

        # Rule 2: Genre filter — only add genre-specific skills if genre matches
        if skill_id in _all_genre_skills() and not _is_genre_skill_active(skill_id, genre):
            logger.debug("Skill %s skipped: genre mismatch (genre=%s)", skill_id, genre)
            continue

        # Rule 3: Sampling — skip if consistently passing
        if repo and should_skip_sampling(project_id, skill_id, chapter_number, repo):
            logger.debug("Skill %s skipped: sampling mode", skill_id)
            continue

        active.append(skill_id)

    return active


def _extract_genre(genre_contract: dict[str, Any] | None) -> str:
    """Extract genre string from genre contract."""
    if not genre_contract:
        return ""
    return str(genre_contract.get("genre", "")).strip().lower()


def _passes_chapter_position_rule(skill_id: str, chapter_number: int) -> bool:
    """Check if skill should run based on chapter position."""
    rule = CHAPTER_POSITIONAL_RULES.get(skill_id)
    if not rule:
        return True  # No positional rule → always run

    max_chapter = rule.get("max_chapter", 999)
    return chapter_number <= max_chapter


def _all_genre_skills() -> set[str]:
    """Get all skill IDs that are genre-specific."""
    skills: set[str] = set()
    for skill_list in GENRE_SKILL_MAP.values():
        skills.update(skill_list)
    return skills


def _is_genre_skill_active(skill_id: str, genre: str) -> bool:
    """Check if a genre-specific skill should be active for the given genre."""
    if not genre:
        return False
    for genre_keyword, skill_ids in GENRE_SKILL_MAP.items():
        if genre_keyword in genre and skill_id in skill_ids:
            return True
    return False


def should_skip_sampling(
    project_id: str,
    skill_id: str,
    chapter_number: int,
    repo: Any,
) -> bool:
    """Check if skill should be skipped due to sampling mode.

    A skill enters sampling mode when it has passed consecutively
    for `interval` chapters. In sampling mode, it runs every `interval` chapters.

    Args:
        project_id: Project identifier.
        skill_id: Skill to check.
        chapter_number: Current chapter number.
        repo: Repository for querying historical runs.

    Returns:
        True if the skill should be skipped this chapter.
    """
    interval = DEFAULT_SAMPLING_INTERVALS.get(skill_id)
    if not interval:
        return False  # Skill doesn't support sampling

    try:
        runs = repo.get_skill_runs(
            project_id=project_id,
            skill_id=skill_id,
            agent_id="editor",
            limit=interval + 1,
        )
    except Exception:
        logger.debug("Sampling check failed for %s, running normally", skill_id, exc_info=True)
        return False

    if len(runs) < interval:
        return False  # Not enough history

    # Check if all recent runs passed
    recent_runs = runs[:interval]
    all_passed = all(r.get("ok", False) for r in recent_runs)

    if not all_passed:
        return False  # Recent failure → run normally

    # All passed → check chapter distance
    latest_chapter = runs[0].get("chapter_number")
    if latest_chapter is None:
        return False

    chapters_since = chapter_number - latest_chapter

    # If we've run within the last (interval - 1) chapters, skip
    # If it's been >= interval chapters since last run, don't skip
    if 0 < chapters_since < interval:
        return True  # Too recent, skip

    return False  # Time to run again

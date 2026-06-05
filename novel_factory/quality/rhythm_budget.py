"""v6.9.0: Rhythm Budget deterministic layer.

Evaluates chapter rhythm metrics deterministically before LLM review.
Detects common pacing issues like pressure streaks, passive protagonists,
payoff gaps, and mystery debt accumulation.

Spec reference: Section 4.6.2 - Default blocking rules.
"""

from __future__ import annotations

import logging
from typing import Any

from ..models.chapter_contracts import (
    ChapterBrief,
    RhythmBudgetResult,
    RhythmBudgetFlags,
)
from ..models.creative_contracts import GenreContract

logger = logging.getLogger(__name__)


# ── Default blocking thresholds ──────────────────────────────────────────

DEFAULT_THRESHOLDS = {
    "max_pressure_streak": 4,           # 4+ chapters of high pressure → blocking
    "max_passive_protagonist_streak": 3, # 3+ chapters without protagonist agency → blocking
    "max_payoff_gap": 5,                 # 5+ chapters without reader payoff → blocking
    "max_visible_upgrade_gap": 8,        # 8+ chapters without visible upgrade → blocking
    "max_mystery_answer_gap": 6,         # 6+ chapters without mystery resolution → blocking
    "max_new_mysteries_per_chapter": 3,  # 3+ new mysteries in one chapter → warning
}


# ── Helper functions ─────────────────────────────────────────────────────


def _extract_chapter_metrics(chapter: dict) -> dict[str, Any]:
    """Extract rhythm-relevant metrics from a chapter dict.

    Expected chapter fields:
    - content: chapter text
    - status: chapter status
    - metadata: optional dict with rhythm data
    """
    metadata = chapter.get("metadata", {})
    if isinstance(metadata, str):
        import json
        try:
            metadata = json.loads(metadata)
        except json.JSONDecodeError:
            metadata = {}

    return {
        "has_pressure": metadata.get("has_pressure", False),
        "has_protagonist_agency": metadata.get("has_protagonist_agency", True),
        "has_payoff": metadata.get("has_payoff", False),
        "has_visible_upgrade": metadata.get("has_visible_upgrade", False),
        "mysteries_introduced": metadata.get("mysteries_introduced", []),
        "mysteries_resolved": metadata.get("mysteries_resolved", []),
        "has_relationship_movement": metadata.get("has_relationship_movement", False),
    }


# ── Deterministic detection functions ────────────────────────────────────


def detect_pressure_streak(chapters: list[dict]) -> int:
    """Count consecutive chapters with high pressure from the end.

    Returns the length of the trailing pressure streak.
    A chapter is considered "high pressure" if it has unresolved tension,
    conflict, or danger that hasn't been relieved.
    """
    if not chapters:
        return 0

    streak = 0
    for chapter in reversed(chapters):
        metrics = _extract_chapter_metrics(chapter)
        if metrics["has_pressure"]:
            streak += 1
        else:
            break
    return streak


def detect_passive_protagonist_streak(chapters: list[dict]) -> int:
    """Count consecutive chapters without protagonist agency from the end.

    Returns the length of the trailing passive streak.
    A chapter lacks protagonist agency if the main character is reactive
    rather than proactive, or absent from key decisions.
    """
    if not chapters:
        return 0

    streak = 0
    for chapter in reversed(chapters):
        metrics = _extract_chapter_metrics(chapter)
        if not metrics["has_protagonist_agency"]:
            streak += 1
        else:
            break
    return streak


def detect_payoff_gap(chapters: list[dict]) -> int:
    """Count chapters since last reader payoff from the end.

    Returns the number of chapters without a satisfying payoff moment.
    A payoff is a moment of triumph, revelation, revenge, or emotional
    catharsis that rewards the reader's investment.
    """
    if not chapters:
        return 0

    gap = 0
    for chapter in reversed(chapters):
        metrics = _extract_chapter_metrics(chapter)
        if metrics["has_payoff"]:
            break
        gap += 1
    return gap


def detect_visible_upgrade_gap(chapters: list[dict]) -> int:
    """Count chapters since last visible upgrade/power increase from the end.

    Returns the number of chapters without a visible upgrade moment.
    In progression genres, readers expect regular power increases that
    are shown through action, not just stated.
    """
    if not chapters:
        return 0

    gap = 0
    for chapter in reversed(chapters):
        metrics = _extract_chapter_metrics(chapter)
        if metrics["has_visible_upgrade"]:
            break
        gap += 1
    return gap


def count_new_mysteries(brief: dict) -> int:
    """Count new mysteries introduced in the current chapter brief.

    Returns the number of new mystery threads being opened.
    Too many new mysteries without resolution creates reader frustration.
    """
    mystery_actions = brief.get("mystery_actions", [])
    if isinstance(mystery_actions, list):
        return len([m for m in mystery_actions if "introduce" in str(m).lower() or "new" in str(m).lower()])
    return 0


def detect_mystery_answer_gap(chapters: list[dict]) -> int:
    """Count chapters since last mystery resolution from the end.

    Returns the number of chapters without any mystery being answered.
    Mystery threads that linger too long lose reader engagement.
    """
    if not chapters:
        return 0

    gap = 0
    for chapter in reversed(chapters):
        metrics = _extract_chapter_metrics(chapter)
        if metrics["mysteries_resolved"]:
            break
        gap += 1
    return gap


# ── Blocking rules ───────────────────────────────────────────────────────


def _check_blocking_rules(
    flags: RhythmBudgetFlags,
    thresholds: dict[str, int],
) -> tuple[bool, list[str]]:
    """Check deterministic blocking rules.

    Returns (passed, blocking_reasons).
    If any blocking rule triggers, passed=False.
    """
    blocking_reasons = []

    if flags.pressure_streak >= thresholds["max_pressure_streak"]:
        blocking_reasons.append(
            f"pressure_streak: {flags.pressure_streak} consecutive high-pressure chapters "
            f"(max: {thresholds['max_pressure_streak']})"
        )

    if flags.passive_protagonist_streak >= thresholds["max_passive_protagonist_streak"]:
        blocking_reasons.append(
            f"passive_protagonist: {flags.passive_protagonist_streak} consecutive chapters without "
            f"protagonist agency (max: {thresholds['max_passive_protagonist_streak']})"
        )

    if flags.payoff_gap >= thresholds["max_payoff_gap"]:
        blocking_reasons.append(
            f"payoff_gap: {flags.payoff_gap} chapters without reader payoff "
            f"(max: {thresholds['max_payoff_gap']})"
        )

    if flags.visible_upgrade_gap >= thresholds["max_visible_upgrade_gap"]:
        blocking_reasons.append(
            f"upgrade_gap: {flags.visible_upgrade_gap} chapters without visible upgrade "
            f"(max: {thresholds['max_visible_upgrade_gap']})"
        )

    if flags.mystery_answer_gap >= thresholds["max_mystery_answer_gap"]:
        blocking_reasons.append(
            f"mystery_gap: {flags.mystery_answer_gap} chapters without mystery resolution "
            f"(max: {thresholds['max_mystery_answer_gap']})"
        )

    return len(blocking_reasons) == 0, blocking_reasons


def _check_warnings(
    flags: RhythmBudgetFlags,
    thresholds: dict[str, int],
) -> list[str]:
    """Check for warning conditions (not blocking but concerning)."""
    warnings = []

    if flags.new_mystery_count >= thresholds["max_new_mysteries_per_chapter"]:
        warnings.append(
            f"new_mysteries: {flags.new_mystery_count} new mysteries in one chapter "
            f"(recommended max: {thresholds['max_new_mysteries_per_chapter']})"
        )

    return warnings


# ── Main evaluation function ─────────────────────────────────────────────


def evaluate_deterministic(
    chapters: list[dict],
    brief: dict,
    genre_contract: dict | None = None,
    thresholds: dict[str, int] | None = None,
) -> RhythmBudgetResult:
    """Evaluate rhythm budget deterministically.

    Runs 6 metric checks and applies blocking rules.
    Returns RhythmBudgetResult with flags and blocking decisions.

    Args:
        chapters: List of previous chapter dicts (ordered by chapter number)
        brief: Current chapter brief dict (from Planner)
        genre_contract: Optional genre contract with custom thresholds
        thresholds: Optional custom threshold overrides

    Returns:
        RhythmBudgetResult with deterministic evaluation
    """
    # Merge thresholds: defaults < genre contract < explicit overrides
    effective_thresholds = dict(DEFAULT_THRESHOLDS)

    if genre_contract:
        genre_thresholds = genre_contract.get("rhythm_thresholds", {})
        if isinstance(genre_thresholds, dict):
            effective_thresholds.update(genre_thresholds)

    if thresholds:
        effective_thresholds.update(thresholds)

    # Compute flags
    flags = RhythmBudgetFlags(
        pressure_streak=detect_pressure_streak(chapters),
        passive_protagonist_streak=detect_passive_protagonist_streak(chapters),
        payoff_gap=detect_payoff_gap(chapters),
        visible_upgrade_gap=detect_visible_upgrade_gap(chapters),
        new_mystery_count=count_new_mysteries(brief),
        mystery_answer_gap=detect_mystery_answer_gap(chapters),
    )

    # Check blocking rules
    passed, blocking_reasons = _check_blocking_rules(flags, effective_thresholds)

    # Check warnings
    warnings = _check_warnings(flags, effective_thresholds)

    result = RhythmBudgetResult(
        passed=passed,
        blocking_reasons=blocking_reasons,
        warnings=warnings,
        flags=flags,
    )

    if not passed:
        logger.warning(f"Rhythm budget BLOCKED: {blocking_reasons}")
    elif warnings:
        logger.info(f"Rhythm budget warnings: {warnings}")

    return result


# ── Genre-specific rules ─────────────────────────────────────────────────


def apply_genre_specific_rules(
    result: RhythmBudgetResult,
    genre_contract: dict,
) -> RhythmBudgetResult:
    """Apply genre-specific rhythm rules.

    Some genres have special requirements:
    - Cultivation/Upgrade: Must have visible upgrade every N chapters
    - Mystery/Suspense: Must maintain clue threading
    - Romance: Must have relationship progression
    """
    genre_id = genre_contract.get("genre_id", "")

    if genre_id in ("cultivation_upgrade", "xianxia", "xuanhuan"):
        # Cultivation genres need more frequent upgrades
        if result.flags.visible_upgrade_gap > 5:
            result.warnings.append(
                f"cultivation_genre: {result.flags.visible_upgrade_gap} chapters without upgrade "
                f"(cultivation readers expect regular power-ups)"
            )

    if genre_id in ("suspense_mystery", "detective"):
        # Mystery genres need tighter mystery management
        if result.flags.mystery_answer_gap > 4:
            result.blocking_reasons.append(
                f"mystery_genre: {result.flags.mystery_answer_gap} chapters without resolution "
                f"(mystery readers demand timely answers)"
            )
            result.passed = False

    if genre_id in ("romance", "urban_romance"):
        # Romance genres need relationship progression
        # This is a simplified check - real implementation would track relationship beats
        pass

    return result
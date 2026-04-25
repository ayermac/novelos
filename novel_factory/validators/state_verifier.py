"""State verifier — checks chapter status preconditions and state card consistency.

v1.2 adds:
- State card consistency check: level/number jumps, location shifts, relation reversals.
- Soft check (warnings) when state card is missing.
"""

from __future__ import annotations

import re
from typing import Any

from ..models.quality import (
    PenaltySeverity,
    StateVerifyResult,
    StateViolation,
    StateViolationType,
)
from ..models.state import TRANSITIONS, ChapterStatus


# Each agent requires the chapter to be in a specific status before writing
AGENT_REQUIRED_STATUS: dict[str, str] = {
    "planner": "planned",       # can also work on idea/outlined
    "screenwriter": "planned",
    "author": "scripted",       # or revision
    "polisher": "drafted",      # or revision
    "editor": "polished",       # also review
}


def check_status_precondition(
    agent_id: str,
    current_status: str,
) -> list[str]:
    """Check if an agent is allowed to write given the current chapter status.

    Args:
        agent_id: The agent attempting to write.
        current_status: The current chapter status.

    Returns:
        List of violation messages. Empty list means the precondition is met.
    """
    violations: list[str] = []

    required = AGENT_REQUIRED_STATUS.get(agent_id)
    if required is None:
        return violations  # Unknown agent, skip check

    # Special cases
    if agent_id == "planner" and current_status in ("idea", "outlined"):
        return violations  # planner can also plan from idea/outlined

    if agent_id in ("author", "polisher") and current_status == ChapterStatus.REVISION.value:
        return violations  # revision can go to author or polisher

    if agent_id == "editor" and current_status == ChapterStatus.REVIEW.value:
        return violations  # editor can also review from 'review' status

    if current_status != required:
        violations.append(
            f"Agent '{agent_id}' 要求章节状态为 '{required}'，当前为 '{current_status}'"
        )

    return violations


def check_transition(
    current_status: str,
    target_status: str,
) -> list[str]:
    """Check if a status transition is legal per the state machine.

    Args:
        current_status: Current chapter status.
        target_status: Desired target status.

    Returns:
        List of violation messages. Empty means transition is legal.
    """
    from ..models.state import is_valid_transition

    violations: list[str] = []

    if not is_valid_transition(current_status, target_status):
        violations.append(
            f"非法状态转换: '{current_status}' -> '{target_status}'"
        )

    return violations


# ── Q3: State card consistency checks ──────────────────────────


# Level/number pattern: matches "Lv数字" or "等级数字" or similar
_LEVEL_PATTERN = re.compile(r"[Ll]v\.?\s*(\d+)|等级\s*(\d+)|级别\s*(\d+)|阶\s*(\d+)")
# Location keywords that suggest spatial context
_LOCATION_INDICATORS = re.compile(
    r"(公司|学校|家|市场|酒楼|城|镇|山|河|湖|海|岛|殿|宫|府|院|营|寨|洞|林|谷|塔|寺)"
)
# Relation keywords
_RELATION_KEYWORDS = re.compile(r"(师父|徒弟|父亲|母亲|兄弟|姐妹|盟友|敌对|挚友|生死之交)")


def check_state_consistency(
    state_card: dict[str, Any] | None,
    content: str,
) -> StateVerifyResult:
    """Check if chapter content is consistent with the previous state card.

    Args:
        state_card: The previous chapter's state card data. None if unavailable.
        content: The current chapter's text content.

    Returns:
        StateVerifyResult with violations and warnings.
    """
    result = StateVerifyResult()
    
    # R1: Defensive handling for None content
    if content is None:
        content = ""

    if state_card is None:
        result.warnings.append("无上一章状态卡，跳过状态一致性检查")
        return result

    state_data = state_card if isinstance(state_card, dict) else {}

    # Extract state_data from nested structure if needed
    if "state_data" in state_data:
        inner = state_data["state_data"]
        if isinstance(inner, dict):
            state_data = inner

    # Check 1: Level/number jumps
    _check_level_jumps(state_data, content, result)

    # Check 2: Location shifts
    _check_location_shifts(state_data, content, result)

    # Check 3: Relation reversals
    _check_relation_reversals(state_data, content, result)

    return result


def _check_level_jumps(
    state_data: dict[str, Any],
    content: str,
    result: StateVerifyResult,
) -> None:
    """Check for level/number jumps without source explanation."""
    # Find level in state card
    state_level = _extract_level(state_data)
    if state_level is None:
        return

    # Find levels in content
    content_levels = []
    for match in _LEVEL_PATTERN.finditer(content):
        for group in match.groups():
            if group is not None:
                content_levels.append(int(group))

    for cl in content_levels:
        if cl > state_level + 1:
            # Jump of more than 1 level without explanation
            result.violations.append(StateViolation(
                type=StateViolationType.LEVEL_JUMP,
                severity=PenaltySeverity.HIGH,
                message=f"等级跳变: 状态卡等级 Lv{state_level}，正文出现 Lv{cl}",
                detail=f"状态卡: Lv{state_level}, 正文: Lv{cl}",
            ))


def _check_location_shifts(
    state_data: dict[str, Any],
    content: str,
    result: StateVerifyResult,
) -> None:
    """Check for location shifts without transition."""
    state_location = state_data.get("location", "")
    if not state_location:
        return

    # Check if state location is mentioned in content
    if state_location not in content:
        # Check if content starts with a different location
        # This is a soft check — just warn
        content_locations = _LOCATION_INDICATORS.findall(content[:2000])
        if content_locations:
            result.warnings.append(
                f"状态卡位置为'{state_location}'，但正文开头未提及，可能存在位置跳转"
            )


def _check_relation_reversals(
    state_data: dict[str, Any],
    content: str,
    result: StateVerifyResult,
) -> None:
    """Check for locked relation reversals."""
    relations = state_data.get("relations", {})
    if not relations:
        return

    if not isinstance(relations, dict):
        return

    # Simple heuristic: if state card says X is "ally" but content
    # has X acting as enemy (or vice versa), flag it
    for name, relation in relations.items():
        if not isinstance(relation, str):
            continue
        if name not in content:
            continue
        # Very simple check: if relation is "盟友" but content pairs name with enemy words
        enemy_words = ["敌对", "背叛", "反目", "暗算"]
        ally_words = ["联手", "协力", "并肩", "支援"]

        if "盟" in relation or "友" in relation:
            for ew in enemy_words:
                # Check if enemy word appears near the character name
                idx = content.find(name)
                if idx >= 0:
                    context = content[max(0, idx - 50):idx + 50]
                    if ew in context:
                        result.violations.append(StateViolation(
                            type=StateViolationType.RELATION_REVERSAL,
                            severity=PenaltySeverity.HIGH,
                            message=f"角色关系反转: '{name}'在状态卡中为'{relation}'，但正文出现'{ew}'",
                        ))
                        break


def _extract_level(state_data: dict[str, Any]) -> int | None:
    """Extract character level from state data."""
    # Try common field names
    for key in ("level", "等级", "级别", "lv", "Lv"):
        val = state_data.get(key)
        if val is not None:
            try:
                return int(val)
            except (ValueError, TypeError):
                pass

    # Try nested structures
    assets = state_data.get("assets", {})
    if isinstance(assets, dict):
        for key in ("level", "等级", "lv"):
            val = assets.get(key)
            if val is not None:
                try:
                    return int(val)
                except (ValueError, TypeError):
                    pass

    return None

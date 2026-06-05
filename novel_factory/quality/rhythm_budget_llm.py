"""v6.9.0: Rhythm Budget LLM-assisted layer.

Runs after deterministic layer passes. Uses LLM to detect subtle
rhythm issues that require semantic understanding:
- Style fatigue (repetitive patterns)
- Character tooling (characters used as plot devices)
- Breathing room (pacing between intense scenes)
- Relationship movement (relationship progression)

Spec reference: Section 4.6.3 - LLM-assisted rhythm checks.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from ..llm.provider import LLMProvider
from ..models.chapter_contracts import RhythmBudgetLLMSignals

logger = logging.getLogger(__name__)


# ── LLM prompts ──────────────────────────────────────────────────────────

STYLE_FATIGUE_PROMPT = """分析以下章节文本，检测是否存在风格疲劳（重复的叙事模式、过度使用的句式、AI模板痕迹）。

返回JSON格式：
{{
    "fatigue_score": 0.0-1.0,  // 0=无疲劳, 1=严重疲劳
    "repetitive_patterns": ["pattern1", "pattern2"],
    "ai_template_signs": ["sign1", "sign2"]
}}

章节文本：
{draft}"""

CHARACTER_TOOLING_PROMPT = """分析以下章节文本，检测角色是否被当作工具人使用（仅服务于情节需要，缺乏独立动机和能动性）。

返回JSON格式：
{{
    "tooling_detected": true/false,
    "tool_characters": ["character1", "character2"],
    "issues": ["issue1", "issue2"]
}}

章节文本：
{draft}

已知角色列表：
{characters}"""

BREATHING_ROOM_PROMPT = """分析以下章节文本，检查高强度场景之间是否有足够的喘息空间（情感调节、节奏变化）。

返回JSON格式：
{{
    "breathing_room_ok": true/false,
    "intensity_pattern": ["high", "medium", "low", ...],
    "suggestion": "建议内容"
}}

章节文本：
{draft}

前几章摘要：
{previous_chapters_summary}"""

RELATIONSHIP_MOVEMENT_PROMPT = """分析以下章节文本，检查角色关系是否有推进或变化（不能停滞不前）。

返回JSON格式：
{{
    "relationship_movement": true/false,
    "changes": [
        {{"characters": ["A", "B"], "change": "变化描述"}}
    ],
    "stagnant_relationships": [["A", "B"]]
}}

章节文本：
{draft}

已知角色关系：
{relationships}"""


# ── LLM check functions ──────────────────────────────────────────────────


async def check_style_fatigue(
    draft: str,
    llm: LLMProvider,
    ledger: dict | None = None,
) -> float:
    """Check for style fatigue in the draft.

    Returns a fatigue score from 0.0 (no fatigue) to 1.0 (severe fatigue).
    High scores indicate repetitive patterns, AI templates, or formulaic writing.
    """
    if not draft or len(draft) < 100:
        return 0.0

    try:
        prompt = STYLE_FATIGUE_PROMPT.format(draft=draft[:3000])  # Limit token usage
        response = await llm.generate(prompt, response_format={"type": "json_object"})
        result = json.loads(response)
        return float(result.get("fatigue_score", 0.0))
    except Exception as e:
        logger.warning(f"Style fatigue check failed: {e}")
        return 0.0


async def detect_character_tooling(
    draft: str,
    llm: LLMProvider,
    characters: list[str] | None = None,
    ledger: dict | None = None,
) -> list[str]:
    """Detect characters being used as plot tools.

    Returns list of character names identified as tooling.
    Tooling means characters exist only to serve plot needs without
    independent motivation or agency.
    """
    if not draft or len(draft) < 100:
        return []

    char_list = ", ".join(characters) if characters else "未知"
    try:
        prompt = CHARACTER_TOOLING_PROMPT.format(
            draft=draft[:3000],
            characters=char_list,
        )
        response = await llm.generate(prompt, response_format={"type": "json_object"})
        result = json.loads(response)
        if result.get("tooling_detected", False):
            return result.get("tool_characters", [])
        return []
    except Exception as e:
        logger.warning(f"Character tooling check failed: {e}")
        return []


async def check_breathing_room(
    draft: str,
    llm: LLMProvider,
    previous_chapters: list[dict] | None = None,
) -> bool:
    """Check if there's adequate breathing room between intense scenes.

    Returns True if pacing is acceptable, False if too intense without breaks.
    """
    if not draft or len(draft) < 100:
        return True

    # Build previous chapters summary
    prev_summary = ""
    if previous_chapters:
        summaries = []
        for ch in previous_chapters[-3:]:  # Last 3 chapters
            content = ch.get("content", "")[:200]
            summaries.append(content)
        prev_summary = "\n---\n".join(summaries)

    try:
        prompt = BREATHING_ROOM_PROMPT.format(
            draft=draft[:3000],
            previous_chapters_summary=prev_summary[:1000],
        )
        response = await llm.generate(prompt, response_format={"type": "json_object"})
        result = json.loads(response)
        return result.get("breathing_room_ok", True)
    except Exception as e:
        logger.warning(f"Breathing room check failed: {e}")
        return True


async def check_relationship_movement(
    draft: str,
    llm: LLMProvider,
    relationships: list[dict] | None = None,
    ledger: dict | None = None,
) -> bool:
    """Check if character relationships have movement/progression.

    Returns True if relationships are progressing, False if stagnant.
    """
    if not draft or len(draft) < 100:
        return True

    rel_list = ""
    if relationships:
        rel_list = json.dumps(relationships[:10], ensure_ascii=False)

    try:
        prompt = RELATIONSHIP_MOVEMENT_PROMPT.format(
            draft=draft[:3000],
            relationships=rel_list[:500],
        )
        response = await llm.generate(prompt, response_format={"type": "json_object"})
        result = json.loads(response)
        return result.get("relationship_movement", True)
    except Exception as e:
        logger.warning(f"Relationship movement check failed: {e}")
        return True


# ── Main evaluation function ─────────────────────────────────────────────


async def evaluate_llm_signals(
    draft: str,
    llm: LLMProvider,
    characters: list[str] | None = None,
    relationships: list[dict] | None = None,
    previous_chapters: list[dict] | None = None,
    ledger: dict | None = None,
) -> RhythmBudgetLLMSignals:
    """Run all LLM-assisted rhythm checks.

    Returns RhythmBudgetLLMSignals with all check results.
    These signals are informational and don't block production,
    but are used by the chief editor for final decisions.
    """
    import asyncio

    # Run checks concurrently
    fatigue_task = check_style_fatigue(draft, llm, ledger)
    tooling_task = detect_character_tooling(draft, llm, characters, ledger)
    breathing_task = check_breathing_room(draft, llm, previous_chapters)
    relationship_task = check_relationship_movement(draft, llm, relationships, ledger)

    fatigue_score, tool_characters, breathing_ok, relationship_ok = await asyncio.gather(
        fatigue_task, tooling_task, breathing_task, relationship_task,
        return_exceptions=True,
    )

    # Handle exceptions
    if isinstance(fatigue_score, Exception):
        logger.warning(f"Fatigue check failed: {fatigue_score}")
        fatigue_score = 0.0
    if isinstance(tool_characters, Exception):
        logger.warning(f"Tooling check failed: {tool_characters}")
        tool_characters = []
    if isinstance(breathing_ok, Exception):
        logger.warning(f"Breathing check failed: {breathing_ok}")
        breathing_ok = True
    if isinstance(relationship_ok, Exception):
        logger.warning(f"Relationship check failed: {relationship_ok}")
        relationship_ok = True

    return RhythmBudgetLLMSignals(
        style_fatigue_score=float(fatigue_score),
        character_tooling_detected=len(tool_characters) > 0,
        scene_breathing_room_ok=bool(breathing_ok),
        relationship_movement_ok=bool(relationship_ok),
    )
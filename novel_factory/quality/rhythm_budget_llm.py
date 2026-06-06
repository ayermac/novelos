"""v6.9.0: Rhythm Budget LLM-assisted layer.

Runs after deterministic layer passes. Uses LLM to detect subtle
rhythm issues that require semantic understanding:
- Style fatigue (repetitive patterns)
- Character tooling (characters used as plot devices)
- Breathing room (pacing between intense scenes)
- Relationship movement (relationship progression)

Spec reference: Section 4.6.3 - LLM-assisted rhythm checks.

All LLM calls go through ``LLMProvider.invoke_json`` for interface
consistency with the rest of the codebase. Calls are synchronous; callers
can wrap with ``asyncio.to_thread`` if concurrency is needed.
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
    "fatigue_score": 0.0-1.0,
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
    "intensity_pattern": ["high", "medium", "low"],
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


# ── Helper to invoke LLM uniformly ───────────────────────────────────────


def _invoke_llm_json(llm: LLMProvider, prompt: str, agent_id: str) -> dict[str, Any]:
    """Invoke an LLM provider for a JSON response, tolerant of different shapes.

    Always prefer ``invoke_json`` (the formal interface). Falls back to other
    method names only if the provider does not implement it (e.g. test mocks).
    """
    messages = [{"role": "user", "content": prompt}]
    if hasattr(llm, "invoke_json"):
        result = llm.invoke_json(messages, agent_id=agent_id)
        if isinstance(result, dict):
            return result
        if isinstance(result, str):
            try:
                return json.loads(result)
            except json.JSONDecodeError:
                return {}
        return {}
    # Last-resort fallbacks (test mocks may expose these)
    if hasattr(llm, "invoke_text"):
        text = llm.invoke_text(messages)
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return {}
    return {}


# ── LLM check functions (synchronous) ────────────────────────────────────


def check_style_fatigue(
    draft: str,
    llm: LLMProvider,
    ledger: dict | None = None,
) -> float:
    """Check for style fatigue in the draft.

    Returns a fatigue score from 0.0 (no fatigue) to 1.0 (severe fatigue).
    """
    if not draft or len(draft) < 100:
        return 0.0

    try:
        prompt = STYLE_FATIGUE_PROMPT.format(draft=draft[:3000])
        result = _invoke_llm_json(llm, prompt, agent_id="rhythm_budget.style_fatigue")
        return float(result.get("fatigue_score", 0.0))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Style fatigue check failed: %s", exc)
        return 0.0


def detect_character_tooling(
    draft: str,
    llm: LLMProvider,
    characters: list[str] | None = None,
    ledger: dict | None = None,
) -> list[str]:
    """Detect characters being used as plot tools.

    Returns list of character names identified as tooling.
    """
    if not draft or len(draft) < 100:
        return []

    char_list = ", ".join(characters) if characters else "未知"
    try:
        prompt = CHARACTER_TOOLING_PROMPT.format(
            draft=draft[:3000],
            characters=char_list,
        )
        result = _invoke_llm_json(llm, prompt, agent_id="rhythm_budget.character_tooling")
        if result.get("tooling_detected", False):
            tools = result.get("tool_characters", [])
            return [str(c) for c in tools] if isinstance(tools, list) else []
        return []
    except Exception as exc:  # noqa: BLE001
        logger.warning("Character tooling check failed: %s", exc)
        return []


def check_breathing_room(
    draft: str,
    llm: LLMProvider,
    previous_chapters: list[dict] | None = None,
) -> bool:
    """Check if there's adequate breathing room between intense scenes."""
    if not draft or len(draft) < 100:
        return True

    prev_summary = ""
    if previous_chapters:
        summaries = []
        for ch in previous_chapters[-3:]:
            content = ch.get("content", "")[:200]
            summaries.append(content)
        prev_summary = "\n---\n".join(summaries)

    try:
        prompt = BREATHING_ROOM_PROMPT.format(
            draft=draft[:3000],
            previous_chapters_summary=prev_summary[:1000],
        )
        result = _invoke_llm_json(llm, prompt, agent_id="rhythm_budget.breathing_room")
        return bool(result.get("breathing_room_ok", True))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Breathing room check failed: %s", exc)
        return True


def check_relationship_movement(
    draft: str,
    llm: LLMProvider,
    relationships: list[dict] | None = None,
    ledger: dict | None = None,
) -> bool:
    """Check if character relationships have movement/progression."""
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
        result = _invoke_llm_json(llm, prompt, agent_id="rhythm_budget.relationship_movement")
        return bool(result.get("relationship_movement", True))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Relationship movement check failed: %s", exc)
        return True


# ── Main evaluation function ─────────────────────────────────────────────


def evaluate_llm_signals(
    draft: str,
    llm: LLMProvider,
    characters: list[str] | None = None,
    relationships: list[dict] | None = None,
    previous_chapters: list[dict] | None = None,
    ledger: dict | None = None,
) -> RhythmBudgetLLMSignals:
    """Run all LLM-assisted rhythm checks sequentially.

    Each check is independent and failures are degraded gracefully to
    a neutral default. The result is informational; the chief editor
    may use these signals when weighing review decisions.
    """
    fatigue_score = check_style_fatigue(draft, llm, ledger)
    tool_characters = detect_character_tooling(draft, llm, characters, ledger)
    breathing_ok = check_breathing_room(draft, llm, previous_chapters)
    relationship_ok = check_relationship_movement(draft, llm, relationships, ledger)

    return RhythmBudgetLLMSignals(
        style_fatigue_score=float(fatigue_score),
        character_tooling_detected=len(tool_characters) > 0,
        scene_breathing_room_ok=bool(breathing_ok),
        relationship_movement_ok=bool(relationship_ok),
    )

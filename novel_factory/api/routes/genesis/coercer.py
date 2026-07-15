"""Genesis draft type coercion — normalize LLM output to canonical types.

This module contains functions to coerce various LLM output formats
into the canonical Genesis draft structure.
"""

from __future__ import annotations

from .utils import _as_text, _as_int, _short_title
from novel_factory.validators.chapter_checker import DEFAULT_INSTRUCTION_WORD_TARGET


def _coerce_world_setting(item, index: int) -> dict | None:
    if isinstance(item, dict):
        title = _as_text(item.get("title", "")) or f"世界设定 {index}"
        return {
            "title": title,
            "category": _as_text(item.get("category", "其他")) or "其他",
            "content": _as_text(item.get("content", "")),
        }
    text = _as_text(item).strip()
    if not text:
        return None
    return {"title": _short_title(text, f"世界设定 {index}"), "category": "其他", "content": text}


def _coerce_character(item, index: int) -> dict | None:
    if isinstance(item, dict):
        name = _as_text(item.get("name", "")) or f"角色 {index}"
        # v6.6.4: Merge extra depth fields into description so nothing is lost on approval
        description = _as_text(item.get("description", ""))
        goal = _as_text(item.get("goal", "")) or _as_text(item.get("desire", "")) or _as_text(item.get("current_goal", ""))
        conflict = _as_text(item.get("conflict", "")) or _as_text(item.get("inner_conflict", "")) or _as_text(item.get("secret", ""))
        interest = _as_text(item.get("interest_relation", "")) or _as_text(item.get("relationship_with_protagonist", ""))
        if goal and goal not in description:
            description = f"{description}\n当前目标: {goal}".strip()
        if conflict and conflict not in description:
            description = f"{description}\n内在矛盾/秘密: {conflict}".strip()
        if interest and interest not in description:
            description = f"{description}\n与主角利益关系: {interest}".strip()
        return {
            **item,
            "name": name,
            "role": _normalize_character_role(_as_text(item.get("role", "supporting"))),
            "description": description,
            "traits": _as_text(item.get("traits", "")),
        }
    text = _as_text(item).strip()
    if not text:
        return None
    return {
        "name": _short_title(text, f"角色 {index}", limit=12),
        "role": "supporting",
        "description": text,
        "traits": "",
    }


def _coerce_named_item(item, index: int, fallback_prefix: str) -> dict | None:
    if isinstance(item, dict):
        # v6.6.4: Merge extra depth fields into description for factions
        description = _as_text(item.get("description", ""))
        resources = _as_text(item.get("resources", "")) or _as_text(item.get("means", ""))
        attitude = _as_text(item.get("attitude", "")) or _as_text(item.get("attitude_toward_protagonist", ""))
        action = _as_text(item.get("action", "")) or _as_text(item.get("current_action", ""))
        if resources and resources not in description:
            description = f"{description}\n资源/手段: {resources}".strip()
        if attitude and attitude not in description:
            description = f"{description}\n对主角态度: {attitude}".strip()
        if action and action not in description:
            description = f"{description}\n当前阶段行动: {action}".strip()
        return {
            **item,
            "description": description,
        }
    text = _as_text(item).strip()
    if not text:
        return None
    return {
        "name": _short_title(text, f"{fallback_prefix} {index}", limit=16),
        "type": "",
        "description": text,
        "relationship_with_protagonist": "",
    }


def _coerce_outline(item, index: int) -> dict | None:
    if isinstance(item, dict):
        # v6.6.4: Merge extra depth fields into content for outlines
        content = _as_text(item.get("content", ""))
        stage_conflict = _as_text(item.get("stage_conflict", "")) or _as_text(item.get("conflict", ""))
        twist = _as_text(item.get("twist", "")) or _as_text(item.get("turning_point", ""))
        stage_result = _as_text(item.get("stage_result", "")) or _as_text(item.get("result", ""))
        if stage_conflict and stage_conflict not in content:
            content = f"{content}\n阶段冲突: {stage_conflict}".strip()
        if twist and twist not in content:
            content = f"{content}\n转折: {twist}".strip()
        if stage_result and stage_result not in content:
            content = f"{content}\n阶段结果: {stage_result}".strip()
        return {
            **item,
            "level": _as_text(item.get("level", "arc")) or "arc",
            "sequence": _as_int(item.get("sequence"), index),
            "title": _as_text(item.get("title", "")) or f"大纲 {index}",
            "content": content,
            "chapters_range": _as_text(item.get("chapters_range", "")),
        }
    text = _as_text(item).strip()
    if not text:
        return None
    return {
        "level": "arc",
        "sequence": index,
        "title": _short_title(text, f"大纲 {index}"),
        "content": text,
        "chapters_range": "",
    }


def _coerce_plot_hole(item, index: int) -> dict | None:
    if isinstance(item, dict):
        code = _as_text(item.get("code", "")) or f"PH-{index:03d}"
        # v6.6.4: Merge extra depth fields into description for plot holes
        description = _as_text(item.get("description", ""))
        trigger_scene = _as_text(item.get("trigger_scene", "")) or _as_text(item.get("trigger", ""))
        appearance = _as_text(item.get("reader_appearance", "")) or _as_text(item.get("appearance", ""))
        truth_direction = _as_text(item.get("truth_direction", "")) or _as_text(item.get("truth", ""))
        resolve_plan = _as_text(item.get("resolve_plan", "")) or _as_text(item.get("planned_resolve_chapter", ""))
        if trigger_scene and trigger_scene not in description:
            description = f"{description}\n触发场景: {trigger_scene}".strip()
        if appearance and appearance not in description:
            description = f"{description}\n读者表象: {appearance}".strip()
        if truth_direction and truth_direction not in description:
            description = f"{description}\n真相方向: {truth_direction}".strip()
        if resolve_plan and str(resolve_plan) not in description:
            description = f"{description}\n预计兑现: {resolve_plan}".strip()
        return {
            **item,
            "code": code,
            "type": _as_text(item.get("type", "")),
            "title": _as_text(item.get("title", "")) or code,
            "description": description,
            "status": _normalize_plot_status(_as_text(item.get("status", "planted"))),
        }
    text = _as_text(item).strip()
    if not text:
        return None
    code = f"PH-{index:03d}"
    return {"code": code, "type": "", "title": _short_title(text, code), "description": text, "status": "planted"}


def _coerce_instruction(item, index: int) -> dict | None:
    if isinstance(item, dict):
        chapter_number = _as_int(item.get("chapter_number"), index)
        word_target = _as_int(
            item.get("word_target"),
            DEFAULT_INSTRUCTION_WORD_TARGET,
        )
        if word_target <= 0:
            word_target = DEFAULT_INSTRUCTION_WORD_TARGET
        # v6.6.4: Normalize key_events array into structured text without losing info
        raw_key_events = item.get("key_events", "")
        if isinstance(raw_key_events, list):
            key_events = "；".join(str(ev) for ev in raw_key_events if ev)
        else:
            key_events = _as_text(raw_key_events)
        raw_action_chain = item.get("action_chain", [])
        if isinstance(raw_action_chain, list):
            action_chain = [_as_text(action) for action in raw_action_chain if _as_text(action)]
        elif raw_action_chain:
            action_chain = [_as_text(raw_action_chain)]
        else:
            action_chain = []
        return {
            **item,
            "chapter_number": chapter_number,
            "objective": _as_text(item.get("objective", "")),
            "protagonist": _as_text(item.get("protagonist", "")),
            "primary_location": _as_text(item.get("primary_location", "")),
            "opposing_force": _as_text(item.get("opposing_force", "")),
            "action_chain": action_chain,
            "visible_result": _as_text(item.get("visible_result", "")),
            "state_change": _as_text(item.get("state_change", "")),
            "key_events": key_events,
            "emotion_tone": _as_text(item.get("emotion_tone", "")),
            "ending_hook": _as_text(item.get("ending_hook", "")),
            "continuity_seed": _as_text(item.get("continuity_seed", "")),
            "word_target": word_target,
        }
    text = _as_text(item).strip()
    if not text:
        return None
    return {
        "chapter_number": index,
        "objective": text,
        "key_events": text,
        "emotion_tone": "",
        "ending_hook": "",
        "continuity_seed": "",
        "word_target": DEFAULT_INSTRUCTION_WORD_TARGET,
    }


def _format_instruction_contract_details(instruction: dict) -> str:
    """Format structured instruction contract fields for legacy key_events storage."""
    lines: list[str] = []
    label_by_key = {
        "protagonist": "本章主角",
        "primary_location": "主要场景",
        "opposing_force": "阻力来源",
        "visible_result": "可见结果",
        "state_change": "状态变化",
    }
    for key, label in label_by_key.items():
        value = _as_text(instruction.get(key, "")).strip()
        if value:
            lines.append(f"{label}: {value}")

    action_chain = instruction.get("action_chain")
    if isinstance(action_chain, list):
        actions = [_as_text(action).strip() for action in action_chain if _as_text(action).strip()]
    else:
        action_text = _as_text(action_chain).strip()
        actions = [action_text] if action_text else []
    if actions:
        lines.append("行动链: " + "；".join(actions))

    return "\n".join(lines)


def _normalize_character_role(role: str | None) -> str:
    """Map real LLM Chinese role labels to canonical character roles."""
    role_text = (role or "").strip().lower()
    mapping = {
        "主角": "protagonist",
        "男主": "protagonist",
        "女主": "protagonist",
        "protagonist": "protagonist",
        "反派": "antagonist",
        "反派boss": "antagonist",
        "antagonist": "antagonist",
        "配角": "supporting",
        "supporting": "supporting",
    }
    if role_text in mapping:
        return mapping[role_text]
    if "主角" in role_text or "男主" in role_text or "女主" in role_text:
        return "protagonist"
    if "反派" in role_text or "boss" in role_text:
        return "antagonist"
    return role or "supporting"


def _normalize_plot_status(status: str | None) -> str:
    """Map free-form LLM plot-hole statuses to canonical values."""
    status_text = (status or "").strip().lower()
    if status_text in ("planted", "resolved", "abandoned"):
        return status_text
    if "解决" in status_text or "resolved" in status_text:
        return "resolved"
    if "废弃" in status_text or "abandoned" in status_text:
        return "abandoned"
    return "planted"

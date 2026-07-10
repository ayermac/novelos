"""Autonomous planner agent for v5.5.4 real LLM auto-fill and arc-plan.

Uses the project's LLM provider to generate missing context (world settings,
characters, outlines, plot holes, instructions) and arc plans without
overwriting existing user content.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import ValidationError

from ..llm.provider import LLMProvider
from ..validators.chapter_checker import derive_word_target
from ..models.schemas import (
    AutoFillLLMOutput,
    ArcPlanLLMOutput,
)
from ..agent_runtime.title_contract import build_title_contract

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_AUTOFILL_SYSTEM_PROMPT = """你是一位专业的小说项目资料规划师。你的任务是根据已有信息，为小说项目生成缺失的世界观设定、角色、大纲、伏笔和章节写作指令。

重要规则：
1. 输出必须是严格的 JSON，不要包含 Markdown、代码块、注释或解释文字。
2. 不要覆盖已有内容。如果某项已经存在，留空列表即可。
3. 所有内容使用中文，符合中文小说创作语境。
4. 生成内容要能被后续 planner/screenwriter/author 直接使用。
5. 章节指令需包含 objective、key_events、emotion_tone、ending_hook、word_target。
"""

_ARC_PLAN_SYSTEM_PROMPT = """你是一位专业的小说情节规划师。你的任务是为指定章节范围生成弧线大纲、每章写作指令和必要伏笔。

重要规则：
1. 输出必须是严格的 JSON，不要包含 Markdown、代码块、注释或解释文字。
2. 不重新创世，不重写已确认基础设定。
3. 已存在的章节指令不要覆盖，只生成缺失的。
4. 所有内容使用中文，符合中文小说创作语境。
5. 大纲需要按弧线分段，每段覆盖若干章节。
"""


def _build_project_context(repo, project_id: str) -> dict[str, Any]:
    """Gather project context for prompt construction."""
    project = repo.get_project(project_id)
    if not project:
        return {}

    genesis = repo.get_latest_genesis_run(project_id)
    return {
        "project": project,
        "genesis": genesis,
        "world_settings": repo.list_world_settings(project_id),
        "characters": repo.list_characters(project_id, include_inactive=True),
        "outlines": repo.list_outlines(project_id),
        "plot_holes": repo.list_plot_holes(project_id),
    }


def _format_context(ctx: dict[str, Any]) -> str:
    """Format project context into a prompt string."""
    project = ctx.get("project", {})
    genesis = ctx.get("genesis")
    lines: list[str] = []

    lines.append("【项目信息】")
    lines.append(f"名称: {project.get('name', '未命名')}")
    lines.append(f"类型: {project.get('genre', '未指定')}")
    lines.append(f"描述: {project.get('description', '')}")
    lines.append(f"目标字数: {project.get('target_words', 0)}")
    lines.append(f"计划章节数: {project.get('total_chapters_planned', 0)}")
    lines.append("")
    lines.append(build_title_contract(project))

    if genesis and genesis.get("content"):
        lines.append("\n【创世草案】")
        lines.append(genesis["content"])

    if ctx.get("world_settings"):
        lines.append("\n【已有世界观设定】")
        for ws in ctx["world_settings"]:
            lines.append(f"- [{ws.get('category', '')}] {ws.get('title', '')}: {ws.get('content', '')}")

    if ctx.get("characters"):
        lines.append("\n【已有角色】")
        for ch in ctx["characters"]:
            lines.append(f"- {ch.get('name', '')} ({ch.get('role', '')}): {ch.get('description', '')}")

    if ctx.get("outlines"):
        lines.append("\n【已有大纲】")
        for ol in ctx["outlines"]:
            lines.append(f"- [{ol.get('level', '')}] {ol.get('title', '')}: {ol.get('content', '')}")

    if ctx.get("plot_holes"):
        lines.append("\n【已有伏笔】")
        for ph in ctx["plot_holes"]:
            lines.append(f"- [{ph.get('code', '')}] {ph.get('title', '')}: {ph.get('description', '')}")

    return "\n".join(lines)


def _build_autofill_prompt(
    ctx: dict[str, Any],
    chapter_start: int,
    chapter_end: int,
    missing_types: list[str],
) -> str:
    """Build the user prompt for auto-fill."""
    context_str = _format_context(ctx)

    lines: list[str] = [
        context_str,
        "",
        f"【任务】请为第 {chapter_start} 章到第 {chapter_end} 章生成缺失资料。",
        f"需要补齐的类型: {', '.join(missing_types)}",
        "",
        "【输出格式】严格 JSON，顶层字段:",
        "- world_settings: 世界观设定数组，每项含 category, title, content",
        "- characters: 角色数组，每项含 name, role, description, traits",
        "- outlines: 大纲数组，每项含 level, sequence, title, content, chapters_range",
        "- plot_holes: 伏笔数组，每项含 code, type, title, description, planted_chapter, planned_resolve_chapter",
        "- instructions: 章节指令数组，每项含 chapter_number, objective, key_events, plots_to_plant, plots_to_resolve, emotion_tone, ending_hook, word_target",
        "",
        "如果某类资料已经存在且不需要新增，返回空数组 []。",
        "所有新增资料必须严格遵守【书名契约】；如果已有资料与书名冲突，不要沿用错误方向。",
        "不要输出任何其他文字。",
    ]
    return "\n".join(lines)


def _build_arc_plan_prompt(
    ctx: dict[str, Any],
    chapter_start: int,
    chapter_end: int,
) -> str:
    """Build the user prompt for arc-plan."""
    context_str = _format_context(ctx)

    lines: list[str] = [
        context_str,
        "",
        f"【任务】请为第 {chapter_start} 章到第 {chapter_end} 章生成弧线规划和章节指令。",
        "",
        "【输出格式】严格 JSON，顶层字段:",
        "- outlines: 弧线大纲数组，每项含 level, sequence, title, content, chapters_range。每个大纲覆盖一段连续章节。",
        "- plot_holes: 新伏笔数组，每项含 code, type, title, description, planted_chapter, planned_resolve_chapter",
        "- instructions: 每章写作指令数组，每项含 chapter_number, objective, key_events, plots_to_plant, plots_to_resolve, emotion_tone, ending_hook, word_target",
        "",
        "如果某章已有指令，不需要覆盖，尽量只生成缺失部分。",
        "所有弧线规划和章节指令必须严格遵守【书名契约】，不得把故事推进成与书名无关的题材。",
        "不要输出任何其他文字。",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# LLM invocation helpers
# ---------------------------------------------------------------------------

def _invoke_structured(
    llm: LLMProvider,
    system_prompt: str,
    user_prompt: str,
    schema: type,
) -> dict[str, Any]:
    """Invoke LLM and return parsed JSON dict.

    Raises LLMOutputInvalid on parse/validation failure.
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    try:
        raw = llm.invoke_json(messages, schema=schema, temperature=0.7, agent_id="autonomous_planner")
    except TypeError as te:
        # v6.6.21-review: Fallback for test fakes that don't accept agent_id
        if "agent_id" in str(te):
            raw = llm.invoke_json(messages, schema=schema, temperature=0.7)
        else:
            raise
    except Exception as e:
        logger.warning("LLM invocation failed: %s", e)
        raise LLMOutputInvalid(f"LLM 调用失败: {e}") from e

    if not isinstance(raw, dict):
        raise LLMOutputInvalid(f"LLM 返回非对象: {type(raw).__name__}")

    return raw


class LLMOutputInvalid(Exception):
    """Raised when LLM output cannot be parsed or validated."""
    pass


def _text(value: Any) -> str:
    """Normalize provider scalar/list/dict values into DB-safe text."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _list_of_text(value: Any) -> list[str]:
    """Normalize provider scalar/list output into a list of strings."""
    if value is None:
        return []
    if isinstance(value, list):
        return [_text(item) for item in value if _text(item)]
    text = _text(value)
    return [text] if text else []


def _coerce_autofill_raw(raw: dict[str, Any]) -> dict[str, Any]:
    """Coerce common real-LLM shape drift before Pydantic validation."""
    data = dict(raw)

    characters = []
    for item in data.get("characters") or []:
        if not isinstance(item, dict):
            continue
        next_item = dict(item)
        next_item["name"] = _text(next_item.get("name"))
        next_item["role"] = _text(next_item.get("role")) or "supporting"
        next_item["description"] = _text(next_item.get("description"))
        next_item["traits"] = _text(next_item.get("traits"))
        characters.append(next_item)
    data["characters"] = characters

    instructions = []
    for item in data.get("instructions") or []:
        if not isinstance(item, dict):
            continue
        next_item = dict(item)
        next_item["objective"] = _text(next_item.get("objective"))
        next_item["key_events"] = _text(next_item.get("key_events"))
        next_item["plots_to_plant"] = _list_of_text(next_item.get("plots_to_plant"))
        next_item["plots_to_resolve"] = _list_of_text(next_item.get("plots_to_resolve"))
        next_item["emotion_tone"] = _text(next_item.get("emotion_tone"))
        next_item["ending_hook"] = _text(next_item.get("ending_hook"))
        instructions.append(next_item)
    data["instructions"] = instructions

    return data


# ---------------------------------------------------------------------------
# Auto-fill executor
# ---------------------------------------------------------------------------

def _determine_missing_types(repo, project_id: str, chapter_start: int, chapter_end: int) -> list[str]:
    """Determine which content types are missing."""
    missing: list[str] = []

    if len(repo.list_world_settings(project_id)) == 0:
        missing.append("world_settings")
    if len(repo.list_characters(project_id, include_inactive=True)) == 0:
        missing.append("characters")
    if len(repo.list_outlines(project_id)) == 0:
        missing.append("outlines")
    if len(repo.list_plot_holes(project_id)) == 0:
        missing.append("plot_holes")

    # Check instructions in range
    has_missing_instructions = False
    for ch_num in range(chapter_start, chapter_end + 1):
        if repo.get_instruction_by_chapter(project_id, ch_num) is None:
            has_missing_instructions = True
            break
    if has_missing_instructions:
        missing.append("instructions")

    return missing


def execute_autofill(
    repo,
    llm: LLMProvider,
    project_id: str,
    chapter_start: int,
    chapter_end: int,
    missing_types_override: list[str] | None = None,
) -> tuple[dict[str, int], list[str], list[str]]:
    """Execute real LLM auto-fill for missing project context.

    Returns:
        (created_counts, warnings, missing_types) where created_counts maps type -> count.
    """
    created = {
        "world_settings": 0,
        "characters": 0,
        "outlines": 0,
        "instructions": 0,
        "plot_holes": 0,
    }
    warnings: list[str] = []

    missing_types = (
        [item for item in missing_types_override if item]
        if missing_types_override is not None
        else _determine_missing_types(repo, project_id, chapter_start, chapter_end)
    )

    # If nothing is missing, return early
    if not missing_types:
        return created, warnings, missing_types

    if missing_types_override is None and len(missing_types) > 1:
        all_missing = list(missing_types)
        for missing_type in all_missing:
            partial_created, partial_warnings, _partial_missing = execute_autofill(
                repo,
                llm,
                project_id,
                chapter_start,
                chapter_end,
                missing_types_override=[missing_type],
            )
            for key, count in partial_created.items():
                created[key] += count
            warnings.extend(partial_warnings)
        return created, warnings, all_missing

    ctx = _build_project_context(repo, project_id)
    user_prompt = _build_autofill_prompt(ctx, chapter_start, chapter_end, missing_types)

    try:
        raw = _invoke_structured(llm, _AUTOFILL_SYSTEM_PROMPT, user_prompt, AutoFillLLMOutput)
    except LLMOutputInvalid as e:
        warnings.append(str(e))
        return created, warnings, missing_types

    # Validate against Pydantic schema
    try:
        output = AutoFillLLMOutput(**_coerce_autofill_raw(raw))
    except ValidationError as e:
        logger.warning("Auto-fill output validation failed: %s", e)
        warnings.append(f"LLM 输出结构校验失败: {e}")
        return created, warnings, missing_types

    # Write world_settings (only if missing, skip if already exists)
    if "world_settings" in missing_types:
        existing_ws_titles = {ws.get("title", "") for ws in ctx.get("world_settings", [])}
        for ws in output.world_settings:
            if ws.title in existing_ws_titles:
                warnings.append(f"世界观设定 '{ws.title}' 已存在，跳过")
                continue
            repo.create_world_setting(project_id, ws.category, ws.title, ws.content)
            created["world_settings"] += 1
    elif output.world_settings:
        warnings.append("LLM 返回了 world_settings，但该类型已有数据，已忽略")

    # Write characters (only if missing, skip if name already exists)
    if "characters" in missing_types:
        existing_char_names = {ch.get("name", "") for ch in ctx.get("characters", [])}
        for ch in output.characters:
            if ch.name in existing_char_names:
                warnings.append(f"角色 '{ch.name}' 已存在，跳过")
                continue
            repo.create_character(
                project_id,
                name=ch.name,
                role=ch.role,
                description=ch.description,
                traits=ch.traits,
            )
            created["characters"] += 1
    elif output.characters:
        warnings.append("LLM 返回了 characters，但该类型已有数据，已忽略")

    # Write outlines (only if missing, skip if similar title exists)
    if "outlines" in missing_types:
        existing_ol_titles = {ol.get("title", "") for ol in ctx.get("outlines", [])}
        for ol in output.outlines:
            if ol.title in existing_ol_titles:
                warnings.append(f"大纲 '{ol.title}' 已存在，跳过")
                continue
            repo.create_outline(project_id, ol.level, ol.sequence, ol.title, ol.content, ol.chapters_range)
            created["outlines"] += 1
    elif output.outlines:
        warnings.append("LLM 返回了 outlines，但该类型已有数据，已忽略")

    # Write plot holes (only if missing, skip if code already exists)
    if "plot_holes" in missing_types:
        existing_ph_codes = {ph.get("code", "") for ph in ctx.get("plot_holes", [])}
        for ph in output.plot_holes:
            if ph.code in existing_ph_codes:
                warnings.append(f"伏笔 '{ph.code}' 已存在，跳过")
                continue
            repo.create_plot_hole(
                project_id, ph.code, ph.type, ph.title, ph.description,
                ph.planted_chapter, ph.planned_resolve_chapter, ph.status,
            )
            created["plot_holes"] += 1
    elif output.plot_holes:
        warnings.append("LLM 返回了 plot_holes，但该类型已有数据，已忽略")

    # Write instructions (only if missing, skip if chapter already has one)
    project = repo.get_project(project_id)
    if "instructions" in missing_types:
        for inst in output.instructions:
            if chapter_start <= inst.chapter_number <= chapter_end:
                existing = repo.get_instruction_by_chapter(project_id, inst.chapter_number)
                if existing is not None:
                    warnings.append(f"第 {inst.chapter_number} 章指令已存在，跳过")
                    continue
                # v6.10.7: Override LLM word_target with project-derived value
                # to prevent LLM from hallucinating unreasonable targets.
                word_target = derive_word_target(None, project)
                if inst.word_target != word_target:
                    warnings.append(
                        f"第 {inst.chapter_number} 章 LLM 字数目标 {inst.word_target} "
                        f"被修正为项目默认值 {word_target}"
                    )
                repo.create_instruction(
                    project_id,
                    chapter_number=inst.chapter_number,
                    objective=inst.objective,
                    key_events=inst.key_events,
                    plots_to_plant=json.dumps(inst.plots_to_plant, ensure_ascii=False),
                    plots_to_resolve=json.dumps(inst.plots_to_resolve, ensure_ascii=False),
                    emotion_tone=inst.emotion_tone,
                    ending_hook=inst.ending_hook,
                    word_target=word_target,
                    status="active",
                )
                created["instructions"] += 1
    elif output.instructions:
        warnings.append("LLM 返回了 instructions，但目标章节范围已有指令，已忽略")

    return created, warnings, missing_types


# ---------------------------------------------------------------------------
# Arc-plan executor
# ---------------------------------------------------------------------------

def execute_arc_plan(
    repo,
    llm: LLMProvider,
    project_id: str,
    chapter_start: int,
    chapter_end: int,
) -> tuple[dict[str, int], list[str]]:
    """Execute real LLM arc-plan for a chapter range.

    Returns:
        (created_counts, warnings) where created_counts maps type -> count.
    """
    created = {
        "outlines": 0,
        "instructions": 0,
        "plot_holes": 0,
    }
    warnings: list[str] = []

    ctx = _build_project_context(repo, project_id)
    user_prompt = _build_arc_plan_prompt(ctx, chapter_start, chapter_end)

    try:
        raw = _invoke_structured(llm, _ARC_PLAN_SYSTEM_PROMPT, user_prompt, ArcPlanLLMOutput)
    except LLMOutputInvalid as e:
        warnings.append(str(e))
        return created, warnings

    try:
        output = ArcPlanLLMOutput(**raw)
    except ValidationError as e:
        logger.warning("Arc-plan output validation failed: %s", e)
        warnings.append(f"LLM 输出结构校验失败: {e}")
        return created, warnings

    # Write outlines (skip duplicates by title or chapters_range)
    existing_ol_titles = {ol.get("title", "") for ol in ctx.get("outlines", [])}
    existing_ol_ranges = {ol.get("chapters_range", "") for ol in ctx.get("outlines", [])}
    for ol in output.outlines:
        if ol.title in existing_ol_titles:
            warnings.append(f"大纲 '{ol.title}' 已存在，跳过")
            continue
        if ol.chapters_range in existing_ol_ranges:
            warnings.append(f"章节范围 '{ol.chapters_range}' 已有大纲覆盖，跳过")
            continue
        # Auto-assign sequence if not provided
        seq = ol.sequence
        if seq <= 0:
            all_seqs = [o.get("sequence", 0) for o in repo.list_outlines(project_id)]
            seq = max(all_seqs, default=0) + 1
        repo.create_outline(project_id, ol.level, seq, ol.title, ol.content, ol.chapters_range)
        created["outlines"] += 1

    # Write plot holes (skip duplicates by code)
    existing_ph_codes = {ph.get("code", "") for ph in ctx.get("plot_holes", [])}
    for ph in output.plot_holes:
        if ph.code in existing_ph_codes:
            warnings.append(f"伏笔 '{ph.code}' 已存在，跳过")
            continue
        repo.create_plot_hole(
            project_id, ph.code, ph.type, ph.title, ph.description,
            ph.planted_chapter, ph.planned_resolve_chapter, ph.status,
        )
        created["plot_holes"] += 1

    # Write instructions (skip if chapter already has one)
    project = repo.get_project(project_id)
    for inst in output.instructions:
        if chapter_start <= inst.chapter_number <= chapter_end:
            existing = repo.get_instruction_by_chapter(project_id, inst.chapter_number)
            if existing is not None:
                warnings.append(f"第 {inst.chapter_number} 章指令已存在，跳过")
                continue
            # v6.10.7: Override LLM word_target with project-derived value
            word_target = derive_word_target(None, project)
            if inst.word_target != word_target:
                warnings.append(
                    f"第 {inst.chapter_number} 章 LLM 字数目标 {inst.word_target} "
                    f"被修正为项目默认值 {word_target}"
                )
            repo.create_instruction(
                project_id,
                chapter_number=inst.chapter_number,
                objective=inst.objective,
                key_events=inst.key_events,
                plots_to_plant=json.dumps(inst.plots_to_plant, ensure_ascii=False),
                plots_to_resolve=json.dumps(inst.plots_to_resolve, ensure_ascii=False),
                emotion_tone=inst.emotion_tone,
                ending_hook=inst.ending_hook,
                word_target=word_target,
                status="active",
            )
            created["instructions"] += 1

    return created, warnings

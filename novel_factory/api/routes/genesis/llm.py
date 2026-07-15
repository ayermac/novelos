"""Genesis LLM operations — prompt building, invocation, and repair.

v6.11.0 refactor: Extracted from _endpoints.py for modular organization.
Contains:
- Prompt building functions for Genesis segments
- LLM invocation and draft generation
- Instruction quality repair
- Recovery and fallback handling
"""

from __future__ import annotations

import json
import asyncio
import logging
from typing import Callable

from novel_factory.agent_runtime.title_contract import build_title_contract
from novel_factory.llm.provider import is_configured_live_provider
from novel_factory.quality.genesis_quality_gate import evaluate_genesis_draft

from .models import GenesisGenerateRequest
from .progress import (
    GENESIS_SEGMENT_LABELS,
    GENESIS_SEGMENT_MAX_TOKENS,
    GENESIS_INSTRUCTION_CHUNK_SIZE,
    GENESIS_REPAIRABLE_INSTRUCTION_CODES,
)
from .utils import _as_list
from .normalizer import (
    _normalize_genesis_draft,
    _dedupe_genesis_draft,
)
from .scaffold import (
    _generate_genesis_scaffold,
    _fill_missing_genesis_sections,
    _merge_genesis_drafts,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Prompt Building Functions
# =============================================================================


def _build_genesis_common_context(body: GenesisGenerateRequest) -> str:
    """Build shared project context for segmented Genesis prompts."""
    title_contract = build_title_contract({
        "name": body.title,
        "genre": body.genre,
        "description": body.premise,
        "target_words": body.target_words,
        "total_chapters_planned": body.target_chapters,
    })
    premise_display = body.premise.strip() or f"基于标题《{body.title}》和类型「{body.genre}」自动推断故事前提"
    return (
        f"标题: {body.title}\n"
        f"类型: {body.genre}\n"
        f"创意: {premise_display}\n"
        "创世范围说明: 本次需要生成整本书的底盘设定，并只展开首批章节指令。\n"
        f"首批章节规划范围: 前 {body.target_chapters} 章，首批合计约 {body.target_words} 字\n"
        "注意: 上面的章数和字数不是整本书总篇幅，后续章节会通过章节批次规划继续延展。\n"
        f"读者: {body.target_audience}\n"
        f"风格: {body.style_preference}\n"
        f"约束: {body.constraints}\n\n"
        f"{title_contract}\n"
    )


def _build_genesis_segment_prompt(
    body: GenesisGenerateRequest,
    *,
    segment: str,
    draft_json: str | None = None,
    chapter_start: int | None = None,
    chapter_end: int | None = None,
) -> str:
    """Build a short, focused Genesis prompt for one segment."""
    context = _build_genesis_common_context(body)
    draft_block = ""
    if draft_json:
        draft_block = f"【已有草案 JSON】\n{draft_json}\n\n"

    if segment == "foundation":
        return (
            "【生成段落】foundation\n"
            f"{context}\n"
            "请只返回严格 JSON 对象，且只包含以下字段:\n"
            "- project_updates: {\"description\": \"项目描述\"}\n"
            "- world_settings: [{\"title\": \"\", \"category\": \"\", \"content\": \"\"}]\n\n"
            "要求：\n"
            "1. 只生成世界观底座、时代背景、能力规则、冲突结构，不要返回角色、势力、大纲、伏笔或章节指令。\n"
            "2. project_updates 的 description 要用一句话概括项目核心卖点。\n"
            "3. world_settings 至少 3 项，避免空泛和重复。\n"
            "4. 输出必须是纯 JSON，不要 Markdown、解释或尾逗号。"
        )

    if segment == "cast":
        return (
            "【生成段落】cast\n"
            f"{context}\n"
            f"{draft_block}"
            "请只返回严格 JSON 对象，且只包含以下字段:\n"
            "- characters: [{\"name\": \"\", \"role\": \"protagonist|antagonist|supporting\", \"description\": \"\", \"traits\": \"\"}]\n"
            "- factions: [{\"name\": \"\", \"type\": \"\", \"description\": \"\", \"relationship_with_protagonist\": \"\"}]\n\n"
            "要求：\n"
            "1. 角色必须包含主角、核心盟友或重要配角、主要反派或对立人物。\n"
            "2. 每个角色必须写清目标、矛盾或秘密、与主角的利益关系。\n"
            "3. 势力必须写清资源/手段、当前阶段行动、对主角态度。\n"
            "4. 不要返回 project_updates、world_settings、outlines、plot_holes 或 instructions。\n"
            "5. 输出必须是纯 JSON，不要 Markdown、解释或尾逗号。"
        )

    if segment == "plot":
        return (
            "【生成段落】plot\n"
            f"{context}\n"
            f"{draft_block}"
            "请只返回严格 JSON 对象，且只包含以下字段:\n"
            "- outlines: [{\"chapters_range\": \"1-3\", \"title\": \"\", \"content\": \"\", \"level\": \"arc\", \"sequence\": 1}]\n"
            "- plot_holes: [{\"code\": \"PH-001\", \"type\": \"\", \"title\": \"\", \"description\": \"\", \"planted_chapter\": 1, \"planned_resolve_chapter\": 10, \"status\": \"planted\"}]\n\n"
            "要求：\n"
            "1. 大纲必须写出阶段冲突、转折、阶段结果。\n"
            "2. 伏笔必须写出触发场景、读者看到的表象、真相方向、预计兑现章节。\n"
            "3. 不要返回 project_updates、world_settings、characters、factions 或 instructions。\n"
            "4. 输出必须是纯 JSON，不要 Markdown、解释或尾逗号。"
        )

    if segment == "instructions":
        if chapter_start is None or chapter_end is None:
            raise ValueError("instructions segment requires chapter range")
        return (
            f"【生成段落】instructions:{chapter_start}-{chapter_end}\n"
            f"{context}\n"
            f"{draft_block}"
            f"请只返回第 {chapter_start}-{chapter_end} 章的章节指令，且只包含以下字段:\n"
            "- instructions: [{\"chapter_number\": 1, \"objective\": \"\", \"protagonist\": \"\", \"primary_location\": \"\", \"opposing_force\": \"\", \"action_chain\": [\"\", \"\", \"\"], \"visible_result\": \"\", \"state_change\": \"\", \"key_events\": \"\", \"emotion_tone\": \"\", \"ending_hook\": \"\", \"continuity_seed\": \"\", \"word_target\": 3000}]\n\n"
            "要求：\n"
            "1. 只生成当前章段，不要补写其他章。\n"
            "2. 每章必须是一张可执行施工单，不是阶段大纲；必须写清谁、在哪里、被谁阻拦、连续做了什么、最后局势如何改变。\n"
            "3. objective 必须包含本章具体目标、主要阻力和结果变化，禁止只写\"扩大冲突/推动剧情/获得主动权/打破定律/吸引注意\"这类抽象总结。\n"
            "4. protagonist 必须使用具体角色名；primary_location 必须具体到场景或地点；opposing_force 必须写具体人物、组织或压力源。\n"
            "5. action_chain 必须至少 3 步，每一步都要包含执行者、动作和对象，例如\"陆恒在临江觉醒者学院考核场召唤刀盾手挡住E级魔物群\"。\n"
            "6. visible_result 写读者可见的外部结果；state_change 写本章结束后主角、敌人、势力或资源状态的变化。\n"
            "7. key_events 至少写 3 个具体事件，并与 action_chain 一致；ending_hook 和 continuity_seed 必须可直接承接下一章。\n"
            "8. 不要返回 project_updates、world_settings、characters、factions、outlines 或 plot_holes。\n"
            "9. 输出必须是纯 JSON，不要 Markdown、解释或尾逗号。"
        )

    raise ValueError(f"Unknown genesis segment: {segment}")


def _build_genesis_llm(settings):
    """Build the dedicated Genesis LLM profile."""
    from novel_factory.workflow.runner import _build_llm_router

    llm = _build_llm_router(settings, "real").for_agent("genesis")
    if is_configured_live_provider(llm):
        llm.config.request_timeout_seconds = max(llm.config.request_timeout_seconds, 180)
        llm.config.retry_attempts = max(llm.config.retry_attempts, 2)
    return llm


def _build_genesis_completion_prompt(
    body: GenesisGenerateRequest,
    current_draft: dict,
    missing_sections: list[str],
) -> str:
    """Build a focused prompt that asks the LLM to fill missing Genesis sections."""
    missing_labels = "、".join(missing_sections)
    current_json = json.dumps(current_draft, ensure_ascii=False)[:12000]
    title_contract = build_title_contract({
        "name": body.title,
        "genre": body.genre,
        "description": body.premise,
        "target_words": body.target_words,
        "total_chapters_planned": body.target_chapters,
    })
    return (
        "下面的创世草案不完整。请只补齐缺失部分，保持已有设定方向一致，不要重写已有内容。\n"
        f"标题: {body.title}\n"
        f"类型: {body.genre}\n"
        f"创意: {body.premise.strip() or '根据标题和类型推断'}\n"
        f"首批章节规划范围: 前 {body.target_chapters} 章，约 {body.target_words} 字\n"
        f"缺失部分: {missing_labels}\n\n"
        f"{title_contract}\n\n"
        f"【已有草案 JSON】\n{current_json}\n\n"
        "请返回严格 JSON 对象，顶层字段可以只包含缺失部分，但字段结构必须符合：\n"
        "- world_settings: [{\"title\": \"\", \"category\": \"\", \"content\": \"\"}]\n"
        "- characters: [{\"name\": \"\", \"role\": \"protagonist|antagonist|supporting\", \"description\": \"\", \"traits\": \"\"}]\n"
        "- factions: [{\"name\": \"\", \"type\": \"\", \"description\": \"\", \"relationship_with_protagonist\": \"\"}]\n"
        "- outlines: [{\"chapters_range\": \"1-3\", \"title\": \"\", \"content\": \"\", \"level\": \"arc\", \"sequence\": 1}]\n"
        "- plot_holes: [{\"code\": \"PH-001\", \"type\": \"\", \"title\": \"\", \"description\": \"\", \"planted_chapter\": 1, \"planned_resolve_chapter\": 10, \"status\": \"planted\"}]\n"
        "- instructions: [{\"chapter_number\": 1, \"objective\": \"\", \"protagonist\": \"\", \"primary_location\": \"\", \"opposing_force\": \"\", \"action_chain\": [\"\", \"\", \"\"], \"visible_result\": \"\", \"state_change\": \"\", \"key_events\": \"\", \"emotion_tone\": \"\", \"ending_hook\": \"\", \"continuity_seed\": \"\", \"word_target\": 3000}]\n\n"
        "要求：\n"
        "1. 角色至少包含主角、核心盟友/女主/重要配角、主要反派或对立势力人物，必须有具体姓名、目标、矛盾和利益关系。\n"
        "2. 大纲至少覆盖首批章节范围，必须包含阶段冲突、转折和阶段结果。\n"
        "3. 章节指令必须覆盖首批每一章，包含 objective、protagonist、primary_location、opposing_force、action_chain、visible_result、state_change、key_events、ending_hook、continuity_seed。\n"
        "4. 输出纯 JSON，不要 Markdown、解释、注释或尾逗号。"
    )


# =============================================================================
# LLM Invocation Functions
# =============================================================================


async def _invoke_genesis_segment(
    llm,
    *,
    prompt: str,
    max_tokens: int,
) -> dict:
    """Invoke one Genesis segment with a bounded response budget."""
    return await asyncio.to_thread(
        llm.invoke_json,
        [
            {
                "role": "system",
                "content": "你只输出纯 JSON 对象，不要输出任何 Markdown 代码块、注释或解释文字。不要在 JSON 中添加尾逗号。",
            },
            {"role": "user", "content": prompt},
        ],
        max_tokens=max_tokens,
        max_retries=2,
    )


async def _generate_real_draft(
    body: GenesisGenerateRequest,
    settings,
    *,
    run_id: str | None = None,
    progress: Callable | None = None,
) -> dict:
    """Generate a genesis draft using real LLM.

    v6.7.7: Accepts optional progress callback for SSE streaming.
    """
    from novel_factory.llm.openai_compatible import LLMTimeoutError

    def _emit(event_type: str, **kwargs):
        if progress and run_id:
            progress(event_type, {"run_id": run_id, **kwargs})

    llm = _build_genesis_llm(settings)
    merged: dict | None = None
    active_segment = "foundation"

    try:
        # Foundation segment
        active_segment = "foundation"
        _emit("segment_started", segment="foundation", label=GENESIS_SEGMENT_LABELS["foundation"])
        foundation_prompt = _build_genesis_segment_prompt(body, segment="foundation")
        foundation = await _invoke_genesis_segment(
            llm,
            prompt=foundation_prompt,
            max_tokens=GENESIS_SEGMENT_MAX_TOKENS["foundation"],
        )
        merged = _merge_genesis_drafts(None, foundation)
        _emit("segment_completed", segment="foundation", label=GENESIS_SEGMENT_LABELS["foundation"])

        # Cast segment
        active_segment = "cast"
        _emit("segment_started", segment="cast", label=GENESIS_SEGMENT_LABELS["cast"])
        cast_prompt = _build_genesis_segment_prompt(
            body,
            segment="cast",
            draft_json=json.dumps(merged, ensure_ascii=False)[:10000],
        )
        cast = await _invoke_genesis_segment(
            llm,
            prompt=cast_prompt,
            max_tokens=GENESIS_SEGMENT_MAX_TOKENS["cast"],
        )
        merged = _merge_genesis_drafts(merged, cast)
        _emit("segment_completed", segment="cast", label=GENESIS_SEGMENT_LABELS["cast"])

        # Plot segment
        active_segment = "plot"
        _emit("segment_started", segment="plot", label=GENESIS_SEGMENT_LABELS["plot"])
        plot_prompt = _build_genesis_segment_prompt(
            body,
            segment="plot",
            draft_json=json.dumps(merged, ensure_ascii=False)[:10000],
        )
        plot = await _invoke_genesis_segment(
            llm,
            prompt=plot_prompt,
            max_tokens=GENESIS_SEGMENT_MAX_TOKENS["plot"],
        )
        merged = _merge_genesis_drafts(merged, plot)
        _emit("segment_completed", segment="plot", label=GENESIS_SEGMENT_LABELS["plot"])

        # Instructions segment (per-chunk)
        chapter_count = max(1, int(body.target_chapters or 1))
        chunk_size = max(1, GENESIS_INSTRUCTION_CHUNK_SIZE)
        instruction_max_tokens = min(4500, 1800 + chunk_size * 420)
        for chapter_start in range(1, chapter_count + 1, chunk_size):
            chapter_end = min(chapter_count, chapter_start + chunk_size - 1)
            active_segment = f"instructions:{chapter_start}-{chapter_end}"
            _emit("chapter_start", chapter_start=chapter_start, chapter_end=chapter_end,
                  label=f"正在生成章节指令 {chapter_start}-{chapter_end}")
            instruction_prompt = _build_genesis_segment_prompt(
                body,
                segment="instructions",
                draft_json=json.dumps(merged, ensure_ascii=False)[:12000],
                chapter_start=chapter_start,
                chapter_end=chapter_end,
            )
            instruction_patch = await _invoke_genesis_segment(
                llm,
                prompt=instruction_prompt,
                max_tokens=instruction_max_tokens,
            )
            merged = _merge_genesis_drafts(merged, instruction_patch)
            _emit("chapter_end", chapter_start=chapter_start, chapter_end=chapter_end,
                  label=f"章节指令 {chapter_start}-{chapter_end} 完成")
    except LLMTimeoutError as exc:
        logger.warning(
            "Genesis segment timed out; using local recovery segment=%s title=%s",
            active_segment,
            body.title,
            exc_info=True,
        )
        _emit("segment_started", segment="repair", label="LLM 超时，正在保留已完成分段并本地补齐")
        recovered = _recover_genesis_from_partial_draft(
            body,
            merged,
            reason=f"{active_segment}_llm_unavailable",
            error_message=str(exc),
        )
        _emit("segment_completed", segment="repair", label="已保留可用分段并完成本地补齐")
        return recovered

    return _dedupe_genesis_draft(_normalize_genesis_draft(merged)) or merged


async def _complete_real_genesis_draft(
    body: GenesisGenerateRequest,
    settings,
    draft: dict,
    *,
    run_id: str | None = None,
    progress: Callable | None = None,
) -> dict:
    """Repair incomplete real Genesis output before it becomes reviewable."""
    from .scaffold import _missing_required_genesis_sections
    from novel_factory.llm.openai_compatible import LLMTimeoutError

    normalized = _dedupe_genesis_draft(_normalize_genesis_draft(draft)) or {}
    missing = _missing_required_genesis_sections(normalized)
    if not missing:
        return normalized

    llm = _build_genesis_llm(settings)
    for _attempt in range(2):
        prompt = _build_genesis_completion_prompt(body, normalized, missing)
        try:
            patch = await asyncio.to_thread(
                llm.invoke_json,
                [
                    {
                        "role": "system",
                        "content": "你只输出纯 JSON 对象，用于补齐小说项目创世草案缺失部分。",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=9000,
                max_retries=2,
            )
        except LLMTimeoutError as exc:
            logger.warning(
                "Genesis completion repair timed out; using local recovery title=%s",
                body.title,
                exc_info=True,
            )
            return _recover_genesis_from_partial_draft(
                body,
                normalized,
                reason="completion_llm_unavailable",
                error_message=str(exc),
            )
        normalized_patch = _dedupe_genesis_draft(_normalize_genesis_draft(patch))
        normalized = _merge_genesis_drafts(normalized, normalized_patch)
        missing = _missing_required_genesis_sections(normalized)
        if not missing:
            return normalized

    return _mark_genesis_local_recovery(
        _fill_missing_genesis_sections(body, normalized),
        reason="incomplete_json",
        error_message="真实 LLM 草案在两次补齐后仍缺少必需创世章节，系统已用本地恢复内容补齐。",
    )


# =============================================================================
# Instruction Quality Repair
# =============================================================================


def _instruction_repair_issue_count(quality_report) -> int:
    """Count repairable instruction-quality issues in a Genesis quality report."""
    return sum(
        1
        for issue in quality_report.issues
        if issue.section == "instructions"
        and issue.code in GENESIS_REPAIRABLE_INSTRUCTION_CODES
        and issue.severity == "blocker"
    )


def _has_instruction_repair_target(quality_report) -> bool:
    """Return whether a blocked Genesis draft should receive instruction-only repair."""
    return _instruction_repair_issue_count(quality_report) > 0


def _format_genesis_quality_issues_for_prompt(quality_report) -> str:
    """Format instruction quality issues for a focused repair prompt."""
    lines: list[str] = []
    for issue in quality_report.issues:
        if issue.section != "instructions":
            continue
        if issue.code not in GENESIS_REPAIRABLE_INSTRUCTION_CODES:
            continue
        lines.append(
            f"- {issue.code} [{issue.severity}]: {issue.message}"
            + (f"；修复要求: {issue.suggestion}" if issue.suggestion else "")
        )
    return "\n".join(lines) or "- 章节指令缺少具体人物、地点、行动链或结果变化"


def _build_genesis_instruction_repair_prompt(
    body: GenesisGenerateRequest,
    draft: dict,
    quality_report,
) -> str:
    """Build a focused prompt that repairs only Genesis chapter instructions."""
    current_json = json.dumps(draft, ensure_ascii=False)[:18000]
    issue_text = _format_genesis_quality_issues_for_prompt(quality_report)
    return (
        "下面的小说创世草案只有章节指令质量未达标。请只重写 instructions，不要改世界观、角色、势力、大纲或伏笔。\n"
        f"标题: {body.title}\n"
        f"类型: {body.genre}\n"
        f"创意: {body.premise.strip() or '根据标题和类型推断'}\n"
        f"首批章节范围: 前 {body.target_chapters} 章\n\n"
        f"【质量问题】\n{issue_text}\n\n"
        f"【已有草案 JSON】\n{current_json}\n\n"
        "请返回严格 JSON 对象，且只包含 instructions 字段：\n"
        "{\"instructions\": [{\"chapter_number\": 1, \"objective\": \"\", \"protagonist\": \"\", \"primary_location\": \"\", \"opposing_force\": \"\", \"action_chain\": [\"\", \"\", \"\"], \"visible_result\": \"\", \"state_change\": \"\", \"key_events\": \"\", \"emotion_tone\": \"\", \"ending_hook\": \"\", \"continuity_seed\": \"\", \"word_target\": 3000}]}\n\n"
        "硬性要求：\n"
        "1. 必须覆盖已有草案中的每一章，不得增删章节。\n"
        "2. 每章必须具体到人物、地点、阻力、三步以上行动链、可见结果和状态变化。\n"
        "3. objective 必须写成本章可执行目标：主角要做什么、被谁/什么阻拦、结束时局势如何变化。\n"
        "4. key_events 至少 3 个具体事件，必须与 action_chain 一致。\n"
        "5. ending_hook 和 continuity_seed 必须能直接指导下一章承接。\n"
        "6. 禁止只写阶段目标、抽象总结或营销式概括。\n"
        "7. 输出纯 JSON，不要 Markdown、解释、注释或尾逗号。"
    )


def _instruction_repair_rank(quality_report) -> tuple[int, int, int]:
    """Rank instruction repair candidates; lower is better."""
    blocking_count = sum(1 for issue in quality_report.issues if issue.severity == "blocker")
    return (
        _instruction_repair_issue_count(quality_report),
        blocking_count,
        -quality_report.score,
    )


def _build_local_instruction_repair_candidate(
    body: GenesisGenerateRequest,
    draft: dict,
):
    """Deterministically rebuild instructions from existing Genesis entities."""
    scaffold = _generate_genesis_scaffold(body, seed_draft=draft)
    repaired_instructions = scaffold.get("instructions")
    if not isinstance(repaired_instructions, list) or not repaired_instructions:
        return draft, evaluate_genesis_draft(
            draft,
            title=body.title,
            genre=body.genre,
            premise=body.premise,
            target_chapters=body.target_chapters,
        )

    candidate = dict(draft)
    candidate["instructions"] = repaired_instructions
    meta = dict(candidate.get("_meta") or {})
    warnings = list(meta.get("warnings") or [])
    warning = "章节指令存在模板化或重复问题，已基于现有角色/势力进行本地重建。"
    if warning not in warnings:
        warnings.append(warning)
    meta.update({
        "instruction_repair_source": "local_seeded_rebuild",
        "warnings": warnings,
    })
    candidate["_meta"] = meta
    candidate = _dedupe_genesis_draft(_normalize_genesis_draft(candidate)) or candidate
    report = evaluate_genesis_draft(
        candidate,
        title=body.title,
        genre=body.genre,
        premise=body.premise,
        target_chapters=body.target_chapters,
    )
    return candidate, report


async def _repair_genesis_instruction_quality(
    body: GenesisGenerateRequest,
    settings,
    draft: dict,
    quality_report,
) -> dict:
    """Repair instruction-only Genesis quality failures without regenerating other sections."""
    if not _has_instruction_repair_target(quality_report):
        return draft

    best_draft = draft
    best_report = quality_report
    local_draft, local_report = _build_local_instruction_repair_candidate(body, draft)
    if _instruction_repair_rank(local_report) < _instruction_repair_rank(best_report):
        best_draft = local_draft
        best_report = local_report
    if not _has_instruction_repair_target(best_report):
        return best_draft

    llm = _build_genesis_llm(settings)

    for _attempt in range(2):
        prompt = _build_genesis_instruction_repair_prompt(body, best_draft, best_report)
        try:
            patch = await asyncio.to_thread(
                llm.invoke_json,
                [
                    {
                        "role": "system",
                        "content": "你只输出纯 JSON 对象，用于定向修复小说创世草案的章节指令。",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=min(9000, 2600 + max(1, len(_as_list(best_draft.get("instructions", [])))) * 650),
                max_retries=2,
            )
        except Exception:
            logger.warning("Genesis instruction quality repair failed", exc_info=True)
            return best_draft

        normalized_patch = _dedupe_genesis_draft(_normalize_genesis_draft(patch)) or {}
        repaired_instructions = normalized_patch.get("instructions")
        if not isinstance(repaired_instructions, list) or not repaired_instructions:
            continue

        candidate = _merge_genesis_drafts(best_draft, {"instructions": repaired_instructions})
        candidate = _dedupe_genesis_draft(_normalize_genesis_draft(candidate)) or candidate
        candidate_report = evaluate_genesis_draft(
            candidate,
            title=body.title,
            genre=body.genre,
            premise=body.premise,
            target_chapters=body.target_chapters,
        )

        if _instruction_repair_rank(candidate_report) < _instruction_repair_rank(best_report):
            best_draft = candidate
            best_report = candidate_report
        if not _has_instruction_repair_target(candidate_report):
            return candidate

    return best_draft


# =============================================================================
# Recovery and Fallback Functions
# =============================================================================


def _mark_genesis_generation_fallback(
    draft: dict,
    *,
    reason: str,
    error_message: str,
) -> dict:
    """Mark a generated Genesis draft as a degraded local fallback."""
    marked = dict(draft)
    meta = marked.get("_meta")
    if not isinstance(meta, dict):
        meta = {}
    warnings = list(meta.get("warnings") or [])
    warning = "真实 LLM 输出不是可解析 JSON，已生成系统兜底草案。请重新生成或人工补全后再批准。"
    if warning not in warnings:
        warnings.append(warning)
    meta.update({
        "source": "scaffold_fallback",
        "quality_status": "scaffold_fallback",
        "generation_fallback": True,
        "fallback_reason": reason,
        "original_error": error_message[:500],
        "warnings": warnings,
    })
    marked["_meta"] = meta
    return marked


def _mark_genesis_local_recovery(
    draft: dict,
    *,
    reason: str,
    error_message: str,
) -> dict:
    """Mark local Genesis recovery content as reviewable instead of blocked."""
    recovered = dict(draft)
    meta = dict(recovered.get("_meta") or {})
    warnings = [
        warning
        for warning in list(meta.get("warnings") or [])
        if "兜底模板" not in str(warning) and "系统模板补齐" not in str(warning)
    ]
    warning = "真实 LLM 输出不完整或不是可解析 JSON，系统已根据项目描述生成可审核的本地恢复草案。"
    if warning not in warnings:
        warnings.append(warning)
    meta.update({
        "source": "local_recovery",
        "quality_status": "recovered_from_invalid_json"
        if reason == "invalid_json"
        else "recovered_from_incomplete_json",
        "generation_fallback": True,
        "fallback_reason": reason,
        "original_error": error_message[:500],
        "warnings": warnings,
    })
    recovered["_meta"] = meta
    return recovered


def _build_genesis_recovery_draft(
    body: GenesisGenerateRequest,
    *,
    reason: str,
    error_message: str,
) -> dict:
    """Build a usable local Genesis draft after recoverable provider failure.

    Invalid provider JSON and transient provider failures are not proof that the
    user's project should degrade into an unapprovable template. This recovery
    path uses the same deterministic section builder, but marks the result as a
    reviewable local recovery draft so the normal quality gate can judge the
    actual content instead of automatically blocking it as scaffold.
    """
    return _mark_genesis_local_recovery(
        _generate_genesis_scaffold(body),
        reason=reason,
        error_message=error_message,
    )


def _recover_genesis_from_partial_draft(
    body: GenesisGenerateRequest,
    partial_draft: dict | None,
    *,
    reason: str,
    error_message: str,
) -> dict:
    """Keep any successful LLM Genesis sections and locally fill the missing ones."""
    partial = partial_draft if isinstance(partial_draft, dict) else {}
    recovered = _fill_missing_genesis_sections(body, partial)
    return _mark_genesis_local_recovery(
        recovered,
        reason=reason,
        error_message=error_message,
    )


async def _generate_real_draft_with_scaffold_fallback(
    body: GenesisGenerateRequest,
    settings,
    *,
    run_id: str | None = None,
    progress: Callable | None = None,
) -> dict:
    """Generate Genesis with real LLM, falling back only for invalid JSON output.

    v6.7.7: Accepts optional progress callback for SSE streaming.
    """
    from novel_factory.llm.openai_compatible import OutputValidationError

    def _emit(event_type: str, **kwargs):
        if progress and run_id:
            progress(event_type, {"run_id": run_id, **kwargs})

    try:
        draft = await _generate_real_draft(body, settings, run_id=run_id, progress=progress)

        # Repair/completion phase
        _emit("segment_started", segment="repair", label=GENESIS_SEGMENT_LABELS["repair"])
        result = await _complete_real_genesis_draft(body, settings, draft, run_id=run_id, progress=progress)
        _emit("segment_completed", segment="repair", label=GENESIS_SEGMENT_LABELS["repair"])
        quality_report = evaluate_genesis_draft(
            result,
            title=body.title,
            genre=body.genre,
            premise=body.premise,
            target_chapters=body.target_chapters,
        )
        if _has_instruction_repair_target(quality_report):
            _emit("segment_started", segment="repair", label="正在定向修复章节指令")
            result = await _repair_genesis_instruction_quality(
                body,
                settings,
                result,
                quality_report,
            )
            _emit("segment_completed", segment="repair", label="章节指令定向修复完成")
        return result
    except OutputValidationError as exc:
        logger.warning(
            "Genesis real LLM returned invalid JSON; using scaffold fallback title=%s genre=%s",
            body.title,
            body.genre,
            exc_info=True,
        )
        _emit("segment_started", segment="repair", label="正在使用本地恢复草案")
        result = _build_genesis_recovery_draft(
            body,
            reason="invalid_json",
            error_message=str(exc),
        )
        _emit("segment_completed", segment="repair", label="本地恢复草案生成完成")
        return result

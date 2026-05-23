"""Memory Curator Agent — extracts project patches from reviewed chapters.

Runs after Editor passes review. Analyzes chapter content to extract
structured patches for all project tables (characters, world_settings,
factions, outlines, plot_holes, instructions, story_facts) and creates
memory update batches for user review.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from ..models.state import ChapterStatus, FactoryState
from ..llm.openai_compatible import LLMTimeoutError, OutputValidationError
from ..skills.registry import SkillRegistry
from ..agent_runtime.base import BaseAgent
from ..agent_runtime.skill_hooks import run_agent_skills
from ..agent_runtime.self_check import SelfCheckLoop, SelfCheckResult

logger = logging.getLogger(__name__)

# ── Robust JSON extraction helpers ────────────────────────────────


def _robust_extract_patches(raw_response: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    """Extract patches from LLM response with enhanced resilience.

    Returns (patches, warnings).
    Handles: raw dict, fenced json, unclosed fences, prose wrappers,
    schema-extraneous fields, and first-complete-object extraction.
    """
    patches: list[dict[str, Any]] = []
    warnings: list[str] = []

    # Direct patches list
    if "patches" in raw_response and isinstance(raw_response["patches"], list):
        patches = list(raw_response["patches"])
    elif "facts" in raw_response and isinstance(raw_response["facts"], list):
        patches = list(raw_response["facts"])
        warnings.append("Legacy 'facts' key used instead of 'patches'")
    else:
        # The response itself might be a single patch object
        if isinstance(raw_response, dict) and any(k in raw_response for k in ("target_table", "operation")):
            patches = [raw_response]
        else:
            warnings.append(f"Unrecognized response schema: keys={list(raw_response.keys())}")

    return patches, warnings


def _validate_patches(
    patches: list[dict[str, Any]],
    chapter_content: str = "",
) -> tuple[list[dict[str, Any]], list[str]]:
    """Strictly validate patches. Return (valid_patches, validation_issues).

    Rules:
    1. patches must be a non-empty list.
    2. Each patch must have target_table, operation, confidence, evidence_text.
    3. confidence must be in [0, 1].
    4. evidence_text must be non-empty.
    5. evidence_text should ideally be traceable to chapter_content or state card.
    """
    issues: list[str] = []
    valid: list[dict[str, Any]] = []

    if not patches:
        issues.append("patches is empty")
        return valid, issues

    content_lower = chapter_content.lower() if chapter_content else ""

    for i, patch in enumerate(patches):
        idx = i + 1
        if not isinstance(patch, dict):
            issues.append(f"Patch {idx} is not a dict: {type(patch).__name__}")
            continue

        # Required fields
        target_table = patch.get("target_table")
        operation = patch.get("operation")
        confidence = patch.get("confidence")
        evidence_text = str(patch.get("evidence_text") or "").strip()

        if not target_table:
            issues.append(f"Patch {idx} missing target_table")
            continue
        if not operation:
            issues.append(f"Patch {idx} missing operation")
            continue
        if confidence is None:
            issues.append(f"Patch {idx} missing confidence")
            continue

        try:
            conf_val = float(confidence)
        except (TypeError, ValueError):
            issues.append(f"Patch {idx} confidence is not a number: {confidence}")
            continue

        if not (0.0 <= conf_val <= 1.0):
            issues.append(f"Patch {idx} confidence {conf_val} out of [0,1]")
            continue

        if not evidence_text:
            issues.append(f"Patch {idx} evidence_text is empty")
            continue

        # Evidence traceability (advisory only)
        if content_lower and len(evidence_text) >= 4:
            # Check if a significant substring of evidence appears in content
            evidence_lower = evidence_text.lower()
            found = False
            # Try sliding window of 8 chars
            for start in range(0, max(1, len(evidence_lower) - 7), 4):
                needle = evidence_lower[start : start + 8]
                if needle in content_lower:
                    found = True
                    break
            if not found:
                issues.append(f"Patch {idx} evidence_text not traceable to chapter content (advisory)")

        # Normalize patch: keep known fields, discard extras silently
        normalized = {
            "target_table": str(target_table).strip(),
            "operation": str(operation).strip(),
            "target_name": str(patch.get("target_name") or "").strip(),
            "data": patch.get("data") if isinstance(patch.get("data"), dict) else {},
            "confidence": conf_val,
            "evidence_text": evidence_text,
            "rationale": str(patch.get("rationale") or "").strip(),
        }
        valid.append(normalized)

    return valid, issues


# ── Patch count threshold for "meaningful" extraction ─────────────
_MIN_PATCHES_FOR_TRUSTED = 1

MEMORY_CURATOR_SYSTEM_PROMPT = """你是网文工厂的记忆管理员（Memory Curator），负责从已审校的章节中提取项目资料变更建议。

你的任务：
1. 分析本章内容，提取所有需要更新的项目资料
2. 识别新角色、新设定、新势力、伏笔变化、大纲偏移、指令需求
3. 输出结构化的 patch 列表

提取维度（target_table）：
- characters: 新角色出现或现有角色信息变化（name, role, description, traits）
- world_settings: 新世界观设定或规则变化（title, category, content）
- factions: 新势力或势力关系变化（name, type, description, relationship_with_protagonist）
- outlines: 大纲偏移或新增弧线（chapters_range, title, content, level, sequence）
- plot_holes: 新伏笔埋设、伏笔解决或废弃（code, type, title, description, planted_chapter, planned_resolve_chapter, status）
- instructions: 下一章或后续章节的写作指令（chapter_number, objective, key_events, emotion_tone, word_target）
- story_facts: 事实账本变化（fact_key, fact_type, subject, attribute, value, unit）。明确时间约定/期限/会面必须标为 fact_type=timeline_event 或 time_constraint

输出格式：严格按 JSON 格式输出：
- patches: patch 列表，每项包含：
  - target_table: 目标表（characters/world_settings/factions/outlines/plot_holes/instructions/story_facts）
  - operation: 操作（create/update/resolve/deprecate）
  - target_name: 用于匹配现有记录的名称（如角色名、设定标题、伏笔编码）— 用于判断 create 还是 update
  - data: 该表的字段数据（见上方字段列表）
  - confidence: 置信度（0.0-1.0）
  - evidence_text: 支持证据（原文片段）
  - rationale: 变更理由

注意：
- 只提取本章新发生或变化的内容，不要重复已知信息
- 对于已存在的角色/设定/伏笔，使用 update 操作并只提供变化字段
- 对于新出现的，使用 create 操作并提供完整字段
- 如果本章推进了已有伏笔，优先使用 plot_holes update/resolve，target_name 必须填写现有伏笔 code 或 title，禁止重复创建近义伏笔
- "三天后/明天/今晚/旧工业区见"等时间地点约束必须同时沉淀到 story_facts，fact_type 使用 timeline_event/time_constraint/deadline/appointment
- 伏笔状态：planted（埋设）、resolved（解决）、abandoned（废弃）
- 指令只生成下一章（chapter_number = 当前章节号 + 1）的
- 如果本章没有需要更新的项目资料，返回空列表"""


class MemoryCuratorAgent(BaseAgent):
    """Memory Curator: extracts story facts from reviewed chapters."""

    agent_id = "memory_curator"
    context_char_limit = 9000

    def __init__(
        self,
        repo,
        llm,
        skill_registry: SkillRegistry | None = None,
        fallback_llm=None,
        **kwargs,
    ):
        super().__init__(repo, llm, skill_registry=skill_registry, **kwargs)
        self.skill_registry = skill_registry
        self.fallback_llm = fallback_llm

    def build_context(
        self,
        state: FactoryState,
        *,
        chapter_content_override: str | None = None,
    ) -> str:
        parts = []
        project_id = state.get("project_id", "")
        chapter_number = int(state.get("chapter_number", 0) or 0)

        state_card_data: dict[str, Any] | None = None
        try:
            state_card = self.repo.get_chapter_state(project_id, chapter_number)
            raw_state = (state_card or {}).get("state_data") or {}
            if isinstance(raw_state, str):
                raw_state = json.loads(raw_state)
            if isinstance(raw_state, dict) and raw_state:
                state_card_data = raw_state
                parts.append(
                    "【编辑状态卡】\n"
                    + json.dumps(raw_state, ensure_ascii=False)[:3000]
                )
        except Exception:
            logger.debug("MemoryCurator: state card context unavailable", exc_info=True)

        # Chapter content
        chapter = self._get_chapter_info(state)
        if chapter and chapter.get("content"):
            content = chapter_content_override if chapter_content_override is not None else str(chapter["content"])
            if state_card_data:
                excerpt = content[:2500]
                if len(content) > 3500:
                    excerpt += "\n\n【正文末尾摘录】\n" + content[-1000:]
                parts.append(f"【本章正文摘录】\n{excerpt}")
            else:
                parts.append(f"【本章正文】\n{content[:7000]}")

        # Instruction for context
        instruction = self._get_instruction(state)
        if instruction:
            parts.append(
                f"【写作指令】\n"
                f"目标: {instruction.get('objective', '')}\n"
                f"关键事件: {instruction.get('key_events', '')}"
            )

        # Existing characters
        characters = self.repo.get_characters(project_id)
        if characters:
            char_str = "\n".join(
                f"- {c['name']}({c['role']}): {(c.get('description') or '')[:60]}"
                for c in characters[:10]
            )
            parts.append(f"【现有角色】\n{char_str}")

        # Existing world settings
        ws_list = self.repo.list_world_settings(project_id)
        if ws_list:
            ws_str = "\n".join(
                f"- [{w.get('category', '')}] {w.get('title', '')}: {(w.get('content') or '')[:60]}"
                for w in ws_list[:10]
            )
            parts.append(f"【现有世界观】\n{ws_str}")

        # Existing factions
        factions = self.repo.list_factions(project_id)
        if factions:
            fac_str = "\n".join(
                f"- {f['name']}({f.get('type', '')}): {(f.get('description') or '')[:60]}"
                for f in factions[:8]
            )
            parts.append(f"【现有力势】\n{fac_str}")

        # Existing plot holes
        phs = self.repo.list_plot_holes(project_id)
        if phs:
            ph_str = "\n".join(
                f"- [{p.get('code', '')}] {p.get('title', '')} ({p.get('status', '')}): {(p.get('description') or '')[:60]}"
                for p in phs[:10]
            )
            parts.append(f"【现有伏笔】\n{ph_str}")

        # Existing story facts
        existing_facts = self.repo.list_story_facts(project_id, status="active")
        if existing_facts:
            facts_summary = []
            for f in existing_facts[:15]:
                facts_summary.append(
                    f"- {f['fact_key']}: {f.get('subject', '')}.{f.get('attribute', '')} = {f.get('value_json', '{}')}"
                )
            parts.append(f"【已知事实】\n" + "\n".join(facts_summary))

        return "\n\n".join(parts)

    def _find_existing(self, project_id: str, target_table: str, target_name: str) -> dict | None:
        """Find an existing record by name/key for upsert logic."""
        if not target_name:
            return None
        try:
            if target_table == "characters":
                chars = self.repo.get_characters(project_id)
                return next((c for c in chars if c.get("name") == target_name), None)
            elif target_table == "world_settings":
                ws = self.repo.list_world_settings(project_id)
                return next((w for w in ws if w.get("title") == target_name), None)
            elif target_table == "factions":
                facs = self.repo.list_factions(project_id)
                return next((f for f in facs if f.get("name") == target_name), None)
            elif target_table == "outlines":
                outlines = self.repo.list_outlines(project_id)
                return next((o for o in outlines if o.get("title") == target_name), None)
            elif target_table == "plot_holes":
                phs = self.repo.list_plot_holes(project_id)
                return next((p for p in phs if p.get("code") == target_name or p.get("title") == target_name), None)
            elif target_table == "instructions":
                inst = self.repo.get_instruction_by_chapter(project_id, int(target_name))
                return inst
            elif target_table == "story_facts":
                return self.repo.get_story_fact_by_key(project_id, target_name)
        except Exception:
            return None
        return None

    def _patches_from_chapter_state_card(self, project_id: str, chapter_number: int) -> list[dict[str, Any]]:
        """Build deterministic memory patches from Editor's chapter state card.

        The LLM extractor can legitimately return an empty patch list, but the
        Editor may already have persisted a useful state card. In that case the
        workflow should still surface pending memory updates for human review.
        """
        try:
            state_card = self.repo.get_chapter_state(project_id, chapter_number)
        except Exception:
            logger.exception(
                "MemoryCurator: failed to load chapter state fallback for project=%s chapter=%s",
                project_id,
                chapter_number,
            )
            return []

        state_data = (state_card or {}).get("state_data") or {}
        if not isinstance(state_data, dict):
            return []

        patches: list[dict[str, Any]] = []

        def _fact_key(kind: str, value: Any, index: int) -> str:
            raw = (
                json.dumps(value, ensure_ascii=False, sort_keys=True)
                if isinstance(value, (dict, list))
                else str(value)
            )
            digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]
            return f"chapter_{chapter_number}.{kind}.{index}.{digest}"

        new_facts = state_data.get("new_facts") or state_data.get("新增事实") or []
        for index, fact in enumerate(new_facts, start=1):
            text = str(fact).strip()
            if not text:
                continue
            fact_key = _fact_key("fact", text, index)
            patches.append(
                {
                    "target_table": "story_facts",
                    "operation": "create",
                    "target_name": fact_key,
                    "data": {
                        "fact_key": fact_key,
                        "fact_type": "narrative_event",
                        "subject": f"第{chapter_number}章",
                        "attribute": "新增事实",
                        "value": {"text": text},
                        "source_chapter": chapter_number,
                        "source_agent": "memory_curator",
                    },
                    "confidence": 0.45,
                    "evidence_text": text[:240],
                    "rationale": "状态卡兜底候选：来自 Editor 章节状态卡中的 new_facts，未经过 MemoryCurator LLM 复核，请人工确认后应用。",
                }
            )

        character_status = state_data.get("character_status") or state_data.get("角色状态") or {}
        if isinstance(character_status, dict):
            for index, (name, status) in enumerate(character_status.items(), start=1):
                character_name = str(name).strip()
                status_text = str(status).strip()
                if not character_name or not status_text:
                    continue
                fact_key = _fact_key(
                    "character_status",
                    {"name": character_name, "status": status_text},
                    index,
                )
                patches.append(
                    {
                        "target_table": "story_facts",
                        "operation": "create",
                        "target_name": fact_key,
                        "data": {
                            "fact_key": fact_key,
                            "fact_type": "character_state",
                            "subject": character_name,
                            "attribute": f"第{chapter_number}章状态",
                            "value": {"status": status_text},
                            "source_chapter": chapter_number,
                            "source_agent": "memory_curator",
                        },
                        "confidence": 0.45,
                        "evidence_text": status_text[:240],
                        "rationale": "状态卡兜底候选：来自 Editor 章节状态卡中的 character_status，未经过 MemoryCurator LLM 复核，请人工确认后应用。",
                    }
                )

        suspense_hooks = state_data.get("suspense_hooks") or state_data.get("悬念") or []
        for index, hook in enumerate(suspense_hooks, start=1):
            if isinstance(hook, dict):
                title = str(
                    hook.get("title")
                    or hook.get("name")
                    or f"第{chapter_number}章悬念{index}"
                ).strip()
                description = str(hook.get("description") or hook.get("content") or hook).strip()
                value: Any = hook
            else:
                title = f"第{chapter_number}章悬念{index}"
                description = str(hook).strip()
                value = {"text": description}
            if not description:
                continue
            fact_key = _fact_key("suspense_hook", value, index)
            patches.append(
                {
                    "target_table": "story_facts",
                    "operation": "create",
                    "target_name": fact_key,
                    "data": {
                        "fact_key": fact_key,
                        "fact_type": "suspense_hook",
                        "subject": title,
                        "attribute": "埋设悬念",
                        "value": value,
                        "source_chapter": chapter_number,
                        "source_agent": "memory_curator",
                    },
                    "confidence": 0.45,
                    "evidence_text": description[:240],
                    "rationale": "状态卡兜底候选：来自 Editor 章节状态卡中的 suspense_hooks，未经过 MemoryCurator LLM 复核，请人工确认后应用。",
                }
            )

        return patches

    def _try_segmented_extraction(
        self,
        state: FactoryState,
        base_context: str,
        chapter_content: str,
        exec_events: list[dict] | None,
    ) -> dict[str, Any]:
        """Extract memory patches from long chapters by content chunks."""
        from ..agent_runtime.segmented_generation import chunk_text_by_paragraphs
        from ..workflow.execution_events import (
            EVENT_SEGMENT_STARTED,
            EVENT_SEGMENT_COMPLETED,
            EVENT_SEGMENT_FAILED,
        )

        project_id = state["project_id"]
        chapter_number = state["chapter_number"]

        chunks = list(chunk_text_by_paragraphs(chapter_content, soft_limit=1000))
        total_chunks = len(chunks)

        all_patches: list[dict[str, Any]] = []
        all_warnings: list[str] = []

        for idx, chunk in enumerate(chunks):
            segment_num = idx + 1

            if exec_events is not None:
                exec_events.append({
                    "event_type": EVENT_SEGMENT_STARTED,
                    "message": f"MemoryCurator 开始提取第 {segment_num}/{total_chunks} 段",
                    "status": "info",
                    "payload": {
                        "segment_index": segment_num,
                        "total_segments": total_chunks,
                    },
                })

            segment_context = self.build_context(state, chapter_content_override=chunk)

            messages = [
                {"role": "system", "content": MEMORY_CURATOR_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"项目ID: {project_id}\n章节号: {chapter_number}\n\n"
                        f"{segment_context}\n\n"
                        f"【分段提取】本段为第{segment_num}/{total_chunks}段，"
                        f"请从以上段落中提取项目资料变更建议。"
                    ),
                },
            ]

            try:
                raw = self.llm.invoke_json(messages)
            except LLMTimeoutError as e:
                if exec_events is not None:
                    exec_events.append({
                        "event_type": EVENT_SEGMENT_FAILED,
                        "message": f"MemoryCurator 第 {segment_num}/{total_chunks} 段提取超时",
                        "status": "error",
                        "payload": {
                            "segment_index": segment_num,
                            "error": str(e)[:200],
                        },
                    })
                continue
            except OutputValidationError as e:
                if exec_events is not None:
                    exec_events.append({
                        "event_type": EVENT_SEGMENT_FAILED,
                        "message": f"MemoryCurator 第 {segment_num}/{total_chunks} 段 JSON 解析失败",
                        "status": "error",
                        "payload": {
                            "segment_index": segment_num,
                            "error": str(e)[:200],
                        },
                    })
                continue

            patches, extract_warnings = _robust_extract_patches(raw)
            all_patches.extend(patches)
            all_warnings.extend(extract_warnings)

            if exec_events is not None:
                exec_events.append({
                    "event_type": EVENT_SEGMENT_COMPLETED,
                    "message": f"MemoryCurator 完成第 {segment_num}/{total_chunks} 段 ({len(patches)} patches)",
                    "status": "info",
                    "payload": {
                        "segment_index": segment_num,
                        "patch_count": len(patches),
                    },
                })

        return {
            "output": all_patches,
            "extract_warnings": all_warnings,
            "segmented": True,
            "segment_count": total_chunks,
        }

    def _should_repair_empty_extraction(self, project_id: str, chapter_number: int) -> bool:
        """Return True when an empty real-mode extraction is suspicious enough to retry."""
        try:
            chapter = self.repo.get_chapter(project_id, chapter_number)
            content = str((chapter or {}).get("content") or "")
            if len(content.strip()) >= 1000:
                return True
        except Exception:
            pass

        try:
            state_card = self.repo.get_chapter_state(project_id, chapter_number)
            state_data = (state_card or {}).get("state_data") or {}
            if isinstance(state_data, str):
                state_data = json.loads(state_data)
            if not isinstance(state_data, dict):
                return False
            return any(
                bool(state_data.get(key))
                for key in ("new_facts", "character_status", "suspense_hooks", "新增事实", "角色状态", "悬念")
            )
        except Exception:
            return False

    def _execute(self, state: FactoryState) -> dict[str, Any]:
        project_id = state["project_id"]
        chapter_number = state["chapter_number"]
        run_id = state.get("workflow_run_id")

        lock_result = self.repo.acquire_memory_curator_lock(
            project_id,
            chapter_number,
            run_id=run_id,
        )
        if not lock_result.get("acquired"):
            active_lock = lock_result.get("lock") or {}
            active_run_id = active_lock.get("run_id")
            message = (
                f"第{chapter_number}章记忆正在提取，不能重复启动。"
                + (f" 当前运行: {active_run_id}" if active_run_id else "")
            )
            return {
                "memory_curator_processed": False,
                "memory_curator_locked": True,
                "memory_curator_warning": message,
                "memory_curator_active_run_id": active_run_id,
                "memory_items_count": 0,
                "extraction_success": False,
                "chapter_status": state.get("chapter_status"),
                "requires_human": False,
                "_exec_events": [
                    {
                        "event_type": "memory_curator_locked",
                        "message": message,
                        "status": "warning",
                        "payload": {"active_run_id": active_run_id},
                    }
                ],
            }

        try:
            return self._execute_locked(state)
        finally:
            try:
                self.repo.release_memory_curator_lock(
                    project_id,
                    chapter_number,
                    run_id=run_id,
                )
            except Exception:
                logger.warning(
                    "MemoryCurator: failed to release lock for project=%s chapter=%s run=%s",
                    project_id,
                    chapter_number,
                    run_id,
                    exc_info=True,
                )

    def _execute_locked(self, state: FactoryState) -> dict[str, Any]:
        project_id = state["project_id"]
        chapter_number = state["chapter_number"]
        exec_events: list[dict] = []

        context = self._build_v6_context(state)

        # v6.6.17: Self-check loop for patch extraction quality with fallback support
        loop = SelfCheckLoop(agent_id=self.agent_id, max_repair_attempts=1)

        def _generate_wrap() -> dict[str, Any]:
            chapter = self._get_chapter_info(state)
            chapter_content = str((chapter or {}).get("content") or "")
            if state.get("llm_mode") == "real" and len(chapter_content) > 1000:
                return self._try_segmented_extraction(state, context, chapter_content, exec_events)
            messages = [
                {"role": "system", "content": MEMORY_CURATOR_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"项目ID: {project_id}\n章节号: {chapter_number}\n\n{context}\n\n请提取本章的项目资料变更建议。",
                },
            ]
            try:
                raw = self.llm.invoke_json(messages)
                exec_events.append({
                    "event_type": "llm_extraction_success",
                    "message": "记忆提取主模型返回可解析结果",
                    "payload": {
                        "primary_profile": getattr(getattr(self.llm, "config", None), "model", "unknown"),
                    },
                })
            except LLMTimeoutError as e:
                primary_profile = getattr(getattr(self.llm, "config", None), "model", "unknown")
                primary_timeout = getattr(getattr(self.llm, "config", None), "request_timeout_seconds", "unknown")
                exec_events.append({
                    "event_type": "llm_extraction_timeout",
                    "message": "记忆提取主模型超时",
                    "payload": {
                        "primary_profile": primary_profile,
                        "primary_timeout_seconds": primary_timeout,
                    },
                })
                return {"output": [], "primary_timeout": True, "warning": str(e)}
            except OutputValidationError as e:
                return {"output": [], "json_error": str(e), "warning": str(e)}
            # v6.6.7: Use robust extraction with validation
            patches, extract_warnings = _robust_extract_patches(raw)
            return {"output": patches, "extract_warnings": extract_warnings}

        def _self_check_wrap(data: dict[str, Any]) -> SelfCheckResult:
            patches = data.get("output", [])
            issues: list[dict[str, Any]] = []
            if data.get("primary_timeout"):
                issues.append({
                    "type": "primary_timeout",
                    "message": "主模型 LLM 提取超时，将尝试 fallback 或状态卡兜底",
                })
            if (
                state.get("llm_mode") == "real"
                and not patches
                and not data.get("fallback_source")
                and not data.get("primary_timeout")
                and self._should_repair_empty_extraction(project_id, chapter_number)
            ):
                issues.append({
                    "type": "empty_extraction",
                    "message": "真实 LLM 对长正文/状态卡章节返回空记忆提取结果",
                })
            if data.get("json_error"):
                issues.append({
                    "type": "json_parse",
                    "message": f"MemoryCurator JSON 解析失败: {str(data.get('json_error'))[:160]}",
                })
            # v6.6.7: Enhanced validation
            chapter = self.repo.get_chapter(project_id, chapter_number)
            chapter_content = str((chapter or {}).get("content") or "")
            valid_patches, validation_issues = _validate_patches(patches, chapter_content)
            data["validated_patches"] = valid_patches
            for issue in validation_issues:
                # Only treat structural issues as blocking; traceability warnings are advisory
                if "not traceable" in issue:
                    continue
                issues.append({"type": "patch_validation", "message": issue})
            # v6.6.7: Skip confidence checks for fallback patches (already known low-confidence)
            if not data.get("fallback_source"):
                for i, patch in enumerate(valid_patches):
                    if patch.get("confidence", 0) < 0.45:
                        issues.append({"type": "patch_confidence", "message": f"Patch {i+1} confidence {patch['confidence']} below threshold 0.45"})
            return SelfCheckResult(
                passed=len(issues) == 0,
                issues=issues,
                repair_needed=len(issues) > 0,
                repair_suggestion="尝试 fallback provider 或状态卡兜底",
            )

        def _repair_wrap(data: dict[str, Any], check: SelfCheckResult) -> dict[str, Any] | None:
            primary_timeout = data.get("primary_timeout")
            json_parse_error = any(issue.get("type") == "json_parse" for issue in check.issues)
            empty_extraction = any(issue.get("type") == "empty_extraction" for issue in check.issues)

            messages = [
                {"role": "system", "content": MEMORY_CURATOR_SYSTEM_PROMPT + "\n\n注意：每个 patch 必须包含 target_table, operation, target_name, data, confidence 字段。"},
                {
                    "role": "user",
                    "content": f"项目ID: {project_id}\n章节号: {chapter_number}\n\n{context}\n\n请重新提取本章的项目资料变更建议，确保字段完整。",
                },
            ]

            # v6.6.17: Primary timeout -> try fallback provider once
            if primary_timeout and self.fallback_llm:
                fallback_profile = getattr(
                    self.fallback_llm,
                    "profile_name",
                    getattr(getattr(self.fallback_llm, "config", None), "model", "unknown"),
                )
                try:
                    raw = self.fallback_llm.invoke_json(messages)
                    patches, extract_warnings = _robust_extract_patches(raw)
                    chapter = self.repo.get_chapter(project_id, chapter_number)
                    chapter_content = str((chapter or {}).get("content") or "")
                    valid_patches, validation_issues = _validate_patches(patches, chapter_content)
                    if valid_patches:
                        return {
                            "output": valid_patches,
                            "fallback_source": "fallback_model_after_primary_timeout",
                            "fallback_model_profile": fallback_profile,
                            "extract_warnings": extract_warnings,
                            "partial_success": True,
                        }
                    exec_events.append({
                        "event_type": "fallback_model_failed",
                        "message": "备用模型 fallback 未生成有效记忆候选",
                        "payload": {
                            "fallback_model_profile": fallback_profile,
                            "patch_count": len(patches),
                            "validation_issues": validation_issues[:5],
                        },
                    })
                except Exception as e:
                    exec_events.append({
                        "event_type": "fallback_model_failed",
                        "message": f"备用模型 fallback 失败: {str(e)[:200]}",
                        "payload": {"fallback_model_profile": fallback_profile, "error": str(e)[:500]},
                    })

            # Original repair path (for json_parse / empty_extraction without timeout)
            if not primary_timeout:
                repair_instruction = (
                    "上一次返回了空 patches，但本章有较长正文或状态卡。请重新逐段提取本章新增/变化的角色、设定、势力、伏笔、下一章指令和事实账本；除非正文确实没有任何可沉淀信息，否则不要返回空 patches。"
                    if empty_extraction
                    else "请重新提取本章的项目资料变更建议，确保字段完整。"
                )
                if json_parse_error:
                    repair_instruction = (
                        "上一次输出不是合法 JSON。请重新提取本章记忆，并严格返回一个 JSON 对象：{\"patches\": [...]}。"
                        "不要使用 Markdown 代码块，不要输出解释文字。"
                        "evidence_text 只能写 30 字以内摘要，不要复制带单双引号的对白原文，不要在 JSON 字符串里换行。"
                        "所有字符串必须正确转义。"
                    )
                messages = [
                    {"role": "system", "content": MEMORY_CURATOR_SYSTEM_PROMPT + "\n\n注意：每个 patch 必须包含 target_table, operation, target_name, data, confidence 字段。"},
                    {
                        "role": "user",
                        "content": f"项目ID: {project_id}\n章节号: {chapter_number}\n\n{context}\n\n{repair_instruction}",
                    },
                ]
                try:
                    raw = self.llm.invoke_json(messages)
                    patches, extract_warnings = _robust_extract_patches(raw)
                    return {"output": patches, "extract_warnings": extract_warnings}
                except Exception:
                    pass

            # Final fallback: chapter state card
            fallback_patches = self._patches_from_chapter_state_card(project_id, chapter_number)
            if fallback_patches:
                # v6.6.17: timeout uses extraction_failure label for backward compatibility
                return {
                    "output": fallback_patches,
                    "fallback_source": (
                        "chapter_state_after_llm_extraction_failure"
                        if (primary_timeout or json_parse_error)
                        else "chapter_state_after_llm_repair_failure"
                    ),
                    "warning": data.get("warning"),
                    "partial_success": True,
                }

            # Degraded noop: no patches, no state card
            exec_events.append({
                "event_type": "degraded_noop",
                "message": "记忆整理降级为空操作，未生成可信记忆批次",
                "payload": {"memory_items_count": 0},
            })
            return {
                "output": [],
                "degraded": True,
                "fallback_source": "none",
                "warning": data.get("warning", "LLM 提取失败且状态卡为空"),
            }

        loop_result = loop.run(_generate_wrap, _self_check_wrap, _repair_wrap)
        # v6.6.7: Prefer validated patches if available
        patches = loop_result.get("validated_patches") or loop_result.get("output", [])
        trace = loop_result.get("_trace", {})
        autonomy = loop_result.get("_autonomy", {})

        # v6.6.17: Handle degraded noop (fallback_source="none")
        if loop_result.get("degraded") and loop_result.get("fallback_source") == "none":
            return {
                "memory_curator_processed": True,
                "memory_items_count": 0,
                "extraction_success": False,
                "fallback_created": False,
                "memory_curator_degraded": True,
                "partial_success": False,
                "fallback_source": "none",
                "memory_curator_warning": "记忆整理降级为空操作，未生成可信记忆批次",
                "_trace": trace,
                "_autonomy": autonomy,
                "_exec_events": exec_events,
            }

        if loop_result.get("degraded"):
            return {
                "memory_curator_processed": True,
                "memory_curator_degraded": True,
                "memory_curator_warning": loop_result.get("warning", ""),
                "extraction_success": False,
                "fallback_created": False,
                "_trace": trace,
                "_autonomy": autonomy,
            }

        if state.get("llm_mode") == "real" and autonomy.get("decision") in {"ask_human", "reroute", "refuse"}:
            reason = autonomy.get("reason") or "MemoryCurator 自检未通过"
            return {
                "memory_curator_processed": True,
                "error": f"MemoryCurator 自检未通过: {reason}",
                "chapter_status": state.get("chapter_status"),
                "requires_human": True,
                "extraction_success": False,
                "_trace": trace,
                "_autonomy": autonomy,
            }

        fallback_source = loop_result.get("fallback_source")
        fallback_model_profile = loop_result.get("fallback_model_profile")
        warning = loop_result.get("warning")

        if not patches:
            fallback_patches = self._patches_from_chapter_state_card(project_id, chapter_number)
            if fallback_patches:
                patches = fallback_patches
                fallback_source = "chapter_state"
                exec_events.append({
                    "event_type": "fallback_memory_success",
                    "message": f"记忆提取为空，已使用章节状态卡兜底生成 {len(patches)} 条候选",
                    "payload": {"fallback_type": "chapter_state", "patch_count": len(patches)},
                })
                logger.info(
                    "MemoryCurator: generated %d fallback patches from chapter_state for project=%s chapter=%s",
                    len(patches),
                    project_id,
                    chapter_number,
                )

        run_agent_skills(
            repo=self.repo,
            skill_registry=self.skill_registry,
            project_id=project_id,
            chapter_number=chapter_number,
            agent="memory_curator",
            stage="after_extract",
            payload={"patches": patches},
            project_overrides=self._get_project_skill_overrides(project_id),
            skill_type_hint="validator",
        )

        if not patches:
            logger.info(
                "MemoryCurator: no patches extracted for project=%s chapter=%s",
                project_id,
                chapter_number,
            )
            exec_events.append({
                "event_type": "degraded_noop",
                "message": "记忆整理降级为空操作，未生成可信记忆批次",
                "payload": {"memory_items_count": 0},
            })
            return {
                "memory_curator_processed": True,
                "memory_items_count": 0,
                "extraction_success": False,
                "fallback_created": False,
                "memory_curator_degraded": True,
                "partial_success": False,
                "fallback_source": "none",
                "memory_curator_warning": "记忆整理降级为空操作，未生成可信记忆批次",
                "_trace": trace,
                "_autonomy": autonomy,
                "_exec_events": exec_events,
            }

        if fallback_source:
            try:
                from ..api.routes._memory_curator_gate import ignore_duplicate_state_card_fallback_batches

                ignore_duplicate_state_card_fallback_batches(
                    self.repo,
                    project_id,
                    chapter_number,
                    keep_latest=False,
                )
            except Exception:
                logger.debug("MemoryCurator fallback cleanup failed", exc_info=True)

        # Create memory update batch
        batch = self.repo.create_memory_batch(
            project_id,
            chapter_number=chapter_number,
            run_id=state.get("workflow_run_id"),
            summary=(
                f"第{chapter_number}章记忆提取 - 状态卡兜底 ({len(patches)}项)"
                if fallback_source and fallback_source != "fallback_model_after_primary_timeout"
                else (
                    f"第{chapter_number}章记忆提取 - fallback模型 ({len(patches)}项)"
                    if fallback_source == "fallback_model_after_primary_timeout"
                    else f"第{chapter_number}章记忆提取 ({len(patches)}项)"
                )
            ),
        )

        # Create memory update items for each patch
        items_created = 0
        for patch in patches:
            target_table = patch.get("target_table", "story_facts")
            operation = patch.get("operation", "create")
            target_name = patch.get("target_name", "")
            data = patch.get("data", {})

            # For story_facts, also accept the old format (fact_key as target_name)
            if target_table == "story_facts" and not target_name:
                target_name = data.get("fact_key", "")

            # Find existing record for upsert
            existing = self._find_existing(project_id, target_table, target_name)

            after_data = dict(data)
            if target_table == "story_facts":
                after_data.setdefault("fact_key", target_name)
                after_data.setdefault("source_chapter", chapter_number)
                after_data.setdefault("source_agent", "memory_curator")

            before_json = None
            if existing and operation in ("update", "resolve", "deprecate"):
                before_json = json.dumps(
                    {k: v for k, v in existing.items() if k not in ("id", "created_at", "updated_at")},
                    ensure_ascii=False,
                )
                operation = "update"

            self.repo.create_memory_item(
                batch_id=batch["id"],
                project_id=project_id,
                target_table=target_table,
                operation=operation,
                target_id=existing["id"] if existing else None,
                before_json=before_json,
                after_json=json.dumps(after_data, ensure_ascii=False),
                confidence=patch.get("confidence", 0.8),
                evidence_text=patch.get("evidence_text", ""),
                rationale=patch.get("rationale", f"第{chapter_number}章提取"),
            )
            items_created += 1

        logger.info(
            "MemoryCurator: created batch %s with %d items for project=%s chapter=%s",
            batch["id"],
            items_created,
            project_id,
            chapter_number,
        )

        if not fallback_source:
            try:
                from ..api.routes._memory_curator_gate import ignore_state_card_fallback_batches_for_chapter

                ignore_state_card_fallback_batches_for_chapter(
                    self.repo,
                    project_id,
                    chapter_number,
                )
            except Exception:
                logger.debug("MemoryCurator trusted extraction cleanup failed", exc_info=True)

        exec_events.append({
            "event_type": "artifact_saved",
            "message": f"创建记忆批次：{items_created} 条候选" + (
                "（备用模型）" if fallback_source == "fallback_model_after_primary_timeout"
                else ("（状态卡兜底）" if fallback_source else "")
            ),
            "payload": {"batch_id": batch["id"], "items_count": items_created, "fallback_source": fallback_source},
        })

        # v6.6.17: Classify result into categories
        if fallback_source == "fallback_model_after_primary_timeout":
            result_category = "fallback_candidate"
        elif fallback_source:
            result_category = "fallback_candidate"
        else:
            result_category = "trusted_extraction"

        if fallback_source == "fallback_model_after_primary_timeout":
            exec_events.append({
                "event_type": "fallback_model_success",
                "message": "记忆整理降级完成（备用模型）",
                "payload": {
                    "fallback_type": fallback_source,
                    "fallback_model_profile": fallback_model_profile,
                    "patch_count": items_created,
                },
            })
        elif fallback_source:
            exec_events.append({
                "event_type": "fallback_memory_success",
                "message": "记忆整理降级完成（状态卡兜底）",
                "payload": {
                    "fallback_type": fallback_source,
                    "patch_count": items_created,
                    "warning": warning,
                },
            })

        return {
            "memory_curator_processed": True,
            "memory_batch_id": batch["id"],
            "memory_items_count": items_created,
            "extraction_success": fallback_source is None,
            "fallback_created": fallback_source is not None,
            "partial_success": fallback_source is not None,
            "fallback_source": fallback_source,
            "result_category": result_category,
            **({"memory_curator_fallback": fallback_source} if fallback_source else {}),
            **({"fallback_model_profile": fallback_model_profile} if fallback_model_profile else {}),
            **({"memory_curator_warning": warning} if warning else {}),
            "_trace": trace,
            "_autonomy": autonomy,
            "_exec_events": exec_events,
        }

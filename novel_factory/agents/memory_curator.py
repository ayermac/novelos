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
from ..llm.provider import is_configured_live_provider
from ..skills.registry import SkillRegistry
from .base import BaseAgent
from .skill_hooks import run_agent_skills
from .self_check import SelfCheckLoop, SelfCheckResult

logger = logging.getLogger(__name__)

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
- story_facts: 事实账本变化（fact_key, fact_type, subject, attribute, value, unit）

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
- 伏笔状态：planted（埋设）、resolved（解决）、abandoned（废弃）
- 指令只生成下一章（chapter_number = 当前章节号 + 1）的
- 如果本章没有需要更新的项目资料，返回空列表"""


class MemoryCuratorAgent(BaseAgent):
    """Memory Curator: extracts story facts from reviewed chapters."""

    agent_id = "memory_curator"

    def __init__(self, repo, llm, skill_registry: SkillRegistry | None = None, **kwargs):
        super().__init__(repo, llm, skill_registry=skill_registry, **kwargs)
        self.skill_registry = skill_registry

    def build_context(self, state: FactoryState) -> str:
        parts = []
        project_id = state.get("project_id", "")

        # Chapter content
        chapter = self._get_chapter_info(state)
        if chapter and chapter.get("content"):
            parts.append(f"【本章正文】\n{chapter['content'][:10000]}")

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

        for index, fact in enumerate(state_data.get("new_facts") or [], start=1):
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
                    "confidence": 0.85,
                    "evidence_text": text[:240],
                    "rationale": "LLM 记忆提取为空，使用 Editor 章节状态卡中的 new_facts 兜底生成。",
                }
            )

        character_status = state_data.get("character_status") or {}
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
                        "confidence": 0.82,
                        "evidence_text": status_text[:240],
                        "rationale": "LLM 记忆提取为空，使用 Editor 章节状态卡中的 character_status 兜底生成。",
                    }
                )

        for index, hook in enumerate(state_data.get("suspense_hooks") or [], start=1):
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
                    "confidence": 0.8,
                    "evidence_text": description[:240],
                    "rationale": "LLM 记忆提取为空，使用 Editor 章节状态卡中的 suspense_hooks 兜底生成。",
                }
            )

        return patches

    def _execute(self, state: FactoryState) -> dict[str, Any]:
        project_id = state["project_id"]
        chapter_number = state["chapter_number"]

        context = self._build_v6_context(state)

        # v6.0: Self-check loop for patch extraction quality
        loop = SelfCheckLoop(agent_id=self.agent_id, max_repair_attempts=1)

        def _generate_wrap() -> dict[str, Any]:
            messages = [
                {"role": "system", "content": MEMORY_CURATOR_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"项目ID: {project_id}\n章节号: {chapter_number}\n\n{context}\n\n请提取本章的项目资料变更建议。",
                },
            ]
            try:
                invoke_kwargs = {"max_tokens": 700} if is_configured_live_provider(self.llm) else {}
                raw = self.llm.invoke_json(messages, **invoke_kwargs)
            except (LLMTimeoutError, OutputValidationError) as e:
                logger.warning("MemoryCurator: degraded to no-op after LLM extraction failure: %s", e)
                return {"output": [], "degraded": True, "warning": str(e)}
            patches = raw.get("patches", raw.get("facts", []))
            return {"output": patches}

        def _self_check_wrap(data: dict[str, Any]) -> SelfCheckResult:
            patches = data.get("output", [])
            issues: list[dict[str, Any]] = []
            for i, patch in enumerate(patches):
                if not patch.get("target_table"):
                    issues.append({"type": "patch_structure", "message": f"Patch {i+1} missing target_table"})
                if not patch.get("operation"):
                    issues.append({"type": "patch_structure", "message": f"Patch {i+1} missing operation"})
                if patch.get("confidence", 0) < 0.3:
                    issues.append({"type": "patch_confidence", "message": f"Patch {i+1} confidence too low"})
            return SelfCheckResult(
                passed=len(issues) == 0,
                issues=issues,
                repair_needed=len(issues) > 0,
                repair_suggestion="要求 LLM 返回完整 patch 结构",
            )

        def _repair_wrap(data: dict[str, Any], check: SelfCheckResult) -> dict[str, Any] | None:
            messages = [
                {"role": "system", "content": MEMORY_CURATOR_SYSTEM_PROMPT + "\n\n注意：每个 patch 必须包含 target_table, operation, target_name, data, confidence 字段。"},
                {
                    "role": "user",
                    "content": f"项目ID: {project_id}\n章节号: {chapter_number}\n\n{context}\n\n请重新提取本章的项目资料变更建议，确保字段完整。",
                },
            ]
            try:
                invoke_kwargs = {"max_tokens": 700} if is_configured_live_provider(self.llm) else {}
                raw = self.llm.invoke_json(messages, **invoke_kwargs)
                patches = raw.get("patches", raw.get("facts", []))
                return {"output": patches}
            except Exception:
                return None

        loop_result = loop.run(_generate_wrap, _self_check_wrap, _repair_wrap)
        patches = loop_result.get("output", [])
        trace = loop_result.get("_trace", {})
        autonomy = loop_result.get("_autonomy", {})
        if state.get("llm_mode") == "real" and autonomy.get("decision") in {"ask_human", "reroute", "refuse"}:
            reason = autonomy.get("reason") or "MemoryCurator 自检未通过"
            return {
                "error": f"MemoryCurator 自检未通过: {reason}",
                "chapter_status": state.get("chapter_status"),
                "requires_human": True,
                "_trace": trace,
                "_autonomy": autonomy,
            }

        if loop_result.get("degraded"):
            return {
                "memory_curator_processed": True,
                "memory_curator_degraded": True,
                "memory_curator_warning": loop_result.get("warning", ""),
                "_trace": trace,
                "_autonomy": autonomy,
            }

        fallback_source = None
        if not patches:
            fallback_patches = self._patches_from_chapter_state_card(project_id, chapter_number)
            if fallback_patches:
                patches = fallback_patches
                fallback_source = "chapter_state"
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
            return {
                "memory_curator_processed": True,
                "memory_items_count": 0,
                "_trace": trace,
                "_autonomy": autonomy,
            }

        # Create memory update batch
        batch = self.repo.create_memory_batch(
            project_id,
            chapter_number=chapter_number,
            run_id=state.get("workflow_run_id"),
            summary=f"第{chapter_number}章记忆提取 ({len(patches)}项)",
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

        return {
            "memory_curator_processed": True,
            "memory_batch_id": batch["id"],
            "memory_items_count": items_created,
            **({"memory_curator_fallback": fallback_source} if fallback_source else {}),
            "_trace": trace,
            "_autonomy": autonomy,
        }

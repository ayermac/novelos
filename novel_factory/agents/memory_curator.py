"""Memory Curator Agent — extracts project patches from reviewed chapters.

Runs after Editor passes review. Analyzes chapter content to extract
structured patches for all project tables (characters, world_settings,
factions, outlines, plot_holes, instructions, story_facts) and creates
memory update batches for user review.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from ..models.state import ChapterStatus, FactoryState
from .base import BaseAgent

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

    def _execute(self, state: FactoryState) -> dict[str, Any]:
        project_id = state["project_id"]
        chapter_number = state["chapter_number"]

        context = self.build_context(state)

        messages = [
            {"role": "system", "content": MEMORY_CURATOR_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"项目ID: {project_id}\n章节号: {chapter_number}\n\n{context}\n\n请提取本章的项目资料变更建议。",
            },
        ]

        raw = self.llm.invoke_json(messages)
        patches = raw.get("patches", raw.get("facts", []))

        if not patches:
            logger.info(
                "MemoryCurator: no patches extracted for project=%s chapter=%s",
                project_id,
                chapter_number,
            )
            return {"memory_curator_processed": True}

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
        }

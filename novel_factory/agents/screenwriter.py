"""Screenwriter Agent — decomposes instructions into scene beats."""

from __future__ import annotations

import json
import logging
from typing import Any

from ..models.schemas import ScreenwriterOutput
from ..models.state import ChapterStatus, FactoryState
from .base import BaseAgent

logger = logging.getLogger(__name__)

SCREENWRITER_SYSTEM_PROMPT = """你是网文工厂的编剧（Screenwriter），负责将总编的章节指令拆解成可执行的场景 beat。

输出格式：严格按 JSON 格式输出，包含 scene_beats 数组，每个 beat 包含：
- sequence: 序号（从1开始）
- scene_goal: 场景目标
- conflict: 冲突
- turn: 转折
- plot_refs: 涉及的伏笔代码列表
- hook: 场景钩子

核心原则：
1. 每个场景必须有推进作用
2. 标记伏笔埋设或兑现位置
3. 控制单章节奏，确保章末钩子

禁止：
- 改写世界观和角色设定
- 写最终正文
- 决定审核结果"""


class ScreenwriterAgent(BaseAgent):
    """Screenwriter: decomposes chapter instructions into scene beats."""

    agent_id = "screenwriter"

    def build_context(self, state: FactoryState) -> str:
        parts = []

        # Writing instruction
        instruction = self._get_instruction(state)
        if instruction:
            parts.append(f"【写作指令】\n目标: {instruction.get('objective', '')}\n"
                         f"关键事件: {instruction.get('key_events', '')}\n"
                         f"章末钩子: {instruction.get('ending_hook', '')}\n"
                         f"埋设伏笔: {instruction.get('plots_to_plant', '[]')}\n"
                         f"兑现伏笔: {instruction.get('plots_to_resolve', '[]')}")

        # Previous state card
        prev_state = self._get_prev_state_card(state)
        if prev_state:
            parts.append(f"【上一章状态卡】\n{json.dumps(prev_state.get('state_data', {}), ensure_ascii=False, indent=2)}")

        # Characters
        characters = self.repo.get_characters(state["project_id"])
        if characters:
            char_str = "\n".join(f"- {c['name']}({c['role']}): {c.get('description', '')}" for c in characters)
            parts.append(f"【角色设定】\n{char_str}")

        return "\n\n".join(parts)

    def _execute(self, state: FactoryState) -> dict[str, Any]:
        project_id = state["project_id"]
        chapter_number = state["chapter_number"]

        context = self.build_context(state)

        messages = [
            {"role": "system", "content": SCREENWRITER_SYSTEM_PROMPT},
            {"role": "user", "content": f"项目ID: {project_id}\n章节号: {chapter_number}\n\n{context}\n\n请将以上指令拆解为场景 beat。"},
        ]

        raw = self.llm.invoke_json(messages, schema=ScreenwriterOutput)
        output = ScreenwriterOutput(**raw)

        self.validate_output(output.model_dump())

        # Advance status FIRST to lock the transition; abort if stale
        ok = self.repo.update_chapter_status(
            project_id, chapter_number, ChapterStatus.SCRIPTED.value,
            expected_status=ChapterStatus.PLANNED.value,
        )
        if not ok:
            logger.error("Screenwriter: status advance planned→scripted failed (stale state)")
            return {"error": "Screenwriter: stale state, status advance failed", "chapter_status": state.get("chapter_status")}

        # Save scene beats (only after status advance succeeds)
        try:
            beats_data = [b.model_dump() for b in output.scene_beats]
            self.repo.save_scene_beats(project_id, chapter_number, beats_data)

            # Save artifact
            self.repo.save_artifact(
                project_id, chapter_number, "screenwriter", "scene_plan",
                content_json=output.model_dump(),
            )
        except Exception as e:
            self._compensate_status(
                project_id, chapter_number,
                ChapterStatus.SCRIPTED.value, ChapterStatus.PLANNED.value,
            )
            return {"error": f"Screenwriter: write failed: {e}", "chapter_status": ChapterStatus.PLANNED.value}

        return {
            "chapter_status": ChapterStatus.SCRIPTED.value,
            "current_stage": "scripted",
        }

    def validate_output(self, output: dict) -> None:
        ScreenwriterOutput(**output)

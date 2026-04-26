"""Planner Agent — creates chapter writing instructions."""

from __future__ import annotations

import json
import logging
from typing import Any

from ..models.schemas import PlannerOutput
from ..models.state import ChapterStatus, FactoryState
from .base import BaseAgent

logger = logging.getLogger(__name__)

PLANNER_SYSTEM_PROMPT = """你是网文工厂的总编（Planner），负责章节规划。
你的职责是：根据项目大纲、上一章状态卡和伏笔情况，生成下一章的写作指令。

输出格式：严格按 JSON 格式输出 chapter_brief 对象，包含以下字段：
- objective: 本章目标（必须以状态卡数值开头）
- required_events: 2-4个关键事件列表
- plots_to_plant: 要埋的伏笔代码列表
- plots_to_resolve: 要兑现的伏笔代码列表
- ending_hook: 章末钩子
- constraints: 约束条件列表

核心原则：
1. objective 必须以上一章状态卡开头
2. 反派行为必须逻辑化
3. 每个伏笔必须有计划兑现
4. 禁止抽象描述（如"主角变得更强"）

禁止：
- 写正文
- 跳过审核直接发布
- 唤醒其他 Agent"""


class PlannerAgent(BaseAgent):
    """Planner: creates writing instructions for a chapter."""

    agent_id = "planner"

    def build_context(self, state: FactoryState) -> str:
        parts = []
        
        # R3: Review notes from human review sessions (v3.2)
        project_id = state["project_id"]
        chapter_number = state["chapter_number"]
        review_notes = self.repo.get_chapter_review_notes(project_id, chapter_number)
        if review_notes:
            latest_note = review_notes[0]
            parts.append(f"【人工审核意见】\n{latest_note['notes']}")
        
        # Previous state card
        prev_state = self._get_prev_state_card(state)
        if prev_state:
            parts.append(f"【上一章状态卡】\n{json.dumps(prev_state.get('state_data', {}), ensure_ascii=False, indent=2)}")
        else:
            parts.append("【初始状态】第一章，无上一章状态卡")

        # Characters
        characters = self.repo.get_characters(state["project_id"])
        if characters:
            char_str = "\n".join(f"- {c['name']}({c['role']}): {c.get('description', '')}" for c in characters)
            parts.append(f"【角色设定】\n{char_str}")

        # Pending plots
        plots = self.repo.get_pending_plots(state["project_id"])
        if plots:
            plot_str = "\n".join(
                f"- [{p['code']}] {p['title']} (埋设:第{p.get('planted_chapter','?')}章, 计划兑现:第{p.get('planned_resolve_chapter','?')}章)"
                for p in plots
            )
            parts.append(f"【待处理伏笔】\n{plot_str}")

        # Pending messages
        messages = self.repo.get_pending_messages(state["project_id"], "planner")
        if messages:
            msg_str = "\n".join(f"- [{m['from_agent']}] {m['type']}: {m['content'][:200]}" for m in messages[:5])
            parts.append(f"【待处理异议】\n{msg_str}")

        # v4.0: Style Bible injection
        style_ctx = self._get_style_bible_context(project_id, "planner")
        if style_ctx:
            parts.append(style_ctx)

        return "\n\n".join(parts)

    def _execute(self, state: FactoryState) -> dict[str, Any]:
        project_id = state["project_id"]
        chapter_number = state["chapter_number"]

        context = self.build_context(state)

        messages = [
            {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
            {"role": "user", "content": f"项目ID: {project_id}\n章节号: {chapter_number}\n\n{context}\n\n请生成第{chapter_number}章的写作指令。"},
        ]

        raw = self.llm.invoke_json(messages, schema=PlannerOutput)
        output = PlannerOutput(**raw)

        self.validate_output(output.model_dump())

        # Save instruction to DB
        brief = output.chapter_brief
        self.repo.create_instruction(
            project_id=project_id,
            chapter_number=chapter_number,
            objective=brief.objective,
            key_events=json.dumps(brief.required_events, ensure_ascii=False),
            plots_to_plant=json.dumps(brief.plots_to_plant, ensure_ascii=False),
            plots_to_resolve=json.dumps(brief.plots_to_resolve, ensure_ascii=False),
            ending_hook=brief.ending_hook,
        )

        # Update chapter status
        self.repo.update_chapter_status(
            project_id, chapter_number, ChapterStatus.PLANNED.value,
            expected_status=ChapterStatus.PLANNED.value,
        )

        # Save artifact
        self.repo.save_artifact(
            project_id, chapter_number, "planner", "chapter_brief",
            content_json=output.model_dump(),
        )

        return {
            "chapter_status": ChapterStatus.PLANNED.value,
            "current_stage": "planned",
        }

    def validate_output(self, output: dict) -> None:
        """Validate PlannerOutput schema."""
        PlannerOutput(**output)  # Will raise ValidationError if invalid

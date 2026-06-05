"""Planner Agent — creates chapter writing instructions."""

from __future__ import annotations

import json
import logging
from typing import Any

from ..models.schemas import PlannerOutput
from ..models.state import ChapterStatus, FactoryState
from ..skills.registry import SkillRegistry
from ..validators.chapter_checker import derive_word_target
from ..agent_runtime.base import BaseAgent
from ..agent_runtime.revision_context import revision_feedback_block
from ..agent_runtime.skill_hooks import run_agent_skills
from ..agent_runtime.context_builder import AgentContextBuilder, format_context_bundle_for_prompt
from ..quality.chapter_inheritance import validate_chapter_inheritance
from ..quality.chapter_seam import (
    build_chapter_seam_context,
    build_planner_inheritance_context,
    enforce_planner_inheritance,
)

logger = logging.getLogger(__name__)

PLANNER_SYSTEM_PROMPT = """你是网文工厂的总编（Planner），负责章节规划。
你的职责是：根据项目大纲、上一章状态卡和伏笔情况，生成下一章的写作指令。

输出格式：严格按 JSON 格式输出 chapter_brief 对象，包含以下字段：

Tier 1 (必填):
- chapter_goal: 本章目标（必须以状态卡数值开头）
- reader_payoff: 读者回报
- protagonist_agency: 主角能动性
- forbidden_moves: 禁止动作列表

Tier 2 (可选，缺失将用默认值填充):
- pressure_budget: 压力预算
- payoff_budget: 回报预算
- upgrade_or_skill_use: 升级或技能使用
- character_arc_moves: 角色弧线推进
- mystery_actions: 悬疑动作
- conflict_actions: 冲突动作
- ledger_debts_to_pay: 需要偿还的台账债务
- new_debts_allowed: 是否允许新债务
- scene_count_target: 场景数量目标
- opening_hook: 开篇钩子
- ending_hook: 结尾钩子
- quality_threshold_overrides: 质量阈值覆盖

同时包含以下传统字段（用于向后兼容）：
- objective: 本章目标（必须以状态卡数值开头）
- required_events: 2-4个关键事件列表
- plots_to_plant: 要埋的伏笔代码列表
- plots_to_resolve: 要兑现的伏笔代码列表
- ending_hook: 章末钩子
- constraints: 约束条件列表

核心原则：
1. objective/chapter_goal 必须以上一章状态卡开头
2. 反派行为必须逻辑化
3. 每个伏笔必须有计划兑现
4. 禁止抽象描述（如"主角变得更强"）
5. 必须回应上一章未处理悬念、时间约束和地点约定；如暂不处理，必须写入明确延期事件
6. 必须优先继承已应用事实账本和可信记忆候选，不得忽略上一章真实记忆

禁止：
- 写正文
- 跳过审核直接发布
- 唤醒其他 Agent"""


def build_memory_context_audit(chapter_number: int, bundle) -> dict:
    """Build an auditable summary of the memory context consumed by Planner."""
    if chapter_number <= 1:
        batch_status = "not_applicable"
    elif bundle.memory_context_degraded or not bundle.trusted_memory_batch_id:
        batch_status = "missing"
    else:
        batch_status = "trusted"
    return {
        "chapter_number": chapter_number,
        "batch_id": bundle.trusted_memory_batch_id,
        "batch_status": batch_status,
        "memory_items_count": len(bundle.trusted_memory),
        "memory_context_degraded": bundle.memory_context_degraded,
        "built_at_node": "planner_node",
    }


class PlannerAgent(BaseAgent):
    """Planner: creates writing instructions for a chapter."""

    agent_id = "planner"

    def __init__(self, repo, llm, skill_registry: SkillRegistry | None = None, **kwargs):
        super().__init__(repo, llm, skill_registry=skill_registry, **kwargs)
        self.skill_registry = skill_registry

    def build_context(self, state: FactoryState) -> str:
        parts = []
        project_id = state["project_id"]
        chapter_number = state["chapter_number"]

        title_contract = self._get_title_contract_context(project_id)
        if title_contract:
            parts.append(title_contract)

        # v6.6.2: Unified context builder
        builder = AgentContextBuilder(self.repo)
        bundle = builder.build_for_planner(project_id, chapter_number, state)
        formatted = format_context_bundle_for_prompt(bundle, agent_name="planner", max_chars=12000)
        if formatted:
            parts.append(formatted)

        # v6.6.2: Retain legacy planner inheritance context for backward compatibility
        inheritance_context = build_planner_inheritance_context(
            self.repo,
            project_id,
            chapter_number,
        )
        if inheritance_context:
            parts.append(inheritance_context)

        # R3: Review notes from human review sessions (v3.2)
        review_notes = self.repo.get_chapter_review_notes(project_id, chapter_number)
        if review_notes:
            latest_note = review_notes[0]
            parts.append(f"【人工审核意见】\n{latest_note['notes']}")

        # Seam context (retained for explicit bridge constraints)
        seam_context = build_chapter_seam_context(repo=self.repo, project_id=project_id, chapter_number=chapter_number)
        if seam_context:
            parts.append(seam_context)

        # Pending messages
        messages = self.repo.get_pending_messages(state["project_id"], "planner")
        if messages:
            msg_str = "\n".join(f"- [{m['from_agent']}] {m['type']}: {m['content'][:200]}" for m in messages[:5])
            parts.append(f"【待处理异议】\n{msg_str}")

        # v4.0: Style Bible injection
        style_ctx = self._get_style_bible_context(project_id, "planner")
        if style_ctx:
            parts.append(style_ctx)

        # v6.9.0: Creative ledger context injection
        try:
            from ..context.ledger_context import load_ledgers_for_planner, format_ledger_context_for_prompt
            ledgers = load_ledgers_for_planner(self.repo, project_id, chapter_number)
            ledger_context = format_ledger_context_for_prompt(ledgers)
            if ledger_context:
                parts.append(ledger_context)
        except Exception as e:
            logger.warning(f"Failed to load ledger context: {e}")

        return "\n\n".join(parts)

    def _execute(self, state: FactoryState) -> dict[str, Any]:
        project_id = state["project_id"]
        chapter_number = state["chapter_number"]
        exec_events: list[dict] = []

        context = self._build_v6_context(state)

        messages = [
            {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
            {"role": "user", "content": f"项目ID: {project_id}\n章节号: {chapter_number}\n\n{context}\n\n请生成第{chapter_number}章的写作指令。"},
        ]

        raw = self._invoke_json(messages, schema=PlannerOutput)
        output = PlannerOutput(**raw)

        self.validate_output(output.model_dump())

        # Save instruction to DB, preserving word_target if one already exists
        brief = output.chapter_brief

        # v6.6.2: Inheritance check on generated brief
        prev_state = self._get_prev_state_card(state)
        builder = AgentContextBuilder(self.repo)
        bundle = builder.build_for_planner(project_id, chapter_number, state)

        # v6.6.14: Build memory context audit from the bundle metadata
        memory_context_audit: dict = build_memory_context_audit(chapter_number, bundle)

        inheritance_check = validate_chapter_inheritance(
            prev_state,
            bundle,
            brief.model_dump(),
        )
        if inheritance_check.warnings:
            exec_events.append({
                "event_type": "planner_inheritance_check",
                "message": f"Planner 继承检查提醒：{len(inheritance_check.warnings)} 项",
                "status": "warning",
                "payload": {"warnings": inheritance_check.warnings[:5]},
            })
        if inheritance_check.advisory_issues:
            exec_events.append({
                "event_type": "planner_inheritance_advisory",
                "message": f"Planner 继承建议：{len(inheritance_check.advisory_issues)} 项",
                "status": "info",
                "payload": {"advisory": inheritance_check.advisory_issues[:5]},
            })

        repaired_inheritance, inheritance_issues = enforce_planner_inheritance(
            brief,
            self.repo,
            project_id,
            chapter_number,
        )
        if repaired_inheritance:
            exec_events.append({
                "event_type": "planner_inheritance_repaired",
                "message": f"自动补齐章节继承约束：{len(inheritance_issues)} 项",
                "status": "warning",
                "payload": {"issues": inheritance_issues[:5]},
            })

        project_skill_overrides = self._get_project_skill_overrides(project_id)
        skill_result = run_agent_skills(
            repo=self.repo,
            skill_registry=self.skill_registry,
            project_id=project_id,
            chapter_number=chapter_number,
            agent="planner",
            stage="after_llm",
            payload=brief.model_dump(),
            project_overrides=project_skill_overrides,
            skill_type_hint="validator",
        )
        if skill_result.skill_results:
            for sr in skill_result.skill_results:
                exec_events.append({
                    "event_type": "skill_completed",
                    "message": f"Skill {sr.get('skill_id', '')} {'通过' if sr.get('ok') else '失败'}",
                    "status": "info" if sr.get("ok") else "warning",
                    "payload": {"skill_id": sr.get("skill_id"), "ok": sr.get("ok")},
                })

        existing = self.repo.get_instruction(project_id, chapter_number)
        project = self.repo.get_project(project_id)
        word_target = existing.get("word_target") if existing else None
        if not word_target:
            word_target = derive_word_target(existing, project)

        self.repo.create_instruction(
            project_id=project_id,
            chapter_number=chapter_number,
            objective=brief.objective,
            key_events=json.dumps(brief.required_events, ensure_ascii=False),
            plots_to_plant=json.dumps(brief.plots_to_plant, ensure_ascii=False),
            plots_to_resolve=json.dumps(brief.plots_to_resolve, ensure_ascii=False),
            ending_hook=brief.ending_hook,
            word_target=word_target,
        )

        exec_events.append({
            "event_type": "artifact_saved",
            "message": "保存产物：章节指令",
            "payload": {"artifact_type": "chapter_brief"},
        })

        # Update chapter status. Planner can be entered from a normal planned
        # chapter or from a planner-targeted revision after Editor rejects.
        expected_status = (
            ChapterStatus.REVISION.value
            if state.get("chapter_status") == ChapterStatus.REVISION.value
            else ChapterStatus.PLANNED.value
        )
        ok = self.repo.update_chapter_status(
            project_id, chapter_number, ChapterStatus.PLANNED.value,
            expected_status=expected_status,
        )
        if not ok:
            return {"error": "Planner: stale state, status advance failed", "chapter_status": state.get("chapter_status")}

        # Save artifact (bind to workflow run for isolation)
        workflow_run_id = state.get("workflow_run_id")
        self.repo.save_artifact(
            project_id, chapter_number, "planner", "chapter_brief",
            content_json=output.model_dump(),
            workflow_run_id=workflow_run_id,
        )
        # v6.6.14: persist memory context audit for run detail observability
        self.repo.save_artifact(
            project_id, chapter_number, "planner", "memory_context_audit",
            content_json=memory_context_audit,
            workflow_run_id=workflow_run_id,
        )

        return {
            "chapter_status": ChapterStatus.PLANNED.value,
            "current_stage": "planned",
            "_exec_events": exec_events,
            "memory_context_audit": memory_context_audit,
        }

    def validate_output(self, output: dict) -> None:
        """Validate PlannerOutput schema."""
        PlannerOutput(**output)  # Will raise ValidationError if invalid

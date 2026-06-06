"""Screenwriter Agent — decomposes instructions into scene beats."""

from __future__ import annotations

import json
import logging
from typing import Any

from ..models.schemas import ScreenwriterOutput
from ..models.state import ChapterStatus, FactoryState
from ..skills.registry import SkillRegistry
from ..agent_runtime.base import BaseAgent
from ..agent_runtime.skill_hooks import run_agent_skills
from ..agent_runtime.self_check import SelfCheckLoop, SelfCheckResult
from ..agent_runtime.context_builder import AgentContextBuilder, format_context_bundle_for_prompt
from ..quality.chapter_inheritance import validate_chapter_inheritance

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
4. 遵守 ChapterBrief 的 forbidden_moves（禁止动作）
5. 优先处理 ledger_debts_to_pay（需要偿还的台账债务）

禁止：
- 改写世界观和角色设定
- 写最终正文
- 决定审核结果
- 违反 ChapterBrief 中明确禁止的动作"""


class ScreenwriterAgent(BaseAgent):
    """Screenwriter: decomposes chapter instructions into scene beats."""

    agent_id = "screenwriter"

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
        bundle = builder.build_for_screenwriter(project_id, chapter_number, state)
        formatted = format_context_bundle_for_prompt(bundle, agent_name="screenwriter", max_chars=12000)
        if formatted:
            parts.append(formatted)

        # Scene beats from instruction (Screenwriter needs to see them explicitly as beats)
        instruction = self._get_instruction(state)
        if instruction:
            parts.append(f"【Planner Brief】\n目标: {instruction.get('objective', '')}\n"
                         f"关键事件: {instruction.get('key_events', '')}\n"
                         f"章末钩子: {instruction.get('ending_hook', '')}\n"
                         f"埋设伏笔: {instruction.get('plots_to_plant', '[]')}\n"
                         f"兑现伏笔: {instruction.get('plots_to_resolve', '[]')}")
        
        # v6.9.0: Inject ChapterBrief constraints
        chapter_brief = state.get("chapter_brief", {})
        if chapter_brief:
            forbidden_moves = chapter_brief.get("forbidden_moves", [])
            ledger_debts = chapter_brief.get("ledger_debts_to_pay", [])
            if forbidden_moves or ledger_debts:
                brief_constraints = []
                if forbidden_moves:
                    brief_constraints.append(f"禁止动作: {', '.join(forbidden_moves)}")
                if ledger_debts:
                    brief_constraints.append(f"需要偿还的债务: {', '.join(ledger_debts)}")
                parts.append("【ChapterBrief 约束】\n" + "\n".join(brief_constraints))

        # v6.8.1: Style-aware prompt injection (webnovel excitement, suspense, romance)
        style_prompt = self._get_style_prompt_injection(project_id, "screenwriter")
        if style_prompt:
            parts.append(style_prompt)

        return "\n\n".join(parts)

    def _execute(self, state: FactoryState) -> dict[str, Any]:
        project_id = state["project_id"]
        chapter_number = state["chapter_number"]
        exec_events: list[dict] = []

        context = self._build_v6_context(state)

        # v6.0: Self-check loop for scene beat quality
        loop = SelfCheckLoop(agent_id=self.agent_id, max_repair_attempts=1)

        def _generate_wrap() -> dict[str, Any]:
            messages = [
                {"role": "system", "content": SCREENWRITER_SYSTEM_PROMPT},
                {"role": "user", "content": f"项目ID: {project_id}\n章节号: {chapter_number}\n\n{context}\n\n请将以上指令拆解为场景 beat。"},
            ]
            raw = self._invoke_json(messages, schema=ScreenwriterOutput)
            raw = self._normalize_output(raw)
            out = ScreenwriterOutput(**raw)
            self.validate_output(out.model_dump())
            return {"output": out}

        def _self_check_wrap(data: dict[str, Any]) -> SelfCheckResult:
            out = data["output"]
            issues: list[dict[str, Any]] = []
            for i, beat in enumerate(out.scene_beats):
                if not beat.scene_goal:
                    issues.append({"type": "beat_completeness", "message": f"Beat {i+1} missing scene_goal"})
                if not beat.conflict:
                    issues.append({"type": "beat_completeness", "message": f"Beat {i+1} missing conflict"})
                if not beat.turn:
                    issues.append({"type": "beat_completeness", "message": f"Beat {i+1} missing turn"})
                if not beat.hook:
                    issues.append({"type": "beat_completeness", "message": f"Beat {i+1} missing hook"})
            return SelfCheckResult(
                passed=len(issues) == 0,
                issues=issues,
                repair_needed=len(issues) > 0,
                repair_suggestion="重新生成缺失字段的 beat",
            )

        def _repair_wrap(data: dict[str, Any], check: SelfCheckResult) -> dict[str, Any] | None:
            # One retry with stronger prompt
            messages = [
                {"role": "system", "content": SCREENWRITER_SYSTEM_PROMPT + "\n\n注意：每个 beat 必须包含 sequence, scene_goal, conflict, turn, hook 五个字段，缺一不可。"},
                {"role": "user", "content": f"项目ID: {project_id}\n章节号: {chapter_number}\n\n{context}\n\n请将以上指令拆解为场景 beat。确保每个 beat 都有完整的五个字段，sequence 从 1 开始连续编号。"},
            ]
            try:
                raw = self._invoke_json(messages, schema=ScreenwriterOutput)
                raw = self._normalize_output(raw)
                out = ScreenwriterOutput(**raw)
                self.validate_output(out.model_dump())
                return {"output": out}
            except Exception:
                return None

        loop_result = loop.run(_generate_wrap, _self_check_wrap, _repair_wrap)
        output = loop_result["output"]
        trace = loop_result.get("_trace", {})
        autonomy = loop_result.get("_autonomy", {})
        if state.get("llm_mode") == "real" and autonomy.get("decision") in {"ask_human", "reroute", "refuse"}:
            reason = autonomy.get("reason") or "Screenwriter 自检未通过"
            return {
                "error": f"Screenwriter 自检未通过: {reason}",
                "chapter_status": state.get("chapter_status"),
                "requires_human": True,
                "quality_gate": {
                    "pass": False,
                    "revision_target": "screenwriter",
                    "self_check_fail": True,
                    "message": reason,
                    "agent": "screenwriter",
                    "workflow_run_id": state.get("workflow_run_id"),
                },
                "_trace": trace,
                "_autonomy": autonomy,
            }

        beats_data = [b.model_dump() for b in output.scene_beats]

        # v6.6.2: Light inheritance check on scene beats
        prev_state = self._get_prev_state_card(state)
        builder = AgentContextBuilder(self.repo)
        bundle = builder.build_for_screenwriter(project_id, chapter_number, state)
        inheritance_check = validate_chapter_inheritance(
            prev_state, bundle, {"scene_beats": beats_data},
        )
        if inheritance_check.warnings:
            exec_events.append({
                "event_type": "screenwriter_inheritance_check",
                "message": f"Screenwriter 继承检查提醒：{len(inheritance_check.warnings)} 项",
                "status": "warning",
                "payload": {"warnings": inheritance_check.warnings[:5]},
            })

        exec_events.append({
            "event_type": "artifact_saved",
            "message": f"保存产物：场景规划 ({len(beats_data)} 个 beat)",
            "payload": {"artifact_type": "scene_plan", "beat_count": len(beats_data)},
        })
        skill_result = run_agent_skills(
            repo=self.repo,
            skill_registry=self.skill_registry,
            project_id=project_id,
            chapter_number=chapter_number,
            agent="screenwriter",
            stage="after_llm",
            payload={"scene_beats": beats_data},
            project_overrides=self._get_project_skill_overrides(project_id),
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

        # Advance status FIRST to lock the transition; abort if stale
        ok = self.repo.update_chapter_status(
            project_id, chapter_number, ChapterStatus.SCRIPTED.value,
            expected_status=ChapterStatus.PLANNED.value,
        )
        if not ok:
            # v6.8.1: Check if chapter is already at or past SCRIPTED (recovery run)
            current_status = self.repo.get_chapter_status(project_id, chapter_number)
            _STATUS_ORDER = {
                "idea": 0, "outlined": 1, "planned": 2, "scripted": 3,
                "drafted": 4, "polished": 5, "review": 6, "reviewed": 7,
                "revision": 8, "published": 9, "blocking": 10,
            }
            current_order = _STATUS_ORDER.get(current_status, -1)
            scripted_order = _STATUS_ORDER.get("scripted", 3)
            if current_order >= scripted_order:
                logger.info(
                    "Screenwriter: chapter already at '%s' (order %d >= %d), skipping status advance (recovery run)",
                    current_status, current_order, scripted_order,
                )
            else:
                logger.error("Screenwriter: status advance planned→scripted failed (stale state)")
                return {"error": "Screenwriter: stale state, status advance failed", "chapter_status": state.get("chapter_status"), "_trace": trace, "_autonomy": autonomy}

        # Save scene beats (only after status advance succeeds)
        try:
            self.repo.save_scene_beats(project_id, chapter_number, beats_data)

            # Save artifact (bind to workflow run for isolation)
            workflow_run_id = state.get("workflow_run_id")
            self.repo.save_artifact(
                project_id, chapter_number, "screenwriter", "scene_plan",
                content_json=output.model_dump(),
                workflow_run_id=workflow_run_id,
            )
        except Exception as e:
            self._compensate_status(
                project_id, chapter_number,
                ChapterStatus.SCRIPTED.value, ChapterStatus.PLANNED.value,
            )
            return {"error": f"Screenwriter: write failed: {e}", "chapter_status": ChapterStatus.PLANNED.value, "_trace": trace, "_autonomy": autonomy}

        return {
            "chapter_status": ChapterStatus.SCRIPTED.value,
            "current_stage": "scripted",
            "_trace": trace,
            "_autonomy": autonomy,
            "_exec_events": exec_events,
        }

    def validate_output(self, output: dict) -> None:
        ScreenwriterOutput(**self._normalize_output(output))

    def _normalize_output(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Repair harmless Screenwriter JSON omissions before strict schema validation.

        Real LLMs occasionally emit otherwise usable scene beats without the
        mechanical sequence field. The database and downstream context require
        stable ordering, so assign missing/invalid sequence values from the
        array position instead of failing the whole workflow.
        """
        if not isinstance(raw, dict):
            return raw

        normalized = dict(raw)
        beats = normalized.get("scene_beats")
        if not isinstance(beats, list):
            return normalized

        repaired_beats: list[Any] = []
        for index, beat in enumerate(beats, start=1):
            if not isinstance(beat, dict):
                repaired_beats.append(beat)
                continue
            next_beat = dict(beat)
            try:
                sequence = int(next_beat.get("sequence", index))
            except (TypeError, ValueError):
                sequence = index
            if sequence <= 0:
                sequence = index
            next_beat["sequence"] = sequence
            if next_beat.get("plot_refs") is None:
                next_beat["plot_refs"] = []
            repaired_beats.append(next_beat)

        normalized["scene_beats"] = repaired_beats
        return normalized

"""Screenwriter Agent — decomposes instructions into scene beats."""

from __future__ import annotations

import json
import logging
from typing import Any

from ..models.schemas import ScreenwriterOutput
from ..models.state import ChapterStatus, FactoryState, status_order
from ..skills.registry import SkillRegistry
from ..agent_runtime.base import BaseAgent
from ..agent_runtime.skill_hooks import run_agent_skills
from ..agent_runtime.self_check import SelfCheckLoop, SelfCheckResult
from ..agent_runtime.context_builder import AgentContextBuilder, format_context_bundle_for_prompt
from ..quality.chapter_inheritance import validate_chapter_inheritance
from ..quality.concept_budget import CONCEPT_BUDGET_CONTRACT

logger = logging.getLogger(__name__)

SCREENWRITER_SYSTEM_PROMPT = """你是网文工厂的编剧（Screenwriter），负责将总编的章节指令拆解成可执行的场景 beat。

输出格式：严格按 JSON 格式输出，包含 scene_beats 数组，每个 beat 包含：
- sequence: 序号（从1开始）
- scene_goal: 场景目标
- conflict: 冲突
- turn: 转折
- plot_refs: 涉及的伏笔代码列表
- hook: 场景钩子

核心循环前置字段：
- is_reward_beat: boolean —— 该 beat 是否承载核心爽点。Planner 指定的 reward_event_index 对应的 beat 必须设为 true
- character_states: object —— 该 beat 中各角色的物理状态（如 {"陆璃": "锁死于金属床，无意识"}）
- dialogue_slots: array —— 该 beat 中的对白设计槽位，每个槽位包含：
  - speakers: 对话双方角色列表
  - conflict_type: 冲突类型（"立场对立"/"信息差"/"潜台词"）
  - key_line: 关键台词（可留空）
  - must_convey: 这段对白必须传递的信息

核心原则：
1. 每个场景必须有推进作用
2. 标记伏笔埋设或兑现位置
3. 控制单章节奏，确保章末钩子
4. 遵守 ChapterBrief 的 forbidden_moves（禁止动作）
5. 优先处理 ledger_debts_to_pay（需要偿还的台账债务）

【核心循环前置原则】：
1. 读取 Planner 指令中的 core_loop.reward_event_index
2. 将该事件对应的 beat 标记为 is_reward_beat = true
3. 确保该 beat 的 scene_goal 明确包含核心爽点的展开
4. 确保主角在该 beat 中有主动行动，不是被动接受

【事实锁感知原则】：
1. 读取 fact_locks 中的角色物理状态
2. 每个 beat 的 character_states 必须反映这些限制
3. 如果角色状态是"锁死/无意识"，dialogue_slots 中不能包含该角色的主动发言

【对白设计原则】：
1. 总对白槽位数 ≥ 3（对应 15% 占比目标）
2. 至少 1 段对白必须有冲突（conflict_type 不为空）
3. 避免所有信息通过旁白/说明传递，优先设计对白

【beat 数量约束】：
1. scene_beats 数量必须与 scene_count_target 一致（默认 3，最多 4）
2. 禁止生成超过 scene_count_target+1 个 beat
3. 每个 beat 必须有足够的展开空间（4000 字目标 ÷ beat 数 = 每个 beat 的字数预算）
4. 如果 required_events 有 3 个，beat 数量应为 3-4，不要拆成 8 个

禁止：
- 改写世界观和角色设定
- 写最终正文
- 决定审核结果
- 违反 ChapterBrief 中明确禁止的动作"""

SCREENWRITER_SYSTEM_PROMPT += (
    "\n\n" + CONCEPT_BUDGET_CONTRACT
    + "\n- 分场时全章所有 scene beat 必须围绕同一个核心新概念推进，不得每个场景各自展开新机制。"
)


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

            # Inject scene_count_target as a hard beat limit
            scene_count_target = chapter_brief.get("scene_count_target", 3)
            parts.append(f"【场景数量约束】\n目标场景数: {scene_count_target}\n"
                         f"硬性上限: {scene_count_target + 1} 个 beat\n"
                         f"禁止生成超过 {scene_count_target + 1} 个 beat")

            # Inject core_loop governance into Screenwriter context
            core_loop = chapter_brief.get("core_loop", {})
            if core_loop:
                core_loop_parts = ["【核心循环设计约束】"]
                reward_idx = core_loop.get("reward_event_index", 1)
                reward_type = core_loop.get("reward_type", "ability")
                reward_evidence = core_loop.get("reward_evidence", "")
                protagonist_decision = core_loop.get("protagonist_decision", "")
                core_loop_parts.append(f"核心爽点对应第 {reward_idx} 个关键事件")
                core_loop_parts.append(f"爽点类型: {reward_type}")
                if reward_evidence:
                    core_loop_parts.append(f"爽点证据: {reward_evidence}")
                if protagonist_decision:
                    core_loop_parts.append(f"主角主动决策: {protagonist_decision}")
                parts.append("\n".join(core_loop_parts))

            # Inject fact_locks into Screenwriter context
            fact_locks = chapter_brief.get("fact_locks", [])
            if fact_locks:
                parts.append("【事实锁 — 角色物理状态约束】\n"
                             + "\n".join(f"- {fl}" for fl in fact_locks))

            # Inject dialogue_target_ratio into Screenwriter context
            dialogue_target = chapter_brief.get("dialogue_target_ratio", 0.15)
            parts.append(f"【对白设计目标】\n目标对白占比: {dialogue_target * 100:.0f}%\n"
                         f"要求: 至少设计 3 段对白槽位，其中至少 1 段有冲突或潜台词")

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
            # v6.10.8: Reject empty scene_beats — downstream Author needs at least one beat
            if not out.scene_beats:
                issues.append({"type": "beat_completeness", "message": "scene_beats 列表为空，至少需要 1 个 beat"})
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
            # v6.10.8: Use shared status_order() instead of local dict.
            current_status = self.repo.get_chapter_status(project_id, chapter_number)
            current_order = status_order(current_status)
            scripted_order = status_order("scripted")
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

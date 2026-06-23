"""Editor Agent — performs five-dimension quality review.

v6.6.8: Refactored _execute() into clear private methods:
  _load_editor_inputs -> _call_editor_llm -> _run_quality_diagnosis
  -> _run_chapter_seam_check -> _apply_review_strategy
  -> _persist_editor_artifacts -> _build_editor_state_updates

Review semantics are now determined by editor_strategy.py exclusively.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from typing import Any

from ..models.schemas import EditorOutput
from ..models.state import ChapterStatus, FactoryState
from ..validators.chapter_checker import count_words, check_word_count_quality_gate, derive_word_target
from ..validators.death_penalty import check_death_penalty, check_death_penalty_structured
from ..validators.revision_classifier import classify_issues
from ..quality.editor_strategy import (
    EditorDecision,
    EditorPolicyInput,
    build_policy_input,
    classify_editor_result,
    determine_revision_target,
    post_process_llm_decision,
)
from ..quality.feedback_bridge import build_compact_feedback, format_editor_context
from ..skills.registry import SkillRegistry
from ..skills.base import SkillFinding, parse_skill_findings, sort_findings_by_severity
from ..llm.provider import is_configured_live_provider
from ..agent_runtime.base import BaseAgent
from ..agent_runtime.revision_context import normalize_revision_review
from ..agent_runtime.skill_hooks import run_agent_skills
from ..agent_runtime.context_builder import AgentContextBuilder, format_context_bundle_for_prompt
from ..quality.chapter_seam import build_chapter_seam_context, evaluate_chapter_seam
from ..quality.concept_budget import CONCEPT_BUDGET_CONTRACT
from ..quality.continuity_gate import (
    evaluate_chapter_continuity,
    SEVERITY_BLOCKING,
)

logger = logging.getLogger(__name__)

EDITOR_SYSTEM_PROMPT = """你是网文工厂的质检（Editor），是读者毒抗的最后一道防线。

五层审校维度：
1. 设定一致性 (满分25) — 与世界观、角色、前文一致
2. 逻辑漏洞 (满分25) — 无硬伤、无降智
3. 毒点检测 (满分20) — 无读者厌恶套路
4. 文字质量 (满分15) — 无AI烂词、无说教
5. 爽点钩子 (满分15) — 有高潮、有悬念

文字质量子维度（v6.4 质量信号，评审时重点关注）：
- AI 痕迹：无模板句式、无直白情绪词（"感到/觉得/意识到"）、无机械解释
- 叙事质感：感官细节充足（光影/声音/气味/温度）、动作描写具体、对白自然
- 节奏控制：段落长短有变化、紧张场景用短句/短段、避免均匀段落
- 设定展现：无旁白式 info dump（"这个世界是..."/"所谓..."/"简单来说"）、设定通过动作/对话展现
- 对白人物化：对白有角色目的、潜台词或冲突、不同角色语气有差异

评审原则：
- 只评审和给修订建议，**不直接改写正文**
- issues 和 suggestions 各最多 3 条，必须具体可执行
- 不要泛泛评价（如"写得不错"），要给出可操作的修改方向

评分规则：
- 总分 >= 85 且无 blocking/priority 问题 → 通过 (pass=true)
- 80-84 如只有 advisory 问题 → 通过并给发布前建议；如存在明确高优先级问题 → 退回返修
- 78-79 只有在存在具体、可执行的高优先级问题时才退回；不要为了轻微风格瑕疵卡在 79
- < 78 → 退回 Author/Polisher 修复关键问题

死刑红线：发现 AI 烂词(冷笑、嘴角微扬等) → 总分=50

输出格式：严格按 JSON 格式输出：
- pass: boolean (通过/退回)
- score: 总分 (0-100)
- scores: {setting, logic, poison, text, pacing} 各维度分数
- issues: 问题列表
- suggestions: 修改建议列表
- revision_target: 退回目标 ("author"/"polisher"/"planner"/null)
- state_card: 如果通过，提取本章状态卡数据

示例（注意布尔值不加引号，null不加引号）：
{"pass":true,"score":85,"scores":{"setting":24,"logic":23,"poison":18,"text":12,"pacing":8},"issues":["问题描述"],"suggestions":["修改建议"],"revision_target":null,"state_card":{}}

revision_target 规则：
- 剧情、逻辑、设定、伏笔问题 → "author"
- 文风、句式、节奏、AI 痕迹、对白、场景质感问题 → "polisher"
- info dump / 设定旁白 / 直白情绪 → "author"
- 指令本身错误或设定冲突 → "planner"
- beat 设计层问题 → "screenwriter"（见下方规则）
- 通过时 → null

【beat 设计层路由规则】（在判定 revision_target 时必须先检查）：
当你检测到以下问题时，先检查 scene_beats（输入上下文中提供）：
1. 核心循环漂移/缺失：
   - 如果 scene_beats 中有 is_reward_beat=true 的 beat → "author"（beat 设计了但 Author 没写出来）
   - 如果 scene_beats 中没有 is_reward_beat=true 的 beat → "screenwriter"（beat 没设计核心循环）
2. 事实一致性矛盾：
   - 如果 scene_beats 的 character_states 已正确标注但正文违反 → "author"
   - 如果 scene_beats 的 character_states 缺失或本身错误 → "screenwriter"
3. 对白占比过低：
   - 如果 scene_beats 的 dialogue_slots ≥ 3 但正文对白不足 → "author"
   - 如果 scene_beats 的 dialogue_slots < 3 或缺失 → "screenwriter"
4. 角色物理状态冲突（如被锁死的角色有肢体互动）：
   - 如果 character_states 已标注"锁死/无意识"但正文仍写互动 → "author"
   - 如果 character_states 未标注 → "screenwriter"

简言之：beat 设计对了但 Author 没执行 → "author"；beat 本身设计有缺陷 → "screenwriter"。"""

EDITOR_SYSTEM_PROMPT += (
    "\n\n" + CONCEPT_BUDGET_CONTRACT
    + "\n评审时如发现概念超载，优先建议 Author 收束到本章唯一核心概念；除非章节目标本身冲突，否则不要退回 Planner。"
)


# ── Data classes for refactored pipeline ─────────────────────────────


@dataclass
class EditorInputs:
    """Loaded inputs for editor pipeline."""
    project_id: str
    chapter_number: int
    chapter: dict[str, Any]
    content: str
    llm_mode: str = "stub"
    revision_review: dict[str, Any] | None = None
    workflow_run_id: str | None = None
    retry_count: int = 0
    max_retries: int = 3
    db_status: str = ""
    expected_before: str = ""
    rollback_status: str = ""


@dataclass
class QualityDiagnosisResult:
    """Result from quality diagnosis."""
    priority_count: int = 0
    advisory_count: int = 0
    advisory_only: bool = True
    feedback_dict: dict[str, Any] | None = None
    diagnosis_failed: bool = False
    diagnosis_warning: str = ""


@dataclass
class SeamCheckResult:
    """Result from chapter seam check."""
    passed: bool = True
    blocking_count: int = 0
    advisory_count: int = 0
    blocking_issues: list[str] = field(default_factory=list)
    advisory_issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class EditorStrategyResult:
    """Deterministic review policy result plus auditable inputs."""
    decision: EditorDecision
    policy_input: EditorPolicyInput
    word_gate_details: dict[str, Any] = field(default_factory=dict)


# v6.6.14: story_facts compliance threshold
#
# A violation marked "blocking" by the facts checker is a hard continuity
# contradiction, not an advisory signal.  The earlier threshold of 3 let one
# or two explicit contradictions flow into generic score-based revision, which
# could route to Polisher and cause destructive rewrite loops.
FACTS_COMPLIANCE_BLOCK_THRESHOLD = 1


@dataclass
class StoryFactsComplianceResult:
    """Result from lightweight story_facts contradiction check."""
    checked: bool = False
    violation_count: int = 0
    blocking_violation_count: int = 0
    violations: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "checked": self.checked,
            "violation_count": self.violation_count,
            "blocking_violation_count": self.blocking_violation_count,
            "violations": self.violations,
        }


class EditorAgent(BaseAgent):
    """Editor: five-dimension quality review."""

    @staticmethod
    def _format_review_content_excerpt(content: str, max_chars: int) -> str:
        """Return a review excerpt that preserves the chapter ending.

        Editor decisions often depend on the ending hook and final state. A
        simple head-only excerpt can make the reviewer falsely report missing
        endings on long chapters.
        """
        text = str(content or "")
        if len(text) <= max_chars:
            return text

        head_chars = max(1200, int(max_chars * 0.42))
        tail_chars = max_chars - head_chars
        head = text[:head_chars].rstrip()
        tail = text[-tail_chars:].lstrip()
        omitted = len(text) - len(head) - len(tail)
        return (
            f"【正文开头节选】\n{head}\n\n"
            f"【中段省略：约 {omitted} 字】\n\n"
            f"【正文章末尾段，审核 ending_hook / 任务结算 / 悬念必须以此为准】\n{tail}"
        )

    agent_id = "editor"

    def __init__(self, repo, llm, skill_registry: SkillRegistry | None = None, **kwargs):
        """Initialize Editor agent.

        Args:
            repo: Repository instance.
            llm: LLM provider instance.
            skill_registry: Optional SkillRegistry for skill execution.
        """
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
        bundle = builder.build_for_editor(project_id, chapter_number, state)
        formatted = format_context_bundle_for_prompt(bundle, agent_name="editor", max_chars=12000)
        if formatted:
            parts.append(formatted)

        # Chapter content
        chapter = self._get_chapter_info(state)
        if chapter and chapter.get("content"):
            excerpt = self._format_review_content_excerpt(chapter["content"], 8000)
            parts.append(f"【本章正文】\n{excerpt}")

        # Instruction (redundant with bundle but ensures explicit visibility)
        instruction = self._get_instruction(state)
        if instruction:
            parts.append(f"【写作指令】\n目标: {instruction.get('objective', '')}\n"
                         f"关键事件: {instruction.get('key_events', '')}\n"
                         f"埋设伏笔: {instruction.get('plots_to_plant', '[]')}\n"
                         f"兑现伏笔: {instruction.get('plots_to_resolve', '[]')}")

        seam_context = build_chapter_seam_context(
            self.repo,
            project_id,
            chapter_number,
        )
        if seam_context:
            parts.append(seam_context)

        # v4.0: Style Bible injection
        style_ctx = self._get_style_bible_context(project_id, "editor")
        if style_ctx:
            parts.append(style_ctx)

        # v6.8.1: Style-aware prompt injection (webnovel excitement, suspense, romance)
        style_prompt = self._get_style_prompt_injection(project_id, "editor")
        if style_prompt:
            parts.append(style_prompt)

        # v6.6.1: Inject deterministic quality diagnosis feedback
        quality_feedback = self._build_quality_feedback(state)
        if quality_feedback:
            parts.append(quality_feedback)

        # v6.10.9: Inject quality_gate core_loop status so editor LLM does not
        # independently re-evaluate what the deterministic checker already passed.
        core_loop_status = self._build_quality_gate_core_loop_status(state)
        if core_loop_status:
            parts.append(core_loop_status)

        return "\n\n".join(parts)

    def _build_quality_feedback(self, state: FactoryState) -> str:
        """Run deterministic quality diagnosis and return compact feedback for prompt."""
        project_id = state["project_id"]
        chapter_number = state["chapter_number"]
        chapter = self._get_chapter_info(state)
        content = (chapter or {}).get("content", "") if chapter else ""
        if not content or not self.skill_registry:
            return ""

        try:
            from ..quality.hub import QualityHub
            hub = QualityHub(self.repo, self.skill_registry)
            diagnose_result = hub.diagnose(content, context={
                "project_id": project_id,
                "chapter_number": chapter_number,
            })
            feedback = build_compact_feedback(diagnose_result)
            return format_editor_context(feedback)
        except Exception:
            logger.warning("Editor: quality diagnosis failed, skipping feedback injection", exc_info=True)
            return ""

    def _build_quality_gate_core_loop_status(self, state: FactoryState) -> str:
        """v6.10.9: Inject quality_gate core_loop status into editor context.

        When the deterministic core_loop_checker already passed, tell the editor
        LLM so it doesn't independently re-evaluate core_loop and produce
        conflicting blocking issues.
        """
        quality_gate = state.get("quality_gate", {}) or {}
        if not quality_gate:
            return ""

        gate_passed = quality_gate.get("pass", quality_gate.get("passed", None))
        if gate_passed is not True:
            return ""

        # Quality gate passed — check if core_loop was among the checks
        checks_run = quality_gate.get("checks_run", [])
        core_loop_checked = any("core_loop" in str(c).lower() for c in checks_run)
        if not core_loop_checked:
            return ""

        return (
            "【确定性质检结果】\n"
            "quality_gate 已通过全部确定性检查（包括 core_loop_compliance）。"
            "核心循环兑现证据已通过确定性文本匹配验证。"
            "请聚焦于 LLM 层面的质量评估（文风、逻辑、对白、节奏等），"
            "不要独立重复评估核心循环兑现 — 该项已由上游确定性检查器确认通过。"
        )

    def _build_compact_review_context(self, state: FactoryState) -> str:
        """Build a short review prompt for live LLM calls."""
        parts = []
        project_id = state["project_id"]
        chapter_number = state["chapter_number"]

        # v6.6.2: Compact unified context
        builder = AgentContextBuilder(self.repo)
        bundle = builder.build_for_editor(project_id, chapter_number, state)
        formatted = format_context_bundle_for_prompt(bundle, agent_name="editor", max_chars=6000)
        if formatted:
            parts.append(formatted)

        chapter = self._get_chapter_info(state)
        if chapter and chapter.get("content"):
            content = chapter["content"]
            excerpt = self._format_review_content_excerpt(content, 6000)
            parts.append(f"【本章正文】\n{excerpt}")

        instruction = self._get_instruction(state)
        if instruction:
            parts.append(
                "【写作指令】\n"
                f"目标: {instruction.get('objective', '')}\n"
                f"关键事件: {instruction.get('key_events', '')}\n"
                f"伏笔: {instruction.get('plots_to_plant', '')}\n"
                f"钩子: {instruction.get('ending_hook', '')}"
            )

        seam_context = build_chapter_seam_context(
            self.repo,
            project_id,
            chapter_number,
        )
        if seam_context:
            parts.append(seam_context)

        characters = self.repo.get_characters(project_id)
        if characters:
            char_str = "\n".join(
                f"- {c['name']}({c['role']}): {c.get('description', '')}"
                for c in characters[:5]
            )
            parts.append(f"【角色】\n{char_str}")

        # v6.10.9: Inject quality_gate core_loop status for compact review too
        core_loop_status = self._build_quality_gate_core_loop_status(state)
        if core_loop_status:
            parts.append(core_loop_status)

        parts.append(
            "【输出要求】\n"
            "只返回紧凑 JSON。issues 和 suggestions 各最多 3 条；"
            "state_card 只保留本章新增事实、角色状态和悬念，不要复述正文。"
        )
        return "\n\n".join(parts)

    def _run_advisory_quality_check(self, content: str) -> tuple[list[str], list[str]]:
        """Run deterministic anti-AI skills and map findings to advisory issues/suggestions.

        These are advisory only — they are appended to issues/suggestions but do NOT
        affect pass/fail/score/revision_target.  No LLM calls.

        v6.9.1: Skill IDs now read from registry config instead of hard-coded list.
        """
        if not content or not self.skill_registry:
            return [], []

        try:
            skill_ids = self.skill_registry.get_skills_for_agent("editor", "advisory")
        except Exception:
            logger.warning("Editor: failed to load advisory skills from registry", exc_info=True)
            return [], []

        all_findings: list[SkillFinding] = []

        for skill_id in skill_ids:
            try:
                result = self.skill_registry.run_skill(
                    skill_id,
                    {"text": content},
                    agent="editor",
                    stage="advisory",
                )
                if result.get("ok"):
                    data = result.get("data") or {}
                    findings = parse_skill_findings(data)
                    all_findings.extend(findings)
            except Exception:
                logger.warning("Editor: advisory skill %s failed", skill_id, exc_info=True)
                continue

        if not all_findings:
            return [], []

        all_findings = sort_findings_by_severity(all_findings)
        capped = all_findings[:3]

        issues: list[str] = []
        suggestions: list[str] = []
        for finding in capped:
            code = finding.code
            message = finding.message
            suggestion = finding.suggestion
            if message:
                issues.append(f"[v6.4质量信号] {code}: {message}")
            if suggestion:
                suggestions.append(f"[{code}] {suggestion}")

        return issues, suggestions

    def _fallback_rule_review(
        self, content: str, reason: str, *,
        project_id: str = "",
        chapter_number: int = 0,
    ) -> EditorOutput:
        """Fallback review when live editor LLM cannot return a usable result.

        v6.7.9: Degraded fallback — can no longer give 88/excellent.
        Maximum score is 70 with a clear warning that this is a rule-based
        fallback, not a full editorial review.
        """
        dp_result = check_death_penalty_structured(content)
        has_content = bool(content.strip())

        # v6.7.9: Run continuity gate even in fallback
        continuity_result = None
        if project_id and chapter_number:
            try:
                continuity_result = evaluate_chapter_continuity(
                    self.repo, project_id, chapter_number, content,
                )
            except Exception:
                logger.warning("Editor fallback: continuity gate failed", exc_info=True)

        continuity_blocking = continuity_result is not None and continuity_result.should_block_publish

        # v6.7.9: Fallback can never auto-pass if continuity blocks
        passed = has_content and not dp_result.has_critical and not continuity_blocking
        # v6.8.2: Raise fallback ceiling to 78 (just below pass threshold)
        score = 78 if passed else 60

        issues = []
        if not has_content:
            issues.append("正文为空")
        if dp_result.has_critical:
            issues.extend([f"CRITICAL 死刑红线: {v}" for v in dp_result.violations])

        # v6.7.9: Mandatory degraded-review warning
        issues.append(
            "AI 审核不可用，本结果仅为规则兜底，不代表完整审校通过。"
            f"降级原因: {reason}"
        )

        if continuity_blocking and continuity_result:
            for ci in continuity_result.issues:
                if ci not in issues:
                    issues.append(f"[连续性阻断] {ci}")

        # v6.4.4: Advisory quality signals even in fallback
        advisory_issues, advisory_suggestions = self._run_advisory_quality_check(content)
        issues = issues + advisory_issues

        suggestions = ["请人工复核后再继续。"] + advisory_suggestions
        if continuity_result:
            suggestions = continuity_result.suggestions + suggestions

        return EditorOutput(
            pass_=passed,
            score=score,
            scores={
                "setting": 18 if passed else 12,
                "logic": 18 if passed else 12,
                "poison": 14 if passed else 10,
                "text": 10 if passed else 8,
                "pacing": 10 if passed else 8,
            },
            issues=issues,
            suggestions=suggestions,
            # v6.8.5-fix: 使用 determine_revision_target() 而非硬编码，
            # 确保 fallback 路径也能正确路由作者级问题（时间逻辑、冲突、对话比例等）
            revision_target=None if passed else determine_revision_target(
                issues=issues,
                death_penalty=dp_result.has_critical,
                seam_blocking_count=1 if continuity_blocking else 0,
            ),
            state_card=self._build_fallback_state_card(
                content, project_id, chapter_number, passed,
            ),
        )

    # ── v6.6.8: Refactored pipeline steps ───────────────────────────

    def _load_editor_inputs(self, state: FactoryState) -> EditorInputs:
        """Step 1: Load all inputs needed for the editor pipeline."""
        project_id = state["project_id"]
        chapter_number = state["chapter_number"]

        db_status = self.repo.get_chapter_status(project_id, chapter_number) or ChapterStatus.POLISHED.value
        expected_before = db_status if db_status in (ChapterStatus.POLISHED.value, ChapterStatus.REVIEW.value) else ChapterStatus.POLISHED.value
        rollback_status = ChapterStatus.POLISHED.value if expected_before == ChapterStatus.POLISHED.value else ChapterStatus.REVIEW.value

        chapter = self._get_chapter_info(state)
        if not chapter:
            raise ValueError("Chapter not found in DB")
        content = chapter.get("content", "")

        revision_review = normalize_revision_review(state.get("_revision_review"))

        return EditorInputs(
            project_id=project_id,
            chapter_number=chapter_number,
            chapter=chapter,
            content=content,
            llm_mode=state.get("llm_mode", "stub"),
            revision_review=revision_review,
            workflow_run_id=state.get("workflow_run_id"),
            retry_count=state.get("retry_count", 0),
            max_retries=state.get("max_retries", 3),
            db_status=db_status,
            expected_before=expected_before,
            rollback_status=rollback_status,
        )

    def _call_editor_llm(self, inputs: EditorInputs, state: FactoryState) -> tuple[EditorOutput, list[dict]]:
        """Step 2: Call LLM for review. Returns (output, exec_events).

        Handles JSON/schema/timeout errors and falls back to rule review.
        Does NOT make any pass/fail strategy decisions.
        """
        exec_events: list[dict] = []
        use_compact_review = inputs.llm_mode == "real" and is_configured_live_provider(self.llm)
        context = self._build_compact_review_context(state) if use_compact_review else self._build_v6_context(state)

        messages = [
            {"role": "system", "content": EDITOR_SYSTEM_PROMPT},
            {"role": "user", "content": f"项目ID: {inputs.project_id}\n章节号: {inputs.chapter_number}\n\n{context}\n\n请执行五层审校并评分。"},
        ]

        # v6.10.14: LLM retry mechanism - reduce fallback probability
        max_retries = 3 if use_compact_review else 1
        last_error = None

        for attempt in range(max_retries):
            try:
                invoke_kwargs = {}
                raw = self._invoke_json(
                    messages,
                    schema=EditorOutput,
                    **invoke_kwargs,
                )

                # v6.10.14: Validate output format before accepting
                if not self._is_valid_editor_output(raw):
                    last_error = f"Invalid output format: missing required fields"
                    logger.warning(f"Editor attempt {attempt+1}/{max_retries}: {last_error}")
                    if attempt < max_retries - 1:
                        import time
                        time.sleep(2 ** attempt)  # Exponential backoff
                        continue
                    break

                output = EditorOutput(**raw)
                self.validate_output(output.model_dump())

                # Success - log if retried
                if attempt > 0:
                    exec_events.append({
                        "event_type": "editor_retry_success",
                        "message": f"Editor LLM 第 {attempt+1} 次尝试成功",
                        "payload": {"attempt": attempt + 1, "max_retries": max_retries},
                    })

                return output, exec_events

            except Exception as e:
                last_error = str(e)
                logger.warning(f"Editor attempt {attempt+1}/{max_retries} failed: {e}")

                if attempt < max_retries - 1:
                    import time
                    time.sleep(2 ** attempt)  # Exponential backoff
                    continue

        # All retries failed - fall back to rule review
        if not use_compact_review:
            raise Exception(last_error)

        logger.warning("Editor: LLM review degraded to rule-based fallback after %d attempts: %s", max_retries, last_error)
        output = self._fallback_rule_review(
            inputs.content, str(last_error),
            project_id=inputs.project_id,
            chapter_number=inputs.chapter_number,
        )
        exec_events.append({
            "event_type": "fallback_used",
            "message": f"LLM 审核降级为规则兜底：{str(last_error)[:100]}",
            "payload": {
                "fallback_type": "rule_review",
                "reason": str(last_error)[:200],
                "degraded_review": True,
                "blocks_auto_publish": not output.pass_,
            },
        })

        return output, exec_events

    def _run_quality_diagnosis(self, inputs: EditorInputs, output: EditorOutput) -> QualityDiagnosisResult:
        """Step 3: Run deterministic quality diagnosis.

        QualityHub failure degrades to advisory warning — never blocks workflow.
        """
        result = QualityDiagnosisResult()

        if not self.skill_registry:
            return result

        try:
            from ..quality.hub import QualityHub
            from ..quality.feedback_bridge import build_compact_feedback

            hub = QualityHub(self.repo, self.skill_registry)
            diagnose_result = hub.diagnose(inputs.content, context={
                "project_id": inputs.project_id,
                "chapter_number": inputs.chapter_number,
            })
            qf = build_compact_feedback(diagnose_result)
            result.priority_count = len(qf.priority_findings)
            result.advisory_count = len(qf.advisory_findings)
            result.advisory_only = not qf.priority_findings
            result.feedback_dict = qf.to_dict()

            # Inject high-priority quality findings into output for audit
            if qf.priority_findings:
                for f in qf.priority_findings[:3]:
                    note = f"[诊断] [{f['code']}] {f['message']}"
                    if note not in output.issues:
                        output.issues.append(note)
            if qf.advisory_findings:
                for f in qf.advisory_findings[:2]:
                    note = f"[诊断建议] [{f['code']}] {f['message']}"
                    if note not in output.suggestions:
                        output.suggestions.append(note)
        except Exception:
            logger.warning("Editor: quality diagnosis for strategy failed", exc_info=True)
            result.diagnosis_failed = True
            result.diagnosis_warning = "质量诊断执行失败，已降级为 advisory"

        return result

    def _run_chapter_seam_check(self, inputs: EditorInputs, output: EditorOutput) -> SeamCheckResult:
        """Step 4: Chapter seam check via skill system (v6.9.1).

        Blocking seam issues can enter priority/blocking.
        Advisory seam issues do not hard-block.
        """
        if not self.skill_registry:
            return SeamCheckResult()

        try:
            # Run chapter-seam skill
            skill_result = self.skill_registry.run_skill(
                "chapter-seam",
                {
                    "content": inputs.content,
                    "project_id": inputs.project_id,
                    "chapter_number": inputs.chapter_number,
                    "_repo": self.repo,
                },
                agent="editor",
                stage="before_review",
            )

            if not skill_result.get("ok"):
                logger.warning("Editor: chapter-seam skill failed: %s", skill_result.get("error"))
                return SeamCheckResult()

            data = skill_result.get("data") or {}
            findings = data.get("findings") or []
            
            # Extract blocking and advisory issues from findings
            blocking_issues = []
            advisory_issues = []
            suggestions = []
            
            for finding in findings:
                severity = finding.get("severity", "info")
                message = finding.get("message", "")
                suggestion = finding.get("suggestion", "")
                
                if severity == "blocking":
                    blocking_issues.append(message)
                elif severity == "warning":
                    advisory_issues.append(message)
                else:  # info
                    if suggestion:
                        suggestions.append(suggestion)

            result = SeamCheckResult(
                passed=data.get("passed", True),
                blocking_count=len(blocking_issues),
                advisory_count=len(advisory_issues),
                blocking_issues=blocking_issues,
                advisory_issues=advisory_issues,
                suggestions=suggestions,
            )

            if not result.passed:
                output.pass_ = False
                output.score = min(output.score, 79)
                output.revision_target = "author"
                for issue in result.blocking_issues[:3]:
                    note = f"[章间衔接] {issue}"
                    if note not in output.issues:
                        output.issues.append(note)
                for suggestion in result.suggestions[:3]:
                    note = f"[章间衔接修复] {suggestion}"
                    if note not in output.suggestions:
                        output.suggestions.append(note)
                result.details = {
                    "chapter_seam_fail": True,
                    "message": "; ".join(result.blocking_issues[:3]),
                    "revision_target": "author",
                    "agent": "editor",
                    "workflow_run_id": inputs.workflow_run_id,
                }
            else:
                for issue in result.advisory_issues[:2]:
                    note = f"[章间衔接建议] {issue}"
                    if note not in output.suggestions:
                        output.suggestions.append(note)

            return result
        except Exception:
            logger.warning("Editor: chapter seam check execution failed", exc_info=True)
            return SeamCheckResult()

    def _apply_review_strategy(
        self,
        output: EditorOutput,
        quality_result: QualityDiagnosisResult,
        seam_result: SeamCheckResult,
        inputs: EditorInputs,
    ) -> EditorStrategyResult:
        """Step 5: Apply the single policy decision point.

        Returns the decision and the exact policy input snapshot.
        This is the ONLY place where pass/revision/human_review is determined.
        """
        # v6.4.4: Append advisory quality signals — do NOT change pass/fail/routing
        advisory_issues, advisory_suggestions = self._run_advisory_quality_check(inputs.content)
        if advisory_issues:
            output.issues = output.issues + advisory_issues
        if advisory_suggestions:
            output.suggestions = output.suggestions + advisory_suggestions

        # Death penalty check
        dp_result = check_death_penalty_structured(inputs.content)
        if dp_result.has_critical:
            output.pass_ = False
            output.score = min(output.score, 50)
            output.issues = output.issues + [f"CRITICAL 死刑红线: {v}" for v in dp_result.violations]

        # Word count quality gate
        instruction = self._get_instruction({"project_id": inputs.project_id, "chapter_number": inputs.chapter_number} if inputs else {})
        # Recover instruction from DB if not in state
        if not instruction:
            try:
                instruction = self.repo.get_instruction(inputs.project_id, inputs.chapter_number)
            except Exception:
                instruction = None
        project = self.repo.get_project(inputs.project_id)
        word_target = derive_word_target(instruction, project)
        word_gate_passed, word_gate_msg = check_word_count_quality_gate(
            inputs.content, word_target, "editor"
        )
        word_gate_details: dict[str, Any] = {}
        if not word_gate_passed:
            logger.warning("Editor: word count quality gate failed: %s", word_gate_msg)
            output.pass_ = False
            output.revision_target = "polisher"
            output.issues = output.issues + [word_gate_msg]
            word_gate_details = {
                "word_count_fail": True,
                "message": word_gate_msg,
                "actual_word_count": count_words(inputs.content),
                "word_target": word_target,
                "agent": "editor",
                "workflow_run_id": inputs.workflow_run_id,
            }

        # Run before_review skills and collect aggregation data
        skill_aggregation = self._run_before_review_skills(inputs, output)
        skill_scores = skill_aggregation.get("skill_scores", {})
        blocking_skill_count = skill_aggregation.get("blocking_skill_count", 0)
        warning_skill_count = skill_aggregation.get("warning_skill_count", 0)

        # Get editor_weights from genre contract
        editor_weights: dict[str, float] = {}
        try:
            project = self.repo.get_project(inputs.project_id)
            if project and "genre_contract" in project:
                genre_contract = project["genre_contract"]
                if isinstance(genre_contract, dict):
                    editor_weights = genre_contract.get("editor_weights", {})
        except Exception:
            logger.warning("Editor: failed to load genre contract for editor_weights", exc_info=True)

        # Calculate skill_weighted_score
        from ..quality.editor_strategy import aggregate_skill_scores
        skill_weighted_score = aggregate_skill_scores(skill_scores, editor_weights)

        # Classify issues for revision_target (overrides LLM self-report)
        # But NOT if a specific gate (word count, seam) already set a target
        # v6.7.9: Exclude advisory/warning continuity issues from target
        # classification — they are structural/continuity signals, not prose
        # or plot issues that should reroute to author/polisher.
        if not output.pass_ and output.issues:
            pre_classify_target = output.revision_target
            classifyable_issues = [
                i for i in output.issues
                if not i.startswith("[连续性建议]") and not i.startswith("[连续性警告]")
            ]
            classify_result = classify_issues(
                classifyable_issues if classifyable_issues else output.issues,
                output.revision_target,
            )
            gate_forced_target = (
                bool(word_gate_details)
                or seam_result.blocking_count > 0
                or any("事实一致性违规" in str(issue) for issue in output.issues)
            )
            # Override the LLM's self-reported target when issue semantics are clearer.
            # Preserve targets set by hard gates such as word count and chapter seam.
            if classify_result.dominant_target and not gate_forced_target:
                output.revision_target = classify_result.dominant_target
            elif classify_result.dominant_target and pre_classify_target:
                # Gate-set target takes precedence over issue classification
                output.revision_target = pre_classify_target

        # QualityHub final_gate (only for passing reviews)
        if output.pass_ and self.skill_registry:
            self._run_final_gate(inputs, output)

        # Apply the unified strategy
        policy_input = build_policy_input(
            score=output.score,
            pass_=output.pass_,
            issues=output.issues,
            has_hard_word_fail=bool(word_gate_details),
            has_death_penalty=dp_result.has_critical,
            quality_priority_count=quality_result.priority_count,
            quality_advisory_count=quality_result.advisory_count,
            quality_advisory_only=quality_result.advisory_only,
            seam_blocking_count=seam_result.blocking_count,
            seam_advisory_count=seam_result.advisory_count,
            retry_count=inputs.retry_count,
            max_retries=inputs.max_retries,
            skill_weighted_score=skill_weighted_score,
            blocking_skill_count=blocking_skill_count,
            warning_skill_count=warning_skill_count,
            skill_scores=skill_scores,
            editor_weights=editor_weights,
        )
        strategy_decision = classify_editor_result(policy_input)

        # LLM says fail, but policy says advisory — override without losing the input snapshot.
        # v6.10.0: Only override when the LLM score is borderline (>= 75),
        # indicating potential over-harshness.  A clear LLM fail (< 75)
        # should not be overturned by high skill scores alone.
        if not output.pass_ and strategy_decision.category == "advisory" and output.score >= 75:
            strategy_decision = post_process_llm_decision(
                output.pass_,
                output.score,
                output.issues,
                has_hard_word_fail=bool(word_gate_details),
                has_death_penalty=dp_result.has_critical,
                quality_priority_count=quality_result.priority_count,
                quality_advisory_count=quality_result.advisory_count,
                quality_advisory_only=quality_result.advisory_only,
                seam_blocking_count=seam_result.blocking_count,
                seam_advisory_count=seam_result.advisory_count,
                retry_count=inputs.retry_count,
                max_retries=inputs.max_retries,
                skill_weighted_score=skill_weighted_score,
                blocking_skill_count=blocking_skill_count,
                warning_skill_count=warning_skill_count,
                skill_scores=skill_scores,
                editor_weights=editor_weights,
            )

        # v6.10.0: Only override a clear LLM rejection when the score is
        # borderline (>= 75), indicating potential over-harshness.  A score
        # below 75 is a genuine fail and should not be overturned by skill
        # aggregation alone.
        if strategy_decision.pass_ and not output.pass_ and output.score >= 75:
            logger.info("Editor strategy accepted advisory review: %s", strategy_decision.reason)
            output.pass_ = True
            output.revision_target = None
            output.suggestions = output.suggestions + [
                f"[v6.6策略] {strategy_decision.reason}；保留为发布前建议，不进入自动返修。"
            ]
        elif not strategy_decision.pass_:
            # v6.10.4: Protect LLM's explicit pass decision when the strategy
            # failure is only due to score threshold (no hard blockers).
            # Hard blockers (death_penalty, blocking issues, blocking skills)
            # always override. Score-based revision should respect LLM's
            # explicit pass judgment to avoid unnecessary revision loops.
            has_hard_blockers = (
                dp_result.has_critical
                or bool(word_gate_details)
                or seam_result.blocking_count > 0
                or blocking_skill_count > 0
            )
            if output.pass_ and not has_hard_blockers:
                # LLM said pass, no hard blockers — respect LLM decision
                # but surface strategy concern as advisory suggestion
                logger.info(
                    "Editor strategy deferred to LLM pass: score=%s, reason=%s",
                    output.score, strategy_decision.reason,
                )
                strategy_note = f"[v6.6策略] {strategy_decision.reason}；LLM判定通过，保留为建议。"
                if strategy_note not in output.suggestions:
                    output.suggestions.append(strategy_note)
            else:
                output.pass_ = False
                if not output.revision_target:
                    output.revision_target = determine_revision_target(
                        death_penalty=dp_result.has_critical,
                        issues=output.issues,
                        llm_revision_target=output.revision_target,
                        quality_priority_count=quality_result.priority_count,
                        seam_blocking_count=seam_result.blocking_count,
                        retry_count=inputs.retry_count,
                    )
                strategy_note = f"[v6.6策略] {strategy_decision.reason}"
                if strategy_note not in output.issues:
                    output.issues.append(strategy_note)

        # advisory_pass must NOT set revision_target.  Guard this with the
        # effective final decision: hard gates may keep output.pass_=False even
        # if score/skill aggregation produced an advisory strategy snapshot.
        if output.pass_ and strategy_decision.decision_type == "advisory_pass":
            output.revision_target = None

        return EditorStrategyResult(
            decision=strategy_decision,
            policy_input=policy_input,
            word_gate_details=word_gate_details,
        )

    def _apply_style_weight_adjustment(
        self,
        inputs: EditorInputs,
        output: EditorOutput,
    ) -> None:
        """v6.8.1: Adjust dimension scores based on style profile.

        In excitement mode (high), pacing weight increases from 15→30,
        and other weights decrease proportionally. The LLM scores are
        post-processed so that pacing carries more weight in the final total.
        """
        try:
            from ..quality.style_detector import detect_style_from_text, get_editor_weight_multiplier
            project = self.repo.get_project(inputs.project_id)
            if not project:
                return
            text = " ".join(filter(None, [
                project.get("name", ""),  # 项目名称
                project.get("genre", ""),  # 类型
                project.get("description", ""),  # 项目描述
            ]))
            if not text.strip():
                return
            profile = detect_style_from_text(text)
            multipliers = get_editor_weight_multiplier(profile)

            # Only adjust if multipliers differ from identity
            if all(abs(v - 1.0) < 0.01 for v in multipliers.values()):
                return

            # Apply multipliers to each dimension score (cap at max)
            max_scores = {"setting": 25, "logic": 25, "poison": 20, "text": 15, "pacing": 15}
            adjusted_scores = {}
            weighted_sum = 0.0
            for dim in ("setting", "logic", "poison", "text", "pacing"):
                raw = getattr(output.scores, dim, 0) if hasattr(output.scores, dim) else output.scores.get(dim, 0)
                mult = multipliers.get(dim, 1.0)
                adjusted = min(round(raw * mult), max_scores.get(dim, 25))
                adjusted_scores[dim] = adjusted
                weighted_sum += adjusted

            # Recalculate total score (normalized to 100)
            # Default total max = 25+25+20+15+15 = 100
            # With multipliers, the weighted max = sum(max * mult)
            weighted_max = sum(max_scores[dim] * multipliers.get(dim, 1.0) for dim in max_scores)
            if weighted_max > 0:
                new_total = round(weighted_sum / weighted_max * 100)
            else:
                new_total = output.score

            # Update scores and total
            for dim, val in adjusted_scores.items():
                if hasattr(output.scores, dim):
                    setattr(output.scores, dim, val)
                elif isinstance(output.scores, dict):
                    output.scores[dim] = val
            output.score = new_total

            logger.info(
                "Editor: style weight adjustment applied (excitement_level=%s, new_score=%d)",
                profile.excitement_level, new_total,
            )
        except Exception:
            logger.warning("Editor: style weight adjustment failed", exc_info=True)

    def _run_continuity_gate(
        self,
        inputs: EditorInputs,
        output: EditorOutput,
    ) -> Any:
        """Run deterministic narrative continuity gate via skill system (v6.9.1).

        Blocking continuity issues override pass_/score and force revision.
        Warning/advisory issues are appended to issues/suggestions but do NOT
        mutate score or pass_ unless the issue is blocking.
        """
        if not self.skill_registry:
            return None

        try:
            # Run continuity-gate skill
            skill_result = self.skill_registry.run_skill(
                "continuity-gate",
                {
                    "content": inputs.content,
                    "title": inputs.chapter.get("title") if inputs.chapter else "",
                    "project_id": inputs.project_id,
                    "chapter_number": inputs.chapter_number,
                    "_repo": self.repo,
                },
                agent="editor",
                stage="before_review",
            )

            if not skill_result.get("ok"):
                logger.warning("Editor: continuity-gate skill failed: %s", skill_result.get("error"))
                return None

            data = skill_result.get("data") or {}
            findings = data.get("findings") or []
            
            # Process findings
            for finding in findings:
                severity = finding.get("severity", "info")
                message = finding.get("message", "")
                suggestion = finding.get("suggestion", "")
                code = finding.get("code", "")
                
                if severity == "blocking":
                    output.pass_ = False
                    output.score = min(output.score, 70)
                    output.revision_target = output.revision_target or "author"
                    note = f"[连续性阻断] {message}"
                    if note not in output.issues:
                        output.issues.append(note)
                    if suggestion:
                        note = f"[连续性修复] {suggestion}"
                        if note not in output.suggestions:
                            output.suggestions.append(note)
                elif severity == "warning":
                    note = f"[连续性警告] {message}"
                    if note not in output.issues:
                        output.issues.append(note)
                    if suggestion:
                        note = f"[连续性建议] {suggestion}"
                        if note not in output.suggestions:
                            output.suggestions.append(note)
                else:  # info
                    if suggestion:
                        note = f"[连续性建议] {suggestion}"
                        if note not in output.suggestions:
                            output.suggestions.append(note)

            return data
        except Exception:
            logger.warning("Editor: continuity gate execution failed", exc_info=True)
            return None

    def _run_before_review_skills(self, inputs: EditorInputs, output: EditorOutput) -> dict[str, Any]:
        """Run before_review skill hooks and append findings to output.

        v6.9.1: Removed hard-coded skill_id branches. All skills now parsed
        uniformly via ``parse_skill_findings()``. Returns skill aggregation data
        for use in strategy layer.

        v6.9.1 Phase 4: Dynamic skill scheduling — resolve_active_skills()
        filters the skill list based on genre, chapter position, and sampling.
        """
        if not self.skill_registry:
            return {}

        skill_payload: dict[str, Any] = {"text": inputs.content, "content": inputs.content, "chapter_number": inputs.chapter_number}
        try:
            bible_record = self.repo.get_style_bible(inputs.project_id)
            if bible_record:
                skill_payload["style_bible"] = bible_record.get("bible", {})
        except Exception:
            logger.warning("Editor: failed to load style_bible for skill payload", exc_info=True)

        project_skill_overrides = self._get_project_skill_overrides(inputs.project_id)

        # v6.9.1 Phase 4: Dynamic skill scheduling
        # Get genre contract and full skill list, then filter
        try:
            from ..skills.editor_skill_resolver import resolve_active_skills
            project = self.repo.get_project(inputs.project_id)
            genre_contract = project.get("genre_contract") if project else None
            full_skill_ids = self.skill_registry.get_skills_for_agent(
                "editor", "before_review", project_overrides=project_skill_overrides,
            )
            active_skill_ids = resolve_active_skills(
                project_id=inputs.project_id,
                chapter_number=inputs.chapter_number,
                genre_contract=genre_contract,
                skill_ids=full_skill_ids,
                repo=self.repo,
            )
            skipped_ids = set(full_skill_ids) - set(active_skill_ids)
            if skipped_ids:
                logger.info("Editor: skipped %d skills via resolver: %s", len(skipped_ids), skipped_ids)
                # Disable skipped skills via project_overrides["skills"][skill_id]
                if not project_skill_overrides:
                    project_skill_overrides = {}
                skills_overrides = project_skill_overrides.setdefault("skills", {})
                for sid in skipped_ids:
                    skills_overrides[sid] = {"enabled": False}
        except Exception:
            logger.warning("Editor: skill resolver failed, running all skills", exc_info=True)

        before_review_hook = run_agent_skills(
            repo=self.repo,
            skill_registry=self.skill_registry,
            project_id=inputs.project_id,
            chapter_number=inputs.chapter_number,
            agent="editor",
            stage="before_review",
            payload=skill_payload,
            project_overrides=project_skill_overrides,
            skill_type_hint="validator",
        )

        # Collect skill scores and counts for strategy layer
        skill_scores: dict[str, float] = {}
        blocking_skill_count = 0
        warning_skill_count = 0
        seen_blocking_groups: set[str] = set()

        for skill_item in before_review_hook.skill_results:
            skill_id = skill_item.get("skill_id", "")
            result = {"ok": skill_item.get("ok"), "error": skill_item.get("error"), "data": skill_item.get("data") or {}}

            if not result.get("ok"):
                logger.warning("Editor: skill %s failed: %s", skill_id, result.get("error"))
                continue

            if not result.get("data"):
                continue

            # v6.9.1: Unified parsing — no special-case branches per skill_id
            findings = parse_skill_findings(result["data"])
            findings = self._govern_before_review_findings(
                skill_id,
                findings,
                seen_blocking_groups,
            )

            # v6.10.0: Record skill score even when no findings are present.
            # A clean skill run (score=100, no findings) is still a valid data
            # point for aggregation.  Without this, only skills that emit
            # warnings/blockings contribute, skewing the aggregate downward.
            skill_score = result["data"].get("score")
            if skill_score is not None:
                skill_scores[skill_id] = self._govern_before_review_score(skill_id, float(skill_score))
            elif not findings:
                continue
            else:
                # Infer score from findings severity
                findings = sort_findings_by_severity(findings)
                has_blocking = any(f.severity in ("blocking", "critical") for f in findings)
                has_warning = any(f.severity == "warning" for f in findings)
                if has_blocking:
                    skill_scores[skill_id] = 0.0
                elif has_warning:
                    skill_scores[skill_id] = 70.0
                else:
                    skill_scores[skill_id] = 100.0

            # Count blocking and warning findings
            for finding in findings:
                if finding.severity in ("blocking", "critical"):
                    blocking_skill_count += 1
                elif finding.severity == "warning":
                    warning_skill_count += 1

                prefix = "[质量诊断]"
                if finding.severity in ("blocking", "critical"):
                    msg = f"{prefix} [{finding.code}] {finding.message}" if finding.code else f"{prefix} {finding.message}"
                    if msg not in output.issues:
                        output.issues.append(msg)
                elif finding.severity == "warning":
                    msg = f"{prefix} [{finding.code}] {finding.message}" if finding.code else f"{prefix} {finding.message}"
                    if msg not in output.suggestions:
                        output.suggestions.append(msg)
                else:  # info
                    if finding.suggestion:
                        sugg = f"[质量诊断建议] [{finding.code}] {finding.suggestion}" if finding.code else f"[质量诊断建议] {finding.suggestion}"
                        if sugg not in output.suggestions:
                            output.suggestions.append(sugg)

        return {
            "skill_scores": skill_scores,
            "blocking_skill_count": blocking_skill_count,
            "warning_skill_count": warning_skill_count,
        }

    def _govern_before_review_score(self, skill_id: str, score: float) -> float:
        """Apply v6.10.2 severity policy to Skill score aggregation.

        Advisory skills may lower confidence, but they should not drive the
        strategy layer's ``skill_weighted_score < 70`` hard revision rule by
        themselves.  Clamp advisory scores to the warning band.
        """
        if not self.skill_registry:
            return score

        try:
            manifest = self.skill_registry.get_manifest(skill_id)
        except Exception:
            manifest = None

        severity_default = getattr(manifest, "severity_default", "blocking") if manifest else "blocking"
        if severity_default == "advisory":
            return max(score, 70.0)
        if severity_default == "disabled":
            return 100.0
        return score

    def _govern_before_review_findings(
        self,
        skill_id: str,
        findings: list[SkillFinding],
        seen_blocking_groups: set[str],
    ) -> list[SkillFinding]:
        """Apply v6.10.2 governance metadata to before_review findings.

        Subjective/advisory skills should not create hard revision loops by
        default.  Skills in the same ``dedupe_group`` can still report all
        findings, but only the first blocking finding in that group remains
        blocking for strategy counting.
        """
        if not findings or not self.skill_registry:
            return findings

        manifest = None
        try:
            manifest = self.skill_registry.get_manifest(skill_id)
        except Exception:
            manifest = None

        severity_default = getattr(manifest, "severity_default", "blocking") if manifest else "blocking"
        dedupe_group = getattr(manifest, "dedupe_group", "") if manifest else ""
        group_key = dedupe_group or skill_id
        knowledge_ids = list(getattr(manifest, "knowledge_skill_ids", []) or []) if manifest else []

        governed: list[SkillFinding] = []
        for finding in findings:
            severity = finding.severity
            if severity_default == "disabled":
                severity = "info"
            elif severity_default == "advisory" and severity in ("blocking", "critical", "high"):
                severity = "warning"

            if severity in ("blocking", "critical"):
                if group_key in seen_blocking_groups:
                    severity = "warning"
                else:
                    seen_blocking_groups.add(group_key)

            suggestion = finding.suggestion
            if knowledge_ids and suggestion:
                knowledge_note = "、".join(f"knowledge:{item}" for item in knowledge_ids)
                if knowledge_note not in suggestion:
                    suggestion = f"{suggestion}（参考 {knowledge_note}）"

            governed.append(SkillFinding(
                severity=severity,
                code=finding.code,
                message=finding.message,
                suggestion=suggestion,
            ))

        return governed

    def _run_final_gate(self, inputs: EditorInputs, output: EditorOutput) -> None:
        """Run QualityHub final_gate on passing reviews."""
        if not self.skill_registry:
            return

        try:
            from ..quality.hub import QualityHub
            hub = QualityHub(self.repo, self.skill_registry)
            gate_result = hub.final_gate(
                inputs.project_id,
                inputs.chapter_number,
                include_editor_review=False,
            )

            if not gate_result.get("ok"):
                logger.error("Editor: QualityHub final_gate failed: %s", gate_result.get("error"))
                return

            gate_data = gate_result.get("data", {})
            if not gate_data.get("pass"):
                output.pass_ = False
                output.revision_target = gate_data.get("revision_target")
                blocking_issues = gate_data.get("blocking_issues", [])
                for issue in blocking_issues:
                    issue_msg = issue.get("message", str(issue))
                    if issue_msg not in output.issues:
                        output.issues.append(issue_msg)
                output.score = min(output.score, int(gate_data.get("overall_score", 60)))
                logger.warning(
                    "Editor: final_gate not passed (score=%.2f), revision_target=%s",
                    gate_data.get("overall_score", 0),
                    output.revision_target,
                )
            else:
                try:
                    self.repo.save_quality_report(
                        project_id=inputs.project_id,
                        chapter_number=inputs.chapter_number,
                        stage="final",
                        overall_score=gate_data.get("overall_score", 0),
                        pass_=True,
                        revision_target=None,
                        blocking_issues=gate_data.get("blocking_issues", []),
                        warnings=gate_data.get("warnings", []),
                        skill_results=gate_data.get("skill_results", []),
                        quality_dimensions=gate_data.get("quality_dimensions", {}),
                    )
                except Exception as e:
                    logger.warning("Editor: failed to save quality report: %s", e)
        except Exception:
            logger.warning("Editor: final_gate execution failed", exc_info=True)

    def _persist_editor_artifacts(
        self,
        inputs: EditorInputs,
        output: EditorOutput,
        quality_result: QualityDiagnosisResult,
        seam_result: SeamCheckResult,
        strategy_result: EditorStrategyResult,
        compliance_result: StoryFactsComplianceResult | None = None,
    ) -> int | None:
        """Step 6: Save review, state card, and artifacts.

        Returns review_id or None on failure.
        Does NOT change strategy decisions.
        """
        # Save review AFTER all gates have mutated output
        review_id = self.repo.save_review(
            project_id=inputs.project_id,
            chapter_id=inputs.chapter["id"],
            passed=output.pass_,
            score=output.score,
            setting_score=output.scores.setting,
            logic_score=output.scores.logic,
            poison_score=output.scores.poison,
            text_score=output.scores.text,
            pacing_score=output.scores.pacing,
            issues=output.issues,
            suggestions=output.suggestions,
            revision_target=output.revision_target,
        )

        # Save classified issues
        if not output.pass_ and output.issues:
            try:
                classify_result = classify_issues(output.issues, output.revision_target)
                categories = [
                    {"issue": ci.issue, "category": ci.category.value, "target": ci.revision_target}
                    for ci in classify_result.issues
                ]
                self.repo.save_review_categories(review_id, categories)
            except Exception:
                logger.warning("Failed to save review categories")

        # Write learned patterns when rejecting
        if not output.pass_:
            self._save_learned_patterns(inputs.project_id, inputs.chapter_number, output)

        return review_id

    def _build_editor_state_updates(
        self,
        inputs: EditorInputs,
        output: EditorOutput,
        quality_result: QualityDiagnosisResult,
        seam_result: SeamCheckResult,
        strategy_result: EditorStrategyResult,
        exec_events: list[dict],
        compliance_result: StoryFactsComplianceResult | None = None,
        review_id: int | None = None,
    ) -> dict[str, Any]:
        """Step 7: Build final state updates.

        Handles status transitions, artifact saves, and retry logic.
        Returns the complete state update dict.
        """
        # Revision followup verification
        if inputs.revision_review:
            prev_issues = inputs.revision_review.get("issues") or []
            prev_issue_set = set(str(i).strip() for i in (prev_issues or []) if str(i).strip())
            current_issue_set = set(str(i).strip() for i in (output.issues or []) if str(i).strip())
            resolved = list(prev_issue_set - current_issue_set)[:10]
            unresolved = list(prev_issue_set & current_issue_set)[:10]
            exec_events.append({
                "event_type": "revision_followup_verified",
                "message": f"返修复核：{'通过' if output.pass_ else '未通过'}，已解决 {len(resolved)} 项，未解决 {len(unresolved)} 项",
                "status": "info" if output.pass_ else "warning",
                "payload": {
                    "source_review_id": inputs.revision_review.get("review_id"),
                    "resolved": resolved,
                    "unresolved": unresolved,
                    "partially_resolved": [],
                    "current_score": output.score,
                    "previous_score": inputs.revision_review.get("score"),
                },
            })

        if output.pass_:
            return self._build_pass_updates(
                inputs, output, quality_result, seam_result, strategy_result,
                exec_events, compliance_result,
            )
        else:
            return self._build_fail_updates(
                inputs, output, quality_result, seam_result, strategy_result,
                exec_events, compliance_result, review_id,
            )

    def _build_pass_updates(
        self,
        inputs: EditorInputs,
        output: EditorOutput,
        quality_result: QualityDiagnosisResult,
        seam_result: SeamCheckResult,
        strategy_result: EditorStrategyResult,
        exec_events: list[dict],
        compliance_result: StoryFactsComplianceResult | None = None,
    ) -> dict[str, Any]:
        """Build state updates for passing review."""
        ok = self.repo.update_chapter_status(
            inputs.project_id, inputs.chapter_number, ChapterStatus.REVIEWED.value,
            expected_status=inputs.expected_before,
        )
        if not ok:
            logger.error("Editor: status advance %s→reviewed failed (stale state)", inputs.expected_before)
            return {"error": "Editor: stale state, status advance failed", "chapter_status": inputs.db_status}

        try:
            # Save state card
            state_card = output.state_card or self._build_minimal_state_card(inputs.content)
            state_ok = self.repo.save_chapter_state(
                inputs.project_id, inputs.chapter_number, state_card,
                summary=f"第{inputs.chapter_number}章状态卡 (score={output.score})",
            )
            if not state_ok:
                self._compensate_status(
                    inputs.project_id, inputs.chapter_number,
                    ChapterStatus.REVIEWED.value, inputs.rollback_status,
                )
                return {"error": "Editor: save_chapter_state failed", "chapter_status": inputs.rollback_status}

            # Save artifact with policy snapshots
            artifact_payload = self._build_artifact_payload(
                output, quality_result, seam_result, strategy_result, compliance_result,
            )
            self.repo.save_artifact(
                inputs.project_id, inputs.chapter_number, "editor", "review",
                content_json=artifact_payload,
                workflow_run_id=inputs.workflow_run_id,
            )
        except Exception as e:
            self._compensate_status(
                inputs.project_id, inputs.chapter_number,
                ChapterStatus.REVIEWED.value, inputs.rollback_status,
            )
            return {"error": f"Editor: write failed: {e}", "chapter_status": inputs.rollback_status}

        exec_events.append({
            "event_type": "artifact_saved",
            "message": f"保存产物：审核报告 (评分: {output.score}，{'通过' if output.pass_ else '退回'})",
            "payload": {
                "artifact_type": "review",
                "score": output.score,
                "passed": output.pass_,
                "revision_target": output.revision_target,
            },
        })

        return {
            "chapter_status": ChapterStatus.REVIEWED.value,
            "current_stage": "reviewed",
            "retry_count": inputs.retry_count,
            "requires_human": False,
            "quality_gate": {
                "pass": True,
                "passed": True,  # v6.8.5: 兼容 quality_gate_node 的字段名
                "score": output.score,
                "revision_target": None,
                **strategy_result.word_gate_details,
                **seam_result.details,
            },
            "_exec_events": exec_events,
        }

    def _build_fail_updates(
        self,
        inputs: EditorInputs,
        output: EditorOutput,
        quality_result: QualityDiagnosisResult,
        seam_result: SeamCheckResult,
        strategy_result: EditorStrategyResult,
        exec_events: list[dict],
        compliance_result: StoryFactsComplianceResult | None = None,
        review_id: int | None = None,
    ) -> dict[str, Any]:
        """Build state updates for failing review."""
        # Use DB retry count as source of truth (may differ from state)
        retry_count = self.repo.get_chapter_retry_count(inputs.project_id, inputs.chapter_number)

        # Check circuit breaker
        if retry_count >= inputs.max_retries:
            return self._build_human_review_updates(
                inputs, output, quality_result, seam_result, strategy_result,
                exec_events, retry_count, compliance_result, review_id,
            )

        # Revision
        return self._build_revision_updates(
            inputs, output, quality_result, seam_result, strategy_result,
            exec_events, retry_count, compliance_result, review_id,
        )

    def _build_human_review_updates(
        self,
        inputs: EditorInputs,
        output: EditorOutput,
        quality_result: QualityDiagnosisResult,
        seam_result: SeamCheckResult,
        strategy_result: EditorStrategyResult,
        exec_events: list[dict],
        retry_count: int,
        compliance_result: StoryFactsComplianceResult | None = None,
        review_id: int | None = None,
    ) -> dict[str, Any]:
        """Build state updates for human_review (max retries reached)."""
        ok = self.repo.update_chapter_status(
            inputs.project_id, inputs.chapter_number, ChapterStatus.BLOCKING.value,
            expected_status=inputs.expected_before,
        )
        if not ok:
            logger.error("Editor: status advance %s→blocking failed (stale state)", inputs.expected_before)
            return {"error": "Editor: stale state, status advance failed", "chapter_status": inputs.db_status}

        try:
            self.repo.send_message(
                inputs.project_id, "editor", "dispatcher", "ESCALATE",
                {"reason": f"Chapter {inputs.chapter_number} reached max retries ({retry_count})"},
                priority="urgent", chapter_number=inputs.chapter_number,
            )
            artifact_payload = self._build_artifact_payload(
                output, quality_result, seam_result, strategy_result, compliance_result,
            )
            self.repo.save_artifact(
                inputs.project_id, inputs.chapter_number, "editor", "review",
                content_json=artifact_payload,
                workflow_run_id=inputs.workflow_run_id,
            )
        except Exception as e:
            self._compensate_status(
                inputs.project_id, inputs.chapter_number,
                ChapterStatus.BLOCKING.value, inputs.rollback_status,
            )
            return {"error": f"Editor: write failed: {e}", "chapter_status": inputs.rollback_status}

        exec_events.append({
            "event_type": "artifact_saved",
            "message": f"保存产物：审核报告 (评分: {output.score}，退回→人工)",
            "payload": {
                "artifact_type": "review",
                "score": output.score,
                "passed": False,
                "revision_target": output.revision_target,
            },
        })

        return {
            "chapter_status": ChapterStatus.BLOCKING.value,
            "current_stage": "blocking",
            "retry_count": retry_count,
            "requires_human": True,
            "quality_gate": {
                "pass": False,
                "score": output.score,
                "revision_target": output.revision_target,
                **strategy_result.word_gate_details,
                **seam_result.details,
            },
            "_revision_review": {
                "review_id": review_id,
                "score": output.score,
                "revision_target": output.revision_target,
                "issues": output.issues,
                "suggestions": output.suggestions,
            },
            "_exec_events": exec_events,
        }

    def _build_revision_updates(
        self,
        inputs: EditorInputs,
        output: EditorOutput,
        quality_result: QualityDiagnosisResult,
        seam_result: SeamCheckResult,
        strategy_result: EditorStrategyResult,
        exec_events: list[dict],
        retry_count: int,
        compliance_result: StoryFactsComplianceResult | None = None,
        review_id: int | None = None,
    ) -> dict[str, Any]:
        """Build state updates for revision routing."""
        retry_agent = output.revision_target or "author"
        ok = self.repo.update_chapter_status(
            inputs.project_id, inputs.chapter_number, ChapterStatus.REVISION.value,
            expected_status=inputs.expected_before,
        )
        if not ok:
            logger.error("Editor: status advance %s→revision failed (stale state)", inputs.expected_before)
            return {"error": "Editor: stale state, status advance failed", "chapter_status": inputs.db_status}

        try:
            revise_task_id = self.repo.start_task(
                inputs.project_id,
                inputs.chapter_number,
                "revise",
                retry_agent,
                workflow_run_id=inputs.workflow_run_id,
            )
            self.repo.complete_task(revise_task_id, success=True)
            if retry_agent != "author":
                self.repo.send_message(
                    inputs.project_id, "editor", retry_agent, "FLAG_ISSUE",
                    {"issues": output.issues[:3], "chapter": inputs.chapter_number},
                    chapter_number=inputs.chapter_number,
                )
            artifact_payload = self._build_artifact_payload(
                output, quality_result, seam_result, strategy_result, compliance_result,
            )
            self.repo.save_artifact(
                inputs.project_id, inputs.chapter_number, "editor", "review",
                content_json=artifact_payload,
                workflow_run_id=inputs.workflow_run_id,
            )
        except Exception as e:
            self._compensate_status(
                inputs.project_id, inputs.chapter_number,
                ChapterStatus.REVISION.value, inputs.rollback_status,
            )
            return {"error": f"Editor: write failed: {e}", "chapter_status": inputs.rollback_status}

        exec_events.append({
            "event_type": "artifact_saved",
            "message": f"保存产物：审核报告 (评分: {output.score}，退回)",
            "payload": {
                "artifact_type": "review",
                "score": output.score,
                "passed": False,
                "revision_target": output.revision_target,
            },
        })

        return {
            "chapter_status": ChapterStatus.REVISION.value,
            "current_stage": "revision",
            "retry_count": retry_count + 1,
            "requires_human": False,
            "quality_gate": {
                "pass": False,
                "score": output.score,
                "revision_target": output.revision_target,
                **strategy_result.word_gate_details,
                **seam_result.details,
            },
            "_revision_review": {
                "review_id": review_id,
                "score": output.score,
                "revision_target": output.revision_target,
                "issues": output.issues,
                "suggestions": output.suggestions,
            },
            "_exec_events": exec_events,
        }

    def _build_artifact_payload(
        self,
        output: EditorOutput,
        quality_result: QualityDiagnosisResult,
        seam_result: SeamCheckResult,
        strategy_result: EditorStrategyResult,
        compliance_result: StoryFactsComplianceResult | None = None,
    ) -> dict[str, Any]:
        """Build artifact payload with full observability data (v6.6.8)."""
        payload = output.model_dump()

        # Quality diagnosis feedback
        if quality_result.feedback_dict:
            payload["_quality_feedback"] = quality_result.feedback_dict

        # Seam check result
        payload["_seam_check"] = {
            "passed": seam_result.passed,
            "blocking_count": seam_result.blocking_count,
            "advisory_count": seam_result.advisory_count,
        }

        policy_input = asdict(strategy_result.policy_input)
        policy_output = asdict(strategy_result.decision)
        payload["_policy_input"] = policy_input
        payload["_policy_output"] = policy_output
        if compliance_result is not None:
            payload["story_facts_compliance"] = compliance_result.to_dict()

        # Strategy decision snapshot (legacy artifact shape)
        payload["_strategy_decision"] = {
            "pass_": strategy_result.decision.pass_,
            "category": strategy_result.decision.category,
            "decision_type": strategy_result.decision.decision_type,
            "reason": strategy_result.decision.reason,
            "recommended_action": strategy_result.decision.recommended_action,
            "revision_target": strategy_result.decision.revision_target,
        }

        return payload

    # ── Main _execute entry point ────────────────────────────────────

    def _run_story_facts_compliance(
        self, inputs: "EditorInputs"
    ) -> StoryFactsComplianceResult:
        """Run lightweight story_facts contradiction check (v6.6.14).

        Only flags explicit contradictions where chapter text directly opposes a
        confirmed fact. A fact that is simply absent from the chapter is NOT a
        violation.
        """
        result = StoryFactsComplianceResult()

        # Stub mode: no LLM call
        if inputs.llm_mode == "stub":
            return result

        # Load confirmed story_facts (status="active" = confirmed in this schema)
        try:
            confirmed_facts = self.repo.list_story_facts(inputs.project_id, status="active")
        except Exception:
            confirmed_facts = []

        if not confirmed_facts:
            return result

        # v6.10.11: Deduplicate by subject.attribute, keeping only the latest source_chapter
        # This prevents contradictory facts from being checked against chapter content
        latest_facts: dict[str, tuple[dict, int]] = {}
        for fact in confirmed_facts:
            subject = fact.get("subject") or ""
            attribute = fact.get("attribute") or ""
            key = f"{subject}.{attribute}" if subject and attribute else (subject or attribute or fact.get("fact_key", ""))
            src_ch = int(fact.get("source_chapter") or fact.get("last_changed_chapter") or 0)
            if src_ch > inputs.chapter_number:
                continue
            if key not in latest_facts or src_ch > latest_facts[key][1]:
                latest_facts[key] = (fact, src_ch)
        confirmed_facts = [f for f, _ in latest_facts.values()]

        if not confirmed_facts:
            return result

        # Prefer facts whose subject/key tokens appear in the chapter text (up to 30)
        chapter_lower = inputs.content.lower()

        def _relevance(fact: dict) -> int:
            # v6.10.10: Also check attribute field for better relevance matching
            subject = str(fact.get("subject") or fact.get("fact_key") or "").lower()
            attribute = str(fact.get("attribute") or "").lower()
            tokens = (subject + " " + attribute).split()
            return sum(1 for t in tokens if len(t) > 1 and t in chapter_lower)

        sorted_facts = sorted(confirmed_facts, key=_relevance, reverse=True)
        facts_to_check = sorted_facts[:30]

        facts_lines = []
        for f in facts_to_check:
            subject = f.get("subject") or f.get("fact_key") or "unknown"
            attribute = f.get("attribute") or ""
            value = f.get("value_json") or ""
            if isinstance(value, str) and value.startswith(("{", "[")):
                try:
                    import json as _j
                    value = _j.loads(value)
                except Exception:
                    pass
            label = f"{subject}.{attribute}" if attribute else subject
            facts_lines.append(f"- {label}: {value}")

        facts_str = "\n".join(facts_lines)
        chapter_excerpt = inputs.content[:12000]

        system_msg = (
            "你是连续性审核员。请核查章节正文中是否存在与已确认事实的【明确矛盾】。\n\n"
            "核查规则：\n"
            "1. 只报告明确矛盾：正文直接与事实相悖（例如事实记录角色叫林泽，"
            "正文把同一角色写成另一个身份、名字、阵营或状态）。\n"
            "2. 事实未被章节提及 = 不算违规，不要报告。\n"
            "3. 伏笔未兑现 = 不算违规。\n"
            "4. 状态型事实（恐惧、被围住、瘫软、狼狈、被控制等）与后续行为/对话"
            "的搭配不算矛盾。例如事实为\"赵宏明.状态=被安保围住，极度恐惧\"，"
            "正文写\"赵宏明强撑着威胁对方\"或\"赵宏明虚张声势地大喊\"属于"
            "合理的人物反应（恐惧中的强撑/挣扎/伪装），不应标记为矛盾。"
            "只有当正文明确写出角色自由行动、主动命令安保、或完全忽略被围状态时"
            "（如\"赵宏明从容指挥安保\"、\"赵宏明大步离开\"），才构成矛盾。\n"
            "5. 严格输出 JSON，无额外说明。\n\n"
            '输出格式：{"violations": [{"fact_key": "...", "fact_statement": "...", '
            '"violation_text": "章节中矛盾段落(30-80字)", "severity": "blocking"|"warning"}]}'
        )
        user_msg = (
            f"【已确认事实列表】\n{facts_str}\n\n"
            f"【章节正文（节选）】\n{chapter_excerpt}"
        )

        try:
            raw = self._invoke_json(
                [
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": user_msg},
                ],
                schema=None,
            )
            violations = raw.get("violations") or [] if isinstance(raw, dict) else []
        except Exception as e:
            logger.warning("Editor: story_facts compliance check failed: %s", e)
            return result

        # v6.7.8: Deterministic status-fact filter.
        # Status-type facts (fear, surrounded, paralyzed, bedraggled, controlled, etc.)
        # combined with actions/dialogue that are *consistent* with that status
        # (struggling, bluffing, speaking under duress) should never be blocking.
        #
        # P1-2: A hard-contradiction guard prevents downgrading when the text
        # also contains phrases that are unambiguously incompatible with the
        # status (e.g. "从容指挥安保" while fact says "被围住").
        _STATUS_FACT_KEYWORDS = (
            "恐惧", "害怕", "惊恐", "被围", "围住", "包围", "瘫软", "瘫倒",
            "狼狈", "被控制", "被困", "被擒", "被缚", "被押", "动弹不得",
            "无法动弹", "极度恐惧", "瑟瑟发抖", "浑身发抖", "双腿发软",
            "遍体鳞伤", "精疲力竭", "奄奄一息", "伤痕累累",
        )
        _CONSISTENT_ACTION_KEYWORDS = (
            "强撑", "虚张声势", "硬撑", "挣扎", "颤抖", "哆嗦", "勉强",
            "嘴硬", "色厉内荏", "外强中干", "装作", "假装", "强装",
            "鼓起勇气", "壮着胆子", "硬着头皮", "故作", "强自",
            "强行维持", "摇摇欲坠", "声音粗重", "声音干涩", "声音发颤",
            "强作镇定", "故作镇定", "咬牙撑住", "强打精神", "苦撑",
            "外厉内荏", "有气无力", "气若游丝",
        )
        # Hard-contradiction phrases: if the violation text contains any of
        # these, the downgrade is blocked regardless of consistent-action hits.
        _HARD_CONTRADICTION_PHRASES = (
            "从容指挥", "从容离开", "大步离开", "大步走出", "大步走开",
            "自由离开", "自由行动", "调动安保", "解除包围", "指挥安保",
            "下令放行", "转身离去", "起身离去", "扬长而去", "拂袖而去",
            "泰然自若", "若无其事", "面不改色", "镇定自若", "气定神闲",
            "安然无恙", "毫发无伤", "从容不迫",
        )

        def _is_status_fact_consistent(violation: dict) -> bool:
            """Return True if the violation is a status-fact vs consistent-action.

            Returns False (no downgrade) when:
            - The fact is not a status-type fact, OR
            - The text contains a hard-contradiction phrase, OR
            - The text does not contain any consistent-action keyword.
            """
            fact_stmt = str(violation.get("fact_statement") or violation.get("fact_key") or "")
            violation_text = str(violation.get("violation_text") or "")
            has_status = any(kw in fact_stmt for kw in _STATUS_FACT_KEYWORDS)
            if not has_status:
                return False
            # Hard-contradiction guard: explicit incompatible behavior blocks downgrade.
            if any(kw in violation_text for kw in _HARD_CONTRADICTION_PHRASES):
                return False
            has_consistent_action = any(kw in violation_text for kw in _CONSISTENT_ACTION_KEYWORDS)
            return has_consistent_action

        for v in violations:
            if v.get("severity") == "blocking" and _is_status_fact_consistent(v):
                v["severity"] = "warning"
                v["_downgrade_reason"] = "status_fact_with_consistent_action"

        blocking = [v for v in violations if v.get("severity") == "blocking"]
        result.checked = True
        result.violations = violations
        result.violation_count = len(violations)
        result.blocking_violation_count = len(blocking)
        return result

    def _apply_revision_regression_guard(
        self,
        inputs: EditorInputs,
        output: EditorOutput,
        compliance_result: StoryFactsComplianceResult,
        exec_events: list[dict],
    ) -> None:
        """Prevent retry loops from degrading a chapter while chasing feedback.

        When a revision attempt scores materially worse than the review that
        triggered it, the safest automated action is not another prose polish.
        Keep the failure, but force the target back to Author with explicit
        "patch the current draft" instructions.
        """
        if output.pass_:
            return

        previous = inputs.revision_review or {}
        previous_score_raw = previous.get("score")
        try:
            previous_score = float(previous_score_raw)
            current_score = float(output.score)
        except (TypeError, ValueError):
            return

        score_delta = current_score - previous_score
        if score_delta > -10:
            return

        previous_issues = previous.get("issues") or []
        previous_fact_blocks = sum(1 for item in previous_issues if "事实一致性违规" in str(item))
        current_fact_blocks = compliance_result.blocking_violation_count

        output.pass_ = False
        output.revision_target = "author"
        issue = (
            f"[质量回退保护] 本轮返修评分从 {previous_score:.0f} 降至 {current_score:.0f}"
            f"（{score_delta:.0f}），禁止继续语言润色式返修，必须由 Author 基于当前稿做定点事实/结构修复。"
        )
        if issue not in output.issues:
            output.issues.insert(0, issue)

        if current_fact_blocks > previous_fact_blocks:
            fact_issue = (
                f"[质量回退保护] 事实一致性阻断从 {previous_fact_blocks} 增至 {current_fact_blocks}，"
                "下一轮只允许修复矛盾证据段，不得新增概念、地点或旧场景回放。"
            )
            if fact_issue not in output.issues:
                output.issues.insert(1, fact_issue)

        suggestion = (
            "基于当前保留稿做补丁式返修：优先替换被标记的事实矛盾段，"
            "保留未被点名的剧情、对白和篇幅；不要整章重写。"
        )
        if suggestion not in output.suggestions:
            output.suggestions.insert(0, suggestion)

        exec_events.append({
            "event_type": "revision_regression_guard_applied",
            "message": (
                f"返修评分回退保护：{previous_score:.0f} → {current_score:.0f}，"
                "强制退回 Author 定点修复"
            ),
            "status": "warning",
            "payload": {
                "previous_score": previous_score,
                "current_score": current_score,
                "score_delta": score_delta,
                "previous_fact_blocks": previous_fact_blocks,
                "current_fact_blocks": current_fact_blocks,
                "revision_target": "author",
            },
        })

    def _execute(self, state: FactoryState) -> dict[str, Any]:
        """Execute editor review — v6.8.5 simplified pipeline.

        v6.8.5: Deterministic quality checks (death_penalty, word_count, seam,
        continuity, quality_diagnosis) are now handled by the upstream
        quality_gate_node. Editor focuses on LLM-based review and final
        strategy decision.
        """
        # Step 1: Load inputs
        inputs = self._load_editor_inputs(state)

        # v6.10.0: Emit progress event - editor started
        exec_events: list[dict] = []
        exec_events.append({
            "event_type": "editor_started",
            "message": f"开始审核第 {inputs.chapter_number} 章",
            "status": "info",
            "payload": {"project_id": inputs.project_id, "chapter_number": inputs.chapter_number},
        })

        # Step 2: Call LLM
        output, llm_exec_events = self._call_editor_llm(inputs, state)
        exec_events.extend(llm_exec_events)

        # Step 2.5: Style-aware weight adjustment (v6.8.1)
        self._apply_style_weight_adjustment(inputs, output)

        # v6.10.0: Emit progress event - LLM review completed
        exec_events.append({
            "event_type": "llm_review_completed",
            "message": f"LLM 审核完成，评分: {output.score}",
            "status": "info",
            "payload": {"score": output.score, "pass": output.pass_},
        })

        # v6.8.5: Read quality_gate results from state (set by upstream quality_gate_node)
        quality_gate = state.get("quality_gate", {}) or {}

        # v6.8.5: Validate quality_gate presence
        if not quality_gate:
            logger.warning(
                "Editor: quality_gate missing from state, using defaults. "
                "This may indicate upstream quality_gate_node did not run. "
                "project_id=%s, chapter_number=%s",
                inputs.project_id, inputs.chapter_number,
            )
        elif not quality_gate.get("checks_run"):
            logger.warning(
                "Editor: quality_gate present but checks_run empty, quality_gate_node may have failed. "
                "project_id=%s, chapter_number=%s",
                inputs.project_id, inputs.chapter_number,
            )

        # Build quality_result from quality_gate state
        quality_result = QualityDiagnosisResult(
            priority_count=len(quality_gate.get("priority_issues", [])),
            advisory_count=len(quality_gate.get("advisory_issues", [])),
            advisory_only=not quality_gate.get("priority_issues"),
        )

        # Build seam_result from quality_gate state
        seam_diagnostics = quality_gate.get("diagnostics", {}).get("chapter_seam", {})
        seam_result = SeamCheckResult(
            passed=seam_diagnostics.get("passed", True),
            blocking_count=len(quality_gate.get("blocking_issues", [])) if "章间衔接" in str(quality_gate.get("blocking_issues", [])) else 0,
            advisory_count=len(seam_diagnostics.get("advisory_issues", [])),
        )

        # Inject quality_gate issues into output for strategy
        if quality_gate.get("blocking_issues"):
            for issue in quality_gate["blocking_issues"]:
                if issue not in output.issues:
                    output.issues.append(issue)
        if quality_gate.get("priority_issues"):
            for issue in quality_gate["priority_issues"][:3]:
                if issue not in output.issues:
                    output.issues.append(issue)
        if quality_gate.get("advisory_issues"):
            for issue in quality_gate["advisory_issues"][:2]:
                if issue not in output.suggestions:
                    output.suggestions.append(issue)

        # v6.10.0: Emit progress event - quality diagnosis started
        exec_events.append({
            "event_type": "quality_diagnosis_started",
            "message": "开始质量诊断",
            "status": "info",
            "payload": {},
        })

        # Step 4.5: Story facts compliance check (v6.6.14) — still runs in Editor (LLM-based)
        compliance_result = self._run_story_facts_compliance(inputs)

        # v6.10.0: Emit progress event - quality diagnosis completed
        exec_events.append({
            "event_type": "quality_diagnosis_completed",
            "message": f"质量诊断完成，优先问题: {quality_result.priority_count}，建议: {quality_result.advisory_count}",
            "status": "info",
            "payload": {
                "priority_count": quality_result.priority_count,
                "advisory_count": quality_result.advisory_count,
                "advisory_only": quality_result.advisory_only,
            },
        })
        if compliance_result.blocking_violation_count >= FACTS_COMPLIANCE_BLOCK_THRESHOLD:
            for v in compliance_result.violations:
                if v.get("severity") == "blocking":
                    issue_msg = (
                        f"[事实一致性违规] {v.get('fact_statement', '')[:60]}: "
                        f"{v.get('violation_text', '')[:80]}"
                    )
                    if issue_msg not in output.issues:
                        output.issues.append(issue_msg)
            output.pass_ = False
            output.revision_target = "author"

        # v6.10.0: Emit progress event - story facts compliance completed
        exec_events.append({
            "event_type": "story_facts_compliance_completed",
            "message": f"事实一致性检查完成，违规: {compliance_result.violation_count}",
            "status": "info",
            "payload": {
                "violation_count": compliance_result.violation_count,
                "blocking_violation_count": compliance_result.blocking_violation_count,
            },
        })

        # Step 5: Apply review strategy (THE single decision point)
        strategy_result = self._apply_review_strategy(
            output, quality_result, seam_result, inputs,
        )

        self._apply_revision_regression_guard(
            inputs, output, compliance_result, exec_events,
        )

        # v6.10.0: Emit progress event - review strategy applied
        # Use output.pass_ (post-processed final decision) to stay consistent
        # with editor_completed. The raw strategy_decision may differ when
        # score < 75 prevents the advisory override from taking effect.
        exec_events.append({
            "event_type": "review_strategy_applied",
            "message": f"审核策略应用完成，通过: {output.pass_}",
            "status": "info",
            "payload": {
                "pass": output.pass_,
                "revision_needed": strategy_result.decision.revision_needed,
                "category": strategy_result.decision.category,
                "revision_target": output.revision_target,
                "score": output.score,
            },
        })

        # Step 6: Persist artifacts
        review_id = self._persist_editor_artifacts(
            inputs, output, quality_result, seam_result,
            strategy_result, compliance_result,
        )

        # v6.10.0: Emit progress event - editor completed
        exec_events.append({
            "event_type": "editor_completed",
            "message": f"审核完成，{'通过' if output.pass_ else '退回'}，评分: {output.score}",
            "status": "info",
            "payload": {
                "pass": output.pass_,
                "score": output.score,
                "revision_target": output.revision_target,
                "review_id": review_id,
            },
        })

        # Step 7: Build state updates
        result = self._build_editor_state_updates(
            inputs, output, quality_result, seam_result,
            strategy_result, exec_events, compliance_result, review_id,
        )
        result["story_facts_compliance"] = compliance_result.to_dict()
        return result

    def _is_valid_editor_output(self, raw: Any) -> bool:
        """v6.10.14: Validate Editor LLM output format before parsing.

        Checks if the output has the required structure to avoid
        JSON parsing errors that cause fallback.
        """
        if not isinstance(raw, dict):
            return False

        # Check required fields
        required_fields = ["pass", "score", "issues", "suggestions"]
        for field in required_fields:
            if field not in raw:
                return False

        # Check score is a number
        if not isinstance(raw.get("score"), (int, float)):
            return False

        # Check issues is a list
        if not isinstance(raw.get("issues"), list):
            return False

        return True

    def validate_output(self, output: dict) -> None:
        parsed = EditorOutput(**output)
        if parsed.revision_target and parsed.revision_target not in ("author", "polisher", "planner", None):
            raise ValueError(f"Invalid revision_target: {parsed.revision_target}")

    def _build_minimal_state_card(self, content: str) -> dict[str, Any]:
        """Build a conservative state card when the LLM returns an empty one."""
        text = str(content or "").strip()
        tail = text[-500:] if text else ""
        return {
            "summary": tail[:180] if tail else "本章已通过审核。",
            "new_facts": [],
            "character_status": {},
            "suspense_hooks": [],
        }

    def _build_fallback_state_card(
        self,
        content: str,
        project_id: str,
        chapter_number: int,
        passed: bool,
    ) -> dict[str, Any]:
        """Build state card for fallback review with character state extraction.

        v6.10.13: When LLM review fails and we use rule-based fallback,
        we still need to extract basic character states to ensure chapter
        inheritance works correctly for the next chapter.
        """
        # Start with minimal state card
        state_card = self._build_minimal_state_card(content)

        # Add fallback markers
        state_card["degraded_review"] = True
        state_card["fallback_type"] = "rule_review"
        state_card["summary"] = "AI 审核不可用，已完成规则兜底检查；请人工发布前复核。"

        if not passed:
            return {}

        # Try to extract character states from previous chapter state
        try:
            if project_id and chapter_number > 1:
                prev_state = self.repo.get_chapter_state(project_id, chapter_number - 1)
                if prev_state:
                    prev_data = prev_state.get("state_data", {})
                    if isinstance(prev_data, str):
                        import json
                        try:
                            prev_data = json.loads(prev_data)
                        except Exception:
                            prev_data = {}

                    # Carry forward character_status from previous chapter
                    if "character_status" in prev_data and isinstance(prev_data["character_status"], dict):
                        state_card["character_status"] = prev_data["character_status"]

                    # Carry forward suspense_hooks from previous chapter
                    if "suspense_hooks" in prev_data and isinstance(prev_data["suspense_hooks"], list):
                        state_card["suspense_hooks"] = prev_data["suspense_hooks"]
        except Exception:
            logger.warning("Editor fallback: failed to carry forward previous state")

        # Try to extract character names from content for basic tracking
        try:
            # Get known characters from database
            characters = self.repo.get_characters(project_id)
            if characters and content:
                for char in characters:
                    char_name = char.get("name", "")
                    if char_name and char_name in content:
                        state_card.setdefault("character_status", {})[char_name] = "出场"
        except Exception:
            logger.debug("Editor fallback: character extraction not available")

        return state_card

    def _save_learned_patterns(
        self, project_id: str, chapter_number: int, output: EditorOutput,
    ) -> None:
        """Q5: Write high-value issues to learned_patterns for future context."""
        try:
            classify_result = classify_issues(output.issues, output.revision_target)
            for ci in classify_result.issues:
                self.repo.save_learned_pattern(
                    project_id=project_id,
                    category=ci.category.value,
                    pattern=ci.issue[:200],
                    chapter_number=chapter_number,
                )
        except Exception:
            logger.warning("Failed to save learned patterns")

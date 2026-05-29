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
from ..llm.provider import is_configured_live_provider
from ..agent_runtime.base import BaseAgent
from ..agent_runtime.revision_context import normalize_revision_review
from ..agent_runtime.skill_hooks import run_agent_skills
from ..agent_runtime.context_builder import AgentContextBuilder, format_context_bundle_for_prompt
from ..quality.chapter_seam import build_chapter_seam_context, evaluate_chapter_seam

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

revision_target 规则：
- 剧情、逻辑、设定、伏笔问题 → "author"
- 文风、句式、节奏、AI 痕迹、对白、场景质感问题 → "polisher"
- info dump / 设定旁白 / 直白情绪 → "author"
- 指令本身错误或设定冲突 → "planner"
- 通过时 → null"""


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
FACTS_COMPLIANCE_BLOCK_THRESHOLD = 3


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

        # v6.6.1: Inject deterministic quality diagnosis feedback
        quality_feedback = self._build_quality_feedback(state)
        if quality_feedback:
            parts.append(quality_feedback)

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
        """
        if not content or not self.skill_registry:
            return [], []

        skill_ids = [
            "show-dont-tell",
            "info-dump-detector",
            "scene-texture",
            "dialogue-naturalness",
        ]
        all_findings: list[dict[str, Any]] = []

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
                    for f in data.get("findings", []):
                        if isinstance(f, dict):
                            all_findings.append(f)
            except Exception:
                logger.warning("Editor: advisory skill %s failed", skill_id, exc_info=True)
                continue

        if not all_findings:
            return [], []

        # Severity ordering: critical > high > medium > warning > info
        severity_order = {"critical": 0, "high": 1, "medium": 2, "warning": 3, "info": 4}
        all_findings.sort(
            key=lambda f: severity_order.get(f.get("severity", "info"), 5)
        )

        # Cap to avoid noise explosion
        capped = all_findings[:3]

        issues: list[str] = []
        suggestions: list[str] = []
        for finding in capped:
            code = finding.get("code", "")
            message = finding.get("message", "")
            suggestion = finding.get("suggestion", "")
            if message:
                issues.append(f"[v6.4质量信号] {code}: {message}")
            if suggestion:
                suggestions.append(f"[{code}] {suggestion}")

        return issues, suggestions

    def _fallback_rule_review(self, content: str, reason: str) -> EditorOutput:
        """Fallback review when live editor LLM cannot return a usable result."""
        dp_result = check_death_penalty_structured(content)
        has_content = bool(content.strip())
        passed = has_content and not dp_result.has_critical
        score = 88 if passed else 60
        issues = []
        if not has_content:
            issues.append("正文为空")
        if dp_result.has_critical:
            issues.extend([f"CRITICAL 死刑红线: {v}" for v in dp_result.violations])
        if reason:
            issues.append(f"AI 审核降级为规则检查: {reason}")

        # v6.4.4: Advisory quality signals even in fallback
        advisory_issues, advisory_suggestions = self._run_advisory_quality_check(content)
        issues = issues + advisory_issues

        return EditorOutput(
            pass_=passed,
            score=score,
            scores={
                "setting": 22 if passed else 15,
                "logic": 22 if passed else 15,
                "poison": 18 if passed else 10,
                "text": 13 if passed else 10,
                "pacing": 13 if passed else 10,
            },
            issues=issues,
            suggestions=advisory_suggestions if passed else (["请人工检查正文后再继续。"] + advisory_suggestions),
            revision_target=None if passed else "polisher",
            state_card={
                "summary": "AI 审核不可用，已完成规则兜底检查；请人工发布前复核。",
            } if passed else {},
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

        try:
            invoke_kwargs = {"max_tokens": 700} if use_compact_review else {}
            raw = self._invoke_json(
                messages,
                schema=EditorOutput,
                **invoke_kwargs,
            )
            output = EditorOutput(**raw)
            self.validate_output(output.model_dump())
        except Exception as e:
            if not use_compact_review:
                raise
            logger.warning("Editor: LLM review degraded to rule-based fallback: %s", e)
            output = self._fallback_rule_review(inputs.content, str(e))
            exec_events.append({
                "event_type": "fallback_used",
                "message": f"LLM 审核降级为规则兜底：{str(e)[:100]}",
                "payload": {"fallback_type": "rule_review", "reason": str(e)[:200]},
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
        """Step 4: Chapter seam check.

        Blocking seam issues can enter priority/blocking.
        Advisory seam issues do not hard-block.
        """
        seam_gate = evaluate_chapter_seam(
            self.repo, inputs.project_id, inputs.chapter_number, inputs.content
        )

        result = SeamCheckResult(
            passed=seam_gate.get("pass", True),
            blocking_count=len(seam_gate.get("blocking_issues", [])),
            advisory_count=len(seam_gate.get("advisory_issues", [])),
            blocking_issues=seam_gate.get("blocking_issues", []),
            advisory_issues=seam_gate.get("advisory_issues", []),
            suggestions=seam_gate.get("suggestions", []),
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

        # Run before_review skills
        self._run_before_review_skills(inputs, output)

        # Classify issues for revision_target (overrides LLM self-report)
        # But NOT if a specific gate (word count, seam) already set a target
        if not output.pass_ and output.issues:
            pre_classify_target = output.revision_target
            classify_result = classify_issues(output.issues, output.revision_target)
            gate_forced_target = bool(word_gate_details) or seam_result.blocking_count > 0
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
        )
        strategy_decision = classify_editor_result(policy_input)

        # LLM says fail, but policy says advisory — override without losing the input snapshot.
        if not output.pass_ and strategy_decision.category == "advisory":
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
            )

        if strategy_decision.pass_ and not output.pass_:
            logger.info("Editor strategy accepted advisory review: %s", strategy_decision.reason)
            output.pass_ = True
            output.revision_target = None
            output.suggestions = output.suggestions + [
                f"[v6.6策略] {strategy_decision.reason}；保留为发布前建议，不进入自动返修。"
            ]
        elif not strategy_decision.pass_:
            output.pass_ = False
            if not output.revision_target:
                output.revision_target = determine_revision_target(
                    death_penalty=dp_result.has_critical,
                    issues=output.issues,
                    llm_revision_target=output.revision_target,
                    quality_priority_count=quality_result.priority_count,
                    seam_blocking_count=seam_result.blocking_count,
                )
            strategy_note = f"[v6.6策略] {strategy_decision.reason}"
            if strategy_note not in output.issues:
                output.issues.append(strategy_note)

        # advisory_pass must NOT set revision_target
        if strategy_decision.decision_type == "advisory_pass":
            output.revision_target = None

        return EditorStrategyResult(
            decision=strategy_decision,
            policy_input=policy_input,
            word_gate_details=word_gate_details,
        )

    def _run_before_review_skills(self, inputs: EditorInputs, output: EditorOutput) -> None:
        """Run before_review skill hooks and append findings to output."""
        if not self.skill_registry:
            return

        skill_payload: dict[str, Any] = {"text": inputs.content, "chapter_number": inputs.chapter_number}
        try:
            bible_record = self.repo.get_style_bible(inputs.project_id)
            if bible_record:
                skill_payload["style_bible"] = bible_record.get("bible", {})
        except Exception:
            logger.warning("Editor: failed to load style_bible for skill payload", exc_info=True)

        project_skill_overrides = self._get_project_skill_overrides(inputs.project_id)

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

        for skill_item in before_review_hook.skill_results:
            skill_id = skill_item.get("skill_id", "")
            result = {"ok": skill_item.get("ok"), "error": skill_item.get("error"), "data": skill_item.get("data") or {}}

            if not result.get("ok"):
                logger.warning("Editor: skill %s failed: %s", skill_id, result.get("error"))
                continue

            if not result.get("data"):
                continue

            if skill_id == "ai-style-detector":
                ai_trace_score = result["data"].get("ai_trace_score", 0)
                ai_issues = result["data"].get("issues", [])
                if ai_issues:
                    ai_style_issues = [
                        f"[质量诊断建议] {issue.get('message', '')}"
                        for issue in ai_issues
                        if issue.get("message")
                    ]
                    output.issues = output.issues + ai_style_issues
                if ai_trace_score > 70:
                    note = f"[质量诊断建议] AI痕迹偏高 (评分: {ai_trace_score})"
                    if note not in output.suggestions:
                        output.suggestions.append(note)

            elif skill_id == "narrative-quality":
                narrative_score = result["data"].get("scores", {}).get("overall_score", 0)
                narrative_issues_list = result["data"].get("issues", [])
                suggestions = result["data"].get("suggestions", [])
                if narrative_issues_list:
                    narrative_issues = [
                        f"[质量诊断建议] {issue.get('message', '')}"
                        for issue in narrative_issues_list
                        if issue.get("message")
                    ]
                    output.issues = output.issues + narrative_issues
                if suggestions:
                    output.suggestions = output.suggestions + [
                        f"[质量诊断建议] {suggestion}" for suggestion in suggestions
                    ]
                if narrative_score < 50:
                    note = f"[质量诊断建议] 叙事质量偏低 (评分: {narrative_score})"
                    if note not in output.suggestions:
                        output.suggestions.append(note)

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

        # Prefer facts whose subject/key tokens appear in the chapter text (up to 30)
        chapter_lower = inputs.content.lower()

        def _relevance(fact: dict) -> int:
            tokens = str(fact.get("subject") or fact.get("fact_key") or "").lower().split()
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

    def _execute(self, state: FactoryState) -> dict[str, Any]:
        """Execute editor review — refactored to clear pipeline steps."""
        # Step 1: Load inputs
        inputs = self._load_editor_inputs(state)

        # Step 2: Call LLM
        output, exec_events = self._call_editor_llm(inputs, state)

        # Step 3: Quality diagnosis
        quality_result = self._run_quality_diagnosis(inputs, output)

        # Step 4: Chapter seam check
        seam_result = self._run_chapter_seam_check(inputs, output)

        # Step 4.5: Story facts compliance check (v6.6.14)
        compliance_result = self._run_story_facts_compliance(inputs)
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
            output.revision_target = output.revision_target or "author"

        # Step 5: Apply review strategy (THE single decision point)
        strategy_result = self._apply_review_strategy(
            output, quality_result, seam_result, inputs,
        )

        # Step 6: Persist artifacts
        review_id = self._persist_editor_artifacts(
            inputs, output, quality_result, seam_result,
            strategy_result, compliance_result,
        )

        # Step 7: Build state updates
        result = self._build_editor_state_updates(
            inputs, output, quality_result, seam_result,
            strategy_result, exec_events, compliance_result, review_id,
        )
        result["story_facts_compliance"] = compliance_result.to_dict()
        return result

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

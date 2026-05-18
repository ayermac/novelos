"""Editor Agent — performs five-dimension quality review."""

from __future__ import annotations

import json
import logging
from typing import Any

from ..models.schemas import EditorOutput
from ..models.state import ChapterStatus, FactoryState
from ..validators.chapter_checker import count_words, check_word_count_quality_gate, derive_word_target
from ..validators.death_penalty import check_death_penalty, check_death_penalty_structured
from ..validators.revision_classifier import classify_issues
from ..quality.editor_strategy import post_process_llm_decision
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
- 总分 >= 90 且无单项不及格 → 通过 (pass=true)
- 80-89 → 退回润色或局部返修
- 60-79 → 退回 Author 重写关键问题
- < 60 → 严重失败

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


class EditorAgent(BaseAgent):
    """Editor: five-dimension quality review."""

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
            parts.append(f"【本章正文】\n{chapter['content'][:8000]}")

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
            parts.append(f"【本章正文】\n{content[:3000]}")

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

    def _execute(self, state: FactoryState) -> dict[str, Any]:
        project_id = state["project_id"]
        chapter_number = state["chapter_number"]
        exec_events: list[dict] = []

        # Determine actual DB status for optimistic locking. Editor may be
        # invoked from either POLISHED or REVIEW (checkpoint recovery / retry).
        db_status = self.repo.get_chapter_status(project_id, chapter_number) or ChapterStatus.POLISHED.value
        expected_before = db_status if db_status in (ChapterStatus.POLISHED.value, ChapterStatus.REVIEW.value) else ChapterStatus.POLISHED.value
        rollback_status = ChapterStatus.POLISHED.value if expected_before == ChapterStatus.POLISHED.value else ChapterStatus.REVIEW.value

        use_compact_review = state.get("llm_mode") == "real" and is_configured_live_provider(self.llm)
        context = self._build_compact_review_context(state) if use_compact_review else self._build_v6_context(state)

        messages = [
            {"role": "system", "content": EDITOR_SYSTEM_PROMPT},
            {"role": "user", "content": f"项目ID: {project_id}\n章节号: {chapter_number}\n\n{context}\n\n请执行五层审校并评分。"},
        ]

        # Q2: Enhanced death penalty check with severity
        chapter = self._get_chapter_info(state)
        if not chapter:
            raise ValueError("Chapter not found in DB")

        content = chapter.get("content", "")

        try:
            invoke_kwargs = {"max_tokens": 700} if use_compact_review else {}
            raw = self.llm.invoke_json(
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
            output = self._fallback_rule_review(content, str(e))
            exec_events.append({
                "event_type": "fallback_used",
                "message": f"LLM 审核降级为规则兜底：{str(e)[:100]}",
                "payload": {"fallback_type": "rule_review", "reason": str(e)[:200]},
            })
        
        # v6.4.4: Advisory quality signals — append to review but do NOT change pass/fail/routing
        advisory_issues, advisory_suggestions = self._run_advisory_quality_check(content)
        if advisory_issues:
            output.issues = output.issues + advisory_issues
        if advisory_suggestions:
            output.suggestions = output.suggestions + advisory_suggestions

        dp_result = check_death_penalty_structured(content)
        if dp_result.has_critical:
            # Force low score and fail
            output.pass_ = False
            output.score = min(output.score, 50)
            output.issues = output.issues + [f"CRITICAL 死刑红线: {v}" for v in dp_result.violations]

        seam_gate = evaluate_chapter_seam(self.repo, project_id, chapter_number, content)
        seam_gate_details: dict[str, Any] = {}
        if not seam_gate.get("pass", True):
            output.pass_ = False
            output.score = min(output.score, 79)
            output.revision_target = "author"
            for issue in seam_gate.get("blocking_issues", [])[:3]:
                note = f"[章间衔接] {issue}"
                if note not in output.issues:
                    output.issues.append(note)
            for suggestion in seam_gate.get("suggestions", [])[:3]:
                note = f"[章间衔接修复] {suggestion}"
                if note not in output.suggestions:
                    output.suggestions.append(note)
            seam_gate_details = {
                "chapter_seam_fail": True,
                "message": "; ".join(seam_gate.get("blocking_issues", [])[:3]),
                "revision_target": "author",
                "agent": "editor",
                "workflow_run_id": state.get("workflow_run_id"),
            }
        else:
            for issue in seam_gate.get("advisory_issues", [])[:2]:
                note = f"[章间衔接建议] {issue}"
                if note not in output.suggestions:
                    output.suggestions.append(note)

        # Apply skills from config (before_review stage)
        if self.skill_registry:
            # v5.3.7: Inject style_bible into payload so style-bible-checker
            # can run against the project's style rules instead of silently skipping.
            skill_payload: dict[str, Any] = {"text": content, "chapter_number": chapter_number}
            try:
                bible_record = self.repo.get_style_bible(project_id)
                if bible_record:
                    skill_payload["style_bible"] = bible_record.get("bible", {})
            except Exception:
                logger.warning("Editor: failed to load style_bible for skill payload", exc_info=True)

            project_skill_overrides = self._get_project_skill_overrides(project_id)

            before_review_hook = run_agent_skills(
                repo=self.repo,
                skill_registry=self.skill_registry,
                project_id=project_id,
                chapter_number=chapter_number,
                agent="editor",
                stage="before_review",
                payload=skill_payload,
                project_overrides=project_skill_overrides,
                skill_type_hint="validator",
            )
            
            # Process skill results
            for skill_item in before_review_hook.skill_results:
                skill_id = skill_item.get("skill_id", "")
                result = {"ok": skill_item.get("ok"), "error": skill_item.get("error"), "data": skill_item.get("data") or {}}
                
                if not result.get("ok"):
                    logger.warning("Editor: skill %s failed: %s", skill_id, result.get("error"))
                    continue
                
                if not result.get("data"):
                    continue
                
                # Handle AIStyleDetector
                if skill_id == "ai-style-detector":
                    ai_trace_score = result["data"].get("ai_trace_score", 0)
                    ai_issues = result["data"].get("issues", [])
                    
                    # Add AI style issues as advisory audit notes. The v6.4/v6.6
                    # quality signal layer must not override the Editor's review
                    # score by itself; hard blocking is handled by death-penalty,
                    # word-count, and explicit seam gates.
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
                
                # Handle NarrativeQualityScorer
                elif skill_id == "narrative-quality":
                    narrative_score = result["data"].get("scores", {}).get("overall_score", 0)
                    narrative_issues_list = result["data"].get("issues", [])
                    suggestions = result["data"].get("suggestions", [])
                    
                    # Add narrative quality findings for audit/revision focus only.
                    # They should guide Polisher/Editor, not silently turn a
                    # passing review into an automatic revision loop.
                    if narrative_issues_list:
                        narrative_issues = [
                            f"[质量诊断建议] {issue.get('message', '')}"
                            for issue in narrative_issues_list
                            if issue.get("message")
                        ]
                        output.issues = output.issues + narrative_issues
                    
                    # Add suggestions
                    if suggestions:
                        output.suggestions = output.suggestions + [
                            f"[质量诊断建议] {suggestion}" for suggestion in suggestions
                        ]
                    
                    if narrative_score < 50:
                        note = f"[质量诊断建议] 叙事质量偏低 (评分: {narrative_score})"
                        if note not in output.suggestions:
                            output.suggestions.append(note)

        # Q7: Classify issues and determine revision_target (overrides LLM self-report)
        if not output.pass_ and output.issues:
            classify_result = classify_issues(output.issues, output.revision_target)
            output.revision_target = classify_result.dominant_target

        # R2: Run QualityHub final_gate BEFORE save_review to ensure consistency
        if output.pass_ and self.skill_registry:
            from ..quality.hub import QualityHub
            hub = QualityHub(self.repo, self.skill_registry)
            gate_result = hub.final_gate(project_id, chapter_number)
            
            if not gate_result.get("ok"):
                logger.error("Editor: QualityHub final_gate failed: %s", gate_result.get("error"))
                return {
                    "error": f"Editor: final_gate failed: {gate_result.get('error')}",
                    "chapter_status": state.get("chapter_status"),
                }
            
            gate_data = gate_result.get("data", {})
            if not gate_data.get("pass"):
                # Final gate not passed, merge gate results to output
                output.pass_ = False
                output.revision_target = gate_data.get("revision_target")
                
                # Add blocking issues to output
                blocking_issues = gate_data.get("blocking_issues", [])
                for issue in blocking_issues:
                    issue_msg = issue.get("message", str(issue))
                    if issue_msg not in output.issues:
                        output.issues.append(issue_msg)
                
                # Adjust score based on gate result
                output.score = min(output.score, int(gate_data.get("overall_score", 60)))
                
                logger.warning(
                    "Editor: final_gate not passed (score=%.2f), revision_target=%s",
                    gate_data.get("overall_score", 0),
                    output.revision_target
                )
            else:
                # Save quality report for passed gate
                try:
                    self.repo.save_quality_report(
                        project_id=project_id,
                        chapter_number=chapter_number,
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

        # v6.6.0: Word count quality gate (shared hard gate = 0.85;
        # 0.90 is advisory and should not trigger automatic revision alone).
        # Apply BEFORE save_review so persisted review matches the gate decision
        instruction = self._get_instruction(state)
        project = self.repo.get_project(project_id)
        word_target = derive_word_target(instruction, project)
        word_gate_passed, word_gate_msg = check_word_count_quality_gate(
            content, word_target, "editor"
        )
        word_gate_details = {}
        if not word_gate_passed:
            logger.warning("Editor: word count quality gate failed: %s", word_gate_msg)
            # Force fail and set revision_target to polisher (word count issue)
            output.pass_ = False
            output.revision_target = "polisher"
            output.issues = output.issues + [word_gate_msg]
            word_gate_details = {
                "word_count_fail": True,
                "message": word_gate_msg,
                "actual_word_count": count_words(content),
                "word_target": word_target,
                "agent": "editor",
                "workflow_run_id": state.get("workflow_run_id"),
            }

        # v6.6.1: Run deterministic quality diagnosis for strategy input
        quality_priority_count = 0
        quality_advisory_only = True
        quality_feedback_dict: dict[str, Any] | None = None
        if self.skill_registry:
            try:
                from ..quality.hub import QualityHub
                from ..quality.feedback_bridge import build_compact_feedback
                hub = QualityHub(self.repo, self.skill_registry)
                diagnose_result = hub.diagnose(content, context={
                    "project_id": project_id,
                    "chapter_number": chapter_number,
                })
                qf = build_compact_feedback(diagnose_result)
                quality_priority_count = len(qf.priority_findings)
                quality_advisory_only = not qf.priority_findings
                quality_feedback_dict = qf.to_dict()
                # Inject high-priority quality findings into suggestions for audit
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

        # v6.6.0/6.6.1: prevent high-score advisory-only reviews from entering
        # automatic revision loops. Hard gates above remain blocking.
        strategy_decision = post_process_llm_decision(
            output.pass_,
            output.score,
            output.issues,
            has_hard_word_fail=bool(word_gate_details),
            has_death_penalty=dp_result.has_critical,
            quality_priority_count=quality_priority_count,
            quality_advisory_only=quality_advisory_only,
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
                output.revision_target = "polisher"
            strategy_note = f"[v6.6策略] {strategy_decision.reason}"
            if strategy_note not in output.issues:
                output.issues.append(strategy_note)

        # Save review AFTER all gates have mutated output
        review_id = self.repo.save_review(
            project_id=project_id,
            chapter_id=chapter["id"],
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

        # Q7: Save classified issues to review
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

        # Q5: Write learned patterns when rejecting
        if not output.pass_:
            self._save_learned_patterns(project_id, chapter_number, output)

        # v6.1.1: Emit revision followup verified event after review on revision chapter
        prev_review = normalize_revision_review(state.get("_revision_review"))
        if prev_review:
            prev_issues = prev_review.get("issues") or []
            prev_issue_set = set(str(i).strip() for i in (prev_issues or []) if str(i).strip())
            current_issue_set = set(str(i).strip() for i in (output.issues or []) if str(i).strip())
            resolved = list(prev_issue_set - current_issue_set)[:10]
            unresolved = list(prev_issue_set & current_issue_set)[:10]
            exec_events.append({
                "event_type": "revision_followup_verified",
                "message": f"返修复核：{'通过' if output.pass_ else '未通过'}，已解决 {len(resolved)} 项，未解决 {len(unresolved)} 项",
                "status": "info" if output.pass_ else "warning",
                "payload": {
                    "source_review_id": prev_review.get("review_id"),
                    "resolved": resolved,
                    "unresolved": unresolved,
                    "partially_resolved": [],
                    "current_score": output.score,
                    "previous_score": prev_review.get("score"),
                },
            })

        # Advance chapter status FIRST to lock the transition; abort if stale
        if output.pass_:
            ok = self.repo.update_chapter_status(
                project_id, chapter_number, ChapterStatus.REVIEWED.value,
                expected_status=expected_before,
            )
            if not ok:
                logger.error("Editor: status advance %s→reviewed failed (stale state)", expected_before)
                return {"error": "Editor: stale state, status advance failed", "chapter_status": state.get("chapter_status")}

            try:
                # Save state card if provided
                state_card = output.state_card or self._build_minimal_state_card(content)
                state_ok = self.repo.save_chapter_state(
                    project_id, chapter_number, state_card,
                    summary=f"第{chapter_number}章状态卡 (score={output.score})",
                )
                if not state_ok:
                    self._compensate_status(
                        project_id, chapter_number,
                        ChapterStatus.REVIEWED.value, rollback_status,
                    )
                    return {"error": "Editor: save_chapter_state failed", "chapter_status": rollback_status}

                # Save artifact (bind to workflow run for isolation)
                workflow_run_id = state.get("workflow_run_id")
                artifact_payload = output.model_dump()
                if quality_feedback_dict:
                    artifact_payload["_quality_feedback"] = quality_feedback_dict
                self.repo.save_artifact(
                    project_id, chapter_number, "editor", "review",
                    content_json=artifact_payload,
                    workflow_run_id=workflow_run_id,
                )
            except Exception as e:
                self._compensate_status(
                    project_id, chapter_number,
                    ChapterStatus.REVIEWED.value, rollback_status,
                )
                return {"error": f"Editor: write failed: {e}", "chapter_status": rollback_status}

            new_status = ChapterStatus.REVIEWED.value
            new_stage = "reviewed"
        else:
            # Check circuit breaker
            retry_count = self.repo.get_chapter_retry_count(project_id, chapter_number)
            max_retries = state.get("max_retries", 3)

            if retry_count >= max_retries:
                ok = self.repo.update_chapter_status(
                    project_id, chapter_number, ChapterStatus.BLOCKING.value,
                    expected_status=expected_before,
                )
                if not ok:
                    logger.error("Editor: status advance %s→blocking failed (stale state)", expected_before)
                    return {"error": "Editor: stale state, status advance failed", "chapter_status": state.get("chapter_status")}

                try:
                    # Send message for human intervention
                    self.repo.send_message(
                        project_id, "editor", "dispatcher", "ESCALATE",
                        {"reason": f"Chapter {chapter_number} reached max retries ({retry_count})"},
                        priority="urgent", chapter_number=chapter_number,
                    )
                    # Save artifact (bind to workflow run for isolation)
                    workflow_run_id = state.get("workflow_run_id")
                    artifact_payload = output.model_dump()
                    if quality_feedback_dict:
                        artifact_payload["_quality_feedback"] = quality_feedback_dict
                    self.repo.save_artifact(
                        project_id, chapter_number, "editor", "review",
                        content_json=artifact_payload,
                        workflow_run_id=workflow_run_id,
                    )
                except Exception as e:
                    self._compensate_status(
                        project_id, chapter_number,
                        ChapterStatus.BLOCKING.value, rollback_status,
                    )
                    return {"error": f"Editor: write failed: {e}", "chapter_status": rollback_status}

                new_status = ChapterStatus.BLOCKING.value
                new_stage = "blocking"
            else:
                retry_agent = output.revision_target or "author"
                ok = self.repo.update_chapter_status(
                    project_id, chapter_number, ChapterStatus.REVISION.value,
                    expected_status=expected_before,
                )
                if not ok:
                    logger.error("Editor: status advance %s→revision failed (stale state)", expected_before)
                    return {"error": "Editor: stale state, status advance failed", "chapter_status": state.get("chapter_status")}

                try:
                    revise_task_id = self.repo.start_task(
                        project_id,
                        chapter_number,
                        "revise",
                        retry_agent,
                        workflow_run_id=state.get("workflow_run_id"),
                    )
                    self.repo.complete_task(revise_task_id, success=True)
                    # Send message to responsible agent if not author
                    if retry_agent != "author":
                        self.repo.send_message(
                            project_id, "editor", retry_agent, "FLAG_ISSUE",
                            {"issues": output.issues[:3], "chapter": chapter_number},
                            chapter_number=chapter_number,
                        )
                    # Save artifact (bind to workflow run for isolation)
                    workflow_run_id = state.get("workflow_run_id")
                    artifact_payload = output.model_dump()
                    if quality_feedback_dict:
                        artifact_payload["_quality_feedback"] = quality_feedback_dict
                    self.repo.save_artifact(
                        project_id, chapter_number, "editor", "review",
                        content_json=artifact_payload,
                        workflow_run_id=workflow_run_id,
                    )
                except Exception as e:
                    self._compensate_status(
                        project_id, chapter_number,
                        ChapterStatus.REVISION.value, rollback_status,
                    )
                    return {"error": f"Editor: write failed: {e}", "chapter_status": rollback_status}

                new_status = ChapterStatus.REVISION.value
                new_stage = "revision"
                retry_count = retry_count + 1

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
            "chapter_status": new_status,
            "current_stage": new_stage,
            "retry_count": retry_count if not output.pass_ else state.get("retry_count", 0),
            "requires_human": new_status == ChapterStatus.BLOCKING.value,
            "quality_gate": {
                "pass": output.pass_,
                "score": output.score,
                "revision_target": output.revision_target,
                **word_gate_details,
                **seam_gate_details,
            },
            "_exec_events": exec_events,
        }

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

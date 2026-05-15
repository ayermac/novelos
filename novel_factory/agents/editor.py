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
from ..skills.registry import SkillRegistry
from ..llm.openai_compatible import LLMTimeoutError, OutputValidationError
from ..llm.provider import is_configured_live_provider
from .base import BaseAgent
from .revision_context import normalize_revision_review
from .skill_hooks import run_agent_skills

logger = logging.getLogger(__name__)

EDITOR_SYSTEM_PROMPT = """你是网文工厂的质检（Editor），是读者毒抗的最后一道防线。

五层审校维度：
1. 设定一致性 (满分25) — 与世界观、角色、前文一致
2. 逻辑漏洞 (满分25) — 无硬伤、无降智
3. 毒点检测 (满分20) — 无读者厌恶套路
4. 文字质量 (满分15) — 无AI烂词、无说教
5. 爽点钩子 (满分15) — 有高潮、有悬念

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
- 文风、句式、节奏、AI 痕迹问题 → "polisher"
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
        title_contract = self._get_title_contract_context(state["project_id"])
        if title_contract:
            parts.append(title_contract)

        # Chapter content
        chapter = self._get_chapter_info(state)
        if chapter and chapter.get("content"):
            parts.append(f"【本章正文】\n{chapter['content'][:8000]}")

        # Instruction
        instruction = self._get_instruction(state)
        if instruction:
            parts.append(f"【写作指令】\n目标: {instruction.get('objective', '')}\n"
                         f"关键事件: {instruction.get('key_events', '')}\n"
                         f"埋设伏笔: {instruction.get('plots_to_plant', '[]')}\n"
                         f"兑现伏笔: {instruction.get('plots_to_resolve', '[]')}")

        # Previous state card
        prev_state = self._get_prev_state_card(state)
        if prev_state:
            parts.append(f"【上一章状态卡】\n{json.dumps(prev_state.get('state_data', {}), ensure_ascii=False, indent=2)}")

        # Characters
        characters = self.repo.get_characters(state["project_id"])
        if characters:
            char_str = "\n".join(f"- {c['name']}({c['role']}): {c.get('description', '')}" for c in characters[:10])
            parts.append(f"【角色设定】\n{char_str}")

        # v4.0: Style Bible injection
        style_ctx = self._get_style_bible_context(state["project_id"], "editor")
        if style_ctx:
            parts.append(style_ctx)

        return "\n\n".join(parts)

    def _build_compact_review_context(self, state: FactoryState) -> str:
        """Build a short review prompt for live LLM calls."""
        parts = []

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

        characters = self.repo.get_characters(state["project_id"])
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
            suggestions=[] if passed else ["请人工检查正文后再继续。"],
            revision_target=None if passed else "polisher",
            state_card={
                "summary": "AI 审核不可用，已完成规则兜底检查；请人工发布前复核。",
            } if passed else {},
        )

    def _execute(self, state: FactoryState) -> dict[str, Any]:
        project_id = state["project_id"]
        chapter_number = state["chapter_number"]
        exec_events: list[dict] = []

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
        except (LLMTimeoutError, OutputValidationError) as e:
            if not use_compact_review:
                raise
            logger.warning("Editor: LLM review degraded to rule-based fallback: %s", e)
            output = self._fallback_rule_review(content, str(e))
            exec_events.append({
                "event_type": "fallback_used",
                "message": f"LLM 审核降级为规则兜底：{str(e)[:100]}",
                "payload": {"fallback_type": "rule_review", "reason": str(e)[:200]},
            })
        
        dp_result = check_death_penalty_structured(content)
        if dp_result.has_critical:
            # Force low score and fail
            output.pass_ = False
            output.score = min(output.score, 50)
            output.issues = output.issues + [f"CRITICAL 死刑红线: {v}" for v in dp_result.violations]

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
                    
                    # Add AI style issues to output
                    if ai_issues:
                        ai_style_issues = [issue.get("message", "") for issue in ai_issues if issue.get("message")]
                        output.issues = output.issues + ai_style_issues
                    
                    # Adjust score if AI trace is high
                    if ai_trace_score > 70:
                        output.score = min(output.score, 75)
                        if "AI痕迹过重" not in output.issues:
                            output.issues.append(f"AI痕迹过重 (评分: {ai_trace_score})")
                
                # Handle NarrativeQualityScorer
                elif skill_id == "narrative-quality":
                    narrative_score = result["data"].get("scores", {}).get("overall_score", 0)
                    narrative_issues_list = result["data"].get("issues", [])
                    suggestions = result["data"].get("suggestions", [])
                    
                    # Add narrative issues to output
                    if narrative_issues_list:
                        narrative_issues = [issue.get("message", "") for issue in narrative_issues_list if issue.get("message")]
                        output.issues = output.issues + narrative_issues
                    
                    # Add suggestions
                    if suggestions:
                        output.suggestions = output.suggestions + suggestions
                    
                    # Adjust score if narrative quality is low
                    if narrative_score < 50:
                        output.score = min(output.score, 70)
                        if "叙事质量不足" not in output.issues:
                            output.issues.append(f"叙事质量不足 (评分: {narrative_score})")

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

        # v5.3.0: Word count quality gate (Editor threshold = 0.90)
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
                expected_status=ChapterStatus.POLISHED.value,
            )
            if not ok:
                logger.error("Editor: status advance polished→reviewed failed (stale state)")
                return {"error": "Editor: stale state, status advance failed", "chapter_status": state.get("chapter_status")}

            try:
                # Save state card if provided
                if output.state_card:
                    state_ok = self.repo.save_chapter_state(
                        project_id, chapter_number, output.state_card,
                        summary=f"第{chapter_number}章状态卡 (score={output.score})",
                    )
                    if not state_ok:
                        self._compensate_status(
                            project_id, chapter_number,
                            ChapterStatus.REVIEWED.value, ChapterStatus.POLISHED.value,
                        )
                        return {"error": "Editor: save_chapter_state failed", "chapter_status": ChapterStatus.POLISHED.value}

                # Save artifact (bind to workflow run for isolation)
                workflow_run_id = state.get("workflow_run_id")
                self.repo.save_artifact(
                    project_id, chapter_number, "editor", "review",
                    content_json=output.model_dump(),
                    workflow_run_id=workflow_run_id,
                )
            except Exception as e:
                self._compensate_status(
                    project_id, chapter_number,
                    ChapterStatus.REVIEWED.value, ChapterStatus.POLISHED.value,
                )
                return {"error": f"Editor: write failed: {e}", "chapter_status": ChapterStatus.POLISHED.value}

            new_status = ChapterStatus.REVIEWED.value
            new_stage = "reviewed"
        else:
            # Check circuit breaker
            retry_count = self.repo.get_chapter_retry_count(project_id, chapter_number)
            max_retries = state.get("max_retries", 3)

            if retry_count >= max_retries:
                ok = self.repo.update_chapter_status(
                    project_id, chapter_number, ChapterStatus.BLOCKING.value,
                    expected_status=ChapterStatus.POLISHED.value,
                )
                if not ok:
                    logger.error("Editor: status advance polished→blocking failed (stale state)")
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
                    self.repo.save_artifact(
                        project_id, chapter_number, "editor", "review",
                        content_json=output.model_dump(),
                        workflow_run_id=workflow_run_id,
                    )
                except Exception as e:
                    self._compensate_status(
                        project_id, chapter_number,
                        ChapterStatus.BLOCKING.value, ChapterStatus.POLISHED.value,
                    )
                    return {"error": f"Editor: write failed: {e}", "chapter_status": ChapterStatus.POLISHED.value}

                new_status = ChapterStatus.BLOCKING.value
                new_stage = "blocking"
            else:
                retry_agent = output.revision_target or "author"
                ok = self.repo.update_chapter_status(
                    project_id, chapter_number, ChapterStatus.REVISION.value,
                    expected_status=ChapterStatus.POLISHED.value,
                )
                if not ok:
                    logger.error("Editor: status advance polished→revision failed (stale state)")
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
                    self.repo.save_artifact(
                        project_id, chapter_number, "editor", "review",
                        content_json=output.model_dump(),
                        workflow_run_id=workflow_run_id,
                    )
                except Exception as e:
                    self._compensate_status(
                        project_id, chapter_number,
                        ChapterStatus.REVISION.value, ChapterStatus.POLISHED.value,
                    )
                    return {"error": f"Editor: write failed: {e}", "chapter_status": ChapterStatus.POLISHED.value}

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
            },
            "_exec_events": exec_events,
        }

    def validate_output(self, output: dict) -> None:
        parsed = EditorOutput(**output)
        if parsed.revision_target and parsed.revision_target not in ("author", "polisher", "planner", None):
            raise ValueError(f"Invalid revision_target: {parsed.revision_target}")

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

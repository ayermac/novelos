"""Polisher Agent — polishes chapter content without changing facts."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from ..context.builder import ContextBuilder
from ..models.schemas import PolisherOutput
from ..models.state import ChapterStatus, FactoryState
from ..validators.chapter_checker import validate_chapter_output, check_word_count_quality_gate, derive_word_target
from ..validators.death_penalty import check_death_penalty, check_death_penalty_structured, has_critical_violation
from ..validators.fact_lock import check_fact_integrity, extract_fact_lock
from ..skills.registry import SkillRegistry
from .base import BaseAgent

logger = logging.getLogger(__name__)

POLISHER_SYSTEM_PROMPT = """你是网文工厂的润色编辑（Polisher），负责清理草稿中的问题。

职责：
1. 清理 AI 味表达、模板化句式和陈词滥调
2. 优化语言质感、对话节奏、场景转换和动作描写
3. 保持剧情事实、伏笔、角色动机和数值状态不变
4. 输出润色报告，说明改动范围和风险

核心约束：
- 不改变剧情事实
- 不新增或删除关键事件
- 不改写 Planner 的伏笔计划
- 不替 Editor 做通过/退回判断

输出格式：严格按 JSON 格式输出，包含：
- content: 润色后的正文
- fact_change_risk: 事实变更风险（none/low/high，必须为 none）
- changed_scope: 改动范围列表（如 sentence, dialogue, rhythm）
- summary: 润色摘要"""


class PolisherAgent(BaseAgent):
    """Polisher: polishes chapter content without changing facts."""

    agent_id = "polisher"

    def __init__(self, repo, llm, skill_registry: SkillRegistry | None = None):
        """Initialize Polisher agent.
        
        Args:
            repo: Repository instance.
            llm: LLM provider instance.
            skill_registry: Optional SkillRegistry for skill execution.
        """
        super().__init__(repo, llm)
        self.skill_registry = skill_registry

    def build_context(self, state: FactoryState) -> str:
        """Build context using ContextBuilder.build_for_polisher().

        This ensures fact_lock, death_penalty, instruction, learned_patterns,
        and best_practices are injected into the actual LLM messages.
        """
        builder = ContextBuilder(self.repo)
        return builder.build_for_polisher(state["project_id"], state["chapter_number"])

    def _execute(self, state: FactoryState) -> dict[str, Any]:
        project_id = state["project_id"]
        chapter_number = state["chapter_number"]

        context = self.build_context(state)

        messages = [
            {"role": "system", "content": POLISHER_SYSTEM_PROMPT},
            {"role": "user", "content": f"项目ID: {project_id}\n章节号: {chapter_number}\n\n{context}\n\n请润色以上草稿，注意不要改变任何剧情事实。"},
        ]

        try:
            raw = self.llm.invoke_json(messages, schema=PolisherOutput)
            output = PolisherOutput(**raw)
        except Exception as e:
            logger.error("Polisher LLM call failed: %s", e)
            return {"error": f"Polisher failed: {e}", "chapter_status": state.get("chapter_status")}

        self.validate_output(output.model_dump())

        # Q8: Fact lock hard verification — BEFORE status advance
        original_content = ""
        chapter = self._get_chapter_info(state)
        if chapter:
            original_content = chapter.get("content", "") or ""

        instruction = self._get_instruction(state)
        prev_state_card = self._get_prev_state_card(state)
        fact_lock = extract_fact_lock(instruction, prev_state_card)

        # Apply skills from config (after_llm stage)
        polished_content = output.content
        if self.skill_registry:
            after_llm_result = self.skill_registry.run_skills_for_agent(
                agent="polisher",
                stage="after_llm",
                payload={
                    "text": polished_content,
                    "fact_lock": {"key_events": [f.content for f in fact_lock] if fact_lock else []},
                },
            )
            
            # Process skill results
            for skill_item in after_llm_result:
                skill_id = skill_item.get("skill_id", "")
                result = skill_item.get("result", {})
                
                # Save skill run to database
                try:
                    self.repo.save_skill_run(
                        project_id=project_id,
                        skill_id=skill_id,
                        skill_type="transform",
                        ok=result.get("ok", False),
                        error=result.get("error"),
                        input_json={"text": polished_content[:500]},  # Truncate for storage
                        output_json=result.get("data"),
                        chapter_number=chapter_number,
                    )
                except Exception as e:
                    logger.warning("Polisher: failed to save skill_run: %s", e)
                
                # Check if critical skill failed
                if not result.get("ok"):
                    logger.error("Polisher: critical skill %s failed: %s", skill_id, result.get("error"))
                    # Critical skills (humanizer-zh, ai-style-detector) must block on failure
                    if skill_id in ("humanizer-zh", "ai-style-detector"):
                        return {
                            "error": f"Polisher: critical skill {skill_id} failed: {result.get('error')}",
                            "chapter_status": state.get("chapter_status"),
                        }
                
                # Handle HumanizerZh skill (transform skill)
                if skill_id == "humanizer-zh" and result.get("ok") and result.get("data"):
                    polished_content = result["data"].get("humanized_text", polished_content)

        if fact_lock:
            integrity = check_fact_integrity(original_content, polished_content, fact_lock)
            if integrity.risk != "none":
                missing = [f.content for f in integrity.missing_facts]
                changed = [f.content for f in integrity.changed_facts]
                logger.error(
                    "Polisher: fact lock verification FAILED — "
                    "missing=%s changed=%s risk=%s",
                    missing, changed, integrity.risk,
                )
                return {
                    "error": (
                        f"Polisher: fact lock verification failed "
                        f"(risk={integrity.risk}, "
                        f"missing={missing}, changed={changed})"
                    ),
                    "chapter_status": state.get("chapter_status"),
                }

        # v5.3.0: Word count quality gate
        instruction = self._get_instruction(state)
        project = self.repo.get_project(project_id)
        word_target = derive_word_target(instruction, project)
        word_gate_passed, word_gate_msg = check_word_count_quality_gate(
            polished_content, word_target, "polisher"
        )
        if not word_gate_passed:
            logger.warning("Polisher: word count quality gate failed: %s", word_gate_msg)
            return {
                "error": f"字数质量门未通过: {word_gate_msg}",
                "chapter_status": state.get("chapter_status"),
                "quality_gate": {
                    "pass": False,
                    "revision_target": "polisher",
                    "word_count_fail": True,
                    "message": word_gate_msg,
                },
            }

        # Apply skills from config (before_save stage)
        if self.skill_registry:
            before_save_result = self.skill_registry.run_skills_for_agent(
                agent="polisher",
                stage="before_save",
                payload={"text": polished_content},
            )
            
            # Check AI trace score from AIStyleDetector
            for skill_item in before_save_result:
                skill_id = skill_item.get("skill_id", "")
                result = skill_item.get("result", {})
                
                # Save skill run to database
                try:
                    self.repo.save_skill_run(
                        project_id=project_id,
                        skill_id=skill_id,
                        skill_type="validator",
                        ok=result.get("ok", False),
                        error=result.get("error"),
                        input_json={"text": polished_content[:500]},  # Truncate for storage
                        output_json=result.get("data"),
                        chapter_number=chapter_number,
                    )
                except Exception as e:
                    logger.warning("Polisher: failed to save skill_run: %s", e)
                
                # Check if critical skill failed
                if not result.get("ok"):
                    logger.error("Polisher: critical skill %s failed: %s", skill_id, result.get("error"))
                    # Critical skills must block on failure
                    if skill_id in ("humanizer-zh", "ai-style-detector"):
                        return {
                            "error": f"Polisher: critical skill {skill_id} failed: {result.get('error')}",
                            "chapter_status": state.get("chapter_status"),
                        }
                
                if skill_id == "ai-style-detector" and result.get("ok") and result.get("data"):
                    ai_trace_score = result["data"].get("ai_trace_score", 0)
                    if ai_trace_score > 70:  # TODO: move to config
                        logger.error(
                            "Polisher: AI trace score too high: %d > 70",
                            ai_trace_score
                        )
                        return {
                            "error": f"Polisher: AI trace score too high ({ai_trace_score} > 70)",
                            "chapter_status": state.get("chapter_status"),
                        }

        # Advance status FIRST to lock the transition; abort if stale.
        # Normal flow polishes a drafted chapter; revision flow polishes a
        # chapter currently marked revision.
        current_status = state.get("chapter_status")
        expected_status = (
            ChapterStatus.REVISION.value
            if current_status == ChapterStatus.REVISION.value
            else ChapterStatus.DRAFTED.value
        )
        ok = self.repo.update_chapter_status(
            project_id, chapter_number, ChapterStatus.POLISHED.value,
            expected_status=expected_status,
        )
        if not ok:
            logger.error("Polisher: status advance %s→polished failed (stale state)", expected_status)
            return {"error": "Polisher: stale state, status advance failed", "chapter_status": state.get("chapter_status")}

        # Save polished content (only after status advance succeeds)
        try:
            content_ok = self.repo.save_chapter_content(project_id, chapter_number, polished_content)
            if not content_ok:
                self._compensate_status(
                    project_id, chapter_number,
                    ChapterStatus.POLISHED.value, expected_status,
                )
                return {"error": "Polisher: save_chapter_content failed", "chapter_status": expected_status}

            # Save version
            self.repo.save_version(
                project_id, chapter_number, polished_content,
                created_by="polisher",
                notes=output.summary,
            )

            # Save polish report
            self.repo.save_polish_report(
                project_id=project_id,
                chapter_number=chapter_number,
                fact_change_risk=output.fact_change_risk,
                style_changes=output.changed_scope if "style" in str(output.changed_scope) else [],
                summary=output.summary,
            )

            # Save artifact
            self.repo.save_artifact(
                project_id, chapter_number, "polisher", "polished_draft",
                content_json=output.model_dump(),
            )
        except Exception as e:
            self._compensate_status(
                project_id, chapter_number,
                ChapterStatus.POLISHED.value, expected_status,
            )
            return {"error": f"Polisher: write failed: {e}", "chapter_status": expected_status}

        return {
            "chapter_status": ChapterStatus.POLISHED.value,
            "current_stage": "polished",
        }

    def validate_output(self, output: dict) -> None:
        parsed = PolisherOutput(**output)
        # Strict: fact_change_risk must be "none"
        if parsed.fact_change_risk != "none":
            raise ValueError(
                f"Polisher fact_change_risk must be 'none', got '{parsed.fact_change_risk}'. "
                "Polisher must NOT change plot facts."
            )
        # Q2: Enhanced death penalty with severity
        dp_result = check_death_penalty_structured(parsed.content)
        if dp_result.has_critical:
            raise ValueError(
                f"Polisher 输出包含 CRITICAL 死刑红线: {', '.join(dp_result.violations)}"
            )
        if dp_result.violations:
            raise ValueError(f"Polisher 输出包含死刑红线词汇: {', '.join(dp_result.violations)}")

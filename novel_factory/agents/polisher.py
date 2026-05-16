"""Polisher Agent — polishes chapter content without changing facts."""

from __future__ import annotations

import json
import logging
import re
import statistics
import time
from typing import Any

from ..context.builder import ContextBuilder
from ..models.schemas import PolisherOutput
from ..models.state import ChapterStatus, FactoryState
from ..validators.chapter_checker import validate_chapter_output, check_word_count_quality_gate, derive_word_target
from ..validators.death_penalty import check_death_penalty, check_death_penalty_structured, has_critical_violation
from ..validators.fact_lock import check_fact_integrity, extract_fact_lock
from ..skills.registry import SkillRegistry
from ..agent_runtime.base import BaseAgent
from ..agent_runtime.chapter_text import default_chapter_title, ensure_chapter_heading, strip_chapter_heading
from ..agent_runtime.revision_context import normalize_revision_review, revision_feedback_block
from ..agent_runtime.skill_hooks import run_agent_skills

logger = logging.getLogger(__name__)

POLISHER_SYSTEM_PROMPT = """你是网文工厂的润色编辑（Polisher），负责将草稿改写成"像人写过"的小说段落。

职责边界（不可逾越）：
1. 保留剧情事实、关键事件、伏笔和角色动机——不得改写剧情走向
2. 不新增或删除关键事件
3. 不改写 Planner 的伏笔计划
4. 不替 Editor 做通过/退回判断

润色重点（v6.4.2）：
1. 对白自然化
   - 减少功能性问答式对白，让对白承载目的、遮掩、试探或情绪摩擦
   - 加入语气词、省略、打断、反问，避免所有角色使用同一套书面语
   - 不同角色的句式长度、用词习惯应有差异
2. 场景质感增强
   - 补充动作细节、环境反馈和感官线索（光影、声音、温度、气味）
   - 将抽象描述改为具体动作，避免形容词堆砌
   - 优先强化已有感官线索；必要时只补最小动作/环境反馈，不硬加无关描写
3. 节奏变化
   - 打破均匀段落，长短句交替
   - 紧张场景使用短句/短段，描写场景可用长句但避免超长句（>40字）
   - 避免连续多个段落长度相近
4. 减少 AI 味
   - 删减总结句（"综上所述/总之/简单来说"）
   - 将直白心理解释（"他感到愤怒"）改为动作或神态（"他攥紧拳头，指节发白"）
   - 删除宏大空泛判断（"这一刻，他知道，一切都将改变"）

输出格式：严格按 JSON 格式输出，包含：
- content: 润色后的正文
- fact_change_risk: 事实变更风险（none/low/high，必须为 none）
- changed_scope: 改动范围列表（如 sentence, dialogue, rhythm, scene_texture）
- summary: 润色摘要"""


class PolisherAgent(BaseAgent):
    """Polisher: polishes chapter content without changing facts."""

    agent_id = "polisher"

    def __init__(self, repo, llm, skill_registry: SkillRegistry | None = None, **kwargs):
        """Initialize Polisher agent.

        Args:
            repo: Repository instance.
            llm: LLM provider instance.
            skill_registry: Optional SkillRegistry for skill execution.
        """
        super().__init__(repo, llm, skill_registry=skill_registry, **kwargs)
        self.skill_registry = skill_registry

    def build_context(self, state: FactoryState) -> str:
        """Build context using ContextBuilder.build_for_polisher().

        This ensures fact_lock, death_penalty, instruction, learned_patterns,
        and best_practices are injected into the actual LLM messages.
        v6.4.2: Appends polishing writing reminders derived from quality diagnosis dimensions.
        """
        builder = ContextBuilder(self.repo)
        title_contract = self._get_title_contract_context(state["project_id"])
        context = builder.build_for_polisher(state["project_id"], state["chapter_number"])
        parts = []
        if title_contract:
            parts.append(title_contract)
        chapter = self._get_chapter_info(state)
        if state.get("chapter_status") == ChapterStatus.REVISION.value or (
            chapter and chapter.get("status") == ChapterStatus.REVISION.value
        ):
            review = state.get("_revision_review")
            if not review and chapter:
                review = self.repo.get_latest_review(state["project_id"], chapter["id"])
            feedback = revision_feedback_block(review)
            if feedback:
                parts.append(feedback)
        parts.append(context)

        # v6.4.2: Inject quality-diagnosis-derived writing reminders
        parts.append(
            "【润色写作提醒】\n"
            "1. 对白自然化：检查是否有功能性问答，尝试加入语气词、打断、省略或反问；"
            "让不同角色的句式长度和用词习惯有差异。\n"
            "2. 场景质感：优先强化已有感官线索；必要时只补最小动作/环境反馈，不硬加无关描写；"
            "将抽象描述（\"他很紧张\"）改为具体动作（\"他攥紧拳头\"）。\n"
            "3. 节奏变化：避免连续多个段落长度相近；紧张处用短句，描写处可用长句但避免>40字。\n"
            "4. 去AI味：删除总结句（\"总之/简单来说\"）、直白心理解释和宏大空泛判断。\n"
            "5. Show, Don't Tell：将\"感到/觉得/意识到/明白\"等直白情绪词改为动作或神态。"
        )
        return "\n\n".join(parts)

    def _execute(self, state: FactoryState) -> dict[str, Any]:
        project_id = state["project_id"]
        chapter_number = state["chapter_number"]
        exec_events: list[dict] = []

        context = self._build_v6_context(state)

        # v6.1.1: Emit revision context loaded event for revision chapters
        current_status = state.get("chapter_status", "")
        if current_status == ChapterStatus.REVISION.value:
            revision_review = normalize_revision_review(state.get("_revision_review"))
            if revision_review:
                issues = revision_review.get("issues") or []
                suggestions = revision_review.get("suggestions") or []
                exec_events.append({
                    "event_type": "revision_context_loaded",
                    "message": f"返修依据：评分 {revision_review.get('score', '?')}，{len(issues)} 个问题，{len(suggestions)} 条建议",
                    "payload": {
                        "review_id": revision_review.get("review_id"),
                        "score": revision_review.get("score"),
                        "revision_target": revision_review.get("revision_target"),
                        "issues": issues[:10],
                        "suggestions": suggestions[:10],
                    },
                })

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

        # v6.1: Compute diff summary before skills may modify content
        from ..validators.chapter_checker import count_words as _count_words
        original_body = strip_chapter_heading(original_content, chapter_number, (chapter or {}).get("title"))
        original_wc = _count_words(original_body)

        # Apply skills from config (after_llm stage)
        polished_content = output.content
        if self.skill_registry:
            project_skill_overrides = self._get_project_skill_overrides(project_id)
            after_llm_hook = run_agent_skills(
                repo=self.repo,
                skill_registry=self.skill_registry,
                project_id=project_id,
                chapter_number=chapter_number,
                agent="polisher",
                stage="after_llm",
                payload={
                    "text": polished_content,
                    "fact_lock": {"key_events": [f.content for f in fact_lock] if fact_lock else []},
                },
                project_overrides=project_skill_overrides,
                skill_type_hint="transform",
                fail_closed_ids={"humanizer-zh", "ai-style-detector"},
            )
            if not after_llm_hook.ok:
                return {
                    "error": f"Polisher: critical skill failed: {after_llm_hook.blocking_error}",
                    "chapter_status": state.get("chapter_status"),
                }

            for transform in after_llm_hook.transforms:
                if transform.get("skill_id") == "humanizer-zh":
                    polished_content = transform.get("content", polished_content)

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

        chapter_title = (chapter or {}).get("title") or default_chapter_title(chapter_number)
        polished_content = ensure_chapter_heading(polished_content, chapter_title, chapter_number)

        # v5.3.0: Word count quality gate
        instruction = self._get_instruction(state)
        project = self.repo.get_project(project_id)
        word_target = derive_word_target(instruction, project)
        word_gate_passed, word_gate_msg = check_word_count_quality_gate(
            polished_content, word_target, "polisher"
        )
        if not word_gate_passed:
            logger.warning("Polisher: word count quality gate failed: %s", word_gate_msg)
            # P1: Record actual word count and target for traceability
            from ..validators.chapter_checker import count_words
            actual_wc = count_words(polished_content)
            return {
                "error": f"字数质量门未通过: {word_gate_msg}",
                "chapter_status": state.get("chapter_status"),
                "quality_gate": {
                    "pass": False,
                    "revision_target": "polisher",
                    "word_count_fail": True,
                    "message": word_gate_msg,
                    "actual_word_count": actual_wc,
                    "word_target": word_target,
                    "agent": "polisher",
                    "workflow_run_id": state.get("workflow_run_id"),
                },
            }

        # Apply skills from config (before_save stage)
        if self.skill_registry:
            project_skill_overrides = self._get_project_skill_overrides(project_id)
            before_save_hook = run_agent_skills(
                repo=self.repo,
                skill_registry=self.skill_registry,
                project_id=project_id,
                chapter_number=chapter_number,
                agent="polisher",
                stage="before_save",
                payload={"text": polished_content},
                project_overrides=project_skill_overrides,
                skill_type_hint="validator",
                fail_closed_ids={"humanizer-zh", "ai-style-detector"},
            )
            if not before_save_hook.ok:
                return {
                    "error": f"Polisher: critical skill failed: {before_save_hook.blocking_error}",
                    "chapter_status": state.get("chapter_status"),
                }

            # Check AI trace score from AIStyleDetector
            for skill_item in before_save_hook.skill_results:
                if skill_item.get("skill_id") == "ai-style-detector" and skill_item.get("ok") and skill_item.get("data"):
                    ai_trace_score = skill_item["data"].get("ai_trace_score", 0)
                    exec_events.append({
                        "event_type": "skill_completed",
                        "message": f"AI 痕迹检查{'通过' if ai_trace_score <= 70 else '未通过'}（评分: {ai_trace_score}）",
                        "status": "info" if ai_trace_score <= 70 else "error",
                        "payload": {"skill_id": "ai-style-detector", "ai_trace_score": ai_trace_score},
                    })
                    if ai_trace_score > 70:  # TODO: move to config
                        logger.error(
                            "Polisher: AI trace score too high: %d > 70",
                            ai_trace_score
                        )
                        return {
                            "error": f"Polisher: AI trace score too high ({ai_trace_score} > 70)",
                            "chapter_status": state.get("chapter_status"),
                        }

        # v6.4.2: Deterministic self-check warnings (do NOT affect routing)
        warnings = self._run_polisher_warnings(polished_content)
        if warnings:
            exec_events.append({
                "event_type": "polisher_warnings",
                "message": f"润色自检提醒：{len(warnings)} 项",
                "status": "warning",
                "payload": {"warnings": warnings},
            })

        # Advance status FIRST to lock the transition; abort if stale.
        # Normal flow polishes a drafted chapter; revision flow polishes a
        # chapter currently marked revision.
        # v6.1: Log diff summary
        polished_body = strip_chapter_heading(polished_content, chapter_number, chapter_title)
        polished_wc = _count_words(polished_body)
        changed_scope = output.changed_scope if hasattr(output, "changed_scope") else []
        diff_msg = f"改动：{original_wc} → {polished_wc} 字"
        if changed_scope:
            scope_str = ", ".join(changed_scope) if isinstance(changed_scope, list) else str(changed_scope)
            diff_msg += f"，改动范围：{scope_str}"
        if abs(polished_wc - original_wc) < 10:
            diff_msg += "（内容几乎未变）"
        low_change = abs(polished_wc - original_wc) < 10
        event_type = "revision_diff_generated" if current_status == ChapterStatus.REVISION.value else "diff_generated"
        exec_events.append({
            "event_type": event_type,
            "message": diff_msg,
            "payload": {
                "original_word_count": original_wc,
                "polished_word_count": polished_wc,
                "revised_word_count": polished_wc,
                "word_count_delta": polished_wc - original_wc,
                "changed_scope": changed_scope,
                "low_change_warning": low_change,
            },
        })

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

            # Save artifact (bind to workflow run for isolation)
            workflow_run_id = state.get("workflow_run_id")
            artifact_payload = output.model_dump()
            artifact_payload["content"] = polished_content
            # v6.1.1: Embed revision metadata in artifact for auditability
            if current_status == ChapterStatus.REVISION.value:
                revision_review = normalize_revision_review(state.get("_revision_review")) or {}
                artifact_payload["_revision_metadata"] = {
                    "revision_source_review_id": revision_review.get("review_id"),
                    "revision_target": revision_review.get("revision_target", "polisher"),
                    "revision_issues": revision_review.get("issues", []),
                    "revision_suggestions": revision_review.get("suggestions", []),
                }
            self.repo.save_artifact(
                project_id, chapter_number, "polisher", "polished_draft",
                content_json=artifact_payload,
                workflow_run_id=workflow_run_id,
            )
        except Exception as e:
            self._compensate_status(
                project_id, chapter_number,
                ChapterStatus.POLISHED.value, expected_status,
            )
            return {"error": f"Polisher: write failed: {e}", "chapter_status": expected_status}

        exec_events.append({
            "event_type": "artifact_saved",
            "message": f"保存产物：润色稿 ({polished_wc} 字)",
            "payload": {"artifact_type": "polished_draft", "word_count": polished_wc},
        })

        return {
            "chapter_status": ChapterStatus.POLISHED.value,
            "current_stage": "polished",
            "_exec_events": exec_events,
        }

    def _run_polisher_warnings(self, text: str) -> list[str]:
        """v6.4.3: Deterministic warnings on polished content.

        Prefer skill-based detection when skill_registry is available;
        fall back to built-in heuristics otherwise.
        These are advisory only and do NOT affect passed/repair_needed/workflow routing.
        """
        warnings: list[str] = []
        if not text:
            return warnings

        total_chars = max(len(text), 1)
        warned_codes: set[str] = set()

        # -- Try skill-based detection first (v6.4.3) --
        if self.skill_registry:
            # 1. Show-Don't-Tell
            sdt_result = self.skill_registry.run_skill(
                "show-dont-tell", {"text": text},
                agent="polisher", stage="before_save",
            )
            if sdt_result.get("ok"):
                sdt_data = sdt_result.get("data", {})
                per_1k = sdt_data.get("per_1000_chars", 0)
                summary_count = sdt_data.get("summary_count", 0)
                if isinstance(per_1k, (int, float)) and per_1k > 5:
                    warnings.append(
                        f"excessive_explanation: 直白情绪词密度 {per_1k:.1f}/千字，"
                        "建议改为动作或神态展现"
                    )
                    warned_codes.add("excessive_explanation")
                if isinstance(summary_count, int) and summary_count > 0:
                    warnings.append(
                        f"excessive_explanation: 检测到 {summary_count} 处总结句，建议删除"
                    )
                    warned_codes.add("excessive_explanation")

            # 2. Info Dump
            id_result = self.skill_registry.run_skill(
                "info-dump-detector", {"text": text},
                agent="polisher", stage="before_save",
            )
            if id_result.get("ok"):
                id_data = id_result.get("data", {})
                lore_count = id_data.get("lore_count", 0)
                dump_paras = id_data.get("dump_paragraphs", 0)
                if (isinstance(lore_count, int) and lore_count > 0) or \
                        (isinstance(dump_paras, int) and dump_paras > 0):
                    warnings.append(
                        f"info_dump_detected: 设定旁白 {lore_count} 处，纯说明段落 {dump_paras} 处，"
                        "建议通过动作/对话展现设定"
                    )
                    warned_codes.add("info_dump")

            # 3. Scene Texture
            st_result = self.skill_registry.run_skill(
                "scene-texture", {"text": text},
                agent="polisher", stage="before_save",
            )
            if st_result.get("ok"):
                st_data = st_result.get("data", {})
                sensory_per_1k = st_data.get("sensory_per_1000", 0)
                if isinstance(sensory_per_1k, (int, float)) and sensory_per_1k < 3:
                    warnings.append(
                        f"scene_texture_low: 感官细节密度 {sensory_per_1k:.1f}/千字，"
                        "建议补充光影、声音、温度或气味等感官线索"
                    )
                    warned_codes.add("scene_texture")

            # 4. Dialogue Naturalness
            dn_result = self.skill_registry.run_skill(
                "dialogue-naturalness", {"text": text},
                agent="polisher", stage="before_save",
            )
            if dn_result.get("ok"):
                dn_data = dn_result.get("data", {})
                dialogue_ratio = dn_data.get("dialogue_ratio", 0)
                colloquial_ratio = dn_data.get("colloquial_ratio", 0)
                functional_ratio = dn_data.get("functional_ratio", 0)
                if isinstance(dialogue_ratio, (int, float)) and dialogue_ratio < 0.05:
                    warnings.append(
                        f"dialogue_naturalness_low: 对白占比 {dialogue_ratio*100:.1f}%，"
                        "建议增加有冲突或潜台词的角色对话"
                    )
                    warned_codes.add("dialogue_naturalness")
                elif isinstance(colloquial_ratio, (int, float)) and colloquial_ratio < 0.1:
                    warnings.append(
                        "dialogue_naturalness_low: 对白口语化标记不足，"
                        "建议加入语气词、省略或打断"
                    )
                    warned_codes.add("dialogue_naturalness")
                if isinstance(functional_ratio, (int, float)) and functional_ratio > 0.3:
                    warnings.append(
                        f"dialogue_naturalness_low: 功能性对白比例偏高（{functional_ratio*100:.0f}%），"
                        "建议让对白承载目的、遮掩或情绪摩擦"
                    )
                    warned_codes.add("dialogue_naturalness")

        # -- Fallback heuristics for codes not covered by skills --
        # Exclude dialogue from narrative-only checks
        narrative_only = re.sub(
            '["\u201c\u201d\u300c\u300e].*?[\u201d\u300d\u300f"]',
            '「D」', text, flags=re.DOTALL,
        )

        if "excessive_explanation" not in warned_codes:
            straight_patterns = [
                r"感到[^，。！？]{1,8}", r"觉得[^，。！？]{1,8}", r"意识到[^，。！？]{1,8}",
                r"明白[^，。！？]{1,8}", r"知道[^，。！？]{1,8}", r"理解[^，。！？]{1,8}",
                r"察觉[^，。！？]{1,8}", r"心中暗想", r"心道",
            ]
            straight_count = sum(len(re.findall(p, narrative_only)) for p in straight_patterns)
            explain_per_1k = (straight_count / total_chars) * 1000
            summary_markers = ["综上所述", "总之", "简单来说", "说白了", "总而言之"]
            summary_count = sum(1 for m in summary_markers if m in text)
            if explain_per_1k > 5:
                warnings.append(
                    f"excessive_explanation: 直白情绪词密度 {explain_per_1k:.1f}/千字，"
                    "建议改为动作或神态展现"
                )
            if summary_count > 0:
                warnings.append(
                    f"excessive_explanation: 检测到 {summary_count} 处总结句，建议删除"
                )

        if "scene_texture" not in warned_codes:
            sensory_words = ["光", "影", "声", "响", "味", "香", "臭", "冷", "热", "湿", "干燥", "干涩", "风", "雨", "雷", "温度", "颜色", "色彩"]
            sensory_count = sum(text.count(w) for w in sensory_words)
            sensory_per_1k = (sensory_count / total_chars) * 1000
            if sensory_per_1k < 3:
                warnings.append(
                    f"scene_texture_low: 感官细节密度 {sensory_per_1k:.1f}/千字，"
                    "建议补充光影、声音、温度或气味等感官线索"
                )

        if "dialogue_naturalness" not in warned_codes:
            dialogues = re.findall(
                '["\u201c\u201d\u300c\u300e]([^\u201d\u300d\u300f"]+)[\u201d\u300d\u300f"]',
                text,
            )
            dialogue_chars = sum(len(d) for d in dialogues)
            dialogue_ratio = dialogue_chars / total_chars
            if dialogue_ratio < 0.05:
                warnings.append(
                    f"dialogue_naturalness_low: 对白占比 {dialogue_ratio*100:.1f}%，"
                    "建议增加有冲突或潜台词的角色对话"
                )
            else:
                colloquial_marks = ["啊", "呢", "吧", "嘛", "哦", "呀", "哈", "哼", "呸"]
                colloquial_count = sum(1 for d in dialogues for m in colloquial_marks if m in d)
                if dialogues and colloquial_count / len(dialogues) < 0.1:
                    warnings.append(
                        "dialogue_naturalness_low: 对白口语化标记不足，"
                        "建议加入语气词、省略或打断"
                    )

        # 5. pacing_too_uniform — always from built-in heuristic (no dedicated skill yet)
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        if len(paragraphs) >= 5:
            lengths = [len(p) for p in paragraphs]
            avg_len = statistics.mean(lengths)
            if avg_len > 0:
                cv = statistics.stdev(lengths) / avg_len if len(lengths) > 1 else 0
                if cv < 0.25:
                    warnings.append(
                        f"pacing_too_uniform: 段落长度过于均匀（变异系数 {cv:.2f}），"
                        "建议长短句交替，打破均匀节奏"
                    )

        return warnings

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

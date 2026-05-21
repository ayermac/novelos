"""Author Agent — writes chapter content based on instructions and scene beats."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from ..models.schemas import AuthorOutput
from ..models.state import ChapterStatus, FactoryState
from ..validators.chapter_checker import (
    validate_chapter_output,
    check_word_count_quality_gate,
    derive_word_target,
    normalize_declared_word_count,
    count_words,
)
from ..validators.death_penalty import (
    check_death_penalty,
    check_death_penalty_structured,
    format_death_penalty_for_prompt,
    has_critical_violation,
    sanitize_death_penalty_text,
)
from ..validators.plot_verifier import check_plot_coverage
from ..llm.openai_compatible import OutputValidationError
from ..llm.provider import is_configured_live_provider
from ..skills.registry import SkillRegistry
from ..agent_runtime.base import BaseAgent
from ..agent_runtime.chapter_text import ensure_chapter_heading, first_content_line, is_chapter_heading, strip_chapter_heading
from ..agent_runtime.revision_context import normalize_revision_review, revision_feedback_block
from ..agent_runtime.skill_hooks import run_agent_skills
from ..agent_runtime.self_check import SelfCheckLoop, SelfCheckResult
from ..quality.chapter_seam import build_chapter_seam_context
from ..agent_runtime.context_builder import AgentContextBuilder, format_context_bundle_for_prompt

logger = logging.getLogger(__name__)

AUTHOR_LONG_FORM_TIMEOUT_SECONDS = 300
AUTHOR_CONTEXT_CHAR_LIMIT = 12000

AUTHOR_SYSTEM_PROMPT = """你是网文工厂的执笔（Author），负责章节创作。

核心职责：
1. 状态驱动创作 — 严格基于上一章状态卡
2. 动作化叙事 — Show, Don't Tell
3. 精准落实指令 — 不遗漏指令中的任何要素
4. 钩子控制 — 每章末尾必须有悬念

Drafting Contract（v6.4.1）：
- 禁止写成剧情摘要、设定说明、章节梗概。必须以场景为单位推进。
- 每个关键事件必须通过动作、对白、环境变化或冲突体现，不得旁白解释。
- 情绪必须通过动作、神态、对话展现；禁止"感到/觉得/意识到/明白/心中暗想"等直白情绪词。
- 每个场景至少包含 1 种视觉 + 1 种听觉/触觉/嗅觉细节。
- 对白必须有角色目的、潜台词或冲突；禁止所有角色使用同一套礼貌/书面语。
- 世界观和设定必须通过角色的动作、对话或场景细节展现，禁止旁白式解释。
- 章节结尾留悬念，禁止归纳人生道理、总结本章意义、发表作者评论。
- 保持与 instruction objective/key_events 对齐。

铁律：
1. 禁止自己编造数值，必须从状态卡抄
2. 禁止创建伏笔、角色或世界观规则
3. 返修时只修复质检指出的问题，不重写全文

输出格式：严格按 JSON 格式输出，包含：
- title: 章节标题
- content: 正文内容
- word_count: 字数
- implemented_events: 已实现的关键事件列表
- used_plot_refs: 使用的伏笔代码列表"""


class AuthorAgent(BaseAgent):
    """Author: writes chapter content."""

    agent_id = "author"

    def __init__(self, repo, llm, skill_registry: SkillRegistry | None = None, **kwargs):
        super().__init__(repo, llm, skill_registry=skill_registry, **kwargs)
        self.skill_registry = skill_registry

    def _load_revision_review(
        self,
        state: FactoryState,
        chapter: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        """Load revision feedback from state, with DB fallback for direct/resumed runs."""
        revision_review = normalize_revision_review(state.get("_revision_review"))
        if revision_review:
            return revision_review
        if not chapter or chapter.get("status") != ChapterStatus.REVISION.value:
            return None
        try:
            return normalize_revision_review(
                self.repo.get_latest_review(state.get("project_id"), chapter.get("id"))
            )
        except Exception:
            logger.warning("Author: failed to load revision review fallback", exc_info=True)
            return None

    def build_context(self, state: FactoryState) -> str:
        parts = []
        project_id = state["project_id"]
        chapter_number = state["chapter_number"]

        title_contract = self._get_title_contract_context(project_id)
        if title_contract:
            parts.append(title_contract)

        # v6.6.2: Unified context builder
        builder = AgentContextBuilder(self.repo)
        bundle = builder.build_for_author(project_id, chapter_number, state)
        formatted = format_context_bundle_for_prompt(bundle, agent_name="author", max_chars=10000)
        if formatted:
            parts.append(formatted)

        # Writing instruction
        instruction = self._get_instruction(state)
        if instruction:
            word_target = self._get_word_target(state)
            minimum_required = int(word_target * 0.85)
            recommended_target = max(word_target, minimum_required + 500)
            parts.append(f"【写作指令】\n"
                         f"目标: {instruction.get('objective', '')}\n"
                         f"关键事件: {instruction.get('key_events', '')}\n"
                         f"情绪基调: {instruction.get('emotion_tone', '')}\n"
                         f"章末钩子: {instruction.get('ending_hook', '')}\n"
                         f"字数要求: 正文 content 至少 {minimum_required} 字符，"
                         f"建议写到 {recommended_target} 字符左右，低于硬要求会自动返修。")

        seam_context = build_chapter_seam_context(
            self.repo,
            project_id,
            chapter_number,
        )
        if seam_context:
            parts.append(seam_context)

        # R3: Review notes from human review sessions (v3.2)
        review_notes = self.repo.get_chapter_review_notes(project_id, chapter_number)
        if review_notes:
            latest_note = review_notes[0]
            parts.append(f"【人工审核意见】\n{latest_note['notes']}")

        # Scene beats
        beats = self._get_scene_beats(state)
        if beats:
            beats_str = "\n".join(
                f"  {b['sequence']}. 目标: {b.get('scene_goal', '')} | 冲突: {b.get('conflict', '')} "
                f"| 转折: {b.get('turn', '')} | 钩子: {b.get('hook', '')}"
                for b in beats
            )
            parts.append(
                f"【场景 Beat】\n{beats_str}\n\n"
                "【场景覆盖硬约束】\n"
                "必须按 sequence 顺序覆盖所有 beat，不能只写前半章。"
                "最后 2-3 个 beat 的转折和钩子必须出现在正文尾段；"
                "禁止停在中途动作、对抗或选择点。"
            )

        # v4.0: Style Bible injection
        style_ctx = self._get_style_bible_context(project_id, "author")
        if style_ctx:
            parts.append(style_ctx)

        repair_context = self._build_death_penalty_repair_context(state)
        if repair_context:
            parts.append(repair_context)

        # v6.4.1: Anti-AI drafting guide
        parts.append(
            "【去AI味写作指南】\n"
            "1. 禁止'感到/觉得/意识到/明白/知道/理解/察觉/发现'等直白情绪动词。改为动作或神态。\n"
            "2. 禁止'心中暗想/心道/暗道'等内心独白模板。改为动作推进或简短的心理活动。\n"
            "3. 禁止'这个世界是一个.../在这个世界里...'等设定旁白。改为角色动作或对话展现。\n"
            "4. 禁止'简单来说/说白了/所谓...是指'等解释句式。\n"
            "5. 每个场景至少包含一种视觉细节 + 一种其他感官细节（听觉/触觉/嗅觉/味觉）。\n"
            "6. 对白要有冲突或潜台词，避免功能化问答。\n"
            "7. 章节结尾留悬念，禁止说教式总结。"
        )

        # If revision, include review issues
        chapter = self._get_chapter_info(state)
        if chapter and chapter.get("status") == ChapterStatus.REVISION.value:
            review = state.get("_revision_review") or self.repo.get_latest_review(project_id, chapter["id"])
            feedback = revision_feedback_block(review)
            if feedback:
                parts.append(feedback)

        return self._limit_context_size("\n\n".join(parts))

    @staticmethod
    def _limit_context_size(context: str, limit: int = AUTHOR_CONTEXT_CHAR_LIMIT, *, agent_id: str = "author") -> str:
        """Keep long-form author prompts below a conservative input budget.

        The first part contains the core task contract/instructions; the tail
        often contains repair or revision notes. Preserve both and remove the
        middle when project context grows too large.
        """
        text = str(context or "")
        if len(text) <= limit:
            return text
        head_len = int(limit * 0.7)
        tail_len = limit - head_len
        marker = "\n\n【上下文已截断】中间资料过长，已保留开头任务要求和末尾返修/约束信息。\n\n"
        logger.warning(
            "%s context truncated from %d to %d chars",
            agent_id,
            len(text),
            limit,
        )
        head_budget = max(0, head_len - len(marker))
        return f"{text[:head_budget]}{marker}{text[-tail_len:]}"

    def _execute(self, state: FactoryState) -> dict[str, Any]:
        project_id = state["project_id"]
        chapter_number = state["chapter_number"]
        exec_events: list[dict] = []

        context = self._build_v6_context(state)

        chapter = self._get_chapter_info(state)
        is_revision = chapter and chapter.get("status") == ChapterStatus.REVISION.value
        revision_review = self._load_revision_review(state, chapter) if is_revision else None

        # v6.1.1: Emit revision context loaded event
        if is_revision:
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

        task_desc = "返修" if is_revision else "创作"
        system_prompt = f"{AUTHOR_SYSTEM_PROMPT}\n\n{format_death_penalty_for_prompt()}"
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"项目ID: {project_id}\n章节号: {chapter_number}\n任务: {task_desc}\n\n{context}\n\n请{task_desc}第{chapter_number}章。"},
        ]

        if self._should_use_plain_text_primary(state):
            output = self._try_plain_text_draft(state, task_desc, context)
            exec_events.append({
                "event_type": "long_form_generation",
                "message": "使用长文直写模式生成，避免长章节 JSON 截断",
                "status": "info",
                "payload": {"mode": "plain_text_primary"},
            })
        else:
            try:
                raw = self.llm.invoke_json(messages, schema=AuthorOutput)
                output = AuthorOutput(**normalize_declared_word_count(raw))
            except OutputValidationError:
                if state.get("llm_mode") != "real":
                    raise
                logger.warning(
                    "Author: structured JSON output failed; retrying with plain-text drafting fallback"
                )
                output = self._try_plain_text_draft(state, task_desc, context)
                exec_events.append({
                    "event_type": "fallback_used",
                    "message": "JSON 输出失败，降级为纯正文兜底生成",
                    "payload": {"fallback_type": "plain_text_fallback"},
                })

        output = self._sanitize_output(output, state)

        # v6.0: Self-check loop (generate already done; now check + optional repair)
        loop = SelfCheckLoop(agent_id=self.agent_id, max_repair_attempts=1)

        def _generate_wrap() -> dict[str, Any]:
            return {"output": output}

        def _self_check_wrap(data: dict[str, Any]) -> SelfCheckResult:
            out = data["output"]
            issues: list[dict[str, Any]] = []
            warnings_list: list[str] = []
            instruction = self._get_instruction(state) or {}
            # Event coverage
            required_events = self._instruction_items(instruction.get("key_events", ""))
            implemented = out.implemented_events or []
            missing = [e for e in required_events if e and e not in implemented]
            if missing:
                issues.append({"type": "event_coverage", "message": f"Missing events: {missing}"})
            scene_coverage_issues = self._scene_beat_coverage_issues(state, out.content)
            issues.extend(scene_coverage_issues)
            # Death penalty
            dp = check_death_penalty_structured(out.content)
            if dp.has_critical:
                issues.append({"type": "death_penalty", "message": f"Critical: {dp.violations}"})
            elif dp.violations:
                issues.append({"type": "death_penalty", "message": f"Violations: {dp.violations}"})
            # Word count
            wt = self._get_word_target(state)
            body_content = strip_chapter_heading(out.content, chapter_number, out.title)
            wc_passed, wc_msg = check_word_count_quality_gate(body_content, wt, "author")
            if not wc_passed:
                issues.append({"type": "word_count", "message": wc_msg})

            # v6.4.1: Show-don't-tell heuristic (warning only)
            # Scan only narrative text, excluding dialogue lines
            def _exclude_dialogue(text: str) -> str:
                """Replace quoted dialogue with placeholders so narration-only patterns run clean."""
                # Chinese/English quotation marks: "" " 「」 『』
                return re.sub(r'[""「『].*?[""」』]', '「D」', text, flags=re.DOTALL)

            narrative_only = _exclude_dialogue(out.content)
            straight_patterns = [
                r"感到[^，。！？]{1,8}", r"觉得[^，。！？]{1,8}", r"意识到[^，。！？]{1,8}",
                r"明白[^，。！？]{1,8}", r"知道[^，。！？]{1,8}", r"理解[^，。！？]{1,8}",
                r"察觉[^，。！？]{1,8}", r"发现[^，。！？]{1,8}", r"心中暗想", r"心道", r"暗道",
            ]
            straight_count = sum(len(re.findall(p, narrative_only)) for p in straight_patterns)
            per_1k = (straight_count / max(len(out.content), 1)) * 1000
            if per_1k > 5:
                warnings_list.append(
                    f"show_dont_tell: 直白情绪词密度 {per_1k:.1f}/千字，"
                    "建议将'感到/觉得/意识到'等改为动作、神态或对话展现"
                )

            # v6.4.1: Sensory detail heuristic (warning only)
            # Use multi-character words where possible to avoid homonym pollution
            sensory_words = ["光", "影", "声", "响", "味", "香", "臭", "冷", "热", "湿", "干燥", "干涩", "风", "雨", "雷", "温度", "颜色", "色彩"]
            sensory_count = sum(out.content.count(w) for w in sensory_words)
            sensory_per_1k = (sensory_count / max(len(out.content), 1)) * 1000
            if sensory_per_1k < 3:
                warnings_list.append(
                    f"sensory_detail: 感官细节密度 {sensory_per_1k:.1f}/千字，"
                    "建议每个场景至少增加一种视觉 + 一种听觉/触觉/嗅觉细节"
                )

            # v6.4.1: Prose-like heuristic (warning only)
            # Strong summary markers (low threshold) vs weak transition markers (high threshold)
            strong_markers = ["本章", "这一章", "首先", "最后", "综上所述", "总之", "简单来说", "说白了"]
            weak_markers = ["然后", "接着"]
            strong_count = sum(1 for m in strong_markers if m in out.content)
            weak_count = sum(1 for m in weak_markers if m in out.content)
            if strong_count > 3 or weak_count > 8:
                warnings_list.append(
                    f"prose_like: 检测到 {strong_count} 处强摘要标记 + {weak_count} 处弱承接标记，"
                    "建议以场景推进代替叙述"
                )

            # v6.4.1: Dialogue heuristic (warning only)
            # Match Chinese curly quotes (""), straight quotes ("), and corner brackets (「」『』)
            dialogues = re.findall(r'[""“”「『]([^""”」』]+)[""”」』]', out.content)
            dialogue_chars = sum(len(d) for d in dialogues)
            dialogue_ratio = dialogue_chars / max(len(out.content), 1)
            if dialogue_ratio < 0.05:
                warnings_list.append(
                    f"dialogue: 对白占比 {dialogue_ratio*100:.1f}%，"
                    "建议增加有冲突或潜台词的角色对话"
                )

            repairable = any(
                i["type"] in ("word_count", "death_penalty", "scene_beat_coverage")
                for i in issues
            )
            return SelfCheckResult(
                passed=len(issues) == 0,
                issues=issues,
                warnings=warnings_list,
                repair_needed=repairable,
                repair_suggestion="扩写、补齐场景 beat 或清理死刑红线词汇",
            )

        def _repair_wrap(data: dict[str, Any], check: SelfCheckResult) -> dict[str, Any] | None:
            out = data["output"]
            wt = self._get_word_target(state)
            body_content = strip_chapter_heading(out.content, chapter_number, out.title)
            wc_passed, wc_msg = check_word_count_quality_gate(body_content, wt, "author")
            if not wc_passed:
                expanded = self._try_expand_short_output(state, out, wc_msg)
                if expanded is not None:
                    return {"output": expanded}
            scene_coverage_issues = [
                issue for issue in check.issues
                if issue.get("type") == "scene_beat_coverage"
            ]
            if scene_coverage_issues:
                repaired = self._try_repair_scene_beat_coverage(
                    state, out, scene_coverage_issues, context,
                )
                if repaired is not None:
                    return {"output": repaired}
            # Try sanitize death penalty
            if state.get("llm_mode") == "real":
                sanitized, replacements = sanitize_death_penalty_text(out.content)
                if replacements:
                    from ..models.schemas import AuthorOutput
                    new_data = out.model_dump()
                    new_data["content"] = sanitized
                    return {"output": AuthorOutput(**normalize_declared_word_count(new_data))}
            return None

        loop_result = loop.run(_generate_wrap, _self_check_wrap, _repair_wrap)
        output = loop_result["output"]
        trace = loop_result.get("_trace", {})
        autonomy = loop_result.get("_autonomy", {})
        final_scene_coverage_issues = self._scene_beat_coverage_issues(state, output.content)
        if final_scene_coverage_issues:
            message = "Author 未完成场景 beat 覆盖，正文未写到章末钩子"
            return {
                "error": message,
                "chapter_status": state.get("chapter_status"),
                "quality_gate": {
                    "pass": False,
                    "revision_target": "author",
                    "scene_beat_coverage_fail": True,
                    "message": message,
                    "issues": [i.get("message", "") for i in final_scene_coverage_issues],
                    "agent": "author",
                    "workflow_run_id": state.get("workflow_run_id"),
                },
                "_trace": trace,
                "_autonomy": autonomy,
            }
        self_check_data = trace.get("self_check", {}) if isinstance(trace, dict) else {}
        sc_passed = self_check_data.get("passed", True)
        sc_issues = self_check_data.get("issues", [])
        sc_warnings = self_check_data.get("warnings", [])
        exec_events.append({
            "event_type": "self_check_completed",
            "message": f"自检{'通过' if sc_passed else f'未通过 ({len(sc_issues)} 个问题)'}"
            f"{'，' + str(len(sc_warnings)) + ' 个警告' if sc_warnings else ''}",
            "status": "info" if sc_passed else "warning",
            "payload": {
                "passed": sc_passed,
                "issue_count": len(sc_issues),
                "warning_count": len(sc_warnings),
            },
        })
        if state.get("llm_mode") == "real" and autonomy.get("decision") in {"ask_human", "reroute", "refuse"}:
            issue_types = {
                issue.get("type")
                for issue in (trace.get("self_check", {}) or {}).get("issues", [])
                if isinstance(issue, dict)
            }
            # Keep legacy retryable gates working. Death-penalty and word-count
            # failures are handled below by hard validation / quality gates so
            # workflow routing can consume retry attempts instead of jumping
            # straight to human blocking.
            if issue_types and issue_types.issubset({"death_penalty", "word_count"}):
                pass
            else:
                reason = autonomy.get("reason") or "Author 自检未通过"
                target_agent = (autonomy.get("metadata") or {}).get("target_agent", "author")
                return {
                    "error": f"Author 自检未通过: {reason}",
                    "chapter_status": state.get("chapter_status"),
                    "requires_human": True,
                    "quality_gate": {
                        "pass": False,
                        "revision_target": target_agent,
                        "self_check_fail": True,
                        "message": reason,
                        "agent": "author",
                        "workflow_run_id": state.get("workflow_run_id"),
                    },
                    "_trace": trace,
                    "_autonomy": autonomy,
                }

        # v6.0: Preserve original hard validation (schema, max words, death penalty)
        self.validate_output(output.model_dump())

        if is_revision and chapter and chapter.get("content"):
            repaired_regression = self._try_repair_revision_length_regression(
                state=state,
                output=output,
                chapter=chapter,
                revision_review=revision_review or {},
                fallback_context=context,
            )
            if repaired_regression is not None:
                output = repaired_regression
                self.validate_output(output.model_dump())
                exec_events.append({
                    "event_type": "revision_length_repaired",
                    "message": "返修稿篇幅退化已自动修复：基于当前保留稿合成完整修订稿",
                    "status": "info",
                    "payload": {"repair_type": "revision_length_regression"},
                })

        # Legacy skill hooks (still run for compatibility)
        instruction = self._get_instruction(state) or {}
        from ..validators.chapter_checker import count_words as _count_words
        body_content = strip_chapter_heading(output.content, chapter_number, output.title)
        exec_events.append({
            "event_type": "artifact_saved",
            "message": f"保存产物：章节初稿 ({_count_words(body_content)} 字)",
            "payload": {"artifact_type": "draft", "word_count": _count_words(body_content)},
        })
        run_agent_skills(
            repo=self.repo,
            skill_registry=self.skill_registry,
            project_id=project_id,
            chapter_number=chapter_number,
            agent="author",
            stage="after_llm",
            payload={
                "content": output.content,
                "required_events": instruction.get("key_events"),
                "implemented_events": output.implemented_events,
            },
            project_overrides=self._get_project_skill_overrides(project_id),
            skill_type_hint="validator",
        )

        # v5.3.0: Word count quality gate (final guard after self-check loop)
        word_target = self._get_word_target(state)
        word_gate_passed, word_gate_msg = check_word_count_quality_gate(
            body_content, word_target, "author"
        )
        if not word_gate_passed:
            logger.warning("Author: word count quality gate failed: %s", word_gate_msg)
            from ..validators.chapter_checker import count_words
            actual_wc = count_words(body_content)
            return {
                "error": f"字数质量门未通过: {word_gate_msg}",
                "chapter_status": state.get("chapter_status"),
                "quality_gate": {
                    "pass": False,
                    "revision_target": "author",
                    "word_count_fail": True,
                    "message": word_gate_msg,
                    "actual_word_count": actual_wc,
                    "word_target": word_target,
                    "agent": "author",
                    "workflow_run_id": state.get("workflow_run_id"),
                },
                "_trace": trace,
                "_autonomy": autonomy,
            }

        # v6.1.1: Emit revision diff event for revision chapters
        if is_revision and chapter:
            from ..validators.chapter_checker import count_words as _cw
            original_content = chapter.get("content", "") or ""
            original_body = strip_chapter_heading(original_content, chapter_number, chapter.get("title"))
            revised_body = strip_chapter_heading(output.content, chapter_number, output.title)
            original_wc = _cw(original_body)
            revised_wc = _cw(revised_body)
            wc_delta = revised_wc - original_wc
            low_change = abs(wc_delta) < 20 and original_body.strip() == revised_body.strip()
            exec_events.append({
                "event_type": "revision_diff_generated",
                "message": f"返修改动：{original_wc} → {revised_wc} 字（{'内容几乎未变' if low_change else f'变化 {wc_delta:+d} 字'}）",
                "status": "warning" if low_change else "info",
                "payload": {
                    "original_word_count": original_wc,
                    "revised_word_count": revised_wc,
                    "word_count_delta": wc_delta,
                    "low_change_warning": low_change,
                },
            })

        # v6.6.0: Do not let a revision candidate overwrite a stronger
        # existing draft when it clearly regresses.
        if is_revision and chapter and chapter.get("content"):
            from ..quality.version_regression_guard import VersionRegressionGuard

            revision_review = revision_review or {}
            reject, reason = VersionRegressionGuard.should_reject_new_draft(
                chapter.get("content", "") or "",
                output.content,
                self._get_word_target(state),
                editor_suggestions=revision_review.get("suggestions", []),
            )
            if reject:
                self.repo.save_artifact(
                    project_id,
                    chapter_number,
                    "author",
                    "rejected_regression",
                    content_json={
                        "title": output.title,
                        "content": output.content,
                        "rejection_reason": reason,
                        "revision_source_review_id": revision_review.get("review_id"),
                    },
                    workflow_run_id=state.get("workflow_run_id"),
                )
                return {
                    "error": f"返修稿退化，已保留上一版本：{reason}",
                    "chapter_status": state.get("chapter_status"),
                    "quality_gate": {
                        "pass": False,
                        "revision_target": "author",
                        "version_regression": True,
                        "message": reason,
                    },
                    "_revision_review": revision_review,
                    "_exec_events": exec_events,
                }

        # Advance status FIRST to lock the transition; abort if stale
        # For revision, expect status to be revision; for normal flow, expect scripted
        expected_status = ChapterStatus.REVISION.value if is_revision else ChapterStatus.SCRIPTED.value
        ok = self.repo.update_chapter_status(
            project_id, chapter_number, ChapterStatus.DRAFTED.value,
            expected_status=expected_status,
        )
        if not ok:
            logger.error(f"Author: status advance {expected_status}→drafted failed (stale state)")
            return {"error": "Author: stale state, status advance failed", "chapter_status": state.get("chapter_status")}

        # Save chapter content (only after status advance succeeds)
        try:
            content_ok = self.repo.save_chapter_content(
                project_id, chapter_number, output.content, output.title,
            )
            if not content_ok:
                self._compensate_status(
                    project_id, chapter_number,
                    ChapterStatus.DRAFTED.value, ChapterStatus.SCRIPTED.value,
                )
                return {"error": "Author: save_chapter_content failed", "chapter_status": ChapterStatus.SCRIPTED.value}

            # Save version
            self.repo.save_version(
                project_id, chapter_number, output.content,
                created_by="author" if not is_revision else "revision",
            )

            # Save artifact (bind to workflow run for isolation)
            workflow_run_id = state.get("workflow_run_id")
            artifact_payload = output.model_dump()
            # v6.1.1: Embed revision metadata in artifact for auditability
            if is_revision:
                revision_review = revision_review or {}
                artifact_payload["_revision_metadata"] = {
                    "revision_source_review_id": revision_review.get("review_id"),
                    "revision_target": revision_review.get("revision_target", "author"),
                    "revision_issues": revision_review.get("issues", []),
                    "revision_suggestions": revision_review.get("suggestions", []),
                }
            self.repo.save_artifact(
                project_id, chapter_number, "author", "draft",
                content_json=artifact_payload,
                workflow_run_id=workflow_run_id,
            )
        except Exception as e:
            self._compensate_status(
                project_id, chapter_number,
                ChapterStatus.DRAFTED.value, ChapterStatus.SCRIPTED.value,
            )
            return {"error": f"Author: write failed: {e}", "chapter_status": ChapterStatus.SCRIPTED.value}

        return {
            "chapter_status": ChapterStatus.DRAFTED.value,
            "current_stage": "drafted",
            "_revision_review": revision_review if is_revision else state.get("_revision_review"),
            "_trace": trace,
            "_autonomy": autonomy,
            "_exec_events": exec_events,
        }

    def validate_output(self, output: dict) -> None:
        AuthorOutput(**output)
        # Hard validation: schema, word_count match, death penalty.
        # Skip word-count range here — the retryable quality gate handles it
        # so short drafts route to revision instead of blocking.
        violations = validate_chapter_output(output, check_min_words=False, check_max_words=True)
        if violations:
            raise ValueError(f"Author 输出校验失败: {'; '.join(violations)}")
        # Q2: Enhanced death penalty with severity
        dp_result = check_death_penalty_structured(output.get("content", ""))
        if dp_result.has_critical:
            raise ValueError(
                f"Author 输出包含 CRITICAL 死刑红线: {', '.join(dp_result.violations)}"
            )
        if dp_result.violations:
            raise ValueError(f"Author 输出包含死刑红线词汇: {', '.join(dp_result.violations)}")

    def _try_expand_short_output(
        self,
        state: FactoryState,
        output: AuthorOutput,
        word_gate_msg: str,
    ) -> AuthorOutput | None:
        """Ask the LLM once to expand a valid-but-short draft.

        This only runs in real mode. Stub mode stays deterministic for tests
        and demos, while real model output gets one chance to satisfy the hard
        word-count gate before the chapter escalates to human review.
        """
        instruction = self._get_instruction(state)
        project = self.repo.get_project(state["project_id"])
        word_target = derive_word_target(instruction, project)
        minimum_required = int(word_target * 0.85)
        expansion_target = max(word_target + 300, minimum_required + 700)

        messages = [
            {"role": "system", "content": AUTHOR_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"第{state['chapter_number']}章正文未达到字数硬闸门：{word_gate_msg}。\n"
                    f"请在不改变已实现关键事件、伏笔和事实的前提下扩写正文，"
                    f"至少达到 {minimum_required} 字符，建议扩到 {expansion_target} 字符，"
                    "不要只补几十字或一小段。\n"
                    "必须返回完整 JSON，字段仍为 title/content/word_count/"
                    "implemented_events/used_plot_refs。word_count 可填写估算值，"
                    "系统会以 content 实际长度为准。\n\n"
                    f"【当前标题】\n{output.title}\n\n"
                    f"【当前正文】\n{output.content}\n\n"
                    f"【已实现事件】\n{json.dumps(output.implemented_events, ensure_ascii=False)}\n"
                    f"【已使用伏笔】\n{json.dumps(output.used_plot_refs, ensure_ascii=False)}"
                ),
            },
        ]

        try:
            raw = self.llm.invoke_json(messages, schema=AuthorOutput)
            expanded = AuthorOutput(**normalize_declared_word_count(raw))
            expanded = self._sanitize_output(expanded, state)
            self.validate_output(expanded.model_dump())
            return expanded
        except Exception as e:
            logger.warning("Author: expand-short-output retry failed: %s", e)
            return None

    _SCENE_TERM_STOPWORDS = {
        "场景", "目标", "冲突", "转折", "钩子", "正文", "本章", "章节", "最后",
        "开始", "完成", "进行", "出现", "继续", "形成", "展示", "建立", "推动",
        "林泽", "系统", "当前", "一个", "一种", "这个", "那个", "他们", "自己",
    }

    @classmethod
    def _scene_terms(cls, text: Any) -> list[str]:
        """Extract high-signal terms for deterministic beat coverage checks."""
        raw = str(text or "")
        terms: list[str] = []
        for token in re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,}", raw):
            token = token.strip()
            if token in cls._SCENE_TERM_STOPWORDS:
                continue
            if len(token) > 18:
                token = token[:18]
            if token and token not in terms:
                terms.append(token)
        return terms

    def _scene_beat_coverage_issues(
        self,
        state: FactoryState,
        content: str,
    ) -> list[dict[str, Any]]:
        """Detect drafts that stop before the final scene beats land.

        The check is intentionally conservative: it only enforces the final
        beat and ending hook in the tail. Earlier beats may be valid
        middle-scene material and may be paraphrased, so deterministic checks
        on them can cause false revision loops.
        """
        beats = self._get_scene_beats(state)
        if len(beats) < 3:
            return []

        chapter_number = state.get("chapter_number", 0)
        title = (self._get_chapter_info(state) or {}).get("title")
        body = strip_chapter_heading(str(content or ""), chapter_number, title)
        if not body.strip():
            return [{
                "type": "scene_beat_coverage",
                "message": "正文为空，无法覆盖场景 beat",
            }]

        tail_start = int(len(body) * 0.45)
        tail = body[tail_start:]
        issues: list[dict[str, Any]] = []

        final_beat = beats[-1]
        sequence = final_beat.get("sequence", "?")
        combined = " ".join(
            str(final_beat.get(field) or "")
            for field in ("scene_goal", "turn", "hook")
        )
        terms = self._scene_terms(combined)
        if terms and not any(term in tail for term in terms[:10]):
            issues.append({
                "type": "scene_beat_coverage",
                "message": f"正文尾段缺少第 {sequence} 个 scene beat 的关键落点: {', '.join(terms[:5])}",
                "sequence": sequence,
                "required_terms": terms[:10],
            })

        instruction = self._get_instruction(state) or {}
        ending_terms = self._scene_terms(instruction.get("ending_hook", ""))
        if ending_terms and not any(term in tail for term in ending_terms[:8]):
            issues.append({
                "type": "scene_beat_coverage",
                "message": f"正文尾段缺少章节 ending_hook: {', '.join(ending_terms[:5])}",
                "required_terms": ending_terms[:8],
            })

        return issues

    def _try_repair_scene_beat_coverage(
        self,
        state: FactoryState,
        output: AuthorOutput,
        coverage_issues: list[dict[str, Any]],
        fallback_context: str,
    ) -> AuthorOutput | None:
        """Ask the live model once to rewrite an incomplete draft to the final beat."""
        if state.get("llm_mode") != "real":
            return None

        instruction = self._get_instruction(state) or {}
        word_target = self._get_word_target(state)
        current_body_len = count_words(strip_chapter_heading(output.content, state["chapter_number"], output.title))
        minimum_required = max(int(word_target * 0.85), int(current_body_len * 0.9))
        target_hint = max(word_target, current_body_len)
        compact_context = self._build_plain_text_context(state, fallback_context)
        issue_lines = "\n".join(
            f"- {issue.get('message', '')}" for issue in coverage_issues
        )
        prose_max_tokens = max(2048, min(6144, int(word_target * 2.0)))
        per_call_retries = 1 if is_configured_live_provider(self.llm) else None

        messages = [
            {
                "role": "system",
                "content": (
                    "你是网文工厂的执笔。现在修复一个未写到章末的章节草稿。"
                    "只输出完整章节正文纯文本，不要 JSON、解释、清单或 Markdown。"
                    "必须按 scene beat 顺序重写到最后一个 beat 的 hook，"
                    "禁止停在中途动作、战斗、选择或对话上。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"第{state['chapter_number']}章草稿未完成场景覆盖，问题如下：\n{issue_lines}\n\n"
                    f"正文至少 {minimum_required} 字符，建议接近 {target_hint} 字符。\n"
                    "请保留已成立的事实和人物关系，但必须重写为完整章节，"
                    "尾段必须落到最后一个 scene beat 和章节 ending_hook。\n\n"
                    f"{compact_context}\n\n"
                    f"【当前不完整草稿】\n{output.content}\n\n"
                    "请直接输出修复后的完整章节正文。"
                ),
            },
        ]

        try:
            content = self._invoke_text_for_author(
                messages,
                temperature=0.68,
                max_tokens=prose_max_tokens,
                max_retries=per_call_retries,
                request_timeout_seconds=(
                    AUTHOR_LONG_FORM_TIMEOUT_SECONDS
                    if is_configured_live_provider(self.llm)
                    else None
                ),
            )
            content = self._coerce_plain_text_content(content)
            if not content:
                return None
            repaired = AuthorOutput(
                title=self._derive_title(state, instruction, content),
                content=content,
                word_count=len(content),
                implemented_events=self._instruction_items(instruction.get("key_events", "")),
                used_plot_refs=self._instruction_items(instruction.get("plots_to_plant", "")),
            )
            repaired = self._sanitize_output(repaired, state)
            self.validate_output(repaired.model_dump())
            return repaired
        except Exception as e:
            logger.warning("Author: scene-beat coverage repair failed: %s", e)
            return None

    @staticmethod
    def _revision_requests_compression(revision_review: dict[str, Any] | None) -> bool:
        suggestions = (revision_review or {}).get("suggestions") or []
        issues = (revision_review or {}).get("issues") or []
        text = "\n".join(str(item) for item in [*suggestions, *issues])
        return any(word in text for word in ("压缩", "缩短", "精简", "删减篇幅"))

    def _try_repair_revision_length_regression(
        self,
        state: FactoryState,
        output: AuthorOutput,
        chapter: dict[str, Any],
        revision_review: dict[str, Any] | None,
        fallback_context: str,
    ) -> AuthorOutput | None:
        """Repair a revision candidate that fixed issues but collapsed the draft length."""
        if state.get("llm_mode") != "real":
            return None
        if self._revision_requests_compression(revision_review):
            return None

        chapter_number = state["chapter_number"]
        current_body = strip_chapter_heading(
            chapter.get("content", "") or "",
            chapter_number,
            chapter.get("title"),
        ).strip()
        candidate_body = strip_chapter_heading(
            output.content,
            chapter_number,
            output.title,
        ).strip()
        current_len = count_words(current_body)
        candidate_len = count_words(candidate_body)
        if current_len <= 0:
            return None
        shrink_ratio = (current_len - candidate_len) / current_len
        if shrink_ratio <= 0.15:
            return None

        minimum_required = max(int(current_len * 0.9), int(self._get_word_target(state) * 0.85))
        issue_lines = "\n".join(
            f"- {issue}" for issue in (revision_review or {}).get("issues", [])[:8]
        )
        suggestion_lines = "\n".join(
            f"- {suggestion}" for suggestion in (revision_review or {}).get("suggestions", [])[:8]
        )
        compact_context = self._build_plain_text_context(state, fallback_context)
        prose_max_tokens = max(4096, min(8192, int(current_len * 1.6)))
        per_call_retries = 1 if is_configured_live_provider(self.llm) else None

        messages = [
            {
                "role": "system",
                "content": (
                    "你是网文工厂的返修编辑。现在不是重新创作，而是合并修订。"
                    "只输出完整章节正文纯文本，不要 JSON、解释、清单或 Markdown。"
                    "必须以当前保留稿为底稿，吸收候选返修稿中解决问题的部分，"
                    "保留完整篇幅和已成立事件。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"第{chapter_number}章返修候选稿明显变短：当前保留稿约 {current_len} 字符，"
                    f"候选返修稿约 {candidate_len} 字符，Editor 未要求压缩。\n"
                    f"请输出完整修订稿，正文至少 {minimum_required} 字符，建议接近 {current_len} 字符。\n"
                    "操作规则：\n"
                    "- 以【当前保留稿】为主体，不要另起炉灶重写短版。\n"
                    "- 只把【候选返修稿】中真正修复退回问题的段落、句子或章末钩子合并回底稿。\n"
                    "- 保留未被点名的问题段落、人物关系、已成立事件、场景顺序和整体篇幅。\n"
                    "- 尾段必须补全任务结算、违规记录、失败名单编号和章末钩子。\n\n"
                    f"【退回问题】\n{issue_lines}\n\n"
                    f"【修改建议】\n{suggestion_lines}\n\n"
                    f"{compact_context}\n\n"
                    f"【当前保留稿】\n{current_body}\n\n"
                    f"【候选返修稿】\n{candidate_body}\n\n"
                    "请直接输出合并后的完整章节正文。"
                ),
            },
        ]

        try:
            content = self._invoke_text_for_author(
                messages,
                temperature=0.62,
                max_tokens=prose_max_tokens,
                max_retries=per_call_retries,
                request_timeout_seconds=(
                    AUTHOR_LONG_FORM_TIMEOUT_SECONDS
                    if is_configured_live_provider(self.llm)
                    else None
                ),
            )
            content = self._coerce_plain_text_content(content)
            if not content:
                return None
            repaired = AuthorOutput(
                title=self._derive_title(state, self._get_instruction(state) or {}, content),
                content=content,
                word_count=len(content),
                implemented_events=output.implemented_events,
                used_plot_refs=output.used_plot_refs,
            )
            repaired = self._sanitize_output(repaired, state)
            repaired_body = strip_chapter_heading(repaired.content, chapter_number, repaired.title)
            if count_words(repaired_body) < minimum_required:
                logger.warning(
                    "Author: revision length repair still too short (%s < %s)",
                    count_words(repaired_body),
                    minimum_required,
                )
                return None
            return repaired
        except Exception as e:
            logger.warning("Author: revision length regression repair failed: %s", e)
            return None

    def _try_plain_text_draft(
        self,
        state: FactoryState,
        task_desc: str,
        context: str,
    ) -> AuthorOutput:
        """Generate prose directly when real models fail long-form JSON output.

        Long prose is much more likely than short structured outputs to be
        wrapped in Markdown or truncated before the closing JSON brace. For
        production writing, preserve progress by generating plain chapter text
        and deriving the small metadata fields deterministically.
        """
        project_id = state["project_id"]
        chapter_number = state["chapter_number"]
        instruction = self._get_instruction(state) or {}
        word_target = self._get_word_target(state)
        minimum_required = int(word_target * 0.85)
        effective_target = word_target
        length_guard_note = (
            f"正文至少 {minimum_required} 字符，建议接近 {word_target} 字符；"
            f"最多不要超过 {max(word_target + 250, minimum_required + 250)} 字符。"
        )
        revision_source_section = ""
        if task_desc == "返修":
            existing_chapter = self._get_chapter_info(state) or {}
            existing_body = strip_chapter_heading(
                existing_chapter.get("content", "") or "",
                chapter_number,
                existing_chapter.get("title"),
            )
            existing_len = count_words(existing_body)
            if existing_body.strip():
                revision_source_section = (
                    "【当前保留稿 / 必须在此基础上返修】\n"
                    "下面是当前已保存章节正文。请把它当作底稿进行定点修改："
                    "保留未被 Editor 点名的问题段落、人物关系、已成立事件和整体篇幅，"
                    "只重写或补足退回问题涉及的段落。禁止脱离该底稿另起炉灶重写短版。\n\n"
                    f"{existing_body.strip()}\n"
                )
            revision_review = normalize_revision_review(state.get("_revision_review")) or {}
            compress_requested = self._revision_requests_compression(revision_review)
            if existing_len > 0 and not compress_requested:
                minimum_required = max(minimum_required, int(existing_len * 0.9))
                effective_target = max(word_target, existing_len)
                upper_bound = max(effective_target + 700, int(existing_len * 1.08))
                length_guard_note = (
                    f"当前保留稿约 {existing_len} 字符，Editor 未要求压缩；"
                    f"返修必须保留完整篇幅，不要主动压缩。正文至少 {minimum_required} 字符，"
                    f"建议接近 {effective_target} 字符，合理上限 {upper_bound} 字符。"
                )
        prose_max_tokens = max(1024, min(6144, int(effective_target * 1.5)))
        compact_context = self._build_plain_text_context(state, context)
        per_call_retries = 1 if is_configured_live_provider(self.llm) else None

        messages = [
            {
                "role": "system",
                "content": (
                    "你是网文工厂的执笔。现在只输出章节正文纯文本。"
                    "禁止输出 JSON、Markdown 代码块、字段名、解释或清单。"
                    "直接从正文第一句开始，到正文最后一句结束。"
                    "禁止写成剧情摘要或设定说明；以场景为单位推进。"
                    "情绪通过动作、神态、对话展现，禁止直白情绪词。"
                    "对白要有冲突或潜台词，避免功能化问答。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"项目ID: {project_id}\n章节号: {chapter_number}\n任务: {task_desc}\n"
                    f"{length_guard_note}\n\n"
                    f"{compact_context}\n\n"
                    f"{revision_source_section}\n"
                    f"请直接写第{chapter_number}章正文。"
                ),
            },
        ]

        content = self._invoke_text_for_author(
            messages,
            temperature=0.7,
            max_tokens=prose_max_tokens,
            max_retries=per_call_retries,
            request_timeout_seconds=(
                AUTHOR_LONG_FORM_TIMEOUT_SECONDS
                if is_configured_live_provider(self.llm)
                else None
            ),
        ).strip()
        content = self._coerce_plain_text_content(content)
        if not content:
            retry_messages = [
                *messages,
                {
                    "role": "user",
                    "content": (
                        "上一轮返回为空。请立刻重写本章正文纯文本，"
                        "不要输出 JSON、字段名、解释、标题占位或 Markdown。"
                        f"正文至少 {minimum_required} 字符，从第一句正文直接开始。"
                    ),
                },
            ]
            content = self._invoke_text_for_author(
                retry_messages,
                temperature=0.75,
                max_tokens=prose_max_tokens,
                max_retries=per_call_retries,
                request_timeout_seconds=(
                    AUTHOR_LONG_FORM_TIMEOUT_SECONDS
                    if is_configured_live_provider(self.llm)
                    else None
                ),
            ).strip()
            content = self._coerce_plain_text_content(content)
        if not content:
            raise OutputValidationError("Author 纯正文生成空内容（已重试一次）")

        title = self._derive_title(state, instruction, content)
        return AuthorOutput(
            title=title,
            content=content,
            word_count=len(content),
            implemented_events=self._instruction_items(instruction.get("key_events", "")),
            used_plot_refs=self._instruction_items(instruction.get("plots_to_plant", "")),
        )

    def _should_use_plain_text_primary(self, state: FactoryState) -> bool:
        """Use prose-first authoring for live providers.

        Stub tests and deterministic demo providers still exercise the legacy
        JSON path. Real OpenAI-compatible providers expose ``config`` and are
        better served by plain text for long-form chapter prose.
        """
        return state.get("llm_mode") == "real" and is_configured_live_provider(self.llm)

    def _invoke_text_for_author(
        self,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        max_retries: int | None,
        request_timeout_seconds: int | None = None,
    ) -> str:
        """Invoke text generation with per-call retry control when supported."""
        if max_retries is None and request_timeout_seconds is None:
            return self.llm.invoke_text(messages, temperature=temperature, max_tokens=max_tokens)
        try:
            return self.llm.invoke_text(
                messages,
                temperature=temperature,
                max_tokens=max_tokens,
                max_retries=max_retries,
                request_timeout_seconds=request_timeout_seconds,
            )
        except TypeError as exc:
            exc_text = str(exc)
            if "max_retries" not in exc_text and "request_timeout_seconds" not in exc_text:
                raise
            try:
                return self.llm.invoke_text(
                    messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    max_retries=max_retries,
                )
            except TypeError as retry_exc:
                if "max_retries" not in str(retry_exc):
                    raise
                return self.llm.invoke_text(messages, temperature=temperature, max_tokens=max_tokens)

    def _build_plain_text_context(self, state: FactoryState, fallback_context: str) -> str:
        """Build a compact prompt for direct prose generation.

        v6.6.2: 统一使用 AgentContextBuilder，确保 plain-text 路径也包含
        revision feedback、inheritance context 和 hard constraints。
        """
        from ..agent_runtime.revision_context import build_revision_feedback_context

        project_id = state["project_id"]
        chapter_number = state["chapter_number"]
        instruction = self._get_instruction(state) or {}
        parts = []

        # v6.6.2: Unified context builder for plain-text path
        try:
            builder = AgentContextBuilder(self.repo)
            bundle = builder.build_for_author(project_id, chapter_number, state)
            formatted = format_context_bundle_for_prompt(bundle, agent_name="author", max_chars=8000)
            if formatted:
                parts.append(formatted)
        except Exception:
            pass

        # 保留 revision feedback 显式注入（builder 已包含，此处作为冗余保障）
        revision_block = build_revision_feedback_context(
            state, self.repo, self._get_chapter_info(state)
        )
        if revision_block:
            parts.append(revision_block)

        if instruction:
            parts.append(
                "【写作指令】\n"
                f"目标: {instruction.get('objective', '')}\n"
                f"关键事件: {instruction.get('key_events', '')}\n"
                f"情绪基调: {instruction.get('emotion_tone', '')}\n"
                f"章末钩子: {instruction.get('ending_hook', '')}\n"
                f"伏笔: {instruction.get('plots_to_plant', '')}"
            )

        seam_context = build_chapter_seam_context(
            self.repo,
            project_id,
            chapter_number,
        )
        if seam_context:
            parts.append(seam_context)

        beats = self._get_scene_beats(state)
        if beats:
            beat_lines = []
            for beat in beats:
                beat_lines.append(
                    f"{beat.get('sequence')}. {beat.get('scene_goal', '')}"
                    f" / 冲突: {beat.get('conflict', '')}"
                    f" / 转折: {beat.get('turn', '')}"
                    f" / 钩子: {beat.get('hook', '')}"
                )
            parts.append(
                "【场景 Beat】\n" + "\n".join(beat_lines) +
                "\n\n【场景覆盖硬约束】必须按 sequence 覆盖全部 beat，"
                "最后 2-3 个 beat 的转折和钩子必须出现在正文尾段；"
                "禁止停在中途动作、对抗或选择点。"
            )

        characters = self.repo.get_characters(project_id)
        if characters:
            char_lines = [
                f"- {c['name']}({c['role']}): {c.get('description', '')}"
                for c in characters[:5]
            ]
            parts.append("【角色】\n" + "\n".join(char_lines))

        parts.append(
            "【写作约束】\n"
            "禁止剧情摘要和设定说明；以场景推进。\n"
            "情绪通过动作展现，禁止直白情绪词。\n"
            "对白要有冲突或潜台词。"
        )

        if parts:
            return "\n\n".join(parts)
        return fallback_context

    @staticmethod
    def _coerce_plain_text_content(text: str) -> str:
        """Strip accidental wrappers from a plain-text fallback response."""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()

        if cleaned.startswith("{"):
            try:
                data = json.loads(cleaned)
                if isinstance(data, dict) and data.get("content"):
                    return str(data["content"]).strip()
            except Exception:
                pass

        return cleaned

    def _derive_title(
        self,
        state: FactoryState,
        instruction: dict,
        content: str | None = None,
    ) -> str:
        chapter = self._get_chapter_info(state) or {}
        chapter_number = state["chapter_number"]
        title = chapter.get("title") or ""
        if self._is_usable_chapter_title(title, chapter_number, instruction):
            return title
        derived_from_content = self._title_from_content_heading(content or "", chapter_number)
        if derived_from_content:
            return derived_from_content
        derived_from_opening = self._title_from_content_opening(content or "", chapter_number, instruction)
        if derived_from_opening:
            return derived_from_opening
        derived_from_instruction = self._title_from_instruction(instruction, chapter_number)
        if derived_from_instruction:
            return derived_from_instruction
        return f"第{chapter_number}章"

    @staticmethod
    def _strip_chapter_prefix(title: str, chapter_number: int) -> str:
        text = str(title or "").strip()
        patterns = [
            rf"^第\s*{chapter_number}\s*章[\s:：、.-]*",
            r"^第[一二三四五六七八九十百千零〇两]+\s*章[\s:：、.-]*",
        ]
        for pattern in patterns:
            text = re.sub(pattern, "", text).strip()
        return text

    @classmethod
    def _is_usable_chapter_title(
        cls,
        title: str,
        chapter_number: int,
        instruction: dict,
    ) -> bool:
        text = str(title or "").strip()
        if not text:
            return False
        compact_placeholder = re.sub(r"\s+", "", text)
        if compact_placeholder in {f"第{chapter_number}章", f"第{chapter_number}章节"}:
            return False
        if any(marker in compact_placeholder for marker in ("待命名", "未命名", "占位")):
            return False

        suffix = cls._strip_chapter_prefix(text, chapter_number)
        if not suffix:
            return False

        objective = str(instruction.get("objective") or "").strip()
        if len(suffix) >= 6 and objective and (
            objective.startswith(suffix)
            or suffix.startswith(objective[: min(len(objective), 12)])
        ):
            return False

        planning_verbs = (
            "引入",
            "铺垫",
            "描绘",
            "建立",
            "推进",
            "承接",
            "完成",
            "解决",
            "展示",
            "呈现",
            "交代",
            "安排",
            "触发",
            "围绕",
        )
        planning_terms = ("本章", "目标", "关键事件", "写作指令", "铺垫", "建立", "描绘")
        if suffix.startswith(planning_verbs) or any(term in suffix for term in planning_terms):
            return False
        if any(mark in suffix for mark in ("，", "。", "；", ";")):
            return False
        if len(suffix) > 16:
            return False
        return True

    @classmethod
    def _title_from_content_heading(cls, content: str, chapter_number: int) -> str | None:
        first_line = first_content_line(content)
        if not first_line:
            return None
        if len(first_line) > 32:
            return None
        if is_chapter_heading(first_line, chapter_number):
            return first_line if cls._is_usable_chapter_title(first_line, chapter_number, {}) else None
        return None

    @classmethod
    def _title_from_content_opening(
        cls,
        content: str,
        chapter_number: int,
        instruction: dict,
    ) -> str | None:
        """Derive a readable fallback title from the opening prose.

        This is only used when the model title is unusable. It prevents the
        published chapter from falling back to a bare "第N章" heading.
        """
        first_line = first_content_line(content)
        if not first_line or is_chapter_heading(first_line, chapter_number):
            return None
        suffix = cls._clean_title_suffix(first_line)
        if not suffix:
            return None
        title = f"第{chapter_number}章 {suffix}"
        return title if cls._is_usable_chapter_title(title, chapter_number, instruction) else None

    @classmethod
    def _title_from_instruction(cls, instruction: dict, chapter_number: int) -> str | None:
        for value in (
            instruction.get("ending_hook"),
            *cls._instruction_items(instruction.get("key_events")),
        ):
            suffix = cls._clean_title_suffix(str(value or ""))
            if not suffix:
                continue
            title = f"第{chapter_number}章 {suffix}"
            if cls._is_usable_chapter_title(title, chapter_number, instruction):
                return title
        return None

    @staticmethod
    def _clean_title_suffix(value: str) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        text = re.sub(r"^[\"'“”‘’《》【】\s]+|[\"'“”‘’《》【】\s]+$", "", text)
        text = re.split(r"[。！？!?；;，,\n\r]", text, maxsplit=1)[0].strip()
        text = re.sub(r"^(本章|章节|场景|目标|关键事件)\s*[:：、.-]?\s*", "", text).strip()
        text = re.sub(r"\s+", "", text)
        if len(text) < 2:
            return ""
        return text[:14]

    @staticmethod
    def _instruction_items(value: Any) -> list[str]:
        """Normalize instruction list-ish fields for fallback metadata."""
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if not value:
            return []
        text = str(value).strip()
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except Exception:
            pass
        for sep in ("；", ";", "\n", "，", ","):
            if sep in text:
                return [item.strip() for item in text.split(sep) if item.strip()]
        return [text]

    def _sanitize_output(self, output: AuthorOutput, state: FactoryState) -> AuthorOutput:
        """Apply deterministic safe rewrites before hard validation."""
        data = output.model_dump()
        instruction = self._get_instruction(state) or {}
        sanitized_title = self._derive_title(state, instruction, output.content)
        if not self._is_usable_chapter_title(output.title, state["chapter_number"], instruction):
            data["title"] = sanitized_title
        data["content"] = ensure_chapter_heading(data.get("content", ""), data.get("title"), state["chapter_number"])

        if state.get("llm_mode") != "real":
            if data == output.model_dump():
                return output
            return AuthorOutput(**normalize_declared_word_count(data))

        sanitized_content, replacements = sanitize_death_penalty_text(data.get("content", ""))
        if replacements:
            logger.info(
                "Author: sanitized death-penalty phrases before validation: %s",
                replacements,
            )
            data["content"] = sanitized_content

        if data == output.model_dump():
            return output
        return AuthorOutput(**normalize_declared_word_count(data))

    def _build_death_penalty_repair_context(self, state: FactoryState) -> str:
        """Build repair context from the active gate and recent failed runs."""
        messages: list[str] = []
        gate = state.get("quality_gate", {}) or {}
        if gate.get("death_penalty_fail"):
            msg = gate.get("message") or "上一轮触发死刑红线"
            messages.append(str(msg))

        project_id = state["project_id"]
        chapter_number = state["chapter_number"]
        try:
            runs = self.repo.get_workflow_runs_for_project(
                project_id, chapter_number=chapter_number, limit=5
            )
        except Exception:
            runs = []
        for run in runs:
            error = str(run.get("error_message") or "")
            if "死刑红线" in error and error not in messages:
                messages.append(error)

        if not messages:
            return ""

        return (
            "【自动复盘：上一轮失败原因】\n"
            + "\n".join(f"- {msg}" for msg in messages[:3])
            + "\n本轮必须彻底避开上述原词和同类模板表达；优先改成具体动作、物理反应或对话推进。"
        )

    def _get_word_target(self, state: FactoryState) -> int:
        """Derive the active word target for this chapter."""
        project_id = state["project_id"]
        instruction = self._get_instruction(state)
        project = self.repo.get_project(project_id)
        return derive_word_target(instruction, project)

    def _check_word_count_gate(self, state: FactoryState, content: str) -> tuple[bool, str]:
        """v5.3.0: Check word count quality gate.

        Returns:
            Tuple of (passed, message).
        """
        word_target = self._get_word_target(state)

        body_content = strip_chapter_heading(content, state["chapter_number"])
        return check_word_count_quality_gate(body_content, word_target, "author")

"""Author Agent — writes chapter content based on instructions and scene beats."""

from __future__ import annotations

import json
import logging
import re
from difflib import SequenceMatcher
from typing import Any

from ..agent_runtime.segmented_generation import chunk_items
from ..workflow.execution_events import (
    EVENT_SEGMENT_STARTED,
    EVENT_SEGMENT_COMPLETED,
    EVENT_SEGMENT_FAILED,
)
from ..models.schemas import AuthorOutput, TitleGenerationOutput
from ..models.state import ChapterStatus, FactoryState
from ..validators.chapter_checker import (
    validate_chapter_output,
    check_word_count_quality_gate,
    check_word_count_upper_gate,
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
from ..llm.openai_compatible import LLMError, OutputValidationError, TokenUsage
from ..llm.provider import is_configured_live_provider
from ..skills.registry import SkillRegistry
from ..agent_runtime.base import BaseAgent
from ..agent_runtime.chapter_text import ensure_chapter_heading, first_content_line, is_chapter_heading, strip_chapter_heading
from ..agent_runtime.revision_context import (
    normalize_revision_review,
    revision_feedback_block,
    revision_review_from_quality_gate,
)
from ..agent_runtime.skill_hooks import run_agent_skills
from ..agent_runtime.self_check import SelfCheckLoop, SelfCheckResult
from ..quality.chapter_seam import build_chapter_seam_context
from ..quality.concept_budget import CONCEPT_BUDGET_CONTRACT
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
5. 遵守 ChapterBrief 约束 — 不违反禁止动作，实现章节目标

Drafting Contract（v6.4.1）：
- 禁止写成剧情摘要、设定说明、章节梗概。必须以场景为单位推进。
- 每个关键事件必须通过动作、对白、环境变化或冲突体现，不得旁白解释。
- 情绪必须通过动作、神态、对话展现；禁止"感到/觉得/意识到/明白/心中暗想"等直白情绪词。
- 每个场景至少包含 1 种视觉 + 1 种听觉/触觉/嗅觉细节。
- 对白必须有角色目的、潜台词或冲突；禁止所有角色使用同一套礼貌/书面语。
- 世界观和设定必须通过角色的动作、对话或场景细节展现，禁止旁白式解释。
- 章节结尾留悬念，禁止归纳人生道理、总结本章意义、发表作者评论。
- 保持与 instruction objective/key_events 对齐。
- 遵守 ChapterBrief 的 forbidden_moves（禁止动作）
- 实现 ChapterBrief 的 chapter_goal（章节目标）和 protagonist_agency（主角能动性）

【主角中心法则】（v6.8.5）：
- 每个场景必须以主角视角展开，禁止切换到配角视角或旁观者视角。
- 主角必须在场景中有主动行为（决策、行动、反应），不得沦为旁观者或背景板。
- 配角存在感不得超过主角的 30%，禁止大段配角独白或配角视角叙述。
- 主角的内心活动、目标、动机必须清晰展现，读者必须知道主角在想什么、要什么。
- 冲突必须围绕主角展开，主角必须是冲突的核心参与者或解决者。

【爽文节奏法则】（v6.8.5）：
- 每 500 字必须有一个"爽点"或"爽点预期"（打脸、逆袭、认可、小胜利、技能展示）。
- 压抑段落 ≤ 200 字，必须紧接反转或小胜利，禁止连续 500 字以上的纯压抑叙述。
- 开局 200 字内必须建立"逆袭预期"：让读者看到主角的潜力、资源或机遇。
- 章末必须指向"即将翻盘"而非"更多困境"，禁止以"主角陷入更大危机"结尾。
- 打脸场景要"爽"：对比鲜明、反应夸张、旁观者震惊、主角淡定或从容。

铁律：
1. 禁止自己编造数值，必须从状态卡抄
2. 禁止创建伏笔、角色或世界观规则
3. 返修时只修复质检指出的问题，不重写全文
4. 禁止违反 ChapterBrief 中明确禁止的动作

输出格式：严格按 JSON 格式输出，包含：
- title: 章节标题
- content: 正文内容
- word_count: 字数
- implemented_events: 已实现的关键事件列表
- used_plot_refs: 使用的伏笔代码列表"""

AUTHOR_SYSTEM_PROMPT += "\n\n" + CONCEPT_BUDGET_CONTRACT


class AuthorAgent(BaseAgent):
    """Author: writes chapter content."""

    agent_id = "author"

    def __init__(self, repo, llm, skill_registry: SkillRegistry | None = None, **kwargs):
        super().__init__(repo, llm, skill_registry=skill_registry, **kwargs)
        self.skill_registry = skill_registry

    @staticmethod
    def _config_max_tokens(llm, fallback: int = 6144) -> int:
        """Read max_tokens from LLM config, with fallback."""
        return int(getattr(getattr(llm, "config", None), "max_tokens", fallback) or fallback)

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
            db_review = normalize_revision_review(
                self.repo.get_latest_review(state.get("project_id"), chapter.get("id"))
            )
            if db_review:
                return db_review
        except Exception:
            logger.warning("Author: failed to load revision review fallback", exc_info=True)
        return normalize_revision_review(
            revision_review_from_quality_gate(
                state.get("quality_gate") or {},
                workflow_run_id=state.get("workflow_run_id"),
            )
        )

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
            minimum_required, recommended_target, maximum_allowed = self._word_count_bounds(word_target)
            parts.append(f"【写作指令】\n"
                         f"目标: {instruction.get('objective', '')}\n"
                         f"关键事件: {instruction.get('key_events', '')}\n"
                         f"情绪基调: {instruction.get('emotion_tone', '')}\n"
                         f"章末钩子: {instruction.get('ending_hook', '')}\n"
                         f"字数要求: 正文 content 至少 {minimum_required} 字符，"
                         f"建议写到 {recommended_target} 字符左右，"
                         f"硬上限 {maximum_allowed} 字符，低于或超过硬要求都会自动返修。")

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

        # v6.10.5: Story Contract injection
        contract_ctx = self._get_story_contract_context(project_id, "author")
        if contract_ctx:
            parts.append(contract_ctx)

        # v6.8.1: Style-aware prompt injection (webnovel excitement, suspense, romance)
        style_prompt = self._get_style_prompt_injection(project_id, "author")
        if style_prompt:
            parts.append(style_prompt)

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

        # v6.9.0: Inject ChapterBrief constraints
        chapter_brief = state.get("chapter_brief", {})
        if chapter_brief:
            brief_constraints = []
            if chapter_brief.get("forbidden_moves"):
                brief_constraints.append(f"禁止动作: {', '.join(chapter_brief['forbidden_moves'])}")
            if chapter_brief.get("chapter_goal"):
                brief_constraints.append(f"章节目标: {chapter_brief['chapter_goal']}")
            if chapter_brief.get("protagonist_agency"):
                brief_constraints.append(f"主角能动性: {chapter_brief['protagonist_agency']}")
            if brief_constraints:
                parts.append("【ChapterBrief 约束】\n" + "\n".join(brief_constraints))

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

        chapter = self._get_chapter_info(state)
        is_revision = chapter and chapter.get("status") == ChapterStatus.REVISION.value
        revision_review = self._load_revision_review(state, chapter) if is_revision else None
        if is_revision and revision_review and not state.get("_revision_review"):
            state = {
                **state,
                "_revision_review": revision_review,
            }

        context = self._build_v6_context(state)

        # v6.8.2: Validate revision context exists when in revision mode.
        # v6.8.3: Only fail-fast for real Editor rejections, NOT for quality gate
        # internal repairs (word_count_fail, death_penalty_fail, etc.) which
        # temporarily set chapter_status=REVISION without creating a review.
        if is_revision and not revision_review:
            gate = state.get("quality_gate") or {}
            is_quality_gate_retry = bool(
                gate.get("word_count_fail")
                or gate.get("death_penalty_fail")
                or gate.get("scene_beat_coverage_fail")
                or gate.get("version_regression")
                or gate.get("checks_run")
                or gate.get("blocking_issues")
            )
            if not is_quality_gate_retry:
                logger.error(
                    "Author: revision context missing for %s ch%d",
                    project_id, chapter_number,
                )
                return {
                    "error": "Author: 返修上下文缺失，无法加载 Editor 审核意见",
                    "chapter_status": state.get("chapter_status"),
                    "requires_human": True,
                    "quality_gate": {
                        "pass": False,
                        "revision_target": "author",
                        "message": "返修上下文缺失，需要人工确认后重新触发",
                        "context_missing": True,
                    },
                }
            else:
                logger.info(
                    "Author: revision context missing for %s ch%d but quality gate retry — continuing without review",
                    project_id, chapter_number,
                )

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

        # v6.10.0: 知识层（双模式）
        genre = self._get_project_genre(project_id) if self.knowledge_manager else None
        project_skill_overrides = self._get_project_skill_overrides(project_id)

        if self.knowledge_manager and self.use_agentic_mode:
            # Agentic 模式：LLM 主动咨询知识 Skill
            knowledge_selection = self._select_knowledge(
                self.agent_id,
                genre=genre,
                project_overrides=project_skill_overrides,
                target="agentic",
                token_budget=self.agent_config.get("knowledge_token_budget"),
            )
            knowledge_skills = knowledge_selection.skills if knowledge_selection else []
            if knowledge_skills:
                tool_definitions = self.knowledge_manager.to_tool_definitions(knowledge_skills)
                agentic_response = self._invoke_with_tools(
                    messages=messages,
                    tools=tool_definitions,
                    tool_executor=self.knowledge_manager.execute_tool,
                    max_tool_rounds=self.max_tool_rounds,
                    exec_events=exec_events,
                )
                # 将 agentic 结果注入 messages 作为上下文
                if agentic_response.content:
                    messages.append({
                        "role": "system",
                        "content": f"写作参考（来自知识咨询）:\n{agentic_response.content}",
                    })
                exec_events.append({
                    "event_type": "knowledge_agentic",
                    "message": "Agentic 模式：LLM 主动咨询知识",
                    "status": "info",
                    "payload": {
                        "genre": genre,
                        "rounds_used": agentic_response.rounds_used,
                        "total_tokens": agentic_response.total_tokens,
                        "knowledge_selection": (
                            knowledge_selection.to_audit_payload(agent=self.agent_id, genre=genre)
                            if knowledge_selection else {}
                        ),
                    },
                })

        elif self.knowledge_manager:
            # 默认模式：知识内容注入 prompt
            knowledge_selection = self._select_knowledge(
                self.agent_id,
                genre=genre,
                project_overrides=project_skill_overrides,
                target="prompt",
                token_budget=self.agent_config.get("knowledge_token_budget"),
            )
            knowledge_skills = knowledge_selection.skills if knowledge_selection else []
            if knowledge_skills:
                knowledge_context = "\n\n---\n\n".join(
                    f"## {s.name}\n\n{s.content}" for s in knowledge_skills
                )
                messages.append({
                    "role": "system",
                    "content": f"写作规范参考（请在创作时遵循以下规范）:\n\n{knowledge_context}",
                })
                if knowledge_selection and knowledge_selection.trimmed_skill_ids:
                    exec_events.append({
                        "event_type": "knowledge_budget_trimmed",
                        "message": f"知识注入预算裁剪：{len(knowledge_selection.trimmed_skill_ids)} 个 Skill 未注入",
                        "status": "warning",
                        "payload": knowledge_selection.to_audit_payload(agent=self.agent_id, genre=genre),
                    })
                exec_events.append({
                    "event_type": "knowledge_injected",
                    "message": f"已注入写作规范知识：{len(knowledge_skills)} 个 Skill",
                    "status": "info",
                    "payload": (
                        knowledge_selection.to_audit_payload(agent=self.agent_id, genre=genre)
                        if knowledge_selection else {"genre": genre}
                    ),
                })

        if self._should_use_plain_text_primary(state):
            try:
                output = self._try_plain_text_draft(state, task_desc, context, exec_events=exec_events, on_chunk=self.on_text_chunk)
            except Exception as e:
                gate = state.get("quality_gate") or {}
                if gate.get("internal_repair") and not gate.get("consume_revision_retry", True):
                    repair_scope = gate.get("repair_scope") or "internal_word_count_compression"
                    message = f"内部修复({repair_scope})调用失败: {e}"
                    logger.warning("Author: %s", message)
                    return {
                        "error": message,
                        "chapter_status": state.get("chapter_status"),
                        "quality_gate": {
                            **gate,
                            "pass": False,
                            "revision_target": gate.get("revision_target") or "author",
                            "agent": gate.get("agent") or "author",
                            "word_count_fail": gate.get("word_count_fail", True),
                            "message": message,
                            "workflow_run_id": state.get("workflow_run_id"),
                            "internal_repair": True,
                            "consume_revision_retry": False,
                            "repair_scope": repair_scope,
                            "internal_repair_failed": True,
                        },
                        "_exec_events": exec_events,
                    }
                raise
            exec_events.append({
                "event_type": "long_form_generation",
                "message": "使用长文直写模式生成，避免长章节 JSON 截断",
                "status": "info",
                "payload": {"mode": "plain_text_primary"},
            })
        else:
            try:
                raw = self._invoke_json(messages, schema=AuthorOutput)
                output = AuthorOutput(**normalize_declared_word_count(raw))
            except OutputValidationError:
                if state.get("llm_mode") != "real":
                    raise
                logger.warning(
                    "Author: structured JSON output failed; retrying with plain-text drafting fallback"
                )
                output = self._try_plain_text_draft(state, task_desc, context, on_chunk=self.on_text_chunk)
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
            upper_passed, upper_msg = check_word_count_upper_gate(body_content, wt, "author")
            if not upper_passed:
                issues.append({"type": "word_count_overflow", "message": upper_msg})

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
            # v6.8.5: 阈值从 5% 提升到 10%，与 Editor 和 Prompt 规则保持一致
            # v6.8.5-fix: 保持 warning 级别，依赖 editor_strategy.determine_revision_target()
            # 中的路由关键词修复确保 LOW_DIALOGUE_RATIO 返修路由到 Author 而非 Polisher
            if dialogue_ratio < 0.10:
                warnings_list.append(
                    f"dialogue: 对白占比 {dialogue_ratio*100:.1f}%（低于 10%），"
                    "必须增加有冲突或潜台词的角色对话"
                )

            # v6.8.5: Exposition paragraph detection (warning only)
            # Split by double newlines to get paragraphs, check for pure exposition
            paragraphs = [p.strip() for p in re.split(r'\n\s*\n', out.content) if p.strip()]
            exposition_count = 0
            for para in paragraphs:
                if len(para) < 50:
                    continue
                has_dialogue = bool(re.search(r'[""「『].*?[""」』]', para))
                has_action = bool(re.search(r'[走跑跳拿放推拉打踢砍刺冲撞闪躲握抓扔抛甩]|站起|坐下|转身|回头|低头|抬头|靠近|后退|推开|抓住', para))
                has_sensory = bool(re.search(r'[光影视声响味香臭冷热湿风雨雷温度颜色]|听到|看到|闻到|感到|摸到', para))
                if not has_dialogue and not has_action and not has_sensory:
                    exposition_count += 1
            if exposition_count > 3:
                warnings_list.append(
                    f"exposition: 检测到 {exposition_count} 处纯说明段落（无对白/动作/感官），"
                    "建议将设定解释融入角色行为或对话中"
                )

            # v6.8.5: Ending hook strength check (warning only)
            last_200 = out.content[-200:] if len(out.content) > 200 else out.content
            hook_markers = [
                r'[？\?]',  # 疑问句
                r'难道|莫非|竟然|居然',  # 意外
                r'必须|不得不|只能|只有',  # 抉择
                r'突然|忽然|骤然|猛然',  # 转折
                r'可是|但是|然而|只是',  # 转折
                r'如果|要是|倘若|万一',  # 假设悬念
                r'不能|不可|不准|不许',  # 禁令悬念
            ]
            hook_count = sum(1 for m in hook_markers if re.search(m, last_200))
            has_unfinished_action = bool(re.search(r'[走跑冲跳]|靠近|推开|抓住|拔出|打开|按下|转身', last_200))
            if hook_count == 0 and not has_unfinished_action:
                warnings_list.append(
                    "ending_hook: 章末200字缺乏悬念标记（问句/转折/抉择/未完成动作），"
                    "建议在结尾增加悬念或未完成的动作"
                )

            # v6.8.5: Title integration check (warning only)
            title_text = out.title or ""
            if title_text:
                # Extract meaningful keywords from title (2+ chars, skip common words)
                title_keywords = [kw for kw in re.findall(r'[一-鿿]{2,}', title_text)
                                  if kw not in ('章节', '第章', '章', '卷', '篇', '部', '上', '下', '前', '后')]
                missing_keywords = [kw for kw in title_keywords if kw not in out.content]
                if missing_keywords and len(missing_keywords) == len(title_keywords):
                    warnings_list.append(
                        f"title_integration: 标题关键词 {missing_keywords} 未在正文中出现，"
                        "建议通过角色对话或场景描写自然融入标题元素"
                    )

            repairable = any(
                i["type"] in ("word_count", "word_count_overflow", "death_penalty", "scene_beat_coverage")
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
            upper_passed, upper_msg = check_word_count_upper_gate(body_content, wt, "author")
            if not upper_passed:
                compressed = self._try_compress_overlong_output(state, out, upper_msg)
                if compressed is not None:
                    return {"output": compressed}
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
            # v6.8.0: Return original output instead of None.
            # None signals "repair failed" to self_check, triggering an error.
            # Returning the original lets the loop continue — the issue will
            # be surfaced to Editor for judgment.
            return {"output": out}

        loop_result = loop.run(_generate_wrap, _self_check_wrap, _repair_wrap)
        output = loop_result["output"]
        trace = loop_result.get("_trace", {})
        autonomy = loop_result.get("_autonomy", {})
        final_scene_coverage_issues = self._scene_beat_coverage_issues(state, output.content)
        if final_scene_coverage_issues:
            # v6.8.0: Downgrade to warning after loop exhaustion.
            # The repair loop already injected specific beat issues into the
            # retry prompt — if the model still can't cover all beats, forcing
            # another workflow-level retry won't help. Let Editor judge instead.
            missing = [i.get("message", "") for i in final_scene_coverage_issues]
            logger.warning(
                "Author: scene beat coverage incomplete after repair attempts: %s",
                "; ".join(missing[:3]),
            )
            exec_events.append({
                "event_type": "scene_beat_coverage_warning",
                "message": f"场景 beat 覆盖不完整（{len(missing)} 项），已降级为警告",
                "status": "warning",
                "payload": {
                    "issues": missing,
                    "downgraded": True,
                },
            })
        self_check_data = trace.get("self_check", {}) if isinstance(trace, dict) else {}
        sc_passed = self_check_data.get("passed", True)
        sc_issues = self_check_data.get("issues", [])
        sc_warnings = self_check_data.get("warnings", [])
        exec_events.append({
            "event_type": "self_check_completed",
            "message": f"自检{'通过' if sc_passed else f'未通过 ({len(sc_issues)} 个问题)'}"
            f"{'，' + str(len(sc_warnings)) + ' 个警告' if sc_warnings else ''}",
            "status": "info" if sc_passed or len(sc_issues) <= 1 else "warning",
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
            if issue_types and issue_types.issubset({"death_penalty", "word_count", "word_count_overflow"}):
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
        after_llm_hook = run_agent_skills(
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
            honor_manifest_failure_policy=True,
        )
        
        # v6.8.5: Check if any validator skill failed with blocking policy
        if not after_llm_hook.ok:
            blocking_error = after_llm_hook.blocking_error
            logger.warning("Author: after_llm skill hook failed: %s", blocking_error)
            exec_events.append({
                "event_type": "skill_blocked",
                "message": f"执笔稿被 Skill 阻断：{blocking_error}",
                "status": "blocking",
                "payload": {"stage": "after_llm", "blocking_error": blocking_error},
            })
            # Find the specific skill that failed for revision targeting
            revision_target = "author"
            for skill_item in after_llm_hook.skill_results:
                if not skill_item.get("ok"):
                    skill_id = skill_item.get("skill_id", "")
                    if "excitement" in skill_id:
                        revision_target = "author"
                        break
                    elif "death" in skill_id:
                        revision_target = "author"
                        break
                    elif "event" in skill_id:
                        revision_target = "author"
                        break
            
            return {
                "error": f"执笔稿质量检查未通过: {blocking_error}",
                "chapter_status": state.get("chapter_status"),
                "quality_gate": {
                    "pass": False,
                    "revision_target": revision_target,
                    "skill_fail": True,
                    "message": blocking_error,
                    "agent": "author",
                    "workflow_run_id": state.get("workflow_run_id"),
                    "skill_results": after_llm_hook.skill_results,
                },
                "_trace": trace,
                "_autonomy": autonomy,
            }

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

        upper_gate_passed, upper_gate_msg = check_word_count_upper_gate(
            body_content, word_target, "author"
        )
        if not upper_gate_passed:
            compressed = self._try_compress_overlong_output(state, output, upper_gate_msg)
            if compressed is not None:
                output = compressed
                self.validate_output(output.model_dump())
                body_content = strip_chapter_heading(output.content, chapter_number, output.title)
                word_gate_passed, word_gate_msg = check_word_count_quality_gate(
                    body_content, word_target, "author"
                )
                upper_gate_passed, upper_gate_msg = check_word_count_upper_gate(
                    body_content, word_target, "author"
                )
                if word_gate_passed and upper_gate_passed:
                    exec_events.append({
                        "event_type": "word_count_compressed",
                        "message": "执笔稿超出字数上限，已自动压缩后继续",
                        "status": "info",
                        "payload": {"agent": "author", "word_target": word_target},
                    })

            if not word_gate_passed:
                logger.warning("Author: word count quality gate failed after compression: %s", word_gate_msg)
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
                        # v6.7.8: internal compression failure does not consume
                        # chapter-level revision retries.
                        "internal_repair": True,
                        "consume_revision_retry": False,
                        "repair_scope": "internal_word_count_compression",
                    },
                    "_trace": trace,
                    "_autonomy": autonomy,
                }
            if not upper_gate_passed:
                logger.warning("Author: word count upper gate failed: %s", upper_gate_msg)
                from ..validators.chapter_checker import count_words
                actual_wc = count_words(body_content)
                return {
                    "error": f"字数质量门未通过: {upper_gate_msg}",
                    "chapter_status": state.get("chapter_status"),
                    "quality_gate": {
                        "pass": False,
                        "revision_target": "author",
                        "word_count_fail": True,
                        "message": upper_gate_msg,
                        "actual_word_count": actual_wc,
                        "word_target": word_target,
                        "agent": "author",
                        "workflow_run_id": state.get("workflow_run_id"),
                        # v6.7.8: internal compression failure does not consume
                        # chapter-level revision retries.
                        "internal_repair": True,
                        "consume_revision_retry": False,
                        "repair_scope": "internal_word_count_compression",
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
            expansion_limit = max(500, int(original_wc * 0.15))
            expansion_tolerance = max(80, int(original_wc * 0.03))
            overexpanded = (
                original_wc > 0
                and wc_delta > expansion_limit + expansion_tolerance
                and not self._revision_requests_compression(revision_review or {})
            )
            exec_events.append({
                "event_type": "revision_diff_generated",
                "message": f"返修改动：{original_wc} → {revised_wc} 字（{'内容几乎未变' if low_change else f'变化 {wc_delta:+d} 字'}）",
                "status": "warning" if (low_change or overexpanded) else "info",
                "payload": {
                    "original_word_count": original_wc,
                    "revised_word_count": revised_wc,
                    "word_count_delta": wc_delta,
                    "low_change_warning": low_change,
                    "overexpanded_warning": overexpanded,
                    "expansion_limit": expansion_limit,
                    "expansion_tolerance": expansion_tolerance,
                },
            })
            if overexpanded:
                reason = (
                    f"返修稿异常膨胀：{original_wc} → {revised_wc} 字，"
                    f"增长 {wc_delta} 字，超过允许增长 {expansion_limit} 字；"
                    "Editor 未要求扩写，已保留上一版本"
                )
                self.repo.save_artifact(
                    project_id,
                    chapter_number,
                    "author",
                    "rejected_regression",
                    content_json={
                        "title": output.title,
                        "content": output.content,
                        "rejection_reason": reason,
                        "revision_source_review_id": (revision_review or {}).get("review_id"),
                        "original_word_count": original_wc,
                        "revised_word_count": revised_wc,
                        "word_count_delta": wc_delta,
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
                        "revision_overexpanded": True,
                        "consume_revision_retry": False,
                        "message": reason,
                    },
                    "_revision_review": revision_review,
                    "_exec_events": exec_events,
                }

        # v6.6.0: Do not let a revision candidate overwrite a stronger
        # existing draft when it clearly regresses.
        if is_revision and chapter and chapter.get("content"):
            reject, reason = self._should_reject_revision_continuity_regression(
                current_content=chapter.get("content", "") or "",
                candidate_content=output.content,
                chapter_number=chapter_number,
                current_title=chapter.get("title"),
                candidate_title=output.title,
                revision_review=revision_review or {},
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
                        "revision_source_review_id": (revision_review or {}).get("review_id"),
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
                        "revision_continuity_regression": True,
                        "message": reason,
                    },
                    "_revision_review": revision_review,
                    "_exec_events": exec_events,
                }

            from ..quality.version_regression_guard import VersionRegressionGuard

            revision_review = revision_review or {}
            system_compressed = any(
                ev.get("event_type") == "word_count_compressed"
                for ev in exec_events
            )
            reject, reason = VersionRegressionGuard.should_reject_new_draft(
                chapter.get("content", "") or "",
                output.content,
                self._get_word_target(state),
                editor_suggestions=revision_review.get("suggestions", []),
                allow_system_compression=system_compressed,
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
            # v6.8.1: Check if chapter is already at or past DRAFTED (recovery run)
            # If so, skip status advance — the chapter was already advanced in a previous run
            current_status = self.repo.get_chapter_status(project_id, chapter_number)
            _STATUS_ORDER = {
                "idea": 0, "outlined": 1, "planned": 2, "scripted": 3,
                "drafted": 4, "polished": 5, "review": 6, "reviewed": 7,
                "revision": 8, "published": 9, "blocking": 10,
            }
            current_order = _STATUS_ORDER.get(current_status, -1)
            drafted_order = _STATUS_ORDER.get("drafted", 4)
            if current_order >= drafted_order:
                logger.info(
                    "Author: chapter already at '%s' (order %d >= %d), skipping status advance (recovery run)",
                    current_status, current_order, drafted_order,
                )
            else:
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

    @staticmethod
    def _should_reject_revision_continuity_regression(
        *,
        current_content: str,
        candidate_content: str,
        chapter_number: int,
        current_title: str | None,
        candidate_title: str | None,
        revision_review: dict[str, Any] | None,
    ) -> tuple[bool, str]:
        """Reject revision drafts that reintroduce an explicitly flagged bad opening."""
        review_text = "\n".join(
            str(item)
            for item in [
                *((revision_review or {}).get("issues") or []),
                *((revision_review or {}).get("suggestions") or []),
            ]
        )
        if not any(marker in review_text for marker in ("章首", "开头", "章间衔接", "时空断裂", "直接从")):
            return False, ""

        current_body = strip_chapter_heading(current_content, chapter_number, current_title).strip()
        candidate_body = strip_chapter_heading(candidate_content, chapter_number, candidate_title).strip()
        if not current_body or not candidate_body:
            return False, ""

        candidate_opening = candidate_body[:900]
        current_opening = current_body[:900]

        required_anchor_groups: list[tuple[str, ...]] = []
        if "宴会厅" in review_text and "主位" in review_text:
            required_anchor_groups.append(("宴会厅", "主位"))
        if "云澜" in review_text and "会馆" in review_text and "主位" in review_text:
            required_anchor_groups.append(("云澜", "主位"))

        stale_opening_terms: list[str] = []
        if any(marker in review_text for marker in ("出租车", "倒叙", "离开公司", "时空断裂")):
            stale_opening_terms.extend([
                "离开公司",
                "公司走廊",
                "叫了车",
                "车上",
                "下车步行",
                "会馆正门",
                "黑西装保安",
                "内部包场",
            ])

        misses_required_anchor = bool(required_anchor_groups) and not any(
            all(term in candidate_opening for term in group)
            for group in required_anchor_groups
        )
        reintroduces_stale_opening = any(term in candidate_opening for term in stale_opening_terms)

        if misses_required_anchor and reintroduces_stale_opening:
            return (
                True,
                "返修稿开头重新回到 Editor 已指出的旧时空线，未按退回意见从当前场景接笔",
            )

        if required_anchor_groups and any(
            all(term in current_opening for term in group)
            for group in required_anchor_groups
        ) and misses_required_anchor:
            return (
                True,
                "返修稿丢失当前保留稿的章首连续性锚点，疑似使用了旧稿作为底稿",
            )

        return False, ""

    def validate_output(self, output: dict) -> None:
        AuthorOutput(**output)
        # Hard validation: schema, word_count match, death penalty.
        # Skip word-count range here — the retryable quality gate handles it
        # so short drafts route to revision instead of blocking.
        violations = validate_chapter_output(output, check_min_words=False, check_max_words=False)
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
            raw = self._invoke_json(messages, schema=AuthorOutput)
            expanded = AuthorOutput(**normalize_declared_word_count(raw))
            expanded = self._sanitize_output(expanded, state)
            self.validate_output(expanded.model_dump())
            return expanded
        except Exception as e:
            logger.warning("Author: expand-short-output retry failed: %s", e)
            return None

    def _try_compress_overlong_output(
        self,
        state: FactoryState,
        output: AuthorOutput,
        upper_gate_msg: str,
    ) -> AuthorOutput | None:
        """Ask the LLM once to compress an overlong complete draft."""
        if state.get("llm_mode") != "real":
            return None

        instruction = self._get_instruction(state)
        project = self.repo.get_project(state["project_id"])
        word_target = derive_word_target(instruction, project)
        minimum_required = int(word_target * 0.85)
        maximum_allowed = max(word_target + 1200, int(word_target * 1.6))

        messages = [
            {"role": "system", "content": AUTHOR_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"第{state['chapter_number']}章正文超过字数硬闸门：{upper_gate_msg}。\n"
                    f"请压缩正文到 {minimum_required} 到 {maximum_allowed} 字符之间，"
                    "必须保留已实现关键事件、伏笔、事实、角色动机和章末钩子。"
                    "只删除重复铺陈、冗余心理解释、重复环境描写和同义反复，"
                    "不要新增事件，不要改成摘要。\n"
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
            raw = self._invoke_json(messages, schema=AuthorOutput)
            compressed = AuthorOutput(**normalize_declared_word_count(raw))
            compressed = self._sanitize_output(compressed, state)
            self.validate_output(compressed.model_dump())
            body_content = strip_chapter_heading(
                compressed.content, state["chapter_number"], compressed.title
            )
            lower_passed, _ = check_word_count_quality_gate(body_content, word_target, "author")
            upper_passed, _ = check_word_count_upper_gate(body_content, word_target, "author")
            coverage_issues = self._scene_beat_coverage_issues(state, compressed.content)
            if lower_passed and upper_passed and not coverage_issues:
                return compressed
        except Exception as e:
            logger.warning("Author: compress-overlong-output retry failed: %s", e)
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

    @staticmethod
    def _is_generic_ending_hook(text: Any) -> bool:
        """Return true for planner placeholder hooks with no concrete content.

        These hooks describe the function of an ending ("leave a new clue")
        rather than a literal story element. Requiring their exact terms in the
        tail creates false retry loops; concrete final scene beat checks still
        enforce that the chapter lands on a real hook.
        """
        raw = re.sub(r"[\s，。！？、；：,.!?;:]+", "", str(text or ""))
        if not raw:
            return False
        generic_hooks = {
            "悬念",
            "新悬念",
            "留下悬念",
            "留下新悬念",
            "留下线索",
            "留下新线索",
            "留下新的线索",
            "留下未解线索",
            "留下新的未解线索",
            "新的未解线索",
            "留下一条新线索",
            "留下可继续追踪的钩子",
            "留下新的可追踪线索",
        }
        return raw in generic_hooks

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
        terms: list[str] = []
        for field in ("hook", "turn", "scene_goal"):
            for term in self._scene_terms(final_beat.get(field)):
                if term not in terms:
                    terms.append(term)
        if terms and not any(term in tail for term in terms[:10]):
            issues.append({
                "type": "scene_beat_coverage",
                "message": f"正文尾段缺少第 {sequence} 个 scene beat 的关键落点: {', '.join(terms[:5])}",
                "sequence": sequence,
                "required_terms": terms[:10],
            })

        instruction = self._get_instruction(state) or {}
        ending_hook = instruction.get("ending_hook", "")
        ending_terms = self._scene_terms(ending_hook)
        if (
            ending_terms
            and not self._is_generic_ending_hook(ending_hook)
            and not any(term in tail for term in ending_terms[:8])
        ):
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

        appended = self._try_append_scene_beat_tail(
            state, output, coverage_issues, fallback_context,
        )
        if appended is not None:
            return appended

        instruction = self._get_instruction(state) or {}
        word_target = self._get_word_target(state)
        current_body_len = count_words(strip_chapter_heading(output.content, state["chapter_number"], output.title))
        minimum_required = max(int(word_target * 0.85), int(current_body_len * 0.9))
        target_hint = max(word_target, current_body_len)
        compact_context = self._build_plain_text_context(state, fallback_context)
        issue_lines = "\n".join(
            f"- {issue.get('message', '')}" for issue in coverage_issues
        )
        config_max = self._config_max_tokens(self.llm)
        prose_max_tokens = max(2048, min(config_max, int(word_target * 2.0)))
        per_call_retries = None

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
            if self._scene_beat_coverage_issues(state, repaired.content):
                return None
            return repaired
        except Exception as e:
            logger.warning("Author: scene-beat coverage repair failed: %s", e)
            return None

    def _try_append_scene_beat_tail(
        self,
        state: FactoryState,
        output: AuthorOutput,
        coverage_issues: list[dict[str, Any]],
        fallback_context: str,
    ) -> AuthorOutput | None:
        """Append a missing final beat tail before falling back to full rewrite."""
        instruction = self._get_instruction(state) or {}
        beats = self._get_scene_beats(state)
        if not beats:
            return None

        chapter_number = state["chapter_number"]
        current_body = strip_chapter_heading(output.content, chapter_number, output.title)
        current_tail = current_body[-900:] if len(current_body) > 900 else current_body
        final_beats = beats[-min(3, len(beats)):]
        beat_lines = "\n".join(
            f"{beat.get('sequence', '?')}. 目标: {beat.get('scene_goal', '')} | "
            f"冲突: {beat.get('conflict', '')} | 转折: {beat.get('turn', '')} | "
            f"钩子: {beat.get('hook', '')}"
            for beat in final_beats
        )
        issue_lines = "\n".join(
            f"- {issue.get('message', '')}" for issue in coverage_issues
        )
        compact_context = self._build_plain_text_context(state, fallback_context)
        tail_target = max(450, min(1200, int(self._get_word_target(state) * 0.35)))
        prose_max_tokens = max(1024, min(3072, int(tail_target * 1.8) + 512))

        messages = [
            {
                "role": "system",
                "content": (
                    "你是网文工厂的执笔。现在只补写章节结尾续写段落。"
                    "只输出可直接接在当前正文后的纯正文，不要标题、解释、清单、JSON 或 Markdown。"
                    "必须自然承接当前尾段，补齐最后 scene beat，并以章节 ending_hook 收束。"
                    "禁止复述已写正文，禁止从开头重写。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"第{chapter_number}章当前正文没有写到章末，缺口如下：\n{issue_lines}\n\n"
                    f"请续写约 {tail_target} 字符，只补结尾，不要重写前文。\n\n"
                    f"{compact_context}\n\n"
                    f"【必须落地的最后 scene beat】\n{beat_lines}\n\n"
                    f"【章节 ending_hook】\n{instruction.get('ending_hook', '')}\n\n"
                    f"【当前正文尾段】\n{current_tail}\n\n"
                    "请输出可直接追加到正文末尾的续写正文。"
                ),
            },
        ]

        try:
            tail = self._invoke_text_for_author(
                messages,
                temperature=0.66,
                max_tokens=prose_max_tokens,
                max_retries=None,
                request_timeout_seconds=(
                    AUTHOR_LONG_FORM_TIMEOUT_SECONDS
                    if is_configured_live_provider(self.llm)
                    else None
                ),
            )
            tail = self._coerce_plain_text_content(tail)
            if not tail:
                return None

            merged = self._merge_segment_outputs([output.content, tail])
            repaired = AuthorOutput(
                title=self._derive_title(state, instruction, merged),
                content=merged,
                word_count=len(merged),
                implemented_events=output.implemented_events or self._instruction_items(instruction.get("key_events", "")),
                used_plot_refs=output.used_plot_refs or self._instruction_items(instruction.get("plots_to_plant", "")),
            )
            repaired = self._sanitize_output(repaired, state)
            self.validate_output(repaired.model_dump())
            if self._scene_beat_coverage_issues(state, repaired.content):
                return None
            return repaired
        except Exception as e:
            logger.warning("Author: scene-beat tail append repair failed: %s", e)
            return None

    @staticmethod
    def _revision_requests_compression(revision_review: dict[str, Any] | None) -> bool:
        suggestions = (revision_review or {}).get("suggestions") or []
        issues = (revision_review or {}).get("issues") or []
        text = "\n".join(str(item) for item in [*suggestions, *issues])
        keywords = [
            "压缩", "缩短", "精简", "删减", "去掉", "减少",
            "过长", "冗余", "啰嗦", "拖沓", "重复",
            "字数过多", "篇幅过大", "超出", "超标",
        ]
        return any(kw in text for kw in keywords)

    @staticmethod
    def _revision_blocking_priority_block(revision_review: dict[str, Any] | None) -> str:
        """Extract hard revision issues that must dominate the rewrite plan."""
        if not revision_review:
            return ""
        issues = (revision_review or {}).get("issues") or []
        suggestions = (revision_review or {}).get("suggestions") or []
        hard_markers = (
            "不可违背事实",
            "事实一致性违规",
            "事实锁",
            "Hard Constraints",
            "硬约束",
            "时间线",
            "章间衔接",
            "QualityGate",
            "质量门",
            "质检门禁",
            "连续性阻断",
            "连续性修复",
            "关键情节缺失",
            "必须",
            "直接违反",
            "硬冲突",
            "标题与正文脱节",
            "标题关键词",
            "时空回退",
        )
        priority_items = [
            str(item).strip()
            for item in issues
            if str(item).strip() and any(marker in str(item) for marker in hard_markers)
        ][:6]
        if not priority_items:
            return ""

        suggestion_items = [
            str(item).strip()
            for item in suggestions
            if str(item).strip() and any(marker in str(item) for marker in hard_markers)
        ][:4]
        lines = [
            "【返修硬阻断优先级】",
            "必须先修复以下硬阻断问题，再考虑语言润色、感官细节或节奏微调；不得只做语言润色。",
            "若退回问题涉及不可违背事实、Hard Constraints、时间线或章间衔接，必须直接改写相关剧情事实和场景顺序。",
            "若涉及 QualityGate / 质检门禁阻断，必须逐条消解，返修稿中不得再次出现同名阻断。",
            "章间衔接问题：章首必须明确承接上一章最后的时间、地点、动作或系统提示，不允许直接跳到新场景。",
            "时空回退问题：禁止用“十分钟前/刚才/回到前台”等方式回到已完成旧场景；如必须回忆，必须明确标注为短暂闪回且不重演旧事件。",
            "标题正文问题：标题核心关键词必须以原词自然落入正文关键场景；做不到就改成正文真实发生过的标题。",
            "硬阻断问题:",
            *[f"- {item}" for item in priority_items],
        ]
        if suggestion_items:
            lines.extend(["硬阻断修复建议:", *[f"- {item}" for item in suggestion_items]])
        lines.extend([
            "返修完成前必须在内部自检，禁止把以下清单或回执写入正文：",
            "- 章首已承接上一章钩子；",
            "- 标题关键词已在正文出现或标题已改；",
            "- 没有无标注时空回退；",
            "- QualityGate 阻断项已逐条消解。",
        ])
        return "\n".join(lines)

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
        per_call_retries = None

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
        exec_events: list[dict] | None = None,
        on_chunk: Any | None = None,
    ) -> AuthorOutput:
        """Generate prose directly when real models fail long-form JSON output.

        Long prose is much more likely than short structured outputs to be
        wrapped in Markdown or truncated before the closing JSON brace. For
        production writing, preserve progress by generating plain chapter text
        and deriving the small metadata fields deterministically.
        """
        beats = self._get_scene_beats(state)
        if state.get("llm_mode") == "real" and task_desc != "返修" and len(beats) >= 4:
            return self._try_segmented_plain_text_draft(state, task_desc, context, exec_events=exec_events, on_chunk=on_chunk)

        project_id = state["project_id"]
        chapter_number = state["chapter_number"]
        instruction = self._get_instruction(state) or {}
        word_target = self._get_word_target(state)
        minimum_required, _, maximum_allowed = self._word_count_bounds(word_target)
        effective_target = word_target
        length_guard_note = (
            f"正文至少 {minimum_required} 字符，建议接近 {word_target} 字符；"
            f"硬上限 {maximum_allowed} 字符，最多不要超过 {maximum_allowed} 字符。"
        )
        revision_source_section = ""
        revision_priority_section = ""
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
            revision_priority_section = self._revision_blocking_priority_block(revision_review)
            compress_requested = self._revision_requests_compression(revision_review)
            if existing_len > 0 and not compress_requested:
                minimum_required = max(minimum_required, int(existing_len * 0.9))
                effective_target = max(word_target, existing_len)
                expansion_limit = max(500, int(existing_len * 0.15))
                upper_bound = existing_len + expansion_limit
                length_guard_note = (
                    f"【返修篇幅边界】当前保留稿约 {existing_len} 字符，Editor 未要求压缩；"
                    "这次是补丁式返修，不是重新扩写。"
                    f"返修必须保留完整篇幅，不要主动压缩。正文至少 {minimum_required} 字符，"
                    f"返修后总篇幅应基本持平，建议接近 {effective_target} 字符，合理上限 {upper_bound} 字符。"
                    f"最大允许新增 {expansion_limit} 字符，超过此新增上限会被系统拒绝；"
                    "只替换或压缩退回问题涉及的句段，新增句子必须同步删除等量冗余说明。"
                )
        config_max = self._config_max_tokens(self.llm)
        # v6.9.0: Chinese text needs ~2-2.5 tokens per character, use 2.5x
        prose_max_tokens = max(1024, min(config_max, int(effective_target * 2.5)))
        compact_context = self._build_plain_text_context(state, context)
        per_call_retries = None

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
                    "\n【反说明段落规则】"
                    "禁止连续超过100字的纯说明/旁白段落。每段说明后必须紧跟角色动作、对白或环境反馈。"
                    "设定、背景、能力解释必须融入角色行为或对话中，不得独立成段。"
                    "检测标准：如果一段文字没有对白引号、没有动作动词、没有感官描写，就是说明段落——必须改写。"
                    "\n【章末钩子规则】"
                    "最后200字必须包含以下至少一种：悬念问句、未完成的动作、角色的艰难抉择、意外信息揭露、冲突升级。"
                    "禁止以'总结本章'、'归纳意义'、'主角反思'结尾。必须让读者想翻下一页。"
                    "\n【对白比例规则】"
                    "对白占比至少10%。每500字至少有一段角色对话。对话必须有冲突、潜台词或信息交换，禁止功能化问答。"
                    "\n【标题整合规则】"
                    "章节标题的关键词必须在正文中至少出现一次，通过角色对话、内心活动或场景描写自然融入。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"项目ID: {project_id}\n章节号: {chapter_number}\n任务: {task_desc}\n"
                    f"{length_guard_note}\n\n"
                    f"{revision_priority_section}\n\n"
                    f"{compact_context}\n\n"
                    f"{revision_source_section}\n"
                    f"请直接写第{chapter_number}章正文。"
                ),
            },
        ]

        # v6.8.5: Truncation retry — if finish_reason=length, retry with 1.5x
        # max_tokens (capped at 8192) to give the model enough room.
        try:
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
                on_chunk=on_chunk or self.on_text_chunk,
            ).strip()
        except LLMError as e:
            if "finish_reason=length" not in str(e):
                raise
            config_max = self._config_max_tokens(self.llm)
            retry_max = min(config_max, int(prose_max_tokens * 1.5))
            logger.warning(
                "Author: truncation detected (max_tokens=%d), retrying with max_tokens=%d",
                prose_max_tokens, retry_max,
            )
            if exec_events is not None:
                exec_events.append({
                    "event_type": "truncation_retry",
                    "message": f"Author 输出被截断，使用 max_tokens={retry_max} 重试",
                    "status": "warning",
                    "payload": {
                        "original_max_tokens": prose_max_tokens,
                        "retry_max_tokens": retry_max,
                    },
                })
            content = self._invoke_text_for_author(
                messages,
                temperature=0.7,
                max_tokens=retry_max,
                max_retries=per_call_retries,
                request_timeout_seconds=(
                    AUTHOR_LONG_FORM_TIMEOUT_SECONDS
                    if is_configured_live_provider(self.llm)
                    else None
                ),
                on_chunk=on_chunk or self.on_text_chunk,
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
                on_chunk=on_chunk or self.on_text_chunk,
            ).strip()
            content = self._coerce_plain_text_content(content)
        if not content:
            fallback = self._local_revision_fallback_from_existing(state, instruction)
            if fallback is not None:
                if exec_events is not None:
                    exec_events.append({
                        "event_type": "fallback_used",
                        "message": "Author 返修纯正文返回为空，已使用当前保留稿做本地最小返修兜底",
                        "status": "warning",
                        "payload": {"fallback_type": "local_revision_patch"},
                    })
                return fallback
            raise OutputValidationError("Author 纯正文生成空内容（已重试一次）")

        title = self._derive_title(state, instruction, content)
        return AuthorOutput(
            title=title,
            content=content,
            word_count=len(content),
            implemented_events=self._instruction_items(instruction.get("key_events", "")),
            used_plot_refs=self._instruction_items(instruction.get("plots_to_plant", "")),
        )

    def _local_revision_fallback_from_existing(
        self,
        state: FactoryState,
        instruction: dict[str, Any],
    ) -> AuthorOutput | None:
        """Return a conservative local patch when revision LLM returns empty.

        Empty provider responses are operational failures, not proof that the
        saved draft is unusable. In revision mode, keep the current draft and
        apply only deterministic seam/title patches so the workflow can
        continue to the normal quality gates instead of blocking immediately.
        """
        if state.get("chapter_status") != ChapterStatus.REVISION.value:
            return None

        chapter_number = state["chapter_number"]
        chapter = self._get_chapter_info(state) or {}
        existing = str(chapter.get("content") or "").strip()
        body = strip_chapter_heading(existing, chapter_number, chapter.get("title")).strip()
        if not body:
            return None

        patched = body
        feedback_text = self._revision_feedback_text(state)
        if "章间衔接" in feedback_text or "时间" in feedback_text or "地点" in feedback_text:
            bridge = self._local_seam_bridge_sentence(feedback_text)
            if bridge and bridge not in patched[:600]:
                patched = f"{bridge}\n\n{patched}"

        existing_title = str(chapter.get("title") or "").strip()
        title = (
            existing_title
            if self._is_usable_chapter_title(existing_title, chapter_number, instruction)
            else self._title_from_instruction(instruction, chapter_number) or f"第{chapter_number}章"
        )
        if ("标题与正文脱节" in feedback_text or "标题关键词" in feedback_text) and title:
            title_keyword = re.sub(r"^第\s*[一二三四五六七八九十百千零〇两\d]+\s*章\s*[:：、.\-—]?\s*", "", title).strip()
            if title_keyword and title_keyword not in patched:
                # v6.10.5: Neutral phrasing, no hardcoded pronoun.
                patched = f"{patched}\n\n{title_keyword}四个字，在心头落得很重。"

        patched = ensure_chapter_heading(patched, title, chapter_number)
        output = AuthorOutput(
            title=title,
            content=patched,
            word_count=len(strip_chapter_heading(patched, chapter_number, title)),
            implemented_events=self._instruction_items(instruction.get("key_events", "")),
            used_plot_refs=self._instruction_items(instruction.get("plots_to_plant", "")),
        )
        return self._sanitize_output(output, state)

    @staticmethod
    def _revision_feedback_text(state: FactoryState) -> str:
        parts: list[str] = []
        review = state.get("_revision_review") or {}
        if isinstance(review, dict):
            parts.extend(str(item) for item in review.get("issues") or [])
            parts.extend(str(item) for item in review.get("suggestions") or [])
        gate = state.get("quality_gate") or {}
        if isinstance(gate, dict):
            parts.extend(str(item) for item in gate.get("blocking_issues") or [])
            parts.extend(str(item) for item in gate.get("priority_issues") or [])
            parts.extend(str(item) for item in gate.get("advisory_issues") or [])
            if gate.get("message"):
                parts.append(str(gate.get("message")))
        return "\n".join(item for item in parts if item.strip())

    @staticmethod
    def _local_seam_bridge_sentence(feedback_text: str) -> str:
        time_match = re.search(r"时间节点[“\"]([^”\"]+)[”\"]", feedback_text)
        place_match = re.search(r"地点[“\"]([^”\"]+)[”\"]", feedback_text)
        time_part = f"“{time_match.group(1)}”" if time_match else "上一章留下的时间"
        place = place_match.group(1) if place_match else ""
        place_part = f"和“{place}”这条地点线" if place and len(place) <= 18 else "和上一章留下的地点线"
        # v6.10.5: Avoid hardcoded gendered pronoun; use neutral phrasing.
        return f"{time_part}{place_part}没有被跳过，未处理的约定压在心头，眼前的局面仍需先稳住。"

    def _try_segmented_plain_text_draft(
        self,
        state: FactoryState,
        task_desc: str,
        context: str,
        exec_events: list[dict] | None = None,
        on_chunk: Any | None = None,
    ) -> AuthorOutput:
        """Generate prose by scene-beat segments for long chapters in real mode."""
        project_id = state["project_id"]
        chapter_number = state["chapter_number"]
        instruction = self._get_instruction(state) or {}
        word_target = self._get_word_target(state)
        minimum_required, _, maximum_allowed = self._word_count_bounds(word_target)
        effective_target = word_target
        beats = self._get_scene_beats(state)
        chunks = list(chunk_items(beats, size=3))
        total_chunks = len(chunks)
        total_segment_beats = max(1, sum(len(chunk) for chunk in chunks))
        chapter_upper_bound = maximum_allowed
        per_call_retries = None

        compact_context = self._build_plain_text_context(state, context)

        revision_source_section = ""
        revision_priority_section = ""
        if task_desc == "返修":
            existing_chapter = self._get_chapter_info(state) or {}
            existing_body = strip_chapter_heading(
                existing_chapter.get("content", "") or "",
                chapter_number,
                existing_chapter.get("title"),
            )
            if existing_body.strip():
                revision_source_section = (
                    "【当前保留稿 / 必须在此基础上返修】\n"
                    "下面是当前已保存章节正文。请把它当作底稿进行定点修改："
                    "保留未被 Editor 点名的问题段落、人物关系、已成立事件和整体篇幅，"
                    "只重写或补足退回问题涉及的段落。禁止脱离该底稿另起炉灶重写短版。\n\n"
                    f"{existing_body.strip()}\n"
                )
            revision_review = normalize_revision_review(state.get("_revision_review")) or {}
            revision_priority_section = self._revision_blocking_priority_block(revision_review)
            compress_requested = self._revision_requests_compression(revision_review)
            existing_len = count_words(existing_body)
            if existing_len > 0 and not compress_requested:
                minimum_required = max(minimum_required, int(existing_len * 0.9))
                effective_target = max(word_target, existing_len)
                expansion_limit = max(500, int(existing_len * 0.15))
                chapter_upper_bound = existing_len + expansion_limit
                revision_source_section += (
                    f"\n【返修篇幅边界】当前保留稿约 {existing_len} 字符。"
                    "Editor 未要求压缩时，这次是补丁式返修，不是重新扩写；返修后总篇幅应基本持平。"
                    f"建议不低于 {int(existing_len * 0.9)} 字符，"
                    f"也不要超过 {chapter_upper_bound} 字符。"
                    f"最大允许新增 {expansion_limit} 字符，超过此新增上限会被系统拒绝。"
                    "禁止通过整段新增解释、重复心理描写或无关打斗来凑修改；"
                    "新增句子必须同步删除等量冗余说明。\n"
                )

        segment_outputs: list[str] = []

        for idx, beat_chunk in enumerate(chunks):
            segment_num = idx + 1
            segment_weight = len(beat_chunk) / total_segment_beats
            segment_target = max(1, int(round(effective_target * segment_weight)))
            segment_minimum = max(1, int(round(minimum_required * segment_weight)))
            segment_upper_bound = max(
                segment_target + 150,
                segment_minimum + 150,
                int(round(chapter_upper_bound * segment_weight)),
            )
            beat_lines = "\n".join(
                f"  {b['sequence']}. 目标: {b.get('scene_goal', '')} | 冲突: {b.get('conflict', '')} "
                f"| 转折: {b.get('turn', '')} | 钩子: {b.get('hook', '')}"
                for b in beat_chunk
            )

            segment_note = (
                f"【分段写作】本段为第{segment_num}/{total_chunks}段，"
                f"请只覆盖以下 scene beat：\n{beat_lines}\n"
            )
            if idx > 0:
                prev_tail = segment_outputs[-1][-300:] if len(segment_outputs[-1]) > 300 else segment_outputs[-1]
                segment_note += (
                    f"\n【承接上文】前一段结尾：\n...{prev_tail}\n"
                    f"请自然承接，不要重复已写内容。"
                )
            if idx == total_chunks - 1:
                segment_note += "\n这是最后一段，必须写到章末钩子，不要停在半途。"

            config_max = self._config_max_tokens(self.llm)
            # v6.9.0: Chinese text needs ~2-2.5 tokens per character, use 2.5x + 1024
            prose_max_tokens = max(1024, min(config_max, int(segment_target * 2.5) + 1024))

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
                        "\n【反说明段落规则】"
                        "禁止连续超过100字的纯说明/旁白段落。每段说明后必须紧跟角色动作、对白或环境反馈。"
                        "设定、背景、能力解释必须融入角色行为或对话中，不得独立成段。"
                        "\n【章末钩子规则】"
                        "最后200字必须包含以下至少一种：悬念问句、未完成的动作、角色的艰难抉择、意外信息揭露、冲突升级。"
                        "禁止以'总结本章'、'归纳意义'、'主角反思'结尾。必须让读者想翻下一页。"
                        "\n【对白比例规则】"
                        "对白占比至少10%。每500字至少有一段角色对话。对话必须有冲突、潜台词或信息交换，禁止功能化问答。"
                        "\n【标题整合规则】"
                        "章节标题的关键词必须在正文中至少出现一次，通过角色对话、内心活动或场景描写自然融入。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"项目ID: {project_id}\n章节号: {chapter_number}\n任务: {task_desc}\n"
                        f"本段正文至少 {segment_minimum} 字符，建议接近 {segment_target} 字符；"
                        f"最多不要超过 {segment_upper_bound} 字符。"
                        f"整章合并后目标约 {effective_target} 字符，硬上限 {chapter_upper_bound} 字符；"
                        "超过硬上限会被系统拒绝，请优先保留情节推进，删除重复铺陈。\n\n"
                        f"{revision_priority_section}\n\n"
                        f"{compact_context}\n\n"
                        f"{segment_note}\n\n"
                        f"{revision_source_section}\n"
                        f"请直接写第{chapter_number}章本段正文。"
                    ),
                },
            ]

            # v6.8.0: Skip segment_started logging (reduces noise)

            try:
                # v6.8.5: Truncation retry for segmented path
                try:
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
                        on_chunk=on_chunk or self.on_text_chunk,
                    ).strip()
                except LLMError as trunc_err:
                    if "finish_reason=length" not in str(trunc_err):
                        raise
                    config_max = self._config_max_tokens(self.llm)
                    seg_retry_max = min(config_max, int(prose_max_tokens * 1.5))
                    logger.warning(
                        "Author segment %d: truncation (max_tokens=%d), retrying with %d",
                        segment_num, prose_max_tokens, seg_retry_max,
                    )
                    content = self._invoke_text_for_author(
                        messages,
                        temperature=0.7,
                        max_tokens=seg_retry_max,
                        max_retries=per_call_retries,
                        request_timeout_seconds=(
                            AUTHOR_LONG_FORM_TIMEOUT_SECONDS
                            if is_configured_live_provider(self.llm)
                            else None
                        ),
                        on_chunk=on_chunk or self.on_text_chunk,
                    ).strip()
                content = self._coerce_plain_text_content(content)
                if not content:
                    retry_messages = [
                        *messages,
                        {
                            "role": "user",
                            "content": (
                                "上一轮返回为空。请立刻重写本段正文纯文本，"
                                "不要输出 JSON、字段名、解释或 Markdown。"
                                "从第一句正文直接开始。"
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
                        on_chunk=on_chunk or self.on_text_chunk,
                    ).strip()
                    content = self._coerce_plain_text_content(content)
            except Exception as e:
                if exec_events is not None:
                    exec_events.append({
                        "event_type": EVENT_SEGMENT_FAILED,
                        "message": f"Author 第 {segment_num}/{total_chunks} 段生成失败: {e}",
                        "status": "error",
                        "payload": {"segment_index": segment_num, "error": str(e)[:200]},
                    })
                raise

            if not content:
                if exec_events is not None:
                    exec_events.append({
                        "event_type": EVENT_SEGMENT_FAILED,
                        "message": f"Author 第 {segment_num}/{total_chunks} 段生成空内容",
                        "status": "error",
                        "payload": {"segment_index": segment_num},
                    })
                raise OutputValidationError(
                    f"Author 分段生成第 {segment_num} 段空内容（已重试）"
                )

            segment_outputs.append(content)

            # v6.8.0: Skip segment_completed logging

            # v6.8.2: Track cumulative budget and adjust remaining segments
            if idx < total_chunks - 1:  # Not the last segment
                accumulated_wc = sum(count_words(seg) for seg in segment_outputs)
                remaining_budget = max(0, chapter_upper_bound - accumulated_wc)
                
                if remaining_budget < segment_target:
                    logger.warning(
                        "Author segmented revision: approaching upper bound "
                        "(%d accumulated, %d remaining, next target %d)",
                        accumulated_wc, remaining_budget, segment_target,
                    )
                    # Note: Next segment's target will be calculated in next iteration
                    # This warning helps track budget exhaustion (reduces noise)

        merged_content = self._merge_segment_outputs(segment_outputs)
        merged_content = self._repair_final_segment_if_needed(
            state=state,
            merged_content=merged_content,
            segment_outputs=segment_outputs,
            chunks=chunks,
            compact_context=compact_context,
            instruction=instruction,
            chapter_number=chapter_number,
            task_desc=task_desc,
            exec_events=exec_events,
        )
        title = self._derive_title(state, instruction, merged_content)
        return AuthorOutput(
            title=title,
            content=merged_content,
            word_count=len(merged_content),
            implemented_events=self._instruction_items(instruction.get("key_events", "")),
            used_plot_refs=self._instruction_items(instruction.get("plots_to_plant", "")),
        )

    def _repair_final_segment_if_needed(
        self,
        *,
        state: FactoryState,
        merged_content: str,
        segment_outputs: list[str],
        chunks: list[list[dict[str, Any]]],
        compact_context: str,
        instruction: dict[str, Any],
        chapter_number: int,
        task_desc: str,
        exec_events: list[dict] | None,
    ) -> str:
        """Retry only the final author segment when it misses the chapter hook."""
        issues = self._scene_beat_coverage_issues(state, merged_content)
        if not issues or not segment_outputs or not chunks:
            return merged_content

        final_chunk = chunks[-1]
        prior_segments = segment_outputs[:-1]
        prior_content = self._merge_segment_outputs(prior_segments)
        prior_tail = prior_content[-900:] if len(prior_content) > 900 else prior_content
        issue_lines = "\n".join(f"- {issue.get('message', '')}" for issue in issues)
        beat_lines = "\n".join(
            f"  {beat.get('sequence', '?')}. 目标: {beat.get('scene_goal', '')} | "
            f"冲突: {beat.get('conflict', '')} | 转折: {beat.get('turn', '')} | "
            f"钩子: {beat.get('hook', '')}"
            for beat in final_chunk
        )
        final_target = max(650, len(segment_outputs[-1]))
        prose_max_tokens = max(1536, min(4096, int(final_target * 1.7) + 512))

        messages = [
            {
                "role": "system",
                "content": (
                    "你是网文工厂的执笔。现在只重写本章最后一段正文。"
                    "只输出可直接接在前文后的纯正文，不要标题、解释、清单、JSON 或 Markdown。"
                    "必须自然承接前文，完整覆盖给定最后 scene beat，并以章节 ending_hook 收束。"
                    "禁止复述前文，禁止停在中途动作、选择或对话上。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"项目ID: {state['project_id']}\n章节号: {chapter_number}\n任务: {task_desc}\n"
                    f"上一版最后分段没有写到章末，问题如下：\n{issue_lines}\n\n"
                    f"请重写最后分段，至少 {final_target} 字符，必须写到最后一句。\n\n"
                    f"{compact_context}\n\n"
                    f"【前文尾段，仅用于承接，禁止重复】\n{prior_tail}\n\n"
                    f"【最后分段必须覆盖的 scene beat】\n{beat_lines}\n\n"
                    f"【章节 ending_hook，必须自然写入章末】\n{instruction.get('ending_hook', '')}\n\n"
                    "请只输出修复后的最后分段正文。"
                ),
            },
        ]

        if exec_events is not None:
            exec_events.append({
                "event_type": "segment_repair_started",
                "message": "Author 最后分段未覆盖章末钩子，开始定向重写最后分段",
                "status": "warning",
                "payload": {"issues": [issue.get("message", "") for issue in issues]},
            })

        try:
            repaired_tail = self._invoke_text_for_author(
                messages,
                temperature=0.68,
                max_tokens=prose_max_tokens,
                max_retries=None,
                request_timeout_seconds=(
                    AUTHOR_LONG_FORM_TIMEOUT_SECONDS
                    if is_configured_live_provider(self.llm)
                    else None
                ),
            )
            repaired_tail = self._coerce_plain_text_content(repaired_tail)
        except Exception as e:
            logger.warning("Author: final segment targeted repair failed: %s", e)
            if exec_events is not None:
                exec_events.append({
                    "event_type": "segment_repair_failed",
                    "message": f"Author 最后分段定向重写失败: {e}",
                    "status": "error",
                    "payload": {"error": str(e)[:200]},
                })
            return merged_content

        if not repaired_tail:
            return merged_content

        candidate = self._merge_segment_outputs([*prior_segments, repaired_tail])
        remaining = self._scene_beat_coverage_issues(state, candidate)
        if remaining:
            if exec_events is not None:
                exec_events.append({
                    "event_type": "segment_repair_failed",
                    "message": "Author 最后分段定向重写后仍未覆盖章末钩子",
                    "status": "warning",
                    "payload": {"issues": [issue.get("message", "") for issue in remaining]},
                })
            return merged_content

        if exec_events is not None:
            exec_events.append({
                "event_type": "segment_repair_completed",
                "message": f"Author 最后分段定向重写完成 ({len(repaired_tail)} 字)",
                "status": "info",
                "payload": {"segment_length": len(repaired_tail)},
            })
        return candidate

    @classmethod
    def _merge_segment_outputs(cls, segments: list[str]) -> str:
        """Merge segmented prose without duplicating boundary overlap."""
        merged = ""
        for segment in segments:
            cleaned = str(segment or "").strip()
            if not cleaned:
                continue
            if not merged:
                merged = cleaned
                continue
            cleaned = cls._trim_segment_boundary_overlap(merged, cleaned)
            if cleaned:
                merged = f"{merged.rstrip()}\n\n{cleaned.lstrip()}"
        return merged.strip()

    @staticmethod
    def _trim_segment_boundary_overlap(previous: str, current: str) -> str:
        """Trim text the model repeated from the previous segment boundary."""
        prev = str(previous or "").rstrip()
        cur = str(current or "").lstrip()
        if not prev or not cur:
            return cur

        max_overlap = min(len(prev), len(cur), 1200)
        for size in range(max_overlap, 11, -1):
            if prev[-size:] == cur[:size]:
                return cur[size:].lstrip()

        prev_parts = [p.strip() for p in re.split(r"\n+", prev) if p.strip()]
        cur_parts = [p.strip() for p in re.split(r"\n+", cur) if p.strip()]
        while prev_parts and cur_parts:
            prev_tail = prev_parts[-1]
            cur_head = cur_parts[0]
            if min(len(prev_tail), len(cur_head)) < 12:
                break
            if max(len(prev_tail), len(cur_head)) > 500:
                break
            similarity = SequenceMatcher(None, prev_tail, cur_head).ratio()
            if prev_tail == cur_head or similarity >= 0.9:
                cur_parts.pop(0)
                continue
            break
        return "\n".join(cur_parts).lstrip() if cur_parts else ""

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
        on_chunk: Any | None = None,
    ) -> str:
        """Invoke text generation with per-call retry control when supported."""
        # v6.10.0: Use streaming if callback provided
        if on_chunk is not None:
            try:
                return self.llm.invoke_text_stream(
                    messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    agent_id=self.agent_id,
                    on_chunk=on_chunk,
                    request_timeout_seconds=request_timeout_seconds,
                )
            except TypeError:
                # Provider doesn't support streaming, fall back
                pass

        if max_retries is None and request_timeout_seconds is None:
            try:
                return self.llm.invoke_text(
                    messages, temperature=temperature, max_tokens=max_tokens, agent_id=self.agent_id
                )
            except TypeError as exc:
                if "agent_id" not in str(exc):
                    raise
                return self.llm.invoke_text(messages, temperature=temperature, max_tokens=max_tokens)
        try:
            return self.llm.invoke_text(
                messages,
                temperature=temperature,
                max_tokens=max_tokens,
                max_retries=max_retries,
                request_timeout_seconds=request_timeout_seconds,
                agent_id=self.agent_id,
            )
        except TypeError as exc:
            exc_text = str(exc)
            if "max_retries" not in exc_text and "request_timeout_seconds" not in exc_text and "agent_id" not in exc_text:
                raise
            try:
                return self.llm.invoke_text(
                    messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    max_retries=max_retries,
                    agent_id=self.agent_id,
                )
            except TypeError as retry_exc:
                retry_text = str(retry_exc)
                if "max_retries" not in retry_text and "agent_id" not in retry_text:
                    raise
                try:
                    return self.llm.invoke_text(
                        messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        request_timeout_seconds=request_timeout_seconds,
                    )
                except TypeError as final_exc:
                    if "request_timeout_seconds" not in str(final_exc):
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
        """Derive chapter title with v6.7.5 independent title generation.

        v6.7.5 fallback order:
        1. Existing usable title (from chapter)
        2. Generated/repaired title (new LLM-based)
        3. Instruction-derived title
        4. Explicit content heading (only if explicit)
        5. "第N章"

        Content opening is NO LONGER used as primary source.
        """
        chapter = self._get_chapter_info(state) or {}
        chapter_number = state["chapter_number"]
        title = chapter.get("title") or ""

        # 1. Check if existing title is usable
        if self._is_usable_chapter_title(title, chapter_number, instruction):
            # v6.7.5: Check if it's an opening-derived title that should be repaired
            if content and self._is_opening_derived_title(title, content, chapter_number):
                repaired = self._repair_or_generate_title(state, instruction, content, title)
                if repaired and self._is_usable_chapter_title(repaired, chapter_number, instruction):
                    return repaired
            return title

        # 2. v6.7.5: Generate new title via LLM (only in real mode with content)
        if state.get("llm_mode") == "real" and content:
            generated = self._generate_chapter_title(state, instruction, content)
            if generated and self._is_usable_chapter_title(generated, chapter_number, instruction):
                return generated

        # 3. Instruction-derived title
        derived_from_instruction = self._title_from_instruction(instruction, chapter_number)
        if derived_from_instruction:
            return derived_from_instruction

        # 4. Explicit content heading (only if it's an actual heading line)
        derived_from_heading = self._title_from_content_heading(content or "", chapter_number)
        if derived_from_heading:
            return derived_from_heading

        # 5. Final fallback
        return f"第{chapter_number}章"

    def _generate_chapter_title(
        self,
        state: FactoryState,
        instruction: dict,
        content: str,
    ) -> str | None:
        """v6.7.5: Generate chapter title independently via LLM.

        Title generation is based on:
        - Chapter content
        - Instruction objective, key_events, ending_hook
        - plots_to_plant/resolve
        - Content opening/ending summaries

        Rules:
        - 4-12 Chinese characters (max 16)
        - No punctuation
        - No planning verbs/terms
        - Not from content opening
        - Highlight key objects/locations/countdown/doubts/crisis/hooks

        Returns None on failure (does NOT block workflow).
        """
        if not content or not content.strip():
            return None

        chapter_number = state["chapter_number"]
        project_id = state["project_id"]

        # Build context for title generation
        objective = str(instruction.get("objective") or "").strip()
        key_events = self._instruction_items(instruction.get("key_events", ""))
        ending_hook = str(instruction.get("ending_hook") or "").strip()
        plots_to_plant = self._instruction_items(instruction.get("plots_to_plant", ""))
        plots_to_resolve = self._instruction_items(instruction.get("plots_to_resolve", ""))

        # Extract content opening and ending (first/last 200 chars)
        content_stripped = content.strip()
        opening_summary = content_stripped[:200] if len(content_stripped) > 200 else content_stripped
        ending_summary = content_stripped[-200:] if len(content_stripped) > 200 else content_stripped

        # Build prompt
        prompt_parts = [
            "请为以下章节生成一个合适的标题。",
            "",
            "【标题规则】",
            "1. 4-12个中文字符（最多16字）",
            "2. 不要标点符号",
            "3. 不要使用规划性动词或术语（如：引入、铺垫、描绘、建立、推进、承接、完成、解决、展示、呈现、交代、安排、触发、围绕、本章、目标、关键事件）",
            "4. 不要直接取自正文开头",
            "5. 突出关键物品、地点、倒计时、疑点、危机、钩子等",
            "",
            f"【章节号】第{chapter_number}章",
        ]

        if objective:
            prompt_parts.append(f"【写作目标】{objective}")
        if key_events:
            prompt_parts.append(f"【关键事件】{'; '.join(key_events[:5])}")
        if ending_hook:
            prompt_parts.append(f"【章末钩子】{ending_hook}")
        if plots_to_plant:
            prompt_parts.append(f"【需埋伏笔】{'; '.join(plots_to_plant[:3])}")
        if plots_to_resolve:
            prompt_parts.append(f"【需回收伏笔】{'; '.join(plots_to_resolve[:3])}")

        prompt_parts.extend([
            f"【正文开头】{opening_summary}",
            f"【正文结尾】{ending_summary}",
            "",
            "请返回JSON格式：{\"title\": \"章节标题\", \"reasoning\": \"简短理由\"}",
        ])

        messages = [
            {
                "role": "system",
                "content": (
                    "你是网文工厂的标题生成器。生成吸引人的章节标题。"
                    "标题要简洁有力，突出悬念和关键元素。"
                    "必须返回JSON格式。"
                ),
            },
            {
                "role": "user",
                "content": "\n".join(prompt_parts),
            },
        ]

        try:
            # P1: Preserve prior token usage before title generation call
            prior_usage = getattr(self.llm, "last_token_usage", None)

            raw = self._invoke_json(messages, schema=TitleGenerationOutput, temperature=0.7)
            output = TitleGenerationOutput(**raw)
            generated_title = output.title.strip()

            # Validate generated title
            if not generated_title:
                # P1: Restore prior usage when rejecting empty title
                if prior_usage:
                    self.llm.last_token_usage = prior_usage
                return None

            # Ensure title has chapter prefix
            if not re.match(rf"^第\s*{chapter_number}\s*章", generated_title):
                generated_title = f"第{chapter_number}章 {generated_title}"

            # P2: Check if generated title is opening-derived
            if self._is_opening_derived_title(generated_title, content, chapter_number):
                logger.info(
                    "Author: generated title for chapter %d is opening-derived, rejecting: %s",
                    chapter_number,
                    generated_title,
                )
                # P1: Restore prior usage when rejecting opening-derived title
                if prior_usage:
                    self.llm.last_token_usage = prior_usage
                return None

            # P1: Combine prior usage with title generation usage (success path)
            title_usage = getattr(self.llm, "last_token_usage", None)
            if prior_usage and title_usage:
                combined = TokenUsage(
                    prompt_tokens=prior_usage.prompt_tokens + title_usage.prompt_tokens,
                    completion_tokens=prior_usage.completion_tokens + title_usage.completion_tokens,
                    total_tokens=prior_usage.total_tokens + title_usage.total_tokens,
                    duration_ms=prior_usage.duration_ms + title_usage.duration_ms,
                )
                self.llm.last_token_usage = combined
            elif prior_usage:
                self.llm.last_token_usage = prior_usage

            logger.info(
                "Author: generated title for chapter %d: %s (reasoning: %s)",
                chapter_number,
                generated_title,
                output.reasoning[:50] if output.reasoning else "",
            )
            return generated_title

        except Exception as e:
            logger.warning("Author: title generation failed for chapter %d: %s", chapter_number, e)
            # P1: Restore prior usage on failure
            if prior_usage:
                self.llm.last_token_usage = prior_usage
            return None

    def _repair_or_generate_title(
        self,
        state: FactoryState,
        instruction: dict,
        content: str,
        current_title: str,
    ) -> str | None:
        """v6.7.5: Repair an opening-derived title or generate a new one.

        This is called when the existing title appears to be derived from
        content opening (which produces unattractive titles in v6.7.5).
        """
        # In real mode, try to generate a better title
        if state.get("llm_mode") == "real":
            return self._generate_chapter_title(state, instruction, content)

        # In stub mode, try instruction-derived fallback
        chapter_number = state["chapter_number"]
        return self._title_from_instruction(instruction, chapter_number)

    @classmethod
    def _is_opening_derived_title(
        cls,
        title: str,
        content: str,
        chapter_number: int,
    ) -> bool:
        """v6.7.5: Detect if title appears to be derived from content opening.

        This identifies titles that should be repaired with the new generation logic.
        """
        if not title or not content:
            return False

        # Strip chapter prefix from title
        suffix = cls._strip_chapter_prefix(title, chapter_number)
        if not suffix:
            return False

        # Get first content line
        first_line = first_content_line(content)
        if not first_line:
            return False

        # Clean first line for comparison
        first_line_clean = cls._clean_title_suffix(first_line)

        # If title suffix matches first line, it's opening-derived
        if first_line_clean and suffix == first_line_clean:
            return True

        # If title suffix is a substring of first line (and substantial)
        if len(suffix) >= 4 and suffix in first_line:
            return True

        return False

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
        chapter_number = state["chapter_number"]

        # P2: Check if title needs replacement BEFORE calling _derive_title
        # to avoid unnecessary LLM calls in real mode
        should_replace = not self._is_usable_chapter_title(output.title, chapter_number, instruction)
        if not should_replace and output.content:
            # Also replace if title is derived from content opening (v6.7.5 goal)
            should_replace = self._is_opening_derived_title(output.title, output.content, chapter_number)

        # Only call _derive_title when replacement is actually needed
        if should_replace:
            sanitized_title = self._derive_title(state, instruction, output.content)
            data["title"] = sanitized_title

        data["content"] = ensure_chapter_heading(data.get("content", ""), data.get("title"), chapter_number)

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

    @staticmethod
    def _word_count_bounds(word_target: int) -> tuple[int, int, int]:
        word_target = max(int(word_target or 2500), 1)
        minimum_required = int(word_target * 0.85)
        recommended_target = max(word_target, minimum_required + 500)
        maximum_allowed = max(word_target + 1200, int(word_target * 1.6))
        return minimum_required, recommended_target, maximum_allowed

    def _build_death_penalty_repair_context(self, state: FactoryState) -> str:
        return self._build_quality_gate_repair_context(state)

    def _build_quality_gate_repair_context(self, state: FactoryState) -> str:
        """Build repair context from the active gate and recent failed runs."""
        messages: list[str] = []
        gate = state.get("quality_gate", {}) or {}
        if gate.get("death_penalty_fail"):
            msg = gate.get("message") or "上一轮触发死刑红线"
            messages.append(str(msg))
        if gate.get("word_count_fail"):
            word_target = int(gate.get("word_target") or self._get_word_target(state))
            actual = gate.get("actual_word_count")
            minimum_required, recommended_target, maximum_allowed = self._word_count_bounds(word_target)
            messages.append(
                "上一轮触发字数硬闸门："
                f"实际 {actual if actual is not None else '?'} 字符，目标 {word_target} 字符，"
                f"本轮正文必须控制在 {minimum_required} 到 {maximum_allowed} 字符之间，"
                f"建议接近 {recommended_target} 字符；不要重新扩写成长章。"
            )

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
            + "\n本轮必须彻底修复上述质量门问题；红线表达改成具体动作、物理反应或对话推进，"
            "字数问题按硬上限收束，优先删重复铺陈而不是新增解释。"
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

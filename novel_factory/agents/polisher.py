"""Polisher Agent — polishes chapter content without changing facts."""

from __future__ import annotations

import json
import logging
import re
import statistics
import time
from typing import Any

from ..agent_runtime.segmented_generation import chunk_text_by_paragraphs
from ..workflow.execution_events import (
    EVENT_SEGMENT_STARTED,
    EVENT_SEGMENT_COMPLETED,
    EVENT_SEGMENT_FAILED,
)
from ..models.schemas import PolisherOutput
from ..models.state import ChapterStatus, FactoryState, status_order
from ..validators.chapter_checker import (
    validate_chapter_output,
    check_word_count_quality_gate,
    check_word_count_upper_gate,
    count_words,
    derive_word_target,
)
from ..validators.death_penalty import (
    check_death_penalty,
    check_death_penalty_structured,
    has_critical_violation,
    sanitize_death_penalty_text,
)
from ..validators.editorial_meta import strip_editorial_meta_blocks
from ..validators.fact_lock import check_fact_integrity, extract_fact_lock
from ..skills.registry import SkillRegistry
from ..agent_runtime.base import BaseAgent
from ..agent_runtime.chapter_text import default_chapter_title, ensure_chapter_heading, strip_chapter_heading
from ..agent_runtime.revision_context import normalize_revision_review, revision_feedback_block
from ..agent_runtime.skill_hooks import run_agent_skills
from ..agent_runtime.context_builder import AgentContextBuilder, format_context_bundle_for_prompt
from ..llm.openai_compatible import LLMError, OutputValidationError
from ..llm.provider import is_configured_live_provider
from ..quality.feedback_bridge import build_compact_feedback, format_polisher_context

logger = logging.getLogger(__name__)

POLISHER_LONG_FORM_TIMEOUT_SECONDS = 300
POLISHER_CONTEXT_CHAR_LIMIT = 18000
POLISHER_DRAFT_CHAR_LIMIT = 12000
POLISHER_MAX_EXPANSION_RATIO = 0.12
POLISHER_MAX_EXPANSION_WORDS = 250

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
4. 减少 AI 味（v2.0 量化规则——优先保事实，再保文风）
   执行优先级：事实保护 > 对白/场景 > AI 去味。去味规则不得以改变剧情、设定、角色动机为代价。
   - 删减总结句（"综上所述/总之/简单来说"）
   - 将直白心理解释（"他感到愤怒"）改为动作或神态（"他攥紧拳头，指节发白"）
   - 删除宏大空泛判断（"这一刻，他知道，一切都将改变"）
   - 【破折号密度】每 500 字不超过 2 个"——"。超限必须拆分为短句或用逗号/句号替代
   - 【禁止三段式】不出现"XX、XX、XX"的刻意三分结构；列举两项或散列即可
   - 【禁止填充短语】删除"就在这时""准确地说""不可否认的是""从某种意义上说"等无意义过渡
   - 【禁止否定式排比】同一章不超过 1 次"不是…而是…""不仅仅…更…"
   - 【句式开头变化】连续 3 个段落不能都以"他/她"开头；交替使用动作、环境、对话、感受开头
   - 【禁止同义词循环】同一概念保持统一指代，不为了"避免重复"而强行换词（如"掌心→手掌→右手"来回切换）
   - 【情感动作化】所有心理动词（"感到/觉得/意识到/暗想/心中"）必须替换为具体动作、神态或环境反馈

输出格式：严格按 JSON 格式输出，包含：
- content: 润色后的正文
- fact_change_risk: 事实变更风险（none/low/high，必须为 none）
- changed_scope: 改动范围列表（如 sentence, dialogue, rhythm, scene_texture）
- summary: 润色摘要"""


class PolisherAgent(BaseAgent):
    """Polisher: polishes chapter content without changing facts."""

    agent_id = "polisher"
    context_char_limit = POLISHER_CONTEXT_CHAR_LIMIT

    def __init__(self, repo, llm, skill_registry: SkillRegistry | None = None, **kwargs):
        """Initialize Polisher agent.

        Args:
            repo: Repository instance.
            llm: LLM provider instance.
            skill_registry: Optional SkillRegistry for skill execution.
        """
        super().__init__(repo, llm, skill_registry=skill_registry, **kwargs)
        self.skill_registry = skill_registry


    @staticmethod
    def _config_max_tokens(llm, fallback: int = 4096) -> int:
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
        if state.get("chapter_status") != ChapterStatus.REVISION.value and (
            not chapter or chapter.get("status") != ChapterStatus.REVISION.value
        ):
            return None
        if not chapter:
            return None
        try:
            return normalize_revision_review(
                self.repo.get_latest_review(state.get("project_id"), chapter.get("id"))
            )
        except Exception:
            logger.warning("Polisher: failed to load revision review fallback", exc_info=True)
            return None

    def _current_draft_block(self, state: FactoryState) -> str:
        chapter = self._get_chapter_info(state)
        content = (chapter or {}).get("content") or ""
        if not content:
            return ""
        draft = content[:POLISHER_DRAFT_CHAR_LIMIT]
        if len(content) > POLISHER_DRAFT_CHAR_LIMIT:
            draft += "\n\n【草稿已截断】当前草稿过长，仅保留前半部分供润色。"
        return f"【当前草稿】\n{draft}"

    def _build_v6_context(self, state: FactoryState) -> str:
        """Build Polisher context while protecting the draft from middle truncation."""
        parts = []
        role_ctx = self._get_role_profile_context()
        if role_ctx:
            parts.append(role_ctx)
        mem_ctx = self._get_agent_memory_context(state.get("project_id", ""))
        if mem_ctx:
            parts.append(mem_ctx)

        base_ctx = self.build_context(state, include_current_draft=False)
        if base_ctx:
            parts.append(base_ctx)

        draft_block = self._current_draft_block(state)
        if not draft_block:
            return self._limit_context_size(
                "\n\n".join(parts),
                self.context_char_limit,
                agent_id=self.agent_id,
            )

        draft_reserved = len(draft_block) + 2
        aux_limit = max(0, self.context_char_limit - draft_reserved)
        aux_context = "\n\n".join(parts)
        if aux_limit > 0:
            aux_context = self._limit_context_size(
                aux_context,
                aux_limit,
                agent_id=self.agent_id,
            )
        else:
            aux_context = ""

        if aux_context:
            return f"{aux_context}\n\n{draft_block}"
        return draft_block

    def build_context(self, state: FactoryState, *, include_current_draft: bool = True) -> str:
        """Build context using AgentContextBuilder.

        v6.6.2: Uses unified context builder for inheritance and fact consistency.
        v6.4.2: Appends polishing writing reminders derived from quality diagnosis dimensions.
        """
        project_id = state["project_id"]
        chapter_number = state["chapter_number"]
        parts = []

        title_contract = self._get_title_contract_context(project_id)
        if title_contract:
            parts.append(title_contract)

        # v6.6.2: Unified context builder
        builder = AgentContextBuilder(self.repo)
        bundle = builder.build_for_polisher(project_id, chapter_number, state)
        formatted = format_context_bundle_for_prompt(bundle, agent_name="polisher", max_chars=12000)
        if formatted:
            parts.append(formatted)

        chapter = self._get_chapter_info(state)
        if state.get("_revision_review") or state.get("chapter_status") == ChapterStatus.REVISION.value or (
            chapter and chapter.get("status") == ChapterStatus.REVISION.value
        ):
            review = state.get("_revision_review")
            if not review and chapter:
                review = self.repo.get_latest_review(project_id, chapter["id"])
            feedback = revision_feedback_block(review)
            if feedback:
                parts.append(feedback)

        # Original draft (Polisher needs the actual text to work on)
        if include_current_draft:
            draft_block = self._current_draft_block(state)
            if draft_block:
                parts.append(draft_block)

        chapter = self._get_chapter_info(state)
        current_content = (chapter or {}).get("content") or ""
        if current_content and (
            state.get("_revision_review")
            or state.get("chapter_status") == ChapterStatus.REVISION.value
            or ((chapter or {}).get("status") == ChapterStatus.REVISION.value)
        ):
            current_wc = count_words(current_content)
            upper_bound = max(current_wc + 400, int(current_wc * 1.12))
            parts.append(
                "【返修润色边界】\n"
                f"当前稿约 {current_wc} 字符。返修润色必须以当前稿为底稿做局部语言修正，"
                f"不要扩写新场景；除非 Editor 明确要求扩写，润色后总篇幅不要超过 {upper_bound} 字符。"
            )

        # v6.4.2: Inject quality-diagnosis-derived writing reminders
        parts.append(
            "【润色写作提醒】\n"
            "1. 对白自然化：检查是否有功能性问答，尝试加入语气词、打断、省略或反问；"
            "让不同角色的句式长度和用词习惯有差异。\n"
            "2. 场景质感：优先强化已有感官线索；必要时只补最小动作/环境反馈，不硬加无关描写；"
            "将抽象描述（\"他很紧张\"）改为具体动作（\"他攥紧拳头\"）。\n"
            "3. 节奏变化：避免连续多个段落长度相近；紧张处用短句，描写处可用长句但避免>40字。\n"
            "4. 去AI味：删除总结句（\"总之/简单来说\"）、直白心理解释和宏大空泛判断。\n"
            "5. Show, Don't Tell：将\"感到/觉得/意识到/明白\"等直白情绪词改为动作或神态。\n"
            "6. 职责边界：Polisher 只修语言、节奏、对白、说明段和质量诊断建议，"
            "不要主动大改剧情结构。如发现剧情级风险，输出 risk note，不要硬改。"
        )

        # v4.0: Style Bible injection
        style_ctx = self._get_style_bible_context(project_id, "polisher")
        if style_ctx:
            parts.append(style_ctx)

        # v6.10.5: Story Contract injection
        contract_ctx = self._get_story_contract_context(project_id, "polisher")
        if contract_ctx:
            parts.append(contract_ctx)

        # v6.6.2: Fact lock for Polisher (backward-compatible title)
        instruction = self._get_instruction(state)
        fact_lock_parts: list[str] = []
        if instruction:
            if instruction.get("key_events"):
                fact_lock_parts.append(f"关键事件: {instruction['key_events']}")
            if instruction.get("plots_to_plant"):
                fact_lock_parts.append(f"伏笔埋设: {instruction['plots_to_plant']}")
            if instruction.get("plots_to_resolve"):
                fact_lock_parts.append(f"伏笔兑现: {instruction['plots_to_resolve']}")
        prev_state = self._get_prev_state_card(state)
        if prev_state:
            state_data = prev_state.get("state_data", prev_state)
            if isinstance(state_data, dict):
                for key in ("level", "等级", "lv", "Lv"):
                    if key in state_data:
                        fact_lock_parts.append(f"等级/数值: {key}={state_data[key]}")
                        break
                assets = state_data.get("assets", {})
                if isinstance(assets, dict):
                    for k, v in list(assets.items())[:5]:
                        fact_lock_parts.append(f"  {k}={v}")
        if fact_lock_parts:
            parts.append("【事实锁定清单 — 润色时不可删除/改变】\n" + "\n".join(fact_lock_parts))

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
            return format_polisher_context(feedback)
        except Exception:
            logger.warning("Polisher: quality diagnosis failed, skipping feedback injection", exc_info=True)
            return ""

    def _execute(self, state: FactoryState) -> dict[str, Any]:
        project_id = state["project_id"]
        chapter_number = state["chapter_number"]
        exec_events: list[dict] = []
        passthrough_mode = False

        context = self._build_v6_context(state)
        chapter = self._get_chapter_info(state)

        # v6.1.1: Emit revision context loaded event for revision chapters
        current_status = state.get("chapter_status", "")
        revision_review = self._load_revision_review(state, chapter)
        in_revision_chain = current_status == ChapterStatus.REVISION.value or bool(revision_review)

        # v6.8.2: Validate revision context exists when in revision mode.
        # v6.8.3: Only fail-fast for real Editor rejections, NOT for quality gate
        # internal repairs which temporarily set chapter_status=REVISION.
        if current_status == ChapterStatus.REVISION.value and not revision_review:
            gate = state.get("quality_gate") or {}
            is_quality_gate_retry = bool(
                gate.get("word_count_fail")
                or gate.get("death_penalty_fail")
                or gate.get("scene_beat_coverage_fail")
                or gate.get("version_regression")
            )
            if not is_quality_gate_retry:
                logger.error(
                    "Polisher: revision context missing for %s ch%d",
                    project_id, chapter_number,
                )
                return {
                    "error": "Polisher: 返修上下文缺失，无法加载 Editor 审核意见",
                    "chapter_status": state.get("chapter_status"),
                    "requires_human": True,
                    "quality_gate": {
                        "pass": False,
                        "revision_target": "polisher",
                        "message": "返修上下文缺失，需要人工确认后重新触发",
                        "context_missing": True,
                    },
                }
            else:
                logger.info(
                    "Polisher: revision context missing for %s ch%d but quality gate retry — continuing without review",
                    project_id, chapter_number,
                )

        if in_revision_chain:
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

        # v6.8.5: Include death penalty list so polisher avoids banned words
        from ..validators.death_penalty import format_death_penalty_for_prompt
        dp_prompt = format_death_penalty_for_prompt()
        polisher_system = f"{POLISHER_SYSTEM_PROMPT}\n\n{dp_prompt}" if dp_prompt else POLISHER_SYSTEM_PROMPT
        messages = [
            {"role": "system", "content": polisher_system},
            {"role": "user", "content": f"项目ID: {project_id}\n章节号: {chapter_number}\n\n{context}\n\n请润色以上草稿，注意不要改变任何剧情事实。"},
        ]

        live_provider = state.get("llm_mode") == "real" and is_configured_live_provider(self.llm)
        try:
            if self._should_use_plain_text_primary(state):
                output = self._try_plain_text_polish(state, context, exec_events=exec_events)
            else:
                raw = self._invoke_json(messages, schema=PolisherOutput)
                output = PolisherOutput(**raw)
        except Exception as e:
            if live_provider and not self._should_use_plain_text_primary(state):
                try:
                    output = self._try_plain_text_polish(state, context)
                except Exception as fallback_error:
                    passthrough = self._passthrough_polish_output(state, fallback_error)
                    if not passthrough:
                        logger.error("Polisher LLM call failed: %s; plain-text fallback failed: %s", e, fallback_error)
                        return {"error": f"Polisher failed: {fallback_error}", "chapter_status": state.get("chapter_status")}
                    output = passthrough
                    passthrough_mode = True
                    exec_events.append(self._passthrough_event(fallback_error))
            elif live_provider:
                passthrough = self._passthrough_polish_output(state, e)
                if not passthrough:
                    logger.error("Polisher LLM call failed: %s", e)
                    return {"error": f"Polisher failed: {e}", "chapter_status": state.get("chapter_status")}
                output = passthrough
                passthrough_mode = True
                exec_events.append(self._passthrough_event(e))
            else:
                logger.error("Polisher LLM call failed: %s", e)
                return {"error": f"Polisher failed: {e}", "chapter_status": state.get("chapter_status")}

        if state.get("llm_mode") == "real":
            sanitized_content, replacements = sanitize_death_penalty_text(output.content)
            if replacements:
                logger.info(
                    "Polisher: sanitized death-penalty phrases before validation: %s",
                    replacements,
                )
                output = output.model_copy(update={"content": sanitized_content})
                exec_events.append({
                    "event_type": "death_penalty_sanitized",
                    "message": f"润色稿已自动替换 {len(replacements)} 处死刑红线表达",
                    "status": "info",
                    "payload": {"replacements": replacements[:10]},
                })

        cleaned_meta_content, removed_meta = strip_editorial_meta_blocks(output.content)
        if removed_meta:
            output = output.model_copy(update={"content": cleaned_meta_content})
            exec_events.append({
                "event_type": "editorial_meta_sanitized",
                "message": f"润色稿中移除 {len(removed_meta)} 段评审/诊断元评论",
                "status": "warning",
                "payload": {
                    "removed_count": len(removed_meta),
                    "samples": removed_meta[:2],
                },
            })

        self.validate_output(output.model_dump())

        # Q8: Fact lock hard verification — BEFORE status advance
        original_content = ""
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
        if self.skill_registry and not passthrough_mode:
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
                fail_closed_ids=set(),
            )
            if not after_llm_hook.ok:
                exec_events.append({
                    "event_type": "skill_completed",
                    "message": f"润色 Skill 降级为提醒：{after_llm_hook.blocking_error}",
                    "status": "warning",
                    "payload": {"stage": "after_llm", "blocking_error": after_llm_hook.blocking_error},
                })

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
                    "quality_gate": {
                        "pass": False,
                        "revision_target": "polisher",
                        "fact_lock_fail": True,
                        "message": (
                            f"润色事实锁未通过: risk={integrity.risk}, "
                            f"missing={missing}, changed={changed}"
                        ),
                        "missing_facts": missing,
                        "changed_facts": changed,
                        "agent": "polisher",
                        "workflow_run_id": state.get("workflow_run_id"),
                    },
                    "_revision_review": revision_review,
                    "_exec_events": exec_events,
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

        upper_gate_passed, upper_gate_msg = check_word_count_upper_gate(
            polished_content, word_target, "polisher"
        )
        if not upper_gate_passed:
            compressed_content = self._try_compress_overlong_polish(
                state=state,
                content=polished_content,
                word_target=word_target,
                upper_gate_msg=upper_gate_msg,
            )
            if compressed_content:
                compressed_content = ensure_chapter_heading(
                    compressed_content, chapter_title, chapter_number
                )
                if fact_lock:
                    integrity = check_fact_integrity(original_content, compressed_content, fact_lock)
                    if integrity.risk != "none":
                        missing = [f.content for f in integrity.missing_facts]
                        changed = [f.content for f in integrity.changed_facts]
                        logger.error(
                            "Polisher: compressed output fact lock verification FAILED — "
                            "missing=%s changed=%s risk=%s",
                            missing, changed, integrity.risk,
                        )
                        return {
                            "error": (
                                f"Polisher: fact lock verification failed after compression "
                                f"(risk={integrity.risk}, "
                                f"missing={missing}, changed={changed})"
                            ),
                            "chapter_status": state.get("chapter_status"),
                        }
                polished_content = compressed_content
                upper_gate_passed, upper_gate_msg = check_word_count_upper_gate(
                    polished_content, word_target, "polisher"
                )
                exec_events.append({
                    "event_type": "word_count_compressed",
                    "message": "润色稿超出字数上限，已自动压缩后继续",
                    "status": "info",
                    "payload": {"agent": "polisher", "word_target": word_target},
                })

            if not upper_gate_passed:
                logger.warning("Polisher: word count upper gate failed: %s", upper_gate_msg)
                from ..validators.chapter_checker import count_words
                actual_wc = count_words(polished_content)
                return {
                    "error": f"字数质量门未通过: {upper_gate_msg}",
                    "chapter_status": state.get("chapter_status"),
                    "quality_gate": {
                        "pass": False,
                        "revision_target": "polisher",
                        "word_count_fail": True,
                        "message": upper_gate_msg,
                        "actual_word_count": actual_wc,
                        "word_target": word_target,
                        "agent": "polisher",
                        "workflow_run_id": state.get("workflow_run_id"),
                        # v6.7.8: internal compression failure does not consume
                        # chapter-level revision retries.
                        "internal_repair": True,
                        "consume_revision_retry": False,
                        "repair_scope": "internal_word_count_compression",
                    },
                }

        lower_gate_passed, lower_gate_msg = check_word_count_quality_gate(
            polished_content, word_target, "polisher"
        )
        if not lower_gate_passed:
            logger.warning("Polisher: word count quality gate failed after compression: %s", lower_gate_msg)
            from ..validators.chapter_checker import count_words
            actual_wc = count_words(polished_content)
            return {
                "error": f"字数质量门未通过: {lower_gate_msg}",
                "chapter_status": state.get("chapter_status"),
                "quality_gate": {
                    "pass": False,
                    "revision_target": "polisher",
                    "word_count_fail": True,
                    "message": lower_gate_msg,
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
                payload={
                    "text": polished_content,
                    "original_text": original_content,
                    "polished_text": polished_content,
                    "fact_lock_items": [f.content for f in fact_lock] if fact_lock else [],
                },
                project_overrides=project_skill_overrides,
                skill_type_hint="validator",
                fail_closed_ids={"fact-lock"},
            )
            if not before_save_hook.ok:
                exec_events.append({
                    "event_type": "skill_completed",
                    "message": f"润色保存前检查未通过：{before_save_hook.blocking_error}",
                    "status": "error",
                    "payload": {"stage": "before_save", "blocking_error": before_save_hook.blocking_error},
                })
                return {
                    "chapter_status": state.get("chapter_status"),
                    "error": before_save_hook.blocking_error or "润色保存前检查未通过",
                    "quality_gate": {
                        "pass": False,
                        "revision_target": "polisher",
                        "fact_lock_fail": "fact-lock" in str(before_save_hook.blocking_error),
                        "message": before_save_hook.blocking_error or "润色保存前检查未通过",
                        "agent": "polisher",
                        "workflow_run_id": state.get("workflow_run_id"),
                    },
                    "_revision_review": revision_review,
                    "_exec_events": exec_events,
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
                        logger.warning(
                            "Polisher: AI trace score high but non-blocking: %d > 70",
                            ai_trace_score
                        )

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
        event_type = "revision_diff_generated" if in_revision_chain else "diff_generated"
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

        if in_revision_chain and low_change:
            reason = f"返修润色无效：改动过小（{original_wc} → {polished_wc} 字），未执行审核退回意见"
            logger.warning("Polisher: revision low-change gate failed: %s", reason)
            self.repo.save_artifact(
                project_id,
                chapter_number,
                "polisher",
                "rejected_low_change_revision",
                content_json={
                    "content": polished_content,
                    "rejection_reason": reason,
                    "revision_source_review_id": revision_review.get("review_id"),
                },
                workflow_run_id=state.get("workflow_run_id"),
            )
            exec_events.append({
                "event_type": "quality_gate_retry",
                "message": reason,
                "status": "warning",
                "payload": {
                    "revision_target": "polisher",
                    "quality_gate": {
                        "pass": False,
                        "revision_target": "polisher",
                        "low_change_fail": True,
                        "message": reason,
                        "internal_repair": True,
                        "consume_revision_retry": False,
                        "repair_scope": "internal_polisher_low_change",
                    },
                },
            })
            return {
                "chapter_status": state.get("chapter_status"),
                "error": reason,
                "quality_gate": {
                    "pass": False,
                    "revision_target": "polisher",
                    "low_change_fail": True,
                    "message": reason,
                    "agent": "polisher",
                    "workflow_run_id": state.get("workflow_run_id"),
                    "internal_repair": True,
                    "consume_revision_retry": False,
                    "repair_scope": "internal_polisher_low_change",
                },
                "_revision_review": revision_review,
                "_exec_events": exec_events,
            }

        # v6.10.4: Prevent Polisher from adding enough material to mutate
        # plot facts.  Broad word-count gates allow useful polish expansion;
        # this local drift guard blocks unsafe relative expansion before
        # Editor later reports fact-lock violations after a retry loop.
        #
        # v6.10.7: Relax limits during revision chains because Editor explicitly
        # requested substantive changes; a moderate expansion is expected.
        if (
            state.get("llm_mode") != "stub"
            and original_content
            and original_wc > 0
            and polished_wc > original_wc
        ):
            system_compressed = any(
                ev.get("event_type") == "word_count_compressed"
                for ev in exec_events
            )
            word_delta = polished_wc - original_wc
            expansion_ratio = word_delta / original_wc
            max_expansion_ratio = 0.25 if in_revision_chain else POLISHER_MAX_EXPANSION_RATIO
            max_expansion_words = 500 if in_revision_chain else POLISHER_MAX_EXPANSION_WORDS
            if (
                not system_compressed
                and expansion_ratio > max_expansion_ratio
                and word_delta > max_expansion_words
            ):
                reason = (
                    f"润色稿扩写漂移：{original_wc} → {polished_wc} 字"
                    f"（+{word_delta}，+{expansion_ratio*100:.1f}%），"
                    "超过 Polisher 安全扩写上限"
                )
                logger.warning("Polisher: expansion drift gate failed: %s", reason)
                self.repo.save_artifact(
                    project_id,
                    chapter_number,
                    "polisher",
                    "rejected_expansion_drift",
                    content_json={
                        "content": polished_content,
                        "rejection_reason": reason,
                        "revision_source_review_id": revision_review.get("review_id") if revision_review else None,
                    },
                    workflow_run_id=state.get("workflow_run_id"),
                )
                exec_events.append({
                    "event_type": "quality_gate_retry",
                    "message": reason,
                    "status": "warning",
                    "payload": {
                        "revision_target": "polisher",
                        "quality_gate": {
                            "pass": False,
                            "revision_target": "polisher",
                            "expansion_drift_fail": True,
                            "message": reason,
                            "original_word_count": original_wc,
                            "polished_word_count": polished_wc,
                            "word_count_delta": word_delta,
                            "internal_repair": True,
                            "consume_revision_retry": False,
                            "repair_scope": "internal_polisher_expansion_drift",
                        },
                    },
                })
                return {
                    "chapter_status": state.get("chapter_status"),
                    "error": reason,
                    "quality_gate": {
                        "pass": False,
                        "revision_target": "polisher",
                        "expansion_drift_fail": True,
                        "message": reason,
                        "original_word_count": original_wc,
                        "polished_word_count": polished_wc,
                        "word_count_delta": word_delta,
                        "agent": "polisher",
                        "workflow_run_id": state.get("workflow_run_id"),
                        "internal_repair": True,
                        "consume_revision_retry": False,
                        "repair_scope": "internal_polisher_expansion_drift",
                    },
                    "_revision_review": revision_review,
                    "_exec_events": exec_events,
                }

        # v6.8.5: Check for excessive word count drift even on first polish.
        # If the polished draft is >20% shorter than the original without any
        # compression request, reject it and keep the original.
        if not in_revision_chain and original_content and polished_wc < original_wc * 0.8:
            # Check if word_count_compressed event exists (system compression)
            system_compressed = any(
                ev.get("event_type") == "word_count_compressed"
                for ev in exec_events
            )
            if not system_compressed:
                shrink_pct = (original_wc - polished_wc) / original_wc * 100
                reason = f"润色稿字数异常缩减：{original_wc} → {polished_wc} 字（-{shrink_pct:.1f}%），超过 20% 阈值"
                logger.warning("Polisher: first polish excessive shrink: %s", reason)
                self.repo.save_artifact(
                    project_id,
                    chapter_number,
                    "polisher",
                    "rejected_regression",
                    content_json={"content": polished_content, "rejection_reason": reason},
                )
                exec_events.append({
                    "event_type": "quality_gate_retry",
                    "message": reason,
                    "status": "warning",
                    "payload": {
                        "revision_target": "polisher",
                        "retry_count": 0,
                        "quality_gate": {
                            "pass": False,
                            "revision_target": "polisher",
                            "version_regression": True,
                            "message": reason,
                        },
                    },
                })
                # Keep original content, return as passthrough
                return {
                    "chapter_status": ChapterStatus.POLISHED.value,
                    "current_stage": "polished",
                    "_revision_review": state.get("_revision_review"),
                    "_exec_events": exec_events,
                }

        # v6.6.0: Protect the current draft from a regressing revision pass.
        if in_revision_chain and original_content:
            from ..quality.version_regression_guard import VersionRegressionGuard

            revision_review = revision_review or {}
            system_compressed = any(
                ev.get("event_type") == "word_count_compressed"
                for ev in exec_events
            )
            reject, reason = VersionRegressionGuard.should_reject_new_draft(
                original_content,
                polished_content,
                word_target,
                editor_suggestions=revision_review.get("suggestions", []),
                allow_system_compression=system_compressed,
            )
            if reject:
                self.repo.save_artifact(
                    project_id,
                    chapter_number,
                    "polisher",
                    "rejected_regression",
                    content_json={
                        "content": polished_content,
                        "summary": output.summary,
                        "rejection_reason": reason,
                        "revision_source_review_id": revision_review.get("review_id"),
                    },
                    workflow_run_id=state.get("workflow_run_id"),
                )
                return {
                    "chapter_status": state.get("chapter_status"),
                    "error": reason,
                    "quality_gate": {
                        "pass": False,
                        "revision_target": "polisher",
                        "version_regression": True,
                        "message": reason,
                    },
                    "_revision_review": revision_review,
                    "_exec_events": exec_events,
                }

        # v6.10.3: If polisher is in revision chain but falls back to passthrough
        # (e.g. model content_filter), do not waste editor tokens on unchanged
        # content and do not consume a revision retry. Route directly to human_review
        # since the model cannot execute the revision.
        if in_revision_chain and passthrough_mode:
            return {
                "error": "Polisher 返修失败：模型输出不可用，无法执行返修润色",
                "chapter_status": state.get("chapter_status"),
                "requires_human": True,
                "_exec_events": exec_events,
            }

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
            # v6.8.1: Check if chapter is already at or past POLISHED (recovery run)
            # v6.10.8: Use shared status_order() instead of local dict.
            current_status = self.repo.get_chapter_status(project_id, chapter_number)
            current_order = status_order(current_status)
            polished_order = status_order("polished")
            if current_order >= polished_order:
                logger.info(
                    "Polisher: chapter already at '%s' (order %d >= %d), skipping status advance (recovery run)",
                    current_status, current_order, polished_order,
                )
            else:
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
            # v6.6.1: Embed quality diagnosis feedback for auditability
            # LLM-reported fixes (may be empty if model does not fill them)
            artifact_payload["_quality_feedback"] = {
                "fixed_findings": output.fixed_quality_findings,
                "deferred_findings": output.deferred_quality_findings,
                "quality_risk_note": output.quality_risk_note,
            }
            # Also save deterministic QualityHub compact result so audit
            # always sees the actual diagnosis regardless of LLM compliance.
            quality_hub_compact: dict[str, Any] | None = None
            if self.skill_registry:
                try:
                    from ..quality.hub import QualityHub
                    from ..quality.feedback_bridge import build_compact_feedback
                    hub = QualityHub(self.repo, self.skill_registry)
                    diagnose_result = hub.diagnose(polished_content, context={
                        "project_id": project_id,
                        "chapter_number": chapter_number,
                    })
                    qf = build_compact_feedback(diagnose_result)
                    quality_hub_compact = qf.to_dict()
                except Exception:
                    logger.warning("Polisher: quality diagnosis for artifact failed", exc_info=True)
            if quality_hub_compact:
                artifact_payload["_quality_feedback"]["quality_hub_compact"] = quality_hub_compact
            # v6.1.1: Embed revision metadata in artifact for auditability
            if in_revision_chain:
                revision_review = revision_review or {}
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
            "_revision_review": revision_review if in_revision_chain else state.get("_revision_review"),
            "_exec_events": exec_events,
        }

    def _should_use_plain_text_primary(self, state: FactoryState) -> bool:
        """Use prose-first polishing for live providers to avoid long JSON failures."""
        return state.get("llm_mode") == "real" and is_configured_live_provider(self.llm)

    def _passthrough_polish_output(self, state: FactoryState, reason: Exception) -> PolisherOutput | None:
        """Preserve the drafted chapter when live polishing is unavailable.

        A failed Polisher LLM call should not destroy a usable Author draft. In
        real mode, keep the current chapter content and let Editor review it,
        while still preserving hard fact-lock and death-penalty checks below.
        """
        chapter = self._get_chapter_info(state)
        content = (chapter or {}).get("content") or ""
        if not content.strip():
            return None
        reason_text = str(reason)[:120]
        return PolisherOutput(
            content=content,
            fact_change_risk="none",
            changed_scope=["passthrough"],
            summary=f"润色模型不可用，保留执笔稿继续审核：{reason_text}",
            fixed_quality_findings=[],
            deferred_quality_findings=[],
            quality_risk_note=None,
        )

    @staticmethod
    def _passthrough_event(reason: Exception) -> dict[str, Any]:
        reason_text = str(reason)[:200]
        return {
            "event_type": "fallback_used",
            "message": f"润色降级：模型输出不可用，已保留执笔稿继续审核（{reason_text}）",
            "status": "warning",
            "payload": {"fallback_type": "polisher_passthrough", "reason": reason_text},
        }

    def _try_plain_text_polish(
        self,
        state: FactoryState,
        context: str,
        exec_events: list[dict] | None = None,
    ) -> PolisherOutput:
        project_id = state["project_id"]
        chapter_number = state["chapter_number"]
        chapter = self._get_chapter_info(state)
        content = (chapter or {}).get("content") or ""

        if state.get("llm_mode") == "real" and len(content) > 2800:
            return self._try_segmented_plain_text_polish(state, context, exec_events=exec_events)

        # v6.8.5: Include death penalty list so polisher avoids banned words
        from ..validators.death_penalty import format_death_penalty_for_prompt as _dp_prompt
        dp_text = _dp_prompt()
        system_content = (
            "你是网文工厂的润色编辑。请只输出润色后的完整正文纯文本，"
            "不要输出 JSON、字段名、Markdown、解释或摘要。"
            "必须保留剧情事实、关键事件、伏笔和角色动机。"
            "润色时只改善语言和节奏，不要扩写情节或增加新场景；"
            "润色后总字数不得超过原稿字数的 110%。"
        )
        if dp_text:
            system_content = f"{system_content}\n\n{dp_text}"
        messages = [
            {
                "role": "system",
                "content": system_content,
            },
            {
                "role": "user",
                "content": (
                    f"项目ID: {project_id}\n章节号: {chapter_number}\n\n{context}\n\n"
                    "请润色以上草稿。只返回润色后的完整正文纯文本。"
                ),
            },
        ]
        max_tokens = self._config_max_tokens(self.llm)
        content = self._invoke_text_for_polisher(
            messages,
            temperature=0.65,
            max_tokens=max_tokens,
            max_retries=None,
            request_timeout_seconds=POLISHER_LONG_FORM_TIMEOUT_SECONDS,
            on_chunk=self.on_text_chunk,
        ).strip()
        content = self._coerce_plain_text_content(content)
        if not content:
            raise OutputValidationError("Polisher 纯正文润色生成空内容")
        return PolisherOutput(
            content=content,
            fact_change_risk="none",
            changed_scope=["sentence", "dialogue", "rhythm", "scene_texture"],
            summary="纯正文润色完成",
            fixed_quality_findings=[],
            deferred_quality_findings=[],
            quality_risk_note=None,
        )

    def _try_segmented_plain_text_polish(
        self,
        state: FactoryState,
        context: str,
        exec_events: list[dict] | None = None,
    ) -> PolisherOutput:
        """Polish long chapters by paragraph chunks in real mode."""
        project_id = state["project_id"]
        chapter_number = state["chapter_number"]
        chapter = self._get_chapter_info(state)
        content = (chapter or {}).get("content") or ""

        if not content.strip():
            raise OutputValidationError("Polisher 分段润色：正文为空")

        chunks = list(chunk_text_by_paragraphs(content, soft_limit=2800))
        total_chunks = len(chunks)

        # If only one chunk, process directly without recursion
        if total_chunks <= 1:
            chunk = chunks[0] if chunks else content
            # v6.8.5: Include death penalty list
            from ..validators.death_penalty import format_death_penalty_for_prompt as _dp_seg
            _dp_txt = _dp_seg()
            _sys = (
                "你是网文工厂的润色编辑。请只输出润色后的完整正文纯文本，"
                "不要输出 JSON、字段名、Markdown、解释或摘要。"
                "必须保留剧情事实、关键事件、伏笔和角色动机。"
                "润色时只改善语言和节奏，不要扩写情节或增加新场景；"
                "润色后总字数不得超过原稿字数的 110%。"
            )
            if _dp_txt:
                _sys = f"{_sys}\n\n{_dp_txt}"
            messages = [
                {
                    "role": "system",
                    "content": _sys,
                },
                {
                    "role": "user",
                    "content": (
                        f"项目ID: {project_id}\n章节号: {chapter_number}\n\n{context}\n\n"
                        "请润色以上草稿。只返回润色后的完整正文纯文本。"
                    ),
                },
            ]
            max_tokens = self._config_max_tokens(self.llm)
            polished = self._invoke_text_for_polisher(
                messages,
                temperature=0.65,
                max_tokens=max_tokens,
                max_retries=None,
                request_timeout_seconds=POLISHER_LONG_FORM_TIMEOUT_SECONDS,
            ).strip()
            polished = self._coerce_plain_text_content(polished)
            if not polished:
                raise OutputValidationError("Polisher 纯正文润色生成空内容")
            return PolisherOutput(
                content=polished,
                fact_change_risk="none",
                changed_scope=["sentence", "dialogue", "rhythm", "scene_texture"],
                summary="纯正文润色完成",
                fixed_quality_findings=[],
                deferred_quality_findings=[],
                quality_risk_note=None,
            )

        segment_outputs: list[str] = []
        failed_segments = 0

        for idx, chunk in enumerate(chunks):
            segment_num = idx + 1
            segment_instruction = (
                f"【分段润色】本段为第{segment_num}/{total_chunks}段，"
                f"请润色以下段落，保持剧情事实不变。"
                f"注意：润色后本段字数不得超过原段落字数的 110%，不要扩写。"
            )
            if idx > 0:
                segment_instruction += " 请确保与上文衔接自然。"
            if idx == total_chunks - 1:
                segment_instruction += " 这是最后一段。"

            # v6.8.5: Include death penalty list per segment
            from ..validators.death_penalty import format_death_penalty_for_prompt as _dp_mc
            _dp_mc_txt = _dp_mc()
            _sys_mc = (
                "你是网文工厂的润色编辑。请只输出润色后的完整正文纯文本，"
                "不要输出 JSON、字段名、Markdown、解释或摘要。"
                "必须保留剧情事实、关键事件、伏笔和角色动机。"
                "润色时只改善语言和节奏，不要扩写情节或增加新场景；"
                "润色后的本段字数不得超过原段落字数的 110%。"
            )
            if _dp_mc_txt:
                _sys_mc = f"{_sys_mc}\n\n{_dp_mc_txt}"
            messages = [
                {
                    "role": "system",
                    "content": _sys_mc,
                },
                {
                    "role": "user",
                    "content": (
                        f"项目ID: {project_id}\n章节号: {chapter_number}\n\n"
                        f"{context}\n\n"
                        f"{segment_instruction}\n\n"
                        f"【待润色段落】\n{chunk}\n\n"
                        f"请只返回润色后的本段正文纯文本。"
                    ),
                },
            ]

            # v6.8.0: Skip segment_started logging (reduces noise)

            try:
                # v6.8.5: Truncation retry for segmented polisher
                config_max = self._config_max_tokens(self.llm)
                try:
                    polished = self._invoke_text_for_polisher(
                        messages,
                        temperature=0.65,
                        max_tokens=config_max,
                        max_retries=None,
                        request_timeout_seconds=POLISHER_LONG_FORM_TIMEOUT_SECONDS,
                    ).strip()
                except LLMError as trunc_err:
                    if "finish_reason=length" not in str(trunc_err):
                        raise
                    seg_retry_max = min(8192, int(config_max * 1.5))
                    logger.warning(
                        "Polisher segment %d: truncation (max_tokens=%d), retrying with %d",
                        segment_num, config_max, seg_retry_max,
                    )
                    polished = self._invoke_text_for_polisher(
                        messages,
                        temperature=0.65,
                        max_tokens=seg_retry_max,
                        max_retries=None,
                        request_timeout_seconds=POLISHER_LONG_FORM_TIMEOUT_SECONDS,
                    ).strip()
                polished = self._coerce_plain_text_content(polished)
                if not polished:
                    raise OutputValidationError(
                        f"Polisher 分段润色第 {segment_num} 段返回空内容"
                    )
                # v6.8.5: Detect per-segment truncation by checking word count
                # ratio.  A >40% loss signals finish_reason=length or severe
                # content degradation that must not silently propagate.
                from ..validators.chapter_checker import count_words as _seg_wc
                seg_in_wc = _seg_wc(chunk)
                seg_out_wc = _seg_wc(polished)
                if seg_in_wc > 100 and seg_out_wc < seg_in_wc * 0.6:
                    raise OutputValidationError(
                        f"Polisher 分段润色第 {segment_num} 段字数异常缩减: "
                        f"{seg_in_wc} → {seg_out_wc} (loss > 40%)"
                    )
            except Exception as e:
                if exec_events is not None:
                    exec_events.append({
                        "event_type": EVENT_SEGMENT_FAILED,
                        "message": f"Polisher 第 {segment_num}/{total_chunks} 段润色失败: {e}",
                        "status": "error",
                        "payload": {
                            "segment_index": segment_num,
                            "error": str(e)[:200],
                        },
                    })
                # v6.10.5: Partial polish — fall back to original chunk for
                # failed segment instead of aborting the entire segmented polish.
                # This avoids passthrough mode in revision chains, which would
                # otherwise block at the v6.10.3 guard.
                logger.warning(
                    "Polisher segment %d/%d failed (%s), using original chunk as fallback",
                    segment_num, total_chunks, e,
                )
                failed_segments += 1
                segment_outputs.append(chunk)
                continue

            segment_outputs.append(polished)

            # v6.8.0: Skip segment_completed logging (reduces noise)

        merged_content = "\n\n".join(segment_outputs)

        # v6.9.0: Post-merge word-count guard against cumulative segment bloat.
        # Each segment may expand slightly; when concatenated the total can
        # exceed the safe upper bound. If that happens, discard the bloated
        # output and keep the original draft so the chapter does not enter a
        # compression → retry loop.
        from ..validators.chapter_checker import count_words as _total_wc
        original_wc = _total_wc(content)
        merged_wc = _total_wc(merged_content)
        if merged_wc > original_wc * 1.25:
            logger.warning(
                "Polisher segmented merge over-expanded: %d -> %d (+%.0f%%), "
                "falling back to original draft",
                original_wc, merged_wc, (merged_wc / original_wc - 1) * 100,
            )
            return PolisherOutput(
                content=content,
                fact_change_risk="none",
                changed_scope=["passthrough"],
                summary=f"分段润色总字数异常膨胀({original_wc}->{merged_wc})，保留原稿",
                fixed_quality_findings=[],
                deferred_quality_findings=[],
                quality_risk_note=None,
            )

        if failed_segments >= total_chunks:
            if exec_events is not None:
                exec_events.append({
                    "event_type": "polisher_degraded",
                    "message": "Polisher 所有分段润色均失败，已保留执笔稿进入后续审核",
                    "status": "warning",
                    "payload": {
                        "failed_segments": failed_segments,
                        "total_segments": total_chunks,
                        "degraded_reason": "all_segments_failed",
                    },
                })
            return PolisherOutput(
                content=content,
                fact_change_risk="none",
                changed_scope=["passthrough"],
                summary=f"分段润色全部失败（{failed_segments}/{total_chunks}），保留原稿",
                fixed_quality_findings=[],
                deferred_quality_findings=["polisher_all_segments_failed"],
                quality_risk_note="polisher_all_segments_failed",
            )

        return PolisherOutput(
            content=merged_content,
            fact_change_risk="none",
            changed_scope=["sentence", "dialogue", "rhythm", "scene_texture"],
            summary=(
                f"分段润色完成（共{total_chunks}段，失败回退{failed_segments}段）"
                if failed_segments else f"分段润色完成（共{total_chunks}段）"
            ),
            fixed_quality_findings=[],
            deferred_quality_findings=(
                ["polisher_partial_segment_fallback"] if failed_segments else []
            ),
            quality_risk_note=(
                "polisher_partial_segment_fallback" if failed_segments else None
            ),
        )

    def _try_compress_overlong_polish(
        self,
        state: FactoryState,
        content: str,
        word_target: int,
        upper_gate_msg: str,
    ) -> str | None:
        """Ask the model once to compress an overlong polished chapter."""
        if state.get("llm_mode") != "real":
            return None

        config_max = self._config_max_tokens(self.llm)
        maximum_allowed = max(word_target + 1200, int(word_target * 1.6))
        chapter_number = state["chapter_number"]
        messages = [
            {
                "role": "system",
                "content": (
                    "你是网文工厂的润色编辑。请只输出压缩后的完整正文纯文本，"
                    "不要输出 JSON、字段名、Markdown、解释或摘要。"
                    "必须保留剧情事实、关键事件、伏笔、角色动机和章末钩子；"
                    "只删除重复铺陈、冗余心理解释、重复环境描写和同义反复，不新增事件。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"第{chapter_number}章润色稿超过字数上限：{upper_gate_msg}。\n"
                    f"请将正文压缩到 {word_target} 到 {maximum_allowed} 字符之间，"
                    "保持小说正文完整、自然、有章末钩子，不要改成摘要。\n\n"
                    f"【当前正文】\n{content}"
                ),
            },
        ]

        try:
            compressed = self._invoke_text_for_polisher(
                messages,
                temperature=0.45,
                # v6.9.0: Chinese text needs ~2-2.5 tokens per character, use 2.5x
                max_tokens=max(2048, min(config_max, int(maximum_allowed * 2.5))),
                max_retries=None,
                request_timeout_seconds=POLISHER_LONG_FORM_TIMEOUT_SECONDS,
            ).strip()
            compressed = self._coerce_plain_text_content(compressed)
            if not compressed:
                return None
            lower_passed, _ = check_word_count_quality_gate(compressed, word_target, "polisher")
            upper_passed, _ = check_word_count_upper_gate(compressed, word_target, "polisher")
            if lower_passed and upper_passed:
                return compressed
        except Exception as e:
            logger.warning("Polisher: compress-overlong retry failed: %s", e)
        return None

    def _invoke_text_for_polisher(
        self,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        max_retries: int | None,
        request_timeout_seconds: int | None,
        on_chunk: Any | None = None,
    ) -> str:
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
                        agent_id=self.agent_id,
                    )
                except TypeError as final_exc:
                    final_text = str(final_exc)
                    if "request_timeout_seconds" not in final_text and "agent_id" not in final_text:
                        raise
                    return self.llm.invoke_text(messages, temperature=temperature, max_tokens=max_tokens)

    @staticmethod
    def _coerce_plain_text_content(text: str) -> str:
        cleaned = str(text or "").strip()
        if not cleaned:
            return ""
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:text|markdown)?\s*", "", cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r"\s*```$", "", cleaned).strip()
        if cleaned.startswith("{") and cleaned.endswith("}"):
            try:
                parsed = json.loads(cleaned)
                if isinstance(parsed, dict) and parsed.get("content"):
                    return str(parsed["content"]).strip()
            except Exception:
                pass
        return cleaned

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
                elif isinstance(colloquial_ratio, (int, float)) and colloquial_ratio < 0.03:
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
                r"明白[^，。！？]{1,8}", r"理解[^，。！？]{1,8}",
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

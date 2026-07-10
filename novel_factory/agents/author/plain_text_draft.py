"""Plain text draft generation mixin for Author agent."""

from __future__ import annotations

import json
import logging
import re
from difflib import SequenceMatcher
from typing import Any

from ...agent_runtime.segmented_generation import chunk_items
from ...workflow.execution_events import EVENT_SEGMENT_FAILED
from ...models.schemas import AuthorOutput
from ...models.state import ChapterStatus, FactoryState
from ...llm.openai_compatible import LLMError, OutputValidationError
from ...llm.provider import is_configured_live_provider
from ...agent_runtime.chapter_text import ensure_chapter_heading, strip_chapter_heading
from ...agent_runtime.revision_context import normalize_revision_review
from ...agent_runtime.context_builder import AgentContextBuilder, format_context_bundle_for_prompt
from ...quality.chapter_seam import build_chapter_seam_context
from ...validators.chapter_checker import count_words

logger = logging.getLogger(__name__)

AUTHOR_LONG_FORM_TIMEOUT_SECONDS = 300


class PlainTextDraftMixin:
    """Mixin providing plain text draft generation methods for Author agent."""

    def _try_plain_text_draft(
        self,
        state: FactoryState,
        task_desc: str,
        context: str,
        exec_events: list[dict] | None = None,
        on_chunk: Any | None = None,
    ) -> AuthorOutput:
        """Generate prose directly when real models fail long-form JSON output."""
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
        is_word_count_retry = False
        if task_desc == "返修":
            existing_chapter = self._get_chapter_info(state) or {}
            existing_body = strip_chapter_heading(
                existing_chapter.get("content", "") or "",
                chapter_number,
                existing_chapter.get("title"),
            )
            existing_len = count_words(existing_body)
            gate = state.get("quality_gate") or {}
            is_word_count_retry = bool(gate.get("word_count_fail"))
            if existing_body.strip() and not is_word_count_retry:
                raw_source = (
                    "【当前保留稿 / 必须在此基础上返修】\n"
                    "下面是当前已保存章节正文。请把它当作底稿进行定点修改："
                    "保留未被 Editor 点名的问题段落、人物关系、已成立事件和整体篇幅，"
                    "只重写或补足退回问题涉及的段落。禁止脱离该底稿另起炉灶重写短版。\n\n"
                    f"{existing_body.strip()}\n"
                )
                revision_source_section = self._limit_context_size(
                    raw_source, limit=3000, agent_id="author-revision-source"
                )
            revision_review = normalize_revision_review(state.get("_revision_review")) or {}
            revision_priority_section = self._revision_blocking_priority_block(revision_review)
            compress_requested = self._revision_requests_compression(revision_review)
            if is_word_count_retry:
                minimum_required = max(minimum_required, int(word_target * 0.85))
                effective_target = word_target
                length_guard_note = (
                    f"【字数扩写提示】当前正文约 {existing_len} 字符，"
                    f"目标 {word_target} 字符，至少 {minimum_required} 字符。"
                    "请在保留现有情节和人物关系的基础上扩写，"
                    "增加场景描写、对话细节和感官描写，不要脱离现有情节另起炉灶。"
                )
            elif existing_len > 0 and not compress_requested:
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
        if is_word_count_retry:
            prose_max_tokens = max(4096, min(8192, int(effective_target * 2.5) + 2048))
        else:
            prose_max_tokens = max(1024, min(config_max, int(effective_target * 2.5) + 1024))
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
            retry_max = min(8192, int(prose_max_tokens * 1.5))
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
        """Return a conservative local patch when revision LLM returns empty."""
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
        time_match = re.search(r'时间节点[\u201c\u201d"]([^\u201c\u201d"]+)[\u201c\u201d"]', feedback_text)
        place_match = re.search(r'地点[\u201c\u201d"]([^\u201c\u201d"]+)[\u201c\u201d"]', feedback_text)
        time_part = f'\u201c{time_match.group(1)}\u201d' if time_match else "上一章留下的时间"
        place = place_match.group(1) if place_match else ""
        place_part = f'和\u201c{place}\u201d这条地点线' if place and len(place) <= 18 else "和上一章留下的地点线"
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
                raw_source = (
                    "【当前保留稿 / 必须在此基础上返修】\n"
                    "下面是当前已保存章节正文。请把它当作底稿进行定点修改："
                    "保留未被 Editor 点名的问题段落、人物关系、已成立事件和整体篇幅，"
                    "只重写或补足退回问题涉及的段落。禁止脱离该底稿另起炉灶重写短版。\n\n"
                    f"{existing_body.strip()}\n"
                )
            revision_source_section = self._limit_context_size(
                raw_source, limit=3000, agent_id="author-segment-revision-source"
            )
            revision_review = normalize_revision_review(state.get("_revision_review")) or {}
            if self._is_internal_repair(state):
                revision_priority_section = self._build_internal_repair_instruction(state)
                revision_review = {}
            else:
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

            try:
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

            if idx < total_chunks - 1:
                accumulated_wc = sum(count_words(seg) for seg in segment_outputs)
                remaining_budget = max(0, chapter_upper_bound - accumulated_wc)
                
                if remaining_budget < segment_target:
                    logger.warning(
                        "Author segmented revision: approaching upper bound "
                        "(%d accumulated, %d remaining, next target %d)",
                        accumulated_wc, remaining_budget, segment_target,
                    )

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
            def _invoke_repair_tail(max_tokens: int) -> str:
                return self._invoke_text_for_author(
                    messages,
                    temperature=0.68,
                    max_tokens=max_tokens,
                    max_retries=None,
                    request_timeout_seconds=(
                        AUTHOR_LONG_FORM_TIMEOUT_SECONDS
                        if is_configured_live_provider(self.llm)
                        else None
                    ),
                )

            try:
                repaired_tail = _invoke_repair_tail(prose_max_tokens)
            except LLMError as trunc_err:
                if "finish_reason=length" not in str(trunc_err):
                    raise
                config_max = self._config_max_tokens(self.llm)
                retry_max_tokens = min(
                    config_max,
                    max(prose_max_tokens + 1024, int(prose_max_tokens * 1.8)),
                )
                if retry_max_tokens <= prose_max_tokens:
                    raise
                logger.warning(
                    "Author: final segment repair truncated (max_tokens=%d), retrying with %d",
                    prose_max_tokens,
                    retry_max_tokens,
                )
                if exec_events is not None:
                    exec_events.append({
                        "event_type": "segment_repair_retry",
                        "message": f"Author 最后分段定向重写被截断，使用 max_tokens={retry_max_tokens} 重试",
                        "status": "warning",
                        "payload": {
                            "reason": "finish_reason=length",
                            "original_max_tokens": prose_max_tokens,
                            "retry_max_tokens": retry_max_tokens,
                        },
                    })
                repaired_tail = _invoke_repair_tail(retry_max_tokens)
            repaired_tail = self._coerce_plain_text_content(repaired_tail)
        except Exception as e:
            logger.warning("Author: final segment targeted repair failed: %s", e)
            if exec_events is not None:
                exec_events.append({
                    "event_type": "segment_repair_failed",
                    "message": f"Author 最后分段定向重写失败，已降级为编辑建议: {e}",
                    "status": "warning",
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
        """Use prose-first authoring for live providers."""
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
        """Build a compact prompt for direct prose generation."""
        is_internal_repair = self._is_internal_repair(state)
        if is_internal_repair:
            limit = self._get_context_char_limit(state)
            return fallback_context[:limit]

        from ...agent_runtime.revision_context import build_revision_feedback_context

        project_id = state["project_id"]
        chapter_number = state["chapter_number"]
        instruction = self._get_instruction(state) or {}
        parts = []

        try:
            builder = AgentContextBuilder(self.repo)
            bundle = builder.build_for_author(project_id, chapter_number, state)
            formatted = format_context_bundle_for_prompt(bundle, agent_name="author", max_chars=8000)
            if formatted:
                parts.append(formatted)

            if bundle.story_facts:
                sorted_facts = sorted(bundle.story_facts, key=lambda f: f.priority)[:8]
                facts_summary = []
                for fact in sorted_facts:
                    facts_summary.append(f"- {fact.text}")
                facts_str = "\n".join(facts_summary)
                parts.append(
                    "【事实账本硬约束】\n"
                    "以下已确认事实必须严格遵守，禁止与之矛盾：\n"
                    f"{facts_str}\n"
                    "如果正文内容与上述事实矛盾，将被判定为严重违规。"
                )

                parts.append(
                    "【生产稳定性约束 v6.10.12】\n"
                    "1. 数值状态变化必须明确书写：涉及魂源、统帅值、积分、血量等数值变化时，"
                    "必须写出'{属性} 从 {旧值} 变为 {新值}'或'{旧值} → {新值}'的显式表述。\n"
                    "2. 修订时严格控制字数：若 Editor 未要求扩写，修订稿增长不得超过上一版的 15%。\n"
                    "3. 仅针对被指出的问题做最小修改，禁止新增场景、支线或过度描写。"
                )
        except Exception:
            pass

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

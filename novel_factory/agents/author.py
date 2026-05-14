"""Author Agent — writes chapter content based on instructions and scene beats."""

from __future__ import annotations

import json
import logging
from typing import Any

from ..models.schemas import AuthorOutput
from ..models.state import ChapterStatus, FactoryState
from ..validators.chapter_checker import (
    validate_chapter_output,
    check_word_count_quality_gate,
    derive_word_target,
    normalize_declared_word_count,
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
from .base import BaseAgent

logger = logging.getLogger(__name__)

AUTHOR_SYSTEM_PROMPT = """你是网文工厂的执笔（Author），负责章节创作。

核心职责：
1. 状态驱动创作 — 严格基于上一章状态卡
2. 动作化叙事 — Show, Don't Tell
3. 精准落实指令 — 不遗漏指令中的任何要素
4. 钩子控制 — 每章末尾必须有悬念

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

    def build_context(self, state: FactoryState) -> str:
        parts = []
        title_contract = self._get_title_contract_context(state["project_id"])
        if title_contract:
            parts.append(title_contract)

        # Writing instruction
        instruction = self._get_instruction(state)
        if instruction:
            word_target = self._get_word_target(state)
            minimum_required = int(word_target * 0.85)
            recommended_target = max(word_target, minimum_required + 500)
            parts.append(f"【写作指令】\n目标: {instruction.get('objective', '')}\n"
                         f"关键事件: {instruction.get('key_events', '')}\n"
                         f"情绪基调: {instruction.get('emotion_tone', '')}\n"
                         f"章末钩子: {instruction.get('ending_hook', '')}\n"
                         f"字数硬要求: 正文 content 至少 {minimum_required} 字符，"
                         f"建议写到 {recommended_target} 字符左右，低于硬要求会自动返修。")

        # R3: Review notes from human review sessions (v3.2)
        project_id = state["project_id"]
        chapter_number = state["chapter_number"]
        review_notes = self.repo.get_chapter_review_notes(project_id, chapter_number)
        if review_notes:
            latest_note = review_notes[0]
            parts.append(f"【人工审核意见】\n{latest_note['notes']}")

        # Scene beats
        beats = self._get_scene_beats(state)
        if beats:
            beats_str = "\n".join(
                f"  {b['sequence']}. 目标: {b.get('scene_goal', '')} | 冲突: {b.get('conflict', '')} | 钩子: {b.get('hook', '')}"
                for b in beats
            )
            parts.append(f"【场景 Beat】\n{beats_str}")

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
        style_ctx = self._get_style_bible_context(project_id, "author")
        if style_ctx:
            parts.append(style_ctx)

        repair_context = self._build_death_penalty_repair_context(state)
        if repair_context:
            parts.append(repair_context)

        # If revision, include review issues
        chapter = self._get_chapter_info(state)
        if chapter and chapter.get("status") == ChapterStatus.REVISION.value:
            review = self.repo.get_latest_review(state["project_id"], chapter["id"])
            if review:
                issues = json.loads(review.get("issues", "[]"))
                suggestions = json.loads(review.get("suggestions", "[]"))
                parts.append(f"【退回问题】\n" + "\n".join(f"- {i}" for i in issues))
                parts.append(f"【修改建议】\n" + "\n".join(f"- {s}" for s in suggestions))

        return "\n\n".join(parts)

    def _execute(self, state: FactoryState) -> dict[str, Any]:
        project_id = state["project_id"]
        chapter_number = state["chapter_number"]

        context = self.build_context(state)

        chapter = self._get_chapter_info(state)
        is_revision = chapter and chapter.get("status") == ChapterStatus.REVISION.value

        task_desc = "返修" if is_revision else "创作"
        system_prompt = f"{AUTHOR_SYSTEM_PROMPT}\n\n{format_death_penalty_for_prompt()}"
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"项目ID: {project_id}\n章节号: {chapter_number}\n任务: {task_desc}\n\n{context}\n\n请{task_desc}第{chapter_number}章。"},
        ]

        if self._should_use_plain_text_primary(state):
            output = self._try_plain_text_draft(state, task_desc, context)
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

        output = self._sanitize_output(output, state)

        self.validate_output(output.model_dump())

        # v5.3.0: Word count quality gate
        word_target = self._get_word_target(state)
        word_gate_passed, word_gate_msg = check_word_count_quality_gate(
            output.content, word_target, "author"
        )
        if not word_gate_passed and state.get("llm_mode") == "real":
            expanded = self._try_expand_short_output(state, output, word_gate_msg)
            if expanded is not None:
                output = expanded
                word_gate_passed, word_gate_msg = check_word_count_quality_gate(
                    output.content, word_target, "author"
                )

        if not word_gate_passed:
            logger.warning("Author: word count quality gate failed: %s", word_gate_msg)
            # Do not advance status, return error for retry
            # P1: Record actual word count and target for traceability
            from ..validators.chapter_checker import count_words
            actual_wc = count_words(output.content)
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
            self.repo.save_artifact(
                project_id, chapter_number, "author", "draft",
                content_json=output.model_dump(),
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
        prose_max_tokens = max(384, min(900, int(word_target * 1.4)))
        compact_context = self._build_plain_text_context(state, context)

        messages = [
            {
                "role": "system",
                "content": (
                    "你是网文工厂的执笔。现在只输出章节正文纯文本。"
                    "禁止输出 JSON、Markdown 代码块、字段名、解释或清单。"
                    "直接从正文第一句开始，到正文最后一句结束。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"项目ID: {project_id}\n章节号: {chapter_number}\n任务: {task_desc}\n"
                    f"正文至少 {minimum_required} 字符，建议接近 {word_target} 字符；"
                    f"最多不要超过 {max(word_target + 250, minimum_required + 250)} 字符。\n\n"
                    f"{compact_context}\n\n"
                    f"请直接写第{chapter_number}章正文。"
                ),
            },
        ]

        content = self.llm.invoke_text(messages, temperature=0.7, max_tokens=prose_max_tokens).strip()
        content = self._coerce_plain_text_content(content)
        if not content:
            raise OutputValidationError("Author 纯正文兜底生成空内容")

        title = self._derive_title(state, instruction)
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

    def _build_plain_text_context(self, state: FactoryState, fallback_context: str) -> str:
        """Build a compact prompt for direct prose generation."""
        instruction = self._get_instruction(state) or {}
        parts = []
        if instruction:
            parts.append(
                "【写作指令】\n"
                f"目标: {instruction.get('objective', '')}\n"
                f"关键事件: {instruction.get('key_events', '')}\n"
                f"情绪基调: {instruction.get('emotion_tone', '')}\n"
                f"章末钩子: {instruction.get('ending_hook', '')}\n"
                f"伏笔: {instruction.get('plots_to_plant', '')}"
            )

        beats = self._get_scene_beats(state)
        if beats:
            beat_lines = []
            for beat in beats[:5]:
                beat_lines.append(
                    f"{beat.get('sequence')}. {beat.get('scene_goal', '')}"
                    f" / 冲突: {beat.get('conflict', '')}"
                    f" / 转折: {beat.get('turn', '')}"
                    f" / 钩子: {beat.get('hook', '')}"
                )
            parts.append("【场景 Beat】\n" + "\n".join(beat_lines))

        characters = self.repo.get_characters(state["project_id"])
        if characters:
            char_lines = [
                f"- {c['name']}({c['role']}): {c.get('description', '')}"
                for c in characters[:5]
            ]
            parts.append("【角色】\n" + "\n".join(char_lines))

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

    def _derive_title(self, state: FactoryState, instruction: dict) -> str:
        chapter = self._get_chapter_info(state) or {}
        title = chapter.get("title") or ""
        if title and not title.startswith("第 ") and title != f"第 {state['chapter_number']} 章":
            return title
        objective = str(instruction.get("objective") or "").strip()
        if objective:
            return f"第{state['chapter_number']}章 {objective[:12]}"
        return f"第{state['chapter_number']}章"

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
        """Apply deterministic safe rewrites before hard death-penalty validation."""
        if state.get("llm_mode") != "real":
            return output
        sanitized_content, replacements = sanitize_death_penalty_text(output.content)
        if not replacements:
            return output
        logger.info(
            "Author: sanitized death-penalty phrases before validation: %s",
            replacements,
        )
        data = output.model_dump()
        data["content"] = sanitized_content
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

        return check_word_count_quality_gate(content, word_target, "author")

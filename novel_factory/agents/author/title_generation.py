"""Title generation logic for Author Agent.

This module contains all title-related methods extracted from AuthorAgent
to improve code organization and maintainability.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from ...models.schemas import TitleGenerationOutput
from ...llm.openai_compatible import TokenUsage
from ...agent_runtime.chapter_text import first_content_line, is_chapter_heading

logger = logging.getLogger(__name__)


class TitleGenerationMixin:
    """Mixin providing title generation and validation methods for AuthorAgent."""

    def _derive_title(
        self,
        state,
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
        state,
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
        state,
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
        text = re.sub(r"^[\"'""''《》【】\s]+|[\"'""''《》【】\s]+$", "", text)
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

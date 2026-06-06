"""Style Editor Lens — prose quality, AI traces, and style fatigue.

Checks for repetitive imagery, AI template phrases, and awkward phrasing.

AI phrase and pattern lists are exposed as module constants so callers
can extend or replace them per project. The lens reads the *current*
module-level constants on each call so monkey-patching for tests works.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from ...models.chapter_contracts import EditorLensReport
from .base_lens import BaseEditorLens

logger = logging.getLogger(__name__)

# Default AI template phrases (death penalty in existing editor).
# Override or extend by mutating this list, or pass a context override.
DEFAULT_AI_PHRASES: list[str] = [
    "嘴角微扬", "嘴角微微上扬", "冷笑", "嗤笑", "嘴角勾起一抹",
    "不禁", "不由得", "下意识", "本能地",
    "心中暗想", "心中暗道", "暗自思忖",
    "眼中闪过一丝", "眸中闪过",
    "一股暖流涌上心头", "一阵暖意",
]

# Default repetitive imagery patterns (regex, description).
DEFAULT_REPETITIVE_IMAGERY: list[tuple[str, str]] = [
    (r"如同.{2,6}一般", "比喻重复"),
    (r"仿佛.{2,6}似的", "比喻重复"),
    (r"宛如.{2,6}一样", "比喻重复"),
]

# Backward-compat aliases (some tests/callers may import these names).
_AI_PHRASES = DEFAULT_AI_PHRASES
_REPETITIVE_IMAGERY = DEFAULT_REPETITIVE_IMAGERY


class StyleEditorLens(BaseEditorLens):
    """Checks prose quality: AI traces, repetitive patterns, style fatigue."""

    lens_type = "style"

    def evaluate(
        self,
        content: str,
        context: dict[str, Any],
        llm: Any | None = None,
    ) -> EditorLensReport:
        findings = []

        if not content or len(content) < 100:
            return EditorLensReport(
                lens_type=self.lens_type,
                passed=True,
                score=100.0,
                summary="内容过短，跳过文风检查",
            )

        # Allow per-call overrides from context (e.g. project-specific lists)
        ai_phrases = context.get("ai_phrases") or DEFAULT_AI_PHRASES
        imagery_patterns = context.get("repetitive_imagery") or DEFAULT_REPETITIVE_IMAGERY

        # Check AI template phrases (death penalty)
        ai_phrase_count = 0
        for phrase in ai_phrases:
            count = content.count(phrase)
            if count > 0:
                ai_phrase_count += count
                findings.append(self._finding(
                    "blocking",
                    "AI_PHRASE",
                    f"检测到AI烂词: '{phrase}' x{count}",
                    f"移除或替换 '{phrase}'",
                ))

        # Check repetitive imagery
        for pattern, desc in imagery_patterns:
            matches = re.findall(pattern, content)
            if len(matches) > 2:
                findings.append(self._finding(
                    "warning",
                    "REPETITIVE_IMAGERY",
                    f"{desc}: 检测到 {len(matches)} 处类似句式",
                    "变换比喻手法，避免重复句式",
                ))

        # Check for straight emotion words (tell vs show)
        straight_emotion = ["感到", "觉得", "意识到", "发现自己"]
        emotion_count = sum(content.count(w) for w in straight_emotion)
        if emotion_count > 5:
            findings.append(self._finding(
                "warning",
                "STRAIGHT_EMOTION",
                f"直白情绪词过多 ({emotion_count}处)，应通过动作/细节展现",
                "用感官细节和动作替代 '感到/觉得' 类表述",
            ))

        # Check info-dump patterns
        info_dump_patterns = [
            (r"所谓.{5,20}就是", "旁白式解释"),
            (r"简单来说", "说教式info dump"),
            (r"在这个世界里", "世界观info dump"),
            (r"这个世界是", "世界观info dump"),
        ]
        for pattern, desc in info_dump_patterns:
            if re.search(pattern, content):
                findings.append(self._finding(
                    "warning",
                    "INFO_DUMP",
                    f"检测到{desc}",
                    "通过角色对话或行动展现设定，避免旁白式解释",
                ))

        # Check style fatigue from ledger
        ledger_context = context.get("ledger_context", {})
        style_ledger = ledger_context.get("style_fatigue", {})
        if style_ledger:
            fatigue_score = style_ledger.get("fatigue_score", 0.0)
            if fatigue_score > 0.7:
                findings.append(self._finding(
                    "warning",
                    "STYLE_FATIGUE",
                    f"风格疲劳指数较高 ({fatigue_score:.2f})",
                    "变换叙事手法、句式结构，避免读者审美疲劳",
                ))

        score = self._compute_score(findings)
        # AI phrases are blocking
        passed = not any(f.severity == "blocking" for f in findings)

        return EditorLensReport(
            lens_type=self.lens_type,
            passed=passed,
            score=score,
            findings=findings,
            summary=f"文风检查: {len(findings)} 个问题 (AI烂词: {ai_phrase_count})",
        )

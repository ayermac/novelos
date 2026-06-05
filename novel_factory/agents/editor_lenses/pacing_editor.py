"""Pacing Editor Lens — pressure/reward rhythm and scene variety.

Checks chapter pacing: pressure balance, scene transitions, tension curves.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from ...models.chapter_contracts import EditorLensReport
from .base_lens import BaseEditorLens

logger = logging.getLogger(__name__)


class PacingEditorLens(BaseEditorLens):
    """Checks pacing: pressure rhythm, scene variety, tension curves."""

    lens_type = "pacing"

    def evaluate(
        self,
        content: str,
        context: dict[str, Any],
        llm: Any | None = None,
    ) -> EditorLensReport:
        findings = []

        if not content or len(content) < 200:
            return EditorLensReport(
                lens_type=self.lens_type,
                passed=True,
                score=100.0,
                summary="内容过短，跳过节奏检查",
            )

        # Check paragraph length variation (sign of good pacing)
        paragraphs = [p.strip() for p in content.split("\n") if p.strip()]
        if len(paragraphs) > 5:
            lengths = [len(p) for p in paragraphs]
            avg_len = sum(lengths) / len(lengths)
            # Check for uniform paragraphs (bad pacing)
            uniform_count = sum(1 for l in lengths if abs(l - avg_len) < avg_len * 0.2)
            if uniform_count > len(lengths) * 0.6:
                findings.append(self._finding(
                    "info",
                    "UNIFORM_PARAGRAPHS",
                    "段落长度过于均匀，缺乏节奏变化",
                    "在紧张场景用短句短段，舒缓场景用长句长段",
                ))

        # Check for action/dialogue vs narration balance
        dialogue_markers = content.count("\u201c") + content.count("\u300c") + content.count("\u300e")
        action_markers = len(re.findall(r"[冲跑跳打踢握挥劈砍刺]", content))
        total_chars = len(content)
        
        if total_chars > 1000:
            dialogue_ratio = dialogue_markers * 50 / total_chars  # rough estimate
            action_ratio = action_markers * 20 / total_chars
            
            if dialogue_ratio < 0.02 and action_ratio < 0.02:
                findings.append(self._finding(
                    "warning",
                    "LOW_SCENE_VARIETY",
                    "场景以叙述为主，缺少对话和动作",
                    "增加对话和动作描写，减少纯叙述段落",
                ))

        # Check for tension indicators
        tension_words = ["危险", "恐惧", "紧张", "压力", "危机", "威胁", "敌", "杀"]
        tension_count = sum(content.count(w) for w in tension_words)
        relief_words = ["轻松", "愉快", "开心", "微笑", "温暖", "安心"]
        relief_count = sum(content.count(w) for w in relief_words)

        # Chapter should have some tension-relief balance
        if tension_count > 10 and relief_count == 0:
            findings.append(self._finding(
                "info",
                "ALL_TENSION_NO_RELIEF",
                "全章高压无释放，可能导致读者疲劳",
                "适当加入舒缓场景或情感释放点",
            ))

        score = self._compute_score(findings)
        passed = not any(f.severity == "blocking" for f in findings)

        return EditorLensReport(
            lens_type=self.lens_type,
            passed=passed,
            score=score,
            findings=findings,
            summary=f"节奏检查: {len(findings)} 个问题",
        )

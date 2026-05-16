"""SceneTextureChecker: detect sensory detail density and action-to-description ratio.

Deterministic validator — no LLM calls.
"""

from __future__ import annotations

import re
from typing import Any

from .base import ValidatorSkill


class SceneTextureChecker(ValidatorSkill):
    """Check scene texture: sensory detail density, action vs description balance."""

    skill_id = "scene-texture"
    version = "1.0.0"

    # Sensory words by modality
    SENSORY_WORDS: list[str] = [
        "光", "影", "声", "响", "味", "香", "臭", "冷", "热", "湿",
        "干燥", "干涩", "风", "雨", "雷", "温度", "颜色", "色彩",
        "光线", "阳光", "月光", "灯光", "阴影", "黑暗",
        "声音", "响声", "噪音", "寂静", "沉默",
        "气味", "香味", "臭味", "气息",
        "寒冷", "炎热", "温暖", "凉爽",
        "触感", "粗糙", "光滑", "柔软", "坚硬",
    ]

    # Action verbs (physical movement)
    ACTION_VERBS: list[str] = [
        "走", "跑", "站", "坐", "看", "听", "说", "拿", "推", "拉",
        "打", "踢", "跳", "爬", "转", "翻", "握", "抓", "挥", "冲",
        "退", "进", "出", "上", "下", "抬", "低", "弯", "直", "靠",
    ]

    @staticmethod
    def _count_unique_sensory_occurrences(text: str, words: list[str]) -> int:
        """Count sensory word occurrences without double-counting overlapping spans.

        Sort words by length descending so longer words (e.g. '阳光') are matched
        before their substrings (e.g. '光').  Each character index can only belong
        to one match.
        """
        occupied = [False] * len(text)
        count = 0
        for w in sorted(words, key=len, reverse=True):
            for m in re.finditer(re.escape(w), text):
                start, end = m.start(), m.end()
                if not any(occupied[start:end]):
                    count += 1
                    for i in range(start, end):
                        occupied[i] = True
        return count

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        text = payload.get("text") or payload.get("content", "")
        if not text:
            return {"ok": True, "error": None, "data": {"score": 100, "findings": []}}

        total_chars = max(len(text), 1)
        findings: list[dict[str, Any]] = []

        # 1. Sensory density (per 1000 chars) — deduplicated overlaps
        sensory_count = self._count_unique_sensory_occurrences(text, self.SENSORY_WORDS)
        sensory_per_1k = (sensory_count / total_chars) * 1000

        # 2. Action verb density
        action_count = sum(text.count(v) for v in self.ACTION_VERBS)
        action_per_1k = (action_count / total_chars) * 1000

        # 3. Paragraphs with no sensory detail at all
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        bare_paras = 0
        for para in paragraphs:
            if not any(w in para for w in self.SENSORY_WORDS):
                bare_paras += 1

        # Score: weighted
        # Sensory 0-50 pts, Action 0-30 pts, Bare para penalty 0-20 pts
        sensory_score = min(sensory_per_1k * 8, 50)
        action_score = min(action_per_1k * 3, 30)
        bare_penalty = min(bare_paras * 3, 20)
        score = max(0, sensory_score + action_score - bare_penalty)

        if sensory_per_1k < 3:
            findings.append({
                "code": "LOW_SENSORY_DETAIL",
                "severity": "warning",
                "message": f"感官细节密度偏低（{sensory_per_1k:.1f}/千字）",
                "evidence": {
                    "sensory_per_1000": round(sensory_per_1k, 1),
                    "action_per_1000": round(action_per_1k, 1),
                    "bare_paragraphs": bare_paras,
                },
                "suggestion": "补充光影、声音、温度或气味等感官线索",
            })

        if action_per_1k < 5:
            findings.append({
                "code": "LOW_ACTION_DETAIL",
                "severity": "info",
                "message": f"动作描写密度偏低（{action_per_1k:.1f}/千字）",
                "evidence": {"action_per_1000": round(action_per_1k, 1)},
                "suggestion": "增加角色的具体动作，避免纯状态描述",
            })

        return {
            "ok": True,
            "error": None,
            "data": {
                "score": round(score, 1),
                "sensory_per_1000": round(sensory_per_1k, 1),
                "action_per_1000": round(action_per_1k, 1),
                "bare_paragraphs": bare_paras,
                "findings": findings,
            },
        }

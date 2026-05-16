"""DialogueNaturalnessChecker: detect functional dialogue and lack of subtext.

Deterministic validator — no LLM calls.
"""

from __future__ import annotations

import re
from typing import Any

from .base import ValidatorSkill


class DialogueNaturalnessChecker(ValidatorSkill):
    """Check dialogue naturalness: ratio, colloquial markers, functional patterns."""

    skill_id = "dialogue-naturalness"
    version = "1.0.0"

    DIALOGUE_PATTERN = r'["\u201c\u300c\u300e]([^"\u201c\u201d\u300d\u300f]+)["\u201d\u300d\u300f]'

    # Colloquial / spoken markers
    COLLOQUIAL_MARKS: list[str] = ["啊", "呢", "吧", "嘛", "哦", "呀", "哈", "哼", "呸"]

    # Functional dialogue patterns (question-answer, pure exposition)
    FUNCTIONAL_PATTERNS: list[str] = [
        r"^(你|我|他|她|它).{0,3}(是|叫|叫|为).{0,5}(谁|什么|名字)",  # "你是谁"
        r"^(这|那).{0,3}(是|叫).{0,5}(什么|哪里|谁)",  # "这是什么"
        r"^(为什么|怎么|如何|何时|哪里).{0,10}\?{0,1}$",  # pure question
    ]

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        text = payload.get("text") or payload.get("content", "")
        if not text:
            return {"ok": True, "error": None, "data": {"score": 100, "findings": []}}

        total_chars = max(len(text), 1)
        findings: list[dict[str, Any]] = []

        dialogues = re.findall(self.DIALOGUE_PATTERN, text)
        dialogue_chars = sum(len(d) for d in dialogues)
        dialogue_ratio = dialogue_chars / total_chars

        # 1. Ratio check
        ratio_score = 0.0
        if 0.1 <= dialogue_ratio <= 0.5:
            ratio_score = 50
        elif dialogue_ratio > 0.05:
            ratio_score = 30
        else:
            ratio_score = 10

        # 2. Colloquial marker check
        colloquial_count = 0
        for d in dialogues:
            if any(m in d for m in self.COLLOQUIAL_MARKS):
                colloquial_count += 1
        colloquial_ratio = colloquial_count / max(len(dialogues), 1) if dialogues else 0
        colloquial_score = min(colloquial_ratio * 50, 30)

        # 3. Functional dialogue check
        functional_count = 0
        for d in dialogues:
            for pattern in self.FUNCTIONAL_PATTERNS:
                if re.search(pattern, d.strip()):
                    functional_count += 1
                    break
        functional_ratio = functional_count / max(len(dialogues), 1) if dialogues else 0
        functional_penalty = min(functional_ratio * 30, 20)

        score = max(0, ratio_score + colloquial_score - functional_penalty)

        if dialogue_ratio < 0.05:
            findings.append({
                "code": "LOW_DIALOGUE_RATIO",
                "severity": "warning",
                "message": f"对白占比过低（{dialogue_ratio*100:.1f}%）",
                "evidence": {"ratio": round(dialogue_ratio, 3), "count": len(dialogues)},
                "suggestion": "增加有冲突或潜台词的角色对话",
            })

        if dialogues and colloquial_ratio < 0.1:
            findings.append({
                "code": "LOW_COLLOQUIAL_MARKERS",
                "severity": "info",
                "message": f"对白口语化标记不足（{colloquial_ratio*100:.0f}% 含语气词）",
                "evidence": {"colloquial_ratio": round(colloquial_ratio, 3)},
                "suggestion": "加入语气词、省略、打断或反问",
            })

        if functional_ratio > 0.3:
            findings.append({
                "code": "HIGH_FUNCTIONAL_DIALOGUE",
                "severity": "info",
                "message": f"功能性对白比例偏高（{functional_ratio*100:.0f}%）",
                "evidence": {"functional_ratio": round(functional_ratio, 3)},
                "suggestion": "让对白承载目的、遮掩、试探或情绪摩擦",
            })

        return {
            "ok": True,
            "error": None,
            "data": {
                "score": round(score, 1),
                "dialogue_ratio": round(dialogue_ratio, 3),
                "dialogue_count": len(dialogues),
                "colloquial_ratio": round(colloquial_ratio, 3),
                "functional_ratio": round(functional_ratio, 3),
                "findings": findings,
            },
        }

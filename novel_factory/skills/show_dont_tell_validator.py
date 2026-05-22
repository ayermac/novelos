"""ShowDontTellValidator: detect straight emotion / tell-instead-of-show patterns.

Deterministic validator — no LLM calls.
Excludes dialogue content from checks.
"""

from __future__ import annotations

import re
from typing import Any

from .base import ValidatorSkill


class ShowDontTellValidator(ValidatorSkill):
    """Detect straight emotion and mental-state words in narrative text.

    Excludes dialogue (quoted content) from detection.
    Returns structured findings with code, severity, message, evidence, suggestion.
    """

    skill_id = "show-dont-tell"
    version = "1.0.0"

    # Narrative-only straight emotion / cognition patterns
    # Keep in sync with polisher.py heuristic (v6.4.2)
    STRAIGHT_PATTERNS: list[str] = [
        r"感到[^，。！？]{1,8}",
        r"觉得[^，。！？]{1,8}",
        r"意识到[^，。！？]{1,8}",
        r"明白[^，。！？]{1,8}",
        r"理解[^，。！？]{1,8}",
        r"察觉[^，。！？]{1,8}",
        r"心中暗想",
        r"心道",
    ]

    # Summary / explaining-away markers (apply to full text)
    SUMMARY_MARKERS: list[str] = [
        "综上所述",
        "总之",
        "简单来说",
        "说白了",
        "总而言之",
    ]

    # Dialogue quote characters (half-width, curly, corner)
    DIALOGUE_QUOTE_OPEN = '"\u201c\u300c\u300e'
    DIALOGUE_QUOTE_CLOSE = '"\u201d\u300d\u300f'

    @staticmethod
    def _strip_dialogue(text: str) -> str:
        """Remove quoted dialogue content, keep quotes as placeholders."""
        return re.sub(
            f'[{ShowDontTellValidator.DIALOGUE_QUOTE_OPEN}]'
            f'.*?'
            f'[{ShowDontTellValidator.DIALOGUE_QUOTE_CLOSE}]',
            '\u300cD\u300d',
            text,
            flags=re.DOTALL,
        )

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        text = payload.get("text") or payload.get("content", "")
        if not text:
            return {"ok": True, "error": None, "data": {"score": 100, "findings": []}}

        narrative_only = self._strip_dialogue(text)
        total_chars = max(len(text), 1)

        findings: list[dict[str, Any]] = []
        straight_count = 0
        hits: list[dict[str, Any]] = []

        for pattern in self.STRAIGHT_PATTERNS:
            matches = list(re.finditer(pattern, narrative_only))
            straight_count += len(matches)
            for m in matches:
                hits.append({
                    "pattern": pattern,
                    "match": m.group(),
                    "position": m.start(),
                })

        summary_count = sum(1 for m in self.SUMMARY_MARKERS if m in text)

        # Score: 100 = none, 0 = very high density
        per_1k = (straight_count / total_chars) * 1000
        score = max(0, 100 - per_1k * 15)
        if summary_count > 0:
            score = max(0, score - summary_count * 10)

        if straight_count > 0:
            severity = "medium" if per_1k > 5 else "info"
            # Limit evidence to avoid huge payloads
            evidence = {
                "count": straight_count,
                "per_1000_chars": round(per_1k, 1),
                "examples": [h["match"] for h in hits[:5]],
            }
            findings.append({
                "code": "STRAIGHT_EMOTION",
                "severity": severity,
                "message": f"检测到 {straight_count} 处直白情绪/心理表达（约 {per_1k:.1f}/千字）",
                "evidence": evidence,
                "suggestion": "将'感到/觉得/意识到'等改为动作、神态或对话展现",
            })

        if summary_count > 0:
            findings.append({
                "code": "SUMMARY_SENTENCE",
                "severity": "info",
                "message": f"检测到 {summary_count} 处总结句",
                "evidence": {"count": summary_count},
                "suggestion": "删除总结句，让场景自然结束",
            })

        return {
            "ok": True,
            "error": None,
            "data": {
                "score": round(score, 1),
                "straight_emotion_count": straight_count,
                "summary_count": summary_count,
                "per_1000_chars": round(per_1k, 1),
                "findings": findings,
            },
        }

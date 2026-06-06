"""WordCountGateSkill: deterministic word count validation.

Wraps validators/chapter_checker.py as a ValidatorSkill.
No LLM calls, no side effects.
"""

from __future__ import annotations

from typing import Any

from .base import ValidatorSkill


class WordCountGateSkill(ValidatorSkill):
    """Check word count against target bounds.

    Delegates to validators.chapter_checker.check_word_count_quality_gate()
    and check_word_count_upper_gate().
    """

    skill_id = "word-count-gate"
    skill_type = "validator"
    version = "1.0.0"

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        from ..validators.chapter_checker import (
            count_words,
            check_word_count_quality_gate,
            check_word_count_upper_gate,
        )

        text = str(payload.get("text") or payload.get("content") or "")
        word_target = int(payload.get("word_target") or 0)
        tolerance_ratio = float(payload.get("tolerance_ratio") or 0.25)

        if not text:
            return {
                "ok": False,
                "error": "缺少 text 字段",
                "data": {
                    "passed": False,
                    "score": 0,
                    "findings": [{"severity": "blocking", "code": "EMPTY_TEXT", "message": "正文为空", "suggestion": "请提供章节正文"}],
                    "summary": "正文为空，无法进行字数检查",
                },
            }

        word_count = count_words(text)
        findings: list[str] = []

        if word_target > 0:
            lower_ok, lower_msg = check_word_count_quality_gate(text, word_target, tolerance_ratio)
            upper_ok, upper_msg = check_word_count_upper_gate(text, word_target, tolerance_ratio)
            if not lower_ok:
                findings.append({"severity": "blocking", "code": "WORD_COUNT_LOW", "message": lower_msg, "suggestion": "请增加正文内容"})
            if not upper_ok:
                findings.append({"severity": "blocking", "code": "WORD_COUNT_HIGH", "message": upper_msg, "suggestion": "请精简正文内容"})
        else:
            lower_ok, upper_ok = True, True

        passed = lower_ok and upper_ok
        score = 100 if passed else 60
        summary = f"字数检查{'通过' if passed else '未通过'}，当前字数: {word_count}，目标: {word_target}"
        
        return {
            "ok": passed,
            "error": "; ".join([f["message"] for f in findings]) if not passed else None,
            "data": {
                "passed": passed,
                "score": score,
                "findings": findings,
                "summary": summary,
                "word_count": word_count,
                "target": word_target,
                "lower_bound": int(word_target * (1 - tolerance_ratio)) if word_target else 0,
                "upper_bound": int(word_target * (1 + tolerance_ratio)) if word_target else 0,
            },
        }

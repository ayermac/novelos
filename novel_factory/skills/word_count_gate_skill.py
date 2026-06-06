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
                "data": {"passed": False, "word_count": 0, "target": word_target, "issues": ["正文为空"]},
            }

        word_count = count_words(text)
        issues: list[str] = []

        if word_target > 0:
            lower_ok, lower_msg = check_word_count_quality_gate(text, word_target, tolerance_ratio)
            upper_ok, upper_msg = check_word_count_upper_gate(text, word_target, tolerance_ratio)
            if not lower_ok:
                issues.append(lower_msg)
            if not upper_ok:
                issues.append(upper_msg)
        else:
            lower_ok, upper_ok = True, True

        passed = lower_ok and upper_ok
        return {
            "ok": passed,
            "error": "; ".join(issues) if not passed else None,
            "data": {
                "passed": passed,
                "word_count": word_count,
                "target": word_target,
                "lower_bound": int(word_target * (1 - tolerance_ratio)) if word_target else 0,
                "upper_bound": int(word_target * (1 + tolerance_ratio)) if word_target else 0,
                "issues": issues,
            },
        }

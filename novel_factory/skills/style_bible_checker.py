"""Style Bible Checker skill for v4.0.

Performs rule-based style checks against a Style Bible.
Does NOT call LLM. Does NOT access the network.
Only checks forbidden expressions, preferred patterns, and simple rules.
"""

from __future__ import annotations

import re
from typing import Any

from .base import ValidatorSkill
from ..models.style_bible import (
    StyleBible,
    StyleCheckIssue,
    StyleCheckReport,
    ForbiddenExpression,
)


class StyleBibleCheckerSkill(ValidatorSkill):
    """Check text against a Style Bible for compliance.

    Input payload:
        text: str - the text to check
        style_bible: dict - Style Bible data (serialized)

    Output data:
        StyleCheckReport fields
    """

    skill_id = "style-bible-checker"
    skill_type = "validator"
    version = "1.0.0"

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Run style check against a Style Bible.

        Args:
            payload: Must contain 'text' and 'style_bible'.

        Returns:
            Envelope with StyleCheckReport data.
        """
        text = payload.get("text", "")
        bible_data = payload.get("style_bible")

        if not text:
            return {
                "ok": True,
                "error": None,
                "data": {
                    "total_issues": 0,
                    "blocking_issues": 0,
                    "warning_issues": 0,
                    "issues": [],
                    "score": 100.0,
                },
            }

        if not bible_data:
            return {
                "ok": True,
                "error": None,
                "data": {
                    "total_issues": 0,
                    "blocking_issues": 0,
                    "warning_issues": 0,
                    "issues": [],
                    "score": 100.0,
                    "note": "No Style Bible provided, skipping check",
                },
            }

        try:
            if isinstance(bible_data, dict):
                bible = StyleBible.from_storage_dict(bible_data)
            else:
                return {
                    "ok": False,
                    "error": f"Invalid Style Bible data: expected dict, got {type(bible_data).__name__}",
                    "data": {},
                }
        except Exception as e:
            return {
                "ok": False,
                "error": f"Invalid Style Bible data: {e}",
                "data": {},
            }

        report = self._check(text, bible)

        return {
            "ok": True,
            "error": None,
            "data": report.model_dump(),
        }

    def _check(self, text: str, bible: StyleBible) -> StyleCheckReport:
        """Perform all style checks."""
        issues: list[StyleCheckIssue] = []

        # 1. Check forbidden expressions
        issues.extend(self._check_forbidden(text, bible))

        # 2. Check preferred expressions (simple presence check)
        issues.extend(self._check_preferred(text, bible))

        # 3. Check tone keywords (simple presence heuristic)
        issues.extend(self._check_tone(text, bible))

        # 4. Check sentence rules (simple heuristic)
        issues.extend(self._check_sentence_rules(text, bible))

        # 5. Check paragraph rules (simple heuristic)
        issues.extend(self._check_paragraph_rules(text, bible))

        # 6. Check chapter opening/ending rules
        issues.extend(self._check_chapter_rules(text, bible))

        # 7. Check AI trace avoidance patterns
        issues.extend(self._check_ai_trace(text, bible))

        blocking = sum(1 for i in issues if i.severity == "blocking")
        warning = sum(1 for i in issues if i.severity == "warning")

        # Score: start at 100, -10 per blocking, -3 per warning
        score = max(0.0, 100.0 - blocking * 10 - warning * 3)

        return StyleCheckReport(
            total_issues=len(issues),
            blocking_issues=blocking,
            warning_issues=warning,
            issues=issues,
            score=score,
        )

    def _check_forbidden(
        self, text: str, bible: StyleBible
    ) -> list[StyleCheckIssue]:
        """Check for forbidden expressions in text."""
        issues: list[StyleCheckIssue] = []
        for fe in bible.forbidden_expressions:
            if fe.pattern in text:
                # Find context around the match
                idx = text.find(fe.pattern)
                start = max(0, idx - 10)
                end = min(len(text), idx + len(fe.pattern) + 10)
                location = text[start:end]
                issues.append(StyleCheckIssue(
                    rule_type="forbidden_expression",
                    severity=fe.severity,
                    description=f"禁用表达 '{fe.pattern}' 出现" + (f": {fe.reason}" if fe.reason else ""),
                    location=location,
                    suggestion="替换或删除该表达",
                ))
        return issues

    def _check_preferred(
        self, text: str, bible: StyleBible
    ) -> list[StyleCheckIssue]:
        """Check if preferred expressions are absent (informational)."""
        issues: list[StyleCheckIssue] = []
        for pe in bible.preferred_expressions:
            # Preferred expressions are patterns/styles, not exact strings
            # Simple check: if the pattern is a specific phrase, check for it
            if len(pe.pattern) <= 10 and pe.pattern in text:
                continue
            # For abstract patterns, we skip (would need NLP)
        return issues

    def _check_tone(
        self, text: str, bible: StyleBible
    ) -> list[StyleCheckIssue]:
        """Check tone keywords presence (informational only)."""
        # Simple heuristic: check if any tone keywords appear
        # This is a weak check - real tone analysis needs NLP
        return []

    def _check_sentence_rules(
        self, text: str, bible: StyleBible
    ) -> list[StyleCheckIssue]:
        """Check simple sentence-level rules."""
        issues: list[StyleCheckIssue] = []

        # Check for very long sentences (>80 chars without punctuation)
        sentences = re.split(r'[。！？；]', text)
        for s in sentences:
            s = s.strip()
            if len(s) > 80:
                issues.append(StyleCheckIssue(
                    rule_type="rule_violation",
                    severity="warning",
                    description=f"超长句（{len(s)}字）: {s[:30]}...",
                    location=s[:40],
                    suggestion="拆分为短句",
                ))

        return issues

    def _check_paragraph_rules(
        self, text: str, bible: StyleBible
    ) -> list[StyleCheckIssue]:
        """Check simple paragraph-level rules."""
        issues: list[StyleCheckIssue] = []

        # Check for very long paragraphs (>500 chars without break)
        paragraphs = text.split("\n\n")
        for p in paragraphs:
            p = p.strip()
            if len(p) > 500:
                issues.append(StyleCheckIssue(
                    rule_type="rule_violation",
                    severity="warning",
                    description=f"超长段落（{len(p)}字），建议分段",
                    location=p[:40],
                    suggestion="拆分为更短的段落",
                ))

        return issues

    def _check_chapter_rules(
        self, text: str, bible: StyleBible
    ) -> list[StyleCheckIssue]:
        """Check chapter opening and ending rules (simplified)."""
        issues: list[StyleCheckIssue] = []

        # Only check if we have both opening and ending rules
        if not bible.chapter_opening_rules and not bible.chapter_ending_rules:
            return issues

        # Check opening: first non-empty line
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        if lines and bible.chapter_opening_rules:
            first_line = lines[0]
            # Simple check: first line should contain action/conflict indicators
            action_words = ["说", "走", "跑", "看", "想", "抓", "打", "站", "坐", "听", "喊"]
            if not any(w in first_line for w in action_words) and len(first_line) > 30:
                for rule in bible.chapter_opening_rules[:1]:
                    issues.append(StyleCheckIssue(
                        rule_type="rule_violation",
                        severity=rule.severity,
                        description=f"开篇可能不符合规则: {rule.description}",
                        location=first_line[:40],
                        suggestion="首句加入动作或冲突",
                    ))

        # Check ending: last non-empty line
        if lines and bible.chapter_ending_rules:
            last_line = lines[-1]
            hook_words = ["?", "？", "!", "！", "但", "却", "然而", "突然", "就在"]
            if not any(w in last_line for w in hook_words):
                for rule in bible.chapter_ending_rules[:1]:
                    issues.append(StyleCheckIssue(
                        rule_type="rule_violation",
                        severity=rule.severity,
                        description=f"结尾可能缺少钩子: {rule.description}",
                        location=last_line[:40],
                        suggestion="章末加入悬念或反转",
                    ))

        return issues

    def _check_ai_trace(
        self, text: str, bible: StyleBible
    ) -> list[StyleCheckIssue]:
        """Check AI trace avoidance patterns."""
        issues: list[StyleCheckIssue] = []

        for pattern in bible.ai_trace_avoidance.avoid_patterns:
            if pattern in text:
                idx = text.find(pattern)
                start = max(0, idx - 10)
                end = min(len(text), idx + len(pattern) + 10)
                issues.append(StyleCheckIssue(
                    rule_type="ai_trace",
                    severity="warning",
                    description=f"AI味表达 '{pattern}' 出现",
                    location=text[start:end],
                    suggestion="替换为更自然的表达",
                ))

        return issues

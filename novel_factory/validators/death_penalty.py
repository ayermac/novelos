"""Death penalty validator — detects forbidden AI-style expressions.

v1.2 extends from hardcoded list to structured rules with:
- Exact word matching
- Substring matching
- Regex matching
- Severity levels: critical/high/medium/low

Critical violations trigger Author/Polisher failure.
"""

from __future__ import annotations

import re
from typing import Any

from ..models.quality import (
    DeathPenaltyResult,
    DeathPenaltyRule,
    PenaltyMatchType,
    PenaltySeverity,
)


# ── Default structured rules ───────────────────────────────────

DEFAULT_RULES: list[DeathPenaltyRule] = [
    # ── 表情动作类 (critical) ──
    DeathPenaltyRule(
        code="DP_EXPR_01", pattern="冷笑", match_type=PenaltyMatchType.EXACT,
        severity=PenaltySeverity.CRITICAL, category="ai_trace",
        description="典型AI表情", alternatives=["淡淡一笑", "轻哼一声"],
    ),
    DeathPenaltyRule(
        code="DP_EXPR_02", pattern="嘴角微扬", match_type=PenaltyMatchType.EXACT,
        severity=PenaltySeverity.CRITICAL, category="ai_trace",
        description="典型AI表情", alternatives=["微微勾唇"],
    ),
    DeathPenaltyRule(
        code="DP_EXPR_03", pattern="嘴角勾起", match_type=PenaltyMatchType.EXACT,
        severity=PenaltySeverity.CRITICAL, category="ai_trace",
        description="典型AI表情", alternatives=["唇角微弯"],
    ),
    DeathPenaltyRule(
        code="DP_EXPR_04", pattern="倒吸一口凉气", match_type=PenaltyMatchType.EXACT,
        severity=PenaltySeverity.CRITICAL, category="ai_trace",
        description="典型AI反应", alternatives=["心中一凛", "瞳孔微缩"],
    ),
    DeathPenaltyRule(
        code="DP_EXPR_05", pattern="眼中闪过", match_type=PenaltyMatchType.EXACT,
        severity=PenaltySeverity.CRITICAL, category="ai_trace",
        description="典型AI表情", alternatives=["目光一闪", "眸中掠过"],
    ),
    DeathPenaltyRule(
        code="DP_EXPR_06", pattern="眼中闪现", match_type=PenaltyMatchType.EXACT,
        severity=PenaltySeverity.CRITICAL, category="ai_trace",
        description="典型AI表情", alternatives=["目光中浮现"],
    ),
    DeathPenaltyRule(
        code="DP_EXPR_07", pattern="眼中精光", match_type=PenaltyMatchType.EXACT,
        severity=PenaltySeverity.CRITICAL, category="ai_trace",
        description="典型AI表情", alternatives=["目光锐利"],
    ),
    DeathPenaltyRule(
        code="DP_EXPR_08", pattern="眼中寒芒", match_type=PenaltyMatchType.EXACT,
        severity=PenaltySeverity.CRITICAL, category="ai_trace",
        description="典型AI表情", alternatives=["目光冰冷"],
    ),
    # ── 句式类 (critical) ──
    DeathPenaltyRule(
        code="DP_SENT_01", pattern="不仅.*而且.*更是", match_type=PenaltyMatchType.REGEX,
        severity=PenaltySeverity.CRITICAL, category="ai_trace",
        description="典型AI递进句式", alternatives=["既...又...", "不但...而且..."],
    ),
    DeathPenaltyRule(
        code="DP_SENT_02", pattern="心中暗想", match_type=PenaltyMatchType.EXACT,
        severity=PenaltySeverity.CRITICAL, category="ai_trace",
        description="典型AI内心独白", alternatives=["心想", "暗自思忖", "心下琢磨"],
    ),
    DeathPenaltyRule(
        code="DP_SENT_03", pattern="心道", match_type=PenaltyMatchType.EXACT,
        severity=PenaltySeverity.HIGH, category="ai_trace",
        description="古风内心独白", alternatives=["心想", "暗道"],
    ),
    DeathPenaltyRule(
        code="DP_SENT_04", pattern="夜色笼罩", match_type=PenaltyMatchType.EXACT,
        severity=PenaltySeverity.HIGH, category="ai_trace",
        description="典型AI环境描写", alternatives=["夜色渐浓", "暮色四合"],
    ),
    DeathPenaltyRule(
        code="DP_SENT_05", pattern="夜幕降临", match_type=PenaltyMatchType.EXACT,
        severity=PenaltySeverity.HIGH, category="ai_trace",
        description="典型AI环境描写", alternatives=["天色将晚", "暮色已深"],
    ),
    # ── 说教类 (critical) ──
    DeathPenaltyRule(
        code="DP_PREACH_01", pattern="不禁感慨", match_type=PenaltyMatchType.EXACT,
        severity=PenaltySeverity.CRITICAL, category="ai_trace",
        description="典型AI说教", alternatives=[],
    ),
    DeathPenaltyRule(
        code="DP_PREACH_02", pattern="人生道理", match_type=PenaltyMatchType.SUBSTRING,
        severity=PenaltySeverity.HIGH, category="ai_trace",
        description="章末总结人生道理", alternatives=[],
    ),
    DeathPenaltyRule(
        code="DP_PREACH_03", pattern="哲理感慨", match_type=PenaltyMatchType.SUBSTRING,
        severity=PenaltySeverity.HIGH, category="ai_trace",
        description="上帝视角哲理", alternatives=[],
    ),
    # ── 中等严重度 ──
    DeathPenaltyRule(
        code="DP_MED_01", pattern="缓缓地", match_type=PenaltyMatchType.EXACT,
        severity=PenaltySeverity.MEDIUM, category="ai_trace",
        description="AI常见副词", alternatives=["慢慢", "渐渐"],
    ),
    DeathPenaltyRule(
        code="DP_MED_02", pattern="不由得", match_type=PenaltyMatchType.EXACT,
        severity=PenaltySeverity.MEDIUM, category="ai_trace",
        description="AI常见副词", alternatives=["忍不住", "情不自禁"],
    ),
    DeathPenaltyRule(
        code="DP_MED_03", pattern="一抹.*浮现", match_type=PenaltyMatchType.REGEX,
        severity=PenaltySeverity.MEDIUM, category="ai_trace",
        description="AI模板表达", alternatives=[],
    ),
]


def check_death_penalty(
    text: str,
    rules: list[DeathPenaltyRule] | None = None,
) -> list[str]:
    """Check text for death-penalty violations.

    Returns:
        List of matched violation strings (pattern or code).
        Empty list means no violations.
    """
    result = check_death_penalty_structured(text, rules)
    return result.violations


def check_death_penalty_structured(
    text: str,
    rules: list[DeathPenaltyRule] | None = None,
) -> DeathPenaltyResult:
    """Check text for death-penalty violations with structured result.

    Returns:
        DeathPenaltyResult with violations list, has_critical flag, and details.
    """
    # R1: Defensive handling for None text
    if text is None:
        text = ""
    
    if rules is None:
        rules = DEFAULT_RULES

    violations: list[str] = []
    has_critical = False
    details: list[dict[str, Any]] = []

    for rule in rules:
        matched = False
        if rule.match_type == PenaltyMatchType.EXACT:
            matched = rule.pattern in text
        elif rule.match_type == PenaltyMatchType.SUBSTRING:
            matched = rule.pattern in text
        elif rule.match_type == PenaltyMatchType.REGEX:
            try:
                matched = bool(re.search(rule.pattern, text))
            except re.error:
                continue

        if matched:
            violations.append(rule.pattern)
            details.append({
                "code": rule.code,
                "pattern": rule.pattern,
                "severity": rule.severity.value,
                "category": rule.category,
            })
            if rule.severity == PenaltySeverity.CRITICAL:
                has_critical = True

    return DeathPenaltyResult(
        violations=violations,
        has_critical=has_critical,
        details=details,
    )


def has_death_penalty(text: str) -> bool:
    """Quick check: does the text contain any death-penalty violation?"""
    return len(check_death_penalty(text)) > 0


def has_critical_violation(text: str) -> bool:
    """Check if text has any critical-severity violation."""
    result = check_death_penalty_structured(text)
    return result.has_critical


def format_death_penalty_for_prompt(
    rules: list[DeathPenaltyRule] | None = None,
) -> str:
    """Format death penalty rules as a context prompt section.

    Returns a string suitable for injection into Agent prompts.
    """
    if rules is None:
        rules = DEFAULT_RULES

    critical_lines = []
    other_lines = []

    for rule in rules:
        alt = f" → 替代: {'/'.join(rule.alternatives)}" if rule.alternatives else ""
        line = f"- [{rule.severity.value.upper()}] {rule.pattern}{alt}  ({rule.description})"

        if rule.severity == PenaltySeverity.CRITICAL:
            critical_lines.append(line)
        else:
            other_lines.append(line)

    parts = ["【死刑红线 - 触发即拒绝】"]
    if critical_lines:
        parts.append("\n致命级（CRITICAL — 触发即失败）：")
        parts.extend(critical_lines)

    if other_lines:
        parts.append("\n警告级：")
        parts.extend(other_lines)

    return "\n".join(parts)

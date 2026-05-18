"""Editor Pass/Fail 策略系统化（v6.6.0）

将 Editor 判定拆分为 blocking / revision / advisory 三类。
高分 advisory 不再触发自动返修。
"""

from __future__ import annotations
from typing import Literal
from dataclasses import dataclass


@dataclass
class EditorDecision:
    pass_: bool
    revision_needed: bool
    category: Literal["blocking", "revision", "advisory"]
    reason: str
    recommended_action: str


def classify_editor_result(
    score: float,
    issues: list[str],
    has_blocking: bool = False,
    has_hard_word_fail: bool = False,
    has_death_penalty: bool = False,
    quality_priority_count: int = 0,
    quality_advisory_only: bool = False,
) -> EditorDecision:
    """
    核心判定逻辑 (v6.6.1)

    quality_priority_count: 来自 deterministic quality diagnosis 的高优先级问题数量
    quality_advisory_only: 是否所有 quality diagnosis 项都是 advisory
    """
    hard_issue_markers = (
        "CRITICAL",
        "死刑红线",
        "硬伤",
        "硬冲突",
        "设定冲突",
        "逻辑漏洞",
        "时间线矛盾",
    )
    advisory_markers = (
        "v6.4质量信号",
        "LOW_COLLOQUIAL",
        "STRAIGHT_EMOTION",
        "EXPOSITION_PARAGRAPH",
        "场景描写较少",
        "章末钩子强度不足",
        "人物动机表达不够清晰",
        "字数偏低",
    )
    has_hard_issue_text = any(
        any(marker in str(issue) for marker in hard_issue_markers)
        for issue in issues
    )
    advisory_only = bool(issues) and all(
        any(marker in str(issue) for marker in advisory_markers)
        for issue in issues
    )

    has_quality_priority = quality_priority_count > 0

    effective_blocking = (
        has_blocking or has_hard_word_fail or has_death_penalty or has_hard_issue_text
    )

    if effective_blocking:
        return EditorDecision(
            pass_=False,
            revision_needed=True,
            category="blocking",
            reason="存在 blocking issue（death penalty / hard word fail / 硬冲突）",
            recommended_action="必须返修或人工介入",
        )

    # v6.6.1: advisory-only quality diagnosis does not override 85+ review score
    if score >= 85:
        if advisory_only and quality_advisory_only:
            return EditorDecision(
                pass_=True,
                revision_needed=False,
                category="advisory",
                reason="审核分 >= 85，所有问题（含诊断）均为 advisory",
                recommended_action="进入 awaiting_publish with warnings，不自动返修",
            )
        return EditorDecision(
            pass_=True,
            revision_needed=False,
            category="advisory",
            reason="分数 >= 85 且无 blocking issues",
            recommended_action="进入 awaiting_publish 或 human_review（带 warning）",
        )

    # v6.6.1: quality diagnosis priority findings prevent advisory-only auto-pass
    # when score < 85. They do NOT override score >= 85.
    if score >= 80 and (advisory_only or quality_advisory_only) and not has_quality_priority:
        return EditorDecision(
            pass_=True,
            revision_needed=False,
            category="advisory",
            reason="分数 80-84，advisory issues / quality diagnosis 可接受",
            recommended_action="推荐 human_review 或 awaiting_publish with warnings",
        )

    # score < 80, or score 80-84 with quality priority findings
    return EditorDecision(
        pass_=False,
        revision_needed=True,
        category="revision",
        reason=(
            "分数 < 80，需要自动返修"
            if score < 80
            else "分数 80-84 但存在质量诊断高优先级问题，需要返修"
        ),
        recommended_action="路由回对应 Agent 返修",
    )


def post_process_llm_decision(
    llm_pass: bool,
    score: float,
    issues: list[str],
    *,
    has_blocking: bool = False,
    has_hard_word_fail: bool = False,
    has_death_penalty: bool = False,
    quality_priority_count: int = 0,
    quality_advisory_only: bool = False,
) -> EditorDecision:
    """纠正 LLM 过度苛刻的情况 (v6.6.1)"""
    decision = classify_editor_result(
        score,
        issues,
        has_blocking=has_blocking,
        has_hard_word_fail=has_hard_word_fail,
        has_death_penalty=has_death_penalty,
        quality_priority_count=quality_priority_count,
        quality_advisory_only=quality_advisory_only,
    )

    # LLM 说不通过，但实际是高分 advisory
    if not llm_pass and decision.category == "advisory":
        return EditorDecision(
            pass_=True,
            revision_needed=False,
            category="advisory",
            reason="LLM 过度苛刻，已通过后处理纠偏",
            recommended_action="进入 awaiting_publish with warnings",
        )

    return decision

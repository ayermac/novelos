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
) -> EditorDecision:
    """
    核心判定逻辑
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

    blocking = has_blocking or has_hard_word_fail or has_death_penalty or has_hard_issue_text

    if blocking:
        return EditorDecision(
            pass_=False,
            revision_needed=True,
            category="blocking",
            reason="存在 blocking issue（death penalty / hard word fail / 硬冲突）",
            recommended_action="必须返修或人工介入",
        )

    if score >= 85 or (score >= 80 and advisory_only):
        return EditorDecision(
            pass_=True,
            revision_needed=False,
            category="advisory",
            reason="分数 >= 85 且无 blocking issues",
            recommended_action="进入 awaiting_publish 或 human_review（带 warning）",
        )

    if 80 <= score < 85:
        return EditorDecision(
            pass_=True,
            revision_needed=False,
            category="advisory",
            reason="分数 80-84，advisory issues 可接受",
            recommended_action="推荐 human_review 或 awaiting_publish with warnings",
        )

    # score < 80
    return EditorDecision(
        pass_=False,
        revision_needed=True,
        category="revision",
        reason="分数 < 80，需要自动返修",
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
) -> EditorDecision:
    """纠正 LLM 过度苛刻的情况"""
    decision = classify_editor_result(
        score,
        issues,
        has_blocking=has_blocking,
        has_hard_word_fail=has_hard_word_fail,
        has_death_penalty=has_death_penalty,
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

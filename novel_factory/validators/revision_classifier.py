"""Revision classifier — categorizes editor issues and determines revision_target.

Q7: Instead of relying solely on LLM self-reported revision_target, this
classifier independently categorizes each issue and determines the most
appropriate target agent.
"""

from __future__ import annotations

import re
from typing import Any

from ..models.quality import ClassifiedIssue, IssueCategory, RevisionClassifyResult


# ── Keyword-based classification rules ─────────────────────────

_CATEGORY_KEYWORDS: dict[IssueCategory, list[str]] = {
    IssueCategory.TEXT: [
        "AI味", "AI烂词", "句式", "文风", "模板化", "陈词滥调",
        "说教", "语言质感", "对话节奏", "AI痕迹", "烂词",
        "冷笑", "嘴角", "倒吸一口凉气", "心中暗想",
        "表达", "遣词", "用词", "描写", "修辞",
    ],
    IssueCategory.PACING: [
        "节奏", "拖沓", "急促", "高潮", "悬念", "钩子",
        "章末", "铺垫", "爽点", "平淡", "推进",
    ],
    IssueCategory.LOGIC: [
        "逻辑", "漏洞", "硬伤", "降智", "矛盾", "不合理",
        "因果", "推理", "自相矛盾", "说不通",
    ],
    IssueCategory.PLOT: [
        "伏笔", "情节", "剧情", "事件", "伏线", "铺垫",
        "回收", "兑现", "埋设", "伏笔引用",
    ],
    IssueCategory.SETTING: [
        "设定", "世界观", "体系", "规则", "背景",
        "力量体系", "等级", "门派", "势力",
    ],
    IssueCategory.STATE: [
        "状态卡", "数值", "等级跳变", "位置", "角色关系",
        "状态不一致", "数值漂移",
    ],
    IssueCategory.POISON: [
        "毒点", "读者厌恶", "套路", "反感", "劝退",
        "圣母", "降智", "无脑", "恶心",
    ],
}

# Category → default revision_target mapping
_CATEGORY_TARGET: dict[IssueCategory, str] = {
    IssueCategory.TEXT: "polisher",
    IssueCategory.PACING: "polisher",
    IssueCategory.LOGIC: "author",
    IssueCategory.PLOT: "author",
    IssueCategory.SETTING: "author",
    IssueCategory.STATE: "author",
    IssueCategory.POISON: "author",  # poison can be both; default to author
}


def classify_issue(issue: str) -> ClassifiedIssue:
    """Classify a single issue string into a category and target.

    Uses keyword matching. Falls back to 'logic' if no keywords match.
    """
    best_category = IssueCategory.LOGIC  # default
    best_score = 0

    for category, keywords in _CATEGORY_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in issue)
        if score > best_score:
            best_score = score
            best_category = category

    target = _CATEGORY_TARGET[best_category]
    return ClassifiedIssue(
        issue=issue,
        category=best_category,
        revision_target=target,
    )


def classify_issues(
    issues: list[str],
    llm_revision_target: str | None = None,
) -> RevisionClassifyResult:
    """Classify a list of editor issues and determine the dominant revision target.

    Args:
        issues: List of issue descriptions from Editor.
        llm_revision_target: The LLM's self-reported revision_target, used
            as a tiebreaker or when classification is uncertain.

    Returns:
        RevisionClassifyResult with classified issues and dominant target.
    """
    classified = [classify_issue(issue) for issue in issues]

    # Count categories
    category_counts: dict[str, int] = {}
    target_counts: dict[str, int] = {}

    for ci in classified:
        cat = ci.category.value
        category_counts[cat] = category_counts.get(cat, 0) + 1
        tgt = ci.revision_target
        target_counts[tgt] = target_counts.get(tgt, 0) + 1

    # Determine dominant target
    if target_counts:
        dominant_target = max(target_counts, key=target_counts.get)  # type: ignore[arg-type]
    else:
        dominant_target = llm_revision_target or "author"

    # Special case: if LLM says "planner" and there are setting/source issues,
    # respect the planner target
    if llm_revision_target == "planner":
        setting_count = category_counts.get("setting", 0)
        if setting_count > 0:
            dominant_target = "planner"

    return RevisionClassifyResult(
        issues=classified,
        dominant_target=dominant_target,
        category_counts=category_counts,
    )

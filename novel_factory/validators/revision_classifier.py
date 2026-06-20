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
    # v6.10.9: Beat 设计层问题 → Screenwriter
    IssueCategory.BEAT_DESIGN: [
        "核心循环设计缺陷", "beat 设计", "场景 beat 设计",
        "爽点标记缺失", "核心循环未标记", "对白槽位缺失",
        "事实锁设计", "角色状态设计", "character_states",
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
    IssueCategory.BEAT_DESIGN: "screenwriter",  # v6.10.9: beat 设计层问题 → Screenwriter
}

_AUTHOR_STRUCTURAL_KEYWORDS = (
    "[CRITICAL]",
    "[DIALOGUE]",
    "[HOOK]",
    "LOW_DIALOGUE_RATIO",
    "对白占比",
    "对白仅占",
    "对白过低",
    "缺少角色言行",
    "角色对话",
    "动作场景呈现",
    "增加对话",
    "新增对话",
    "补充对话",
    "有分歧的对话",
    "面对面的张力",
    "冲突强度",
    "缺乏冲突",
    "章节在核心冲突",
    "断裂",
    "没有后续动作",
    "没有后续决定",
    "没有后续动作/决定/结果",
    "无法得知",
    "严重破坏阅读完整性",
    "章末钩子缺失",
    "钩子缺失",
    "缺失章末钩子",
    "缺失结尾钩子",
    "缺失撤离过程",
    "缺失任务结算",
    "缺失结算界面",
    "缺失场景",
    "缺失结尾",
    "被截断",
    "截断",
    "戛然而止",
    "未实现",
    "伏笔债务",
    "任务结算",
    "失败名单",
    "未完成场景覆盖",
    "未覆盖完整场景",
    "正文未写到章末",
    "人物动机",
    "动机表达",
    "目标、阻力",
    # v6.8.5: Moved from _SOFT_POLISH_KEYWORDS — these are content-level
    # issues that require author to add content, not polisher to refine.
    "对话比例较低",
    "章末钩子强度不足",
    # v6.10.0: Structural issues that polisher cannot fix — require author
    # to restructure scenes, remove duplicates, or rebalance pacing.
    "重复",
    "堆叠",
    "重叠",
    "功能重叠",
    "信息功能重叠",
    "出现两轮",
    "两轮",
    "多轮",
    "压缩",
    "合并",
    "场景重复",
    "段落重复",
    "描写重复",
    "削弱.*加速感",
    "拖慢.*加速感",
    "挤占",
    "接近失真",
    "失真边缘",
)

_SOFT_POLISH_KEYWORDS = (
    "微瑕",
    "略显",
    "稍显",
    "说明性较强",
    "缺乏动作穿插",
    "可更紧凑",
    "易造成读者误判",
    "仍易造成",
    "可插入",
    "可增加",
    "可增删",
    "感官碎片",
    "感官细节",
    "打破均匀节奏",
    "模拟真实录音卡顿",
    "口语化标记不足",
    # v6.8.5: "对话比例较低" and "章末钩子强度不足" moved to
    # _AUTHOR_STRUCTURAL_KEYWORDS — these are content-level issues that
    # polisher cannot fix (can't add dialogue or create hooks from scratch).
    "[v6.4质量信号]",
    "[质量诊断建议]",
)

_HARD_STRUCTURAL_KEYWORDS = (
    "[CRITICAL]",
    "[DIALOGUE]",
    "[HOOK]",
    "硬阻塞",
    "缺失",
    "截断",
    "戛然而止",
    "未实现",
    "伏笔债务",
    "任务结算",
    "失败名单",
    "逻辑漏洞",
    "硬伤",
)


def classify_issue(issue: str) -> ClassifiedIssue:
    """Classify a single issue string into a category and target.

    Uses keyword matching. Falls back to 'logic' if no keywords match.
    """
    if (
        any(keyword in issue for keyword in _SOFT_POLISH_KEYWORDS)
        and not any(keyword in issue for keyword in _HARD_STRUCTURAL_KEYWORDS)
    ):
        return ClassifiedIssue(
            issue=issue,
            category=IssueCategory.TEXT,
            revision_target="polisher",
        )

    # v6.10.9: Beat 设计层问题 → Screenwriter（优先于 Author 结构性问题判断）
    # "核心循环漂移" 默认路由到 author（beat 有 is_reward_beat 但 Author 没写）
    # 如果 beat 没有 is_reward_beat，Editor LLM 会直接输出 "screenwriter"
    _SCREENWRITER_DESIGN_KEYWORDS = (
        "核心循环设计缺陷", "beat 设计", "场景 beat 设计",
        "爽点标记缺失", "核心循环未标记", "对白槽位缺失",
        "事实锁设计", "角色状态设计", "beat 层",
    )
    _CORE_LOOP_DRIFT_KEYWORDS = (
        "核心循环漂移", "核心循环缺少", "核心循环未检测",
        "核心兑现证据", "reward_used",
    )
    if any(keyword in issue for keyword in _SCREENWRITER_DESIGN_KEYWORDS):
        return ClassifiedIssue(
            issue=issue,
            category=IssueCategory.BEAT_DESIGN,
            revision_target="screenwriter",
        )

    # v6.10.9: "核心循环漂移" 默认路由到 author（Author 没写出爽点兑现）
    # Editor LLM 可以根据 scene_beats 的 is_reward_beat 判断是否升级到 screenwriter
    if any(keyword in issue for keyword in _CORE_LOOP_DRIFT_KEYWORDS):
        return ClassifiedIssue(
            issue=issue,
            category=IssueCategory.PLOT,
            revision_target="author",
        )

    if any(keyword in issue for keyword in _AUTHOR_STRUCTURAL_KEYWORDS):
        # v6.7.9: Title truncation is a surface issue, not a structural
        # author-level problem. Exclude title-related issues from structural
        # author routing.
        if "标题" in issue:
            pass  # fall through to normal keyword matching
        else:
            return ClassifiedIssue(
                issue=issue,
                category=IssueCategory.PLOT,
                revision_target="author",
            )

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

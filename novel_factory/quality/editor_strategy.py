"""Editor Pass/Fail 策略系统化（v6.6.8）

将 Editor 判定拆分为明确的决策类型和策略模型。
审核分是发布/返修主判断，质量诊断只提供修订重点和辅助 priority。

Decision Types:
  - pass: 审核通过，可直接发布
  - advisory_pass: 审核通过但带 advisory（不改 pass_，不触发返修）
  - revision: 需要自动返修
  - human_review: 需要人工介入
  - blocking: 硬阻塞（death penalty / critical issues）
"""

from __future__ import annotations
import json
from typing import Literal
from dataclasses import dataclass, field


EditorDecisionType = Literal["pass", "advisory", "advisory_pass", "revision", "human_review", "blocking"]


@dataclass
class EditorDecision:
    pass_: bool
    revision_needed: bool
    category: EditorDecisionType
    reason: str
    recommended_action: str
    decision_type: EditorDecisionType = ""
    revision_target: str | None = None
    strategy_note: str = ""

    def __post_init__(self):
        if not self.decision_type:
            self.decision_type = self.category


@dataclass
class EditorPolicyInput:
    """All inputs needed for the single policy decision point.

    This is the single source of truth for classify_editor_result().
    No policy-relevant field may be missing.
    """
    score: float
    pass_: bool
    death_penalty: bool = False
    blocking_issue_count: int = 0
    priority_issue_count: int = 0
    advisory_issue_count: int = 0
    quality_priority_count: int = 0
    quality_advisory_count: int = 0
    seam_blocking_count: int = 0
    seam_advisory_count: int = 0
    retry_count: int = 0
    max_retries: int = 3


# ── Hard issue markers ──────────────────────────────────────────────

_HARD_ISSUE_MARKERS = (
    "CRITICAL",
    "死刑红线",
    "硬伤",
    "硬冲突",
    "设定冲突",
    "逻辑漏洞",
    "时间线矛盾",
)

_ADVISORY_MARKERS = (
    "v6.4质量信号",
    "LOW_COLLOQUIAL",
    "STRAIGHT_EMOTION",
    "EXPOSITION_PARAGRAPH",
    "EXPOSITION_PARAGRAPH残留",
    "场景描写较少",
    "冲突强度不足",
    "章末钩子强度不足",
    "章末钩子削弱",
    "人物动机表达不够清晰",
    "字数偏低",
    "质量诊断建议",
    "诊断建议",
    "v6.6策略",
    "章间衔接建议",
)


def _has_hard_issue_text(issues: list[str]) -> bool:
    return any(
        any(marker in str(issue) for marker in _HARD_ISSUE_MARKERS)
        for issue in issues
    )


def _is_advisory_only(issues: list[str]) -> bool:
    """Return True if every issue is advisory-only."""
    return bool(issues) and all(
        any(marker in str(issue) for marker in _ADVISORY_MARKERS)
        for issue in issues
    )


def _normalize_issue_items(issues: list[str] | str | None) -> list[str]:
    """Normalize in-memory issue lists and DB JSON strings for policy counting."""
    if issues is None:
        return []
    parsed = issues
    if isinstance(issues, str):
        text = issues.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = [text]
    if isinstance(parsed, list):
        return [str(item).strip() for item in parsed if str(item).strip()]
    return [str(parsed).strip()] if str(parsed).strip() else []


def count_issue_types(issues: list[str] | str | None) -> tuple[int, int, int]:
    """Count (blocking, priority, advisory) issues by text markers.

    Classification heuristic:
    - blocking: contains hard issue markers (CRITICAL, 死刑红线, etc.)
    - priority: not advisory, not blocking (e.g. 逻辑漏洞 without CRITICAL)
    - advisory: matches advisory markers
    """
    blocking = 0
    priority = 0
    advisory = 0
    for issue in _normalize_issue_items(issues):
        text = str(issue)
        is_blocking = any(m in text for m in _HARD_ISSUE_MARKERS)
        is_advisory = any(m in text for m in _ADVISORY_MARKERS)
        if is_blocking:
            blocking += 1
        elif is_advisory:
            advisory += 1
        else:
            # Issues that are neither blocking markers nor advisory
            # are considered priority (they warrant revision but aren't
            # hard blockers like death penalty).
            priority += 1
    return blocking, priority, advisory


def build_policy_input(
    *,
    score: float,
    pass_: bool,
    issues: list[str],
    has_death_penalty: bool = False,
    has_hard_word_fail: bool = False,
    has_blocking: bool = False,
    quality_priority_count: int = 0,
    quality_advisory_count: int = 0,
    quality_advisory_only: bool = True,
    seam_blocking_count: int = 0,
    seam_advisory_count: int = 0,
    retry_count: int = 0,
    max_retries: int = 3,
) -> EditorPolicyInput:
    """Build EditorPolicyInput from the raw editor state.

    This helper counts issue types and merges all inputs into the
    single policy input dataclass.
    """
    blocking_count, priority_count, advisory_count = count_issue_types(issues)

    # Merge hard gates
    effective_blocking = blocking_count + (1 if has_death_penalty else 0) + (1 if has_hard_word_fail else 0) + (1 if has_blocking else 0) + seam_blocking_count

    return EditorPolicyInput(
        score=score,
        pass_=pass_,
        death_penalty=has_death_penalty or has_hard_word_fail,
        blocking_issue_count=effective_blocking,
        priority_issue_count=priority_count,
        advisory_issue_count=advisory_count,
        quality_priority_count=quality_priority_count,
        quality_advisory_count=quality_advisory_count,
        seam_blocking_count=seam_blocking_count,
        seam_advisory_count=seam_advisory_count,
        retry_count=retry_count,
        max_retries=max_retries,
    )


def classify_editor_result(
    score_or_input=None,
    issues: list[str] | None = None,
    has_blocking: bool = False,
    has_hard_word_fail: bool = False,
    has_death_penalty: bool = False,
    quality_priority_count: int = 0,
    quality_advisory_count: int = 0,
    quality_advisory_only: bool = False,
    seam_blocking_count: int = 0,
    seam_advisory_count: int = 0,
    *,
    score: float | None = None,
) -> EditorDecision:
    """Classify editor result.

    Accepts either:
    - An EditorPolicyInput as first positional arg (new v6.6.8 interface)
    - Legacy keyword arguments: score=..., issues=..., etc.
    - Legacy positional: classify_editor_result(87, issues=[...], ...)

    Rules (v6.6.8):
    1. death_penalty / blocking_issue > 0 -> blocking/revision, never pass
    2. retry_count >= max_retries -> human_review (no more auto revision)
    3. score >= 85 + no blocking -> pass/advisory_pass
    4. score 80-84 + no priority/blocking -> advisory_pass, not auto revision
    5. score 80-84 + priority > 0 -> revision
    6. score < 80 -> revision
    7. quality_advisory_count alone must not cause revision
    8. quality_priority_count can influence 80-84 range
    """
    # Dispatch: if first arg is EditorPolicyInput, use new path
    if isinstance(score_or_input, EditorPolicyInput):
        return _classify_from_policy_input(score_or_input)

    # Legacy interface: score is either positional or keyword
    effective_score = score if score is not None else score_or_input
    if effective_score is None:
        raise TypeError("classify_editor_result() requires either an EditorPolicyInput or a score")

    policy_input = build_policy_input(
        score=float(effective_score),
        pass_=float(effective_score) >= 80,
        issues=issues or [],
        has_death_penalty=has_death_penalty,
        has_hard_word_fail=has_hard_word_fail,
        has_blocking=has_blocking,
        quality_priority_count=quality_priority_count,
        quality_advisory_count=quality_advisory_count,
        quality_advisory_only=quality_advisory_only,
        seam_blocking_count=seam_blocking_count,
        seam_advisory_count=seam_advisory_count,
    )
    return _classify_from_policy_input(policy_input)


def _classify_from_policy_input(p: EditorPolicyInput) -> EditorDecision:
    """Internal: classify from EditorPolicyInput."""
    # Rule 1: Hard blocking
    if p.death_penalty or p.blocking_issue_count > 0:
        return EditorDecision(
            pass_=False,
            revision_needed=True,
            category="blocking",
            reason="存在 blocking issue（death penalty / hard word fail / 硬冲突）",
            recommended_action="必须返修或人工介入",
        )

    # Effective priority = LLM priority + quality priority + seam blocking
    effective_priority = p.priority_issue_count + p.quality_priority_count + p.seam_blocking_count

    # Near-miss plateau guard: after at least one retry, a 78-79 review with
    # no actionable priority/blocking issue should not loop forever. Treat it
    # as publishable with advisory notes; concrete priority issues still route
    # to revision/human_review normally.
    if p.score >= 78 and p.retry_count > 0 and effective_priority == 0:
        return EditorDecision(
            pass_=True,
            revision_needed=False,
            category="advisory",
            decision_type="advisory_pass",
            reason="分数 78-79 且已返修，未发现可执行高优先级问题，转为 advisory pass",
            recommended_action="进入 awaiting_publish with warnings，不再自动返修",
        )

    # Rule 2: Max retries reached
    if p.retry_count >= p.max_retries:
        return EditorDecision(
            pass_=False,
            revision_needed=False,
            category="human_review",
            reason=f"已达最大返修次数 ({p.retry_count}/{p.max_retries})",
            recommended_action="停止自动返修，进入人工审核",
        )

    # Rule 3: score >= 85
    if p.score >= 85:
        has_only_advisory = (
            p.advisory_issue_count + p.quality_advisory_count + p.seam_advisory_count > 0
        )
        if has_only_advisory and effective_priority == 0:
            return EditorDecision(
                pass_=True,
                revision_needed=False,
                category="advisory",
                decision_type="advisory_pass",
                reason="审核分 >= 85，所有问题（含诊断）均为 advisory",
                recommended_action="进入 awaiting_publish with warnings，不自动返修",
            )
        return EditorDecision(
            pass_=True,
            revision_needed=False,
            category="advisory",
            decision_type="advisory_pass",
            reason="分数 >= 85 且无 blocking issues",
            recommended_action="进入 awaiting_publish 或 human_review（带 warning）",
        )

    # Rule 4 & 5: score 80-84
    if p.score >= 80:
        if effective_priority == 0:
            # Advisory only — advisory_pass, NOT auto revision
            return EditorDecision(
                pass_=True,
                revision_needed=False,
                category="advisory",
                decision_type="advisory_pass",
                reason="分数 80-84，advisory issues / quality diagnosis 可接受",
                recommended_action="推荐 human_review 或 awaiting_publish with warnings",
            )
        # Has priority issues -> revision
        return EditorDecision(
            pass_=False,
            revision_needed=True,
            category="revision",
            reason="分数 80-84 但存在高优先级问题，需要返修",
            recommended_action="路由回对应 Agent 返修",
        )

    # Rule 6: score < 80
    return EditorDecision(
        pass_=False,
        revision_needed=True,
        category="revision",
        reason="分数 < 80，需要自动返修",
        recommended_action="路由回对应 Agent 返修",
    )


# ── Backward-compatible wrappers ────────────────────────────────────


def classify_editor_result_legacy(
    score: float,
    issues: list[str],
    has_blocking: bool = False,
    has_hard_word_fail: bool = False,
    has_death_penalty: bool = False,
    quality_priority_count: int = 0,
    quality_advisory_only: bool = False,
) -> EditorDecision:
    """Legacy interface for classify_editor_result (v6.6.0/6.6.1 compat).

    Builds EditorPolicyInput internally and delegates to classify_editor_result.
    """
    policy_input = build_policy_input(
        score=score,
        pass_=score >= 80,
        issues=issues,
        has_death_penalty=has_death_penalty,
        has_hard_word_fail=has_hard_word_fail,
        has_blocking=has_blocking,
        quality_priority_count=quality_priority_count,
        quality_advisory_only=quality_advisory_only,
    )
    return _classify_from_policy_input(policy_input)


def post_process_llm_decision(
    llm_pass: bool,
    score: float,
    issues: list[str],
    *,
    has_blocking: bool = False,
    has_hard_word_fail: bool = False,
    has_death_penalty: bool = False,
    quality_priority_count: int = 0,
    quality_advisory_count: int = 0,
    quality_advisory_only: bool = False,
    seam_blocking_count: int = 0,
    seam_advisory_count: int = 0,
    retry_count: int = 0,
    max_retries: int = 3,
) -> EditorDecision:
    """Post-process LLM's pass/fail decision with deterministic policy.

    Corrects LLM over-harshness (advisory-only flagged as fail)
    and enforces hard blocking rules.
    """
    policy_input = build_policy_input(
        score=score,
        pass_=llm_pass,
        issues=issues,
        has_death_penalty=has_death_penalty,
        has_hard_word_fail=has_hard_word_fail,
        has_blocking=has_blocking,
        quality_priority_count=quality_priority_count,
        quality_advisory_count=quality_advisory_count,
        quality_advisory_only=quality_advisory_only,
        seam_blocking_count=seam_blocking_count,
        seam_advisory_count=seam_advisory_count,
        retry_count=retry_count,
        max_retries=max_retries,
    )
    decision = classify_editor_result(policy_input)

    # LLM says fail, but policy says advisory — override
    if not llm_pass and decision.category == "advisory":
        return EditorDecision(
            pass_=True,
            revision_needed=False,
            category="advisory",
            decision_type="advisory_pass",
            reason="LLM 过度苛刻，已通过后处理纠偏",
            recommended_action="进入 awaiting_publish with warnings",
        )

    return decision


def determine_revision_target(
    *,
    death_penalty: bool = False,
    issues: list[str] | None = None,
    llm_revision_target: str | None = None,
    quality_priority_count: int = 0,
    seam_blocking_count: int = 0,
) -> str:
    """Determine revision target based on issue semantics.

    Rules (v6.6.8):
    - death penalty / continuity / plot logic -> author (or planner for instruction-level)
    - prose/style/advisory polish -> polisher
    - missing scene/content -> author
    - unknown -> polisher (non-empty default)
    - advisory_pass should NOT set revision_target
    - human_review preserves revision_target_hint but doesn't trigger auto revision
    """
    if death_penalty:
        return "author"

    issues = issues or []

    # Check if issues contain planner-level problems
    planner_keywords = ("设定体系冲突", "指令本身错误", "设定冲突")
    for issue in issues:
        if any(kw in str(issue) for kw in planner_keywords):
            return "planner"

    # Check if issues contain author-level problems
    author_keywords = (
        "逻辑漏洞", "剧情", "伏笔", "设定", "info dump", "旁白式", "直白情绪",
        "[CRITICAL]", "[DIALOGUE]", "[HOOK]",
        "LOW_DIALOGUE_RATIO", "对白占比", "对白仅占", "对白过低",
        "缺少角色言行", "角色对话", "动作场景呈现",
        "增加对话", "新增对话", "补充对话",
        "有分歧的对话", "面对面的张力", "冲突强度", "缺乏冲突",
        "章节在核心冲突", "断裂", "没有后续动作", "没有后续决定",
        "没有后续动作/决定/结果", "无法得知", "严重破坏阅读完整性",
        "章末钩子缺失", "钩子缺失", "被截断",
        "人物动机", "动机表达", "目标、阻力",
    )
    for issue in issues:
        if any(kw in str(issue) for kw in author_keywords):
            return "author"

    # Check if issues contain polisher-level problems
    polisher_keywords = ("文风", "句式", "节奏", "AI 痕迹", "对白", "场景质感", "模板句式")
    for issue in issues:
        if any(kw in str(issue) for kw in polisher_keywords):
            return "polisher"

    # Seam blocking issues are continuity -> author
    if seam_blocking_count > 0:
        return "author"

    # Quality priority with no clear category default
    if quality_priority_count > 0:
        return "polisher"

    # LLM-provided target, if valid
    if llm_revision_target in ("author", "polisher", "planner"):
        return llm_revision_target

    # Default: polisher (non-empty, safest for surface issues)
    return "polisher"

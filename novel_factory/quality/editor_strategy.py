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

    v6.9.1: Added skill aggregation fields for multi-skill scoring.
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
    # v6.9.1: Skill aggregation fields
    skill_weighted_score: float = 0.0
    blocking_skill_count: int = 0
    warning_skill_count: int = 0
    skill_scores: dict[str, float] = field(default_factory=dict)
    editor_weights: dict[str, float] = field(default_factory=dict)


# ── Hard issue markers ──────────────────────────────────────────────

_HARD_ISSUE_MARKERS = (
    "CRITICAL",
    "死刑红线",
    "硬伤",
    "硬冲突",
    "设定冲突",
    "逻辑漏洞",
    "时间线矛盾",
    "事实一致性违规",
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

_SOFT_SUGGESTION_MARKERS = (
    "建议",
    "略显",
    "稍显",
    "可通过",
    "可让",
    "可插入",
    "可增加",
    "可增删",
    "避免读者混淆",
    "易被误读",
    "微瑕",
    "说明性较强",
    "缺乏动作穿插",
    "可更紧凑",
    "易造成读者误判",
    "仍易造成",
    "感官碎片",
    "感官细节",
    "打破均匀节奏",
    "模拟真实录音卡顿",
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
        
        # v6.8.2: Recognize Author's scene beat coverage warning as advisory
        if "场景 beat 覆盖不完整" in text and "已降级为警告" in text:
            advisory += 1
            continue
        
        
        is_blocking = any(m in text for m in _HARD_ISSUE_MARKERS)
        is_advisory = any(m in text for m in _ADVISORY_MARKERS)
        is_soft_suggestion = any(m in text for m in _SOFT_SUGGESTION_MARKERS)
        if is_blocking:
            blocking += 1
        elif is_advisory or is_soft_suggestion:
            advisory += 1
        else:
            # Issues that are neither blocking markers nor advisory
            # are considered priority (they warrant revision but aren't
            # hard blockers like death penalty).
            priority += 1
    return blocking, priority, advisory


def aggregate_skill_scores(
    skill_scores: dict[str, float],
    editor_weights: dict[str, float] | None = None,
) -> float:
    """Aggregate skill scores with genre-based weighting.

    v6.9.1: Calculates weighted average of skill scores.

    Args:
        skill_scores: Dict mapping skill_id to score (0-100).
        editor_weights: Optional genre-based weights. If None, all weights are 1.0.

    Returns:
        Weighted average score (0-100).
    """
    if not skill_scores:
        return 0.0

    weights = editor_weights or {}
    total_weighted = 0.0
    total_weight = 0.0

    for skill_id, score in skill_scores.items():
        weight = weights.get(skill_id, 1.0)
        total_weighted += score * weight
        total_weight += weight

    if total_weight == 0:
        return 0.0

    return total_weighted / total_weight


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
    skill_weighted_score: float = 0.0,
    blocking_skill_count: int = 0,
    warning_skill_count: int = 0,
    skill_scores: dict[str, float] | None = None,
    editor_weights: dict[str, float] | None = None,
) -> EditorPolicyInput:
    """Build EditorPolicyInput from the raw editor state.

    This helper counts issue types and merges all inputs into the
    single policy input dataclass.

    v6.9.1: Added skill aggregation parameters.
    """
    blocking_count, priority_count, advisory_count = count_issue_types(issues)

    # Merge hard gates
    effective_blocking = blocking_count + (1 if has_death_penalty else 0) + (1 if has_hard_word_fail else 0) + (1 if has_blocking else 0) + seam_blocking_count + blocking_skill_count

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
        skill_weighted_score=skill_weighted_score,
        blocking_skill_count=blocking_skill_count,
        warning_skill_count=warning_skill_count,
        skill_scores=skill_scores or {},
        editor_weights=editor_weights or {},
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
    """Internal: classify from EditorPolicyInput.

    v6.9.1: Added skill-based scoring rules.
    """
    # Rule 1: Hard blocking (including skill blocking)
    if p.death_penalty or p.blocking_issue_count > 0 or p.blocking_skill_count > 0:
        blocking_reason = []
        if p.death_penalty:
            blocking_reason.append("death penalty")
        if p.blocking_issue_count > 0:
            blocking_reason.append(f"{p.blocking_issue_count} blocking issues")
        if p.blocking_skill_count > 0:
            blocking_reason.append(f"{p.blocking_skill_count} blocking skills")
        return EditorDecision(
            pass_=False,
            revision_needed=True,
            category="blocking",
            reason=f"存在 blocking 问题（{', '.join(blocking_reason)}）",
            recommended_action="必须返修或人工介入",
        )

    # Rule 1.5: Skill weighted score check
    # Use skill_weighted_score if available, otherwise fall back to LLM score
    effective_score = p.skill_weighted_score if p.skill_weighted_score > 0 else p.score

    # Rule 1.6: Low skill weighted score
    if p.skill_weighted_score > 0 and p.skill_weighted_score < 70:
        return EditorDecision(
            pass_=False,
            revision_needed=True,
            category="revision",
            reason=f"skill加权分数 {p.skill_weighted_score:.0f} < 70，需要返修",
            recommended_action="路由回对应 Agent 返修",
        )

    # Effective priority = LLM priority + quality priority + seam blocking
    effective_priority = p.priority_issue_count + p.quality_priority_count + p.seam_blocking_count
    advisory_signal_count = p.advisory_issue_count + p.quality_advisory_count + p.seam_advisory_count + p.warning_skill_count

    # Near-miss plateau guard: after at least one retry, a borderline
    # review with no actionable priority/blocking issue should not loop
    # forever or escalate at the final retry only because the score is
    # still in the 75-79 band.
    # Concrete priority issues still route to revision/human_review normally.
    _near_miss_threshold = 75
    if (
        p.score >= _near_miss_threshold
        and p.retry_count >= 1
        and effective_priority == 0
        and advisory_signal_count > 0
    ):
        return EditorDecision(
            pass_=True,
            revision_needed=False,
            category="advisory",
            decision_type="advisory_pass",
            reason=f"分数 {p.score:.0f} 且已返修 {p.retry_count} 次，未发现可执行高优先级问题，转为 advisory pass",
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

    # Rule 3: score >= 85 (using effective_score which considers skill weighted score)
    if effective_score >= 85:
        if advisory_signal_count > 0 and effective_priority == 0:
            return EditorDecision(
                pass_=True,
                revision_needed=False,
                category="advisory",
                decision_type="advisory_pass",
                reason=f"审核分 {effective_score:.0f} >= 85，所有问题（含诊断）均为 advisory",
                recommended_action="进入 awaiting_publish with warnings，不自动返修",
            )
        return EditorDecision(
            pass_=True,
            revision_needed=False,
            category="advisory",
            decision_type="advisory_pass",
            reason=f"分数 {effective_score:.0f} >= 85 且无 blocking issues",
            recommended_action="进入 awaiting_publish 或 human_review（带 warning）",
        )

    # Rule 4 & 5: score 80-84
    if effective_score >= 80:
        if effective_priority == 0:
            # Advisory only — advisory_pass, NOT auto revision
            return EditorDecision(
                pass_=True,
                revision_needed=False,
                category="advisory",
                decision_type="advisory_pass",
                reason=f"分数 {effective_score:.0f} 80-84，advisory issues / quality diagnosis 可接受",
                recommended_action="推荐 human_review 或 awaiting_publish with warnings",
            )
        # Has priority issues -> revision
        return EditorDecision(
            pass_=False,
            revision_needed=True,
            category="revision",
            reason=f"分数 {effective_score:.0f} 80-84 但存在高优先级问题，需要返修",
            recommended_action="路由回对应 Agent 返修",
        )

    # Rule 6: score < 80
    return EditorDecision(
        pass_=False,
        revision_needed=True,
        category="revision",
        reason=f"分数 {effective_score:.0f} < 80，需要自动返修",
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
    skill_weighted_score: float = 0.0,
    blocking_skill_count: int = 0,
    warning_skill_count: int = 0,
    skill_scores: dict[str, float] | None = None,
    editor_weights: dict[str, float] | None = None,
) -> EditorDecision:
    """Post-process LLM's pass/fail decision with deterministic policy.

    Corrects LLM over-harshness (advisory-only flagged as fail)
    and enforces hard blocking rules.

    v6.9.1: Added skill aggregation parameters.
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
        skill_weighted_score=skill_weighted_score,
        blocking_skill_count=blocking_skill_count,
        warning_skill_count=warning_skill_count,
        skill_scores=skill_scores,
        editor_weights=editor_weights,
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
    retry_count: int = 0,
) -> str:
    """Determine revision target based on issue semantics.

    Rules (v6.8.5):
    - death penalty / continuity / plot logic -> author (or planner for instruction-level)
    - prose/style/advisory polish -> polisher
    - missing scene/content -> author
    - unknown -> polisher (non-empty default)
    - advisory_pass should NOT set revision_target
    - human_review preserves revision_target_hint but doesn't trigger auto revision
    - v6.8.5: after retry_count >= 1, style-oriented issues that were
      previously always routed to author are re-routed to polisher to break
      the author-only doom loop (e.g. low dialogue ratio, exposition).
    """
    if death_penalty:
        return "author"

    issues = issues or []

    # Check if issues contain planner-level problems
    planner_keywords = ("设定体系冲突", "指令本身错误", "设定冲突")
    for issue in issues:
        if any(kw in str(issue) for kw in planner_keywords):
            return "planner"

    # v6.10.9: Check if issues contain beat-design-level problems → screenwriter
    screenwriter_keywords = (
        "核心循环设计缺陷", "beat 设计", "场景 beat 设计",
        "爽点标记缺失", "核心循环未标记", "对白槽位缺失",
        "事实锁设计", "角色状态设计", "character_states",
        "beat 层", "is_reward_beat",
    )
    for issue in issues:
        if any(kw in str(issue) for kw in screenwriter_keywords):
            return "screenwriter"

    # v6.8.5: Style-oriented issues that are partly polisher-addressable.
    # After at least one author retry, route these to polisher instead.
    # On the first attempt (retry_count == 0), keep the original behavior of
    # routing to author so the author gets a chance to fix content first.
    # v6.8.5-fix: 仅保留 Polisher 可修的纯文风问题；对话/冲突/时间逻辑等
    # 内容级别问题始终路由到 Author，不在此列表中
    _style_overlapping_keywords = (
        "info dump", "旁白式", "直白情绪",
    )
    if retry_count >= 1:
        for issue in issues:
            if any(kw in str(issue) for kw in _style_overlapping_keywords):
                return "polisher"

    # Check if issues contain author-level problems
    author_keywords = (
        "逻辑漏洞", "剧情", "伏笔", "设定",
        "事实一致性违规", "事实锁", "不可违背事实",
        "[CRITICAL]", "[DIALOGUE]", "[HOOK]",
        "LOW_DIALOGUE_RATIO", "对白占比", "对白仅占", "对白过低",
        "缺少角色言行", "角色对话", "动作场景呈现",
        "增加对话", "新增对话", "补充对话",
        "有分歧的对话", "面对面的张力", "冲突强度", "缺乏冲突",
        "章节在核心冲突", "断裂", "没有后续动作", "没有后续决定",
        "没有后续动作/决定/结果", "无法得知", "严重破坏阅读完整性",
        "章末钩子缺失", "钩子缺失", "被截断",
        "人物动机", "动机表达", "目标、阻力",
        "info dump", "旁白式", "直白情绪",
        # v6.8.5: 内容缺失问题，Author 增加内容，Polisher 无法修复
        "对话比例较低", "章末钩子强度不足",
        # v6.8.5-fix: 时间逻辑、关键事件、冲突强度是 Author 内容问题
        "时间逻辑", "关键事件", "硬约束冲突", "执行偏差",
        # v6.10.9: 核心循环漂移是 Author 问题（beat 有标记但 Author 没写）
        "核心循环漂移", "核心循环缺少", "核心循环未检测",
        "核心兑现证据", "核心循环兑现不足",
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
    # v6.10.9: "screenwriter" for beat-design-level revision
    if llm_revision_target in ("author", "polisher", "planner", "screenwriter"):
        return llm_revision_target

    # Default: polisher (non-empty, safest for surface issues)
    return "polisher"

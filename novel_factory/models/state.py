"""State models for Novel Factory workflow.

Defines FactoryState (LangGraph global state) and ChapterStatus enum.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional, TypedDict


class ChapterStatus(str, Enum):
    """Chapter status enumeration — v1 only, do NOT add new values."""

    IDEA = "idea"
    OUTLINED = "outlined"
    PLANNED = "planned"
    SCRIPTED = "scripted"
    DRAFTED = "drafted"
    POLISHED = "polished"
    REVIEW = "review"
    REVIEWED = "reviewed"
    REVISION = "revision"
    PUBLISHED = "published"
    BLOCKING = "blocking"

    @classmethod
    def values(cls) -> list[str]:
        return [m.value for m in cls]


# v6.10.8: Canonical status ordering for recovery-run checks.
# Derived from declaration order; each agent should use this instead of
# a local hardcoded _STATUS_ORDER dict.
STATUS_ORDER: dict[str, int] = {m.value: i for i, m in enumerate(ChapterStatus)}


def status_order(status: str) -> int:
    """Return the canonical order index for *status*, or -1 if unknown."""
    return STATUS_ORDER.get(status, -1)


# Legal state transitions
TRANSITIONS: dict[str, list[str]] = {
    ChapterStatus.IDEA.value: [ChapterStatus.OUTLINED.value],
    ChapterStatus.OUTLINED.value: [ChapterStatus.PLANNED.value],
    ChapterStatus.PLANNED.value: [ChapterStatus.SCRIPTED.value],
    ChapterStatus.SCRIPTED.value: [ChapterStatus.DRAFTED.value],
    ChapterStatus.DRAFTED.value: [ChapterStatus.POLISHED.value],
    ChapterStatus.POLISHED.value: [ChapterStatus.REVIEW.value],
    ChapterStatus.REVIEW.value: [
        ChapterStatus.REVIEWED.value,
        ChapterStatus.REVISION.value,
    ],
    ChapterStatus.REVIEWED.value: [ChapterStatus.PUBLISHED.value],
    ChapterStatus.REVISION.value: [
        ChapterStatus.DRAFTED.value,   # rewrite
        ChapterStatus.POLISHED.value,  # polish-only fix
        ChapterStatus.PLANNED.value,   # replan
    ],
    ChapterStatus.BLOCKING.value: [],  # requires human
}


def is_valid_transition(current: str, target: str) -> bool:
    """Check if a state transition is legal."""
    allowed = TRANSITIONS.get(current, [])
    return target in allowed


# v6.8.5: Quality Gate 独立节点结果类型
class QualityGateResult(TypedDict, total=False):
    """确定性质检结果 — quality_gate_node 输出"""

    passed: bool  # 综合判定：通过/失败
    score: float  # 确定性检查综合分 (0-100)
    blocking_issues: list[str]  # 阻塞问题（必须修复）
    priority_issues: list[str]  # 高优先级问题
    advisory_issues: list[str]  # 建议性问题
    diagnostics: dict[str, Any]  # 各检查器详细结果
    checks_run: list[str]  # 已执行的检查列表
    revision_target: str  # 失败时的返修目标 ("author"/"polisher"/"planner")
    timestamp: str  # 检查时间戳


class FactoryState(TypedDict, total=False):
    """LangGraph global state for a chapter production run.

    This is the state object passed between nodes in the workflow graph.
    """

    workflow_run_id: str
    project_id: str
    chapter_number: int
    current_stage: str
    task_id: Optional[str]
    chapter_status: str
    artifact_refs: dict[str, str]
    quality_gate: dict[str, Any]
    messages: list[dict[str, Any]]
    retry_count: int
    max_retries: int
    requires_human: bool
    error: Optional[str]
    # v5.1.6: Runtime context (not persisted, injected by node functions)
    steps: list[dict[str, Any]]  # Step records for run_with_graph return value
    # v5.2: Token usage tracking (accumulated across agents)
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    duration_ms: int
    chapter_token_limit: int
    project_token_limit: int
    project_tokens_before_run: int
    # v5.3.0: Planner 必经 - instruction existence flag for routing
    has_instruction: bool
    # v5.3.0: Trusted Generation Chain - LLM mode for publish routing
    llm_mode: str  # "stub" or "real"
    awaiting_publish: bool
    # v6.6.14: Memory context audit written by planner_node
    memory_context_audit: dict
    # v6.10.x: Review-like revision feedback carried between revision_router and agents.
    _revision_review: dict[str, Any]
    _quality_gate_revision_recorded_for: str

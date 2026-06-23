"""FlowRouter — pure function routing for chapter production workflow.

v6.10.13: Inspired by ainovel-cli's Flow Router design.
Route is a pure function: input State, output Instruction. No IO, no Store calls.
State is constructed from Store by LoadState (non-pure) before calling Route.

Design principles:
- Route is deterministic: same input always produces same output
- Route returns Optional[Instruction]: None means "let LLM decide"
- Priority-based decision tree: match first, skip rest
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


class FlowAction(str, Enum):
    """Possible routing actions."""

    # Rewrite/polish queue
    REWRITE = "rewrite"
    POLISH = "polish"

    # Review processing
    PROCESS_REVIEW = "process_review"

    # Memory updates
    APPLY_MEMORY = "apply_memory"

    # User intervention
    PROCESS_STEER = "process_steer"

    # Arc/volume end processing
    ARC_REVIEW = "arc_review"
    ARC_SUMMARY = "arc_summary"
    VOLUME_SUMMARY = "volume_summary"
    EXPAND_ARC = "expand_arc"
    NEXT_VOLUME = "next_volume"

    # Normal flow
    WRITE_NEXT_CHAPTER = "write_next_chapter"
    CONTINUE_CHAPTER = "continue_chapter"

    # Planning
    PLAN = "plan"

    # Completion
    COMPLETE = "complete"


@dataclass
class Instruction:
    """Routing instruction."""

    action: FlowAction
    chapter: int = 0
    agent: str = ""
    task: str = ""
    reason: str = ""
    data: dict[str, Any] | None = None

    def format_message(self) -> str:
        """Format as message for Coordinator."""
        if self.agent:
            return (
                f"[Host 下达指令] 下一步：调用 subagent({self.agent}, {self.task!r})\n"
                f"理由：{self.reason}\n"
                f"这是流程层的明确指令，请立即执行，不要先调 novel_context。"
            )
        return f"[Host 下达指令] {self.task}\n理由：{self.reason}"


@dataclass
class RouterState:
    """Input state for FlowRouter.route().

    All facts must be explicitly declared here.
    Route is forbidden from reading Store directly.
    """

    # Project phase
    phase: str  # "init" / "genesis" / "writing" / "complete"

    # Current flow state
    flow: str  # "writing" / "reviewing" / "rewriting" / "polishing" / "steering"

    # Chapter info
    current_chapter: int = 0
    total_chapters: int = 0
    completed_chapters: list[int] | None = None

    # Pending queues
    pending_rewrites: list[int] | None = None
    pending_reviews: list[dict[str, Any]] | None = None
    pending_memory_updates: list[dict[str, Any]] | None = None
    pending_steer: str | None = None

    # Chapter status
    chapter_status: str | None = None
    in_progress_chapter: int = 0

    # Layered mode
    layered: bool = False
    current_volume: int = 0
    current_arc: int = 0

    # Arc boundary
    is_arc_end: bool = False
    is_volume_end: bool = False
    has_arc_review: bool = False
    has_arc_summary: bool = False
    has_volume_summary: bool = False
    needs_expansion: bool = False
    next_arc: int = 0
    next_volume: int = 0

    # Foundation
    foundation_missing: list[str] | None = None


def route(state: RouterState) -> Instruction | None:
    """Pure function routing: input State, output Instruction.

    Decision priority (mutual exclusive, match top-down):
    1. Phase=Complete → complete
    2. Phase!=Writing → plan (let LLM decide planner selection)
    3. PendingSteer → process_steer
    4. PendingRewrites → rewrite/polish
    5. PendingReviews → process_review
    6. PendingMemoryUpdates → apply_memory
    7. Flow=Reviewing → None (let LLM handle review result)
    8. Flow=Steering → None (let LLM handle steer)
    9. Arc end processing chain (layered mode)
    10. In-progress chapter → continue_chapter
    11. Normal → write_next_chapter

    Returns None to let LLM make semantic decisions.
    """
    # 1. Complete phase
    if state.phase == "complete":
        return Instruction(
            action=FlowAction.COMPLETE,
            task="创作已完成",
            reason="Phase=Complete",
        )

    # 2. Planning phase
    if state.phase != "writing":
        # Foundation missing → need planning
        if state.foundation_missing:
            return Instruction(
                action=FlowAction.PLAN,
                task=f"补齐基础设定: {', '.join(state.foundation_missing)}",
                reason=f"Phase={state.phase}, 缺少: {', '.join(state.foundation_missing)}",
            )
        return None  # Let LLM decide planner selection

    # 3. Pending steer (user intervention)
    if state.pending_steer:
        return None  # Let LLM handle semantic decision

    # 4. Pending rewrites/polish queue
    if state.pending_rewrites and len(state.pending_rewrites) > 0:
        ch = state.pending_rewrites[0]
        if state.flow == "polishing":
            return Instruction(
                action=FlowAction.POLISH,
                chapter=ch,
                agent="polisher",
                task=f"打磨第 {ch} 章",
                reason=f"PendingRewrites 队列剩余 {len(state.pending_rewrites)} 章",
            )
        else:
            return Instruction(
                action=FlowAction.REWRITE,
                chapter=ch,
                agent="author",
                task=f"重写第 {ch} 章",
                reason=f"PendingRewrites 队列剩余 {len(state.pending_rewrites)} 章",
            )

    # 5. Pending reviews
    if state.pending_reviews and len(state.pending_reviews) > 0:
        review = state.pending_reviews[0]
        return Instruction(
            action=FlowAction.PROCESS_REVIEW,
            chapter=review.get("chapter_number", 0),
            task=f"处理第 {review.get('chapter_number', '?')} 章评审结果",
            reason="有待处理的评审结果",
        )

    # 6. Pending memory updates
    if state.pending_memory_updates and len(state.pending_memory_updates) > 0:
        batch = state.pending_memory_updates[0]
        return Instruction(
            action=FlowAction.APPLY_MEMORY,
            task=f"应用记忆更新批次 {batch.get('id', '?')}",
            reason="有待应用的记忆更新",
        )

    # 7. Reviewing flow
    if state.flow == "reviewing":
        return None  # Let LLM handle review result

    # 8. Steering flow
    if state.flow == "steering":
        return None  # Let LLM handle steer

    # 9. Arc end processing (layered mode)
    if state.layered and state.is_arc_end:
        # 9a. Arc review missing
        if not state.has_arc_review:
            return Instruction(
                action=FlowAction.ARC_REVIEW,
                agent="editor",
                task=f"对第 {state.current_volume} 卷第 {state.current_arc} 弧做弧级评审",
                reason="弧末评审未完成",
            )

        # 9b. Arc summary missing
        if not state.has_arc_summary:
            return Instruction(
                action=FlowAction.ARC_SUMMARY,
                agent="editor",
                task=f"生成第 {state.current_volume} 卷第 {state.current_arc} 弧摘要",
                reason="弧摘要未完成",
            )

        # 9c. Volume summary missing (volume end)
        if state.is_volume_end and not state.has_volume_summary:
            return Instruction(
                action=FlowAction.VOLUME_SUMMARY,
                agent="editor",
                task=f"生成第 {state.current_volume} 卷卷摘要",
                reason="卷摘要未完成",
            )

        # 9d. Next arc needs expansion
        if state.needs_expansion and state.next_arc > 0:
            return Instruction(
                action=FlowAction.EXPAND_ARC,
                agent="architect",
                task=f"展开第 {state.next_volume} 卷第 {state.next_arc} 弧",
                reason="下一弧骨架待展开",
            )

        # 9e. Volume end, need decision
        if state.is_volume_end:
            return Instruction(
                action=FlowAction.NEXT_VOLUME,
                agent="architect",
                task="评估后决定追加新卷或结束全书",
                reason="卷末需决定追加新卷或结束全书",
            )

    # 10. In-progress chapter
    if state.in_progress_chapter > 0:
        return Instruction(
            action=FlowAction.CONTINUE_CHAPTER,
            chapter=state.in_progress_chapter,
            agent="author",
            task=f"继续第 {state.in_progress_chapter} 章",
            reason=f"第 {state.in_progress_chapter} 章进行中",
        )

    # 11. Normal: write next chapter
    next_ch = _next_chapter(state)
    if next_ch > 0:
        return Instruction(
            action=FlowAction.WRITE_NEXT_CHAPTER,
            chapter=next_ch,
            agent="author",
            task=f"写第 {next_ch} 章",
            reason="续写下一章",
        )

    # Fallback: let LLM decide
    return None


def _next_chapter(state: RouterState) -> int:
    """Calculate next chapter number."""
    if state.completed_chapters:
        return max(state.completed_chapters) + 1
    if state.current_chapter > 0:
        return state.current_chapter + 1
    return 1


def describe_resume(state: RouterState) -> str:
    """Generate human-readable resume label for UI.

    This is a pure function for display only, does not affect routing.
    """
    if state.phase == "complete":
        return "创作已完成"

    if state.phase != "writing":
        return f"恢复：规划阶段（{state.phase}）"

    # Pending steer
    if state.pending_steer:
        return "恢复：有待处理的用户干预"

    # Pending rewrites
    if state.pending_rewrites and len(state.pending_rewrites) > 0:
        verb = "打磨" if state.flow == "polishing" else "重写"
        return f"恢复：{verb}{len(state.pending_rewrites)} 章待处理"

    # Reviewing
    if state.flow == "reviewing":
        return "恢复：审阅中断"

    # In progress
    if state.in_progress_chapter > 0:
        return f"恢复：第 {state.in_progress_chapter} 章进行中"

    # Arc end
    if state.layered and state.is_arc_end:
        if not state.has_arc_review:
            return f"恢复：弧末评审待处理（V{state.current_volume} A{state.current_arc}）"
        if not state.has_arc_summary:
            return f"恢复：弧摘要待生成（V{state.current_volume} A{state.current_arc}）"
        if state.is_volume_end and not state.has_volume_summary:
            return f"恢复：卷摘要待生成（V{state.current_volume}）"
        if state.needs_expansion:
            return f"恢复：待展开下一弧（V{state.next_volume} A{state.next_arc}）"
        if state.is_volume_end:
            return f"恢复：待决策下一卷（V{state.current_volume} 末）"

    # Normal resume
    next_ch = _next_chapter(state)
    if next_ch > 0:
        return f"恢复：从第 {next_ch} 章继续"

    return "恢复"

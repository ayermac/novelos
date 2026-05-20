"""Workflow state integrity and recovery state derivation.

v6.6.6: Provides a pure function derive_workflow_recovery_state() that computes
the canonical recovery state from chapter status, run status, and checkpoint state.
This ensures consistent UI actions across RunDetail, ChapterWorkspace, and production-next.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel


# ── Constants ──────────────────────────────────────────────────────

STALE_CHECKPOINT_SECONDS = 7 * 24 * 60 * 60  # 7 days
STALE_RUNNING_RUN_SECONDS = 2 * 60 * 60  # 2 hours

# Terminal chapter statuses that should not be re-processed
TERMINAL_STATUSES = frozenset({"reviewed", "awaiting_publish", "published"})

# Protected statuses for local edit - should not enter main workflow blocking
LOCAL_EDIT_PROTECTED_STATUSES = frozenset({"awaiting_publish", "reviewed", "published"})

# Editable statuses for direct content modification
EDITABLE_STATUSES = frozenset({"drafted", "polished", "revision", "scripted", "blocking"})


# ── Enums ──────────────────────────────────────────────────────────


class RecoveryCapability(str, Enum):
    """Canonical recovery capabilities for workflow state."""

    NO_RECOVERY_NEEDED = "no_recovery_needed"
    PUBLISH_READY = "publish_ready"
    RESUME_FROM_CHECKPOINT = "resume_from_checkpoint"
    CLEAR_CHECKPOINT_AND_RERUN = "clear_checkpoint_and_rerun"
    RESET_TO_PLANNED = "reset_to_planned"
    REOPEN_REVISION = "reopen_revision"
    MANUAL_INTERVENTION_REQUIRED = "manual_intervention_required"


class CheckpointState(str, Enum):
    """Checkpoint state classification."""

    ABSENT = "absent"
    EXISTS = "exists"
    STALE = "stale"
    RESUMABLE = "resumable"


# ── Models ──────────────────────────────────────────────────────────


class WorkflowRecoveryState(BaseModel):
    """Canonical recovery state for a chapter's workflow.

    This model is the single source of truth for UI action buttons
    and production-next recommendations.
    """

    current_stage: str
    is_consistent: bool
    recovery_capability: RecoveryCapability
    recommended_action: Optional[str]
    blocking_reason: Optional[str]
    safe_actions: list[str]
    checkpoint_status: CheckpointState

    # Additional context
    chapter_status: str
    run_status: Optional[str]
    run_id: Optional[str]
    checkpoint_thread_id: Optional[str]
    stale_reason: Optional[str]
    recovery_hint: str


# ── Stale Detection ────────────────────────────────────────────────


def _parse_timestamp(value: Any) -> datetime | None:
    """Parse repository timestamps stored as SQLite datetime strings."""
    if not value:
        return None
    text = str(value).strip().replace("T", " ")
    if text.endswith("Z"):
        text = text[:-1]
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _run_is_recent(
    run_started_at: Any,
    max_age_seconds: float = STALE_RUNNING_RUN_SECONDS,
) -> bool:
    """Check if a running run is still within resumable time window."""
    started_at = _parse_timestamp(run_started_at)
    if started_at is None:
        return True  # Unknown time, assume recent
    # workflow_runs.started_at is stored as local China time via SQLite
    # datetime('now','+8 hours'), so compare against the same clock.
    now_local = datetime.utcnow() + timedelta(hours=8)
    age = now_local - started_at
    return age.total_seconds() <= max_age_seconds


def _checkpoint_is_stale(
    run_status: Optional[str],
    checkpoint_exists: bool,
    checkpoint_node: Optional[str],
    checkpoint_chapter_status: Optional[str],
    current_chapter_status: str,
    current_node: Optional[str],
    checkpoint_age_seconds: Optional[float],
) -> tuple[bool, Optional[str]]:
    """Determine if a checkpoint is stale and should not be used.

    Returns:
        (is_stale, reason)
    """
    if not checkpoint_exists:
        return False, None

    # Rule 1: Run is not running/blocked but checkpoint exists
    # Blocked runs can have valid checkpoints for recovery
    if run_status and run_status not in ("running", "blocked"):
        return True, f"Run status is '{run_status}' but checkpoint exists"

    # Rule 2: Checkpoint node doesn't match current run node.
    #
    # Active LangGraph runs can legitimately have a checkpoint at a routing
    # node (for example "loop") while workflow_runs.current_node has already
    # advanced to the next agent. Treating that transient mismatch as stale
    # creates false "rerun" recommendations while the chapter is still moving.
    # For running runs, staleness is determined by the run age window below.
    if run_status == "blocked" and current_node and checkpoint_node:
        if checkpoint_node != current_node:
            return True, f"Checkpoint node '{checkpoint_node}' doesn't match current node '{current_node}'"

    # Rule 3: Checkpoint node doesn't match expected workflow stage (for non-terminal statuses)
    expected_node_for_status = {
        "planned": "planner",
        "scripted": "screenwriter",
        "drafted": "author",
        "polished": "polisher",
        "review": "editor",
        "reviewed": "publisher",
        "revision": "revision_router",
    }
    expected_node = expected_node_for_status.get(current_chapter_status)
    if (
        run_status != "running"
        and checkpoint_node
        and expected_node
        and checkpoint_node not in (expected_node, "task_discovery", "health_check")
    ):
        # Allow checkpoint at task_discovery/health_check as these are entry nodes
        return True, f"Checkpoint node '{checkpoint_node}' doesn't match expected '{expected_node}'"

    # Rule 4: Checkpoint chapter_status doesn't match current chapter status
    if (
        run_status != "running"
        and checkpoint_chapter_status
        and checkpoint_chapter_status != current_chapter_status
        and checkpoint_chapter_status not in ("planned",)  # Allow planned as starting state
    ):
        return True, f"Checkpoint status '{checkpoint_chapter_status}' doesn't match current '{current_chapter_status}'"

    # Rule 5: Checkpoint age exceeds threshold
    if checkpoint_age_seconds and checkpoint_age_seconds > STALE_CHECKPOINT_SECONDS:
        return True, f"Checkpoint age {checkpoint_age_seconds:.0f}s exceeds threshold {STALE_CHECKPOINT_SECONDS}s"

    return False, None


def _classify_checkpoint_state(
    run_status: Optional[str],
    run_started_at: Any,
    checkpoint_exists: bool,
    checkpoint_node: Optional[str],
    checkpoint_chapter_status: Optional[str],
    current_chapter_status: str,
    current_node: Optional[str],
    checkpoint_age_seconds: Optional[float],
) -> tuple[CheckpointState, Optional[str]]:
    """Classify checkpoint state as absent, exists, stale, or resumable.

    Returns:
        (checkpoint_state, stale_reason)
    """
    if not checkpoint_exists:
        return CheckpointState.ABSENT, None

    # Check if stale
    is_stale, stale_reason = _checkpoint_is_stale(
        run_status,
        checkpoint_exists,
        checkpoint_node,
        checkpoint_chapter_status,
        current_chapter_status,
        current_node,
        checkpoint_age_seconds,
    )
    if is_stale:
        return CheckpointState.STALE, stale_reason

    # Check if running run has exceeded time window (stale running)
    if run_status == "running" and not _run_is_recent(run_started_at):
        return CheckpointState.STALE, "Running run exceeds resumable time window"

    # Check if resumable (running run with recent timestamp)
    if run_status == "running" and _run_is_recent(run_started_at):
        return CheckpointState.RESUMABLE, None

    # Default: exists but not actively resumable
    return CheckpointState.EXISTS, None


# ── Recovery State Derivation ──────────────────────────────────────


def derive_workflow_recovery_state(
    *,
    chapter: dict | None,
    latest_run: dict | None,
    checkpoint_info: dict | None,
    has_existing_content: bool = False,
    is_local_edit: bool = False,
) -> dict[str, Any]:
    """Derive canonical recovery state from chapter, run, and checkpoint.

    This is a pure function with no side effects. All inputs are explicitly
    passed, making it fully testable.

    Args:
        chapter: Chapter dict with status, content, etc.
        latest_run: Latest workflow_run dict with status, current_node, etc.
        checkpoint_info: Checkpoint info from inspect_checkpoint_thread().
        has_existing_content: Whether chapter has existing content (for planned check).
        is_local_edit: Whether this is a local edit context.

    Returns:
        Dict with recovery state including:
        - current_stage: Human-readable stage name
        - is_consistent: Whether chapter/run/checkpoint states are consistent
        - recovery_capability: One of RecoveryCapability values
        - recommended_action: Primary action to recommend
        - blocking_reason: Why the workflow is blocked (if applicable)
        - safe_actions: List of safe action keys for UI buttons
        - checkpoint_status: One of CheckpointState values
        - chapter_status, run_status, run_id: Context
        - checkpoint_thread_id: Checkpoint thread ID if exists
        - stale_reason: Why checkpoint is stale (if applicable)
        - recovery_hint: User-facing explanation
    """
    # Extract inputs
    chapter_status = chapter.get("status", "planned") if chapter else "planned"
    run_status = latest_run.get("status") if latest_run else None
    run_id = latest_run.get("id") or latest_run.get("run_id") if latest_run else None
    run_started_at = latest_run.get("started_at") if latest_run else None
    current_node = latest_run.get("current_node") if latest_run else None

    checkpoint_exists = bool(checkpoint_info.get("checkpoint_exists")) if checkpoint_info else False
    checkpoint_node = checkpoint_info.get("checkpoint_node") if checkpoint_info else None
    checkpoint_chapter_status = None
    if checkpoint_info and "state_keys" in checkpoint_info:
        # Try to extract chapter_status from checkpoint state
        pass  # For now, we don't have this info easily available

    # Classify checkpoint state
    checkpoint_state, stale_reason = _classify_checkpoint_state(
        run_status=run_status,
        run_started_at=run_started_at,
        checkpoint_exists=checkpoint_exists,
        checkpoint_node=checkpoint_node,
        checkpoint_chapter_status=checkpoint_chapter_status,
        current_chapter_status=chapter_status,
        current_node=current_node,
        checkpoint_age_seconds=None,  # Would need additional info
    )

    checkpoint_thread_id = None
    if checkpoint_exists and checkpoint_info:
        # Derive thread ID from project/chapter if needed
        project_id = chapter.get("project_id") if chapter else None
        chapter_number = chapter.get("chapter_number") if chapter else None
        if project_id and chapter_number:
            checkpoint_thread_id = f"{project_id}-chapter-{chapter_number}"

    # Determine recovery capability and safe actions
    recovery_capability, safe_actions, recommended_action, blocking_reason, recovery_hint = (
        _derive_recovery_capability(
            chapter_status=chapter_status,
            run_status=run_status,
            run_id=run_id,
            current_node=current_node,
            checkpoint_state=checkpoint_state,
            checkpoint_exists=checkpoint_exists,
            has_existing_content=has_existing_content,
            is_local_edit=is_local_edit,
            stale_reason=stale_reason,
        )
    )

    # Check consistency
    is_consistent = _check_state_consistency(
        chapter_status=chapter_status,
        run_status=run_status,
        checkpoint_state=checkpoint_state,
        recovery_capability=recovery_capability,
    )

    # Build current stage label
    current_stage = _stage_label(chapter_status, run_status, current_node)

    return {
        "current_stage": current_stage,
        "is_consistent": is_consistent,
        "recovery_capability": recovery_capability.value,
        "recommended_action": recommended_action,
        "blocking_reason": blocking_reason,
        "safe_actions": safe_actions,
        "checkpoint_status": checkpoint_state.value,
        "chapter_status": chapter_status,
        "run_status": run_status,
        "run_id": run_id,
        "checkpoint_thread_id": checkpoint_thread_id,
        "stale_reason": stale_reason,
        "recovery_hint": recovery_hint,
    }


def _derive_recovery_capability(
    chapter_status: str,
    run_status: Optional[str],
    run_id: Optional[str],
    current_node: Optional[str],
    checkpoint_state: CheckpointState,
    checkpoint_exists: bool,
    has_existing_content: bool,
    is_local_edit: bool,
    stale_reason: Optional[str],
) -> tuple[RecoveryCapability, list[str], Optional[str], Optional[str], str]:
    """Determine recovery capability and safe actions.

    Returns:
        (capability, safe_actions, recommended_action, blocking_reason, recovery_hint)
    """
    safe_actions: list[str] = []
    recommended_action: Optional[str] = None
    blocking_reason: Optional[str] = None

    # ── Terminal statuses ────────────────────────────────────────

    if chapter_status in TERMINAL_STATUSES:
        if chapter_status == "published":
            # Already published, no action needed
            safe_actions = ["view_content", "create_revision_draft"]
            return (
                RecoveryCapability.NO_RECOVERY_NEEDED,
                safe_actions,
                None,
                None,
                "章节已发布，可创建修订版。",
            )

        # reviewed or awaiting_publish
        if is_local_edit:
            # Local edit on terminal chapter - don't enter main workflow blocking
            safe_actions = ["view_content", "publish", "local_edit"]
            return (
                RecoveryCapability.PUBLISH_READY,
                safe_actions,
                "publish",
                None,
                "章节审核通过，可发布或继续局部编辑。",
            )

        safe_actions = ["view_content", "publish"]
        return (
            RecoveryCapability.PUBLISH_READY,
            safe_actions,
            "publish",
            None,
            "章节审核通过，可确认发布。",
        )

    # ── Revision status ──────────────────────────────────────────

    if chapter_status == "revision":
        if run_status == "running":
            if checkpoint_state == CheckpointState.RESUMABLE:
                return (
                    RecoveryCapability.NO_RECOVERY_NEEDED,
                    [],
                    None,
                    None,
                    "返修工作流正在运行，请等待当前节点完成。",
                )
            # Stale running run
            safe_actions = ["view_detail", "rerun"]
            return (
                RecoveryCapability.CLEAR_CHECKPOINT_AND_RERUN,
                safe_actions,
                "rerun",
                None,
                "返修运行已过期，建议重新运行。",
                )

        safe_actions = ["view_content", "view_detail", "reopen_revision"]
        return (
            RecoveryCapability.REOPEN_REVISION,
            safe_actions,
            "reopen_revision",
            None,
            "章节处于返修状态，可查看详情或重新开始返修。",
        )

    # ── Blocking status ───────────────────────────────────────────

    if chapter_status == "blocking":
        blocking_reason = "工作流进入阻塞状态，需要人工干预。"
        safe_actions = ["view_content", "view_detail", "reset"]

        if run_status == "running":
            if checkpoint_state == CheckpointState.STALE:
                return (
                    RecoveryCapability.CLEAR_CHECKPOINT_AND_RERUN,
                    safe_actions,
                    "reset",
                    blocking_reason,
                    f"阻塞状态有过期运行。{blocking_reason}",
                )
            safe_actions.append("mark_stuck")
            return (
                RecoveryCapability.MANUAL_INTERVENTION_REQUIRED,
                safe_actions,
                "mark_stuck",
                blocking_reason,
                f"阻塞状态有活跃运行。{blocking_reason}",
            )

        if run_status == "blocked":
            # Blocked run - check if checkpoint is stale
            if checkpoint_state == CheckpointState.STALE:
                return (
                    RecoveryCapability.MANUAL_INTERVENTION_REQUIRED,
                    safe_actions,
                    "reset",
                    blocking_reason,
                    f"阻塞状态检查点不一致。{blocking_reason}",
                )
            # Can reset to planned
            return (
                RecoveryCapability.RESET_TO_PLANNED,
                safe_actions,
                "reset",
                None,
                "工作流被阻塞，可清除阻塞并重置。",
            )

        return (
            RecoveryCapability.MANUAL_INTERVENTION_REQUIRED,
            safe_actions,
            "reset",
            blocking_reason,
            blocking_reason,
        )

    # ── Planned status ────────────────────────────────────────────

    if chapter_status == "planned":
        if has_existing_content:
            # Planned with existing content - don't recommend blank generation
            blocking_reason = "章节已有内容但状态为 planned，建议先查看内容或显式重置。"
            safe_actions = ["view_content", "reset_explicitly", "generate"]
            return (
                RecoveryCapability.MANUAL_INTERVENTION_REQUIRED,
                safe_actions,
                "view_content",
                blocking_reason,
                blocking_reason,
            )

        safe_actions = ["generate"]
        return (
            RecoveryCapability.NO_RECOVERY_NEEDED,
            safe_actions,
            "generate",
            None,
            "章节已规划，可开始生成。",
        )

    # ── Running run handling ──────────────────────────────────────

    if run_status == "running":
        if checkpoint_state == CheckpointState.RESUMABLE:
            return (
                RecoveryCapability.NO_RECOVERY_NEEDED,
                [],
                None,
                None,
                "工作流正在运行，请等待当前节点完成。",
            )

        if checkpoint_state == CheckpointState.STALE:
            safe_actions = ["view_detail", "rerun"]
            return (
                RecoveryCapability.CLEAR_CHECKPOINT_AND_RERUN,
                safe_actions,
                "rerun",
                None,
                f"运行已过期（{stale_reason}），建议重新运行。",
            )

        # Running without checkpoint is observable, but not a user recovery task
        # while the run is still inside the active window.
        return (
            RecoveryCapability.NO_RECOVERY_NEEDED,
            [],
            None,
            None,
            "工作流正在运行，请等待当前节点完成。",
        )

    # ── Failed run ────────────────────────────────────────────────

    if run_status == "failed":
        if checkpoint_exists:
            safe_actions = ["view_detail", "rerun"]
            return (
                RecoveryCapability.CLEAR_CHECKPOINT_AND_RERUN,
                safe_actions,
                "rerun",
                None,
                "工作流失败，建议清理检查点后重新运行。",
            )

        safe_actions = ["view_detail", "generate"]
        return (
            RecoveryCapability.RESET_TO_PLANNED,
            safe_actions,
            "generate",
            None,
            "工作流失败，可重新运行。",
        )

    # ── Blocked run ───────────────────────────────────────────────

    if run_status == "blocked":
        safe_actions = ["view_content", "view_detail", "reset"]
        return (
            RecoveryCapability.RESET_TO_PLANNED,
            safe_actions,
            "reset",
            None,
            "工作流被阻塞，可清除阻塞并重置。",
        )

    # ── Completed run with non-terminal status ────────────────────

    if run_status == "completed":
        # This is the problematic case: completed run but chapter not terminal
        if chapter_status in ("drafted", "polished", "review"):
            # Likely interrupted after node completion
            safe_actions = ["view_content", "generate"]
            return (
                RecoveryCapability.NO_RECOVERY_NEEDED,
                safe_actions,
                "generate",
                None,
                f"章节状态为 {chapter_status}，可继续生成。",
            )

        # Edge case: completed run with unexpected chapter status
        safe_actions = ["view_content", "view_detail"]
        return (
            RecoveryCapability.MANUAL_INTERVENTION_REQUIRED,
            safe_actions,
            "view_detail",
            None,
            f"运行已完成但章节状态为 {chapter_status}，请检查详情。",
        )

    # ── No run (initial state) ────────────────────────────────────

    if run_status is None:
        safe_actions = ["generate"]
        return (
            RecoveryCapability.NO_RECOVERY_NEEDED,
            safe_actions,
            "generate",
            None,
            "章节尚未生成，可开始生成。",
        )

    # ── Default: unknown state ────────────────────────────────────

    safe_actions = ["view_detail"]
    return (
        RecoveryCapability.MANUAL_INTERVENTION_REQUIRED,
        safe_actions,
        "view_detail",
        None,
        f"未知状态：chapter_status={chapter_status}, run_status={run_status}",
    )


def _check_state_consistency(
    chapter_status: str,
    run_status: Optional[str],
    checkpoint_state: CheckpointState,
    recovery_capability: RecoveryCapability,
) -> bool:
    """Check if the derived state is consistent."""
    # Terminal chapter should not have running run
    if chapter_status in TERMINAL_STATUSES and run_status == "running":
        return False

    # Blocking chapter should not have completed run without recovery
    if chapter_status == "blocking" and run_status == "completed":
        return False

    # Resumable checkpoint should only exist with running run
    if checkpoint_state == CheckpointState.RESUMABLE and run_status != "running":
        return False

    # Manual intervention should have blocking reason
    if recovery_capability == RecoveryCapability.MANUAL_INTERVENTION_REQUIRED:
        # This is expected to be inconsistent
        return False

    return True


def _stage_label(
    chapter_status: str,
    run_status: Optional[str],
    current_node: Optional[str],
) -> str:
    """Build human-readable stage label."""
    status_labels = {
        "planned": "已规划",
        "scripted": "已编剧",
        "drafted": "已起草",
        "polished": "已润色",
        "review": "审核中",
        "reviewed": "审核通过",
        "revision": "返修中",
        "blocking": "已阻塞",
        "awaiting_publish": "待发布",
        "published": "已发布",
    }

    base = status_labels.get(chapter_status, chapter_status)

    if run_status == "running":
        node_labels = {
            "planner": "规划",
            "screenwriter": "编剧",
            "author": "执笔",
            "polisher": "润色",
            "editor": "审核",
            "memory_curator": "记忆整理",
            "publisher": "发布",
        }
        node_label = node_labels.get(current_node, current_node or "处理中")
        return f"{base} · {node_label}中"

    if run_status == "failed":
        return f"{base} · 失败"

    if run_status == "blocked":
        return f"{base} · 阻塞"

    return base


# ── Helper for local edit protection ───────────────────────────────


def is_local_edit_state(
    chapter_status: str,
    has_local_edit: bool,
) -> bool:
    """Check if chapter is in local edit state that should not enter main workflow blocking.

    Args:
        chapter_status: Current chapter status.
        has_local_edit: Whether chapter has local edit flag.

    Returns:
        True if this is a protected local edit state.
    """
    return chapter_status in LOCAL_EDIT_PROTECTED_STATUSES and has_local_edit


def should_protect_from_blocking(
    chapter_status: str,
    is_local_edit: bool = False,
) -> bool:
    """Check if chapter should be protected from entering blocking state.

    Used in versions.py to prevent local edits from polluting main workflow state.
    """
    if is_local_edit and chapter_status in LOCAL_EDIT_PROTECTED_STATUSES:
        return True
    return False

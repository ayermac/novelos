"""Conditional edge functions for LangGraph workflow routing."""

from __future__ import annotations

import logging
from typing import Any

from ..models.state import ChapterStatus, FactoryState

logger = logging.getLogger(__name__)

VALID_REVISION_TARGETS = frozenset({"author", "polisher", "planner"})


def normalize_revision_target(value: Any) -> str:
    """Return a safe workflow revision target.

    Editor outputs and historical review rows may be missing, empty, or contain
    non-routable values. Revision is safest when it degrades to Author because
    Author can regenerate the chapter from the existing screenplay.
    """
    return value if value in VALID_REVISION_TARGETS else "author"


def revision_target_from_state(state: FactoryState) -> str:
    """Read revision_target from workflow state with a safe default."""
    gate = state.get("quality_gate", {}) or {}
    return normalize_revision_target(gate.get("revision_target"))


def resolve_revision_target(repo: Any, project_id: str, chapter_number: int) -> str:
    """Recover revision_target from the latest review when state.quality_gate is missing.

    When a workflow starts fresh for a revision chapter, quality_gate may not be
    in state. This helper loads the latest review to determine which Agent should
    handle the revision. Falls back to "author" if no review exists.
    """
    try:
        chapter = repo.get_chapter(project_id, chapter_number)
        if not chapter:
            return "author"
        review = repo.get_latest_review(project_id, chapter["id"])
        if review:
            return normalize_revision_target(review.get("revision_target"))
    except Exception:
        logger.debug("resolve_revision_target failed for %s/%s", project_id, chapter_number)
    return "author"


def get_latest_review_data(repo: Any, project_id: str, chapter_number: int) -> dict | None:
    """Load the latest review record for a chapter. Returns None on failure."""
    try:
        chapter = repo.get_chapter(project_id, chapter_number)
        if not chapter:
            return None
        return repo.get_latest_review(project_id, chapter["id"])
    except Exception:
        return None


def hydrate_revision_state(state: FactoryState, repo: Any) -> FactoryState:
    """Populate revision routing metadata for a fresh revision run.

    Fresh graph runs are built from DB chapter status and may not have the
    editor's quality_gate in memory. This helper restores the latest review's
    revision_target and compact review metadata in one place so streaming and
    non-streaming runners cannot drift.
    """
    if state.get("chapter_status") != ChapterStatus.REVISION.value:
        return state

    project_id = state.get("project_id")
    chapter_number = state.get("chapter_number")
    if not project_id or chapter_number is None:
        return state

    hydrated: FactoryState = dict(state)
    resolved_target = resolve_revision_target(repo, project_id, int(chapter_number))
    if not hydrated.get("quality_gate"):
        hydrated["quality_gate"] = {
            "pass": False,
            "revision_target": resolved_target,
        }
    elif not (hydrated.get("quality_gate") or {}).get("revision_target"):
        hydrated["quality_gate"] = {
            **(hydrated.get("quality_gate") or {}),
            "revision_target": resolved_target,
        }

    review = get_latest_review_data(repo, project_id, int(chapter_number))
    if review and not hydrated.get("_revision_review"):
        hydrated["_revision_review"] = {
            "review_id": review.get("id"),
            "score": review.get("score"),
            "revision_target": normalize_revision_target(review.get("revision_target")),
            "issues": review.get("issues"),
            "suggestions": review.get("suggestions"),
        }

    # v6.8.2: Hydrate retry_count from DB as source of truth. Do this even
    # when state already has a non-zero value because resumed graph state may
    # lag behind task-table retry accounting.
    try:
        retry_count = repo.get_chapter_retry_count(project_id, int(chapter_number))
        hydrated["retry_count"] = retry_count
    except Exception:
        logger.debug(
            "hydrate_revision_state: failed to load retry_count for %s/%s",
            project_id, chapter_number,
            exc_info=True,
        )


    return hydrated


# v6.8.5: Quality Gate 独立节点路由
def route_by_quality_gate(state: FactoryState) -> str:
    """quality_gate 节点后路由：通过则继续 LLM 审校，失败则跳过 LLM 直接返修。

    v6.8.5: 确定性检查失败时跳过 Editor LLM 调用，节省 token 和时间。
    """
    if state.get("requires_human") or state.get("error"):
        return "human_review"

    gate = state.get("quality_gate", {}) or {}
    passed = gate.get("passed", False)

    if passed:
        return "editor"  # 继续 LLM 审校

    # 确定性检查失败，跳过 LLM 审校
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 3)

    if retry_count >= max_retries:
        return "human_review"

    return "revision_router"  # 直接返修


def route_by_chapter_status(state: FactoryState) -> str:
    """Route from task_discovery to the appropriate agent node
    based on chapter_status.

    Priority: if requires_human or error is set, always route to human_review
    to prevent stale state from reaching Agent write nodes.

    v5.3.0: Planner 必经 - planned status without instruction routes to planner.
    POLISHED/REVIEW routes to editor.
    """
    # Safety gate: upstream error or human flag always takes priority
    if state.get("requires_human") or state.get("error"):
        return "human_review"

    status = state.get("chapter_status", "")

    routing = {
        ChapterStatus.IDEA.value: "planner",
        ChapterStatus.OUTLINED.value: "planner",
        ChapterStatus.PLANNED.value: "screenwriter",  # Default, but see v5.3.0 check below
        ChapterStatus.SCRIPTED.value: "author",
        ChapterStatus.DRAFTED.value: "polisher",
        ChapterStatus.POLISHED.value: "editor",
        ChapterStatus.REVIEW.value: "editor",
        ChapterStatus.REVIEWED.value: "publisher",
        ChapterStatus.PUBLISHED.value: "archive",  # Terminal: already published
        ChapterStatus.BLOCKING.value: "human_review",
        ChapterStatus.REVISION.value: "revision_router",
    }

    # v5.3.0: Planner 必经 - if planned status without instruction, route to planner
    if status == ChapterStatus.PLANNED.value:
        has_instruction = state.get("has_instruction", False)
        if not has_instruction:
            return "planner"
        return "screenwriter"

    # For revision, check quality_gate to determine target
    if status == ChapterStatus.REVISION.value:
        target = revision_target_from_state(state)
        if target == "polisher":
            return "polisher"
        elif target == "planner":
            return "planner"
        else:
            return "author"

    return routing.get(status, "planner")


def route_by_review_result(state: FactoryState) -> str:
    """Route after editor review: publish, revise, or human intervention.

    v5.3.0: In real mode, do NOT auto-publish. Route to 'awaiting_publish' instead.
    """
    if state.get("requires_human") or state.get("error"):
        return "human_review"

    if state.get("chapter_status") == ChapterStatus.BLOCKING.value:
        return "human_review"

    gate = state.get("quality_gate", {})
    passed = gate.get("pass", False)

    if passed:
        # v5.3.2: Route to memory_curator for fact extraction after review passes
        return "memory_curator"

    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 3)

    if retry_count >= max_retries:
        return "human_review"

    return "revise"


def route_after_agent(state: FactoryState) -> str:
    """Continue to the next node unless the agent returned an error/human flag."""
    if state.get("requires_human"):
        return "human_review"

    gate = state.get("quality_gate", {}) or {}
    current_status = state.get("chapter_status", "")
    # v6.10.5: Retryable quality gates take priority over the generic error field.
    # This prevents polisher internal retries (low_change_fail, expansion_drift_fail)
    # from being misrouted to human_review when they still have revision budget.
    if (
        gate.get("pass") is False
        and (
            gate.get("word_count_fail")
            or gate.get("death_penalty_fail")
            or gate.get("scene_beat_coverage_fail")
            or gate.get("version_regression")
            or gate.get("low_change_fail")
            or gate.get("expansion_drift_fail")
            or gate.get("fact_lock_fail")
        )
        and current_status not in (
            ChapterStatus.DRAFTED.value,
            ChapterStatus.POLISHED.value,
            ChapterStatus.REVIEWED.value,
        )
    ):
        return "revision_router"

    if state.get("error"):
        return "human_review"

    return "next"


def route_after_memory_curator(state: FactoryState) -> str:
    """Route after memory curator: publish (stub) or awaiting_publish (real).

    v6.2: Memory curator failures still route to human_review by default
    to maintain safety. Future versions may support configurable degradation.
    """
    llm_mode = state.get("llm_mode", "stub")
    if state.get("requires_human") or state.get("error"):
        if (
            llm_mode == "real"
            and state.get("chapter_status") in {
                ChapterStatus.REVIEWED.value,
                "awaiting_publish",
                ChapterStatus.PUBLISHED.value,
            }
            and (
                state.get("memory_curator_degraded")
                or state.get("fallback_created")
                or state.get("extraction_success") is False
            )
        ):
            return "awaiting_publish"
        return "human_review"

    if llm_mode == "real":
        if state.get("memory_curator_locked"):
            return "awaiting_publish"
        if (
            state.get("memory_curator_degraded")
            or state.get("fallback_created")
            or state.get("extraction_success") is False
        ):
            return "awaiting_publish"
        return "awaiting_publish"
    return "publish"


def route_after_brief_validation(state: FactoryState) -> str:
    """Route after brief validation: if Tier 1 fields are missing, go back to planner.
    
    v6.9.0: Brief validation checks Tier 1 fields are present.
    If missing, routes back to planner for revision.
    If valid, proceeds to rhythm budget preflight.
    """
    if state.get("requires_human") or state.get("error"):
        return "human_review"
    
    # Check if brief validation passed
    if state.get("brief_validated"):
        return "rhythm_budget_preflight"
    
    # Check for revision reason
    revision_reason = state.get("revision_reason", "")
    if "missing_tier1_fields" in revision_reason or "missing_chapter_brief" in revision_reason or "missing_planner_output" in revision_reason:
        return "planner"

    # Default: proceed to rhythm budget
    return "rhythm_budget_preflight"


def route_after_rhythm_budget(state: FactoryState) -> str:
    """Route after rhythm budget preflight: if blocking issues, go back to planner.
    
    v6.9.0: Rhythm budget checks pacing and narrative metrics.
    If blocking issues detected, routes back to planner for brief revision.
    If passed, proceeds to screenwriter.
    """
    if state.get("requires_human") or state.get("error"):
        return "human_review"
    
    # Check if rhythm budget passed
    if state.get("rhythm_budget_passed"):
        return "screenwriter"
    
    # Check for rhythm budget blocking
    revision_reason = state.get("revision_reason", "")
    if "rhythm_budget_blocked" in revision_reason:
        return "planner"
    
    # Default: proceed to screenwriter
    return "screenwriter"


def route_by_revision_type(state: FactoryState) -> str:
    """Route revision to the appropriate agent based on revision_target."""
    status = state.get("chapter_status", "")
    if status and status != ChapterStatus.REVISION.value:
        routing_by_status = {
            ChapterStatus.IDEA.value: "planner",
            ChapterStatus.OUTLINED.value: "planner",
            ChapterStatus.PLANNED.value: "planner",
            ChapterStatus.SCRIPTED.value: "author",
            ChapterStatus.DRAFTED.value: "polisher",
            ChapterStatus.POLISHED.value: "editor",
            ChapterStatus.REVIEW.value: "editor",
            ChapterStatus.REVIEWED.value: "publisher",
            ChapterStatus.PUBLISHED.value: "archive",
            ChapterStatus.BLOCKING.value: "human_review",
        }
        return routing_by_status.get(status, "human_review")

    target = revision_target_from_state(state)

    routing = {
        "author": "author",
        "polisher": "polisher",
        "planner": "planner",
    }
    return routing.get(target, "author")


def prepare_resume_after_human_review(state: FactoryState, repo: Any) -> dict:
    """Prepare state for resuming after human review intervention.

    This helper clears stale checkpoints and resets key flags so the
    workflow can be safely re-triggered after manual fixes.
    """
    project_id = state.get("project_id")
    chapter_number = state.get("chapter_number")

    result = {
        "requires_human": False,
        "error": None,
        "current_stage": "resumed",
    }

    if project_id and chapter_number:
        try:
            from .checkpoint import delete_checkpoint_thread
            delete_checkpoint_thread(repo.db_path, project_id, int(chapter_number))
        except Exception:
            pass

    return result

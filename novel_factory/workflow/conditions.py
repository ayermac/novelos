"""Conditional edge functions for LangGraph workflow routing."""

from __future__ import annotations

from ..models.state import ChapterStatus, FactoryState


def route_by_chapter_status(state: FactoryState) -> str:
    """Route from task_discovery to the appropriate agent node
    based on chapter_status.

    Priority: if requires_human or error is set, always route to human_review
    to prevent stale state from reaching Agent write nodes.

    v5.3.0: Planner 必经 - planned status without instruction routes to planner.
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
        gate = state.get("quality_gate", {})
        target = gate.get("revision_target", "author")
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
    gate = state.get("quality_gate", {})
    passed = gate.get("pass", False)

    if passed:
        # v5.3.0: Check llm_mode for auto-publish decision
        llm_mode = state.get("llm_mode", "stub")
        if llm_mode == "real":
            # Real mode: do NOT auto-publish, stop at reviewed status
            return "awaiting_publish"
        # Stub mode: auto-publish is allowed
        return "publish"

    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 3)

    if retry_count >= max_retries:
        return "human_review"

    return "revise"


def route_after_agent(state: FactoryState) -> str:
    """Continue to the next node unless the agent returned an error/human flag."""
    if state.get("requires_human") or state.get("error"):
        return "human_review"
    return "next"


def route_by_revision_type(state: FactoryState) -> str:
    """Route revision to the appropriate agent based on revision_target."""
    gate = state.get("quality_gate", {})
    target = gate.get("revision_target", "author")

    routing = {
        "author": "author",
        "polisher": "polisher",
        "planner": "planner",
    }
    return routing.get(target, "author")

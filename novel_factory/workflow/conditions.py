"""Conditional edge functions for LangGraph workflow routing."""

from __future__ import annotations

from ..models.state import ChapterStatus, FactoryState


def route_by_chapter_status(state: FactoryState) -> str:
    """Route from task_discovery to the appropriate agent node
    based on chapter_status.

    Priority: if requires_human or error is set, always route to human_review
    to prevent stale state from reaching Agent write nodes.
    """
    # Safety gate: upstream error or human flag always takes priority
    if state.get("requires_human") or state.get("error"):
        return "human_review"

    status = state.get("chapter_status", "")

    routing = {
        ChapterStatus.IDEA.value: "planner",
        ChapterStatus.OUTLINED.value: "planner",
        ChapterStatus.PLANNED.value: "screenwriter",
        ChapterStatus.SCRIPTED.value: "author",
        ChapterStatus.DRAFTED.value: "polisher",
        ChapterStatus.POLISHED.value: "editor",
        ChapterStatus.REVIEW.value: "editor",
        ChapterStatus.REVIEWED.value: "publisher",
        ChapterStatus.PUBLISHED.value: "archive",  # Terminal: already published
        ChapterStatus.BLOCKING.value: "human_review",
        ChapterStatus.REVISION.value: "revision_router",
    }

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
    """Route after editor review: publish, revise, or human intervention."""
    gate = state.get("quality_gate", {})
    passed = gate.get("pass", False)

    if passed:
        return "publish"

    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 3)

    if retry_count >= max_retries:
        return "human_review"

    return "revise"


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

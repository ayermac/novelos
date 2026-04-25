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

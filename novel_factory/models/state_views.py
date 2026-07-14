"""State Views — Read-only aggregation views over FactoryState.

v6.11.0 Research Prototype:
Provides convenience views that aggregate FactoryState fields for API responses
and frontend consumption, without modifying the underlying state.

Design goals:
1. Read-only: Views never modify FactoryState
2. Aggregation: Combine multiple fields into convenient structures
3. Type-safe: Use Pydantic for validation
4. Frontend-friendly: Match the shape expected by UI components
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from .state import FactoryState, ChapterStatus, STATUS_ORDER


class TokenUsage(BaseModel):
    """Token usage summary."""
    
    prompt: int = 0
    completion: int = 0
    total: int = 0
    
    @classmethod
    def from_state(cls, state: FactoryState) -> "TokenUsage":
        """Extract token usage from state."""
        prompt = state.get("prompt_tokens", 0) or 0
        completion = state.get("completion_tokens", 0) or 0
        return cls(
            prompt=prompt,
            completion=completion,
            total=prompt + completion,
        )


class QualityGateSummary(BaseModel):
    """Summary of quality gate result."""
    
    passed: bool = False
    score: float = 0.0
    blocking_issues: list[str] = Field(default_factory=list)
    revision_target: str | None = None
    
    @classmethod
    def from_state(cls, state: FactoryState) -> "QualityGateSummary | None":
        """Extract quality gate summary from state."""
        qg = state.get("quality_gate")
        if not qg or not isinstance(qg, dict):
            return None
        
        return cls(
            passed=qg.get("passed", False),
            score=qg.get("score", 0.0),
            blocking_issues=qg.get("blocking_issues", []),
            revision_target=qg.get("revision_target"),
        )


class ChapterProgressView(BaseModel):
    """Chapter progress view — aggregates FactoryState for frontend.
    
    v6.11.0 Research Prototype:
    Provides a convenient, read-only aggregation of FactoryState fields
    that the frontend needs to display chapter progress.
    
    Usage:
        state: FactoryState = get_workflow_state()
        view = ChapterProgressView.from_state(state)
        return view.model_dump()
    """
    
    # Core identifiers
    workflow_run_id: str | None = None
    project_id: str = ""
    chapter_number: int = 0
    
    # Progress tracking
    current_stage: str = ""
    chapter_status: str = ""
    status_order: int = -1
    
    # Content metrics
    word_count: int = 0
    token_usage: TokenUsage = Field(default_factory=TokenUsage)
    
    # Quality
    quality_gate: QualityGateSummary | None = None
    
    # Revision tracking
    revision_count: int = 0
    revision_target: str | None = None
    
    # Error state
    error: str | None = None
    requires_human: bool = False
    
    @classmethod
    def from_state(cls, state: FactoryState) -> "ChapterProgressView":
        """Build a ChapterProgressView from FactoryState.
        
        This is the main factory method. It extracts and aggregates
        fields from the LangGraph state into a frontend-friendly format.
        
        Args:
            state: FactoryState from the workflow
            
        Returns:
            ChapterProgressView instance
        """
        chapter_status = state.get("chapter_status", "")
        
        return cls(
            workflow_run_id=state.get("workflow_run_id"),
            project_id=state.get("project_id", ""),
            chapter_number=state.get("chapter_number", 0),
            current_stage=state.get("current_stage", ""),
            chapter_status=chapter_status,
            status_order=STATUS_ORDER.get(chapter_status, -1),
            word_count=state.get("total_word_count", 0) or 0,
            token_usage=TokenUsage.from_state(state),
            quality_gate=QualityGateSummary.from_state(state),
            revision_count=state.get("retry_count", 0) or 0,
            revision_target=state.get("revision_target"),
            error=state.get("error"),
            requires_human=state.get("requires_human", False),
        )
    
    def is_terminal(self) -> bool:
        """Check if chapter is in a terminal state."""
        return self.chapter_status in (
            ChapterStatus.PUBLISHED.value,
            ChapterStatus.BLOCKING.value,
        )
    
    def is_failed(self) -> bool:
        """Check if chapter has failed."""
        return bool(self.error) or self.requires_human
    
    def progress_percentage(self) -> float:
        """Calculate progress percentage based on status order.
        
        Returns:
            Progress as percentage (0-100)
        """
        # Map status order to percentage
        # 11 total statuses, last is published
        total_stages = len(ChapterStatus)
        if self.status_order < 0:
            return 0.0
        return (self.status_order + 1) / total_stages * 100


class ProjectProgressView(BaseModel):
    """Project-level progress view — aggregates multiple chapters.
    
    v6.11.0 Research Prototype:
    Provides a summary of progress across all chapters in a project.
    """
    
    project_id: str
    total_chapters: int = 0
    completed_chapters: int = 0
    in_progress_chapters: int = 0
    blocked_chapters: int = 0
    total_words: int = 0
    total_tokens: TokenUsage = Field(default_factory=TokenUsage)
    
    @classmethod
    def from_chapter_views(
        cls,
        project_id: str,
        chapter_views: list[ChapterProgressView],
    ) -> "ProjectProgressView":
        """Build a ProjectProgressView from multiple ChapterProgressViews.
        
        Args:
            project_id: Project identifier
            chapter_views: List of chapter progress views
            
        Returns:
            ProjectProgressView instance
        """
        completed = 0
        in_progress = 0
        blocked = 0
        total_words = 0
        total_prompt = 0
        total_completion = 0
        
        for view in chapter_views:
            total_words += view.word_count
            total_prompt += view.token_usage.prompt
            total_completion += view.token_usage.completion
            
            if view.chapter_status == ChapterStatus.PUBLISHED.value:
                completed += 1
            elif view.requires_human or view.chapter_status == ChapterStatus.BLOCKING.value:
                blocked += 1
            elif view.chapter_status:
                in_progress += 1
        
        return cls(
            project_id=project_id,
            total_chapters=len(chapter_views),
            completed_chapters=completed,
            in_progress_chapters=in_progress,
            blocked_chapters=blocked,
            total_words=total_words,
            total_tokens=TokenUsage(
                prompt=total_prompt,
                completion=total_completion,
                total=total_prompt + total_completion,
            ),
        )
    
    def completion_percentage(self) -> float:
        """Calculate project completion percentage."""
        if self.total_chapters == 0:
            return 0.0
        return self.completed_chapters / self.total_chapters * 100


# =============================================================================
# Convenience functions
# =============================================================================

def build_chapter_progress(state: FactoryState) -> dict[str, Any]:
    """Build a chapter progress dict from FactoryState.
    
    This is a convenience function that wraps ChapterProgressView.from_state()
    and returns a dict for JSON serialization.
    
    Args:
        state: FactoryState from the workflow
        
    Returns:
        Dict suitable for JSON response
    """
    view = ChapterProgressView.from_state(state)
    return view.model_dump()

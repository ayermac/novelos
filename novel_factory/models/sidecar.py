"""Sidecar diagnostic data models.

Only ContinuityChecker remains active. Legacy Scout, Secretary, and Architect
agents were retired from the runtime surface.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ── ContinuityChecker Models ───────────────────────────────────────


class ContinuityIssue(BaseModel):
    """A single continuity issue detected."""
    
    issue_type: str = Field(..., description="Type of issue")
    severity: str = Field("warning", description="Issue severity: error, warning, info")
    chapter_range: str = Field(..., description="Affected chapter range")
    description: str = Field(..., description="Issue description")
    recommendation: str | None = Field(None, description="Recommended action")


class ContinuityReport(BaseModel):
    """Cross-chapter continuity check report."""
    
    project_id: str = Field(..., description="Project ID")
    from_chapter: int = Field(..., description="Start chapter")
    to_chapter: int = Field(..., description="End chapter")
    
    issues: list[ContinuityIssue] = Field(default_factory=list, description="Detected issues")
    warnings: list[str] = Field(default_factory=list, description="Warnings")
    
    state_card_consistency: bool = Field(True, description="State card consistency check")
    character_consistency: bool = Field(True, description="Character consistency check")
    plot_consistency: bool = Field(True, description="Plot consistency check")
    
    summary: str = Field(..., description="Overall summary")


class ContinuityCheckerOutput(BaseModel):
    """ContinuityChecker agent output structure."""
    
    report: ContinuityReport
    agent_messages: list[dict[str, Any]] = Field(
        default_factory=list, description="Messages to other agents"
    )


# ── Database Record Models ─────────────────────────────────────────


class SidecarRecord(BaseModel):
    """Base model for sidecar agent database records."""
    
    id: int | None = None
    project_id: str
    chapter_number: int | None = None
    agent_id: str
    report_type: str
    status: str = "completed"
    content_json: dict[str, Any] = Field(default_factory=dict)
    summary: str = ""
    created_at: str | None = None
    updated_at: str | None = None


class ContinuityReportRecord(SidecarRecord):
    """Continuity report database record."""
    agent_id: str = "continuity_checker"

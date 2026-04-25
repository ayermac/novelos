"""Sidecar Agent data models for v2 multi-agent extension.

This module defines Pydantic models for sidecar agents:
- Scout: Market reports and opportunity analysis
- Secretary: Reports and exports
- ContinuityChecker: Cross-chapter consistency checks
- Architect: Architecture and prompt proposals
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ── Scout Agent Models ─────────────────────────────────────────────


class MarketReport(BaseModel):
    """Market observation and trend analysis."""
    
    genre: str = Field(..., description="Target genre")
    platform: str | None = Field(None, description="Target platform")
    audience: str | None = Field(None, description="Target audience")
    
    trends: list[str] = Field(default_factory=list, description="Market trends")
    opportunities: list[str] = Field(default_factory=list, description="Market opportunities")
    reader_preferences: list[str] = Field(default_factory=list, description="Reader preferences")
    competitor_notes: list[str] = Field(default_factory=list, description="Competitor analysis")
    
    summary: str = Field(..., description="Executive summary")
    recommendations: list[str] = Field(default_factory=list, description="Actionable recommendations")


class ScoutOutput(BaseModel):
    """Scout agent output structure."""
    
    market_report: MarketReport
    topic: str | None = Field(None, description="Analyzed topic")
    keywords: list[str] = Field(default_factory=list, description="Market keywords")


# ── Secretary Agent Models ─────────────────────────────────────────


class DailyReport(BaseModel):
    """Daily workflow report."""
    
    date: str = Field(..., description="Report date")
    project_id: str = Field(..., description="Project ID")
    
    total_runs: int = Field(0, description="Total workflow runs")
    successful_runs: int = Field(0, description="Successful runs")
    failed_runs: int = Field(0, description="Failed runs")
    
    chapter_status_distribution: dict[str, int] = Field(
        default_factory=dict, description="Chapter status distribution"
    )
    recent_errors: list[str] = Field(default_factory=list, description="Recent errors")
    
    summary: str = Field(..., description="Daily summary")


class ChapterExport(BaseModel):
    """Chapter export data."""
    
    project_id: str = Field(..., description="Project ID")
    chapter_number: int = Field(..., description="Chapter number")
    title: str = Field(..., description="Chapter title")
    content: str = Field(..., description="Chapter content")
    word_count: int = Field(0, description="Word count")
    
    version_count: int = Field(0, description="Number of versions")
    review_count: int = Field(0, description="Number of reviews")
    latest_score: int | None = Field(None, description="Latest review score")
    
    export_format: str = Field("markdown", description="Export format")
    exported_at: str = Field(..., description="Export timestamp")


class SecretaryOutput(BaseModel):
    """Secretary agent output structure."""
    
    report_type: str = Field(..., description="Type of report")
    report: DailyReport | ChapterExport | dict[str, Any]
    summary: str = Field(..., description="Report summary")


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


# ── Architect Agent Models ─────────────────────────────────────────


class ArchitectureProposal(BaseModel):
    """Architecture or rule improvement proposal."""
    
    proposal_type: str = Field(..., description="Type: architecture, prompt, quality_rule, migration")
    scope: str = Field(..., description="Scope: quality, workflow, agent, system")
    
    title: str = Field(..., description="Proposal title")
    description: str = Field(..., description="Detailed description")
    
    risk_level: str = Field("medium", description="Risk level: low, medium, high")
    affected_area: list[str] = Field(default_factory=list, description="Affected areas")
    recommendation: str = Field(..., description="Recommendation")
    
    rationale: str | None = Field(None, description="Rationale for the proposal")
    implementation_notes: str | None = Field(None, description="Implementation notes")
    
    status: str = Field("pending", description="Proposal status: pending, accepted, rejected")


class ArchitectOutput(BaseModel):
    """Architect agent output structure."""
    
    proposals: list[ArchitectureProposal] = Field(default_factory=list)
    summary: str = Field(..., description="Summary of proposals")
    total_proposals: int = Field(0, description="Total number of proposals")


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


class MarketReportRecord(SidecarRecord):
    """Market report database record."""
    agent_id: str = "scout"


class ReportRecord(SidecarRecord):
    """Report database record."""
    agent_id: str = "secretary"


class ContinuityReportRecord(SidecarRecord):
    """Continuity report database record."""
    agent_id: str = "continuity_checker"


class ArchitectureProposalRecord(SidecarRecord):
    """Architecture proposal database record."""
    agent_id: str = "architect"
    report_type: str = "proposal"

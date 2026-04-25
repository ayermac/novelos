"""Quality-related data models for v1.2.

Defines structured types for death penalty rules, state verification,
plot verification, and revision classification.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ── Death Penalty Rule (Q2) ────────────────────────────────────


class PenaltySeverity(str, Enum):
    """Severity level for death penalty rules."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class PenaltyMatchType(str, Enum):
    """How a death penalty rule matches text."""
    EXACT = "exact"        # exact word match (substring)
    SUBSTRING = "substring"  # broader substring match
    REGEX = "regex"        # regular expression match


class DeathPenaltyRule(BaseModel):
    """A single death penalty rule with structured metadata."""
    code: str
    pattern: str
    match_type: PenaltyMatchType = PenaltyMatchType.EXACT
    severity: PenaltySeverity = PenaltySeverity.CRITICAL
    category: str = "text"  # ai_trace, logic, setting, poison, pacing, text
    description: str = ""
    alternatives: list[str] = Field(default_factory=list)


class DeathPenaltyResult(BaseModel):
    """Result of death penalty check."""
    violations: list[str] = Field(default_factory=list)
    has_critical: bool = False
    details: list[dict[str, Any]] = Field(default_factory=list)


# ── State Verification (Q3) ────────────────────────────────────


class StateViolationType(str, Enum):
    LEVEL_JUMP = "level_jump"
    LOCATION_SHIFT = "location_shift"
    RELATION_REVERSAL = "relation_reversal"


class StateViolation(BaseModel):
    """A single state card violation."""
    type: StateViolationType
    severity: PenaltySeverity
    message: str
    detail: str = ""


class StateVerifyResult(BaseModel):
    """Result of state card consistency check."""
    violations: list[StateViolation] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


# ── Plot Verification (Q4) ─────────────────────────────────────


class PlotVerifyResult(BaseModel):
    """Structured result of plot verification."""
    missing_plants: list[str] = Field(default_factory=list)
    missing_resolves: list[str] = Field(default_factory=list)
    invalid_refs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


# ── Revision Classification (Q7) ──────────────────────────────


class IssueCategory(str, Enum):
    """Category for editor-identified issues."""
    SETTING = "setting"
    LOGIC = "logic"
    POISON = "poison"
    TEXT = "text"
    PACING = "pacing"
    PLOT = "plot"
    STATE = "state"


class ClassifiedIssue(BaseModel):
    """An issue with its category determined by the classifier."""
    issue: str
    category: IssueCategory
    revision_target: str  # "author", "polisher", or "planner"


class RevisionClassifyResult(BaseModel):
    """Result of revision classification."""
    issues: list[ClassifiedIssue] = Field(default_factory=list)
    dominant_target: str = "author"  # most frequent target
    category_counts: dict[str, int] = Field(default_factory=dict)


# ── Fact Lock (Q8) ─────────────────────────────────────────────


class FactLockItem(BaseModel):
    """A single fact to lock before polishing."""
    fact_type: str   # "event", "plot_ref", "state_value", "relation"
    content: str
    source: str = ""


class FactLockResult(BaseModel):
    """Result of fact lock check after polishing."""
    missing_facts: list[FactLockItem] = Field(default_factory=list)
    changed_facts: list[FactLockItem] = Field(default_factory=list)
    risk: str = "none"  # none, low, high

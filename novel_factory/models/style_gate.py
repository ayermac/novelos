"""v4.1 Style Gate & Evolution data models.

Extends v4.0 Style Bible with:
- StyleGateConfig: per-project gate configuration
- StyleBibleVersion: version records for Style Bible changes
- StyleEvolutionProposal: human-approved style adjustments
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ── Enums ──────────────────────────────────────────────────────


class StyleGateMode(str, Enum):
    """Style Gate enforcement mode."""
    OFF = "off"      # No gate, only record
    WARN = "warn"    # Add warnings, don't block
    BLOCK = "block"  # Block on threshold breach


class StyleGateStage(str, Enum):
    """Stage at which Style Gate applies."""
    DRAFT = "draft"
    POLISHED = "polished"
    FINAL_GATE = "final_gate"


class ProposalStatus(str, Enum):
    """Status of a Style Evolution Proposal."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ProposalType(str, Enum):
    """Type of style evolution proposal."""
    ADD_FORBIDDEN_EXPRESSION = "add_forbidden_expression"
    ADJUST_PACING = "adjust_pacing"
    ADD_SENTENCE_RULE = "add_sentence_rule"
    ADD_PARAGRAPH_RULE = "add_paragraph_rule"
    RELAX_RULE = "relax_rule"
    ADD_AI_TRACE_PATTERN = "add_ai_trace_pattern"
    ADD_TONE_KEYWORD = "add_tone_keyword"
    OTHER = "other"


# ── Style Gate Config ──────────────────────────────────────────


class StyleGateConfig(BaseModel):
    """Per-project Style Gate configuration.

    Default mode is 'warn' so existing flows are not disrupted.
    """

    enabled: bool = False
    mode: StyleGateMode = StyleGateMode.WARN
    blocking_threshold: int = 70        # score below this triggers block
    max_blocking_issues: int = 0        # 0 = use blocking_threshold only
    revision_target: str = "polisher"   # author | polisher
    apply_stages: list[StyleGateStage] = Field(
        default_factory=lambda: [StyleGateStage.POLISHED, StyleGateStage.FINAL_GATE]
    )

    def to_storage_dict(self) -> dict[str, Any]:
        """Serialize for JSON storage."""
        data = self.model_dump()
        data["mode"] = self.mode.value
        data["apply_stages"] = [s.value for s in self.apply_stages]
        return data

    @classmethod
    def from_storage_dict(cls, data: dict[str, Any]) -> StyleGateConfig:
        """Deserialize from JSON storage."""
        if isinstance(data.get("mode"), str):
            data["mode"] = StyleGateMode(data["mode"])
        if isinstance(data.get("apply_stages"), list):
            data["apply_stages"] = [
                StyleGateStage(s) if isinstance(s, str) else s
                for s in data["apply_stages"]
            ]
        return cls(**data)


# ── Style Bible Version ────────────────────────────────────────


class StyleBibleVersion(BaseModel):
    """A snapshot of a Style Bible at a point in time."""

    id: str = ""
    project_id: str = ""
    style_bible_id: str = ""
    version: str = "1.0.0"
    bible_json: dict[str, Any] = Field(default_factory=dict)
    change_summary: str = ""
    created_by: str = "system"
    created_at: str = ""


# ── Style Evolution Proposal ───────────────────────────────────


class StyleEvolutionProposal(BaseModel):
    """A proposed change to the Style Bible, pending human review."""

    id: str = ""
    project_id: str = ""
    proposal_type: ProposalType = ProposalType.OTHER
    source: str = "quality_reports"
    status: ProposalStatus = ProposalStatus.PENDING
    proposal_json: dict[str, Any] = Field(default_factory=dict)
    rationale: str = ""
    created_at: str = ""
    decided_at: str = ""
    decision_notes: str = ""


# ── Style Revision Advice ──────────────────────────────────────


class StyleRevisionAdvice(BaseModel):
    """Structured advice for revising a chapter based on style check results."""

    revision_target: str = "polisher"
    priority: str = "medium"  # high | medium | low
    issues: list[str] = Field(default_factory=list)
    rewrite_guidance: str = ""
    forbidden_expression_fixes: list[dict[str, str]] = Field(default_factory=list)
    preferred_expression_suggestions: list[dict[str, str]] = Field(default_factory=list)
    paragraph_suggestions: list[str] = Field(default_factory=list)
    sentence_suggestions: list[str] = Field(default_factory=list)

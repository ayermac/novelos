"""v4.2 Style Sample Analyzer data models.

Provides:
- StyleSampleSource: import source type
- StyleSampleStatus: lifecycle status
- StyleSampleMetrics: extracted statistical features
- StyleSampleRecord: database record model
- StyleSampleProposalInput: input for proposal generation
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ── Enums ──────────────────────────────────────────────────────


class StyleSampleSource(str, Enum):
    """Source type for a style sample."""
    LOCAL_TEXT = "local_text"
    MANUAL = "manual"


class StyleSampleStatus(str, Enum):
    """Lifecycle status of a style sample."""
    IMPORTED = "imported"
    ANALYZED = "analyzed"
    DELETED = "deleted"


# ── Style Sample Metrics ──────────────────────────────────────


class StyleSampleMetrics(BaseModel):
    """Statistical features extracted from a style sample text.

    All ratios are 0.0-1.0. Counts are integers.
    """
    char_count: int = 0
    paragraph_count: int = 0
    sentence_count: int = 0
    avg_sentence_length: float = 0.0
    avg_paragraph_length: float = 0.0
    dialogue_ratio: float = 0.0
    action_ratio: float = 0.0
    description_ratio: float = 0.0
    psychology_ratio: float = 0.0
    punctuation_density: float = 0.0
    short_sentence_ratio: float = 0.0
    long_sentence_ratio: float = 0.0
    ai_trace_risk: str = "unknown"  # low | medium | high | unknown
    tone_keywords: list[str] = Field(default_factory=list)
    rhythm_notes: list[str] = Field(default_factory=list)


# ── Style Sample Record ───────────────────────────────────────


class StyleSampleRecord(BaseModel):
    """Database record for a style sample.

    IMPORTANT: the full source text is never stored.
    Only a preview (<=500 chars), hash, and extracted metrics are kept.
    """
    id: str = ""
    project_id: str = ""
    name: str = ""
    source_type: str = StyleSampleSource.LOCAL_TEXT.value
    content_hash: str = ""
    content_preview: str = ""
    metrics: dict[str, Any] = Field(default_factory=dict)
    analysis: dict[str, Any] = Field(default_factory=dict)
    status: str = StyleSampleStatus.IMPORTED.value
    created_at: str = ""
    analyzed_at: str = ""


# ── Style Sample Proposal Input ───────────────────────────────


class StyleSampleProposalInput(BaseModel):
    """Input for generating style evolution proposals from samples."""
    project_id: str = ""
    sample_ids: list[str] = Field(default_factory=list)
    proposal_strategy: str = "conservative"  # conservative | moderate | aggressive
    notes: str = ""

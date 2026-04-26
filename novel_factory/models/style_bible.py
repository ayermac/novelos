"""Style Bible data models for v4.0.

Defines Pydantic models for project-level style specifications.
All fields have reasonable defaults. No field may reference a specific
living author — only abstract style dimensions.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ── Enums ──────────────────────────────────────────────────────


class Pacing(str, Enum):
    SLOW = "slow"
    BALANCED = "balanced"
    FAST = "fast"


class POV(str, Enum):
    FIRST_PERSON = "first_person"
    THIRD_PERSON_LIMITED = "third_person_limited"
    OMNISCIENT = "omniscient"
    MIXED = "mixed"


class EmotionalIntensity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# ── Sub-models ─────────────────────────────────────────────────


class StyleRule(BaseModel):
    """A single style rule (sentence, paragraph, chapter-level)."""

    description: str = ""
    severity: str = "warning"  # warning | blocking


class ForbiddenExpression(BaseModel):
    """An expression that must not appear in the text."""

    pattern: str
    reason: str = ""
    severity: str = "warning"  # warning | blocking


class PreferredExpression(BaseModel):
    """An expression or style that should appear when possible."""

    pattern: str
    context: str = ""


class AITraceAvoidance(BaseModel):
    """Rules for avoiding AI-sounding writing."""

    avoid_patterns: list[str] = Field(default_factory=list)
    prefer_patterns: list[str] = Field(default_factory=list)
    notes: str = ""


# ── Check results ──────────────────────────────────────────────


class StyleCheckIssue(BaseModel):
    """A single issue found by StyleBibleChecker."""

    rule_type: str  # forbidden_expression | preferred_missing | tone_deviation | rule_violation | ai_trace
    severity: str = "warning"  # warning | blocking
    description: str
    location: str = ""  # approximate text snippet
    suggestion: str = ""


class StyleCheckReport(BaseModel):
    """Complete style check result for a text passage."""

    total_issues: int = 0
    blocking_issues: int = 0
    warning_issues: int = 0
    issues: list[StyleCheckIssue] = Field(default_factory=list)
    score: float = 100.0  # 0-100, 100 = perfect compliance


# ── Main model ─────────────────────────────────────────────────


class StyleBible(BaseModel):
    """Project-level style specification.

    IMPORTANT: No field may reference a specific living author.
    Only abstract style dimensions are allowed.
    """

    project_id: str = ""
    name: str = "Default Style Bible"
    genre: str = ""
    target_platform: str = ""
    target_audience: str = ""

    # Core style dimensions
    tone_keywords: list[str] = Field(default_factory=list)
    pacing: Pacing = Pacing.BALANCED
    pov: POV = POV.THIRD_PERSON_LIMITED
    dialogue_style: str = ""  # e.g., "snappy", "formal", "casual"
    prose_style: str = ""  # e.g., "lean", "descriptive", "lyrical"
    tension_style: str = ""  # e.g., "slow_burn", "constant", "peaks"
    humor_style: str = ""  # e.g., "dry", "slapstick", "none"
    emotional_intensity: EmotionalIntensity = EmotionalIntensity.MEDIUM

    # Expression rules
    forbidden_expressions: list[ForbiddenExpression] = Field(default_factory=list)
    preferred_expressions: list[PreferredExpression] = Field(default_factory=list)

    # Structural rules
    sentence_rules: list[StyleRule] = Field(default_factory=list)
    paragraph_rules: list[StyleRule] = Field(default_factory=list)
    chapter_opening_rules: list[StyleRule] = Field(default_factory=list)
    chapter_ending_rules: list[StyleRule] = Field(default_factory=list)

    # AI trace avoidance
    ai_trace_avoidance: AITraceAvoidance = Field(default_factory=AITraceAvoidance)

    # Metadata
    version: str = "1.0.0"
    created_at: str = ""
    updated_at: str = ""

    def to_storage_dict(self) -> dict[str, Any]:
        """Serialize to a dict suitable for JSON storage in DB."""
        return self.model_dump()

    @classmethod
    def from_storage_dict(cls, data: dict[str, Any]) -> StyleBible:
        """Deserialize from a dict loaded from DB JSON."""
        return cls(**data)

    def summary_for_context(self, token_budget: int = 800) -> str:
        """Generate a concise summary for agent context injection.

        Respects token budget (estimated at 0.5 token/char for Chinese).
        """
        parts: list[str] = []

        # Core dimensions (always included)
        if self.name:
            parts.append(f"风格规范: {self.name}")
        if self.genre:
            parts.append(f"题材: {self.genre}")
        if self.target_platform:
            parts.append(f"平台: {self.target_platform}")
        if self.target_audience:
            parts.append(f"目标读者: {self.target_audience}")
        if self.tone_keywords:
            parts.append(f"基调关键词: {', '.join(self.tone_keywords)}")
        parts.append(f"节奏: {self.pacing.value}")
        parts.append(f"视角: {self.pov.value}")
        if self.dialogue_style:
            parts.append(f"对话风格: {self.dialogue_style}")
        if self.prose_style:
            parts.append(f"行文风格: {self.prose_style}")
        if self.tension_style:
            parts.append(f"张力风格: {self.tension_style}")
        if self.humor_style:
            parts.append(f"幽默风格: {self.humor_style}")
        parts.append(f"情感强度: {self.emotional_intensity.value}")

        # Forbidden expressions (high priority)
        if self.forbidden_expressions:
            blocking = [f for f in self.forbidden_expressions if f.severity == "blocking"]
            if blocking:
                parts.append(f"严禁表达: {', '.join(f.pattern for f in blocking)}")

        # Preferred expressions
        if self.preferred_expressions:
            parts.append(f"推荐表达: {', '.join(p.pattern for p in self.preferred_expressions[:5])}")

        # AI trace avoidance
        if self.ai_trace_avoidance.avoid_patterns:
            parts.append(f"避免AI味: {', '.join(self.ai_trace_avoidance.avoid_patterns[:5])}")

        text = "\n".join(parts)

        # Respect token budget
        max_chars = int(token_budget / 0.5)
        if len(text) > max_chars:
            text = text[: max_chars - 20] + "\n...[已截断]"

        return text

    def rules_for_agent(self, agent_id: str) -> str:
        """Generate agent-specific style rules for context injection.

        Different agents get different subsets of rules.
        """
        parts: list[str] = []

        if agent_id == "planner":
            # Planner needs tone/pacing/structure guidance
            parts.append(f"【风格规范 - 策划摘要】")
            if self.tone_keywords:
                parts.append(f"基调: {', '.join(self.tone_keywords)}")
            parts.append(f"节奏: {self.pacing.value}, 视角: {self.pov.value}")
            if self.chapter_opening_rules:
                for r in self.chapter_opening_rules[:3]:
                    parts.append(f"开篇规则: {r.description}")
            if self.chapter_ending_rules:
                for r in self.chapter_ending_rules[:3]:
                    parts.append(f"结尾规则: {r.description}")

        elif agent_id == "author":
            # Author needs prose/dialogue/tone guidance
            parts.append(f"【风格规范 - 写作指引】")
            if self.prose_style:
                parts.append(f"行文风格: {self.prose_style}")
            if self.dialogue_style:
                parts.append(f"对话风格: {self.dialogue_style}")
            if self.tone_keywords:
                parts.append(f"基调: {', '.join(self.tone_keywords)}")
            if self.preferred_expressions:
                for p in self.preferred_expressions[:5]:
                    ctx = f" ({p.context})" if p.context else ""
                    parts.append(f"推荐表达: {p.pattern}{ctx}")
            if self.sentence_rules:
                for r in self.sentence_rules[:3]:
                    parts.append(f"句式规则: {r.description}")

        elif agent_id in ("polisher", "editor"):
            # Polisher/Editor need forbidden/preferred/ai-trace rules
            parts.append(f"【风格规范 - 审校规则】")
            if self.forbidden_expressions:
                for f in self.forbidden_expressions:
                    parts.append(f"{'[严禁]' if f.severity == 'blocking' else '[禁用]'} {f.pattern}: {f.reason}")
            if self.ai_trace_avoidance.avoid_patterns:
                parts.append(f"避免AI味: {', '.join(self.ai_trace_avoidance.avoid_patterns)}")
            if self.ai_trace_avoidance.prefer_patterns:
                parts.append(f"偏自然表达: {', '.join(self.ai_trace_avoidance.prefer_patterns)}")
            if self.paragraph_rules:
                for r in self.paragraph_rules[:3]:
                    parts.append(f"段落规则: {r.description}")

        else:
            # Default: generic summary
            parts.append(self.summary_for_context(token_budget=400))

        return "\n".join(parts) if parts else ""

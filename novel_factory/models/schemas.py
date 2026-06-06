"""Pydantic schemas for Agent input/output validation.

v1 Agent output contracts per architecture doc section 17.4.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator


# ── Planner output ─────────────────────────────────────────────


class ChapterBrief(BaseModel):
    """Planner output: chapter brief / writing instruction."""

    # Traditional fields (for backward compatibility)
    objective: str = ""
    required_events: list[str] = Field(default_factory=list)
    plots_to_plant: list[str] = Field(default_factory=list)
    plots_to_resolve: list[str] = Field(default_factory=list)
    ending_hook: str = ""
    constraints: list[str] = Field(default_factory=list)
    
    # Tier 1 fields (required)
    chapter_goal: str = ""
    reader_payoff: str = ""
    protagonist_agency: str = ""
    forbidden_moves: list[str] = Field(default_factory=list)
    
    # Tier 2 fields (optional)
    pressure_budget: str = ""
    payoff_budget: str = ""
    upgrade_or_skill_use: str = ""
    character_arc_moves: list[str] = Field(default_factory=list)
    mystery_actions: list[str] = Field(default_factory=list)
    conflict_actions: list[str] = Field(default_factory=list)
    ledger_debts_to_pay: list[str] = Field(default_factory=list)
    new_debts_allowed: bool = True
    scene_count_target: int = 3
    opening_hook: str = ""
    quality_threshold_overrides: dict = Field(default_factory=dict)


class PlannerOutput(BaseModel):
    """Planner structured output."""

    chapter_brief: ChapterBrief

    @model_validator(mode="before")
    @classmethod
    def accept_flat_chapter_brief(cls, data):
        """Accept real LLMs that return the brief fields without a wrapper."""
        if not isinstance(data, dict) or "chapter_brief" in data:
            return data

        brief_keys = {
            "objective",
            "required_events",
            "key_events",
            "plots_to_plant",
            "plots_to_resolve",
            "ending_hook",
            "constraints",
            # Tier 1 fields
            "chapter_goal",
            "reader_payoff",
            "protagonist_agency",
            "forbidden_moves",
            # Tier 2 fields
            "pressure_budget",
            "payoff_budget",
            "upgrade_or_skill_use",
            "character_arc_moves",
            "mystery_actions",
            "conflict_actions",
            "ledger_debts_to_pay",
            "new_debts_allowed",
            "scene_count_target",
            "opening_hook",
            "quality_threshold_overrides",
        }
        if not any(key in data for key in brief_keys):
            return data

        brief = dict(data)
        if "required_events" not in brief and "key_events" in brief:
            brief["required_events"] = brief.pop("key_events")
        return {"chapter_brief": brief}


# ── Screenwriter output ────────────────────────────────────────


class SceneBeat(BaseModel):
    """A single scene beat."""

    sequence: int
    scene_goal: str
    conflict: str = ""
    turn: str = ""
    plot_refs: list[str] = Field(default_factory=list)
    hook: str = ""


class ScreenwriterOutput(BaseModel):
    """Screenwriter structured output."""

    scene_beats: list[SceneBeat]


# ── Author output ──────────────────────────────────────────────


class AuthorOutput(BaseModel):
    """Author structured output."""

    title: str
    content: str
    word_count: int = 0
    implemented_events: list[str] = Field(default_factory=list)
    used_plot_refs: list[str] = Field(default_factory=list)


# ── Title generation output (v6.7.5) ────────────────────────────


class TitleGenerationOutput(BaseModel):
    """v6.7.5: Structured output for chapter title generation."""

    title: str
    reasoning: str = ""


# ── Polisher output ────────────────────────────────────────────


class PolisherOutput(BaseModel):
    """Polisher structured output."""

    content: str
    fact_change_risk: str = "none"
    changed_scope: list[str] = Field(default_factory=list)
    summary: str = ""
    # v6.6.1: Quality diagnosis feedback tracking
    fixed_quality_findings: list[str] = Field(default_factory=list)
    deferred_quality_findings: list[str] = Field(default_factory=list)
    quality_risk_note: str | None = None


# ── Editor output ──────────────────────────────────────────────


class EditorScores(BaseModel):
    """Five-dimension scores from Editor."""

    setting: int = 0
    logic: int = 0
    poison: int = 0
    text: int = 0
    pacing: int = 0


class EditorOutput(BaseModel):
    """Editor structured output."""

    pass_: bool = Field(alias="pass")
    score: int
    scores: EditorScores = Field(default_factory=EditorScores)
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    revision_target: str | None = None
    state_card: dict = Field(default_factory=dict)

    model_config = {"populate_by_name": True}

    @field_validator("issues", "suggestions", mode="before")
    @classmethod
    def normalize_review_text_list(cls, value):
        """Accept real LLMs that return issue objects instead of strings."""
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        if not isinstance(value, list):
            return [str(value)]

        normalized = []
        for item in value:
            if isinstance(item, str):
                normalized.append(item)
                continue
            if isinstance(item, dict):
                parts = []
                for key in ("type", "severity", "title", "message", "detail", "suggestion"):
                    text = item.get(key)
                    if text:
                        parts.append(str(text))
                if parts:
                    normalized.append(": ".join(parts))
                else:
                    normalized.append(str(item))
                continue
            normalized.append(str(item))
        return normalized

    @field_validator("state_card", mode="before")
    @classmethod
    def normalize_state_card(cls, value):
        """Treat LLM null state_card as an empty state card."""
        if value is None:
            return {}
        return value


# ── Autonomous Planning output ─────────────────────────────────


class GeneratedWorldSetting(BaseModel):
    """World setting generated by autonomous planning."""

    category: str
    title: str
    content: str


class GeneratedCharacter(BaseModel):
    """Character generated by autonomous planning."""

    name: str
    role: str = "supporting"
    description: str
    traits: str = ""


class GeneratedOutline(BaseModel):
    """Outline generated by autonomous planning."""

    level: str = "arc"
    sequence: int
    title: str
    content: str
    chapters_range: str = ""


class GeneratedPlotHole(BaseModel):
    """Plot hole / foreshadowing generated by autonomous planning."""

    code: str
    type: str = "伏笔"
    title: str
    description: str
    planted_chapter: int
    planned_resolve_chapter: int
    status: str = "planted"


class GeneratedInstruction(BaseModel):
    """Chapter instruction generated by autonomous planning."""

    chapter_number: int
    objective: str
    key_events: str = ""
    plots_to_plant: list[str] = Field(default_factory=list)
    plots_to_resolve: list[str] = Field(default_factory=list)
    emotion_tone: str = ""
    ending_hook: str = ""
    word_target: int = 3000


class AutoFillLLMOutput(BaseModel):
    """Structured output for auto-fill LLM generation."""

    world_settings: list[GeneratedWorldSetting] = Field(default_factory=list)
    characters: list[GeneratedCharacter] = Field(default_factory=list)
    outlines: list[GeneratedOutline] = Field(default_factory=list)
    plot_holes: list[GeneratedPlotHole] = Field(default_factory=list)
    instructions: list[GeneratedInstruction] = Field(default_factory=list)


class ArcPlanLLMOutput(BaseModel):
    """Structured output for arc-plan LLM generation."""

    outlines: list[GeneratedOutline] = Field(default_factory=list)
    plot_holes: list[GeneratedPlotHole] = Field(default_factory=list)
    instructions: list[GeneratedInstruction] = Field(default_factory=list)

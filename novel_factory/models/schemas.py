"""Pydantic schemas for Agent input/output validation.

v1 Agent output contracts per architecture doc section 17.4.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ── Planner output ─────────────────────────────────────────────


class ChapterBrief(BaseModel):
    """Planner output: chapter brief / writing instruction."""

    objective: str
    required_events: list[str] = Field(default_factory=list)
    plots_to_plant: list[str] = Field(default_factory=list)
    plots_to_resolve: list[str] = Field(default_factory=list)
    ending_hook: str = ""
    constraints: list[str] = Field(default_factory=list)


class PlannerOutput(BaseModel):
    """Planner structured output."""

    chapter_brief: ChapterBrief


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


# ── Polisher output ────────────────────────────────────────────


class PolisherOutput(BaseModel):
    """Polisher structured output."""

    content: str
    fact_change_risk: str = "none"
    changed_scope: list[str] = Field(default_factory=list)
    summary: str = ""


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

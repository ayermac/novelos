"""v6.9.0: Chapter-level contracts for briefs, editor lens reports, and rhythm budget.

These models define the per-chapter contracts that flow through the
workflow: ChapterBrief (Planner → Screenwriter/Author), RhythmBudget
(preflight check), and EditorLensReports (specialized editor lenses).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ── Chapter Brief (Planner output) ──────────────────────────────


class ChapterBriefTier1(BaseModel):
    """Tier 1 — required fields. Missing any of these blocks production."""

    chapter_goal: str = ""
    reader_payoff: str = ""
    protagonist_agency: str = ""
    forbidden_moves: list[str] = Field(default_factory=list)


class ChapterBriefTier2(BaseModel):
    """Tier 2 — best-effort fields. Missing values filled from genre profile defaults."""

    pressure_budget: str = ""
    payoff_budget: str = ""
    upgrade_or_skill_use: str = ""
    character_arc_moves: list[str] = Field(default_factory=list)
    mystery_actions: list[str] = Field(default_factory=list)
    conflict_actions: list[str] = Field(default_factory=list)
    ledger_debts_to_pay: list[str] = Field(default_factory=list)
    new_debts_allowed: list[str] = Field(default_factory=list)
    scene_count_target: int = 0
    opening_hook: str = ""
    ending_hook: str = ""
    quality_threshold_overrides: dict = Field(default_factory=dict)


class ChapterBrief(BaseModel):
    """Full chapter brief contract produced by Planner.

    Tier 1 fields are mandatory (blocking if missing).
    Tier 2 fields are optional (filled with genre defaults if missing).
    """

    tier1: ChapterBriefTier1 = Field(default_factory=ChapterBriefTier1)
    tier2: ChapterBriefTier2 = Field(default_factory=ChapterBriefTier2)


# ── Rhythm Budget Result ────────────────────────────────────────


class RhythmBudgetFlags(BaseModel):
    """Deterministic rhythm budget flags."""

    pressure_streak: int = 0
    passive_protagonist_streak: int = 0
    payoff_gap: int = 0
    visible_upgrade_gap: int = 0
    new_mystery_count: int = 0
    mystery_answer_gap: int = 0


class RhythmBudgetLLMSignals(BaseModel):
    """LLM-assisted rhythm signals (cached after first evaluation)."""

    style_fatigue_score: float = 0.0
    character_tooling_detected: bool = False
    scene_breathing_room_ok: bool = True
    relationship_movement_ok: bool = True


class RhythmBudgetResult(BaseModel):
    """Rhythm budget evaluation result for a chapter.

    Deterministic layer runs first. LLM layer only runs if deterministic passes.
    """

    passed: bool = True
    blocking_reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    flags: RhythmBudgetFlags = Field(default_factory=RhythmBudgetFlags)
    llm_signals: RhythmBudgetLLMSignals = Field(default_factory=RhythmBudgetLLMSignals)




"""v6.9.0: Creative contract models for project launch profiles and genre contracts.

These models define the creative contracts that bind a project to its market lane,
genre expectations, and creative strategy before chapter production begins.
"""

from __future__ import annotations

from typing import TypedDict

from pydantic import BaseModel, Field


# ── Typed sub-shapes for GenreProfile dicts ─────────────────────


class ChapterRhythmDefaults(TypedDict, total=False):
    """Default rhythm pacing parameters loaded from a genre profile YAML."""

    minor_payoff_frequency: int
    visible_upgrade_frequency: int
    public_reversal_frequency: int
    max_consecutive_pressure: int
    max_passive_protagonist: int
    max_payoff_gap: int
    max_visible_upgrade_gap: int


class EditorWeightProfile(TypedDict, total=False):
    """Editor weighting profile for ChiefEditor aggregation."""

    type: int
    commercial: int
    pacing: int
    character: int
    mystery: int
    style: int
    continuity: int
    logic: int


class ProfileSpecificRules(TypedDict, total=False):
    """Genre-specific deterministic rules."""

    must_have_tropes: list[str]
    avoid_patterns: list[str]
    style_constraints: list[str]


# ── Genre Profile (config-driven template) ──────────────────────


class GenreProfile(BaseModel):
    """Genre profile template loaded from YAML configuration.

    Provides default expectations, rhythm constraints, and style patterns
    for a specific genre lane. Does NOT contain project-specific overrides.
    """

    profile_id: str = "generic"
    default_reader_expectations: list[str] = Field(default_factory=list)
    default_payoff_loop: str = ""
    opening_requirements: list[str] = Field(default_factory=list)
    chapter_rhythm_defaults: dict = Field(default_factory=dict)
    common_poison_points: list[str] = Field(default_factory=list)
    style_noise_patterns: list[str] = Field(default_factory=list)
    editor_weight_profile: dict = Field(default_factory=dict)
    profile_specific_rules: dict = Field(default_factory=dict)


# ── Project Launch Profile ──────────────────────────────────────


class ProjectLaunchProfile(BaseModel):
    """Project launch profile generated during Genesis.

    This is the strategic creative contract that defines what kind of novel
    is being created, who it's for, and how it should be positioned.
    Requires user approval before chapter production can begin.
    """

    target_reader: str = ""
    market_lane: str = ""
    genre_family: str = ""
    subgenre: str = ""
    title_promise: str = ""
    core_hook: str = ""
    primary_payoff_loop: str = ""
    secondary_payoff_loops: list[str] = Field(default_factory=list)
    protagonist_growth_engine: str = ""
    commercial_comps: list[str] = Field(default_factory=list)
    first_30_chapter_strategy: str = ""
    hard_do_not_drift_rules: list[str] = Field(default_factory=list)


# ── Genre Contract ──────────────────────────────────────────────


class PayoffCadence(BaseModel):
    """Payoff rhythm constraints."""

    minor_payoff: str = "每章"
    visible_upgrade: str = "每3-5章"
    public_reversal: str = "每5-10章"


class PressureLimits(BaseModel):
    """Pressure and pacing constraints."""

    max_consecutive_heavy: int = 3
    max_passive_protagonist: int = 2


class GenreContract(BaseModel):
    """Genre contract derived from launch profile and genre profile.

    This is the enforceable contract that all agents (Planner, Screenwriter,
    Author, Polisher, Editor) must respect during chapter production.
    """

    genre_id: str = ""
    promise_statement: str = ""
    reader_expectations: list[str] = Field(default_factory=list)
    must_have_beats: list[str] = Field(default_factory=list)
    allowed_dark_lines: list[str] = Field(default_factory=list)
    forbidden_drift: list[str] = Field(default_factory=list)
    payoff_cadence: PayoffCadence = Field(default_factory=PayoffCadence)
    pressure_limits: PressureLimits = Field(default_factory=PressureLimits)
    upgrade_cadence: str = ""
    relationship_cadence: str = ""
    mystery_reveal_cadence: str = ""
    style_constraints: list[str] = Field(default_factory=list)
    editor_weights: dict = Field(default_factory=dict)


# ── v6.10.5: Story Contract Governance ──────────────────────────


class CoreLoopStep(BaseModel):
    """A single step in the project's core payoff loop."""

    id: str
    label: str
    description: str = ""
    payoff_type: str = ""
    required: bool = True


class SupportingMechanism(BaseModel):
    """A supporting narrative mechanism that must serve the core loop."""

    id: str
    label: str
    description: str = ""
    allowed_role: str = "pressure"  # pressure, reveal, tension, mystery
    must_serve_core_loop: bool = True


class DriftRule(BaseModel):
    """A contract rule that detects creative drift."""

    id: str
    description: str
    severity: str = "warning"  # warning, blocking
    window_chapters: int = 1
    threshold: int = 1


class StoryContract(BaseModel):
    """v6.10.5: Structured story contract for core-loop governance.

    Stored as project_creative_contracts.contract_type = "story_contract".
    When absent, a fallback is derived from launch_profile + genre_contract.
    """

    project_id: str = ""
    core_promise: str = ""
    core_loop: list[CoreLoopStep] = Field(default_factory=list)
    supporting_mechanisms: list[SupportingMechanism] = Field(default_factory=list)
    payoff_types: list[str] = Field(default_factory=list)
    drift_rules: list[DriftRule] = Field(default_factory=list)
    cadence: dict[str, int] = Field(default_factory=dict)
    status: str = "draft"  # draft, needs_review, confirmed
    version: str = "1.0.0"

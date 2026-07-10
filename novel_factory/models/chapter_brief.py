"""v6.10.18: Unified ChapterBrief model.

This module defines the new flat ChapterBrief class that replaces the
schemas.py version. The nested chapter_contracts.py version remains
for backward compatibility but is deprecated.
"""

from __future__ import annotations

import warnings
from typing import Any

from pydantic import BaseModel, Field, model_validator


class CoreLoopDesign(BaseModel):
    """v6.10.9: Core loop design constraints.

    Moved from schemas.py for v6.10.18 unification.
    """

    reward_event_index: int = Field(
        default=1, ge=1, le=5,
        description="Specify which key event is the core payoff (1-based)"
    )
    reward_type: str = Field(
        default="ability",
        pattern="^(ability|intellect|emotion|identity|resource)$",
        description="Payoff type"
    )
    reward_evidence: str = Field(
        default="",
        description="Specific payoff evidence description"
    )
    protagonist_decision: str = Field(
        default="",
        description="Key decision or action by protagonist"
    )


class ChapterBrief(BaseModel):
    """v6.10.18: Unified chapter brief (flat, 10-12 target fields).

    This replaces schemas.py:ChapterBrief. The nested chapter_contracts.py
    version is deprecated and will be removed in v6.11.0.
    """

    # === Core 6 fields (required) ===
    chapter_goal: str = Field("", description="Chapter goal")
    conflict: str = Field("", description="Core conflict (NEW v6.10.18)")
    ending_hook: str = Field("", description="Ending hook")
    emotion_tone: str = Field("", description="Emotional tone (NEW v6.10.18)")
    notes: str = Field("", description="Free-form notes (NEW v6.10.18)")

    # === Contract 4 fields (optional) ===
    forbidden_moves: list[str] = Field(default_factory=list, description="Forbidden moves")
    required_beats: list[str] = Field(
        default_factory=list, description="Required beats (NEW v6.10.18)"
    )
    emotion_target: str = Field("", description="Target emotion")
    payoff_points: list[str] = Field(
        default_factory=list, description="Payoff points (NEW v6.10.18)"
    )

    # === v6.10.9 fields (keep) ===
    core_loop: CoreLoopDesign = Field(default_factory=CoreLoopDesign)
    dialogue_target_ratio: float = Field(default=0.15, ge=0.0, le=1.0)
    fact_locks: list[str] = Field(default_factory=list)

    # === Deprecated fields (keep for backward compat) ===
    reader_payoff: str = Field("", deprecated=True)
    protagonist_agency: str = Field("", deprecated=True)
    core_loop_target: str = Field("", deprecated=True)
    primary_payoff: str = Field("", deprecated=True)
    payoff_evidence_plan: str = Field("", deprecated=True)
    pressure_budget: str = Field("", deprecated=True)
    payoff_budget: str = Field("", deprecated=True)
    upgrade_or_skill_use: str = Field("", deprecated=True)
    character_arc_moves: list[str] = Field(default_factory=list, deprecated=True)
    mystery_actions: list[str] = Field(default_factory=list, deprecated=True)
    conflict_actions: list[str] = Field(default_factory=list, deprecated=True)
    ledger_debts_to_pay: list[str] = Field(default_factory=list, deprecated=True)
    new_debts_allowed: list[str] = Field(default_factory=list, deprecated=True)
    scene_count_target: int = Field(default=0, deprecated=True)
    opening_hook: str = Field("", deprecated=True)
    quality_threshold_overrides: dict = Field(default_factory=dict, deprecated=True)
    supporting_mechanisms_used: list[str] = Field(default_factory=list, deprecated=True)
    new_mechanisms_allowed: list[str] = Field(default_factory=list, deprecated=True)
    drift_risks: list[str] = Field(default_factory=list, deprecated=True)
    contract_checklist: list[str] = Field(default_factory=list, deprecated=True)

    # === Legacy fields for schemas.py compat ===
    objective: str = Field("", deprecated=True)
    required_events: list[str] = Field(default_factory=list, deprecated=True)
    plots_to_plant: list[str] = Field(default_factory=list, deprecated=True)
    plots_to_resolve: list[str] = Field(default_factory=list, deprecated=True)
    constraints: list[str] = Field(default_factory=list, deprecated=True)

    @model_validator(mode="after")
    def warn_deprecated_fields(self) -> "ChapterBrief":
        """Warn when deprecated fields are set."""
        deprecated_fields = [
            "reader_payoff",
            "protagonist_agency",
            "core_loop_target",
            "primary_payoff",
            "payoff_evidence_plan",
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
            "supporting_mechanisms_used",
            "new_mechanisms_allowed",
            "drift_risks",
            "contract_checklist",
            "objective",
            "required_events",
            "plots_to_plant",
            "plots_to_resolve",
            "constraints",
        ]
        for field_name in deprecated_fields:
            value = getattr(self, field_name, None)
            if value and (not isinstance(value, (list, dict)) or len(value) > 0):
                warnings.warn(
                    f"ChapterBrief.{field_name} is deprecated and will be removed in v6.11.0. "
                    f"Use new fields (conflict, emotion_tone, notes, payoff_points, required_beats) instead.",
                    DeprecationWarning,
                    stacklevel=3,
                )
        return self

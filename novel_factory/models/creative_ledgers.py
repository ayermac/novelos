"""v6.9.0: Creative ledger models for tracking narrative promises and creative state.

These models track what the novel has promised, what it owes readers, and
the creative state that persists across chapters. Updated by CreativeLedgerCurator
after each chapter passes review.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ── Base Ledger Entry ───────────────────────────────────────────


class LedgerEntry(BaseModel):
    """A single entry in any creative ledger."""

    id: str = ""
    chapter_introduced: int = 0
    chapter_resolved: int = 0
    status: str = "open"  # open, resolved, abandoned
    description: str = ""
    metadata: dict = Field(default_factory=dict)


# ── Reader Promise Ledger ───────────────────────────────────────


class ReaderPromiseLedger(BaseModel):
    """Tracks reader-facing promises: title promise, premise hook, expected payoffs."""

    promises: list[LedgerEntry] = Field(default_factory=list)
    fulfilled: list[LedgerEntry] = Field(default_factory=list)
    broken: list[LedgerEntry] = Field(default_factory=list)


# ── Power Growth Ledger ─────────────────────────────────────────


class PowerGrowthLedger(BaseModel):
    """Tracks protagonist abilities, costs, limitations, upgrades, and recognition."""

    abilities: list[LedgerEntry] = Field(default_factory=list)
    upgrades: list[LedgerEntry] = Field(default_factory=list)
    limitations: list[LedgerEntry] = Field(default_factory=list)
    recognitions: list[LedgerEntry] = Field(default_factory=list)


# ── Character Arc Ledger ────────────────────────────────────────


class CharacterArcEntry(BaseModel):
    """Tracks a character's arc: desire, fear, stakes, relationships, scene function."""

    character_id: str = ""
    character_name: str = ""
    desire: str = ""
    fear: str = ""
    stakes: str = ""
    relationships: list[LedgerEntry] = Field(default_factory=list)
    scene_functions: list[LedgerEntry] = Field(default_factory=list)


class CharacterArcLedger(BaseModel):
    """Tracks arcs for all major characters."""

    characters: list[CharacterArcEntry] = Field(default_factory=list)


# ── Mystery Reveal Ledger ───────────────────────────────────────


class MysteryEntry(BaseModel):
    """Tracks a mystery/foreshadowing element."""

    mystery_id: str = ""
    planted_chapter: int = 0
    status: str = "planted"  # planted, clue_given, partially_revealed, fully_revealed
    description: str = ""
    clues: list[LedgerEntry] = Field(default_factory=list)
    reveal_plan: str = ""
    answer_debt: bool = False


class MysteryRevealLedger(BaseModel):
    """Tracks mysteries, clues, misdirections, and reveal debts."""

    mysteries: list[MysteryEntry] = Field(default_factory=list)


# ── Conflict Ledger ─────────────────────────────────────────────


class ConflictEntry(BaseModel):
    """Tracks an active conflict: antagonist, social pressure, obstacle."""

    conflict_id: str = ""
    conflict_type: str = ""  # antagonist, social, obstacle, internal
    status: str = "active"  # active, escalated, resolved
    description: str = ""
    escalation_history: list[LedgerEntry] = Field(default_factory=list)


class ConflictLedger(BaseModel):
    """Tracks enemies, social pressures, obstacles, and unresolved confrontations."""

    conflicts: list[ConflictEntry] = Field(default_factory=list)


# ── Payoff Ledger ───────────────────────────────────────────────


class PayoffEntry(BaseModel):
    """Tracks a payoff element: humiliation, oath, reward, setup."""

    payoff_id: str = ""
    payoff_type: str = ""  # humiliation, oath, reward, setup
    planted_chapter: int = 0
    delivered_chapter: int = 0
    status: str = "pending"  # pending, delivered
    description: str = ""


class PayoffLedger(BaseModel):
    """Tracks planted payoffs and whether readers have received returns."""

    payoffs: list[PayoffEntry] = Field(default_factory=list)


# ── Style Fatigue Ledger ────────────────────────────────────────


class StyleFatigueEntry(BaseModel):
    """Tracks a style fatigue pattern: repeated imagery, high-frequency words, tension patterns."""

    pattern_type: str = ""  # imagery, word, tension, template
    pattern_value: str = ""
    occurrences: int = 0
    first_seen_chapter: int = 0
    last_seen_chapter: int = 0


class StyleFatigueLedger(BaseModel):
    """Tracks repeated imagery, high-frequency words, tension patterns, and scene texture fatigue."""

    patterns: list[StyleFatigueEntry] = Field(default_factory=list)


# ── v6.10.5: Chapter Contract Metrics ────────────────────────────


class ChapterContractMetrics(BaseModel):
    """v6.10.5: Per-chapter Story Contract compliance metrics.

    Recorded after each chapter passes review or is published.
    Used for trend checking, drift detection, and Run Doctor diagnostics.
    """

    chapter_number: int = 0
    core_payoff_present: bool = False
    payoff_type: str = ""
    core_loop_steps_completed: list[str] = Field(default_factory=list)
    supporting_mechanisms_used: list[str] = Field(default_factory=list)
    dominant_mechanism: str = ""
    new_mechanisms_introduced: list[str] = Field(default_factory=list)
    protagonist_agency: bool = True
    contract_drift_warnings: list[str] = Field(default_factory=list)
    contract_score: float = 0.0

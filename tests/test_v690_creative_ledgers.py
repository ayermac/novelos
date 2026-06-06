"""v6.9.0: Creative Ledgers model and curator tests.

Covers:
- All 7 ledger models: ReaderPromise, PowerGrowth, CharacterArc,
  MysteryReveal, Conflict, Payoff, StyleFatigue
- CreativeLedgerCurator._compute_patch
- LedgerEntry model
- CharacterArcEntry model
"""

from __future__ import annotations

import pytest

from novel_factory.models.creative_ledgers import (
    LedgerEntry,
    ReaderPromiseLedger,
    PowerGrowthLedger,
    CharacterArcEntry,
    CharacterArcLedger,
    MysteryEntry,
    MysteryRevealLedger,
    ConflictEntry,
    ConflictLedger,
    PayoffEntry,
    PayoffLedger,
    StyleFatigueEntry,
    StyleFatigueLedger,
)
from novel_factory.agents.creative_ledger_curator import CreativeLedgerCurator


class TestLedgerEntry:
    def test_model_creation(self):
        entry = LedgerEntry(
            id="e1", chapter_introduced=1, chapter_resolved=0,
            status="open", description="test entry",
        )
        assert entry.id == "e1"
        assert entry.status == "open"

    def test_default_values(self):
        entry = LedgerEntry()
        assert entry.id == ""
        assert entry.status == "open"
        assert entry.metadata == {}

    def test_serialization(self):
        entry = LedgerEntry(id="e1", description="test")
        data = entry.model_dump()
        assert data["id"] == "e1"
        restored = LedgerEntry(**data)
        assert restored.id == "e1"


class TestReaderPromiseLedger:
    def test_model_creation(self):
        ledger = ReaderPromiseLedger(
            promises=[LedgerEntry(id="p1", description="title promise")],
            fulfilled=[LedgerEntry(id="f1", status="resolved")],
        )
        assert len(ledger.promises) == 1
        assert len(ledger.fulfilled) == 1
        assert len(ledger.broken) == 0

    def test_default_values(self):
        ledger = ReaderPromiseLedger()
        assert ledger.promises == []
        assert ledger.fulfilled == []
        assert ledger.broken == []


class TestPowerGrowthLedger:
    def test_model_creation(self):
        ledger = PowerGrowthLedger(
            abilities=[LedgerEntry(id="a1", description="灵力觉醒")],
            upgrades=[LedgerEntry(id="u1", description="突破二层")],
        )
        assert len(ledger.abilities) == 1
        assert len(ledger.upgrades) == 1

    def test_all_fields(self):
        ledger = PowerGrowthLedger()
        assert hasattr(ledger, "abilities")
        assert hasattr(ledger, "upgrades")
        assert hasattr(ledger, "limitations")
        assert hasattr(ledger, "recognitions")


class TestCharacterArcLedger:
    def test_model_creation(self):
        arc = CharacterArcEntry(
            character_id="c1", character_name="林默",
            desire="寻找真相", fear="失去亲人",
            stakes="生死存亡",
        )
        ledger = CharacterArcLedger(characters=[arc])
        assert len(ledger.characters) == 1
        assert ledger.characters[0].character_name == "林默"

    def test_default_values(self):
        arc = CharacterArcEntry()
        assert arc.character_id == ""
        assert arc.relationships == []
        assert arc.scene_functions == []


class TestMysteryRevealLedger:
    def test_model_creation(self):
        mystery = MysteryEntry(
            mystery_id="m1", planted_chapter=1,
            status="planted", description="灵力来源之谜",
        )
        ledger = MysteryRevealLedger(mysteries=[mystery])
        assert len(ledger.mysteries) == 1
        assert ledger.mysteries[0].status == "planted"

    def test_mystery_statuses(self):
        for status in ["planted", "clue_given", "partially_revealed", "fully_revealed"]:
            m = MysteryEntry(status=status)
            assert m.status == status


class TestConflictLedger:
    def test_model_creation(self):
        conflict = ConflictEntry(
            conflict_id="c1", conflict_type="antagonist",
            status="active", description="与暗影组织的对抗",
        )
        ledger = ConflictLedger(conflicts=[conflict])
        assert len(ledger.conflicts) == 1

    def test_conflict_types(self):
        for ctype in ["antagonist", "social", "obstacle", "internal"]:
            c = ConflictEntry(conflict_type=ctype)
            assert c.conflict_type == ctype


class TestPayoffLedger:
    def test_model_creation(self):
        payoff = PayoffEntry(
            payoff_id="p1", payoff_type="humiliation",
            planted_chapter=1, status="pending",
        )
        ledger = PayoffLedger(payoffs=[payoff])
        assert len(ledger.payoffs) == 1
        assert ledger.payoffs[0].status == "pending"

    def test_payoff_types(self):
        for ptype in ["humiliation", "oath", "reward", "setup"]:
            p = PayoffEntry(payoff_type=ptype)
            assert p.payoff_type == ptype


class TestStyleFatigueLedger:
    def test_model_creation(self):
        entry = StyleFatigueEntry(
            pattern_type="imagery", pattern_value="寒光",
            occurrences=5, first_seen_chapter=1, last_seen_chapter=5,
        )
        ledger = StyleFatigueLedger(patterns=[entry])
        assert len(ledger.patterns) == 1
        assert ledger.patterns[0].occurrences == 5

    def test_pattern_types(self):
        for ptype in ["imagery", "word", "tension", "template"]:
            e = StyleFatigueEntry(pattern_type=ptype)
            assert e.pattern_type == ptype


class TestComputePatch:
    def test_empty_to_entries(self):
        patch = CreativeLedgerCurator._compute_patch(
            {}, {"entries": [{"id": "e1", "val": 1}]}
        )
        assert len(patch["added"]) == 1

    def test_no_changes(self):
        data = {"entries": [{"id": "e1", "val": 1}]}
        patch = CreativeLedgerCurator._compute_patch(data, data)
        assert len(patch["added"]) == 0
        assert len(patch["modified"]) == 0

    def test_modified_entry(self):
        prev = {"entries": [{"id": "e1", "val": 1}]}
        new = {"entries": [{"id": "e1", "val": 2}]}
        patch = CreativeLedgerCurator._compute_patch(prev, new)
        assert len(patch["modified"]) == 1

    def test_added_and_removed(self):
        prev = {"entries": [{"id": "e1"}]}
        new = {"entries": [{"id": "e1"}, {"id": "e2"}]}
        patch = CreativeLedgerCurator._compute_patch(prev, new)
        assert len(patch["added"]) == 1
        assert patch["added"][0]["id"] == "e2"


class TestCreativeLedgerCuratorInit:
    def test_ledger_types(self):
        """CreativeLedgerCurator should track 7 ledger types."""
        # We can't fully instantiate without repo/llm, but check class attribute
        class MockRepo:
            pass
        curator = CreativeLedgerCurator(MockRepo(), None)
        assert len(curator.ledger_types) == 7
        assert "reader_promise" in curator.ledger_types
        assert "power_growth" in curator.ledger_types
        assert "character_arc" in curator.ledger_types
        assert "mystery_reveal" in curator.ledger_types
        assert "conflict" in curator.ledger_types
        assert "payoff" in curator.ledger_types
        assert "style_fatigue" in curator.ledger_types

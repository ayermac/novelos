"""v6.9.0: Rhythm Budget deterministic tests.

Covers:
- 6 deterministic detection functions
- 4 default blocking rules
- Warning conditions
- Genre-specific rules (cultivation, mystery, romance)
- evaluate_deterministic integration
- Threshold overrides
"""

from __future__ import annotations

import pytest

from novel_factory.quality.rhythm_budget import (
    detect_pressure_streak,
    detect_passive_protagonist_streak,
    detect_payoff_gap,
    detect_visible_upgrade_gap,
    count_new_mysteries,
    detect_mystery_answer_gap,
    evaluate_deterministic,
    apply_genre_specific_rules,
    DEFAULT_THRESHOLDS,
)
from novel_factory.models.chapter_contracts import ChapterBrief, RhythmBudgetResult


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════


def _chapter(has_pressure=False, has_agency=True, has_payoff=False,
             has_upgrade=False, mysteries_resolved=None, mysteries_introduced=None):
    """Create a chapter dict with metadata flags."""
    return {
        "content": "test content",
        "status": "published",
        "metadata": {
            "has_pressure": has_pressure,
            "has_protagonist_agency": has_agency,
            "has_payoff": has_payoff,
            "has_visible_upgrade": has_upgrade,
            "mysteries_resolved": mysteries_resolved or [],
            "mysteries_introduced": mysteries_introduced or [],
        },
    }


def _brief(mystery_actions=None):
    """Create a minimal brief dict."""
    return {
        "chapter_goal": "test goal",
        "reader_payoff": "test payoff",
        "protagonist_agency": "test agency",
        "forbidden_moves": [],
        "mystery_actions": mystery_actions or [],
    }


# ══════════════════════════════════════════════════════════════════════
# Test 1: detect_pressure_streak
# ══════════════════════════════════════════════════════════════════════


class TestPressureStreak:
    """Tests for detect_pressure_streak."""

    def test_empty_chapters(self):
        assert detect_pressure_streak([]) == 0

    def test_no_pressure(self):
        chapters = [_chapter(has_pressure=False) for _ in range(5)]
        assert detect_pressure_streak(chapters) == 0

    def test_all_pressure(self):
        chapters = [_chapter(has_pressure=True) for _ in range(5)]
        assert detect_pressure_streak(chapters) == 5

    def test_trailing_streak(self):
        chapters = [
            _chapter(has_pressure=False),
            _chapter(has_pressure=True),
            _chapter(has_pressure=True),
            _chapter(has_pressure=True),
        ]
        assert detect_pressure_streak(chapters) == 3

    def test_streak_broken(self):
        chapters = [
            _chapter(has_pressure=True),
            _chapter(has_pressure=True),
            _chapter(has_pressure=False),  # break
            _chapter(has_pressure=True),
        ]
        assert detect_pressure_streak(chapters) == 1

    def test_single_chapter_pressure(self):
        chapters = [_chapter(has_pressure=True)]
        assert detect_pressure_streak(chapters) == 1


# ══════════════════════════════════════════════════════════════════════
# Test 2: detect_passive_protagonist_streak
# ══════════════════════════════════════════════════════════════════════


class TestPassiveProtagonistStreak:
    """Tests for detect_passive_protagonist_streak."""

    def test_empty_chapters(self):
        assert detect_passive_protagonist_streak([]) == 0

    def test_active_protagonist(self):
        chapters = [_chapter(has_agency=True) for _ in range(5)]
        assert detect_passive_protagonist_streak(chapters) == 0

    def test_all_passive(self):
        chapters = [_chapter(has_agency=False) for _ in range(4)]
        assert detect_passive_protagonist_streak(chapters) == 4

    def test_trailing_passive(self):
        chapters = [
            _chapter(has_agency=True),
            _chapter(has_agency=False),
            _chapter(has_agency=False),
        ]
        assert detect_passive_protagonist_streak(chapters) == 2

    def test_streak_broken_by_active(self):
        chapters = [
            _chapter(has_agency=False),
            _chapter(has_agency=True),   # break
            _chapter(has_agency=False),
        ]
        assert detect_passive_protagonist_streak(chapters) == 1


# ══════════════════════════════════════════════════════════════════════
# Test 3: detect_payoff_gap
# ══════════════════════════════════════════════════════════════════════


class TestPayoffGap:
    """Tests for detect_payoff_gap."""

    def test_empty_chapters(self):
        assert detect_payoff_gap([]) == 0

    def test_immediate_payoff(self):
        chapters = [_chapter(has_payoff=True)]
        assert detect_payoff_gap(chapters) == 0

    def test_gap_of_3(self):
        chapters = [
            _chapter(has_payoff=True),
            _chapter(has_payoff=False),
            _chapter(has_payoff=False),
            _chapter(has_payoff=False),
        ]
        assert detect_payoff_gap(chapters) == 3

    def test_no_payoff_ever(self):
        chapters = [_chapter(has_payoff=False) for _ in range(7)]
        assert detect_payoff_gap(chapters) == 7

    def test_payoff_resets_gap(self):
        chapters = [
            _chapter(has_payoff=False),
            _chapter(has_payoff=False),
            _chapter(has_payoff=True),   # reset
            _chapter(has_payoff=False),
        ]
        assert detect_payoff_gap(chapters) == 1


# ══════════════════════════════════════════════════════════════════════
# Test 4: detect_visible_upgrade_gap
# ══════════════════════════════════════════════════════════════════════


class TestVisibleUpgradeGap:
    """Tests for detect_visible_upgrade_gap."""

    def test_empty_chapters(self):
        assert detect_visible_upgrade_gap([]) == 0

    def test_immediate_upgrade(self):
        chapters = [_chapter(has_upgrade=True)]
        assert detect_visible_upgrade_gap(chapters) == 0

    def test_gap_of_5(self):
        chapters = [_chapter(has_upgrade=False) for _ in range(5)]
        assert detect_visible_upgrade_gap(chapters) == 5

    def test_upgrade_resets_gap(self):
        chapters = [
            _chapter(has_upgrade=False),
            _chapter(has_upgrade=False),
            _chapter(has_upgrade=True),
            _chapter(has_upgrade=False),
        ]
        assert detect_visible_upgrade_gap(chapters) == 1


# ══════════════════════════════════════════════════════════════════════
# Test 5: count_new_mysteries
# ══════════════════════════════════════════════════════════════════════


class TestCountNewMysteries:
    """Tests for count_new_mysteries."""

    def test_no_mysteries(self):
        assert count_new_mysteries({}) == 0

    def test_empty_mystery_actions(self):
        assert count_new_mysteries({"mystery_actions": []}) == 0

    def test_introduce_mysteries(self):
        brief = {"mystery_actions": ["introduce new villain", "deepen old mystery"]}
        # "introduce new villain" matches "introduce", "deepen old mystery" matches neither
        assert count_new_mysteries(brief) == 1

    def test_only_introduce_counts(self):
        brief = {"mystery_actions": ["resolve old mystery", "deepen existing thread"]}
        assert count_new_mysteries(brief) == 0

    def test_mixed_actions(self):
        brief = {"mystery_actions": [
            "introduce new subplot",
            "resolve villain identity",
            "new clue about the artifact",
        ]}
        # "introduce" and "new" match
        assert count_new_mysteries(brief) == 2


# ══════════════════════════════════════════════════════════════════════
# Test 6: detect_mystery_answer_gap
# ══════════════════════════════════════════════════════════════════════


class TestMysteryAnswerGap:
    """Tests for detect_mystery_answer_gap."""

    def test_empty_chapters(self):
        assert detect_mystery_answer_gap([]) == 0

    def test_immediate_resolution(self):
        chapters = [_chapter(mysteries_resolved=["m1"])]
        assert detect_mystery_answer_gap(chapters) == 0

    def test_gap_of_4(self):
        chapters = [
            _chapter(mysteries_resolved=["m1"]),
            _chapter(mysteries_resolved=[]),
            _chapter(mysteries_resolved=[]),
            _chapter(mysteries_resolved=[]),
            _chapter(mysteries_resolved=[]),
        ]
        assert detect_mystery_answer_gap(chapters) == 4

    def test_no_resolution_ever(self):
        chapters = [_chapter(mysteries_resolved=[]) for _ in range(8)]
        assert detect_mystery_answer_gap(chapters) == 8


# ══════════════════════════════════════════════════════════════════════
# Test 7: Default blocking rules
# ══════════════════════════════════════════════════════════════════════


class TestBlockingRules:
    """Tests for the 4 default blocking rules."""

    def test_pressure_streak_blocking(self):
        """4+ consecutive pressure chapters should block."""
        chapters = [_chapter(has_pressure=True) for _ in range(4)]
        result = evaluate_deterministic(chapters, _brief())
        assert result.passed is False
        assert any("pressure_streak" in r for r in result.blocking_reasons)

    def test_passive_protagonist_blocking(self):
        """3+ consecutive passive chapters should block."""
        chapters = [_chapter(has_agency=False) for _ in range(3)]
        result = evaluate_deterministic(chapters, _brief())
        assert result.passed is False
        assert any("passive_protagonist" in r for r in result.blocking_reasons)

    def test_payoff_gap_blocking(self):
        """5+ chapters without payoff should block."""
        chapters = [_chapter(has_payoff=False) for _ in range(5)]
        result = evaluate_deterministic(chapters, _brief())
        assert result.passed is False
        assert any("payoff_gap" in r for r in result.blocking_reasons)

    def test_visible_upgrade_gap_blocking(self):
        """8+ chapters without upgrade should block."""
        chapters = [_chapter(has_upgrade=False) for _ in range(8)]
        result = evaluate_deterministic(chapters, _brief())
        assert result.passed is False
        assert any("upgrade_gap" in r for r in result.blocking_reasons)

    def test_mystery_answer_gap_blocking(self):
        """6+ chapters without mystery resolution should block."""
        chapters = [_chapter(mysteries_resolved=[]) for _ in range(6)]
        result = evaluate_deterministic(chapters, _brief())
        assert result.passed is False
        assert any("mystery_gap" in r for r in result.blocking_reasons)


# ══════════════════════════════════════════════════════════════════════
# Test 8: Warning conditions
# ══════════════════════════════════════════════════════════════════════


class TestWarnings:
    """Tests for warning (non-blocking) conditions."""

    def test_new_mysteries_warning(self):
        """3+ new mysteries in one chapter triggers warning."""
        brief = _brief(mystery_actions=[
            "introduce villain A",
            "introduce villain B",
            "introduce new prophecy",
        ])
        result = evaluate_deterministic([], brief)
        assert result.passed is True  # not blocking
        assert len(result.warnings) > 0
        assert any("new_mysteries" in w for w in result.warnings)

    def test_below_warning_threshold(self):
        """2 new mysteries should not trigger warning."""
        brief = _brief(mystery_actions=[
            "introduce villain A",
            "deepen existing mystery",
        ])
        result = evaluate_deterministic([], brief)
        assert len(result.warnings) == 0


# ══════════════════════════════════════════════════════════════════════
# Test 9: Genre-specific rules
# ══════════════════════════════════════════════════════════════════════


class TestGenreSpecificRules:
    """Tests for genre-specific rhythm rules."""

    def test_cultivation_upgrade_gap_warning(self):
        """Cultivation genre warns after 5 chapters without upgrade."""
        from novel_factory.models.chapter_contracts import RhythmBudgetFlags

        result = RhythmBudgetResult(
            passed=True,
            flags=RhythmBudgetFlags(visible_upgrade_gap=6),
        )
        genre = {"genre_id": "cultivation_upgrade"}
        updated = apply_genre_specific_rules(result, genre)
        assert any("cultivation" in w.lower() for w in updated.warnings)

    def test_mystery_genre_stricter_blocking(self):
        """Mystery genre blocks after 4 chapters without resolution."""
        from novel_factory.models.chapter_contracts import RhythmBudgetFlags

        result = RhythmBudgetResult(
            passed=True,
            flags=RhythmBudgetFlags(mystery_answer_gap=5),
        )
        genre = {"genre_id": "suspense_mystery"}
        updated = apply_genre_specific_rules(result, genre)
        assert updated.passed is False
        assert any("mystery_genre" in r for r in updated.blocking_reasons)

    def test_mystery_genre_within_limit(self):
        """Mystery genre passes with 3 chapters gap."""
        from novel_factory.models.chapter_contracts import RhythmBudgetFlags

        result = RhythmBudgetResult(
            passed=True,
            flags=RhythmBudgetFlags(mystery_answer_gap=3),
        )
        genre = {"genre_id": "suspense_mystery"}
        updated = apply_genre_specific_rules(result, genre)
        assert updated.passed is True

    def test_unknown_genre_no_extra_rules(self):
        """Unknown genre should not add extra rules."""
        from novel_factory.models.chapter_contracts import RhythmBudgetFlags

        result = RhythmBudgetResult(
            passed=True,
            flags=RhythmBudgetFlags(visible_upgrade_gap=6),
        )
        genre = {"genre_id": "sci_fi"}
        updated = apply_genre_specific_rules(result, genre)
        assert updated.passed is True
        assert len(updated.warnings) == 0


# ══════════════════════════════════════════════════════════════════════
# Test 10: evaluate_deterministic integration
# ══════════════════════════════════════════════════════════════════════


class TestEvaluateDeterministic:
    """Integration tests for evaluate_deterministic."""

    def test_all_good_passes(self):
        """Healthy rhythm should pass."""
        chapters = [
            _chapter(has_pressure=False, has_agency=True, has_payoff=True, has_upgrade=True),
            _chapter(has_pressure=False, has_agency=True, has_payoff=True, has_upgrade=False),
        ]
        result = evaluate_deterministic(chapters, _brief())
        assert result.passed is True
        assert len(result.blocking_reasons) == 0

    def test_multiple_violations(self):
        """Multiple violations should all be reported."""
        chapters = [
            _chapter(has_pressure=True, has_agency=False, has_payoff=False, has_upgrade=False),
            _chapter(has_pressure=True, has_agency=False, has_payoff=False, has_upgrade=False),
            _chapter(has_pressure=True, has_agency=False, has_payoff=False, has_upgrade=False),
            _chapter(has_pressure=True, has_agency=False, has_payoff=False, has_upgrade=False),
        ]
        result = evaluate_deterministic(chapters, _brief())
        assert result.passed is False
        assert len(result.blocking_reasons) >= 2  # pressure(4) + passive(4) + payoff_gap(4)

    def test_threshold_override(self):
        """Custom thresholds should override defaults."""
        chapters = [_chapter(has_pressure=True) for _ in range(2)]
        # Default is 4, but override to 2
        result = evaluate_deterministic(chapters, _brief(), thresholds={"max_pressure_streak": 2})
        assert result.passed is False

    def test_genre_contract_thresholds(self):
        """Genre contract thresholds should be applied."""
        chapters = [_chapter(has_pressure=True) for _ in range(3)]
        genre_contract = {"rhythm_thresholds": {"max_pressure_streak": 3}}
        result = evaluate_deterministic(chapters, _brief(), genre_contract=genre_contract)
        assert result.passed is False

    def test_flags_populated(self):
        """Result flags should reflect actual chapter metrics."""
        chapters = [
            _chapter(has_pressure=True, has_agency=False, has_payoff=False),
            _chapter(has_pressure=True, has_agency=False, has_payoff=True),
        ]
        result = evaluate_deterministic(chapters, _brief())
        assert result.flags.pressure_streak == 2
        assert result.flags.passive_protagonist_streak == 2
        assert result.flags.payoff_gap == 0  # last chapter has payoff

    def test_empty_input(self):
        """Empty chapters and brief should return a passing result."""
        result = evaluate_deterministic([], _brief())
        assert result.passed is True
        assert result.flags.pressure_streak == 0


# ══════════════════════════════════════════════════════════════════════
# Test 11: Default thresholds
# ══════════════════════════════════════════════════════════════════════


class TestDefaultThresholds:
    """Test default threshold values match spec."""

    def test_pressure_threshold(self):
        assert DEFAULT_THRESHOLDS["max_pressure_streak"] == 4

    def test_passive_protagonist_threshold(self):
        assert DEFAULT_THRESHOLDS["max_passive_protagonist_streak"] == 3

    def test_payoff_gap_threshold(self):
        assert DEFAULT_THRESHOLDS["max_payoff_gap"] == 5

    def test_upgrade_gap_threshold(self):
        assert DEFAULT_THRESHOLDS["max_visible_upgrade_gap"] == 8

    def test_mystery_gap_threshold(self):
        assert DEFAULT_THRESHOLDS["max_mystery_answer_gap"] == 6

    def test_new_mysteries_threshold(self):
        assert DEFAULT_THRESHOLDS["max_new_mysteries_per_chapter"] == 3

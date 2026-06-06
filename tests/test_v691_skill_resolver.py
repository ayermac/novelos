"""Tests for v6.9.1 Phase 4: Dynamic Skill Scheduling.

Tests the editor_skill_resolver module which determines which skills
should run based on genre, chapter position, and sampling history.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from novel_factory.skills.editor_skill_resolver import (
    resolve_active_skills,
    should_skip_sampling,
    _extract_genre,
    _passes_chapter_position_rule,
    _is_genre_skill_active,
    CHAPTER_POSITIONAL_RULES,
    GENRE_SKILL_MAP,
    DEFAULT_SAMPLING_INTERVALS,
)


# ── A. Chapter Position Rules ────────────────────────────────────────


class TestChapterPositionRules:
    """Test chapter position filtering."""

    def test_opening_hook_only_for_chapter1(self):
        """opening-hook-checker only runs for chapter 1."""
        assert _passes_chapter_position_rule("opening-hook-checker", 1) is True

    def test_opening_hook_skipped_for_chapter2(self):
        """opening-hook-checker skipped for chapter 2+."""
        assert _passes_chapter_position_rule("opening-hook-checker", 2) is False
        assert _passes_chapter_position_rule("opening-hook-checker", 50) is False

    def test_non_positional_skill_always_passes(self):
        """Skills without positional rules always pass."""
        assert _passes_chapter_position_rule("word-count-gate", 1) is True
        assert _passes_chapter_position_rule("word-count-gate", 50) is True
        assert _passes_chapter_position_rule("death-penalty", 1) is True
        assert _passes_chapter_position_rule("death-penalty", 99) is True

    def test_resolve_removes_opening_hook_for_later_chapters(self):
        """resolve_active_skills filters opening-hook-checker for ch2+."""
        skill_ids = ["word-count-gate", "opening-hook-checker", "death-penalty"]
        result = resolve_active_skills(
            project_id="test",
            chapter_number=2,
            genre_contract=None,
            skill_ids=skill_ids,
        )
        assert "opening-hook-checker" not in result
        assert "word-count-gate" in result
        assert "death-penalty" in result

    def test_resolve_keeps_opening_hook_for_chapter1(self):
        """resolve_active_skills keeps opening-hook-checker for ch1."""
        skill_ids = ["word-count-gate", "opening-hook-checker", "death-penalty"]
        result = resolve_active_skills(
            project_id="test",
            chapter_number=1,
            genre_contract=None,
            skill_ids=skill_ids,
        )
        assert "opening-hook-checker" in result


# ── B. Genre Rules ───────────────────────────────────────────────────


class TestGenreRules:
    """Test genre-based skill filtering."""

    def test_mystery_genre_enables_mystery_skill(self):
        """Mystery genre activates mystery-integrity-check."""
        assert _is_genre_skill_active("mystery-integrity-check", "悬疑") is True

    def test_mystery_genre_english(self):
        """English mystery genre activates mystery-integrity-check."""
        assert _is_genre_skill_active("mystery-integrity-check", "mystery") is True
        assert _is_genre_skill_active("mystery-integrity-check", "thriller") is True

    def test_mystery_genre_with_suffix(self):
        """Genre string containing keyword activates skill."""
        assert _is_genre_skill_active("mystery-integrity-check", "都市悬疑") is True
        assert _is_genre_skill_active("mystery-integrity-check", "悬疑推理") is True

    def test_non_mystery_genre_disables_mystery_skill(self):
        """Non-mystery genre does not activate mystery-integrity-check."""
        assert _is_genre_skill_active("mystery-integrity-check", "言情") is False
        assert _is_genre_skill_active("mystery-integrity-check", "玄幻") is False
        assert _is_genre_skill_active("mystery-integrity-check", "") is False

    def test_resolve_enables_mystery_for_suspense_genre(self):
        """resolve_active_skills enables mystery-integrity-check for suspense."""
        skill_ids = ["word-count-gate", "mystery-integrity-check"]
        result = resolve_active_skills(
            project_id="test",
            chapter_number=5,
            genre_contract={"genre": "悬疑"},
            skill_ids=skill_ids,
        )
        assert "mystery-integrity-check" in result

    def test_resolve_disables_mystery_for_romance_genre(self):
        """resolve_active_skills disables mystery-integrity-check for romance."""
        skill_ids = ["word-count-gate", "mystery-integrity-check"]
        result = resolve_active_skills(
            project_id="test",
            chapter_number=5,
            genre_contract={"genre": "言情"},
            skill_ids=skill_ids,
        )
        assert "mystery-integrity-check" not in result
        assert "word-count-gate" in result

    def test_resolve_disables_mystery_when_no_genre(self):
        """mystery-integrity-check disabled when no genre contract."""
        skill_ids = ["word-count-gate", "mystery-integrity-check"]
        result = resolve_active_skills(
            project_id="test",
            chapter_number=5,
            genre_contract=None,
            skill_ids=skill_ids,
        )
        assert "mystery-integrity-check" not in result


# ── C. Genre Extraction ─────────────────────────────────────────────


class TestGenreExtraction:
    """Test genre extraction from contracts."""

    def test_extract_from_dict(self):
        assert _extract_genre({"genre": "悬疑"}) == "悬疑"

    def test_extract_empty_dict(self):
        assert _extract_genre({}) == ""

    def test_extract_none(self):
        assert _extract_genre(None) == ""

    def test_extract_with_whitespace(self):
        assert _extract_genre({"genre": "  悬疑  "}) == "悬疑"

    def test_extract_case_insensitive(self):
        assert _extract_genre({"genre": "Mystery"}) == "mystery"


# ── D. Sampling Mode ────────────────────────────────────────────────


class TestSamplingMode:
    """Test sampling-based skill skipping."""

    def test_no_sampling_without_repo(self):
        """No sampling skip when repo is None."""
        result = resolve_active_skills(
            project_id="test",
            chapter_number=5,
            genre_contract=None,
            skill_ids=["word-count-gate"],
            repo=None,
        )
        assert "word-count-gate" in result

    def test_no_sampling_for_unsupported_skill(self):
        """Skills without sampling config are never skipped."""
        repo = MagicMock()
        result = resolve_active_skills(
            project_id="test",
            chapter_number=5,
            genre_contract=None,
            skill_ids=["continuity-gate"],
            repo=repo,
        )
        assert "continuity-gate" in result
        repo.get_skill_runs.assert_not_called()

    def test_sampling_skip_when_consecutive_passes(self):
        """Skill is skipped when it has enough consecutive passes."""
        repo = MagicMock()
        # word-count-gate has sampling_interval=3
        # Simulate 3 consecutive passes at chapters 2,3,4
        repo.get_skill_runs.return_value = [
            {"ok": True, "chapter_number": 4},
            {"ok": True, "chapter_number": 3},
            {"ok": True, "chapter_number": 2},
        ]
        result = should_skip_sampling("test", "word-count-gate", 5, repo)
        assert result is True  # ch5 is within interval from ch4

    def test_sampling_no_skip_at_interval_boundary(self):
        """Skill runs when exactly at interval boundary."""
        repo = MagicMock()
        repo.get_skill_runs.return_value = [
            {"ok": True, "chapter_number": 3},
            {"ok": True, "chapter_number": 2},
            {"ok": True, "chapter_number": 1},
        ]
        # interval=3, latest=3, current=6 → chapters_since=3 → not skipped
        result = should_skip_sampling("test", "word-count-gate", 6, repo)
        assert result is False

    def test_sampling_reverts_on_failure(self):
        """Skill runs normally after a failure."""
        repo = MagicMock()
        repo.get_skill_runs.return_value = [
            {"ok": False, "chapter_number": 4},  # failure
            {"ok": True, "chapter_number": 3},
            {"ok": True, "chapter_number": 2},
        ]
        result = should_skip_sampling("test", "word-count-gate", 5, repo)
        assert result is False

    def test_sampling_no_skip_insufficient_history(self):
        """Skill runs when not enough history."""
        repo = MagicMock()
        repo.get_skill_runs.return_value = [
            {"ok": True, "chapter_number": 4},
        ]
        result = should_skip_sampling("test", "word-count-gate", 5, repo)
        assert result is False

    def test_sampling_handles_repo_error(self):
        """Skill runs normally when repo raises exception."""
        repo = MagicMock()
        repo.get_skill_runs.side_effect = Exception("db error")
        result = should_skip_sampling("test", "word-count-gate", 5, repo)
        assert result is False


# ── E. Integration ──────────────────────────────────────────────────


class TestResolveIntegration:
    """Integration tests for resolve_active_skills."""

    def test_combined_rules(self):
        """Test all three rules together."""
        repo = MagicMock()
        # word-count-gate: sampling_interval=3, simulate 3 consecutive passes
        repo.get_skill_runs.return_value = [
            {"ok": True, "chapter_number": 4},
            {"ok": True, "chapter_number": 3},
            {"ok": True, "chapter_number": 2},
        ]

        skill_ids = [
            "word-count-gate",      # sampling: skip (ch5 within interval)
            "opening-hook-checker",  # position: skip (ch5 > 1)
            "mystery-integrity-check",  # genre: skip (言情)
            "death-penalty",         # no rule: keep
            "continuity-gate",       # no rule: keep
        ]

        result = resolve_active_skills(
            project_id="test",
            chapter_number=5,
            genre_contract={"genre": "言情"},
            skill_ids=skill_ids,
            repo=repo,
        )

        assert "death-penalty" in result
        assert "continuity-gate" in result
        assert "word-count-gate" not in result  # sampling skip
        assert "opening-hook-checker" not in result  # position skip
        assert "mystery-integrity-check" not in result  # genre skip

    def test_mystery_chapter1_with_sampling(self):
        """Mystery genre, chapter 1, with sampling."""
        repo = MagicMock()
        repo.get_skill_runs.return_value = []  # No history

        skill_ids = [
            "word-count-gate",
            "opening-hook-checker",
            "mystery-integrity-check",
            "death-penalty",
        ]

        result = resolve_active_skills(
            project_id="test",
            chapter_number=1,
            genre_contract={"genre": "悬疑"},
            skill_ids=skill_ids,
            repo=repo,
        )

        assert "word-count-gate" in result
        assert "opening-hook-checker" in result  # ch1
        assert "mystery-integrity-check" in result  # 悬疑
        assert "death-penalty" in result
